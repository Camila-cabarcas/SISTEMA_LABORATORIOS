"""
Migraciones de la fase Personal (etapa 1):
- laboratorio.0023_dar_de_baja_y_borrar_personas (solo datos, reversible)
- laboratorio.0024_laboratorista_un_solo_laboratorio (validación +
  tablas intermedias explícitas + restricciones únicas, reversible)
"""
import importlib

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

M0022 = [('laboratorio', '0022_fichamonitor'), ('users', '0007_email_unico_sin_mayusculas')]
M0023 = [('laboratorio', '0023_dar_de_baja_y_borrar_personas')]
M0024 = [('laboratorio', '0024_laboratorista_un_solo_laboratorio')]

DatosInvalidos = importlib.import_module(
    'laboratorio.migrations.0024_laboratorista_un_solo_laboratorio'
).DatosInvalidos

CUENTAS_LAB = {
    'lab_mecanica': 'LAB-Mecanica',
    'lab_test': 'Lab Test',
    'lab_ondas': 'Laboratorio de ondas',
    'lab_sistemas': 'Lab de Ingenieria de sistemas',
}


def _migrar(destino):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    # La última de reservas (ya aplicada, no cambia nada) para tener el
    # modelo Reserva en el estado y comprobar que las bajas no borran datos.
    destino = [*destino, *executor.loader.graph.leaf_nodes('reservas')]
    executor.migrate(destino)
    return executor.loader.project_state(destino).apps


def _limpiar_y_migrar_al_final(apps):
    """Borra lo creado por el test (con los modelos del estado `apps`) y deja
    la BD de pruebas en la última migración para los demás tests."""
    apps.get_model('users', 'Usuario').objects.all().delete()
    apps.get_model('laboratorio', 'Laboratorio').objects.all().delete()
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


def _rol(apps, nombre):
    return apps.get_model('users', 'Rol').objects.get_or_create(nombre=nombre)[0]


def _cuenta(apps, username, rol='Laboratorista', activa=True):
    return apps.get_model('users', 'Usuario').objects.create(
        username=username, rol=_rol(apps, rol), is_active=activa,
    )


def _aplicada(nombre):
    return ('laboratorio', nombre) in MigrationRecorder(connection).applied_migrations()


# ── 0023: dar de baja y borrar personas ─────────────────────────────────

def _datos_0023(apps):
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
    Laboratorista = apps.get_model('laboratorio', 'Laboratorista')
    LaboratoristaLab = apps.get_model('laboratorio', 'LaboratoristaLab')
    Reserva = apps.get_model('reservas', 'Reserva')

    labs = {nombre: Laboratorio.objects.create(nombre=nombre, ubicacion='X') for nombre in CUENTAS_LAB.values()}
    for username, nombre_lab in CUENTAS_LAB.items():
        labs[nombre_lab].laboratoristas.add(_cuenta(apps, username))
    e2e = _cuenta(apps, 'e2e_laboratorista')
    Reserva.objects.create(usuario=e2e, fecha_reserva=timezone.now(), codigo='R-E2E-MIG')

    # Cuenta que la 0023 NO debe tocar.
    otra = _cuenta(apps, 'lab_que_se_queda')
    otro_lab = Laboratorio.objects.create(nombre='Lab Otro', ubicacion='Y')
    otro_lab.laboratoristas.add(otra)

    for i, nombre_lab in enumerate(['LAB-Mecanica', 'Lab Test', 'Laboratorio de ondas']):
        persona = Laboratorista.objects.create(nombre=f'P{i}', apellido='X', cedula=f'C{i}')
        LaboratoristaLab.objects.create(laboratorista=persona, laboratorio=labs[nombre_lab], tipo='encargado')
        LaboratoristaLab.objects.create(laboratorista=persona, laboratorio=otro_lab)


@pytest.mark.django_db(transaction=True)
def test_0023_da_de_baja_quita_laboratorios_y_borra_personas():
    apps = _migrar(M0022)
    _datos_0023(apps)
    try:
        apps = _migrar(M0023)
        Usuario = apps.get_model('users', 'Usuario')
        Reserva = apps.get_model('reservas', 'Reserva')

        for username in [*CUENTAS_LAB, 'e2e_laboratorista']:
            cuenta = Usuario.objects.get(username=username)  # no se borra
            assert cuenta.is_active is False
            assert not cuenta.laboratorios_asignados.exists()

        assert Reserva.objects.get(codigo='R-E2E-MIG').usuario.username == 'e2e_laboratorista'

        intacta = Usuario.objects.get(username='lab_que_se_queda')
        assert intacta.is_active is True
        assert list(intacta.laboratorios_asignados.values_list('nombre', flat=True)) == ['Lab Otro']

        assert apps.get_model('laboratorio', 'Laboratorista').objects.count() == 0
        assert apps.get_model('laboratorio', 'LaboratoristaLab').objects.count() == 0
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0023_reversa_reactiva_cuentas_y_devuelve_laboratorios():
    apps = _migrar(M0022)
    _datos_0023(apps)
    try:
        _migrar(M0023)
        apps = _migrar(M0022)
        Usuario = apps.get_model('users', 'Usuario')

        for username, nombre_lab in CUENTAS_LAB.items():
            cuenta = Usuario.objects.get(username=username)
            assert cuenta.is_active is True
            assert list(cuenta.laboratorios_asignados.values_list('nombre', flat=True)) == [nombre_lab]

        e2e = Usuario.objects.get(username='e2e_laboratorista')
        assert e2e.is_active is True
        assert not e2e.laboratorios_asignados.exists()

        # Las personas descartadas no se restauran.
        assert apps.get_model('laboratorio', 'Laboratorista').objects.count() == 0
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0023_reversa_si_el_laboratorio_ya_no_existe_la_cuenta_queda_sin_laboratorio():
    apps = _migrar(M0022)
    _datos_0023(apps)
    try:
        apps = _migrar(M0023)
        apps.get_model('laboratorio', 'Laboratorio').objects.filter(nombre='Lab Test').delete()
        apps = _migrar(M0022)
        cuenta = apps.get_model('users', 'Usuario').objects.get(username='lab_test')
        assert cuenta.is_active is True
        assert not cuenta.laboratorios_asignados.exists()
    finally:
        _limpiar_y_migrar_al_final(apps)


