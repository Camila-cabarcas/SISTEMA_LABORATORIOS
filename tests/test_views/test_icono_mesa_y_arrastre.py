"""
Tests del ícono de mesa (forma 'mesa' de CategoriaModulo) y de las reglas de
arrastre del editor de mapa (static/js/editor_mapa_reglas.js, ejecutadas en
Node): pasar por encima de otro módulo está permitido, pero al soltar sobre
otro vuelve a la posición inicial. El servidor sigue rechazando
solapamientos como respaldo.
"""
import importlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.template.loader import render_to_string
from django.urls import reverse

from laboratorio.models import CategoriaModulo, Modulo
from laboratorio.services import posiciones_mapa as pm

pytestmark = pytest.mark.django_db

RAIZ = Path(__file__).resolve().parents[2]
migracion_mesa = importlib.import_module('laboratorio.migrations.0019_categoria_forma_mesa')


def _figura(forma, color='#0d6efd'):
    return render_to_string('laboratorio/partials/figura_categoria.html', {'forma': forma, 'color': color})


@pytest.fixture
def cats(db):
    # La migración ya creó Mesa/Computador/Maquinaria; se usan esas.
    return {c.nombre: c for c in CategoriaModulo.objects.filter(nombre__in=['Mesa', 'Computador', 'Maquinaria'])}


# ── Ícono de mesa ─────────────────────────────────────────────────────────

class TestFiguras:

    def test_mesa_renderiza_icono_de_mesa(self):
        html = _figura('mesa')
        assert 'forma-mesa' in html
        assert '<svg class="modulo-figura-icono icono-mesa"' in html
        assert html.count('<rect') == 5  # canto del tablero + 4 patas
        assert 'fill="currentColor"' in html  # toma el color de la categoría
        assert 'style="--cat-color: #0d6efd;"' in html

    def test_computador_y_maquinaria_mantienen_su_figura(self):
        assert 'fa-desktop' in _figura('computador') and 'icono-mesa' not in _figura('computador')
        assert 'fa-gears' in _figura('maquinaria') and 'icono-mesa' not in _figura('maquinaria')

    @pytest.mark.parametrize('forma', ['cuadrado', 'circulo', 'rombo', 'triangulo'])
    def test_formas_sin_icono(self, forma):
        html = _figura(forma)
        assert '<svg' not in html and '<i ' not in html

    def test_icono_js_y_plantilla_son_el_mismo_dibujo(self):
        js = (RAIZ / 'static/js/modulo_figura.js').read_text(encoding='utf-8')
        plantilla = (RAIZ / 'templates/laboratorio/partials/icono_categoria.html').read_text(encoding='utf-8')
        assert "d: 'M6 3h20l4 6H2z'" in js and 'd="M6 3h20l4 6H2z"' in plantilla
        for medida in ('x: 2, y: 9, width: 28', 'x: 3, y: 11, width: 2.6', 'x: 26.4, y: 11',
                       'x: 8.5, y: 11, width: 2', 'x: 21.5, y: 11'):
            assert medida in js
        for medida in ('x="2" y="9" width="28"', 'x="3" y="11" width="2.6"', 'x="26.4" y="11"',
                       'x="8.5" y="11" width="2"', 'x="21.5" y="11"'):
            assert medida in plantilla

    def test_editor_no_tiene_copia_propia_de_los_iconos(self):
        js = (RAIZ / 'static/js/editar_mapa.js').read_text(encoding='utf-8')
        assert 'fa-desktop' not in js and 'fa-gears' not in js
        assert 'ModuloFigura.icono' in js


class TestMigracionMesa:

    def _correr(self):
        migracion_mesa.mesa_a_forma_mesa(django_apps, None)

    def test_la_categoria_mesa_usa_la_forma_mesa(self, cats):
        # Después de las migraciones del test DB.
        assert cats['Mesa'].forma == 'mesa'
        assert (cats['Mesa'].color, cats['Computador'].forma, cats['Maquinaria'].forma) == (
            '#0d6efd', 'computador', 'maquinaria')

    def test_solo_cambia_mesa_si_sigue_en_cuadrado(self, cats):
        mesa = cats['Mesa']
        mesa.forma = 'rombo'  # un Administrador la cambió
        mesa.save()
        otra = CategoriaModulo.objects.create(nombre='Banco', color='#123456', forma='cuadrado')

        self._correr()

        mesa.refresh_from_db()
        otra.refresh_from_db()
        assert mesa.forma == 'rombo'
        assert otra.forma == 'cuadrado'

    def test_idempotente(self, cats):
        mesa = cats['Mesa']
        mesa.forma = 'cuadrado'
        mesa.save()
        self._correr()
        self._correr()
        mesa.refresh_from_db()
        assert mesa.forma == 'mesa'


