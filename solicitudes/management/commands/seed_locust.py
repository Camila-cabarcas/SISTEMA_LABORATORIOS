"""
seed_locust.py — solicitudes
Comando de management que asegura los datos objetivo que locustfile.py
necesita para poder golpear endpoints autenticados/con parámetros reales:
reutiliza seed_e2e (usuarios, laboratorio, horario, insumo) y además crea
una Reserva "Pendiente" (para el flujo de aprobación) y un Prestamo
"Activo" con un ítem (para el flujo de inspección). Ambos usan un `codigo`
fijo para que el comando sea idempotente (no crea filas nuevas en cada
corrida).

Desde v3 del locustfile también asegura: un profesor YA REGISTRADO con
contraseña conocida (`e2e_profesor`) — necesario porque los caminos que crea
el propio sistema (crear_profesor, aprobar SolicitudRegistroProfesor) le
asignan una contraseña aleatoria no recuperable, así que no sirven para un
login real de pruebas —, un Curso a su nombre, y varios Módulos en
Laboratorio E2E (que seed_e2e no crea) para poder ejercitar la asignación de
módulos.

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
        from laboratorio.models import Laboratorio, Modulo
        from reservas.models import EstadoReserva, Reserva
        from prestamos.models import EstadoPrestamo, Prestamo, PrestamoItem
        from inventario.models import Insumo, ItemInventario
        from users.models import Usuario, Rol
        from solicitudes.models import Curso

        # Obtener datos base
        laboratorio = Laboratorio.objects.get(nombre='Laboratorio E2E')
        insumo = Insumo.objects.get(nombre='Insumo E2E')
        admin = Usuario.objects.get(username='e2e_admin')

        # Crear/asegurar profesor registrado
        rol_docente = Rol.objects.get(nombre='Docente')
        profesor, _ = Usuario.objects.get_or_create(
            username='e2e_profesor',
            defaults={
                'rol': rol_docente,
                'codigo': 'E2E-PROF',
                'first_name': 'Profesor',
                'last_name': 'E2E',
            }
        )
        profesor.rol = rol_docente
        profesor.codigo = profesor.codigo or 'E2E-PROF'
        profesor.first_name = profesor.first_name or 'Profesor'
        profesor.last_name = profesor.last_name or 'E2E'
        profesor.is_active = True
        profesor.set_password('E2eProfesor!2026')
        profesor.save()

        # Crear curso para el profesor
        Curso.objects.get_or_create(
            codigo='CURSO-E2E-101',
            defaults={
                'nombre': 'Curso E2E',
                'profesor': profesor,
                'cantidad_estudiantes': 30,
            }
        )

        # Crear módulos en diferentes zonas
        zonas = ['izquierda', 'centro-top', 'centro-mid', 'centro-bot', 'derecha', 'inferior']
        for i, zona in enumerate(zonas, start=1):
            Modulo.objects.get_or_create(
                nombre=f'Módulo E2E {i}',
                laboratorio=laboratorio,
                defaults={'capacidad': 4, 'disponible': True, 'zona': zona}
            )

        # Crear reservas de prueba
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

        # Crear préstamo de prueba
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
            if item:
                PrestamoItem.objects.create(prestamo=prestamo, item_inventario=item)

        # ✅ ARREGLADO: Verificar que existe item antes de acceder a .estado
        item = ItemInventario.objects.filter(insumo=insumo).first()
        if item:
            estado_disponible = item.estado
        else:
            # Si no hay items, usar estado por defecto
            from inventario.models import EstadoItem
            estado_disponible = EstadoItem.objects.get(nombre='Disponible')

        # Crear ítems adicionales para pruebas de carga
        # seed_e2e solo crea 3 ítems (pensados para la suite Cypress)
        # Bajo carga con múltiples usuarios concurrentes se agotan rápido
        for i in range(1, 26):
            ItemInventario.objects.get_or_create(
                codigo=f'LOCUST-ITEM-{i:03d}',
                defaults={
                    'insumo': insumo,
                    'estado': estado_disponible,
                    'laboratorio': laboratorio,
                }
            )

        # Imprimir variables de entorno
        self.stdout.write(self.style.SUCCESS(
            'Datos de carga listos. Variables de entorno para locustfile.py '
            '(los valores mostrados son también los defaults del archivo):\n'
            f'  LOCUST_LAB_ID={laboratorio.id}\n'
            f'  LOCUST_RESERVA_ID={reserva_aprobar.id}\n'
            f'  LOCUST_PRESTAMO_ID={prestamo.id}\n'
            '  LOCUST_ADMIN_USER=e2e_admin  LOCUST_ADMIN_PASS=E2eAdmin!2026\n'
            '  LOCUST_LAB_USER=e2e_laboratorista  LOCUST_LAB_PASS=E2eLab!2026\n'
            '  LOCUST_PROF_USER=e2e_profesor  LOCUST_PROF_PASS=E2eProfesor!2026  LOCUST_PROF_NOMBRE="Profesor E2E"'
        ))