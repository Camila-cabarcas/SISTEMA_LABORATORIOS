"""
Fase 2, etapa 1: modelo Profesor (profesor habilitado SIN cuenta) y el campo
nuevo Curso.profesor_registro (PROTECT). El campo viejo Curso.profesor (cuenta
Docente) se conserva hasta la etapa 3; los datos se copian en la 0012.

Curso.profesor pasa a opcional (SET_NULL): desde la etapa 2 el código ya no
lo llena, y siendo obligatorio no se podría crear ningún curso nuevo.
Reversa: vuelve a obligatorio; falla si para entonces hay cursos sin cuenta
Docente (los creados desde la etapa 2), que es lo esperado.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0009_curso_laboratorio'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Profesor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(max_length=100)),
                ('cedula', models.CharField(max_length=20, unique=True)),
                ('correo', models.EmailField(blank=True, default='', max_length=254)),
                ('programa', models.CharField(blank=True, default='', max_length=200)),
                ('activo', models.BooleanField(default=True)),
                ('cuenta_anterior', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='profesores_migrados', to=settings.AUTH_USER_MODEL)),
                ('solicitud_origen', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='profesores_creados', to='solicitudes.solicitudregistroprofesor')),
            ],
            options={
                'verbose_name': 'Profesor',
                'verbose_name_plural': 'Profesores',
                'ordering': ['apellido', 'nombre'],
            },
        ),
        migrations.AlterField(
            model_name='curso',
            name='profesor',
            field=models.ForeignKey(
                blank=True, null=True, limit_choices_to={'rol__nombre': 'Docente'},
                on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='curso',
            name='profesor_registro',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='cursos', to='solicitudes.profesor'),
        ),
    ]
