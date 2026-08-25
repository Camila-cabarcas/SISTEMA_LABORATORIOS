"""
notificaciones_email.py — utils
Notificaciones por email para el ciclo de vida de una reserva/préstamo:
reserva confirmada, préstamo confirmado, devolución completada y recordatorio
semanal de devolución. Cada función arma su contexto y llama a
utils.email_tasks.enviar_email_html — nunca debe romper el flujo que la
llama (crear una reserva, registrar un préstamo, finalizar una inspección):
cualquier error queda solo en el log.

Resolución del destinatario: SolicitudReserva.email casi nunca se llena hoy
(ni EstudianteSolicitudForm ni ProfesorSolicitudForm lo piden), así que la
fuente confiable es solicitud.usuario.email — solo existe si el solicitante
tiene una cuenta de Usuario registrada (ver SolicitudReserva.crear_reserva(),
que la busca por cédula). Si no hay ningún email disponible, se omite el
envío silenciosamente (log info, no error) — no hay a quién escribirle.
"""
import logging

from utils.email_tasks import enviar_email_html

logger = logging.getLogger(__name__)


def _email_y_nombre(solicitud):
    """(email, nombre) a partir de una SolicitudReserva, o (None, None) si
    no hay forma de identificar un destinatario."""
    if not solicitud:
        return None, None

    nombre = solicitud.nombre or ''
    if solicitud.usuario:
        nombre = nombre or solicitud.usuario.get_full_name() or solicitud.usuario.username

    email = None
    if solicitud.usuario and solicitud.usuario.email:
        email = solicitud.usuario.email
    elif solicitud.email:
        email = solicitud.email

    return email, (nombre or 'Usuario')


def _solicitud_de_reserva(reserva):
    if not reserva:
        return None
    return reserva.solicitud.first()


def _solicitud_de_prestamo(prestamo):
    if not prestamo or not prestamo.reserva_id:
        return None
    return _solicitud_de_reserva(prestamo.reserva)


def notificar_reserva_confirmada(solicitud, reserva, async_=True):
    """Trigger: SolicitudReserva.crear_reserva(), justo después de crear la
    Reserva. `solicitud` es self de ese método — ya tiene laboratorio/
    horario a mano sin necesidad de recorrer la relación inversa."""
    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_reserva_confirmada | sin email de destinatario | solicitud_id=%s',
            solicitud.id if solicitud else None,
        )
        return

    enviar_email_html(
        destinatarios=email,
        asunto=f'Reserva confirmada — {reserva.codigo}',
        template_name='emails/reserva_confirmada.html',
        contexto={
            'nombre': nombre,
            'laboratorio': solicitud.laboratorio.nombre,
            'fecha': solicitud.fecha_reserva.date(),
            'hora_inicio': solicitud.hora_inicio,
            'hora_fin': solicitud.hora_fin,
            'codigo': reserva.codigo,
        },
        async_=async_,
    )


def notificar_prestamo_confirmado(prestamo, async_=True):
    """Trigger: prestamos/views.py:crear_prestamo, después de registrar los
    PrestamoItem seleccionados."""
    from prestamos.models import PrestamoItem

    solicitud = _solicitud_de_prestamo(prestamo)
    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_prestamo_confirmado | sin email de destinatario | prestamo_id=%s',
            prestamo.id,
        )
        return

    items = list(
        PrestamoItem.objects.filter(prestamo=prestamo).select_related('item_inventario__insumo')
    )

    enviar_email_html(
        destinatarios=email,
        asunto=f'Préstamo confirmado — {prestamo.codigo}',
        template_name='emails/prestamo_confirmado.html',
        contexto={
            'nombre': nombre,
            'items': items,
            'laboratorio': solicitud.laboratorio.nombre if solicitud else None,
            'fecha_entrega': prestamo.fecha_entrega,
            'codigo': prestamo.codigo,
        },
        async_=async_,
    )


def notificar_devolucion_completada(prestamo, inspecciones, async_=True):
    """Trigger: FinalizarInspeccionService.finalizar(), con la misma lista
    de InspeccionItem que ya usó para actualizar el inventario."""
    solicitud = _solicitud_de_prestamo(prestamo)
    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_devolucion_completada | sin email de destinatario | prestamo_id=%s',
            prestamo.id,
        )
        return

    enviar_email_html(
        destinatarios=email,
        asunto=f'Devolución registrada — {prestamo.codigo}',
        template_name='emails/devolucion_completada.html',
        contexto={
            'nombre': nombre,
            'inspecciones': inspecciones,
            'codigo': prestamo.codigo,
            'fecha_devolucion': prestamo.fecha_devolucion,
        },
        async_=async_,
    )


def notificar_recordatorio_devolucion(prestamo, async_=True):
    """Aviso de ATRASO (no un recordatorio preventivo): llamada una vez por
    préstamo vencido hace más de 30 min desde RecordatorioDevolucionService,
    que también se encarga de no llamarla dos veces para el mismo préstamo
    (Prestamo.email_atraso_enviado)."""
    from django.utils import timezone

    from prestamos.models import PrestamoItem

    solicitud = _solicitud_de_prestamo(prestamo)
    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_recordatorio_devolucion | sin email de destinatario | prestamo_id=%s',
            prestamo.id,
        )
        return False

    items = list(
        PrestamoItem.objects.filter(prestamo=prestamo).select_related('item_inventario__insumo')
    )
    fecha_vencimiento = prestamo.reserva.fecha_devolucion if prestamo.reserva_id else None
    minutos_atraso = None
    if fecha_vencimiento:
        minutos_atraso = int((timezone.now() - fecha_vencimiento).total_seconds() // 60)

    enviar_email_html(
        destinatarios=email,
        asunto='AVISO: Atraso en devolución de items',
        template_name='emails/recordatorio_devolucion.html',
        contexto={
            'nombre': nombre,
            'items': items,
            'codigo': prestamo.codigo,
            'fecha_vencimiento': fecha_vencimiento,
            'minutos_atraso': minutos_atraso,
            'laboratorio': solicitud.laboratorio.nombre if solicitud else None,
        },
        async_=async_,
    )
    return True
