"""
Tests para el sistema de stock: Insumo.stock_*() (inventario/models.py) y
PrestamoStockService (prestamos/services/prestamo_stock_service.py).

El descuento real de stock al prestar y su reintegro al devolver ya lo hace
MutacionInventarioService/FinalizarInspeccionService (disparados por
signals.py) — estos tests ejercitan ese mismo flujo real (crear PrestamoItem,
finalizar una inspección) y verifican que Insumo.stock_disponible() y
PrestamoStockService reflejan el resultado correctamente, además de la
validación de "sin stock" que antes no existía como paso explícito.
"""
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario
from prestamos.models import EstadoPrestamo, InspeccionItem, Prestamo, PrestamoItem
from prestamos.services.inspeccionar_prestamo_service import FinalizarInspeccionService
from prestamos.services.prestamo_stock_service import PrestamoStockService
from reservas.models import EstadoReserva, Reserva

pytestmark = pytest.mark.django_db


def _insumo_con_items(laboratorio, cantidad=2, nombre='Metro'):
    insumo = Insumo.objects.create(
        nombre=nombre, laboratorio=laboratorio, descripcion='Para tests', stock_minimo=0,
    )
    estado_disponible = EstadoItem.objects.get(nombre='Disponible')
    items = [
        ItemInventario.objects.create(
            codigo=f'{nombre}-{i}', insumo=insumo, estado=estado_disponible, laboratorio=laboratorio,
        )
        for i in range(cantidad)
    ]
    return insumo, items


def _prestamo_activo(usuario_admin):
    return Prestamo.objects.create(
        reserva=Reserva.objects.create(
            fecha_reserva=timezone.now(),
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
        ),
        responsable=usuario_admin,
        estado=EstadoPrestamo.objects.get(nombre='Activo'),
    )


# ── Insumo.stock_*() ─────────────────────────────────────────────────────

class TestInsumoStockMethods:

    def test_stock_total_y_disponible_insumo_sin_items(self, laboratorio, catalogos):
        insumo = Insumo.objects.create(nombre='Vacío', laboratorio=laboratorio, descripcion='x')

        assert insumo.stock_total() == 0
        assert insumo.stock_disponible() == 0

    def test_stock_total_cuenta_todos_los_estados(self, laboratorio, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=2, nombre='Osciloscopio')
        items[0].estado = EstadoItem.objects.get(nombre='Dañado')
        items[0].save()

        assert insumo.stock_total() == 2
        assert insumo.stock_disponible() == 1
        assert insumo.stock_danado() == 1
        assert insumo.stock_prestado() == 0
        assert insumo.stock_perdido() == 0

    def test_stock_disponible_es_igual_a_cantidad_disponible(self, laboratorio, catalogos):
        insumo, _ = _insumo_con_items(laboratorio, cantidad=3, nombre='Multímetro')

        assert insumo.stock_disponible() == insumo.cantidad_disponible() == 3

    def test_item_soft_deleted_no_cuenta_en_stock_total(self, laboratorio, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=2, nombre='Cable')
        items[0].soft_delete()

        assert insumo.stock_total() == 1
        assert insumo.stock_disponible() == 1

    def test_nombre_repetido_en_labs_distintos_es_valido(self, laboratorio, catalogos):
        from laboratorio.models import Laboratorio
        otro_lab = Laboratorio.objects.create(nombre='Otro Lab', ubicacion='Bloque 9')

        Insumo.objects.create(nombre='Multímetro', laboratorio=laboratorio, descripcion='x')
        # No debe chocar: la unicidad ahora es (nombre, laboratorio), no solo nombre.
        Insumo.objects.create(nombre='Multímetro', laboratorio=otro_lab, descripcion='x')

        assert Insumo.objects.filter(nombre='Multímetro').count() == 2

    def test_nombre_repetido_en_mismo_lab_es_invalido(self, laboratorio, catalogos):
        Insumo.objects.create(nombre='Multímetro', laboratorio=laboratorio, descripcion='x')

        with pytest.raises(Exception):
            Insumo.objects.create(nombre='Multímetro', laboratorio=laboratorio, descripcion='x')


# ── PrestamoStockService ─────────────────────────────────────────────────

