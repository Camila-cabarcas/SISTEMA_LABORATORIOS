"""
Tests HTTP de las divisiones (salones) en el editor de mapa, el mapa, las
APIs de módulos de los formularios y las vistas que muestran módulos.
"""
import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from laboratorio.models import Division, Laboratorio, Modulo

pytestmark = pytest.mark.django_db


@pytest.fixture
def otro_lab(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 1')


@pytest.fixture
def salones(laboratorio):
    """Química con 2 divisiones y 3 módulos: A en Salón 1, B en Salón 2, C sin división."""
    s1 = Division.objects.create(laboratorio=laboratorio, nombre='Salón 1', x=0, y=0, ancho=300, alto=300)
    s2 = Division.objects.create(laboratorio=laboratorio, nombre='Salón 2', x=400, y=0, ancho=300, alto=300)
    a = Modulo.objects.create(nombre='Mesa A', capacidad=4, laboratorio=laboratorio, posicion_x=20, posicion_y=40, division=s1)
    b = Modulo.objects.create(nombre='Mesa B', capacidad=4, laboratorio=laboratorio, posicion_x=420, posicion_y=40, division=s2)
    c = Modulo.objects.create(nombre='Mesa C', capacidad=4, laboratorio=laboratorio, posicion_x=20, posicion_y=400)
    return {'s1': s1, 's2': s2, 'a': a, 'b': b, 'c': c}


def _guardar(cliente, laboratorio, cuerpo):
    return cliente.post(reverse('guardar_mapa', args=[laboratorio.id]),
                        data=json.dumps(cuerpo), content_type='application/json')


def _mapa(cliente, laboratorio, **params):
    return cliente.get(reverse('mapa_laboratorio', args=[laboratorio.id]), params)


def _ids(response):
    return [i['modulo'].id for i in response.context['modulos_data']]


# ── Editor ────────────────────────────────────────────────────────────────

class TestEditor:

    def test_muestra_divisiones_y_contador(self, cliente_autenticado, laboratorio, salones):
        resp = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id]))
        html = resp.content.decode()
        assert resp.context['divisiones'] == [salones['s1'], salones['s2']]
        assert html.count('class="division-item"') == 2 + 1  # 2 + la <template> de una nueva
        assert f'data-id="{salones["s1"].id}"' in html
        assert 'style="left: 400px; top: 0px; width: 300px; height: 300px;"' in html
        assert 'id="btn-agregar-division"' in html
        assert 'data-max-divisiones="4"' in html
        assert 'disabled' not in html.split('id="btn-agregar-division"')[1].split('>')[0]

    def test_boton_agregar_deshabilitado_con_cuatro(self, cliente_autenticado, laboratorio):
        for i in range(4):
            Division.objects.create(laboratorio=laboratorio, nombre=f'S{i}', x=i * 160, y=0, ancho=150, alto=150)
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        assert 'disabled' in html.split('id="btn-agregar-division"')[1].split('>')[0]

    def test_lienzo_tiene_tamano_fijo(self, cliente_autenticado, laboratorio):
        # El lienzo ya no crece con el contenido: mide lo mismo que valida el
        # servidor (posiciones_mapa.LIENZO_EDITOR_*).
        from laboratorio.services.posiciones_mapa import LIENZO_EDITOR_ALTO, LIENZO_EDITOR_ANCHO
        Division.objects.create(laboratorio=laboratorio, nombre='Abajo', x=0, y=600, ancho=300, alto=200)
        resp = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id]))
        assert (resp.context['lienzo_ancho'], resp.context['lienzo_alto']) == (LIENZO_EDITOR_ANCHO, LIENZO_EDITOR_ALTO)
        assert f'height: {LIENZO_EDITOR_ALTO}px;' in resp.content.decode()

    def test_divisiones_de_otro_laboratorio_no_aparecen(self, cliente_autenticado, laboratorio, otro_lab):
        Division.objects.create(laboratorio=otro_lab, nombre='Ajena', x=0, y=0)
        resp = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id]))
        assert resp.context['divisiones'] == []
        assert 'Ajena' not in resp.content.decode()

    def test_editor_carga_el_script(self, cliente_autenticado, laboratorio):
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        assert 'js/editar_mapa.js' in html
        assert 'id="plantilla-division"' in html


# ── Guardado (endpoint) ───────────────────────────────────────────────────

