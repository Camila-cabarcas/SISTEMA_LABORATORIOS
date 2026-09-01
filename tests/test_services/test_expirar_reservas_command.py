"""
Tests para el management command expirar_reservas
(reservas/management/commands/expirar_reservas.py).

Cubre específicamente que, bajo auto-aprobación, el comando SOLO expira
reservas "Pendiente" vencidas y NUNCA toca una reserva "Aprobada" vencida
— ver el docstring del comando sobre por qué dejó de hacerlo.
"""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from reservas.models import EstadoReserva, Reserva

pytestmark = pytest.mark.django_db


def _reserva(estado_nombre, horas_atras):
    fecha = timezone.now() - timedelta(hours=horas_atras)
    return Reserva.objects.create(
        fecha_reserva=fecha,
        estado=EstadoReserva.objects.get(nombre=estado_nombre),
    )


def test_expira_pendiente_vencida(catalogos):
    reserva = _reserva('Pendiente', horas_atras=2)

    call_command('expirar_reservas', stdout=StringIO())

    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Expirada'


def test_no_expira_pendiente_no_vencida(catalogos):
    reserva = _reserva('Pendiente', horas_atras=0)  # hora_limite_retiro en el futuro

    call_command('expirar_reservas', stdout=StringIO())

    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Pendiente'


def test_no_expira_aprobada_vencida(catalogos):
    # Caso central bajo auto-aprobación: toda reserva nace Aprobada, así que
    # si el comando siguiera tocando "Aprobada" cancelaría reservas
    # legítimas en uso en vez de solo las que quedaron Pendiente.
    reserva = _reserva('Aprobada', horas_atras=2)

    call_command('expirar_reservas', stdout=StringIO())

    reserva.refresh_from_db()
    assert reserva.estado.nombre == 'Aprobada'


def test_reporta_cantidad_en_stdout(catalogos):
    _reserva('Pendiente', horas_atras=2)
    _reserva('Pendiente', horas_atras=3)
    _reserva('Aprobada', horas_atras=2)  # no debe contarse

    salida = StringIO()
    call_command('expirar_reservas', stdout=salida)

    assert '2 reservas expiradas' in salida.getvalue()
