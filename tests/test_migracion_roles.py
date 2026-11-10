"""
Migraciones de la fase 1: users.0005 (rol "Laboratorio" → "Laboratorista",
nuevo rol "Monitor") y laboratorio.0020 (encargados → laboratoristas,
nuevo campo monitores). Un usuario del rol viejo debe quedar con el rol nuevo
y conservar sus laboratorios.
"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ANTES = [('users', '0004_email_udea'), ('laboratorio', '0019_categoria_forma_mesa')]
DESPUES = [('users', '0005_rol_laboratorista_y_monitor'), ('laboratorio', '0020_laboratoristas_y_monitores')]


def _migrar(destino):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(destino)
    return executor.loader.project_state(destino).apps


@pytest.mark.django_db(transaction=True)
def test_usuario_laboratorio_pasa_a_laboratorista_y_conserva_laboratorios():
    apps = _migrar(ANTES)
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')
    Laboratorio = apps.get_model('laboratorio', 'Laboratorio')

    rol_viejo = Rol.objects.create(nombre='Laboratorio')
    usuario = Usuario.objects.create(username='lab_migracion', codigo='LAB-MIG', rol=rol_viejo)
    lab_a = Laboratorio.objects.create(nombre='Lab A', ubicacion='A')
    lab_b = Laboratorio.objects.create(nombre='Lab B', ubicacion='B')
    lab_a.encargados.add(usuario)
    lab_b.encargados.add(usuario)

    try:
        apps = _migrar(DESPUES)
        Rol = apps.get_model('users', 'Rol')
        Usuario = apps.get_model('users', 'Usuario')
        Laboratorio = apps.get_model('laboratorio', 'Laboratorio')

        usuario = Usuario.objects.get(username='lab_migracion')
        assert usuario.rol.nombre == 'Laboratorista'
        assert not Rol.objects.filter(nombre='Laboratorio').exists()
        assert Rol.objects.filter(nombre='Monitor').exists()
        assert set(
            Laboratorio.objects.filter(laboratoristas=usuario).values_list('nombre', flat=True)
        ) == {'Lab A', 'Lab B'}
        assert not Laboratorio.objects.filter(monitores=usuario).exists()
    finally:
        # Deja la BD de pruebas en el último estado para los demás tests.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_si_ya_existe_laboratorista_se_fusionan_los_roles():
    apps = _migrar(ANTES)
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')

    viejo = Rol.objects.create(nombre='Laboratorio')
    Rol.objects.create(nombre='Laboratorista')
    Usuario.objects.create(username='lab_fusion', codigo='LAB-FUS', rol=viejo)

    try:
        apps = _migrar(DESPUES)
        Rol = apps.get_model('users', 'Rol')
        Usuario = apps.get_model('users', 'Usuario')
        assert Usuario.objects.get(username='lab_fusion').rol.nombre == 'Laboratorista'
        assert Rol.objects.filter(nombre='Laboratorista').count() == 1
        assert not Rol.objects.filter(nombre='Laboratorio').exists()
    finally:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