class TestDondeApareceElIcono:

    def test_editor(self, cliente_autenticado, laboratorio, cats):
        Modulo.objects.create(nombre='Mesa 1', capacidad=4, laboratorio=laboratorio, categoria=cats['Mesa'],
                              posicion_x=10, posicion_y=10)
        Modulo.objects.create(nombre='Gris', capacidad=4, laboratorio=laboratorio, posicion_x=300, posicion_y=10)
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        assert 'modulo-figura forma-mesa" style="--cat-color: #0d6efd;"' in html
        assert 'icono-mesa' in html
        # Sin categoría: sigue gris, rectángulo sin ícono.
        bloque_gris = html.split('data-nombre="Gris"')[1].split('</div>')[0]
        assert 'forma-cuadrado" style="--cat-color: #6c757d;"' in bloque_gris
        assert '<svg' not in bloque_gris
        assert 'js/modulo_figura.js' in html and 'js/editor_mapa_reglas.js' in html

    def test_leyenda_del_mapa(self, cliente_autenticado, laboratorio, cats):
        Modulo.objects.create(nombre='Mesa 1', capacidad=4, laboratorio=laboratorio, categoria=cats['Mesa'])
        html = cliente_autenticado.get(reverse('mapa_laboratorio', args=[laboratorio.id])).content.decode()
        leyenda = html.split('id="leyenda-categorias"')[1].split('</div>')[0]
        assert 'icono-mesa' in leyenda
        assert 'data-categoria-forma="mesa"' in html  # el JS del mapa dibuja el ícono con esto

    def test_gestion_de_categorias(self, cliente_autenticado, cats):
        html = cliente_autenticado.get('/laboratorio/categorias/').content.decode()
        assert 'icono-mesa' in html
        assert 'Mesa (tablero y patas)' in html

    def test_api_de_los_formularios_de_reserva(self, client, laboratorio, cats):
        Modulo.objects.create(nombre='Mesa 1', capacidad=4, laboratorio=laboratorio, categoria=cats['Mesa'])
        data = client.get(reverse('modulos_disponibles_publica_api', args=[laboratorio.id])).json()
        assert data['modulos'][0]['categoria']['forma'] == 'mesa'


# ── Reglas de arrastre (Node) ─────────────────────────────────────────────

NODE = shutil.which('node')