class TestGuardarEndpoint:

    def test_crea_divisiones_y_asigna_modulos(self, cliente_autenticado, laboratorio):
        a = Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio)
        resp = _guardar(cliente_autenticado, laboratorio, {
            'modulos': [{'id': a.id, 'x': 50, 'y': 50}],
            'divisiones': [{'id': None, 'nombre': 'Salón 1', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 300}],
        })
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'actualizados': 1, 'divisiones': 1}
        a.refresh_from_db()
        assert a.division.nombre == 'Salón 1'

    def test_quinta_division_400_sin_guardar(self, cliente_autenticado, laboratorio):
        a = Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio)
        cinco = [{'nombre': f'S{i}', 'x': i * 160, 'y': 0, 'ancho': 150, 'alto': 150} for i in range(5)]
        resp = _guardar(cliente_autenticado, laboratorio, {'modulos': [{'id': a.id, 'x': 9, 'y': 9}], 'divisiones': cinco})
        assert resp.status_code == 400
        assert 'máximo 4' in resp.json()['error']
        a.refresh_from_db()
        assert (a.posicion_x, a.posicion_y) == (0, 0)
        assert not Division.objects.exists()

    def test_eliminar_division_no_borra_modulos(self, cliente_autenticado, laboratorio, salones):
        resp = _guardar(cliente_autenticado, laboratorio, {
            'modulos': [],
            'divisiones': [{'id': salones['s2'].id, 'nombre': 'Salón 2', 'x': 400, 'y': 0, 'ancho': 300, 'alto': 300}],
        })
        assert resp.status_code == 200
        assert not Division.objects.filter(id=salones['s1'].id).exists()
        assert Modulo.objects.filter(laboratorio=laboratorio).count() == 3
        salones['a'].refresh_from_db()
        salones['b'].refresh_from_db()
        assert salones['a'].division is None
        assert salones['b'].division == salones['s2']

    def test_solo_administrador(self, client, usuario_laboratorista, laboratorio):
        client.force_login(usuario_laboratorista)
        resp = _guardar(client, laboratorio, {'modulos': [], 'divisiones': [
            {'nombre': 'S', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
        ]})
        assert resp.status_code == 403
        assert not Division.objects.exists()

    def test_json_invalido_400(self, cliente_autenticado, laboratorio):
        resp = cliente_autenticado.post(reverse('guardar_mapa', args=[laboratorio.id]),
                                        data='{no json', content_type='application/json')
        assert resp.status_code == 400


# ── Mapa ──────────────────────────────────────────────────────────────────

class TestMapa:

    def test_sin_divisiones_se_ve_igual_que_antes(self, cliente_autenticado, laboratorio):
        Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio)
        resp = _mapa(cliente_autenticado, laboratorio)
        html = resp.content.decode()
        assert resp.context['divisiones'] == []
        assert resp.context['usa_posiciones'] is False  # reparto por zonas, como siempre
        assert 'class="division-zona' not in html  # ninguna zona dibujada
        assert 'filtro-division' not in html
        assert 'id="zona-izquierda"' in html

    def test_dibuja_las_divisiones(self, cliente_autenticado, laboratorio, salones):
        resp = _mapa(cliente_autenticado, laboratorio)
        html = resp.content.decode()
        assert resp.context['usa_posiciones'] is True
        assert html.count('class="division-zona ') == 2
        assert 'style="left: 400px; top: 0px; width: 300px; height: 300px;"' in html
        assert '>Salón 1</span>' in html

    def test_divisiones_fuerzan_modo_posiciones_aunque_los_modulos_no_tengan(self, cliente_autenticado, laboratorio):
        Division.objects.create(laboratorio=laboratorio, nombre='S', x=0, y=0)
        Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio)  # (0, 0)
        resp = _mapa(cliente_autenticado, laboratorio)
        assert resp.context['usa_posiciones'] is True
        assert 'id="mapa-posiciones"' in resp.content.decode()

    def test_cada_modulo_lleva_su_division(self, cliente_autenticado, laboratorio, salones):
        html = _mapa(cliente_autenticado, laboratorio).content.decode()
        assert 'data-division="Salón 1"' in html
        assert 'data-division="Salón 2"' in html
        assert 'data-division=""' in html  # Mesa C
        assert 'id="modal-division"' in html

    def test_filtro_por_division(self, cliente_autenticado, laboratorio, salones):
        assert _ids(_mapa(cliente_autenticado, laboratorio, division=salones['s1'].id)) == [salones['a'].id]
        assert _ids(_mapa(cliente_autenticado, laboratorio, division='sin')) == [salones['c'].id]
        assert len(_ids(_mapa(cliente_autenticado, laboratorio))) == 3

    def test_filtro_atenua_las_otras_divisiones(self, cliente_autenticado, laboratorio, salones):
        html = _mapa(cliente_autenticado, laboratorio, division=salones['s1'].id).content.decode()
        assert html.count('division-atenuada') == 1 + 1  # la zona de Salón 2 + la regla CSS

    def test_filtro_no_mueve_los_modulos(self, cliente_autenticado, laboratorio, salones):
        todos = {i['modulo'].id: (i['x'], i['y']) for i in _mapa(cliente_autenticado, laboratorio).context['modulos_data']}
        filtrado = _mapa(cliente_autenticado, laboratorio, division='sin').context['modulos_data']
        assert [(i['x'], i['y']) for i in filtrado] == [todos[salones['c'].id]]

    def test_filtro_con_division_de_otro_lab_se_ignora(self, cliente_autenticado, laboratorio, salones, otro_lab):
        ajena = Division.objects.create(laboratorio=otro_lab, nombre='Ajena', x=0, y=0)
        resp = _mapa(cliente_autenticado, laboratorio, division=ajena.id)
        assert resp.context['division_filtro'] == ''
        assert len(_ids(resp)) == 3

    def test_filtro_sin_resultados_muestra_aviso(self, cliente_autenticado, laboratorio):
        Division.objects.create(laboratorio=laboratorio, nombre='Vacía', x=0, y=0)
        Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio, posicion_x=500, posicion_y=500)
        vacia = Division.objects.get(nombre='Vacía')
        html = _mapa(cliente_autenticado, laboratorio, division=vacia.id).content.decode()
        assert 'id="filtro-division-vacio"' in html
        assert 'no tiene módulos registrados' not in html

    def test_divisiones_de_otro_laboratorio_no_aparecen(self, cliente_autenticado, laboratorio, salones, otro_lab):
        Division.objects.create(laboratorio=otro_lab, nombre='Ajena', x=0, y=0)
        resp = _mapa(cliente_autenticado, laboratorio)
        assert [d.nombre for d in resp.context['divisiones']] == ['Salón 1', 'Salón 2']
        assert 'Ajena' not in resp.content.decode()


