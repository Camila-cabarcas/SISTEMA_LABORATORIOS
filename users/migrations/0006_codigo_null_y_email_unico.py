"""
- Usuario.codigo pasa a null=True y los '' existentes se convierten en NULL,
  para que varios usuarios sin código no choquen con el unique.
- Usuario.email: único cuando no está vacío (UniqueConstraint condicional).
"""
from django.db import migrations, models


def codigo_vacio_a_null(apps, schema_editor):
    Usuario = apps.get_model('users', 'Usuario')
    Usuario.objects.filter(codigo='').update(codigo=None)


def codigo_null_a_vacio(apps, schema_editor):
    # Reverso: solo es posible si hay a lo sumo un usuario sin código (el
    # unique viejo no admite dos ''); si hay más, la migración inversa falla.
    Usuario = apps.get_model('users', 'Usuario')
    Usuario.objects.filter(codigo__isnull=True).update(codigo='')


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('users', '0005_rol_laboratorista_y_monitor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='codigo',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.RunPython(codigo_vacio_a_null, codigo_null_a_vacio),
        migrations.AddConstraint(
            model_name='usuario',
            constraint=models.UniqueConstraint(
                condition=models.Q(('email', ''), _negated=True),
                fields=('email',),
                name='usuario_email_unico_si_no_vacio',
                violation_error_message='Ya existe una cuenta con ese correo electrónico.',
            ),
        ),
    ]
