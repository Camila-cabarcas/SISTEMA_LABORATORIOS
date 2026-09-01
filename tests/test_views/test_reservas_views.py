"""
Tests HTTP (Client) para reservas/views.py.
"""
from datetime import date, datetime, timedelta

import pytest

from inventario.models import EstadoItem, Insumo, ItemInventario
from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva, ReservaInsumo
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db


def _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', email='ana@udea.edu.co'):
    reserva = Reserva.objects.create(
        fecha_reserva=datetime(2026, 8, 1, 8, 0),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula, email=email,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva,
        reserva=reserva,
    )
    return reserva


def _insumo_con_stock(nombre, cantidad, laboratorio=None):
    insumo = Insumo.objects.create(nombre=nombre, descripcion='Para tests', stock_minimo=0)
    estado_disponible = EstadoItem.objects.get(nombre='Disponible')
    for i in range(cantidad):
        ItemInventario.objects.create(
            codigo=f'{nombre}-{i}', insumo=insumo, estado=estado_disponible, laboratorio=laboratorio,
        )
    return insumo


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


def test_aprobar_reserva_accion_desconocida_no_cambia_estado(cliente_autenticado, laboratorio):
    # La vista ya no tiene una rama 'aprobar' — las reservas se aprueban
    # automáticamente al crearse (SolicitudReserva.crear_reserva()). Lo
    # único que esta vista todavía hace es cancelar; cualquier otra acción
    # (incluida la vieja 'aprobar') es un no-op que solo redirige.
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

    response = cliente_autenticado.post(f'/reservas/{reserva.id}/aprobar/', {'accion': 'aprobar'})

    assert response.status_code == 302
    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Pendiente'


def test_cancelar_reserva_no_dispara_notificacion_de_aprobada(cliente_autenticado, laboratorio, monkeypatch):
    estado_pendiente = EstadoReserva.objects.get(nombre='Pendiente')
    reserva = Reserva.objects.create(
        fecha_reserva=datetime(2026, 8, 1, 8, 0),
        estado=estado_pendiente,
    )

    llamadas = []
    monkeypatch.setattr(
        'utils.notificaciones_email.notificar_reserva_creada_aprobada',
        lambda solicitud: llamadas.append(solicitud),
    )

    response = cliente_autenticado.post(f'/reservas/{reserva.id}/aprobar/', {'accion': 'cancelar'})

    assert response.status_code == 302
    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Cancelada'
    assert llamadas == []


# ── editar_insumos_reserva ────────────────────────────────────────────────

def test_editar_insumos_get_laboratorista_del_lab_ok(client, usuario_laboratorista, laboratorio):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    insumo = _insumo_con_stock('Vaso precipitado', 5, laboratorio)
    ReservaInsumo.objects.create(reserva=reserva, insumo=insumo, cantidad=2)
    client.force_login(usuario_laboratorista)

    response = client.get(f'/reservas/{reserva.id}/editar-insumos/')

    assert response.status_code == 200
    assert 'Vaso precipitado' in response.content.decode()


def test_editar_insumos_administrador_ok(cliente_autenticado, laboratorio):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)

    response = cliente_autenticado.get(f'/reservas/{reserva.id}/editar-insumos/')

    assert response.status_code == 200


def test_editar_insumos_laboratorista_de_otro_lab_es_rechazado(client, usuario_laboratorista, laboratorio):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    reserva = _reserva_aprobada_con_solicitud(otro_laboratorio)
    client.force_login(usuario_laboratorista)

    response = client.get(f'/reservas/{reserva.id}/editar-insumos/')

    assert response.status_code == 403


@pytest.mark.parametrize('nombre_estado', ['Pendiente', 'Cancelada', 'Expirada'])
def test_editar_insumos_rechaza_si_no_esta_aprobada(client, usuario_laboratorista, laboratorio, nombre_estado):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    reserva.estado = EstadoReserva.objects.get(nombre=nombre_estado)
    reserva.save()
    client.force_login(usuario_laboratorista)

    response = client.get(f'/reservas/{reserva.id}/editar-insumos/')

    assert response.status_code == 403


