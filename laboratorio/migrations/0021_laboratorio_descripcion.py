"""Laboratorio.descripcion: descripción general del laboratorio (texto, opcional)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0020_laboratoristas_y_monitores'),
    ]

    operations = [
        migrations.AddField(
            model_name='laboratorio',
            name='descripcion',
            field=models.TextField(blank=True, default='', verbose_name='Descripción'),
        ),
    ]
