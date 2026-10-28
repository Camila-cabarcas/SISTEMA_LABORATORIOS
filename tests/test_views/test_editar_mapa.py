"""
Tests HTTP para laboratorio/views.py::editar_mapa_laboratorio
(/laboratorio/<lab_id>/editar-mapa/) y guardar_mapa_laboratorio
(/laboratorio/<lab_id>/guardar-mapa/): editor del mapa, solo Administrador.
"""
import json

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


def test_editor_incluye_url_de_guardado_csrf_y_script(cliente_autenticado, laboratorio):
    contenido = cliente_autenticado.get(_url(laboratorio)).content.decode()

    assert f'data-guardar-url="/laboratorio/{laboratorio.id}/guardar-mapa/"' in contenido
    assert f'data-mapa-url="/laboratorio/{laboratorio.id}/mapa/"' in contenido
    assert 'data-csrf="' in contenido
    assert 'js/editar_mapa.js' in contenido


# ── Guardar posiciones (POST JSON) ───────────────────────────────────────────

def _url_guardar(laboratorio):
    return reverse('guardar_mapa', args=[laboratorio.id])


def _post(cliente, laboratorio, cuerpo):
    datos = cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)
    return cliente.post(_url_guardar(laboratorio), datos, content_type='application/json')


@pytest.fixture
def modulos(laboratorio):
    return [
        Modulo.objects.create(nombre='Mesa A', capacidad=4, laboratorio=laboratorio),
        Modulo.objects.create(nombre='Mesa B', capacidad=4, laboratorio=laboratorio, posicion_x=5, posicion_y=5),
    ]


def test_url_guardar_existe():
    assert reverse('guardar_mapa', args=[7]) == '/laboratorio/7/guardar-mapa/'


def test_guardar_actualiza_posiciones_en_bd(cliente_autenticado, laboratorio, modulos):
    a, b = modulos

    response = _post(cliente_autenticado, laboratorio, {'modulos': [
        {'id': a.id, 'x': 120, 'y': 40},
        {'id': b.id, 'x': 300, 'y': 210},
    ]})

    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'actualizados': 2, 'divisiones': 0}
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.posicion_x, a.posicion_y) == (120, 40)
    assert (b.posicion_x, b.posicion_y) == (300, 210)


def test_guardar_parcial_no_toca_los_demas(cliente_autenticado, laboratorio, modulos):
    a, b = modulos

    _post(cliente_autenticado, laboratorio, {'modulos': [{'id': a.id, 'x': 7, 'y': 8}]})

    b.refresh_from_db()
    assert (b.posicion_x, b.posicion_y) == (5, 5)


def test_guardar_acepta_ids_y_coordenadas_como_texto(cliente_autenticado, laboratorio, modulos):
    a, _ = modulos

    # Lejos de Mesa B (5, 5): sobre ella el guardado se rechaza por solapamiento.
    response = _post(cliente_autenticado, laboratorio, {'modulos': [{'id': str(a.id), 'x': '315', 'y': '225'}]})

    assert response.status_code == 200
    a.refresh_from_db()
    assert (a.posicion_x, a.posicion_y) == (315, 225)


def test_posiciones_guardadas_se_ven_en_el_editor(cliente_autenticado, laboratorio, modulos):
    a, _ = modulos
    _post(cliente_autenticado, laboratorio, {'modulos': [{'id': a.id, 'x': 222, 'y': 111}]})

    contenido = cliente_autenticado.get(_url(laboratorio)).content.decode()

    assert 'style="left: 222px; top: 111px;"' in contenido


def test_modulo_de_otro_laboratorio_400_y_no_guarda_nada(cliente_autenticado, laboratorio, modulos, otro_laboratorio_con_modulo):
    a, _ = modulos
    ajeno = otro_laboratorio_con_modulo

    response = _post(cliente_autenticado, laboratorio, {'modulos': [
        {'id': a.id, 'x': 50, 'y': 50},
        {'id': ajeno.id, 'x': 60, 'y': 60},
    ]})

    assert response.status_code == 400
    assert str(ajeno.id) in response.json()['error']
    a.refresh_from_db()
    ajeno.refresh_from_db()
    assert (a.posicion_x, a.posicion_y) == (0, 0)  # todo o nada
    assert (ajeno.posicion_x, ajeno.posicion_y) == (0, 0)


