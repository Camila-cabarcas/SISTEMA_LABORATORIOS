"""
enviar_recordatorios_devolucion.py — prestamos
Management command que envía el recordatorio semanal de devolución a todos
los préstamos activos. Es la misma lógica que usa la tarea de Celery
(prestamos/tasks.py) — este comando corre sin necesitar Celery ni un broker,
así que sirve para programarlo con el Programador de tareas de Windows / cron
mientras no haya esa infraestructura levantada (ver marcar_retrasados.py,
que sigue el mismo patrón para otro recordatorio periódico).
"""
from django.core.management.base import BaseCommand

from prestamos.services.recordatorio_devolucion_service import RecordatorioDevolucionService


class Command(BaseCommand):

    help = 'Envía el recordatorio de devolución a todos los préstamos activos.'

    def handle(self, *args, **kwargs):
        resultado = RecordatorioDevolucionService.enviar_recordatorios()
        self.stdout.write(
            f"{resultado['enviados']}/{resultado['total']} préstamos activos notificados "
            f"({resultado['total'] - resultado['enviados']} sin email de destinatario)."
        )
