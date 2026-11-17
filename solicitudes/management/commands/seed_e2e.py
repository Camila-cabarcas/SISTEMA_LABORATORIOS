"""
seed_e2e.py — solicitudes
Comando de management que asegura (crea si faltan, no duplica si ya existen)
los datos base que la suite E2E de Cypress necesita para correr contra un
entorno de desarrollo: catálogos de estado, dos usuarios de prueba con
credenciales conocidas, un laboratorio, un programa académico activo y un
insumo con ítems de inventario "Disponible".

Esto es infraestructura de entorno (equivalente a un seed de staging), no
parte del flujo de negocio que los tests E2E ejercitan vía UI — los tests
nunca escriben en la base de datos directamente, solo leen este estado ya
sembrado para poder completar los formularios.

Uso: python manage.py seed_e2e
"""
from django.core.management.base import BaseCommand
from django.db import transaction

# Laboratorista de prueba (reemplaza a e2e_laboratorista, dada de baja en
# laboratorio.0023). Lo usan cypress/fixtures/usuarios.json y locustfile.py.
LABORATORISTA_E2E = 'e2e_laboratorista_v2'
CORREO_LABORATORISTA_E2E = 'e2e.laboratorista@udea.edu.co'
CLAVE_LABORATORISTA_E2E = 'E2eLab!2026'


class Command(BaseCommand):
    help = 'Crea/asegura los datos base que necesita la suite E2E de Cypress.'

    def _laboratorista_e2e(self, laboratorio, admin):
        """Crea la cuenta con personal.crear_laboratorista; si ya existe,
        la deja con la clave conocida y en `laboratorio`. Si alguien la dio
        de baja, no la reactiva (eso no lo hace ningún flujo de Personal):
        avisa y sigue."""
        from laboratorio.services import personal
        from users.models import Usuario

        cuenta = Usuario.objects.filter(username=LABORATORISTA_E2E).first()
        if cuenta is None:
            personal.crear_laboratorista({
                'username': LABORATORISTA_E2E, 'email': CORREO_LABORATORISTA_E2E,
                'first_name': 'Laboratorista', 'last_name': 'E2E',
                'password': CLAVE_LABORATORISTA_E2E,
            }, laboratorio, admin)
            return
        if not cuenta.is_active:
            self.stdout.write(self.style.WARNING(
                f'{LABORATORISTA_E2E} está dada de baja: no se reactiva. '
                f'Créala de nuevo con otro usuario o reactívala a mano.'))
            return
        cuenta.set_password(CLAVE_LABORATORISTA_E2E)
        cuenta.save(update_fields=['password'])
        if cuenta.laboratorios_asignados.first() != laboratorio:
            personal.cambiar_laboratorio(cuenta, laboratorio, admin)

    @transaction.atomic
    def handle(self, *args, **options):
        from users.models import Rol, Usuario, ProgramaAcademico
        from laboratorio.models import Laboratorio, HorarioLaboratorio
        from inventario.models import Insumo, ItemInventario, EstadoItem, EstadoInsumo
        from reservas.models import EstadoReserva
        from prestamos.models import EstadoPrestamo
        from datetime import time

        for nombre in ['Administrador', 'Laboratorista', 'Monitor', 'Estudiante']:
            Rol.objects.get_or_create(nombre=nombre)

        for nombre in ['Pendiente', 'Aprobada', 'Cancelada', 'Expirada']:
            EstadoReserva.objects.get_or_create(nombre=nombre)

        for nombre in ['Activo', 'En Inspección', 'Devuelto', 'Retrasado']:
            EstadoPrestamo.objects.get_or_create(nombre=nombre)

        for nombre in ['Disponible', 'Prestado', 'Dañado', 'Mantenimiento', 'Baja', 'Perdido']:
            EstadoItem.objects.get_or_create(nombre=nombre)

        estado_activo_insumo, _ = EstadoInsumo.objects.get_or_create(nombre='Activo')

        rol_admin = Rol.objects.get(nombre='Administrador')

        # codigo es unique en Usuario: no se puede dejar en blanco, o choca
        # con cualquier otro usuario que también lo tenga vacío.
        admin, _ = Usuario.objects.get_or_create(
            username='e2e_admin',
            defaults={'rol': rol_admin, 'is_staff': True, 'codigo': 'E2E-ADMIN'}
        )
        admin.rol = rol_admin
        admin.codigo = admin.codigo or 'E2E-ADMIN'
        admin.set_password('E2eAdmin!2026')
        admin.save()

        ProgramaAcademico.objects.get_or_create(
            nombre='Ingeniería de Sistemas', defaults={'activo': True}
        )

        laboratorio, _ = Laboratorio.objects.get_or_create(
            nombre='Laboratorio E2E',
            defaults={'ubicacion': 'Bloque E2E - Piso 1'}
        )

        # Laboratorista de prueba: cuenta activa con un solo laboratorio,
        # creada con el servicio de Personal (mismas reglas que la pantalla).
        # La cuenta vieja e2e_laboratorista quedó dada de baja en la
        # migración laboratorio.0023 y este comando ya no la toca.
        self._laboratorista_e2e(laboratorio, admin)

        # SolicitudReserva.clean() valida el horario contra HorarioLaboratorio
        # (por día de semana); sin esto, cualquier solicitud para este
        # laboratorio se rechaza con "El laboratorio no está disponible los <día>s".
        for dia in ['lunes', 'martes', 'miercoles', 'jueves', 'viernes']:
            HorarioLaboratorio.objects.get_or_create(
                laboratorio=laboratorio,
                dia=dia,
                defaults={
                    'hora_inicio': time(6, 0),
                    'hora_fin': time(18, 0),
                    'bloqueado': False,
                }
            )

        insumo, _ = Insumo.objects.get_or_create(
            nombre='Insumo E2E',
            defaults={
                'descripcion': 'Insumo de prueba para la suite E2E',
                'estado': estado_activo_insumo,
            }
        )

        estado_disponible = EstadoItem.objects.get(nombre='Disponible')
        for i in range(1, 4):
            ItemInventario.objects.get_or_create(
                codigo=f'E2E-ITEM-{i:03d}',
                defaults={
                    'insumo': insumo,
                    'estado': estado_disponible,
                    'laboratorio': laboratorio,
                }
            )

        self.stdout.write(self.style.SUCCESS(
            'Datos E2E listos:\n'
            f'  usuarios: e2e_admin / E2eAdmin!2026, {LABORATORISTA_E2E} / {CLAVE_LABORATORISTA_E2E} '
            f'(o {CORREO_LABORATORISTA_E2E})\n'
            '  laboratorio: "Laboratorio E2E" (horario lunes-viernes 06:00-18:00)\n'
            '  insumo: "Insumo E2E" con 3 ítems en estado Disponible'
        ))