@pytest.mark.parametrize('cuerpo', [
    'no es json',
    '{}',
    '{"modulos": "x"}',
    '{"modulos": [{"id": 1}]}',
    '{"modulos": [{"id": 1, "x": "abc", "y": 2}]}',
    '[]',
])
def test_cuerpo_invalido_400(cliente_autenticado, laboratorio, modulos, cuerpo):
    response = _post(cliente_autenticado, laboratorio, cuerpo)

    assert response.status_code == 400
    assert response.json()['status'] == 'error'


def test_posiciones_negativas_400(cliente_autenticado, laboratorio, modulos):
    a, _ = modulos

    response = _post(cliente_autenticado, laboratorio, {'modulos': [{'id': a.id, 'x': -10, 'y': 5}]})

    assert response.status_code == 400
    a.refresh_from_db()
    assert a.posicion_x == 0


def test_get_no_permitido_405(cliente_autenticado, laboratorio):
    assert cliente_autenticado.get(_url_guardar(laboratorio)).status_code == 405


@pytest.mark.parametrize('rol', ['Laboratorio', 'Docente', 'Estudiante'])
def test_guardar_otros_roles_403_y_no_guarda(client, catalogos, laboratorio, modulos, rol):
    usuario = _usuario(rol, f'user_{rol.lower()}')
    laboratorio.encargados.add(usuario)
    client.force_login(usuario)
    a, _ = modulos

    response = _post(client, laboratorio, {'modulos': [{'id': a.id, 'x': 99, 'y': 99}]})

    assert response.status_code == 403
    a.refresh_from_db()
    assert (a.posicion_x, a.posicion_y) == (0, 0)


def test_guardar_anonimo_redirige_al_login(client, laboratorio, modulos):
    response = _post(client, laboratorio, {'modulos': []})

    assert response.status_code == 302
    assert response.url.startswith('/login/')


def test_guardar_laboratorio_inexistente_404(cliente_autenticado):
    response = cliente_autenticado.post('/laboratorio/999999/guardar-mapa/', '{"modulos": []}',
                                        content_type='application/json')

    assert response.status_code == 404


def test_csrf_token_del_editor_es_aceptado(usuario_admin, laboratorio, modulos):
    from django.test import Client
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(usuario_admin)
    a, _ = modulos
    cuerpo = json.dumps({'modulos': [{'id': a.id, 'x': 300, 'y': 300}]})  # libre (Mesa B está en 5, 5)

    sin_token = cliente.post(_url_guardar(laboratorio), cuerpo, content_type='application/json')
    token = cliente.get(_url(laboratorio)).context['csrf_token']
    con_token = cliente.post(_url_guardar(laboratorio), cuerpo, content_type='application/json',
                             HTTP_X_CSRFTOKEN=str(token))

    assert sin_token.status_code == 403
    assert con_token.status_code == 200


# ── Botón "Editar Mapa" en el mapa normal ────────────────────────────────────

