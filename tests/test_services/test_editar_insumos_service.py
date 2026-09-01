"""
Tests para EditarInsumosReservaService (reservas/services/editar_insumos_service.py):
acceso (laboratorista del laboratorio / estado Aprobada / sin Prestamo),
validaciones de insumos (stock, cantidad, duplicados), auditoría (log) y
notificación por email al estudiante.
"""
import logging
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario
from laboratorio.models import Laboratorio
from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva, ReservaInsumo
from reservas.services.editar_insumos_service import EditarInsumosReservaService
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db


def _crear_insumo_con_stock(nombre, cantidad, laboratorio=None):
    insumo = Insumo.objects.create(nombre=nombre, descripcion='Para tests', stock_minimo=0)
    estado_disponible = EstadoItem.objects.get(nombre='Disponible')
    for i in range(cantidad):
        ItemInventario.objects.create(
            codigo=f'{nombre}-{i}', insumo=insumo, estado=estado_disponible, laboratorio=laboratorio,
        )
    return insumo


@pytest.fixture
def reserva_aprobada(laboratorio, catalogos):
    # Sin email en la SolicitudReserva a propósito: guardar() dispara su
    # propia notificar_cambios_o_prestamo_listo en un hilo aparte (async_=True
    # por default) apenas termina — si hubiera email acá, ese hilo mandaría un
    # mensaje real a mail.outbox en paralelo con cualquier assert posterior,
    # con condición de carrera. Los tests que sí necesitan revisar contenido
    # de email lo setean DESPUÉS de llamar a guardar() (mismo patrón que
    # tests/test_services/test_notificaciones_email.py).
    estado_aprobada = EstadoReserva.objects.get(nombre='Aprobada')
    fecha = timezone.now() + timedelta(days=1)
    reserva = Reserva.objects.create(fecha_reserva=fecha, estado=estado_aprobada)
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula='111222333',
        laboratorio=laboratorio, fecha_reserva=fecha, reserva=reserva,
    )
    return reserva


@pytest.fixture
def insumo_stock(laboratorio):
    return _crear_insumo_con_stock('Vaso precipitado', 5, laboratorio)


class TestVerificarAcceso:

    def test_laboratorista_del_laboratorio_correcto_puede(
        self, reserva_aprobada, usuario_laboratorista,
    ):
        laboratorio = EditarInsumosReservaService.verificar_acceso(
            reserva_aprobada, usuario_laboratorista,
        )
        assert laboratorio == reserva_aprobada.solicitud.first().laboratorio

    def test_laboratorista_de_otro_laboratorio_es_rechazado(
        self, reserva_aprobada, catalogos,
    ):
        from users.models import Rol, Usuario

        otro_laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Física', ubicacion='Bloque 9',
        )
        otro_laboratorista = Usuario.objects.create_user(
            username='lab_otro', password='x', rol=Rol.objects.get(nombre='Laboratorio'),
        )
        otro_laboratorio.encargados.add(otro_laboratorista)

        with pytest.raises(PermissionDenied):
            EditarInsumosReservaService.verificar_acceso(reserva_aprobada, otro_laboratorista)

        assert EditarInsumosReservaService.puede_editar(reserva_aprobada, otro_laboratorista) is False

    def test_administrador_puede_de_cualquier_laboratorio(
        self, reserva_aprobada, usuario_admin,
    ):
        # No lanza, sin importar que usuario_admin no esté en encargados.
        EditarInsumosReservaService.verificar_acceso(reserva_aprobada, usuario_admin)

    @pytest.mark.parametrize('nombre_estado', ['Pendiente', 'Cancelada', 'Expirada'])
    def test_rechaza_si_no_esta_aprobada(
        self, reserva_aprobada, usuario_laboratorista, nombre_estado,
    ):
        reserva_aprobada.estado = EstadoReserva.objects.get(nombre=nombre_estado)
        reserva_aprobada.save()

        with pytest.raises(PermissionDenied):
            EditarInsumosReservaService.verificar_acceso(reserva_aprobada, usuario_laboratorista)

    def test_rechaza_si_ya_existe_prestamo(
        self, reserva_aprobada, usuario_laboratorista, usuario_admin,
    ):
        Prestamo.objects.create(
            reserva=reserva_aprobada, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Activo'),
        )

        with pytest.raises(PermissionDenied):
            EditarInsumosReservaService.verificar_acceso(reserva_aprobada, usuario_laboratorista)

        assert EditarInsumosReservaService.puede_editar(reserva_aprobada, usuario_laboratorista) is False


