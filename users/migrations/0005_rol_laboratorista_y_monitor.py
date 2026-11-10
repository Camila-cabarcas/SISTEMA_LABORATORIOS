"""
Renombra el rol "Laboratorio" a "Laboratorista" y crea el rol "Monitor".

Los usuarios conservan su fila de Rol (se cambia el nombre, no la FK), así
que siguen en los mismos laboratorios. Si ya existiera un Rol
"Laboratorista", los usuarios del rol viejo se pasan a ese y se borra el viejo.
"""
from django.db import migrations

VIEJO = 'Laboratorio'
NUEVO = 'Laboratorista'
MONITOR = 'Monitor'


def renombrar(apps, schema_editor):
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')

    destino = Rol.objects.filter(nombre=NUEVO).first()
    for viejo in Rol.objects.filter(nombre=VIEJO):
        if destino is None:
            viejo.nombre = NUEVO
            viejo.save(update_fields=['nombre'])
            destino = viejo
        else:
            Usuario.objects.filter(rol=viejo).update(rol=destino)
            viejo.delete()

    if not Rol.objects.filter(nombre=MONITOR).exists():
        Rol.objects.create(nombre=MONITOR)


def revertir(apps, schema_editor):
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')

    destino = Rol.objects.filter(nombre=VIEJO).first()
    for nuevo in Rol.objects.filter(nombre=NUEVO):
        if destino is None:
            nuevo.nombre = VIEJO
            nuevo.save(update_fields=['nombre'])
            destino = nuevo
        else:
            Usuario.objects.filter(rol=nuevo).update(rol=destino)
            nuevo.delete()

    # Solo se borra el rol Monitor si nadie lo usa (si no, CASCADE se
    # llevaría a esos usuarios).
    for monitor in Rol.objects.filter(nombre=MONITOR):
        if not Usuario.objects.filter(rol=monitor).exists():
            monitor.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_email_udea'),
    ]

    operations = [
        migrations.RunPython(renombrar, revertir),
    ]
