"""
Tests del management command laboratorio/management/commands/
inicializar_posiciones_modulos.py y del alto dinámico del lienzo del editor.
"""
from io import StringIO

import pytest
from django.core.management import call_command

from laboratorio.management.commands.inicializar_posiciones_modulos import (
    ALTO_MODULO,
    ANCHO_LIENZO,
    ANCHO_MODULO,
    calcular_posiciones,
    repartir_en_zonas,
)
from laboratorio.models import Laboratorio, Modulo

pytestmark = pytest.mark.django_db


def _modulos(laboratorio, n, prefijo='M'):
    return [Modulo.objects.create(nombre=f'{prefijo}{i}', capacidad=2, laboratorio=laboratorio) for i in range(n)]


def _posiciones(laboratorio):
    return list(laboratorio.modulos.order_by('id').values_list('posicion_x', 'posicion_y'))


def _correr(*args):
    salida = StringIO()
    call_command('inicializar_posiciones_modulos', *args, stdout=salida)
    return salida.getvalue()


def _se_solapan(posiciones):
    return any(
        abs(a[0] - b[0]) < ANCHO_MODULO and abs(a[1] - b[1]) < ALTO_MODULO
        for i, a in enumerate(posiciones) for b in posiciones[i + 1:]
    )


# ── Cálculo del diseño ───────────────────────────────────────────────────────

def test_reparto_replica_el_js_de_mapa_html():
    # 30 módulos: 18 % por lado y abajo (5), el resto 4 / 7 / 4 en el centro.
    zonas = repartir_en_zonas(30)

    assert [zonas.count(z) for z in ['izquierda', 'centro-top', 'centro-mid', 'centro-bot', 'derecha', 'inferior']] == [5, 4, 7, 4, 5, 5]
    assert zonas[:5] == ['izquierda'] * 5  # en orden, como el JS


@pytest.mark.parametrize('total', [1, 2, 3, 7, 10, 30, 45, 80])
def test_posiciones_sin_solapes_y_dentro_del_ancho(total):
    posiciones = calcular_posiciones(total)

    assert len(posiciones) == total
    assert not _se_solapan(posiciones)
    assert all(x >= 0 and y >= 0 for x, y in posiciones)
    assert max(x for x, _ in posiciones) + ANCHO_MODULO <= ANCHO_LIENZO
    assert (0, 0) not in posiciones  # nada queda "sin inicializar"


def test_30_modulos_caben_en_el_lienzo_de_600px():
    assert max(y for _, y in calcular_posiciones(30)) + ALTO_MODULO <= 600


# ── Comando ──────────────────────────────────────────────────────────────────

def test_inicializa_modulos_en_cero(laboratorio):
    _modulos(laboratorio, 30)

    salida = _correr()

    posiciones = _posiciones(laboratorio)
    assert posiciones == calcular_posiciones(30)
    assert not _se_solapan(posiciones)
    assert 'Total: 30 módulos inicializados.' in salida


def test_distribuye_cada_laboratorio_por_separado(laboratorio):
    otro = Laboratorio.objects.create(nombre='Otro', ubicacion='B2')
    _modulos(laboratorio, 30, 'A')
    _modulos(otro, 30, 'B')

    _correr()

    # Cada lab usa su propio diseño (no un índice acumulado entre labs).
    assert _posiciones(laboratorio) == _posiciones(otro) == calcular_posiciones(30)


def test_es_idempotente(laboratorio):
    _modulos(laboratorio, 12)
    _correr()
    antes = _posiciones(laboratorio)

    salida = _correr()

    assert _posiciones(laboratorio) == antes
    assert 'Total: 0 módulos inicializados.' in salida


def test_no_toca_modulos_ya_posicionados(laboratorio):
    movido, *_ = _modulos(laboratorio, 10)
    movido.posicion_x, movido.posicion_y = 777, 333
    movido.save()

    salida = _correr()

    movido.refresh_from_db()
    assert (movido.posicion_x, movido.posicion_y) == (777, 333)
    assert '9 de 10 módulos a inicializar' in salida


def test_dry_run_no_guarda(laboratorio):
    _modulos(laboratorio, 5)

    salida = _correr('--dry-run')

    assert set(_posiciones(laboratorio)) == {(0, 0)}
    assert 'Dry run: se inicializarían 5 módulos.' in salida


def test_filtro_por_laboratorio(laboratorio):
    otro = Laboratorio.objects.create(nombre='Otro', ubicacion='B2')
    _modulos(laboratorio, 5)
    _modulos(otro, 5)

    _correr('--laboratorio', str(laboratorio.id))

    assert (0, 0) not in _posiciones(laboratorio)
    assert set(_posiciones(otro)) == {(0, 0)}


def test_sin_modulos_no_falla(db):
    assert 'Total: 0 módulos inicializados.' in _correr()


# ── Editor: el lienzo crece con los módulos ──────────────────────────────────

def test_editor_lienzo_minimo_600(cliente_autenticado, laboratorio):
    _modulos(laboratorio, 3)

    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/editar-mapa/')

    assert response.context['alto_canvas'] == 600
    assert 'height: 600px;' in response.content.decode()


def test_editor_lienzo_crece_si_hay_modulos_mas_abajo(cliente_autenticado, laboratorio):
    Modulo.objects.create(nombre='Abajo', capacidad=2, laboratorio=laboratorio, posicion_x=10, posicion_y=900)

    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/editar-mapa/')

    assert response.context['alto_canvas'] == 900 + ALTO_MODULO + 20
