"""
Tests HTTP (Client) para prestamos/views.py.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from inventario.models import EstadoItem, ItemInventario
from prestamos.models import EstadoPrestamo, InspeccionItem, Prestamo
from reservas.models import EstadoReserva, Reserva, ReservaInsumo
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db


def _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', fecha_reserva=None):
    reserva = Reserva.objects.create(
        fecha_reserva=fecha_reserva or (timezone.now() - timedelta(minutes=5)),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva,
        reserva=reserva,
    )
    return reserva


def _prestamo_activo(reserva, responsable):
    return Prestamo.objects.create(
        reserva=reserva, responsable=responsable,
        estado=EstadoPrestamo.objects.get(nombre='Activo'),
    )


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


# ── Aislamiento por laboratorio (CRÍTICO #2 de la auditoría) ───────────────

def test_lista_prestamos_laboratorista_solo_ve_su_lab(client, usuario_laboratorista, usuario_admin, laboratorio):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    propio = _prestamo_activo(_reserva_aprobada_con_solicitud(laboratorio, cedula='111222333'), usuario_admin)
    ajeno = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio, cedula='999888777'), usuario_admin)
    client.force_login(usuario_laboratorista)

    response = client.get('/prestamos/')

    contenido = response.content.decode()
    assert propio.codigo in contenido
    assert ajeno.codigo not in contenido


def test_lista_prestamos_admin_ve_todos(cliente_autenticado, usuario_admin, laboratorio):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    de_un_lab = _prestamo_activo(_reserva_aprobada_con_solicitud(laboratorio, cedula='111222333'), usuario_admin)
    de_otro_lab = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio, cedula='999888777'), usuario_admin)

    response = cliente_autenticado.get('/prestamos/')

    contenido = response.content.decode()
    assert de_un_lab.codigo in contenido
    assert de_otro_lab.codigo in contenido


def test_detalle_prestamo_laboratorista_de_otro_lab_403(client, usuario_laboratorista, usuario_admin):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    ajeno = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio), usuario_admin)
    client.force_login(usuario_laboratorista)

    response = client.get(f'/prestamos/{ajeno.id}/')

    assert response.status_code == 403


def test_crear_prestamo_laboratorista_de_otro_lab_403(client, usuario_laboratorista, insumo):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    ajena = _reserva_aprobada_con_solicitud(otro_laboratorio)
    ReservaInsumo.objects.create(reserva=ajena, insumo=insumo, cantidad=1)
    item = ItemInventario.objects.create(
        codigo='ITEM-OTRO-LAB', insumo=insumo,
        estado=EstadoItem.objects.get(nombre='Disponible'),
        laboratorio=otro_laboratorio,
    )
    client.force_login(usuario_laboratorista)

    response = client.post(f'/prestamos/crear/{ajena.id}/', {'items': [item.id]})

    assert response.status_code == 403
    assert not Prestamo.objects.filter(reserva=ajena).exists()


def test_cambiar_estado_prestamo_laboratorista_de_otro_lab_403(client, usuario_laboratorista, usuario_admin):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    ajeno = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio), usuario_admin)
    client.force_login(usuario_laboratorista)

    response = client.get(f'/prestamos/{ajeno.id}/estado/')

    assert response.status_code == 403


def test_iniciar_inspeccion_laboratorista_de_otro_lab_403(client, usuario_laboratorista, usuario_admin):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    ajeno = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio), usuario_admin)
    client.force_login(usuario_laboratorista)

    response = client.post(f'/prestamos/{ajeno.id}/iniciar-inspeccion/')

    assert response.status_code == 403
    ajeno.refresh_from_db()
    assert ajeno.estado.nombre == 'Activo'


def test_marcar_devuelto_laboratorista_de_otro_lab_403(client, usuario_laboratorista, usuario_admin):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    ajeno = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio), usuario_admin)
    client.force_login(usuario_laboratorista)

    response = client.get(f'/prestamos/{ajeno.id}/marcar-devuelto/')

    assert response.status_code == 403


def test_admin_puede_ver_prestamo_de_cualquier_laboratorio(cliente_autenticado, usuario_admin):
    from laboratorio.models import Laboratorio

    otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
    prestamo = _prestamo_activo(_reserva_aprobada_con_solicitud(otro_laboratorio), usuario_admin)

    response = cliente_autenticado.get(f'/prestamos/{prestamo.id}/')

    assert response.status_code == 200
