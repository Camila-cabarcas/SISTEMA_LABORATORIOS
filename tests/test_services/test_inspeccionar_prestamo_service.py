"""
Tests para InspeccionarPrestamoService y FinalizarInspeccionService
(prestamos/services/inspeccionar_prestamo_service.py).
"""
import pytest
from django.core.exceptions import ValidationError

from inventario.models import EstadoItem, ItemInventario
from prestamos.models import InspeccionItem, PrestamoItem
from prestamos.services.inspeccionar_prestamo_service import (
    FinalizarInspeccionService,
    InspeccionarPrestamoService,
)

pytestmark = pytest.mark.django_db


def test_iniciar_inspeccion_exitosa(reserva_con_prestamo, usuario_admin):
    prestamo = InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )

    assert prestamo.estado.nombre == 'En Inspección'


def test_iniciar_inspeccion_crea_items(reserva_con_prestamo, usuario_admin):
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )

    inspecciones = InspeccionItem.objects.filter(prestamo=reserva_con_prestamo.prestamo)
    assert inspecciones.count() == 1
    assert inspecciones.first().prestamo_item_id == reserva_con_prestamo.prestamo_item.id


def test_finalizar_inspeccion_validar_todos(reserva_con_prestamo, usuario_admin, insumo, laboratorio):
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )

    # Se agrega un segundo ítem al préstamo que nunca pasa por inspección.
    estado_disponible = EstadoItem.objects.get(nombre='Disponible')
    item_extra = ItemInventario.objects.create(
        codigo='ITEM-002',
        insumo=insumo,
        estado=estado_disponible,
        laboratorio=laboratorio,
    )
    PrestamoItem.objects.create(
        prestamo=reserva_con_prestamo.prestamo,
        item_inventario=item_extra,
    )

    with pytest.raises(ValidationError):
        FinalizarInspeccionService().finalizar(prestamo_id=reserva_con_prestamo.prestamo.id)


def test_finalizar_actualiza_estado_bien(reserva_con_prestamo, usuario_admin):
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )
    InspeccionItem.objects.filter(prestamo=reserva_con_prestamo.prestamo).update(
        estado_inspeccion='bien'
    )

    FinalizarInspeccionService().finalizar(prestamo_id=reserva_con_prestamo.prestamo.id)

    reserva_con_prestamo.item.refresh_from_db()
    assert reserva_con_prestamo.item.estado.nombre == 'Disponible'


def test_finalizar_actualiza_estado_danado(reserva_con_prestamo, usuario_admin):
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )
    InspeccionItem.objects.filter(prestamo=reserva_con_prestamo.prestamo).update(
        estado_inspeccion='danado'
    )

    FinalizarInspeccionService().finalizar(prestamo_id=reserva_con_prestamo.prestamo.id)

    reserva_con_prestamo.item.refresh_from_db()
    assert reserva_con_prestamo.item.estado.nombre == 'Dañado'


def test_finalizar_no_entregado_sin_cambio(reserva_con_prestamo, usuario_admin):
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )
    estado_previo_id = reserva_con_prestamo.item.estado_id
    InspeccionItem.objects.filter(prestamo=reserva_con_prestamo.prestamo).update(
        estado_inspeccion='no_entregado'
    )

    FinalizarInspeccionService().finalizar(prestamo_id=reserva_con_prestamo.prestamo.id)

    reserva_con_prestamo.item.refresh_from_db()
    assert reserva_con_prestamo.item.estado_id == estado_previo_id


def test_finalizar_marca_devuelto(reserva_con_prestamo, usuario_admin):
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=reserva_con_prestamo.prestamo.id,
        usuario=usuario_admin,
    )
    InspeccionItem.objects.filter(prestamo=reserva_con_prestamo.prestamo).update(
        estado_inspeccion='bien'
    )

    resultado = FinalizarInspeccionService().finalizar(prestamo_id=reserva_con_prestamo.prestamo.id)

    assert resultado['prestamo'].estado.nombre == 'Devuelto'