def test_editar_insumos_rechaza_si_existe_prestamo(client, usuario_laboratorista, usuario_admin, laboratorio):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    Prestamo.objects.create(
        reserva=reserva, responsable=usuario_admin,
        estado=EstadoPrestamo.objects.get(nombre='Activo'),
    )
    client.force_login(usuario_laboratorista)

    response = client.get(f'/reservas/{reserva.id}/editar-insumos/')

    assert response.status_code == 403


def test_editar_insumos_post_agrega_insumo_y_redirige(client, usuario_laboratorista, laboratorio):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    insumo = _insumo_con_stock('Vaso precipitado', 5, laboratorio)
    client.force_login(usuario_laboratorista)

    response = client.post(f'/reservas/{reserva.id}/editar-insumos/', {
        'insumos_ids': str(insumo.id),
        'insumos_cantidades': '3',
    })

    assert response.status_code == 302
    assert response.url == f'/reservas/{reserva.id}/'
    assert ReservaInsumo.objects.get(reserva=reserva, insumo=insumo).cantidad == 3


def test_editar_insumos_post_stock_insuficiente_muestra_error(client, usuario_laboratorista, laboratorio):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    insumo = _insumo_con_stock('Vaso precipitado', 2, laboratorio)
    client.force_login(usuario_laboratorista)

    response = client.post(f'/reservas/{reserva.id}/editar-insumos/', {
        'insumos_ids': str(insumo.id),
        'insumos_cantidades': '5',
    })

    assert response.status_code == 200
    assert 'Stock insuficiente' in response.content.decode()
    assert not ReservaInsumo.objects.filter(reserva=reserva, insumo=insumo).exists()


def test_editar_insumos_post_cantidad_menor_a_1_muestra_error(client, usuario_laboratorista, laboratorio):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    insumo = _insumo_con_stock('Vaso precipitado', 5, laboratorio)
    client.force_login(usuario_laboratorista)

    response = client.post(f'/reservas/{reserva.id}/editar-insumos/', {
        'insumos_ids': str(insumo.id),
        'insumos_cantidades': '0',
    })

    assert response.status_code == 200
    assert 'cantidad' in response.content.decode().lower()
    assert not ReservaInsumo.objects.filter(reserva=reserva, insumo=insumo).exists()


def test_editar_insumos_no_cambia_fecha_ni_laboratorio_aunque_se_envien_en_el_post(
    client, usuario_laboratorista, laboratorio,
):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    insumo = _insumo_con_stock('Vaso precipitado', 5, laboratorio)
    fecha_original = reserva.fecha_reserva
    client.force_login(usuario_laboratorista)

    response = client.post(f'/reservas/{reserva.id}/editar-insumos/', {
        'insumos_ids': str(insumo.id),
        'insumos_cantidades': '2',
        # Estos dos no son campos que la vista lea — probando que aunque se
        # envíen en el POST (p. ej. un cliente HTTP armado a mano), no hay
        # forma de que lleguen a tocar la Reserva ni su SolicitudReserva.
        'fecha_reserva': '2030-01-01T10:00',
        'laboratorio': otro_laboratorio.id,
    })

    assert response.status_code == 302
    reserva.refresh_from_db()
    assert reserva.fecha_reserva == fecha_original
    assert reserva.solicitud.first().laboratorio_id == laboratorio.id


def test_editar_insumos_dispara_email_al_estudiante(client, usuario_laboratorista, laboratorio, monkeypatch):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)
    insumo = _insumo_con_stock('Vaso precipitado', 5, laboratorio)
    client.force_login(usuario_laboratorista)

    llamadas = []
    monkeypatch.setattr(
        'utils.notificaciones_email.notificar_cambios_o_prestamo_listo',
        lambda reserva, tipo='cambios', **kwargs: llamadas.append(reserva),
    )

    response = client.post(f'/reservas/{reserva.id}/editar-insumos/', {
        'insumos_ids': str(insumo.id),
        'insumos_cantidades': '3',
    })

    assert response.status_code == 302
    assert llamadas == [reserva]