class TestGuardar:

    def test_agrega_insumo_nuevo(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        agregados, quitados, cambiados = EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista,
            [{'insumo_id': insumo_stock.id, 'cantidad': 3}],
        )

        assert [a['insumo'] for a in agregados] == [insumo_stock]
        assert quitados == []
        assert cambiados == []
        assert ReservaInsumo.objects.get(reserva=reserva_aprobada, insumo=insumo_stock).cantidad == 3

    def test_quita_insumo_existente(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        ReservaInsumo.objects.create(reserva=reserva_aprobada, insumo=insumo_stock, cantidad=2)

        agregados, quitados, cambiados = EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista, [],
        )

        assert agregados == []
        assert [q['insumo'] for q in quitados] == [insumo_stock]
        assert cambiados == []
        assert not ReservaInsumo.objects.filter(reserva=reserva_aprobada).exists()

    def test_cambia_cantidad_de_insumo_existente(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        ReservaInsumo.objects.create(reserva=reserva_aprobada, insumo=insumo_stock, cantidad=1)

        agregados, quitados, cambiados = EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista,
            [{'insumo_id': insumo_stock.id, 'cantidad': 4}],
        )

        assert agregados == []
        assert quitados == []
        assert len(cambiados) == 1
        assert cambiados[0]['cantidad_anterior'] == 1
        assert cambiados[0]['cantidad_nueva'] == 4
        assert ReservaInsumo.objects.get(reserva=reserva_aprobada, insumo=insumo_stock).cantidad == 4

    def test_no_cambia_fecha_laboratorio_ni_estado_de_la_reserva(
        self, reserva_aprobada, usuario_laboratorista, insumo_stock,
    ):
        fecha_original = reserva_aprobada.fecha_reserva
        laboratorio_original = reserva_aprobada.solicitud.first().laboratorio_id

        EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista,
            [{'insumo_id': insumo_stock.id, 'cantidad': 2}],
        )

        reserva_aprobada.refresh_from_db()
        assert reserva_aprobada.fecha_reserva == fecha_original
        assert reserva_aprobada.estado.nombre == 'Aprobada'
        assert reserva_aprobada.solicitud.first().laboratorio_id == laboratorio_original

    def test_rechaza_cantidad_menor_a_1(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        with pytest.raises(ValidationError):
            EditarInsumosReservaService.guardar(
                reserva_aprobada, usuario_laboratorista,
                [{'insumo_id': insumo_stock.id, 'cantidad': 0}],
            )
        assert not ReservaInsumo.objects.filter(reserva=reserva_aprobada).exists()

    def test_rechaza_insumo_duplicado(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        with pytest.raises(ValidationError):
            EditarInsumosReservaService.guardar(
                reserva_aprobada, usuario_laboratorista,
                [
                    {'insumo_id': insumo_stock.id, 'cantidad': 1},
                    {'insumo_id': insumo_stock.id, 'cantidad': 2},
                ],
            )
        assert not ReservaInsumo.objects.filter(reserva=reserva_aprobada).exists()

    def test_rechaza_stock_insuficiente(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        # insumo_stock tiene 5 ítems 'Disponible' -> pedir 6 debe fallar.
        with pytest.raises(ValidationError) as exc_info:
            EditarInsumosReservaService.guardar(
                reserva_aprobada, usuario_laboratorista,
                [{'insumo_id': insumo_stock.id, 'cantidad': 6}],
            )
        assert any('Stock insuficiente' in msg for msg in exc_info.value.messages)
        assert not ReservaInsumo.objects.filter(reserva=reserva_aprobada).exists()

    def test_rechaza_si_no_es_laboratorista_del_lab(
        self, reserva_aprobada, insumo_stock, catalogos,
    ):
        from users.models import Rol, Usuario

        otro_laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Física', ubicacion='Bloque 9',
        )
        otro_laboratorista = Usuario.objects.create_user(
            username='lab_otro_guardar', password='x', rol=Rol.objects.get(nombre='Laboratorio'),
        )
        otro_laboratorio.encargados.add(otro_laboratorista)

        with pytest.raises(PermissionDenied):
            EditarInsumosReservaService.guardar(
                reserva_aprobada, otro_laboratorista,
                [{'insumo_id': insumo_stock.id, 'cantidad': 1}],
            )
        assert not ReservaInsumo.objects.filter(reserva=reserva_aprobada).exists()


class TestAuditoria:

    def test_registra_log_con_usuario_y_reserva(
        self, reserva_aprobada, usuario_laboratorista, insumo_stock, caplog,
    ):
        with caplog.at_level(logging.INFO, logger='reservas.services.editar_insumos_service'):
            EditarInsumosReservaService.guardar(
                reserva_aprobada, usuario_laboratorista,
                [{'insumo_id': insumo_stock.id, 'cantidad': 2}],
            )

        mensajes = [r.getMessage() for r in caplog.records]
        assert any(
            usuario_laboratorista.username in m and str(reserva_aprobada.id) in m
            for m in mensajes
        )


class TestNotificacion:

    def test_dispara_notificar_cambios_o_prestamo_listo_con_el_diff(
        self, reserva_aprobada, usuario_laboratorista, insumo_stock, monkeypatch,
    ):
        llamadas = []
        monkeypatch.setattr(
            'utils.notificaciones_email.notificar_cambios_o_prestamo_listo',
            lambda reserva, tipo='cambios', **kwargs: llamadas.append((reserva, tipo, kwargs)),
        )

        EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista,
            [{'insumo_id': insumo_stock.id, 'cantidad': 2}],
        )

        assert len(llamadas) == 1
        reserva_llamada, tipo, kwargs = llamadas[0]
        assert reserva_llamada == reserva_aprobada
        assert tipo == 'cambios'
        assert [a['insumo'] for a in kwargs['agregados']] == [insumo_stock]
        assert kwargs['quitados'] == []
        assert kwargs['cambiados'] == []

    def test_no_notifica_si_no_hubo_cambios(
        self, reserva_aprobada, usuario_laboratorista, insumo_stock, monkeypatch,
    ):
        ReservaInsumo.objects.create(reserva=reserva_aprobada, insumo=insumo_stock, cantidad=2)

        llamadas = []
        monkeypatch.setattr(
            'utils.notificaciones_email.notificar_cambios_o_prestamo_listo',
            lambda *args, **kwargs: llamadas.append(args),
        )

        EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista,
            [{'insumo_id': insumo_stock.id, 'cantidad': 2}],
        )

        assert llamadas == []

    def test_email_llega_al_estudiante(self, reserva_aprobada, usuario_laboratorista, insumo_stock):
        from utils.notificaciones_email import notificar_cambios_o_prestamo_listo

        agregados, quitados, cambiados = EditarInsumosReservaService.guardar(
            reserva_aprobada, usuario_laboratorista,
            [{'insumo_id': insumo_stock.id, 'cantidad': 2}],
        )

        # reserva_aprobada no tiene email hasta acá (ver el fixture) para
        # que el hilo en segundo plano que dispara guardar() no encuentre
        # destinatario; se setea y se llama de nuevo en primer plano
        # (async_=False) para poder revisar mail.outbox sin condición de
        # carrera con ese hilo.
        solicitud = reserva_aprobada.solicitud.first()
        solicitud.email = 'ana@udea.edu.co'
        solicitud.save()

        notificar_cambios_o_prestamo_listo(
            reserva_aprobada, tipo='cambios',
            agregados=agregados, quitados=quitados, cambiados=cambiados, async_=False,
        )

        assert len(mail.outbox) == 1
        enviado = mail.outbox[0]
        assert enviado.to == ['ana@udea.edu.co']
        assert reserva_aprobada.codigo in enviado.subject
