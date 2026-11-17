"""
Un laboratorio por cuenta (fase Personal, etapa 1).

1. Valida los datos y, si algo no cumple, falla con un mensaje que dice qué
   cuentas o laboratorios corregir (no adivina ni cambia nada):
   - toda cuenta Laboratorista ACTIVA tiene exactamente un laboratorio
     (las inactivas pueden no tener ninguno);
   - ninguna cuenta está en más de un laboratorio como laboratorista;
   - ninguna cuenta Monitor está en más de un laboratorio;
   - ningún laboratorio tiene más de una cuenta de monitor.
2. Convierte las tablas intermedias de Laboratorio.laboratoristas y
   Laboratorio.monitores en modelos explícitos (AsignacionLaboratorista y
   AsignacionMonitor) SOBRE LAS MISMAS TABLAS: solo cambia el estado de
   Django, no la base.
3. Agrega las restricciones únicas:
   - laboratorista_un_solo_laboratorio (usuario)
   - monitor_un_solo_laboratorio (usuario)
   - laboratorio_una_cuenta_monitor (laboratorio)

La regla "una cuenta Laboratorista activa tiene exactamente un laboratorio"
no se puede expresar como restricción de la base (depende de que exista una
fila): la base garantiza "a lo sumo uno" y el servicio de Personal, "al
menos uno".

Reversa: quita las restricciones y vuelve a las tablas automáticas.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Count


class DatosInvalidos(Exception):
    pass


def validar(apps, schema_editor):
    Usuario = apps.get_model('users', 'Usuario')
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
    PorLaboratorista = Laboratorio.laboratoristas.through
    PorMonitor = Laboratorio.monitores.through

    problemas = []

    activas = (Usuario.objects.filter(rol__nombre='Laboratorista', is_active=True)
               .annotate(n=Count('laboratorios_asignados')).order_by('username'))
    for usuario in activas:
        if usuario.n != 1:
            problemas.append(
                f'- La cuenta Laboratorista activa "{usuario.username}" tiene {usuario.n} '
                f'laboratorios; debe tener exactamente 1 (o darse de baja).'
            )

    for fila in (PorLaboratorista.objects.values('usuario__username')
                 .annotate(n=Count('id')).filter(n__gt=1).order_by('usuario__username')):
        problemas.append(
            f'- La cuenta "{fila["usuario__username"]}" es laboratorista de {fila["n"]} laboratorios; '
            f'solo puede tener 1.'
        )

    for fila in (PorMonitor.objects.values('usuario__username')
                 .annotate(n=Count('id')).filter(n__gt=1).order_by('usuario__username')):
        problemas.append(
            f'- La cuenta de monitor "{fila["usuario__username"]}" está en {fila["n"]} laboratorios; '
            f'solo puede tener 1.'
        )

    for fila in (PorMonitor.objects.values('laboratorio__nombre')
                 .annotate(n=Count('id')).filter(n__gt=1).order_by('laboratorio__nombre')):
        problemas.append(
            f'- El laboratorio "{fila["laboratorio__nombre"]}" tiene {fila["n"]} cuentas de monitor; '
            f'solo puede tener 1.'
        )

    if problemas:
        raise DatosInvalidos(
            'laboratorio.0024: hay datos que no cumplen "un laboratorio por cuenta". '
            'Corrígelos y vuelve a migrar; no se cambió nada.\n' + '\n'.join(problemas)
        )


ESTADO = [
    migrations.CreateModel(
        name='AsignacionLaboratorista',
        fields=[
            ('id', models.AutoField(primary_key=True, serialize=False)),
            ('laboratorio', models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='laboratorio.laboratorio')),
            ('usuario', models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ],
        options={
            'verbose_name': 'Asignación de laboratorista',
            'verbose_name_plural': 'Asignaciones de laboratoristas',
            'db_table': 'laboratorio_laboratorio_laboratoristas',
            'unique_together': {('laboratorio', 'usuario')},
        },
    ),
    migrations.CreateModel(
        name='AsignacionMonitor',
        fields=[
            ('id', models.AutoField(primary_key=True, serialize=False)),
            ('laboratorio', models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='laboratorio.laboratorio')),
            ('usuario', models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ],
        options={
            'verbose_name': 'Asignación de monitor',
            'verbose_name_plural': 'Asignaciones de monitores',
            'db_table': 'laboratorio_laboratorio_monitores',
            'unique_together': {('laboratorio', 'usuario')},
        },
    ),
    migrations.AlterField(
        model_name='laboratorio',
        name='laboratoristas',
        field=models.ManyToManyField(
            blank=True, limit_choices_to={'rol__nombre': 'Laboratorista'},
            related_name='laboratorios_asignados', through='laboratorio.AsignacionLaboratorista',
            to=settings.AUTH_USER_MODEL, verbose_name='Laboratoristas',
        ),
    ),
    migrations.AlterField(
        model_name='laboratorio',
        name='monitores',
        field=models.ManyToManyField(
            blank=True, limit_choices_to={'rol__nombre': 'Monitor'},
            related_name='laboratorios_monitoreados', through='laboratorio.AsignacionMonitor',
            to=settings.AUTH_USER_MODEL, verbose_name='Monitores',
        ),
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0023_dar_de_baja_y_borrar_personas'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(validar, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(state_operations=ESTADO, database_operations=[]),
        migrations.AddConstraint(
            model_name='asignacionlaboratorista',
            constraint=models.UniqueConstraint(
                fields=('usuario',), name='laboratorista_un_solo_laboratorio',
                violation_error_message='Esta cuenta ya tiene un laboratorio asignado.',
            ),
        ),
        migrations.AddConstraint(
            model_name='asignacionmonitor',
            constraint=models.UniqueConstraint(
                fields=('usuario',), name='monitor_un_solo_laboratorio',
                violation_error_message='Esta cuenta de monitor ya tiene un laboratorio asignado.',
            ),
        ),
        migrations.AddConstraint(
            model_name='asignacionmonitor',
            constraint=models.UniqueConstraint(
                fields=('laboratorio',), name='laboratorio_una_cuenta_monitor',
                violation_error_message='Este laboratorio ya tiene una cuenta de monitor.',
            ),
        ),
    ]