class TestPrestamoStockService:

    def test_hay_disponible_true_con_stock(self, laboratorio, catalogos):
        insumo, _ = _insumo_con_items(laboratorio, cantidad=2, nombre='Llave')

        assert PrestamoStockService.hay_disponible(insumo) is True
        assert PrestamoStockService.hay_disponible(insumo, cantidad=2) is True
        assert PrestamoStockService.hay_disponible(insumo, cantidad=3) is False

    def test_hay_disponible_false_sin_stock(self, laboratorio, catalogos):
        insumo = Insumo.objects.create(nombre='Sin Stock', laboratorio=laboratorio, descripcion='x')

        assert PrestamoStockService.hay_disponible(insumo) is False

    def test_validar_disponibilidad_no_lanza_con_stock(self, laboratorio, catalogos):
        insumo, _ = _insumo_con_items(laboratorio, cantidad=1, nombre='Martillo')

        PrestamoStockService.validar_disponibilidad(insumo)  # no debe lanzar

    def test_validar_disponibilidad_lanza_sin_stock(self, laboratorio, catalogos):
        insumo = Insumo.objects.create(nombre='Agotado', laboratorio=laboratorio, descripcion='x')

        with pytest.raises(ValidationError) as exc_info:
            PrestamoStockService.validar_disponibilidad(insumo)
        assert 'Sin stock disponible' in str(exc_info.value)


# ── Ciclo completo: descuento al prestar, reintegro al devolver ─────────

class TestCicloDeStock:

    def test_prestar_descuenta_stock_hasta_agotarlo(self, laboratorio, usuario_admin, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=2, nombre='Metro')
        assert insumo.stock_disponible() == 2

        prestamo = _prestamo_activo(usuario_admin)

        PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[0])
        assert insumo.stock_disponible() == 1
        assert PrestamoStockService.hay_disponible(insumo) is True

        PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[1])
        assert insumo.stock_disponible() == 0
        assert PrestamoStockService.hay_disponible(insumo) is False

        with pytest.raises(ValidationError):
            PrestamoStockService.validar_disponibilidad(insumo)

    def test_cada_prestamo_item_registra_movimiento_de_auditoria(self, laboratorio, usuario_admin, catalogos):
        from inventario.models import MovimientoInventario

        insumo, items = _insumo_con_items(laboratorio, cantidad=1, nombre='Calibrador')
        prestamo = _prestamo_activo(usuario_admin)

        PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[0])

        movimientos = MovimientoInventario.objects.filter(item_inventario=items[0])
        assert movimientos.count() == 1
        assert movimientos.first().usuario == usuario_admin

    def test_devolver_bien_reintegra_stock(self, laboratorio, usuario_admin, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=1, nombre='Probeta')
        prestamo = _prestamo_activo(usuario_admin)
        prestamo_item = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[0])
        assert insumo.stock_disponible() == 0

        InspeccionItem.objects.create(
            prestamo=prestamo, prestamo_item=prestamo_item,
            estado_inspeccion='bien', inspector=usuario_admin,
        )
        FinalizarInspeccionService().finalizar(prestamo_id=prestamo.id)

        assert insumo.stock_disponible() == 1

    def test_devolver_danado_no_reintegra_stock(self, laboratorio, usuario_admin, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=1, nombre='Matraz')
        prestamo = _prestamo_activo(usuario_admin)
        prestamo_item = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[0])
        assert insumo.stock_disponible() == 0

        InspeccionItem.objects.create(
            prestamo=prestamo, prestamo_item=prestamo_item,
            estado_inspeccion='danado', inspector=usuario_admin,
        )
        FinalizarInspeccionService().finalizar(prestamo_id=prestamo.id)

        assert insumo.stock_disponible() == 0
        assert insumo.stock_danado() == 1

    def test_devolver_no_entregado_queda_perdido_y_no_reintegra(self, laboratorio, usuario_admin, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=1, nombre='Pipeta')
        prestamo = _prestamo_activo(usuario_admin)
        prestamo_item = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[0])

        InspeccionItem.objects.create(
            prestamo=prestamo, prestamo_item=prestamo_item,
            estado_inspeccion='no_entregado', inspector=usuario_admin,
        )
        FinalizarInspeccionService().finalizar(prestamo_id=prestamo.id)

        assert insumo.stock_disponible() == 0
        assert insumo.stock_perdido() == 1

    def test_dos_items_mismo_prestamo_una_bien_otra_danada(self, laboratorio, usuario_admin, catalogos):
        insumo, items = _insumo_con_items(laboratorio, cantidad=2, nombre='Sonda')
        prestamo = _prestamo_activo(usuario_admin)
        pi1 = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[0])
        pi2 = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=items[1])
        assert insumo.stock_disponible() == 0

        InspeccionItem.objects.create(
            prestamo=prestamo, prestamo_item=pi1, estado_inspeccion='bien', inspector=usuario_admin,
        )
        InspeccionItem.objects.create(
            prestamo=prestamo, prestamo_item=pi2, estado_inspeccion='danado', inspector=usuario_admin,
        )
        FinalizarInspeccionService().finalizar(prestamo_id=prestamo.id)

        assert insumo.stock_total() == 2
        assert insumo.stock_disponible() == 1
        assert insumo.stock_danado() == 1
