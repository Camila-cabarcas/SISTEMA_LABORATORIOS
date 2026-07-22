"""
Tests para CrearReservaService (reservas/services/crear_reserva_service.py).
"""
import pytest
from django.core.exceptions import ValidationError

from laboratorio.models import Modulo
from reservas.models import Reserva
from reservas.services.crear_reserva_service import CrearReservaService

pytestmark = pytest.mark.django_db


def test_ejecutar_exitoso(solicitud_valida, usuario_admin):
    reserva = CrearReservaService().ejecutar(
        solicitud_id=solicitud_valida.id,
        usuario=usuario_admin,
    )

    assert isinstance(reserva, Reserva)
    solicitud_valida.refresh_from_db()
    assert solicitud_valida.reserva_id == reserva.id


def test_solicitud_no_existe(usuario_admin):
    with pytest.raises(ValidationError):
        CrearReservaService().ejecutar(solicitud_id=999999, usuario=usuario_admin)


def test_solicitud_ya_tiene_reserva(solicitud_valida, usuario_admin):
    CrearReservaService().ejecutar(solicitud_id=solicitud_valida.id, usuario=usuario_admin)
    solicitud_valida.refresh_from_db()

    with pytest.raises(ValidationError):
        CrearReservaService().ejecutar(solicitud_id=solicitud_valida.id, usuario=usuario_admin)


def test_asignar_modulos(solicitud_valida, usuario_admin, laboratorio):
    solicitud_valida.necesita_modulo = True
    solicitud_valida.save()
    modulo = Modulo.objects.create(nombre='Módulo 1', capacidad=4, laboratorio=laboratorio)

    CrearReservaService().ejecutar(
        solicitud_id=solicitud_valida.id,
        usuario=usuario_admin,
        modulos_ids=[modulo.id],
    )

    solicitud_valida.refresh_from_db()
    assert list(solicitud_valida.modulos_asignados.all()) == [modulo]


def test_usuario_respaldo(solicitud_valida, usuario_admin):
    assert solicitud_valida.usuario is None

    reserva = CrearReservaService().ejecutar(
        solicitud_id=solicitud_valida.id,
        usuario=usuario_admin,
    )

    assert reserva.usuario_id == usuario_admin.id


def test_reserva_marcada_como_aprobada(solicitud_valida, usuario_admin):
    reserva = CrearReservaService().ejecutar(
        solicitud_id=solicitud_valida.id,
        usuario=usuario_admin,
    )

    assert reserva.estado.nombre == 'Aprobada'
