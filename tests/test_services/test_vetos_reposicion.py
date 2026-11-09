"""
Tests de RegistrarVetoService.registrar_por_devolucion (vetos/services.py)
según Insumo.reposicion_obligatoria: un consumible no obligatorio que se
extravía queda 'Perdido' pero no genera veto FALTA_INSUMO.

Se recorre el flujo real (iniciar inspección -> marcar -> finalizar) para
verificar a la vez el estado del ítem y los vetos creados.
"""
import pytest

from inventario.models import EstadoItem, Insumo, ItemInventario
from prestamos.models import InspeccionItem, PrestamoItem
from prestamos.services.inspeccionar_prestamo_service import (
    FinalizarInspeccionService,
    InspeccionarPrestamoService,
)
from solicitudes.models import SolicitudReserva
from vetos.models import Veto

pytestmark = pytest.mark.django_db


@pytest.fixture
def prestamo_identificado(reserva_con_prestamo, laboratorio):
    """reserva_con_prestamo + SolicitudReserva con cédula, para que los
    vetos puedan identificar al sancionado."""
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante',
        cedula='111222333',
        laboratorio=laboratorio,
        fecha_reserva=reserva_con_prestamo.reserva.fecha_reserva,
        reserva=reserva_con_prestamo.reserva,
    )
    return reserva_con_prestamo


def _consumible(laboratorio):
    return Insumo.objects.create(
        nombre='Guantes de nitrilo',
        descripcion='Par de guantes desechables',
        laboratorio=laboratorio,
        tipo='consumible',
        reposicion_obligatoria=False,
    )


def _agregar_item(prestamo, insumo, laboratorio, codigo):
    item = ItemInventario.objects.create(
        codigo=codigo,
        insumo=insumo,
        estado=EstadoItem.objects.get(nombre='Disponible'),
        laboratorio=laboratorio,
    )
    PrestamoItem.objects.create(prestamo=prestamo, item_inventario=item)
    return item


def _inspeccionar_y_finalizar(prestamo, usuario, estados_por_item):
    """estados_por_item: {item_inventario_id: estado_inspeccion}."""
    InspeccionarPrestamoService().iniciar_inspeccion(
        prestamo_id=prestamo.id, usuario=usuario,
    )
    for item_id, estado in estados_por_item.items():
        InspeccionItem.objects.filter(
            prestamo=prestamo, prestamo_item__item_inventario_id=item_id,
        ).update(estado_inspeccion=estado)
    FinalizarInspeccionService().finalizar(prestamo_id=prestamo.id)


def _vetos(prestamo, tipo):
    return Veto.objects.filter(prestamo=prestamo, tipo=tipo)


def test_insumo_existente_es_herramienta_obligatoria_por_defecto(insumo):
    assert insumo.tipo == 'herramienta'
    assert insumo.reposicion_obligatoria is True


def test_herramienta_no_entregada_crea_veto_falta_insumo(prestamo_identificado, usuario_admin):
    ctx = prestamo_identificado
    _inspeccionar_y_finalizar(ctx.prestamo, usuario_admin, {ctx.item.id: 'no_entregado'})

    assert _vetos(ctx.prestamo, Veto.FALTA_INSUMO).count() == 1


def test_consumible_no_entregado_no_crea_veto_y_queda_perdido(
    prestamo_identificado, usuario_admin, laboratorio,
):
    ctx = prestamo_identificado
    # El préstamo solo lleva el consumible: se quita el ítem herramienta
    # del fixture para que no influya.
    ctx.prestamo_item.delete()
    item = _agregar_item(ctx.prestamo, _consumible(laboratorio), laboratorio, 'CONS-001')

    _inspeccionar_y_finalizar(ctx.prestamo, usuario_admin, {item.id: 'no_entregado'})

    item.refresh_from_db()
    assert item.estado.nombre == 'Perdido'
    assert not _vetos(ctx.prestamo, Veto.FALTA_INSUMO).exists()
    assert not Veto.objects.filter(prestamo=ctx.prestamo).exists()


def test_consumible_y_herramienta_perdidos_crean_un_solo_veto(
    prestamo_identificado, usuario_admin, laboratorio,
):
    ctx = prestamo_identificado
    consumible = _agregar_item(ctx.prestamo, _consumible(laboratorio), laboratorio, 'CONS-001')

    _inspeccionar_y_finalizar(ctx.prestamo, usuario_admin, {
        ctx.item.id: 'no_entregado',
        consumible.id: 'no_entregado',
    })

    assert _vetos(ctx.prestamo, Veto.FALTA_INSUMO).count() == 1
    consumible.refresh_from_db()
    ctx.item.refresh_from_db()
    assert consumible.estado.nombre == 'Perdido'
    assert ctx.item.estado.nombre == 'Perdido'


def test_consumible_danado_sigue_creando_veto_dano(
    prestamo_identificado, usuario_admin, laboratorio,
):
    ctx = prestamo_identificado
    ctx.prestamo_item.delete()
    item = _agregar_item(ctx.prestamo, _consumible(laboratorio), laboratorio, 'CONS-001')

    _inspeccionar_y_finalizar(ctx.prestamo, usuario_admin, {item.id: 'danado'})

    assert _vetos(ctx.prestamo, Veto.DANO).count() == 1
    assert not _vetos(ctx.prestamo, Veto.FALTA_INSUMO).exists()
