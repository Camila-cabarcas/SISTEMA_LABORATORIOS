"""
Tests HTTP (Client) para reservas/views.py.
"""
from datetime import date, datetime, timedelta

import pytest

from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db


def test_crear_reserva_get(cliente_autenticado):
    response = cliente_autenticado.get('/reservas/crear/')

    assert response.status_code == 200


def test_crear_reserva_post_exitoso(cliente_autenticado, laboratorio):
    fecha = (date.today() + timedelta(days=2)).isoformat()

    response = cliente_autenticado.post('/reservas/crear/', {
        'tipo_solicitante': 'estudiante',
        'nombre': 'Ana Torres',
        'cedula': '987654321',
        'laboratorio': laboratorio.id,
        'fecha': fecha,
        'hora_inicio': '08:00',
        'hora_fin': '10:00',
        'observaciones': '',
        'email': '',
    })

    assert response.status_code == 302
    solicitud = SolicitudReserva.objects.get(cedula='987654321')
    assert solicitud.reserva_id is not None
    assert solicitud.reserva.estado.nombre == 'Aprobada'


def test_detalle_reserva_get(cliente_autenticado, usuario_admin):
    estado = EstadoReserva.objects.get(nombre='Pendiente')
    reserva = Reserva.objects.create(
        usuario=usuario_admin,
        fecha_reserva=datetime(2026, 8, 1, 8, 0),
        estado=estado,
    )

    response = cliente_autenticado.get(f'/reservas/{reserva.id}/')

    assert response.status_code == 200


def test_crear_reserva_sin_permiso(client, usuario_estudiante):
    client.force_login(usuario_estudiante)

    response = client.get('/reservas/crear/')

    assert response.status_code == 302
    assert response.url == '/usuarios/sin-permiso/'


def test_aprobar_reserva_dispara_notificacion(cliente_autenticado, laboratorio, monkeypatch):
    # aprobar_reserva es el camino que un laboratorista realmente usa hoy
    # (a diferencia de AprobarSolicitudReservaService, que no tiene vista
    # propia todavía) — parcheamos notificar_reserva_aprobada en vez de
    # revisar mail.outbox porque el envío real corre en un hilo aparte
    # (async_=True por default) y la vista la importa localmente.
    estado_pendiente = EstadoReserva.objects.get(nombre='Pendiente')
    reserva = Reserva.objects.create(
        fecha_reserva=datetime(2026, 8, 1, 8, 0),
        estado=estado_pendiente,
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula='111222333', email='ana@udea.edu.co',
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva,
        reserva=reserva,
    )

    llamadas = []
    monkeypatch.setattr(
        'utils.notificaciones_email.notificar_reserva_aprobada',
        lambda reserva: llamadas.append(reserva),
    )

    response = cliente_autenticado.post(f'/reservas/{reserva.id}/aprobar/', {'accion': 'aprobar'})

    assert response.status_code == 302
    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Aprobada'
    assert llamadas == [reserva]


def test_cancelar_reserva_no_dispara_notificacion_de_aprobada(cliente_autenticado, laboratorio, monkeypatch):
    estado_pendiente = EstadoReserva.objects.get(nombre='Pendiente')
    reserva = Reserva.objects.create(
        fecha_reserva=datetime(2026, 8, 1, 8, 0),
        estado=estado_pendiente,
    )

    llamadas = []
    monkeypatch.setattr(
        'utils.notificaciones_email.notificar_reserva_aprobada',
        lambda reserva: llamadas.append(reserva),
    )

    response = cliente_autenticado.post(f'/reservas/{reserva.id}/aprobar/', {'accion': 'cancelar'})

    assert response.status_code == 302
    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Cancelada'
    assert llamadas == []
