"""
seed_locust.py — solicitudes
Comando de management que asegura los datos objetivo que locustfile.py
necesita para poder golpear endpoints autenticados/con parámetros reales:
reutiliza seed_e2e (usuarios, laboratorio, horario, insumo) y además crea
una Reserva "Pendiente" (para el flujo de aprobación) y un Prestamo
"Activo" con un ítem (para el flujo de inspección). Ambos usan un `codigo`
fijo para que el comando sea idempotente (no crea filas nuevas en cada
corrida).

Uso: python manage.py seed_locust
Imprime al final las variables de entorno que locustfile.py puede leer.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Crea/asegura los datos objetivo (reserva, préstamo) para las pruebas de carga con Locust.'

    @transaction.atomic
    def handle(self, *args, **options):
        call_command('seed_e2e')

        from django.utils import timezone
        from laboratorio.models import Laboratorio
        from reservas.models import EstadoReserva, Reserva
        from prestamos.models import EstadoPrestamo, Prestamo, PrestamoItem
        from inventario.models import Insumo, ItemInventario
        from users.models import Usuario

        laboratorio = Laboratorio.objects.get(nombre='Laboratorio E2E')
        insumo = Insumo.objects.get(nombre='Insumo E2E')
        admin = Usuario.objects.get(username='e2e_admin')

        estado_pendiente = EstadoReserva.objects.get(nombre='Pendiente')
        reserva_aprobar, _ = Reserva.objects.get_or_create(
            codigo='LOCUST-RESERVA-APROBAR',
            defaults={'fecha_reserva': timezone.now(), 'estado': estado_pendiente}
        )

        estado_aprobada = EstadoReserva.objects.get(nombre='Aprobada')
        reserva_prestamo, _ = Reserva.objects.get_or_create(
            codigo='LOCUST-RESERVA-PRESTAMO',
            defaults={'fecha_reserva': timezone.now(), 'estado': estado_aprobada}
        )

        estado_activo_prestamo = EstadoPrestamo.objects.get(nombre='Activo')
        prestamo, prestamo_creado = Prestamo.objects.get_or_create(
            codigo='LOCUST-PRESTAMO',
            defaults={
                'reserva': reserva_prestamo,
                'responsable': admin,
                'estado': estado_activo_prestamo,
            }
        )

        if prestamo_creado:
            item = ItemInventario.objects.filter(insumo=insumo).first()
            PrestamoItem.objects.create(prestamo=prestamo, item_inventario=item)

        self.stdout.write(self.style.SUCCESS(
            'Datos de carga listos. Variables de entorno para locustfile.py '
            '(los valores mostrados son también los defaults del archivo):\n'
            f'  LOCUST_LAB_ID={laboratorio.id}\n'
            f'  LOCUST_RESERVA_ID={reserva_aprobar.id}\n'
            f'  LOCUST_PRESTAMO_ID={prestamo.id}\n'
            '  LOCUST_ADMIN_USER=e2e_admin  LOCUST_ADMIN_PASS=E2eAdmin!2026\n'
            '  LOCUST_LAB_USER=e2e_laboratorista  LOCUST_LAB_PASS=E2eLab!2026'
        ))
