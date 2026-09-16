"""
Tests para el management command crear_insumos_por_lab
(inventario/management/commands/crear_insumos_por_lab.py).
"""
from io import StringIO

import pytest
from django.core.management import call_command

from inventario.models import Insumo, ItemInventario, MovimientoInventario
from laboratorio.models import Laboratorio

pytestmark = pytest.mark.django_db


def _correr(**opciones):
    call_command('crear_insumos_por_lab', stdout=StringIO(), **opciones)


def test_crea_insumos_e_items_para_laboratorio_activo(catalogos):
    lab = Laboratorio.objects.create(nombre='Laboratorio de Mecánica', ubicacion='Bloque 1')

    _correr(seed=1)

    insumos = Insumo.objects.filter(laboratorio=lab)
    assert insumos.exists()
    for insumo in insumos:
        assert insumo.stock_total() >= 2


def test_elige_catalogo_segun_nombre_del_laboratorio(catalogos):
    Laboratorio.objects.create(nombre='Laboratorio de Mecánica', ubicacion='Bloque 1')
    Laboratorio.objects.create(nombre='Laboratorio de Ingeniería de Sistemas', ubicacion='Bloque 2')

    _correr(seed=1)

    nombres_mecanica = set(Insumo.objects.filter(laboratorio__nombre__icontains='Mecánica').values_list('nombre', flat=True))
    nombres_sistemas = set(Insumo.objects.filter(laboratorio__nombre__icontains='Ingeniería').values_list('nombre', flat=True))

    assert 'Martillo' in nombres_mecanica
    assert 'Laptop' in nombres_sistemas
    # Catálogos distintos: no deberían coincidir en todos los nombres.
    assert nombres_mecanica != nombres_sistemas


def test_no_pobla_laboratorio_inactivo(catalogos):
    Laboratorio.objects.create(nombre='Laboratorio Inactivo', ubicacion='Bloque 3', activo=False)

    _correr(seed=1)

    assert not Insumo.objects.filter(laboratorio__nombre='Laboratorio Inactivo').exists()


def test_registra_movimiento_de_alta_por_item_creado(catalogos):
    Laboratorio.objects.create(nombre='Laboratorio de Química', ubicacion='Bloque 4')

    _correr(seed=1)

    items = ItemInventario.objects.all()
    assert items.exists()
    for item in items:
        assert MovimientoInventario.objects.filter(item_inventario=item).exists()


def test_es_idempotente_no_duplica_en_segunda_corrida(catalogos):
    Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 5')

    _correr(seed=1)
    total_insumos_1 = Insumo.objects.count()
    total_items_1 = ItemInventario.objects.count()

    _correr(seed=1)
    total_insumos_2 = Insumo.objects.count()
    total_items_2 = ItemInventario.objects.count()

    assert total_insumos_1 == total_insumos_2
    assert total_items_1 == total_items_2


def test_sin_laboratorios_no_falla(catalogos):
    _correr(seed=1)  # No debe lanzar excepción aunque no haya labs.

    assert Insumo.objects.count() == 0
