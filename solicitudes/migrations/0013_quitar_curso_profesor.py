"""
Fase 2, etapa 3: quitar el campo viejo Curso.profesor (cuenta Docente) y
dejar como campo final Curso.profesor → Profesor (sin cuenta).

1. Verifica que todos los cursos tengan profesor_registro (la 0012 los
   llenó); si alguno no, falla con la lista y no cambia nada.
2. Quita Curso.profesor (FK a Usuario).
3. Renombra Curso.profesor_registro → Curso.profesor.
4. Lo hace obligatorio (cada curso tiene su profesor; PROTECT).

Reversa: vuelve a opcional, renombra a profesor_registro, recrea el campo
viejo Curso.profesor (opcional) y lo rellena con la cuenta Docente
anterior de cada Profesor (Profesor.cuenta_anterior), para que las
reversas de la 0012 y la 0010 encuentren los datos como estaban. Los cursos
cuyo profesor no viene de una cuenta Docente (creados desde la fase 2)
quedan con el campo viejo vacío.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class DatosInvalidos(Exception):
    pass


def verificar(apps, schema_editor):
    Curso = apps.get_model('solicitudes', 'Curso')
    sin_profesor = list(Curso.objects.filter(profesor_registro__isnull=True)
                        .order_by('codigo').values_list('codigo', flat=True))
    if sin_profesor:
        raise DatosInvalidos(
            'solicitudes.0013: estos cursos no tienen profesor (Profesor): '
            f'{", ".join(sin_profesor)}. Asígnales uno y vuelve a migrar; no se cambió nada.'
        )


def restaurar_campo_viejo(apps, schema_editor):
    Curso = apps.get_model('solicitudes', 'Curso')
    for curso in Curso.objects.select_related('profesor_registro').filter(
            profesor_registro__cuenta_anterior__isnull=False):
        curso.profesor_id = curso.profesor_registro.cuenta_anterior_id
        curso.save(update_fields=['profesor'])


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0012_docentes_a_profesores'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(verificar, restaurar_campo_viejo),
        migrations.RemoveField(model_name='curso', name='profesor'),
        migrations.RenameField(model_name='curso', old_name='profesor_registro', new_name='profesor'),
        migrations.AlterField(
            model_name='curso',
            name='profesor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='cursos', to='solicitudes.profesor'),
        ),
    ]
