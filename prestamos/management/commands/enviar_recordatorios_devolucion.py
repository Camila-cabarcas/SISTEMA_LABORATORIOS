"""
enviar_recordatorios_devolucion.py — prestamos
Management command que envía el aviso de ATRASO a los préstamos activos
vencidos hace más de 30 minutos (ver MINUTOS_GRACIA en
recordatorio_devolucion_service.py) que todavía no lo recibieron
(Prestamo.email_atraso_enviado=False) — así que correrlo con cualquier
cadencia (recomendado: cada hora, con el Programador de tareas de Windows /
cron) nunca reenvía el mismo aviso dos veces. No hay Celery en este
proyecto (ver marcar_retrasados.py, que sigue el mismo patrón de comando +
scheduler externo para otro chequeo periódico).
"""
from django.core.management.base import BaseCommand

from prestamos.services.recordatorio_devolucion_service import RecordatorioDevolucionService


class Command(BaseCommand):

    help = 'Envía el aviso de atraso a los préstamos vencidos hace más de 30 min que aún no lo recibieron.'

    def handle(self, *args, **kwargs):
        resultado = RecordatorioDevolucionService.enviar_recordatorios()
        self.stdout.write(
            f"{resultado['enviados']}/{resultado['total']} préstamos atrasados notificados "
            f"({resultado['total'] - resultado['enviados']} sin marcar — sin email de "
            f"destinatario o con error de envío, se reintentan en la próxima corrida)."
        )
