"""
Tests HTTP (Client) para prestamos/views.py.
"""
import pytest

from prestamos.models import InspeccionItem

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
