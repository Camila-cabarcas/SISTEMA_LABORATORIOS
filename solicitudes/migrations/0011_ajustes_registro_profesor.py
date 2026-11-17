"""
Fase 2, etapa 1: SolicitudRegistroProfesor
- campos nuevos: laboratorio_interes, resuelto_por, fecha_resolucion,
  motivo_rechazo y profesor (el Profesor creado al aprobar);
- la cédula deja de ser única global (unique=True fuera) y pasa a ser única
  solo entre solicitudes pendientes o aprobadas: tras un rechazo, la misma
  cédula puede volver a solicitar.

Reversa: quita la restricción, vuelve a unique=True y quita los campos. La
reversa falla si para entonces hay dos solicitudes con la misma cédula (una
rechazada y otra nueva): es el comportamiento esperado de un unique.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0025_eliminar_laboratorista_y_laboratoristalab'),
        ('solicitudes', '0010_profesor'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudregistroprofesor',
            name='laboratorio_interes',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='solicitudes_registro_profesor', to='laboratorio.laboratorio'),
        ),
        migrations.AddField(
            model_name='solicitudregistroprofesor',
            name='resuelto_por',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='solicitudes_profesor_resueltas', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='solicitudregistroprofesor',
            name='fecha_resolucion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='solicitudregistroprofesor',
            name='motivo_rechazo',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='solicitudregistroprofesor',
            name='profesor',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='solicitudes', to='solicitudes.profesor'),
        ),
        migrations.AlterField(
            model_name='solicitudregistroprofesor',
            name='cedula',
            field=models.CharField(max_length=20),
        ),
        migrations.AddConstraint(
            model_name='solicitudregistroprofesor',
            constraint=models.UniqueConstraint(
                condition=models.Q(('estado__in', ['pendiente', 'aprobada'])),
                fields=('cedula',),
                name='solicitud_profesor_cedula_activa_unica',
                violation_error_message='Ya existe una solicitud pendiente o aprobada con esta cédula.',
            ),
        ),
    ]
