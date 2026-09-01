"""
notificaciones_email.py — utils
Notificaciones por email para el ciclo de vida de una reserva/préstamo: 4
emails en total — reserva creada y aprobada, cambios en la reserva o
préstamo listo (fusionados en un solo email adaptable, ver
notificar_cambios_o_prestamo_listo), devolución completada y aviso de
atraso. Cada función arma su contexto y llama a
utils.email_tasks.enviar_email_html — nunca debe romper el flujo que la
llama (crear una reserva, registrar un préstamo, finalizar una inspección):
cualquier error queda solo en el log.

Antes había 6 funciones (7 templates contando emails/prueba.html, que no es
una notificación de este ciclo de vida sino un smoke test de SendGrid — ver
users/management/commands/enviar_email_prueba.py, eliminado junto con su
template porque no tenía otro motivo para existir): notificar_reserva_
confirmada + notificar_reserva_aprobada se fusionaron en
notificar_reserva_creada_aprobada porque, con auto-aprobación (ver
SolicitudReserva.crear_reserva()), "creada" y "aprobada" son el mismo
evento; notificar_reserva_modificada + notificar_prestamo_confirmado se
fusionaron en notificar_cambios_o_prestamo_listo porque ambas son avisos de
"algo cambió en tu reserva" que un estudiante recibe en el mismo punto del
flujo (después de aprobada, antes/en el momento del préstamo) — un
parámetro `tipo` decide qué mitad de la plantilla se renderiza.

Resolución del destinatario: solicitud.email es ahora obligatorio y
verificado (@udea.edu.co) en EstudianteSolicitudForm y en el flujo "reserva
libre" (ver ValidarSolicitudReservaService), así que es la fuente preferida
cuando está presente. ProfesorSolicitudForm (flujo normal, con curso
registrado) NO lo pide — para esos casos se cae a solicitud.usuario.email,
que siempre existe porque ese flujo exige encontrar un Usuario Docente
registrado por nombre (ver SolicitudReserva.clean()). Si no hay ningún
email disponible por ninguna vía, se omite el envío silenciosamente (log
info, no error) — no hay a quién escribirle.
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
    if solicitud.email:
        email = solicitud.email
    elif solicitud.usuario and solicitud.usuario.email:
        email = solicitud.usuario.email

    return email, (nombre or 'Usuario')


def _solicitud_de_reserva(reserva):
    if not reserva:
        return None
    return reserva.solicitud.first()


def _solicitud_de_prestamo(prestamo):
    if not prestamo or not prestamo.reserva_id:
        return None
    return _solicitud_de_reserva(prestamo.reserva)


def notificar_reserva_creada_aprobada(solicitud, async_=True):
    """Notificación fusionada de creación + aprobación (antes dos emails
    separados: notificar_reserva_confirmada + notificar_reserva_aprobada).
    Con auto-aprobación (ver SolicitudReserva.crear_reserva()) una reserva
    nace directamente Aprobada, así que "creada" y "aprobada" son el mismo
    evento — no tiene sentido mandar dos correos por él.

    Trigger: SolicitudReserva.crear_reserva(), justo después de crear la
    Reserva. Toma `solicitud` (no `reserva`) porque en ese punto ya tiene
    self.reserva asignado y laboratorio/horario a mano, sin necesidad de
    recorrer la relación inversa."""
    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_reserva_creada_aprobada | sin email de destinatario | solicitud_id=%s',
            solicitud.id if solicitud else None,
        )
        return

    reserva = solicitud.reserva
    enviar_email_html(
        destinatarios=email,
        asunto=f'¡Tu reserva fue creada y aprobada! — {reserva.codigo}',
        template_name='emails/reserva_creada_aprobada.html',
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


def notificar_cambios_o_prestamo_listo(
    reserva, tipo='cambios', *,
    agregados=None, quitados=None, cambiados=None,
    prestamo=None, async_=True,
):
    """Notificación fusionada para dos eventos del ciclo de vida de una
    Reserva Aprobada que antes vivían en funciones separadas
    (notificar_reserva_modificada + notificar_prestamo_confirmado): ambos
    son "algo cambió en tu reserva" en el mismo tramo del flujo (después de
    aprobada, antes o en el momento del préstamo), así que comparten un
    único template adaptable (emails/cambios_y_prestamo.html) según `tipo`.

    Args:
        reserva: la Reserva afectada — se resuelve la solicitud vinculada
            por la relación inversa (`_solicitud_de_reserva`).
        tipo: 'cambios' (default) — un laboratorista agregó/quitó/cambió la
            cantidad de insumos (trigger: EditarInsumosReservaService.
            guardar()); pasa `agregados`/`quitados`/`cambiados` (mismas
            listas de dicts que antes). 'prestamo' — se registró la entrega
            del préstamo asociado (trigger: prestamos/views.py:
            crear_prestamo); pasa `prestamo` (el Prestamo recién creado)
            para no tener que resolverlo de nuevo acá — si no se pasa, usa
            el más reciente de reserva.prestamo_set.
    """
    solicitud = _solicitud_de_reserva(reserva)
    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_cambios_o_prestamo_listo | sin email de destinatario | reserva_id=%s | tipo=%s',
            reserva.id if reserva else None, tipo,
        )
        return

    contexto = {
        'nombre': nombre,
        'tipo': tipo,
        'laboratorio': solicitud.laboratorio.nombre if solicitud else None,
        'codigo': reserva.codigo,
    }

    if tipo == 'prestamo':
        from prestamos.models import PrestamoItem

        prestamo = prestamo or reserva.prestamo_set.order_by('-fecha_entrega').first()
        items = []
        if prestamo:
            items = list(
                PrestamoItem.objects.filter(prestamo=prestamo).select_related('item_inventario__insumo')
            )
        asunto = f'¡Tu préstamo está listo! — {reserva.codigo}'
        contexto.update({
            'items': items,
            'fecha_entrega': prestamo.fecha_entrega if prestamo else None,
        })
    else:
        asunto = f'Tu reserva fue modificada — {reserva.codigo}'
        contexto.update({
            'fecha': solicitud.fecha_reserva.date() if solicitud else None,
            'agregados': agregados or [],
            'quitados': quitados or [],
            'cambiados': cambiados or [],
        })

    enviar_email_html(
        destinatarios=email,
        asunto=asunto,
        template_name='emails/cambios_y_prestamo.html',
        contexto=contexto,
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


def notificar_cancelacion(reserva, cancelada_por, motivo='', async_=True):
    """Trigger: CancelarReservaService (reservas/services/cancelar_reserva_
    service.py), tanto cancelar_propietario() como cancelar_admin() — el
    destinatario cambia según quién canceló:

    - cancelada_por='estudiante': el propio solicitante se autocanceló (ver
      cancelar_propietario) — se avisa a TODOS los encargados
      (Laboratorio.encargados) del laboratorio de la reserva, no al
      solicitante (que ya sabe que canceló porque fue él quien lo hizo).
    - cancelada_por='laboratorista': cancelación administrativa (ver
      cancelar_admin) — se avisa al solicitante, con el motivo que dio quien
      canceló.
    """
    solicitud = _solicitud_de_reserva(reserva)

    if cancelada_por == 'estudiante':
        laboratorio = solicitud.laboratorio if solicitud else None
        destinatarios = [
            e for e in (laboratorio.encargados.values_list('email', flat=True) if laboratorio else [])
            if e
        ]
        if not destinatarios:
            logger.info(
                'notificar_cancelacion | sin encargados con email | reserva_id=%s | laboratorio_id=%s',
                reserva.id if reserva else None, laboratorio.id if laboratorio else None,
            )
            return

        enviar_email_html(
            destinatarios=destinatarios,
            asunto=f'Reserva cancelada por el solicitante — {reserva.codigo}',
            template_name='emails/reserva_cancelada.html',
            contexto={
                'para_laboratorista': True,
                'solicitante': solicitud.nombre if solicitud else 'Desconocido',
                'cedula': solicitud.cedula if solicitud else '',
                'laboratorio': laboratorio.nombre if laboratorio else None,
                'fecha': solicitud.fecha_reserva.date() if solicitud else None,
                'codigo': reserva.codigo,
            },
            async_=async_,
        )
        return

    email, nombre = _email_y_nombre(solicitud)
    if not email:
        logger.info(
            'notificar_cancelacion | sin email de destinatario | reserva_id=%s',
            reserva.id if reserva else None,
        )
        return

    enviar_email_html(
        destinatarios=email,
        asunto=f'Tu reserva fue cancelada — {reserva.codigo}',
        template_name='emails/reserva_cancelada.html',
        contexto={
            'para_laboratorista': False,
            'nombre': nombre,
            'laboratorio': solicitud.laboratorio.nombre if solicitud else None,
            'fecha': solicitud.fecha_reserva.date() if solicitud else None,
            'codigo': reserva.codigo,
            'motivo': motivo,
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
