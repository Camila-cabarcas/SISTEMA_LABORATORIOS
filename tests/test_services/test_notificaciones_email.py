"""
Tests para utils/notificaciones_email.py y
prestamos/services/recordatorio_devolucion_service.py: resolución del
destinatario y que cada notificación efectivamente encole un email (usando
django.core.mail.outbox — Django cambia EMAIL_BACKEND a locmem para tests
automáticamente, así que esto nunca golpea la API real de SendGrid).
"""
from datetime import time, timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from prestamos.services.recordatorio_devolucion_service import RecordatorioDevolucionService
from solicitudes.models import SolicitudReserva
from utils.notificaciones_email import (
    _email_y_nombre,
    notificar_devolucion_completada,
    notificar_prestamo_confirmado,
    notificar_reserva_aprobada,
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

    def test_prefiere_email_de_la_solicitud_sobre_el_del_usuario(self, solicitud_valida, usuario_admin):
        # solicitud.email es ahora obligatorio/verificado (@udea.edu.co) en
        # EstudianteSolicitudForm y en el flujo "libre" -> gana sobre
        # usuario.email cuando ambos están presentes.
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        solicitud_valida.usuario = usuario_admin
        solicitud_valida.email = 'juan@udea.edu.co'
        solicitud_valida.save()

        email, nombre = _email_y_nombre(solicitud_valida)

        assert email == 'juan@udea.edu.co'
        assert nombre == 'Juan Pérez'

    def test_cae_a_email_del_usuario_si_la_solicitud_no_tiene(self, solicitud_valida, usuario_admin):
        # ProfesorSolicitudForm (flujo normal) no pide email -> solicitud.email
        # queda vacío y hay que caer al de la cuenta Usuario del docente.
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


class TestNotificarReservaAprobada:

    def test_sin_email_no_envia_nada(self, solicitud_valida, catalogos):
        reserva = solicitud_valida.crear_reserva()

        notificar_reserva_aprobada(reserva, async_=False)

        assert len(mail.outbox) == 0

    def test_sin_solicitud_vinculada_no_envia(self, catalogos):
        from reservas.models import EstadoReserva, Reserva

        reserva = Reserva.objects.create(
            fecha_reserva=timezone.now(), estado=EstadoReserva.objects.get(nombre='Aprobada'),
        )

        notificar_reserva_aprobada(reserva, async_=False)

        assert len(mail.outbox) == 0

    def test_con_email_encola_un_mensaje_con_info_correcta(self, solicitud_valida, laboratorio, catalogos):
        # El email se setea DESPUÉS de crear_reserva() a propósito: si
        # estuviera antes, esa llamada también dispararía (en un hilo
        # aparte) su propia notificar_reserva_aprobada con destinatario
        # válido, sumando un segundo mensaje a mail.outbox antes de que
        # termine este test — mismo problema que ya resolvió
        # TestNotificarReservaConfirmada.test_con_email_encola_un_mensaje
        # armando la Reserva directo en vez de vía crear_reserva().
        reserva = solicitud_valida.crear_reserva()
        solicitud_valida.email = 'juan@udea.edu.co'
        solicitud_valida.save()

        notificar_reserva_aprobada(reserva, async_=False)

        assert len(mail.outbox) == 1
        enviado = mail.outbox[0]
        assert enviado.to == ['juan@udea.edu.co']
        assert reserva.codigo in enviado.subject
        assert 'Aprobada' in enviado.subject
        cuerpo_html = enviado.alternatives[0][0]
        assert laboratorio.nombre in cuerpo_html
        assert reserva.codigo in cuerpo_html
        assert '08:00' in cuerpo_html  # hora_inicio de solicitud_valida

    def test_crear_reserva_dispara_la_notificacion(self, solicitud_valida, catalogos, monkeypatch):
        # Verifica el cableado real: SolicitudReserva.crear_reserva() llama
        # a notificar_reserva_aprobada ahora que las reservas quedan
        # Aprobada desde que se crean (ya no hay un paso de aprobación
        # manual separado). Parchea el nombre en utils.notificaciones_email
        # (de donde crear_reserva() lo importa localmente en cada llamada)
        # en vez de depender del hilo en segundo plano que usa async_=True
        # por default.
        llamadas = []
        monkeypatch.setattr(
            'utils.notificaciones_email.notificar_reserva_aprobada',
            lambda reserva: llamadas.append(reserva),
        )

        reserva = solicitud_valida.crear_reserva()

        assert llamadas == [reserva]

    def test_aprobar_solicitud_dispara_la_notificacion(self, solicitud_valida, usuario_admin, monkeypatch):
        # Igual que test_crear_reserva_dispara_la_notificacion, pero para el
        # segundo camino que todavía existe hacia el mismo email:
        # AprobarSolicitudReservaService.aprobar() (sin vista propia hoy,
        # pero sigue disponible para reservas que quedaron Pendiente por
        # otra vía). Parchea el nombre en utils.notificaciones_email (de
        # donde lo importa con import local) en vez de depender del hilo en
        # segundo plano de async_=True por default.
        from solicitudes.services.solicitud_reserva_service import AprobarSolicitudReservaService

        reserva = solicitud_valida.crear_reserva()
        solicitud_valida.refresh_from_db()

        llamadas = []
        monkeypatch.setattr(
            'utils.notificaciones_email.notificar_reserva_aprobada',
            lambda reserva: llamadas.append(reserva),
        )

        AprobarSolicitudReservaService.aprobar(solicitud_valida.id, usuario_admin)

        assert llamadas == [reserva]


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


def _marcar_vencido(reserva, minutos_atras):
    """Fuerza reserva.fecha_devolucion a `minutos_atras` minutos en el
    pasado — reserva_con_prestamo la deja ~2h en el futuro por default
    (Reserva.save() la calcula sola si no se pasa), así que hay que
    pisarla explícitamente para simular un préstamo vencido."""
    reserva.fecha_devolucion = timezone.now() - timedelta(minutes=minutos_atras)
    reserva.save()


class TestRecordatorioDevolucionService:

    def test_no_notifica_si_no_esta_vencido(self, reserva_con_prestamo, laboratorio, usuario_admin):
        # reserva_con_prestamo deja fecha_devolucion ~2h en el futuro por
        # default -> ni siquiera está atrasado todavía.
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 0, 'enviados': 0}
        assert len(mail.outbox) == 0

    def test_no_notifica_si_paso_menos_de_30_min(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=10)

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 0, 'enviados': 0}
        assert len(mail.outbox) == 0

    def test_notifica_si_paso_mas_de_30_min(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=45)

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 1, 'enviados': 1}
        assert len(mail.outbox) == 1
        assert 'AVISO: Atraso' in mail.outbox[0].subject

    def test_marca_email_atraso_enviado_tras_notificar(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=45)
        assert reserva_con_prestamo.prestamo.email_atraso_enviado is False

        RecordatorioDevolucionService.enviar_recordatorios()

        reserva_con_prestamo.prestamo.refresh_from_db()
        assert reserva_con_prestamo.prestamo.email_atraso_enviado is True

    def test_no_reenvia_si_ya_se_notifico(self, reserva_con_prestamo, laboratorio, usuario_admin):
        # Simula una segunda corrida del comando (p. ej. una hora después):
        # con el flag ya en True, el préstamo ni siquiera entra al query.
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=90)
        reserva_con_prestamo.prestamo.email_atraso_enviado = True
        reserva_con_prestamo.prestamo.save()

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 0, 'enviados': 0}
        assert len(mail.outbox) == 0

    def test_no_notifica_prestamos_devueltos(self, reserva_con_prestamo, laboratorio, usuario_admin):
        from prestamos.models import EstadoPrestamo

        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=45)
        reserva_con_prestamo.prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
        reserva_con_prestamo.prestamo.save()

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 0, 'enviados': 0}
        assert len(mail.outbox) == 0

    def test_prestamo_sin_email_cuenta_en_total_no_en_enviados(self, reserva_con_prestamo):
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=45)

        resultado = RecordatorioDevolucionService.enviar_recordatorios()

        assert resultado == {'total': 1, 'enviados': 0}
        assert len(mail.outbox) == 0

        # Sin email no se pudo notificar -> no se marca, para reintentar
        # si más adelante el préstamo consigue un destinatario.
        reserva_con_prestamo.prestamo.refresh_from_db()
        assert reserva_con_prestamo.prestamo.email_atraso_enviado is False


class TestComandoEnviarRecordatorios:

    def test_comando_reporta_enviados_y_total(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=45)

        salida = StringIO()
        call_command('enviar_recordatorios_devolucion', stdout=salida)

        assert len(mail.outbox) == 1
        assert '1/1' in salida.getvalue()

    def test_comando_no_reenvia_en_segunda_corrida(self, reserva_con_prestamo, laboratorio, usuario_admin):
        usuario_admin.email = 'admin@example.com'
        usuario_admin.save()
        _vincular_solicitud(reserva_con_prestamo.reserva, laboratorio, usuario=usuario_admin)
        _marcar_vencido(reserva_con_prestamo.reserva, minutos_atras=45)

        call_command('enviar_recordatorios_devolucion', stdout=StringIO())
        call_command('enviar_recordatorios_devolucion', stdout=StringIO())

        assert len(mail.outbox) == 1