def _reglas(script):
    """Ejecuta `script` en Node con `R` = editor_mapa_reglas.js y devuelve su
    salida JSON."""
    if not NODE:
        pytest.skip('Node.js no está disponible')
    ruta = (RAIZ / 'static/js/editor_mapa_reglas.js').as_posix()
    codigo = f"const R = require({json.dumps(ruta)});\n{script}"
    resultado = subprocess.run([NODE, '-e', codigo], capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


ESCENARIO = f"""
const TAM = {{w: {pm.ANCHO_MODULO}, h: {pm.ALTO_MODULO}}};
const LIENZO = {{w: {pm.LIENZO_EDITOR_ANCHO}, h: {pm.LIENZO_EDITOR_ALTO}}};
const otros = [{{x: 300, y: 300}}];   // el otro módulo del laboratorio
const valida = (x, y) => R.posicionValida(x, y, TAM, LIENZO, otros, []);
"""


class TestReglasDeArrastre:

    def test_soltar_sobre_otro_modulo_vuelve_a_la_posicion_inicial(self):
        r = _reglas(ESCENARIO + """
            const inicio = {x: 50, y: 50};
            const final = R.posicionAlSoltar(inicio, {x: 310, y: 310}, valida);
            console.log(JSON.stringify({final, esInicio: final === inicio}));
        """)
        assert r == {'final': {'x': 50, 'y': 50}, 'esInicio': True}

    def test_soltar_en_espacio_libre_queda_en_la_nueva_posicion(self):
        r = _reglas(ESCENARIO + """
            const final = R.posicionAlSoltar({x: 50, y: 50}, {x: 600, y: 500}, valida);
            console.log(JSON.stringify(final));
        """)
        assert r == {'x': 600, 'y': 500}

    def test_pasar_por_encima_de_otro_durante_el_arrastre_no_da_error(self):
        # Recorrido que atraviesa el otro módulo y termina libre.
        r = _reglas(ESCENARIO + """
            const recorrido = [];
            for (let x = 50; x <= 700; x += 25) recorrido.push({x, y: 310});
            const estados = recorrido.map(p => valida(p.x, p.y));
            const final = R.posicionAlSoltar({x: 50, y: 50}, recorrido[recorrido.length - 1], valida);
            console.log(JSON.stringify({pasoEncima: estados.includes(false), final}));
        """)
        assert r['pasoEncima'] is True  # en algún punto estuvo encima (rojo)
        assert r['final'] == {'x': 700, 'y': 310}

    def test_tocarse_por_el_borde_es_valido(self):
        r = _reglas(ESCENARIO + f"""
            console.log(JSON.stringify([valida(300 - TAM.w, 300), valida(300 - TAM.w + 1, 300)]));
        """)
        assert r == [True, False]

    def test_no_puede_salir_del_lienzo(self):
        r = _reglas(ESCENARIO + """
            console.log(JSON.stringify([
                valida(LIENZO.w - TAM.w, 10), valida(LIENZO.w - TAM.w + 1, 10), valida(-1, 10),
            ]));
        """)
        assert r == [True, False, False]

    def test_cortar_una_division_es_invalido_y_entrar_completo_no(self):
        r = _reglas(ESCENARIO + """
            const div = [{x: 400, y: 0, w: 300, h: 300}];
            const v = (x, y) => R.posicionValida(x, y, TAM, LIENZO, [], div);
            console.log(JSON.stringify([v(450, 50), v(350, 50)]));
        """)
        assert r == [True, False]

    def test_modulos_sin_posicion_no_chocan(self):
        r = _reglas(ESCENARIO + """
            console.log(JSON.stringify(R.posicionValida(10, 10, TAM, LIENZO, [{x: 0, y: 0}], [])));
        """)
        assert r is True

    def test_mismas_reglas_que_el_servidor(self):
        # Cualquier par de posiciones: el JS y posiciones_mapa.se_solapan coinciden.
        casos = [((0, 0), (W, 0)) for W in (pm.ANCHO_MODULO,)] + [
            ((100, 100), (100, 100)), ((100, 100), (219, 179)), ((100, 100), (220, 100)), ((100, 100), (100, 180)),
        ]
        r = _reglas(ESCENARIO + f"""
            const casos = {json.dumps([[list(a), list(b)] for a, b in casos])};
            console.log(JSON.stringify(casos.map(([a, b]) =>
                R.seSolapan({{x: a[0], y: a[1], ...TAM}}, {{x: b[0], y: b[1], ...TAM}}))));
        """)
        assert r == [pm.se_solapan(pm.rect_modulo(*a), pm.rect_modulo(*b)) for a, b in casos]


# ── Servidor como respaldo ────────────────────────────────────────────────

def test_el_guardado_sigue_rechazando_solapamientos_de_fuera_del_editor(cliente_autenticado, laboratorio):
    a = Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio, posicion_x=10, posicion_y=10)
    b = Modulo.objects.create(nombre='B', capacidad=1, laboratorio=laboratorio, posicion_x=500, posicion_y=500)
    # Petición directa, sin pasar por el editor.
    resp = cliente_autenticado.post(
        reverse('guardar_mapa', args=[laboratorio.id]),
        data=json.dumps({'modulos': [{'id': b.id, 'x': 20, 'y': 20}]}), content_type='application/json',
    )
    assert resp.status_code == 400
    assert '"A" y "B"' in resp.json()['error']
    b.refresh_from_db()
    assert (b.posicion_x, b.posicion_y) == (500, 500)
