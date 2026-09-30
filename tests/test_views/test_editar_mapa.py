"""
Tests HTTP para laboratorio/views.py::editar_mapa_laboratorio
(/laboratorio/<lab_id>/editar-mapa/): editor del mapa, solo Administrador.
"""
import pytest
from django.urls import reverse

from laboratorio.models import Modulo
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


def _url(laboratorio):
    return reverse('editar_mapa', args=[laboratorio.id])


def _usuario(rol, username, **extra):
    return Usuario.objects.create_user(
        username=username, password='clave12345',
        rol=Rol.objects.get(nombre=rol), codigo=username.upper(), **extra,
    )


def test_url_existe():
    assert reverse('editar_mapa', args=[7]) == '/laboratorio/7/editar-mapa/'


# ── Acceso ───────────────────────────────────────────────────────────────────

def test_administrador_puede_acceder(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(_url(laboratorio))

    assert response.status_code == 200
    assert response.templates[0].name == 'laboratorio/editar_mapa.html'


def test_anonimo_redirige_al_login(client, laboratorio):
    response = client.get(_url(laboratorio))

    assert response.status_code == 302
    assert response.url.startswith('/login/')


@pytest.mark.parametrize('rol', ['Laboratorio', 'Docente', 'Estudiante'])
def test_otros_roles_reciben_403(client, catalogos, laboratorio, rol):
    usuario = _usuario(rol, f'user_{rol.lower()}')
    laboratorio.encargados.add(usuario)  # ni siendo encargado del lab
    client.force_login(usuario)

    assert client.get(_url(laboratorio)).status_code == 403


def test_is_staff_sin_rol_administrador_recibe_403(client, catalogos, laboratorio):
    # El rol manda, no el flag de Django (ver users/helpers.py).
    client.force_login(_usuario('Laboratorio', 'staff_lab', is_staff=True))

    assert client.get(_url(laboratorio)).status_code == 403


def test_laboratorio_inexistente_404(cliente_autenticado):
    assert cliente_autenticado.get('/laboratorio/999999/editar-mapa/').status_code == 404


# ── Contenido ────────────────────────────────────────────────────────────────

def test_renderiza_modulos_con_su_posicion(cliente_autenticado, laboratorio, otro_laboratorio_con_modulo):
    m1 = Modulo.objects.create(nombre='Mesa A', capacidad=4, laboratorio=laboratorio, posicion_x=150, posicion_y=40)
    m2 = Modulo.objects.create(nombre='Mesa B', capacidad=4, laboratorio=laboratorio, posicion_x=300, posicion_y=220)

    response = cliente_autenticado.get(_url(laboratorio))

    assert [m.id for m in response.context['modulos']] == [m1.id, m2.id]
    contenido = response.content.decode()
    assert 'id="editor-canvas"' in contenido
    assert f'data-id="{m1.id}"' in contenido
    assert 'style="left: 150px; top: 40px;"' in contenido
    assert 'style="left: 300px; top: 220px;"' in contenido
    assert 'Mesa de otro lab' not in contenido
    assert 'id="btn-guardar"' in contenido
    assert f'href="/laboratorio/{laboratorio.id}/mapa/"' in contenido


def test_aviso_de_modulos_sin_posicion(cliente_autenticado, laboratorio):
    for n in range(3):
        Modulo.objects.create(nombre=f'Mesa {n}', capacidad=2, laboratorio=laboratorio)
    Modulo.objects.create(nombre='Ubicada', capacidad=2, laboratorio=laboratorio, posicion_x=10, posicion_y=10)

    response = cliente_autenticado.get(_url(laboratorio))

    assert response.context['sin_posicion'] == 3
    assert '3 módulos aún no tienen posición guardada' in response.content.decode()


def test_laboratorio_sin_modulos(cliente_autenticado, laboratorio):
    contenido = cliente_autenticado.get(_url(laboratorio)).content.decode()

    assert 'Este laboratorio no tiene módulos.' in contenido
    assert 'aún no tienen posición' not in contenido


@pytest.fixture
def otro_laboratorio_con_modulo(db):
    from laboratorio.models import Laboratorio
    otro = Laboratorio.objects.create(nombre='Otro', ubicacion='Bloque 9')
    return Modulo.objects.create(nombre='Mesa de otro lab', capacidad=2, laboratorio=otro)
