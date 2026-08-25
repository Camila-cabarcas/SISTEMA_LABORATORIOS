"""
Tests para utils/notificaciones_email.py y
prestamos/services/recordatorio_devolucion_service.py: resolución del
destinatario y que cada notificación efectivamente encole un email (usando
django.core.mail.outbox — Django cambia EMAIL_BACKEND a locmem para tests
automáticamente, así que esto nunca golpea la API real de SendGrid).
"""
from datetime import time
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command

from prestamos.services.recordatorio_devolucion_service import RecordatorioDevolucionService
from solicitudes.models import SolicitudReserva
from utils.notificaciones_email import (
    _email_y_nombre,
    notificar_devolucion_completada,
    notificar_prestamo_confirmado,
    notificar_reserva_confirmada,
)

pytestmark = pytest.mark.django_db


def _vincular_solicitud(reserva, laboratorio, usuario=None, cedula='999999999'):
    """SolicitudReserva vinculada a `reserva`, tal como queda tras
    SolicitudReserva.crear_reserva() — necesaria para que
    _solicitud_de_prestamo/_solicitud_de_reserva encuentren algo."""
    return SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula, usuario=usuario,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva,
        hora_inicio=time(8, 0), hora_fin=time(10, 0), reserva=reserva,
    )


class TestEmailYNombre:

    def test_usa_email_del_usuario_si_existe(self, solicitud_valida, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        solicitud_valida.usuario = usuario_admin
        solicitud_valida.save()

        email, nombre = _email_y_nombre(solicitud_valida)

        assert email == 'admin@example.com'
        assert nombre == 'Juan Pérez'

    def test_cae_a_email_de_la_solicitud_sin_usuario(self, solicitud_valida):
        solicitud_valida.email = 'juan@example.com'
        solicitud_valida.save()

        email, nombre = _email_y_nombre(solicitud_valida)

        assert email == 'juan@example.com'

    def test_sin_ningun_email_devuelve_none(self, solicitud_valida):
        email, nombre = _email_y_nombre(solicitud_valida)

        assert email is None
        assert nombre == 'Juan Pérez'

    def test_solicitud_none_devuelve_none(self):
        assert _email_y_nombre(None) == (None, None)


class TestNotificarReservaConfirmada:

    def test_sin_email_no_envia_nada(self, solicitud_valida):
        # solicitud_valida no tiene usuario ni email -> se omite en silencio
        # antes de tocar `reserva` (por eso None acá es seguro).
        notificar_reserva_confirmada(solicitud_valida, reserva=None, async_=False)

        assert len(mail.outbox) == 0

    def test_con_email_encola_un_mensaje(self, solicitud_valida, usuario_admin):
        from reservas.models import EstadoReserva, Reserva

        usuario_admin.email = 'estudiante@example.com'
        usuario_admin.save()
        solicitud_valida.usuario = usuario_admin
        solicitud_valida.save()

        # Se arma la Reserva directo (no vía solicitud_valida.crear_reserva())
        # para no disparar TAMBIÉN su propia notificación automática — acá
        # solo interesa probar notificar_reserva_confirmada en aislamiento,
        # con async_=False para poder revisar mail.outbox sin condición de
        # carrera con el hilo en segundo plano que usa async_=True.
        reserva = Reserva.objects.create(
            fecha_reserva=solicitud_valida.fecha_reserva,
            estado=EstadoReserva.objects.get(nombre='Pendiente'),
        )
        notificar_reserva_confirmada(solicitud_valida, reserva, async_=False)

        assert len(mail.outbox) == 1
        enviado = mail.outbox[0]
        assert enviado.to == ['estudiante@example.com']
        assert reserva.codigo in enviado.subject

    def test_crear_reserva_dispara_la_notificacion(self, solicitud_valida, usuario_admin, monkeypatch):
        # Verifica el cableado real (SolicitudReserva.crear_reserva() llama
        # a notificar_reserva_confirmada) sin depender del hilo en segundo
        # plano que usa async_=True por default. crear_reserva() importa
        # notificar_reserva_confirmada localmente (dentro del método) en
        # cada llamada, así que parchear el nombre en utils.notificaciones_
        # email (de donde lo importa) alcanza — no hace falta parchear
        # solicitudes.models, que no tiene ese nombre a nivel de módulo.
        llamadas = []
        monkeypatch.setattr(
            'utils.notificaciones_email.notificar_reserva_confirmada',
            lambda solicitud, reserva: llamadas.append((solicitud, reserva)),
        )

        reserva = solicitud_valida.crear_reserva()

        assert llamadas == [(solicitud_valida, reserva)]


class TestNotificarPrestamoYDevolucion:

    def test_prestamo_confirmado_sin_solicitud_vinculada_no_envia(self, reserva_con_prestamo):
        # reserva_con_prestamo arma la Reserva directo, sin SolicitudReserva
        # vinculada -> no hay forma de resolver un destinatario.
        notificar_prestamo_confirmado(reserva_con_prestamo.prestamo, async_=False)

        assert len(mail.outbox) == 0

    def test_prestamo_confirmado_con_solicitud_vinculada_envia(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)

        notificar_prestamo_confirmado(reserva_con_prestamo.prestamo, async_=False)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['admin@example.com']
        assert reserva_con_prestamo.prestamo.codigo in mail.outbox[0].subject

    def test_devolucion_completada_envia_con_inspecciones(self, reserva_con_prestamo, laboratorio, usuario_admin):
        from prestamos.models import InspeccionItem

        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        inspeccion = InspeccionItem.objects.create(
            prestamo=reserva_con_prestamo.prestamo,
            prestamo_item=reserva_con_prestamo.prestamo_item,
            estado_inspeccion='bien',
        )

        notificar_devolucion_completada(
            reserva_con_prestamo.prestamo, [inspeccion], async_=False,
        )

        assert len(mail.outbox) == 1
        assert reserva_con_prestamo.prestamo.codigo in mail.outbox[0].subject


class TestRecordatorioDevolucionService:

    def test_notifica_solo_prestamos_activos(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 1, 'enviados': 1}
        assert len(mail.outbox) == 1

    def test_no_notifica_prestamos_devueltos(self, reserva_con_prestamo, laboratorio, usuario_admin):
        from prestamos.models import EstadoPrestamo

        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        reserva_con_prestamo.prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
        reserva_con_prestamo.prestamo.save()

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 0, 'enviados': 0}
        assert len(mail.outbox) == 0

    def test_prestamo_sin_email_cuenta_en_total_no_en_enviados(self, reserva_con_prestamo):
        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 1, 'enviados': 0}
        assert len(mail.outbox) == 0


class TestComandoEnviarRecordatorios:

    def test_comando_reporta_enviados_y_total(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)

        salida = StringIO()
        call_command('enviar_recordatorios_devolucion', stdout=salida)

        assert len(mail.outbox) == 1
        assert '1/1' in salida.getvalue()