def test_mapa_muestra_boton_editar_al_administrador(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/mapa/')

    assert response.status_code == 200
    contenido = response.content.decode()
    assert f'href="/laboratorio/{laboratorio.id}/editar-mapa/"' in contenido
    assert '✏️ Editar Mapa' in contenido
    etiqueta = contenido.split(f'href="/laboratorio/{laboratorio.id}/editar-mapa/"')[1].split('>')[0]
    assert 'target=' not in etiqueta  # misma pestaña


def test_mapa_no_muestra_boton_editar_al_encargado(client, catalogos, laboratorio):
    # El rol Laboratorio ve el mapa (y es_admin=True ahí), pero el editor le
    # daría 403: el botón no debe aparecer.
    encargado = _usuario('Laboratorio', 'encargado_mapa')
    laboratorio.encargados.add(encargado)
    client.force_login(encargado)

    response = client.get(f'/laboratorio/{laboratorio.id}/mapa/')

    assert response.status_code == 200
    assert response.context['es_admin'] is True
    assert response.context['puede_editar_mapa'] is False
    assert '/editar-mapa/' not in response.content.decode()


# ── Mapa normal: usa las posiciones guardadas ─────────────────────────────────

def _mapa(cliente, laboratorio):
    return cliente.get(f'/laboratorio/{laboratorio.id}/mapa/')


def _datos_por_id(response):
    return {item['modulo'].id: item for item in response.context['modulos_data']}


def test_mapa_sin_posiciones_guardadas_usa_zonas_como_antes(cliente_autenticado, laboratorio, modulos):
    Modulo.objects.filter(laboratorio=laboratorio).update(posicion_x=0, posicion_y=0)

    response = _mapa(cliente_autenticado, laboratorio)

    contenido = response.content.decode()
    assert response.context['usa_posiciones'] is False
    assert 'id="zona-izquierda"' in contenido
    assert 'id="mapa-posiciones"' not in contenido
    assert 'data-x=' not in contenido


def test_mapa_con_posiciones_dibuja_en_coordenadas_guardadas(cliente_autenticado, laboratorio, modulos):
    a, b = modulos
    Modulo.objects.filter(id=a.id).update(posicion_x=140, posicion_y=60)
    Modulo.objects.filter(id=b.id).update(posicion_x=400, posicion_y=250)

    response = _mapa(cliente_autenticado, laboratorio)

    contenido = response.content.decode()
    assert response.context['usa_posiciones'] is True
    assert 'id="mapa-posiciones"' in contenido
    assert 'id="zona-izquierda"' not in contenido
    datos = _datos_por_id(response)
    assert (datos[a.id]['x'], datos[a.id]['y']) == (140, 60)
    assert (datos[b.id]['x'], datos[b.id]['y']) == (400, 250)
    assert f'data-id="{a.id}"' in contenido
    assert 'data-x="140"' in contenido and 'data-y="60"' in contenido


def test_mapa_modulos_en_cero_toman_posicion_por_defecto(cliente_autenticado, laboratorio):
    from laboratorio.services.posiciones_mapa import calcular_posiciones
    m = [Modulo.objects.create(nombre=f'M{i}', capacidad=2, laboratorio=laboratorio) for i in range(4)]
    Modulo.objects.filter(id=m[2].id).update(posicion_x=500, posicion_y=300)

    datos = _datos_por_id(_mapa(cliente_autenticado, laboratorio))

    defecto = calcular_posiciones(4)
    assert (datos[m[2].id]['x'], datos[m[2].id]['y']) == (500, 300)
    for i in (0, 1, 3):
        assert (datos[m[i].id]['x'], datos[m[i].id]['y']) == defecto[i]


def test_mapa_x_cero_con_y_distinta_de_cero_es_posicion_valida(cliente_autenticado, laboratorio, modulos):
    a, _ = modulos
    Modulo.objects.filter(laboratorio=laboratorio).update(posicion_x=0, posicion_y=0)
    Modulo.objects.filter(id=a.id).update(posicion_x=0, posicion_y=250)

    response = _mapa(cliente_autenticado, laboratorio)

    assert response.context['usa_posiciones'] is True
    datos = _datos_por_id(response)
    assert (datos[a.id]['x'], datos[a.id]['y']) == (0, 250)


def test_mapa_lienzo_se_ajusta_a_los_modulos(cliente_autenticado, laboratorio, modulos):
    a, b = modulos
    Modulo.objects.filter(id=a.id).update(posicion_x=1200, posicion_y=20)
    Modulo.objects.filter(id=b.id).update(posicion_x=10, posicion_y=700)

    response = _mapa(cliente_autenticado, laboratorio)

    assert response.context['ancho_mapa'] == 1200 + 120 + 10
    assert response.context['alto_mapa'] == 700 + 80 + 10
    assert 'style="width: 1330px; height: 790px;"' in response.content.decode()


def test_cambios_del_editor_se_ven_en_el_mapa(cliente_autenticado, laboratorio, modulos):
    a, b = modulos
    _post(cliente_autenticado, laboratorio, {'modulos': [
        {'id': a.id, 'x': 333, 'y': 44},
        {'id': b.id, 'x': 55, 'y': 222},
    ]})

    datos = _datos_por_id(_mapa(cliente_autenticado, laboratorio))

    assert (datos[a.id]['x'], datos[a.id]['y']) == (333, 44)
    assert (datos[b.id]['x'], datos[b.id]['y']) == (55, 222)


def test_mapa_con_filtro_de_horario_tambien_usa_posiciones(cliente_autenticado, laboratorio, modulos):
    from datetime import date, timedelta
    a, _ = modulos
    Modulo.objects.filter(id=a.id).update(posicion_x=210, posicion_y=90)
    manana = (date.today() + timedelta(days=1)).isoformat()

    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/mapa/',
                                       {'fecha': manana, 'hora_inicio': '08:00', 'hora_fin': '10:00'})

    assert response.context['filtro_valido'] is True
    datos = _datos_por_id(response)
    assert (datos[a.id]['x'], datos[a.id]['y']) == (210, 90)
