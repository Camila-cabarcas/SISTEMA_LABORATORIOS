"""
Tests HTTP (Client) para prestamos/views.py.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from inventario.models import EstadoItem, ItemInventario
from prestamos.models import InspeccionItem
from reservas.models import EstadoReserva, Reserva, ReservaInsumo

pytestmark = pytest.mark.django_db


def test_iniciar_inspeccion_get_no_cambia_estado(cliente_autenticado, reserva_con_prestamo):
    # La vista solo actúa sobre POST; GET redirige sin tocar el préstamo.
    prestamo = reserva_con_prestamo.prestamo
    estado_previo = prestamo.estado.nombre

    response = cliente_autenticado.get(f'/prestamos/{prestamo.id}/iniciar-inspeccion/')

    prestamo.refresh_from_db()
    assert response.status_code == 302
    assert prestamo.estado.nombre == estado_previo


def test_iniciar_inspeccion_post_cambia_estado(cliente_autenticado, reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo

    response = cliente_autenticado.post(f'/prestamos/{prestamo.id}/iniciar-inspeccion/')

    prestamo.refresh_from_db()
    assert response.status_code == 302
    assert prestamo.estado.nombre == 'En Inspección'


def test_inspeccionar_prestamo_get(cliente_autenticado, reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo

    response = cliente_autenticado.get(f'/prestamos/{prestamo.id}/inspeccionar/')

    assert response.status_code == 200


def test_inspeccionar_prestamo_post(cliente_autenticado, reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo
    item = reserva_con_prestamo.prestamo_item

    response = cliente_autenticado.post(f'/prestamos/{prestamo.id}/inspeccionar/', {
        f'estado_{item.id}': 'bien',
        f'observaciones_{item.id}': 'Todo en orden',
    })

    assert response.status_code == 302
    inspeccion = InspeccionItem.objects.get(prestamo=prestamo, prestamo_item=item)
    assert inspeccion.estado_inspeccion == 'bien'
    assert inspeccion.observaciones == 'Todo en orden'


def test_marcar_devuelto_post(cliente_autenticado, reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo
    item = reserva_con_prestamo.prestamo_item

    InspeccionItem.objects.create(
        prestamo=prestamo,
        prestamo_item=item,
        estado_inspeccion='bien',
    )

    response = cliente_autenticado.post(f'/prestamos/{prestamo.id}/marcar-devuelto/')

    prestamo.refresh_from_db()
    assert response.status_code == 302
    assert prestamo.estado.nombre == 'Devuelto'


def test_marcar_devuelto_dispara_notificacion(cliente_autenticado, reserva_con_prestamo, monkeypatch):
    # FinalizarInspeccionService.finalizar() (llamado por esta vista) debe
    # notificar la devolución completada — se verifica el cableado con
    # monkeypatch en vez de mail.outbox porque notificar_devolucion_
    # completada envía en un hilo aparte (async_=True por default).
    prestamo = reserva_con_prestamo.prestamo
    item = reserva_con_prestamo.prestamo_item
    InspeccionItem.objects.create(
        prestamo=prestamo, prestamo_item=item, estado_inspeccion='bien',
    )
    llamadas = []
    monkeypatch.setattr(
        'utils.notificaciones_email.notificar_devolucion_completada',
        lambda prestamo, inspecciones: llamadas.append(prestamo.id),
    )

    cliente_autenticado.post(f'/prestamos/{prestamo.id}/marcar-devuelto/')

    assert llamadas == [prestamo.id]


def test_crear_prestamo_post_dispara_notificacion(cliente_autenticado, usuario_admin, laboratorio, insumo, monkeypatch):
    # Reserva Aprobada dentro de la ventana de retiro (fecha_reserva pasada,
    # hora_limite_retiro — fecha_reserva + 30min — todavía no vencida), con
    # un insumo solicitado y un ítem disponible para ese insumo: exactamente
    # lo que crear_prestamo necesita para aceptar el POST.
    reserva = Reserva.objects.create(
        usuario=usuario_admin,
        fecha_reserva=timezone.now() - timedelta(minutes=5),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    ReservaInsumo.objects.create(reserva=reserva, insumo=insumo, cantidad=1)
    item = ItemInventario.objects.create(
        codigo='ITEM-NOTIF-001', insumo=insumo,
        estado=EstadoItem.objects.get(nombre='Disponible'),
        laboratorio=laboratorio,
    )
    llamadas = []
    monkeypatch.setattr(
        'utils.notificaciones_email.notificar_cambios_o_prestamo_listo',
        lambda reserva, tipo='cambios', **kwargs: llamadas.append((reserva.id, tipo)),
    )

    response = cliente_autenticado.post(f'/prestamos/crear/{reserva.id}/', {'items': [item.id]})

    assert response.status_code == 302
    assert llamadas == [(reserva.id, 'prestamo')]
