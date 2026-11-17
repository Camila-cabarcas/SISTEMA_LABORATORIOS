"""
Fase 2, etapa 1: quitar el rol Docente.

Adelante (el orden importa: Usuario.rol es CASCADE, borrar la fila del rol
con cuentas apuntándole BORRARÍA esas cuentas):
1. Cada cuenta de rol Docente → is_active=False y rol=None. Ninguna cuenta
   se borra; sus reservas y solicitudes siguen ligadas a ella.
2. Recién entonces se borra la fila Rol "Docente" (ya sin cuentas).

Reversa: recrea el Rol "Docente" y se lo devuelve, reactivándolas, a las
cuentas que quedaron como Profesor.cuenta_anterior (las convertidas en
solicitudes.0012). La cuenta descartada (e2e_profesor) no tiene Profesor y
queda como está: inactiva y sin rol.
"""
from django.db import migrations

ROL_DOCENTE = 'Docente'


def quitar_rol_docente(apps, schema_editor):
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')
    roles = Rol.objects.filter(nombre=ROL_DOCENTE)
    Usuario.objects.filter(rol__in=roles).update(is_active=False, rol=None)
    if Usuario.objects.filter(rol__in=roles).exists():  # no debería pasar
        raise RuntimeError('users.0008: quedan cuentas con rol Docente; no se borra el rol.')
    roles.delete()


def devolver_rol_docente(apps, schema_editor):
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')
    Profesor = apps.get_model('solicitudes', 'Profesor')
    rol, _ = Rol.objects.get_or_create(nombre=ROL_DOCENTE)
    cuentas = Profesor.objects.filter(cuenta_anterior__isnull=False).values_list('cuenta_anterior_id', flat=True)
    Usuario.objects.filter(id__in=list(cuentas)).update(rol=rol, is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_email_unico_sin_mayusculas'),
        ('solicitudes', '0012_docentes_a_profesores'),
    ]

    operations = [
        migrations.RunPython(quitar_rol_docente, devolver_rol_docente),
    ]
