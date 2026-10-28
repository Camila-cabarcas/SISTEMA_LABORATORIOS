"""
Tests del editor de mapa sin solapamientos: tamaño único de módulo y de
lienzo (laboratorio.services.posiciones_mapa), validación del guardado
(choques, fuera del lienzo, categoría), panel del editor y el comando de solo
lectura detectar_solapamientos_modulos.
"""
import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from laboratorio.models import CategoriaModulo, Division, Laboratorio, Modulo
from laboratorio.services import posiciones_mapa as pm
from laboratorio.services.divisiones import MapaInvalido, guardar_mapa

pytestmark = pytest.mark.django_db

W, H = pm.ANCHO_MODULO, pm.ALTO_MODULO


def _modulo(lab, nombre, x=0, y=0, **extra):
    return Modulo.objects.create(nombre=nombre, capacidad=1, laboratorio=lab, posicion_x=x, posicion_y=y, **extra)


def _guardar(cliente, lab, cuerpo):
    return cliente.post(reverse('guardar_mapa', args=[lab.id]), data=json.dumps(cuerpo), content_type='application/json')


# ── Geometría compartida ──────────────────────────────────────────────────

class TestGeometria:

    def test_tocarse_por_el_borde_no_es_solapar(self):
        assert not pm.se_solapan(pm.rect_modulo(0, 0), pm.rect_modulo(W, 0))
        assert not pm.se_solapan(pm.rect_modulo(0, 0), pm.rect_modulo(0, H))
        assert pm.se_solapan(pm.rect_modulo(0, 0), pm.rect_modulo(W - 1, H - 1))

    def test_modulo_en_lienzo(self):
        assert pm.modulo_en_lienzo(0, 0)
        assert pm.modulo_en_lienzo(pm.LIENZO_EDITOR_ANCHO - W, pm.LIENZO_EDITOR_ALTO - H)
        assert not pm.modulo_en_lienzo(pm.LIENZO_EDITOR_ANCHO - W + 1, 0)
        assert not pm.modulo_en_lienzo(0, pm.LIENZO_EDITOR_ALTO - H + 1)

    def test_pares_solapados_ignora_los_sin_posicion(self):
        a, b, c = object(), object(), object()
        assert pm.pares_solapados([(a, 0, 0), (b, 0, 0), (c, 300, 300)]) == []
        assert pm.pares_solapados([(a, 10, 10), (b, 20, 20), (c, 300, 300)]) == [(a, b)]

    def test_minimos_de_division_derivan_del_tamano_del_modulo(self):
        assert Division.ANCHO_MINIMO == W + 20
        assert Division.ALTO_MINIMO == H + 20


# ── Guardado ──────────────────────────────────────────────────────────────

