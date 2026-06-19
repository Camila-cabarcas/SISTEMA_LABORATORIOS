"""
expirar_reservas.py — reservas
Management command que marca como "Expiradas" las reservas pendientes o aprobadas cuya hora_limite_retiro ya pasó.
"""
from django.core.management.base import BaseCommand
from datetime import datetime
from reservas.models import Reserva, EstadoReserva


class Command(BaseCommand):

    help = 'Expira reservas que pasaron su límite de retiro'

    def handle(self, *args, **kwargs):

        estado_expirada = EstadoReserva.objects.get(nombre='Expirada')

        reservas_expiradas = Reserva.objects.filter(
            estado__nombre__in=['Pendiente', 'Aprobada'],
            hora_limite_retiro__lt=datetime.now()
        )

        cantidad = reservas_expiradas.count()

        reservas_expiradas.update(estado=estado_expirada)

        self.stdout.write(
            f'{cantidad} reservas expiradas.'
        )