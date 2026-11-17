"""
Matriz de permisos de la sección Personal: cada acción contra Administrador,
Laboratorista (de `laboratorio`, «A»), Monitor (de A) y anónimo.

Esperado:
- Administrador: todo, en cualquier laboratorio.
- Laboratorista: Personal de SU laboratorio, sus fichas y su descripción;
  nada de cuentas; nada de otro laboratorio («B»).
- Monitor: nada (403).
- Anónimo: al login (302).

Las acciones de baja y borrado, cuando se permiten, responden 200 con el
formulario de contraseña admin (requiere_contrasena_admin): eso cuenta como
"permitido" aquí; lo que pasa después se prueba en test_personal_vistas.py.
"""
import pytest

from laboratorio.models import FichaMonitor, Laboratorio
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db

ROLES = ['admin', 'laboratorista', 'monitor', 'anonimo']
LOGIN = 302


@pytest.fixture
def lab_b(db):
    return Laboratorio.objects.create(nombre='Laboratorio B', ubicacion='Bloque B')


@pytest.fixture
def objetos(catalogos, laboratorio, lab_b, usuario_admin, usuario_laboratorista, usuario_monitor):
    rol_lab = Rol.objects.get(nombre='Laboratorista')
    cuenta_b = Usuario.objects.create_user(
        username='lab_b', password='x', email='lab.b@udea.edu.co', rol=rol_lab)
    lab_b.laboratoristas.add(cuenta_b)
    monitor_b = Usuario.objects.create_user(
        username='monitor_b', password='x', email='monitor.b@udea.edu.co', rol=Rol.objects.get(nombre='Monitor'))
    lab_b.monitores.add(monitor_b)
    ficha_a = FichaMonitor.objects.create(nombre='Ana', apellido='A')
    ficha_a.laboratorios.add(laboratorio)
    ficha_b = FichaMonitor.objects.create(nombre='Beto', apellido='B')
    ficha_b.laboratorios.add(lab_b)
    return {
        'lab_a': laboratorio, 'lab_b': lab_b, 'cuenta_b': cuenta_b, 'monitor_b': monitor_b,
        'ficha_a': ficha_a, 'ficha_b': ficha_b,
        'usuarios': {'admin': usuario_admin, 'laboratorista': usuario_laboratorista, 'monitor': usuario_monitor},
    }


@pytest.fixture
def como(client, objetos):
    def _cliente(rol):
        if rol != 'anonimo':
            client.force_login(objetos['usuarios'][rol])
        return client
    return _cliente


def _cuenta_nueva(o):
    return {'username': 'nueva', 'email': 'nueva@udea.edu.co', 'first_name': 'N', 'last_name': 'N',
            'laboratorio': o['lab_b'].id, 'password': 'Clave12345'}


def _ficha(_):
    return {'nombre': 'Carla', 'apellido': 'C', 'activo': 'on'}


