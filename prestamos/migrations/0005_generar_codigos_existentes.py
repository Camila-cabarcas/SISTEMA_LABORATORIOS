from django.db import migrations


def generar_codigos(apps, schema_editor):
    from prestamos.models import Prestamo

    for prestamo in Prestamo.objects.filter(codigo=''):
        prestamo.codigo = prestamo.generar_codigo()
        prestamo.save(update_fields=['codigo'])


def revertir(apps, schema_editor):
    Prestamo = apps.get_model('prestamos', 'Prestamo')
    Prestamo.objects.update(codigo='')


class Migration(migrations.Migration):

    dependencies = [
        ('prestamos', '0004_prestamo_codigo'),
    ]

    operations = [
        migrations.RunPython(generar_codigos, revertir),
    ]
