"""
Tests de Division (laboratorio/models.py) y laboratorio/services/divisiones.py:
máximo por laboratorio, validaciones, pertenencia por posición y guardado
todo-o-nada del editor de mapa.
"""
import pytest
from django.core.exceptions import ValidationError

from laboratorio.models import Division, Laboratorio, Modulo
from laboratorio.services.divisiones import (
    MapaInvalido, crear_division, division_para, guardar_mapa,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def otro_lab(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 1')


def _division(lab, nombre, x=0, y=0, ancho=300, alto=200):
    return Division.objects.create(laboratorio=lab, nombre=nombre, x=x, y=y, ancho=ancho, alto=alto)


def _modulo(lab, nombre, x=0, y=0, **extra):
    return Modulo.objects.create(nombre=nombre, capacidad=4, laboratorio=lab, posicion_x=x, posicion_y=y, **extra)


def _cuatro(lab):
    # Sin superponerse: 2×2 de 300×200.
    return [_division(lab, f'Salón {i}', x=(i % 2) * 320, y=(i // 2) * 220) for i in range(4)]


# ── Máximo de 4 ───────────────────────────────────────────────────────────

class TestMaximo:

    def test_modelo_rechaza_la_quinta(self, laboratorio):
        _cuatro(laboratorio)
        quinta = Division(laboratorio=laboratorio, nombre='Salón 5', x=700, y=0, ancho=200, alto=200)
        with pytest.raises(ValidationError) as e:
            quinta.full_clean()
        assert 'laboratorio' in e.value.message_dict
        assert 'máximo 4' in e.value.message_dict['laboratorio'][0]

    def test_modelo_permite_editar_una_de_las_cuatro(self, laboratorio):
        divisiones = _cuatro(laboratorio)
        divisiones[0].nombre = 'Renombrada'
        divisiones[0].full_clean()  # no cuenta a sí misma

    def test_servicio_crear_rechaza_la_quinta(self, laboratorio):
        for i in range(4):
            crear_division(laboratorio, f'Salón {i}', x=i * 160, y=0, ancho=150, alto=150)
        with pytest.raises(ValidationError, match='máximo 4'):
            crear_division(laboratorio, 'Salón 5', x=700, y=300)
        assert laboratorio.divisiones.count() == 4

    def test_servicio_guardar_mapa_rechaza_cinco(self, laboratorio):
        cinco = [{'nombre': f'S{i}', 'x': i * 160, 'y': 0, 'ancho': 150, 'alto': 150} for i in range(5)]
        with pytest.raises(MapaInvalido, match='máximo 4'):
            guardar_mapa(laboratorio, {'modulos': [], 'divisiones': cinco})
        assert not Division.objects.exists()

    def test_el_maximo_es_por_laboratorio(self, laboratorio, otro_lab):
        _cuatro(laboratorio)
        crear_division(otro_lab, 'Salón 1')  # el otro lab sigue teniendo cupo
        assert otro_lab.divisiones.count() == 1


# ── Validaciones del modelo ───────────────────────────────────────────────

class TestValidacionModelo:

    @pytest.mark.parametrize('campos, error', [
        ({'nombre': '  '}, 'nombre'),
        ({'x': -1}, 'x'),
        ({'ancho': 50}, 'ancho'),
        ({'alto': 5000}, 'alto'),
    ])
    def test_datos_invalidos(self, laboratorio, campos, error):
        datos = {'nombre': 'Salón', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200, **campos}
        with pytest.raises(ValidationError) as e:
            Division(laboratorio=laboratorio, **datos).full_clean()
        assert error in e.value.message_dict

    def test_nombre_unico_por_laboratorio(self, laboratorio, otro_lab):
        _division(laboratorio, 'Salón A')
        _division(otro_lab, 'Salón A')  # en otro lab sí se puede
        with pytest.raises(ValidationError):
            Division(laboratorio=laboratorio, nombre='Salón A', x=400, y=0).full_clean()

    def test_modulo_no_puede_tener_division_de_otro_laboratorio(self, laboratorio, otro_lab):
        ajena = _division(otro_lab, 'Ajena')
        modulo = Modulo(nombre='M', capacidad=1, laboratorio=laboratorio, division=ajena)
        with pytest.raises(ValidationError) as e:
            modulo.full_clean()
        assert 'division' in e.value.message_dict

    def test_nombre_con_division(self, laboratorio):
        d = _division(laboratorio, 'Salón A')
        assert _modulo(laboratorio, 'Mesa 1', division=d).nombre_con_division == 'Mesa 1 · Salón A'
        assert _modulo(laboratorio, 'Mesa 2').nombre_con_division == 'Mesa 2'


# ── Pertenencia por posición ──────────────────────────────────────────────

class TestDivisionPara:

    def test_por_el_centro_del_modulo(self, laboratorio):
        d = _division(laboratorio, 'A', x=100, y=100, ancho=300, alto=200)
        # Módulo 120×80: centro = (x+60, y+40).
        assert division_para(100, 100, [d]) == d          # centro (160,140) dentro
        assert division_para(39, 100, [d]) is None         # centro (99,140): afuera
        assert division_para(40, 100, [d]) == d            # centro (100,140): borde izquierdo incluido
        assert division_para(340, 100, [d]) is None        # centro (400,140): borde derecho excluido
        assert division_para(600, 600, [d]) is None

    def test_modulo_sin_posicion_no_pertenece(self, laboratorio):
        d = _division(laboratorio, 'A', x=0, y=0, ancho=500, alto=500)
        assert division_para(0, 0, [d]) is None


# ── guardar_mapa ──────────────────────────────────────────────────────────

class TestGuardarMapa:

    def test_cero_divisiones_funciona_como_antes(self, laboratorio):
        a = _modulo(laboratorio, 'A')
        modulos, divisiones = guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 120, 'y': 40}]})
        a.refresh_from_db()
        assert (a.posicion_x, a.posicion_y, a.division) == (120, 40, None)
        assert divisiones == []
        assert [m.id for m in modulos] == [a.id]

    def test_asigna_division_segun_posicion(self, laboratorio):
        a, b, c = _modulo(laboratorio, 'A'), _modulo(laboratorio, 'B'), _modulo(laboratorio, 'C')
        datos = {
            'modulos': [{'id': a.id, 'x': 20, 'y': 40}, {'id': b.id, 'x': 420, 'y': 40}, {'id': c.id, 'x': 20, 'y': 400}],
            'divisiones': [
                {'id': None, 'nombre': 'Salón A', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 300},
                {'id': None, 'nombre': 'Salón B', 'x': 400, 'y': 0, 'ancho': 300, 'alto': 300},
            ],
        }
        guardar_mapa(laboratorio, datos)
        for m in (a, b, c):
            m.refresh_from_db()
        assert a.division.nombre == 'Salón A'
        assert b.division.nombre == 'Salón B'
        assert c.division is None

    def test_mover_un_modulo_fuera_le_quita_la_division(self, laboratorio):
        d = _division(laboratorio, 'A', x=0, y=0, ancho=300, alto=300)
        a = _modulo(laboratorio, 'A', x=20, y=20, division=d)
        guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 500, 'y': 500}]})
        a.refresh_from_db()
        assert a.division is None

    def test_sin_clave_divisiones_las_conserva_y_reasigna(self, laboratorio):
        d = _division(laboratorio, 'A', x=0, y=0, ancho=300, alto=300)
        a = _modulo(laboratorio, 'A', x=500, y=500)
        guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 20, 'y': 20}]})
        a.refresh_from_db()
        assert a.division == d
        assert laboratorio.divisiones.count() == 1

    def test_modulos_no_enviados_tambien_se_reasignan(self, laboratorio):
        b = _modulo(laboratorio, 'B', x=20, y=20)  # ya está donde caerá la división
        guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
            {'nombre': 'Salón A', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 300},
        ]})
        b.refresh_from_db()
        assert b.division.nombre == 'Salón A'

    def test_actualiza_divisiones_existentes(self, laboratorio):
        d = _division(laboratorio, 'Viejo', x=0, y=0)
        guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
            {'id': d.id, 'nombre': 'Nuevo', 'x': 50, 'y': 60, 'ancho': 400, 'alto': 250},
        ]})
        d.refresh_from_db()
        assert (d.nombre, d.x, d.y, d.ancho, d.alto) == ('Nuevo', 50, 60, 400, 250)

    def test_intercambiar_nombres_entre_divisiones(self, laboratorio):
        a = _division(laboratorio, 'A', x=0, y=0)
        b = _division(laboratorio, 'B', x=400, y=0)
        guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
            {'id': a.id, 'nombre': 'B', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
            {'id': b.id, 'nombre': 'A', 'x': 400, 'y': 0, 'ancho': 300, 'alto': 200},
        ]})
        a.refresh_from_db()
        b.refresh_from_db()
        assert (a.nombre, b.nombre) == ('B', 'A')

    def test_eliminar_division_no_borra_modulos(self, laboratorio):
        d = _division(laboratorio, 'A', x=0, y=0, ancho=300, alto=300)
        a = _modulo(laboratorio, 'A', x=20, y=20, division=d)
        b = _modulo(laboratorio, 'B', x=40, y=100, division=d)

        guardar_mapa(laboratorio, {'modulos': [], 'divisiones': []})

        assert not Division.objects.exists()
        assert Modulo.objects.filter(id__in=[a.id, b.id]).count() == 2
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.division is None and b.division is None
        assert (a.posicion_x, a.posicion_y) == (20, 20)

    def test_borrar_division_directo_tampoco_borra_modulos(self, laboratorio):
        d = _division(laboratorio, 'A')
        a = _modulo(laboratorio, 'A', division=d)
        d.delete()
        a.refresh_from_db()
        assert a.division is None

    # ── Todo o nada ──
    @pytest.mark.parametrize('divisiones, mensaje', [
        ([{'nombre': '', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200}], 'nombre'),
        ([{'nombre': 'A', 'x': -5, 'y': 0, 'ancho': 300, 'alto': 200}], 'lienzo'),
        ([{'nombre': 'A', 'x': 0, 'y': 0, 'ancho': 10, 'alto': 200}], 'ancho'),
        ([{'nombre': 'A', 'x': 'mucho', 'y': 0, 'ancho': 300, 'alto': 200}], 'inválido'),
        ([{'nombre': 'A', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
          {'nombre': 'a', 'x': 400, 'y': 0, 'ancho': 300, 'alto': 200}], 'dos divisiones'),
        ([{'nombre': 'A', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
          {'nombre': 'B', 'x': 100, 'y': 100, 'ancho': 300, 'alto': 200}], 'superponen'),
        ('no-es-lista', 'lista'),
    ])
    def test_division_invalida_no_guarda_nada(self, laboratorio, divisiones, mensaje):
        existente = _division(laboratorio, 'Existente', x=800, y=800)
        a = _modulo(laboratorio, 'A')

        with pytest.raises(MapaInvalido, match=mensaje):
            guardar_mapa(laboratorio, {'modulos': [{'id': a.id, 'x': 99, 'y': 99}], 'divisiones': divisiones})

        a.refresh_from_db()
        assert (a.posicion_x, a.posicion_y) == (0, 0)
        assert list(laboratorio.divisiones.all()) == [existente]

    def test_division_de_otro_laboratorio_400(self, laboratorio, otro_lab):
        ajena = _division(otro_lab, 'Ajena')
        with pytest.raises(MapaInvalido, match='no pertenece'):
            guardar_mapa(laboratorio, {'modulos': [], 'divisiones': [
                {'id': ajena.id, 'nombre': 'Robada', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
            ]})
        ajena.refresh_from_db()
        assert (ajena.laboratorio, ajena.nombre) == (otro_lab, 'Ajena')

    def test_no_toca_divisiones_de_otro_laboratorio(self, laboratorio, otro_lab):
        ajena = _division(otro_lab, 'Ajena')
        guardar_mapa(laboratorio, {'modulos': [], 'divisiones': []})
        assert Division.objects.filter(id=ajena.id).exists()

    def test_modulo_ajeno_no_guarda_divisiones(self, laboratorio, otro_lab):
        ajeno = _modulo(otro_lab, 'Ajeno')
        with pytest.raises(MapaInvalido, match='no pertenecen'):
            guardar_mapa(laboratorio, {'modulos': [{'id': ajeno.id, 'x': 1, 'y': 1}], 'divisiones': [
                {'nombre': 'A', 'x': 0, 'y': 0, 'ancho': 300, 'alto': 200},
            ]})
        assert not Division.objects.exists()
