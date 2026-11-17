"""
SOLO DATOS (fase Personal, etapa 1).

Adelante:
- Da de baja (is_active=False) las cuentas lab_mecanica, lab_test, lab_ondas,
  lab_sistemas y e2e_laboratorista, y les quita su laboratorio. No las borra:
  conservan préstamos, reservas y movimientos.
- Borra las personas sin cuenta (modelo Laboratorista) y sus asignaciones
  (LaboratoristaLab). Se descartan: no se migran a FichaMonitor.
  Los modelos se eliminan después, en la 0025, junto con sus vistas.

Reversa:
- Reactiva las 4 cuentas lab_* y les devuelve su laboratorio según
  LABORATORIO_DE_CUENTA (por nombre de laboratorio; si no existe, la cuenta
  queda sin laboratorio).
- Reactiva e2e_laboratorista, sin laboratorio. La migración no guarda el
  estado previo de la cuenta: se asume que estaba activa, como en la base
  donde se aplicó por primera vez.
- Las personas borradas NO se restauran.

Va antes de la 0024 porque esa valida que toda cuenta Laboratorista activa
tenga exactamente un laboratorio, y e2e_laboratorista no tiene ninguno.
"""
from django.db import migrations

LABORATORIO_DE_CUENTA = {
    'lab_mecanica': 'LAB-Mecanica',
    'lab_test': 'Lab Test',
    'lab_ondas': 'Laboratorio de ondas',
    'lab_sistemas': 'Lab de Ingenieria de sistemas',
}
CUENTA_E2E = 'e2e_laboratorista'
CUENTAS_DE_BAJA = [*LABORATORIO_DE_CUENTA, CUENTA_E2E]


def dar_de_baja_y_borrar_personas(apps, schema_editor):
    Usuario = apps.get_model('users', 'Usuario')
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
    Laboratorista = apps.get_model('laboratorio', 'Laboratorista')
    LaboratoristaLab = apps.get_model('laboratorio', 'LaboratoristaLab')

    cuentas = Usuario.objects.filter(username__in=CUENTAS_DE_BAJA)
    Laboratorio.laboratoristas.through.objects.filter(usuario__in=cuentas).delete()
    cuentas.update(is_active=False)

    LaboratoristaLab.objects.all().delete()
    Laboratorista.objects.all().delete()


def reactivar_cuentas(apps, schema_editor):
    Usuario = apps.get_model('users', 'Usuario')
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
    Asignacion = Laboratorio.laboratoristas.through

    for username, nombre_lab in LABORATORIO_DE_CUENTA.items():
        usuario = Usuario.objects.filter(username=username).first()
        if usuario is None:
            continue
        usuario.is_active = True
        usuario.save(update_fields=['is_active'])
        laboratorio = Laboratorio.objects.filter(nombre=nombre_lab).order_by('id').first()
        if laboratorio is not None:
            Asignacion.objects.get_or_create(laboratorio=laboratorio, usuario=usuario)

    Usuario.objects.filter(username=CUENTA_E2E).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0022_fichamonitor'),
        ('users', '0007_email_unico_sin_mayusculas'),
    ]

    operations = [
        migrations.RunPython(dar_de_baja_y_borrar_personas, reactivar_cuentas),
    ]
