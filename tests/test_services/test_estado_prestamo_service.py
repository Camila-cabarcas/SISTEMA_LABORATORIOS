"""
Tests para ObtenerEstadoPrestamoService (reservas/services/estado_prestamo_service.py).
"""
import pytest
from django.utils import timezone

from prestamos.models import EstadoPrestamo
from reservas.models import EstadoReserva, Reserva
from reservas.services.estado_prestamo_service import ObtenerEstadoPrestamoService

pytestmark = pytest.mark.django_db


def test_sin_prestamo(catalogos):
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now(),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )

    resultado = ObtenerEstadoPrestamoService.obtener(reserva)

    assert resultado['tipo'] == ObtenerEstadoPrestamoService.SIN_PRESTAMO
    assert resultado['prestamo'] is None


def test_prestamo_activo(reserva_con_prestamo):
    resultado = ObtenerEstadoPrestamoService.obtener(reserva_con_prestamo.reserva)

    assert resultado['tipo'] == ObtenerEstadoPrestamoService.ACTIVO
    assert resultado['prestamo'] == reserva_con_prestamo.prestamo


def test_prestamo_en_inspeccion_cae_en_bucket_activo(reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo
    prestamo.estado = EstadoPrestamo.objects.get(nombre='En Inspección')
    prestamo.save()

    resultado = ObtenerEstadoPrestamoService.obtener(reserva_con_prestamo.reserva)

    assert resultado['tipo'] == ObtenerEstadoPrestamoService.ACTIVO
    assert resultado['prestamo'].estado.nombre == 'En Inspección'


def test_prestamo_devuelto(reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo
    prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
    prestamo.save()

    resultado = ObtenerEstadoPrestamoService.obtener(reserva_con_prestamo.reserva)

    assert resultado['tipo'] == ObtenerEstadoPrestamoService.DEVUELTO
    assert resultado['prestamo'] == prestamo


def test_prestamo_retrasado(reserva_con_prestamo):
    prestamo = reserva_con_prestamo.prestamo
    prestamo.estado = EstadoPrestamo.objects.get(nombre='Retrasado')
    prestamo.save()

    resultado = ObtenerEstadoPrestamoService.obtener(reserva_con_prestamo.reserva)

    assert resultado['tipo'] == ObtenerEstadoPrestamoService.RETRASADO
    assert resultado['prestamo'] == prestamo