class TestGuardadoSinSolapamiento:

    def test_dos_modulos_en_la_misma_posicion_se_rechazan(self, cliente_autenticado, laboratorio):
        a, b = _modulo(laboratorio, 'Mesa A'), _modulo(laboratorio, 'Mesa B', x=500, y=500)
        resp = _guardar(cliente_autenticado, laboratorio, {'modulos': [
            {'id': a.id, 'x': 100, 'y': 100}, {'id': b.id, 'x': 100, 'y': 100},
        ]})
        assert resp.status_code == 400
        assert resp.json()['error'] == 'Hay módulos que se solapan: "Mesa A" y "Mesa B". Muévelos antes de guardar.'
        a.refresh_from_db()
        b.refresh_from_db()
        assert (a.posicion_x, a.posicion_y, b.posicion_x, b.posicion_y) == (0, 0, 500, 500)  # todo o nada

    def test_solapamiento_parcial_tambien_se_rechaza(self, laboratorio):
        a, b = _modulo(laboratorio, 'A'), _modulo(laboratorio, 'B')
        with pytest.raises(MapaInvalido, match='"A" y "B"'):
            guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 100, 'y': 100},
                                                    {'id': b.id, 'x': 100 + W - 1, 'y': 100}]})

    def test_tocarse_por_el_borde_se_acepta(self, laboratorio):
        a, b = _modulo(laboratorio, 'A'), _modulo(laboratorio, 'B')
        guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 100, 'y': 100},
                                                {'id': b.id, 'x': 100 + W, 'y': 100}]})
        b.refresh_from_db()
        assert b.posicion_x == 100 + W

    def test_choca_con_un_modulo_no_enviado(self, laboratorio):
        a = _modulo(laboratorio, 'A')
        _modulo(laboratorio, 'Fijo', x=300, y=300)
        with pytest.raises(MapaInvalido, match='"A" y "Fijo"'):
            guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 310, 'y': 310}]})

    def test_modulos_sin_posicion_no_cuentan(self, laboratorio):
        # Varios en (0, 0) ("sin posición") no bloquean el guardado.
        _modulo(laboratorio, 'A')
        _modulo(laboratorio, 'B')
        c = _modulo(laboratorio, 'C')
        guardar_mapa(laboratorio, {'modulos': [{'id': c.id, 'x': 400, 'y': 400}]})

    def test_mensaje_lista_varios_pares(self, laboratorio):
        ms = [_modulo(laboratorio, f'M{i}') for i in range(8)]
        with pytest.raises(MapaInvalido) as e:
            guardar_mapa(laboratorio, {'modulos': [{'id': m.id, 'x': 50, 'y': 50} for m in ms]})
        assert '"M0" y "M1"' in str(e.value)
        assert 'par(es) más' in str(e.value)

    @pytest.mark.parametrize('x, y', [
        (pm.LIENZO_EDITOR_ANCHO - W + 1, 10),
        (10, pm.LIENZO_EDITOR_ALTO - H + 1),
        (5000, 5000),
    ])
    def test_modulo_fuera_del_lienzo_se_rechaza(self, cliente_autenticado, laboratorio, x, y):
        a = _modulo(laboratorio, 'Mesa A', x=10, y=10)
        resp = _guardar(cliente_autenticado, laboratorio, {'modulos': [{'id': a.id, 'x': x, 'y': y}]})
        assert resp.status_code == 400
        assert 'fuera del lienzo' in resp.json()['error']
        assert '"Mesa A"' in resp.json()['error']
        a.refresh_from_db()
        assert (a.posicion_x, a.posicion_y) == (10, 10)

    def test_borde_del_lienzo_se_acepta(self, laboratorio):
        a = _modulo(laboratorio, 'A')
        guardar_mapa(laboratorio, {'modulos': [
            {'id': a.id, 'x': pm.LIENZO_EDITOR_ANCHO - W, 'y': pm.LIENZO_EDITOR_ALTO - H},
        ]})

    def test_solapamiento_no_escribe_divisiones(self, laboratorio):
        a, b = _modulo(laboratorio, 'A'), _modulo(laboratorio, 'B')
        vieja = Division.objects.create(laboratorio=laboratorio, nombre='Vieja', x=600, y=0)
        with pytest.raises(MapaInvalido):
            guardar_mapa(laboratorio, {
                'modulos': [{'id': a.id, 'x': 50, 'y': 50}, {'id': b.id, 'x': 60, 'y': 60}],
                'divisiones': [{'nombre': 'Nueva', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200}],
            })
        assert list(laboratorio.divisiones.all()) == [vieja]

    def test_divisiones_solapadas_se_siguen_rechazando(self, laboratorio):
        with pytest.raises(MapaInvalido, match='superponen'):
            guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
                {'nombre': 'A', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
                {'nombre': 'B', 'x': 100, 'y': 100, 'ancho': 300, 'alto': 200},
            ]})

    def test_division_fuera_del_lienzo_se_rechaza(self, laboratorio):
        with pytest.raises(MapaInvalido, match='lienzo'):
            guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
                {'nombre': 'A', 'x': pm.LIENZO_EDITOR_ANCHO - 100, 'y': 0, 'ancho': 300, 'alto': 200},
            ]})

    def test_mover_una_division_no_altera_sus_modulos(self, laboratorio):
        d = Division.objects.create(laboratorio=laboratorio, nombre='Salón', x=0, y=0, ancho=400, alto=300)
        a = _modulo(laboratorio, 'A', x=20, y=20, division=d)
        b = _modulo(laboratorio, 'B', x=200, y=100, division=d)

        guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
            {'id': d.id, 'nombre': 'Salón', 'x': 600, 'y': 300, 'ancho': 400, 'alto': 300},
        ]})

        for m, esperado in ((a, (20, 20)), (b, (200, 100))):
            m.refresh_from_db()
            assert (m.posicion_x, m.posicion_y) == esperado
        d.refresh_from_db()
        assert (d.x, d.y) == (600, 300)