# ── APIs de los selectores de módulos ─────────────────────────────────────

class TestApis:

    def test_api_interna(self, cliente_autenticado, laboratorio, salones):
        data = cliente_autenticado.get(reverse('modulos_disponibles_api', args=[laboratorio.id])).json()
        por_nombre = {m['nombre']: m for m in data['modulos']}
        assert por_nombre['Mesa A']['division'] == {'id': salones['s1'].id, 'nombre': 'Salón 1'}
        assert por_nombre['Mesa C']['division'] is None
        assert data['divisiones'] == [
            {'id': salones['s1'].id, 'nombre': 'Salón 1'},
            {'id': salones['s2'].id, 'nombre': 'Salón 2'},
        ]

    def test_api_publica(self, client, laboratorio, salones):
        data = client.get(reverse('modulos_disponibles_publica_api', args=[laboratorio.id])).json()
        assert {m['nombre']: m['division'] and m['division']['nombre'] for m in data['modulos']} == {
            'Mesa A': 'Salón 1', 'Mesa B': 'Salón 2', 'Mesa C': None,
        }
        assert len(data['divisiones']) == 2

    def test_lab_sin_divisiones(self, client, laboratorio):
        Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio)
        data = client.get(reverse('modulos_disponibles_publica_api', args=[laboratorio.id])).json()
        assert data['divisiones'] == []
        assert data['modulos'][0]['division'] is None

    def test_divisiones_de_otro_laboratorio_no_aparecen(self, client, laboratorio, salones, otro_lab):
        Division.objects.create(laboratorio=otro_lab, nombre='Ajena', x=0, y=0)
        data = client.get(reverse('modulos_disponibles_publica_api', args=[laboratorio.id])).json()
        assert 'Ajena' not in [d['nombre'] for d in data['divisiones']]

    @pytest.mark.parametrize('url, sufijo', [
        ('/reservas/crear/', ''),
    ])
    def test_selector_interno_tiene_filtro(self, cliente_autenticado, url, sufijo):
        html = cliente_autenticado.get(url).content.decode()
        assert f'id="filtro-division{sufijo}"' in html
        assert 'js/filtro_division_modulos.js' in html

    @pytest.mark.parametrize('nombre_url, sufijo', [
        ('solicitud_estudiante', '-est'),
        ('solicitud_profesor', '-prof'),
    ])
    def test_selectores_publicos_tienen_filtro(self, client, catalogos, nombre_url, sufijo):
        html = client.get(reverse(nombre_url)).content.decode()
        assert f'id="filtro-division{sufijo}"' in html
        assert 'js/filtro_division_modulos.js' in html


# ── Otras vistas que muestran módulos ─────────────────────────────────────

class TestOtrasVistas:

    def test_historial_del_modulo_muestra_division(self, cliente_autenticado, laboratorio, salones):
        url = reverse('historial_modulo', args=[laboratorio.id, salones['a'].id])
        assert 'División: Salón 1' in cliente_autenticado.get(url).content.decode()

    def test_detalle_de_reserva_muestra_division(self, cliente_autenticado, laboratorio, salones, catalogos):
        from reservas.models import EstadoReserva, Reserva
        from solicitudes.models import SolicitudReserva

        reserva = Reserva.objects.create(fecha_reserva=timezone.now() + timedelta(days=1),
                                         estado=EstadoReserva.objects.get(nombre='Aprobada'))
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', nombre='Ana', cedula='123', laboratorio=laboratorio,
            fecha_reserva=reserva.fecha_reserva, reserva=reserva, necesita_modulo=True,
        )
        solicitud.modulos_asignados.set([salones['a']])

        html = cliente_autenticado.get(f'/reservas/{reserva.id}/').content.decode()
        assert 'Mesa A · Salón 1' in html

    def test_admin_lista_y_filtra_por_division(self, client, laboratorio, salones):
        from users.models import Usuario
        admin = Usuario.objects.create_superuser('root', 'root@x.co', 'clave12345', codigo='ROOT')
        client.force_login(admin)
        resp = client.get('/admin/laboratorio/modulo/', {'division__id__exact': salones['s1'].id})
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'Mesa A' in html and 'Mesa B' not in html
        assert client.get('/admin/laboratorio/division/').status_code == 200