# ── 0024: un laboratorio por cuenta ─────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_0024_con_datos_validos_aplica_las_restricciones_y_es_reversible():
    apps = _migrar(M0023)
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
    lab_a = Laboratorio.objects.create(nombre='Lab A', ubicacion='A')
    lab_b = Laboratorio.objects.create(nombre='Lab B', ubicacion='B')
    lab_a.laboratoristas.add(_cuenta(apps, 'lab_activa'))
    _cuenta(apps, 'lab_de_baja', activa=False)  # inactiva sin laboratorio: válido
    lab_a.monitores.add(_cuenta(apps, 'monitor_a', rol='Monitor'))
    try:
        apps = _migrar(M0024)
        Usuario = apps.get_model('users', 'Usuario')
        Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
        AsignacionLaboratorista = apps.get_model('laboratorio', 'AsignacionLaboratorista')
        AsignacionMonitor = apps.get_model('laboratorio', 'AsignacionMonitor')
        lab_a, lab_b = Laboratorio.objects.get(nombre='Lab A'), Laboratorio.objects.get(nombre='Lab B')
        activa = Usuario.objects.get(username='lab_activa')
        monitor = Usuario.objects.get(username='monitor_a')

        # Los datos siguen ahí, ahora en los modelos explícitos.
        assert AsignacionLaboratorista.objects.get(usuario=activa).laboratorio == lab_a
        assert AsignacionMonitor.objects.get(usuario=monitor).laboratorio == lab_a

        with pytest.raises(IntegrityError), transaction.atomic():
            AsignacionLaboratorista.objects.create(laboratorio=lab_b, usuario=activa)
        with pytest.raises(IntegrityError), transaction.atomic():
            AsignacionMonitor.objects.create(laboratorio=lab_b, usuario=monitor)
        with pytest.raises(IntegrityError), transaction.atomic():
            AsignacionMonitor.objects.create(
                laboratorio=lab_a, usuario=_cuenta(apps, 'monitor_b', rol='Monitor'))

        # Reversa: sin las restricciones, un segundo laboratorio vuelve a entrar.
        apps = _migrar(M0023)
        Usuario = apps.get_model('users', 'Usuario')
        lab_b = apps.get_model('laboratorio', 'Laboratorio').objects.get(nombre='Lab B')
        lab_b.laboratoristas.add(Usuario.objects.get(username='lab_activa'))
        assert Usuario.objects.get(username='lab_activa').laboratorios_asignados.count() == 2
    finally:
        _limpiar_y_migrar_al_final(apps)


def _activa_sin_laboratorio(apps, labs):
    _cuenta(apps, 'lab_sin_lab')
    return 'La cuenta Laboratorista activa "lab_sin_lab" tiene 0 laboratorios'


def _activa_con_dos_laboratorios(apps, labs):
    cuenta = _cuenta(apps, 'lab_dos')
    labs[0].laboratoristas.add(cuenta)
    labs[1].laboratoristas.add(cuenta)
    return 'La cuenta Laboratorista activa "lab_dos" tiene 2 laboratorios'


def _inactiva_con_dos_laboratorios(apps, labs):
    cuenta = _cuenta(apps, 'lab_baja_dos', activa=False)
    labs[0].laboratoristas.add(cuenta)
    labs[1].laboratoristas.add(cuenta)
    return 'La cuenta "lab_baja_dos" es laboratorista de 2 laboratorios'


def _monitor_en_dos_laboratorios(apps, labs):
    cuenta = _cuenta(apps, 'monitor_dos', rol='Monitor')
    labs[0].monitores.add(cuenta)
    labs[1].monitores.add(cuenta)
    return 'La cuenta de monitor "monitor_dos" está en 2 laboratorios'


def _laboratorio_con_dos_monitores(apps, labs):
    labs[0].monitores.add(_cuenta(apps, 'monitor_1', rol='Monitor'), _cuenta(apps, 'monitor_2', rol='Monitor'))
    return 'El laboratorio "Lab 0" tiene 2 cuentas de monitor'


@pytest.mark.parametrize('preparar', [
    _activa_sin_laboratorio,
    _activa_con_dos_laboratorios,
    _inactiva_con_dos_laboratorios,
    _monitor_en_dos_laboratorios,
    _laboratorio_con_dos_monitores,
])
@pytest.mark.django_db(transaction=True)
def test_0024_falla_con_mensaje_claro_y_no_cambia_nada(preparar):
    apps = _migrar(M0023)
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')
    labs = [Laboratorio.objects.create(nombre=f'Lab {i}', ubicacion='X') for i in range(2)]
    esperado = preparar(apps, labs)
    try:
        with pytest.raises(DatosInvalidos) as error:
            _migrar(M0024)
        assert esperado in str(error.value)
        assert 'no se cambió nada' in str(error.value)
        assert not _aplicada('0024_laboratorista_un_solo_laboratorio')
    finally:
        _limpiar_y_migrar_al_final(apps)
