from django.db import migrations


def generar_codigos(apps, schema_editor):
    from prestamos.models import Prestamo

    # .only('id', 'codigo'): esta migración importa el modelo Prestamo
    # "vivo" (no el historico de apps.get_model()) para poder llamar a
    # generar_codigo(), que hace falta reconstruir a mano si no. Eso hace
    # que el SELECT incluya TODAS las columnas actuales del modelo — si
    # alguna se agregó en una migración posterior a esta (como
    # email_atraso_enviado en 0008), la consulta falla al recrear la base
    # desde cero (tests, entorno nuevo) porque esa columna todavía no
    # existe en este punto de la migración. Restringir a las columnas que
    # existen desde 0004 evita el problema para cualquier campo futuro.
    for prestamo in Prestamo.objects.filter(codigo='').only('id', 'codigo'):
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