#   (acción, método, url(o), datos(o), {rol: estado esperado})
ACCIONES = [
    ('ver Personal', 'get', lambda o: '/laboratorio/personal/', None,
     {'admin': 200, 'laboratorista': 200, 'monitor': 403, 'anonimo': LOGIN}),

    ('formulario crear laboratorista', 'get', lambda o: '/laboratorio/personal/laboratoristas/crear/', None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('crear laboratorista', 'post', lambda o: '/laboratorio/personal/laboratoristas/crear/', _cuenta_nueva,
     {'admin': 302, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('editar laboratorista', 'get', lambda o: f"/laboratorio/personal/laboratoristas/{o['cuenta_b'].id}/editar/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('confirmar baja de laboratorista', 'get', lambda o: f"/laboratorio/personal/laboratoristas/{o['cuenta_b'].id}/baja/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('dar de baja laboratorista', 'post', lambda o: f"/laboratorio/personal/laboratoristas/{o['cuenta_b'].id}/baja/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('eliminar laboratorista', 'post', lambda o: f"/laboratorio/personal/laboratoristas/{o['cuenta_b'].id}/eliminar/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),

    ('formulario crear monitor', 'get', lambda o: '/laboratorio/personal/monitores/crear/', None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('editar monitor', 'get', lambda o: f"/laboratorio/personal/monitores/{o['monitor_b'].id}/editar/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('dar de baja monitor', 'post', lambda o: f"/laboratorio/personal/monitores/{o['monitor_b'].id}/baja/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),

    ('formulario ficha en su laboratorio', 'get', lambda o: f"/laboratorio/personal/fichas/crear/?laboratorio={o['lab_a'].id}", None,
     {'admin': 200, 'laboratorista': 200, 'monitor': 403, 'anonimo': LOGIN}),
    ('formulario ficha en otro laboratorio', 'get', lambda o: f"/laboratorio/personal/fichas/crear/?laboratorio={o['lab_b'].id}", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('crear ficha en su laboratorio', 'post', lambda o: f"/laboratorio/personal/fichas/crear/?laboratorio={o['lab_a'].id}", _ficha,
     {'admin': 302, 'laboratorista': 302, 'monitor': 403, 'anonimo': LOGIN}),
    ('crear ficha en otro laboratorio', 'post', lambda o: f"/laboratorio/personal/fichas/crear/?laboratorio={o['lab_b'].id}", _ficha,
     {'admin': 302, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('editar ficha de su laboratorio', 'get', lambda o: f"/laboratorio/personal/fichas/{o['ficha_a'].id}/editar/", None,
     {'admin': 200, 'laboratorista': 200, 'monitor': 403, 'anonimo': LOGIN}),
    ('editar ficha de otro laboratorio', 'get', lambda o: f"/laboratorio/personal/fichas/{o['ficha_b'].id}/editar/", None,
     {'admin': 200, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('quitar ficha de su laboratorio', 'post', lambda o: f"/laboratorio/personal/fichas/{o['ficha_a'].id}/quitar/",
     lambda o: {'laboratorio_id': o['lab_a'].id},
     {'admin': 302, 'laboratorista': 302, 'monitor': 403, 'anonimo': LOGIN}),
    ('quitar ficha de otro laboratorio', 'post', lambda o: f"/laboratorio/personal/fichas/{o['ficha_b'].id}/quitar/",
     lambda o: {'laboratorio_id': o['lab_b'].id},
     {'admin': 302, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
    ('vincular ficha a su laboratorio', 'post', lambda o: f"/laboratorio/personal/fichas/{o['ficha_b'].id}/vincular/",
     lambda o: {'laboratorio_id': o['lab_a'].id},
     {'admin': 302, 'laboratorista': 302, 'monitor': 403, 'anonimo': LOGIN}),
    ('vincular ficha a otro laboratorio', 'post', lambda o: f"/laboratorio/personal/fichas/{o['ficha_a'].id}/vincular/",
     lambda o: {'laboratorio_id': o['lab_b'].id},
     {'admin': 302, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),

    ('editar descripción de su laboratorio', 'post', lambda o: f"/laboratorio/{o['lab_a'].id}/descripcion/editar/",
     lambda o: {'descripcion': 'Nueva'},
     {'admin': 302, 'laboratorista': 302, 'monitor': 403, 'anonimo': LOGIN}),
    ('editar descripción de otro laboratorio', 'post', lambda o: f"/laboratorio/{o['lab_b'].id}/descripcion/editar/",
     lambda o: {'descripcion': 'Nueva'},
     {'admin': 302, 'laboratorista': 403, 'monitor': 403, 'anonimo': LOGIN}),
]


@pytest.mark.parametrize('rol', ROLES)
@pytest.mark.parametrize('accion, metodo, url, datos, esperado', ACCIONES, ids=[a[0] for a in ACCIONES])
def test_matriz_personal(como, objetos, rol, accion, metodo, url, datos, esperado):
    cliente = como(rol)
    peticion = getattr(cliente, metodo)
    respuesta = peticion(url(objetos), datos(objetos) if datos else {})

    assert respuesta.status_code == esperado[rol], (
        f'{accion} como {rol}: {respuesta.status_code} (esperado {esperado[rol]})')
    if esperado[rol] == LOGIN and rol == 'anonimo':
        assert respuesta['Location'].startswith('/login/')
