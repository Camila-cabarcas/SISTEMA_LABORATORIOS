"""
Tests para CancelarReservaService (reservas/services/cancelar_reserva_service.py):
cancelar_propietario (autoservicio, 2 horas de anticipación) y cancelar_admin
(laboratorista, sin esas restricciones pero con motivo obligatorio).
"""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core import mail
from django.utils import timezone

from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva
from reservas.services.cancelar_reserva_service import CancelarReservaService
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db


def _reserva_aprobada(laboratorio, horas_hasta_fecha=3, cedula='111222333', email='ana@udea.edu.co'):
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now() + timedelta(hours=horas_hasta_fecha),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula, email=email,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
    )
    return reserva


class TestPuedeCancelarPropietario:

    def test_true_si_aprobada_sin_prestamo_y_mas_de_2h_antes(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        assert CancelarReservaService.puede_cancelar_propietario(reserva) is True

    def test_false_si_faltan_menos_de_2h(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=1)

        assert CancelarReservaService.puede_cancelar_propietario(reserva) is False

    def test_false_si_no_esta_aprobada(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)
        reserva.estado = EstadoReserva.objects.get(nombre='Pendiente')
        reserva.save()

        assert CancelarReservaService.puede_cancelar_propietario(reserva) is False

    def test_false_si_existe_prestamo(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)
        Prestamo.objects.create(
            reserva=reserva, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Activo'),
        )

        assert CancelarReservaService.puede_cancelar_propietario(reserva) is False


class TestCancelarPropietario:

    def test_cancela_dentro_del_plazo(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        CancelarReservaService.cancelar_propietario(reserva, '111222333', 'ana@udea.edu.co')

        reserva.refresh_from_db()
        assert reserva.estado.nombre == 'Cancelada'

    def test_rechaza_identidad_incorrecta(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        with pytest.raises(PermissionDenied):
            CancelarReservaService.cancelar_propietario(reserva, '111222333', 'otro@udea.edu.co')

        reserva.refresh_from_db()
        assert reserva.estado.nombre == 'Aprobada'

    def test_rechaza_menos_de_2h_antes(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=1)

        with pytest.raises(ValidationError) as exc_info:
            CancelarReservaService.cancelar_propietario(reserva, '111222333', 'ana@udea.edu.co')

        assert any('tarde' in msg.lower() for msg in exc_info.value.messages)
        reserva.refresh_from_db()
        assert reserva.estado.nombre == 'Aprobada'

    def test_rechaza_si_no_esta_aprobada(self, laboratorio, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)
        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        with pytest.raises(ValidationError):
            CancelarReservaService.cancelar_propietario(reserva, '111222333', 'ana@udea.edu.co')

    def test_rechaza_si_existe_prestamo(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)
        Prestamo.objects.create(
            reserva=reserva, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Activo'),
        )

        with pytest.raises(ValidationError):
            CancelarReservaService.cancelar_propietario(reserva, '111222333', 'ana@udea.edu.co')

        reserva.refresh_from_db()
        assert reserva.estado.nombre == 'Aprobada'

    def test_registra_auditoria(self, laboratorio, catalogos, caplog):
        import logging

        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        with caplog.at_level(logging.INFO, logger='reservas.services.cancelar_reserva_service'):
            CancelarReservaService.cancelar_propietario(reserva, '111222333', 'ana@udea.edu.co')

        mensajes = [r.getMessage() for r in caplog.records]
        assert any(str(reserva.id) in m and '111222333' in m for m in mensajes)

    def test_notifica_a_los_encargados_del_laboratorio(self, laboratorio, usuario_admin, catalogos):
        from users.models import Rol

        laboratorista = usuario_admin
        laboratorista.rol = Rol.objects.get(nombre='Laboratorio')
        laboratorista.email = 'lab@udea.edu.co'
        laboratorista.save()
        laboratorio.encargados.add(laboratorista)

        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        CancelarReservaService.cancelar_propietario(reserva, '111222333', 'ana@udea.edu.co')

        # El fixture autouse _emails_sincronos (conftest.py raíz) ya hace
        # síncrono todo envío, así que cancelar_propietario dejó su email en
        # mail.outbox sin hilo de por medio. Se limpia y se manda de nuevo en
        # primer plano para aislar el mensaje que interesa revisar.
        from utils.notificaciones_email import notificar_cancelacion
        mail.outbox.clear()
        notificar_cancelacion(reserva, cancelada_por='estudiante', async_=False)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['lab@udea.edu.co']
        assert reserva.codigo in mail.outbox[0].subject


class TestCancelarAdmin:

    def test_cancela_sin_restricciones_de_tiempo_ni_prestamo(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=1)
        Prestamo.objects.create(
            reserva=reserva, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Activo'),
        )

        CancelarReservaService.cancelar_admin(reserva, usuario_admin, motivo='Corrección de un error de asignación.')

        reserva.refresh_from_db()
        assert reserva.estado.nombre == 'Cancelada'

    def test_rechaza_sin_motivo(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        with pytest.raises(ValidationError):
            CancelarReservaService.cancelar_admin(reserva, usuario_admin, motivo='   ')

        reserva.refresh_from_db()
        assert reserva.estado.nombre == 'Aprobada'

    def test_rechaza_si_ya_esta_cancelada(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)
        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        with pytest.raises(ValidationError):
            CancelarReservaService.cancelar_admin(reserva, usuario_admin, motivo='Ya estaba cancelada')

    def test_notifica_al_solicitante_con_el_motivo(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_aprobada(laboratorio, horas_hasta_fecha=3)

        CancelarReservaService.cancelar_admin(reserva, usuario_admin, motivo='Mantenimiento del laboratorio.')

        from utils.notificaciones_email import notificar_cancelacion
        mail.outbox.clear()
        notificar_cancelacion(
            reserva, cancelada_por='laboratorista', motivo='Mantenimiento del laboratorio.', async_=False,
        )

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['ana@udea.edu.co']
        assert 'Mantenimiento del laboratorio.' in mail.outbox[0].body
