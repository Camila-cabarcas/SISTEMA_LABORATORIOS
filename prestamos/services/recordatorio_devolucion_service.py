"""
recordatorio_devolucion_service.py — prestamos
Lógica del recordatorio semanal de devolución: recorre los préstamos
activos (no devueltos) y envía un email por cada uno. La invoca el comando
de management enviar_recordatorios_devolucion (programable con el
Programador de tareas de Windows / cron); no hay Celery en este proyecto.
"""
import logging

from prestamos.models import Prestamo

logger = logging.getLogger(__name__)

ESTADOS_PRESTAMO_ACTIVO = ['Activo', 'Retrasado', 'En Inspección']


class RecordatorioDevolucionService:

    @staticmethod
    def enviar_recordatorios():
        """Envía el recordatorio a cada préstamo activo. Devuelve
        {'total': N, 'enviados': N} — 'enviados' puede ser menor que
        'total' si algún préstamo no tiene email de destinatario."""
        from utils.notificaciones_email import notificar_recordatorio_devolucion

        prestamos = Prestamo.objects.filter(
            estado__nombre__in=ESTADOS_PRESTAMO_ACTIVO,
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
