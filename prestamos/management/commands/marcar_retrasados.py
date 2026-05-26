from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from prestamos.models import Prestamo, EstadoPrestamo


class Command(BaseCommand):

    help = 'Marca como retrasados los préstamos que pasaron su fecha de devolución'

    def handle(self, *args, **kwargs):

        estado_retrasado = EstadoPrestamo.objects.get(nombre='Retrasado')

        # 5 minutos de gracia
        ahora = datetime.now() - timedelta(minutes=5)

        prestamos_retrasados = Prestamo.objects.filter(
            estado__nombre='Activo',
            reserva__fecha_devolucion__lt=ahora
        )

        cantidad = prestamos_retrasados.count()

        prestamos_retrasados.update(estado=estado_retrasado)

        self.stdout.write(
            f'{cantidad} préstamos marcados como retrasados.'
        )