# ── Categoría desde el editor ─────────────────────────────────────────────

@pytest.fixture
def cats(db):
    return {
        'pc': CategoriaModulo.objects.create(nombre='Equipo PC', color='#20c997', forma='computador'),
        'vieja': CategoriaModulo.objects.create(nombre='Vieja', color='#111111', forma='rombo', activo=False),
    }


class TestCategoriaDesdeElEditor:

    def test_cambiar_la_categoria_se_guarda(self, cliente_autenticado, laboratorio, cats):
        a = _modulo(laboratorio, 'A', x=10, y=10)
        resp = _guardar(cliente_autenticado, laboratorio, {'modulos': [
            {'id': a.id, 'x': 10, 'y': 10, 'categoria': cats['pc'].id},
        ]})
        assert resp.status_code == 200
        a.refresh_from_db()
        assert a.categoria == cats['pc']

    def test_quitar_la_categoria(self, laboratorio, cats):
        a = _modulo(laboratorio, 'A', categoria=cats['pc'])
        guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 0, 'y': 0, 'categoria': None}]})
        a.refresh_from_db()
        assert a.categoria is None

    def test_sin_clave_categoria_no_la_toca(self, laboratorio, cats):
        a = _modulo(laboratorio, 'A', categoria=cats['pc'])
        guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 300, 'y': 300}]})
        a.refresh_from_db()
        assert a.categoria == cats['pc']

    def test_categoria_inexistente_400_sin_guardar(self, cliente_autenticado, laboratorio):
        a = _modulo(laboratorio, 'A', x=10, y=10)
        resp = _guardar(cliente_autenticado, laboratorio, {'modulos': [
            {'id': a.id, 'x': 300, 'y': 300, 'categoria': 999999},
        ]})
        assert resp.status_code == 400
        a.refresh_from_db()
        assert (a.posicion_x, a.categoria) == (10, None)

    def test_categoria_desactivada_no_se_puede_asignar(self, laboratorio, cats):
        a = _modulo(laboratorio, 'A')
        with pytest.raises(MapaInvalido, match='desactivada'):
            guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 0, 'y': 0, 'categoria': cats['vieja'].id}]})

    def test_conserva_su_categoria_desactivada(self, laboratorio, cats):
        a = _modulo(laboratorio, 'A', categoria=cats['vieja'])
        guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 300, 'y': 300, 'categoria': cats['vieja'].id}]})
        a.refresh_from_db()
        assert a.categoria == cats['vieja']


# ── Página del editor ─────────────────────────────────────────────────────

