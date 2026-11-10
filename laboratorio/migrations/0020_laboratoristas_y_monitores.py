"""
Laboratorio.encargados pasa a llamarse Laboratorio.laboratoristas
(RenameField: conserva las asignaciones actuales) y se agrega
Laboratorio.monitores. El filtro del selector apunta al rol "Laboratorista"
(antes a "Encargado", un rol que no existía).
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0019_categoria_forma_mesa'),
        ('users', '0005_rol_laboratorista_y_monitor'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='laboratorio',
            old_name='encargados',
            new_name='laboratoristas',
        ),
        migrations.AlterField(
            model_name='laboratorio',
            name='laboratoristas',
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={'rol__nombre': 'Laboratorista'},
                related_name='laboratorios_asignados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Laboratoristas',
            ),
        ),
        migrations.AddField(
            model_name='laboratorio',
            name='monitores',
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={'rol__nombre': 'Monitor'},
                related_name='laboratorios_monitoreados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Monitores',
            ),
        ),
    ]
