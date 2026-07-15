from django.db import migrations


def generar_codigos(apps, schema_editor):
    from reservas.models import Reserva

    for reserva in Reserva.objects.filter(codigo=''):
        reserva.codigo = reserva.generar_codigo()
        reserva.save(update_fields=['codigo'])


def revertir(apps, schema_editor):
    Reserva = apps.get_model('reservas', 'Reserva')
    Reserva.objects.update(codigo='')


class Migration(migrations.Migration):

    dependencies = [
        ('reservas', '0004_reserva_codigo'),
    ]

    operations = [
        migrations.RunPython(generar_codigos, revertir),
    ]