class TestPaginaEditor:

    def _html(self, cliente, lab):
        return cliente.get(reverse('editar_mapa', args=[lab.id]))

    def test_tamanos_vienen_del_servidor(self, cliente_autenticado, laboratorio):
        _modulo(laboratorio, 'A', x=10, y=10)
        html = self._html(cliente_autenticado, laboratorio).content.decode()
        assert f'data-ancho-modulo="{W}"' in html and f'data-alto-modulo="{H}"' in html
        assert f'width: {W}px;' in html and f'height: {H}px;' in html
        assert f'width: {pm.LIENZO_EDITOR_ANCHO}px;' in html and f'height: {pm.LIENZO_EDITOR_ALTO}px;' in html
        assert f'data-division-ancho-min="{Division.ANCHO_MINIMO}"' in html

    def test_js_no_duplica_el_tamano(self):
        js = open('static/js/editar_mapa.js', encoding='utf-8').read()
        assert '120' not in js and '80' not in js and '140' not in js

    def test_panel_con_categorias_activas_y_las_en_uso(self, cliente_autenticado, laboratorio, cats):
        _modulo(laboratorio, 'A', x=10, y=10, categoria=cats['vieja'])
        resp = self._html(cliente_autenticado, laboratorio)
        html = resp.content.decode()
        assert 'id="panel-modulo"' in html
        assert 'id="panel-categoria"' in html and 'id="panel-x"' in html and 'id="panel-y"' in html
        ofrecidas = set(resp.context['categorias_editor'])
        assert cats['pc'] in ofrecidas and cats['vieja'] in ofrecidas  # vieja: la usa un módulo
        assert f'value="{cats["pc"].id}" data-color="#20c997" data-forma="computador"' in html

    def test_categoria_desactivada_sin_uso_no_se_ofrece(self, cliente_autenticado, laboratorio, cats):
        resp = self._html(cliente_autenticado, laboratorio)
        assert cats['vieja'] not in set(resp.context['categorias_editor'])

    def test_modulos_llevan_nombre_y_categoria(self, cliente_autenticado, laboratorio, cats):
        m = _modulo(laboratorio, 'Mesa A', x=10, y=10, categoria=cats['pc'])
        html = self._html(cliente_autenticado, laboratorio).content.decode()
        assert f'data-id="{m.id}"' in html
        assert 'data-nombre="Mesa A"' in html
        assert f'data-categoria-id="{cats["pc"].id}"' in html

    def test_mapa_usa_el_mismo_tamano(self, cliente_autenticado, laboratorio):
        _modulo(laboratorio, 'A', x=10, y=10)
        html = cliente_autenticado.get(reverse('mapa_laboratorio', args=[laboratorio.id])).content.decode()
        assert f'width: {W}px; min-height: {H}px;' in html


# ── Comando detectar_solapamientos_modulos ────────────────────────────────

class TestComandoDetectar:

    def _correr(self, *args):
        salida = StringIO()
        call_command('detectar_solapamientos_modulos', *args, stdout=salida)
        return salida.getvalue()

    def _estado(self):
        return list(Modulo.objects.order_by('id').values_list('id', 'posicion_x', 'posicion_y', 'division_id', 'categoria_id'))

    def test_encuentra_un_par_y_no_modifica_nada(self, laboratorio):
        a = _modulo(laboratorio, 'Mesa A', x=100, y=100)
        b = _modulo(laboratorio, 'Mesa B', x=150, y=120)
        _modulo(laboratorio, 'Libre', x=600, y=600)
        antes = self._estado()

        salida = self._correr()

        assert f'"Mesa A" (id {a.id}, 100,100)' in salida
        assert f'"Mesa B" (id {b.id}, 150,120)' in salida
        assert '1 par(es)' in salida
        assert 'Libre' not in salida
        assert self._estado() == antes

    def test_sin_solapamientos(self, laboratorio):
        _modulo(laboratorio, 'A', x=0, y=0)
        _modulo(laboratorio, 'B', x=0, y=0)  # sin posición: no cuentan
        _modulo(laboratorio, 'C', x=300, y=300)
        assert 'No hay módulos solapados' in self._correr()

    def test_filtra_por_laboratorio(self, laboratorio):
        otro = Laboratorio.objects.create(nombre='Física', ubicacion='B1')
        _modulo(otro, 'X1', x=10, y=10)
        _modulo(otro, 'X2', x=20, y=20)
        _modulo(laboratorio, 'Q1', x=10, y=10)

        assert 'No hay módulos solapados' in self._correr('--laboratorio', str(laboratorio.id))
        assert '"X1"' in self._correr('--laboratorio', str(otro.id))

    def test_no_compara_modulos_de_laboratorios_distintos(self, laboratorio):
        otro = Laboratorio.objects.create(nombre='Física', ubicacion='B1')
        _modulo(laboratorio, 'Q1', x=10, y=10)
        _modulo(otro, 'X1', x=10, y=10)  # misma posición, otro laboratorio
        assert 'No hay módulos solapados' in self._correr()

    def test_laboratorio_inexistente(self):
        with pytest.raises(CommandError, match='No existe'):
            self._correr('--laboratorio', '999999')
