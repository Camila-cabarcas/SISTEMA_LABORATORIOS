"""
generar_vetos_no_cancelo.py — vetos
Management command que crea el veto NO_CANCELO de las reservas Aprobadas sin
préstamo cuyo límite de retiro ya pasó (ver GenerarVetosNoCanceloService).
Normalmente no hace falta: VetosAutomaticosMiddleware ya lo ejecuta durante
las requests. Sirve como respaldo por cron (p. ej. si el sitio pasa horas
sin tráfico) o para revisar a mano con --dry-run. Es idempotente, así que
convive con el middleware sin duplicar vetos.
"""
from django.core.management.base import BaseCommand

from vetos.services import GenerarVetosNoCanceloService


class Command(BaseCommand):

    help = 'Crea vetos NO_CANCELO para reservas Aprobadas que nadie retiró antes del límite'

    def add_arguments(self, parser):
        parser.add_argument(
            '--horas', type=int, default=GenerarVetosNoCanceloService.HORAS_VENTANA,
            help='Solo reservas cuyo límite de retiro venció en las últimas N horas '
                 f'(por defecto {GenerarVetosNoCanceloService.HORAS_VENTANA}).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra qué reservas se vetarían sin crear nada.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        resumen = GenerarVetosNoCanceloService.ejecutar(horas=options['horas'], dry_run=dry_run)

        for obj in resumen['creados']:
            reserva = obj if dry_run else obj.reserva
            self.stdout.write(f'  - Reserva {reserva.codigo or reserva.id}')

        verbo = 'se vetarían' if dry_run else 'vetos NO_CANCELO creados'
        self.stdout.write(f"{len(resumen['creados'])} {verbo}.")
        if resumen['sin_identidad']:
            self.stdout.write(self.style.WARNING(
                f"{len(resumen['sin_identidad'])} reservas sin solicitante identificable (omitidas)."
            ))
        if resumen['errores']:
            self.stdout.write(self.style.ERROR(
                f"{len(resumen['errores'])} reservas con error (ver log)."
            ))
