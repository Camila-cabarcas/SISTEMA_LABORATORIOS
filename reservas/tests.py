"""
tests.py — reservas
Tests para clean() de Reserva y ReservaInsumo, y para la unicidad de
EstadoReserva.nombre (ver docs/auditoria_seguridad_codigo.md, CRÍTICO #4 —
el código llama EstadoReserva.objects.get(nombre='Aprobada') en decenas de
lugares; sin unique=True, una fila duplicada rompería todos con
MultipleObjectsReturned).
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.transaction import atomic
from django.test import TestCase
from django.utils import timezone

from inventario.models import Insumo
from reservas.models import EstadoReserva, Reserva, ReservaInsumo
from users.models import Usuario


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

    # -- Solapamiento con reserva aprobada --------------------------------

    def test_solapa_con_aprobada_del_mismo_usuario_es_invalida(self):
        usuario = Usuario.objects.create(username='user_solapa_test', codigo='SOL001')
        estado_aprobada = EstadoReserva.objects.create(nombre='Aprobada')
        inicio = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        Reserva.objects.create(
            usuario=usuario, estado=estado_aprobada,
            fecha_reserva=inicio, fecha_devolucion=inicio + timedelta(hours=2),  # 10:00-12:00
        )

        nueva = Reserva(
            usuario=usuario, estado=estado_aprobada,
            fecha_reserva=inicio + timedelta(hours=1),  # 11:00
            fecha_devolucion=inicio + timedelta(hours=3),  # 13:00 -> se solapa con 10:00-12:00
        )
        with self.assertRaises(ValidationError):
            nueva.full_clean()

    def test_no_solapa_horario_distinto_mismo_dia_es_valida(self):
        usuario = Usuario.objects.create(username='user_no_solapa_test', codigo='SOL002')
        estado_aprobada = EstadoReserva.objects.create(nombre='Aprobada')
        inicio = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        Reserva.objects.create(
            usuario=usuario, estado=estado_aprobada,
            fecha_reserva=inicio, fecha_devolucion=inicio + timedelta(hours=2),  # 10:00-12:00
        )

        nueva = Reserva(
            usuario=usuario, estado=estado_aprobada,
            fecha_reserva=inicio + timedelta(hours=2),  # 12:00
            fecha_devolucion=inicio + timedelta(hours=4),  # 14:00 -> no se solapa
        )
        nueva.full_clean()

    def test_solapa_con_pendiente_del_mismo_usuario_es_invalida(self):
        # El bloqueo también aplica contra reservas "Pendiente" (no solo
        # "Aprobada") — dos solicitudes del mismo usuario que se solapan no
        # deben poder coexistir aunque ninguna haya sido aprobada todavía.
        usuario = Usuario.objects.create(username='user_pendiente_test', codigo='SOL003')
        estado_pendiente = EstadoReserva.objects.create(nombre='Pendiente')
        inicio = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        Reserva.objects.create(
            usuario=usuario, estado=estado_pendiente,
            fecha_reserva=inicio, fecha_devolucion=inicio + timedelta(hours=2),
        )

        nueva = Reserva(
            usuario=usuario, estado=estado_pendiente,
            fecha_reserva=inicio + timedelta(hours=1),
            fecha_devolucion=inicio + timedelta(hours=3),
        )
        with self.assertRaises(ValidationError):
            nueva.full_clean()

    def test_solapa_con_aprobada_de_otro_usuario_no_bloquea(self):
        usuario_1 = Usuario.objects.create(username='user_a_test', codigo='SOL004')
        usuario_2 = Usuario.objects.create(username='user_b_test', codigo='SOL005')
        estado_aprobada = EstadoReserva.objects.create(nombre='Aprobada')
        inicio = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        Reserva.objects.create(
            usuario=usuario_1, estado=estado_aprobada,
            fecha_reserva=inicio, fecha_devolucion=inicio + timedelta(hours=2),
        )

        nueva = Reserva(
            usuario=usuario_2, estado=estado_aprobada,
            fecha_reserva=inicio + timedelta(hours=1),
            fecha_devolucion=inicio + timedelta(hours=3),
        )
        nueva.full_clean()

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


class EstadoReservaUnicidadTests(TestCase):

    def test_crear_dos_estados_con_el_mismo_nombre_lanza_integrity_error(self):
        EstadoReserva.objects.create(nombre='Aprobada')

        with self.assertRaises(IntegrityError):
            with atomic():
                EstadoReserva.objects.create(nombre='Aprobada')

        # La segunda fila nunca se creó — sigue habiendo exactamente una.
        self.assertEqual(EstadoReserva.objects.filter(nombre='Aprobada').count(), 1)

    def test_full_clean_tambien_rechaza_el_duplicado(self):
        # validate_unique() a nivel de Model.full_clean() (el camino que
        # usaría un ModelForm) también debe rechazarlo, con ValidationError
        # en vez de tocar la base de datos.
        EstadoReserva.objects.create(nombre='Cancelada')

        duplicado = EstadoReserva(nombre='Cancelada')
        with self.assertRaises(ValidationError):
            duplicado.full_clean()

    def test_get_por_nombre_sigue_devolviendo_un_unico_resultado(self):
        EstadoReserva.objects.create(nombre='Devuelta')

        # Sanity check de regresión: el patrón que usa el resto del sistema
        # (.get(nombre=...)) sigue funcionando normalmente para nombres que
        # sí son únicos — unique=True no rompe el caso feliz.
        encontrado = EstadoReserva.objects.get(nombre='Devuelta')
        self.assertEqual(encontrado.nombre, 'Devuelta')
