"""
Matriz de permisos de profesores (fase 2): cada acción contra Administrador,
Laboratorista, Monitor, Estudiante y anónimo.

- Profesores habilitados (lista, editar, desactivar): solo Administrador.
- Solicitudes de profesor (lista, aprobar, rechazar): Administrador y
  Laboratorista (aquí, una solicitud sin laboratorio de interés, que
  cualquier laboratorista puede resolver).
- Registro público: todos, sin sesión.

Denegado = rol_requerido redirige a «sin permiso»; anónimo = al login.
"""
import pytest
from django.urls import reverse

from solicitudes.models import Profesor, SolicitudRegistroProfesor

pytestmark = pytest.mark.django_db

ROLES = ['admin', 'laboratorista', 'monitor', 'estudiante', 'anonimo']
OK, NO, LOGIN = 'ok', 'sin_permiso', 'login'


@pytest.fixture
def objetos(catalogos, usuario_admin, usuario_laboratorista, usuario_monitor, usuario_estudiante):
    return {
        'profesor': Profesor.objects.create(nombre='Ana', apellido='Ruiz', cedula='777'),
        'solicitud': SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='321', correo='pedro@udea.edu.co'),
        'usuarios': {'admin': usuario_admin, 'laboratorista': usuario_laboratorista,
                     'monitor': usuario_monitor, 'estudiante': usuario_estudiante},
    }


def _resultado(respuesta, esperado_ok):
    if respuesta.status_code in (301, 302):
        destino = respuesta['Location']
        if destino.startswith('/login/'):
            return LOGIN
        if destino.startswith(reverse('sin_permiso')):
            return NO
        return OK if esperado_ok == 302 else f'redirect {destino}'
    if respuesta.status_code == 403:
        return NO
    return OK if respuesta.status_code == esperado_ok else f'status {respuesta.status_code}'


#   (acción, método, url(o), datos(o), código si se permite, {rol: resultado})
SOLO_ADMIN = {'admin': OK, 'laboratorista': NO, 'monitor': NO, 'estudiante': NO, 'anonimo': LOGIN}
ADMIN_Y_LAB = {'admin': OK, 'laboratorista': OK, 'monitor': NO, 'estudiante': NO, 'anonimo': LOGIN}
TODOS = {rol: OK for rol in ROLES}

ACCIONES = [
    ('lista de profesores habilitados', 'get', lambda o: reverse('lista_profesores'), None, 200, SOLO_ADMIN),
    ('detalle de profesor', 'get', lambda o: reverse('detalle_profesor', args=[o['profesor'].id]), None, 200, SOLO_ADMIN),
    ('editar profesor', 'post', lambda o: reverse('editar_profesor', args=[o['profesor'].id]),
     lambda o: {'nombre': 'Ana María', 'apellido': 'Ruiz', 'correo': '', 'programa': ''}, 302, SOLO_ADMIN),
    ('desactivar profesor', 'post', lambda o: reverse('desactivar_profesor', args=[o['profesor'].id]),
     None, 302, SOLO_ADMIN),
    ('lista de solicitudes', 'get', lambda o: reverse('lista_solicitudes_profesores'), None, 200, ADMIN_Y_LAB),
    ('aprobar solicitud', 'post', lambda o: reverse('detalle_solicitud_profesor', args=[o['solicitud'].id]),
     lambda o: {'accion': 'aprobar_profesor'}, 302, ADMIN_Y_LAB),
    ('rechazar solicitud', 'post', lambda o: reverse('detalle_solicitud_profesor', args=[o['solicitud'].id]),
     lambda o: {'accion': 'rechazar_profesor', 'motivo': 'Datos incompletos'}, 302, ADMIN_Y_LAB),
    ('registro público', 'get', lambda o: reverse('registro_profesor_publico'), None, 200, TODOS),
]


@pytest.mark.parametrize('rol', ROLES)
@pytest.mark.parametrize('accion, metodo, url, datos, codigo_ok, esperado', ACCIONES, ids=[a[0] for a in ACCIONES])
def test_matriz_profesores(client, objetos, rol, accion, metodo, url, datos, codigo_ok, esperado):
    if rol != 'anonimo':
        client.force_login(objetos['usuarios'][rol])
    respuesta = getattr(client, metodo)(url(objetos), datos(objetos) if datos else {})
    assert _resultado(respuesta, codigo_ok) == esperado[rol], f'{accion} como {rol}'


@pytest.mark.parametrize('rol', ['laboratorista', 'monitor', 'estudiante', 'anonimo'])
def test_acciones_denegadas_no_cambian_nada(client, objetos, rol):
    if rol != 'anonimo':
        client.force_login(objetos['usuarios'][rol])
    profesor, solicitud = objetos['profesor'], objetos['solicitud']
    client.post(reverse('desactivar_profesor', args=[profesor.id]))
    client.post(reverse('editar_profesor', args=[profesor.id]),
                {'nombre': 'X', 'apellido': 'Y', 'correo': '', 'programa': ''})
    if rol != 'laboratorista':
        client.post(reverse('detalle_solicitud_profesor', args=[solicitud.id]), {'accion': 'aprobar_profesor'})
    profesor.refresh_from_db()
    solicitud.refresh_from_db()
    assert profesor.activo and profesor.nombre == 'Ana'
    if rol != 'laboratorista':
        assert solicitud.estado == 'pendiente'
