"""
recordatorio_devolucion_service.py — prestamos
Aviso de ATRASO en la devolución (ya no es un recordatorio preventivo):
recorre los préstamos activos cuya fecha límite (Reserva.fecha_devolucion,
no Prestamo.fecha_devolucion — ese campo solo se llena cuando el préstamo
YA se devolvió, así que para un préstamo activo siempre está vacío) ya pasó
hace más de MINUTOS_GRACIA minutos, y envía un email por cada uno — una
sola vez por préstamo, marcado con Prestamo.email_atraso_enviado. La invoca
el comando de management enviar_recordatorios_devolucion (programable con
el Programador de tareas de Windows / cron, cualquier cadencia — p. ej.
cada hora — sin riesgo de reenviar el mismo aviso); no hay Celery en este
proyecto.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from prestamos.models import Prestamo

logger = logging.getLogger(__name__)

# 'En Inspección' se excluye a propósito: si ya está en inspección, el
# proceso de devolución ya arrancó — un aviso de atraso ahí ya no aporta.
ESTADOS_PRESTAMO_CON_ATRASO_POSIBLE = ['Activo', 'Retrasado']

MINUTOS_GRACIA = 30


class RecordatorioDevolucionService:

    @staticmethod
    def enviar_recordatorios():
        """Envía el aviso de atraso a cada préstamo activo cuyo límite de
        devolución venció hace más de MINUTOS_GRACIA minutos y que todavía
        no tiene email_atraso_enviado=True. Marca el flag apenas se envía
        (antes de seguir con el siguiente), así que si el envío falla a
        mitad de la corrida ese préstamo específico queda sin marcar y se
        reintenta en la próxima corrida — pero uno ya enviado con éxito
        nunca se reenvía. Devuelve {'total': N, 'enviados': N} — 'enviados'
        puede ser menor que 'total' si algún préstamo no tiene email de
        destinatario (esos también quedan sin marcar, para reintentarlos si
        más adelante consiguen un email)."""
        from utils.notificaciones_email import notificar_recordatorio_devolucion

        limite = timezone.now() - timedelta(minutes=MINUTOS_GRACIA)

        prestamos = Prestamo.objects.filter(
            estado__nombre__in=ESTADOS_PRESTAMO_CON_ATRASO_POSIBLE,
            reserva__fecha_devolucion__lt=limite,
            email_atraso_enviado=False,
        ).select_related('estado', 'reserva')

        total = 0
        enviados = 0
        for prestamo in prestamos:
            total += 1
            try:
                # Síncrono a propósito: esto corre desde un comando de
                # management de vida corta, no una request HTTP — si se
                # enviara en un hilo aparte (el default de
                # notificar_recordatorio_devolucion), el proceso podría
                # terminar y matar los hilos antes de que SendGrid responda.
                if notificar_recordatorio_devolucion(prestamo, async_=False):
                    prestamo.email_atraso_enviado = True
                    prestamo.save(update_fields=['email_atraso_enviado'])
                    enviados += 1
            except Exception:
                logger.exception(
                    'RecordatorioDevolucionService.enviar_recordatorios | '
                    'error notificando | prestamo_id=%s', prestamo.id,
                )

        logger.info(
            'RecordatorioDevolucionService.enviar_recordatorios | total=%s | enviados=%s',
            total, enviados,
        )
        return {'total': total, 'enviados': enviados}
