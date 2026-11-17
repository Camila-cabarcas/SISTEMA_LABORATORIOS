"""FichaMonitor: persona monitor sin cuenta, en uno o varios laboratorios."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0021_laboratorio_descripcion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FichaMonitor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(max_length=100)),
                ('correo', models.EmailField(blank=True, default='', max_length=254)),
                ('telefono', models.CharField(blank=True, default='', max_length=30)),
                ('descripcion', models.TextField(blank=True, default='')),
                ('activo', models.BooleanField(default=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
                ('creado_por', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='fichas_monitor_creadas', to=settings.AUTH_USER_MODEL,
                )),
                ('laboratorios', models.ManyToManyField(
                    blank=True, related_name='fichas_monitor', to='laboratorio.laboratorio',
                )),
            ],
            options={
                'verbose_name': 'Ficha de monitor',
                'verbose_name_plural': 'Fichas de monitor',
                'ordering': ['apellido', 'nombre'],
            },
        ),
    ]
