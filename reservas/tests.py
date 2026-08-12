"""
tests.py — reservas
Tests para clean() de Reserva y ReservaInsumo.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventario.models import Insumo
from reservas.models import EstadoReserva, Reserva, ReservaInsumo


class ModelosCleanValidationTests(TestCase):

    # -- Reserva --------------------------------------------------------

    def test_fecha_devolucion_posterior_a_fecha_reserva_es_valida(self):
        ahora = timezone.now()
        reserva = Reserva(fecha_reserva=ahora, fecha_devolucion=ahora + timedelta(hours=2))
        reserva.full_clean()

    def test_fecha_devolucion_anterior_o_igual_a_fecha_reserva_es_invalida(self):
        ahora = timezone.now()
        reserva = Reserva(fecha_reserva=ahora, fecha_devolucion=ahora)
        with self.assertRaises(ValidationError):
            reserva.full_clean()

    def test_fecha_devolucion_sin_asignar_no_lanza_error(self):
        # fecha_devolucion se calcula automáticamente en save(); antes de
        # guardar (o si se valida sin haberla seteado) no debe fallar.
        reserva = Reserva(fecha_reserva=timezone.now())
        reserva.full_clean()

    # -- ReservaInsumo ----------------------------------------------------

    def test_cantidad_positiva_es_valida(self):
        estado = EstadoReserva.objects.create(nombre='Pendiente')
        reserva = Reserva.objects.create(fecha_reserva=timezone.now(), estado=estado)
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')

        reserva_insumo = ReservaInsumo(reserva=reserva, insumo=insumo, cantidad=1)
        reserva_insumo.full_clean()

    def test_cantidad_cero_es_invalida(self):
        estado = EstadoReserva.objects.create(nombre='Pendiente')
        reserva = Reserva.objects.create(fecha_reserva=timezone.now(), estado=estado)
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')

        reserva_insumo = ReservaInsumo(reserva=reserva, insumo=insumo, cantidad=0)
        with self.assertRaises(ValidationError):
            reserva_insumo.full_clean()
