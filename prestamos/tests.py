"""
tests.py — prestamos
Prueba de FinalizarInspeccionService: un ítem marcado 'no_entregado' en la
inspección de devolución debe quedar en estado "Perdido" en ItemInventario
(antes no cambiaba de estado — ver inspeccionar_prestamo_service.py).

También prueba MutacionInventarioService (prestamos/services/
mutacion_inventario_service.py): la lógica que antes vivía implícita dentro
de prestamos/signals.py (post_save de PrestamoItem/Prestamo) y ahora es un
service explícito e invocable directamente, sin depender de que un signal
la dispare.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario, MovimientoInventario, TipoMovimiento
from laboratorio.models import Laboratorio
from prestamos.models import EstadoPrestamo, InspeccionItem, Prestamo, PrestamoItem
from prestamos.services.inspeccionar_prestamo_service import FinalizarInspeccionService
from prestamos.services.mutacion_inventario_service import MutacionInventarioService
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from users.models import Usuario


class FinalizarInspeccionServiceTests(TestCase):

    def setUp(self):
        self.estado_disponible = EstadoItem.objects.get_or_create(nombre='Disponible')[0]
        # 'Perdido' ya debería existir por la migración 0005_estadoitem_perdido,
        # pero get_or_create lo deja a salvo de depender de ese orden.
        self.estado_perdido = EstadoItem.objects.get_or_create(nombre='Perdido')[0]
        EstadoItem.objects.get_or_create(nombre='Prestado')

        # prestamos.signals crea un MovimientoInventario en cada paso (alta
        # de PrestamoItem, cambio de estado del Prestamo) y necesita estos
        # TipoMovimiento — no los crea ninguna migración ni seed_e2e, así
        # que el test los deja explícitos en vez de asumir que ya existen.
        TipoMovimiento.objects.get_or_create(nombre='Prestado')
        TipoMovimiento.objects.get_or_create(nombre='Devuelto')

        insumo = Insumo.objects.create(nombre='Multímetro de prueba', descripcion='Para tests')
        self.item = ItemInventario.objects.create(
            codigo='TEST-ITEM-001', insumo=insumo, estado=self.estado_disponible,
        )

        responsable = Usuario.objects.create(username='responsable_test')
        reserva = Reserva.objects.create(
            fecha_reserva=timezone.now(),
            estado=EstadoReserva.objects.get_or_create(nombre='Aprobada')[0],
        )
        self.prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )
        EstadoPrestamo.objects.get_or_create(nombre='Devuelto')

        self.prestamo_item = PrestamoItem.objects.create(
            prestamo=self.prestamo, item_inventario=self.item,
        )

    def test_item_no_entregado_queda_perdido(self):
        self.assertNotEqual(self.item.estado.nombre, 'Perdido')

        InspeccionItem.objects.create(
            prestamo=self.prestamo,
            prestamo_item=self.prestamo_item,
            estado_inspeccion='no_entregado',
        )

        FinalizarInspeccionService().finalizar(prestamo_id=self.prestamo.id)

        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Perdido')

    def test_item_bien_sigue_disponible(self):
        InspeccionItem.objects.create(
            prestamo=self.prestamo,
            prestamo_item=self.prestamo_item,
            estado_inspeccion='bien',
        )

        FinalizarInspeccionService().finalizar(prestamo_id=self.prestamo.id)

        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Disponible')


class MutacionInventarioServiceTests(TestCase):

    def setUp(self):
        self.estado_disponible = EstadoItem.objects.get_or_create(nombre='Disponible')[0]
        self.estado_prestado = EstadoItem.objects.get_or_create(nombre='Prestado')[0]
        self.estado_danado = EstadoItem.objects.get_or_create(nombre='Dañado')[0]

        TipoMovimiento.objects.get_or_create(nombre='Prestado')
        TipoMovimiento.objects.get_or_create(nombre='Devuelto')

        insumo = Insumo.objects.create(nombre='Osciloscopio de prueba', descripcion='Para tests')
        self.item = ItemInventario.objects.create(
            codigo='TEST-ITEM-100', insumo=insumo, estado=self.estado_disponible,
        )

        self.responsable = Usuario.objects.create(username='responsable_mutacion_test')
        reserva = Reserva.objects.create(
            fecha_reserva=timezone.now(),
            estado=EstadoReserva.objects.get_or_create(nombre='Aprobada')[0],
        )
        self.prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=self.responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )
        EstadoPrestamo.objects.get_or_create(nombre='Devuelto')
        EstadoPrestamo.objects.get_or_create(nombre='Retrasado')

        # Al crearlo, la señal ya dispara MutacionInventarioService.marcar_item_en_prestamo
        # (ver prestamos/signals.py) — es el camino real que usan las vistas.
        self.prestamo_item = PrestamoItem.objects.create(
            prestamo=self.prestamo, item_inventario=self.item,
        )

    # -- Crear PrestamoItem → item cambia estado (vía señal → service) -----

    def test_crear_prestamo_item_cambia_estado_a_prestado(self):
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Prestado')

    def test_crear_prestamo_item_registra_movimiento(self):
        movimiento = MovimientoInventario.objects.filter(
            item_inventario=self.item, tipo_movimiento__nombre='Prestado',
        ).first()
        assert movimiento is not None
        self.assertEqual(movimiento.usuario, self.responsable)

    def test_marcar_item_en_prestamo_es_invocable_directamente(self):
        # Se restablece el item a un estado distinto y se llama al service a
        # mano (sin volver a guardar el PrestamoItem, que dispararía la
        # señal) — confirma que la lógica es una función explícita y no solo
        # un efecto colateral de post_save.
        self.item.estado = self.estado_disponible
        self.item.save()

        item_actualizado = MutacionInventarioService.marcar_item_en_prestamo(self.prestamo_item)

        self.assertEqual(item_actualizado.estado.nombre, 'Prestado')

    # -- Devolver préstamo → item vuelve a disponible (vía señal → service) -

    def test_devolver_prestamo_libera_item_a_disponible(self):
        self.prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
        self.prestamo.save()

        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Disponible')

    def test_devolver_prestamo_registra_movimiento(self):
        self.prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
        self.prestamo.save()

        movimiento = MovimientoInventario.objects.filter(
            item_inventario=self.item, tipo_movimiento__nombre='Devuelto',
        ).first()
        self.assertIsNotNone(movimiento)

    def test_prestamo_retrasado_mantiene_item_prestado(self):
        self.prestamo.estado = EstadoPrestamo.objects.get(nombre='Retrasado')
        self.prestamo.save()

        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Prestado')

    def test_estado_prestamo_sin_mutacion_no_toca_inventario(self):
        # 'En Inspección' no está en el mapa de mutaciones: no debe crear
        # movimientos ni tocar el estado del item.
        EstadoPrestamo.objects.get_or_create(nombre='En Inspección')
        movimientos_antes = MovimientoInventario.objects.count()

        self.prestamo.estado = EstadoPrestamo.objects.get(nombre='En Inspección')
        self.prestamo.save()

        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Prestado')
        self.assertEqual(MovimientoInventario.objects.count(), movimientos_antes)

    def test_devolver_prestamo_con_inspeccion_no_sobreescribe_estado_del_item(self):
        # Si el préstamo ya pasó por inspección, el estado del item lo dejó
        # FinalizarInspeccionService (p.ej. 'Dañado') — procesar_cambio_estado_prestamo
        # no debe pisarlo con 'Disponible', pero sí debe registrar el movimiento.
        self.item.estado = self.estado_danado
        self.item._desde_prestamo = True
        self.item.save()
        InspeccionItem.objects.create(
            prestamo=self.prestamo,
            prestamo_item=self.prestamo_item,
            estado_inspeccion='danado',
        )

        self.prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
        self.prestamo.save()

        self.item.refresh_from_db()
        self.assertEqual(self.item.estado.nombre, 'Dañado')

        movimiento = MovimientoInventario.objects.filter(
            item_inventario=self.item, tipo_movimiento__nombre='Devuelto',
        ).first()
        self.assertIsNotNone(movimiento)

    def test_procesar_cambio_estado_prestamo_es_invocable_directamente(self):
        self.prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
        self.prestamo.save(update_fields=['estado'])
        # save() de arriba ya disparó la señal (item -> Disponible); lo
        # restablecemos a 'Prestado' para probar el service de forma
        # aislada, llamándolo directamente en vez de pasar por post_save.
        self.item.estado = self.estado_prestado
        self.item.save()

        items_afectados = MutacionInventarioService.procesar_cambio_estado_prestamo(self.prestamo)

        self.assertEqual(len(items_afectados), 1)
        self.assertEqual(items_afectados[0].estado.nombre, 'Disponible')


class ModelosCleanValidationTests(TestCase):
    """clean() de Prestamo, PrestamoItem e InspeccionItem."""

    def setUp(self):
        self.estado_disponible = EstadoItem.objects.get_or_create(nombre='Disponible')[0]
        # PrestamoItem.objects.create() dispara prestamos.signals, que
        # necesita estas filas de catálogo (ver MutacionInventarioServiceTests).
        EstadoItem.objects.get_or_create(nombre='Prestado')
        TipoMovimiento.objects.get_or_create(nombre='Prestado')
        TipoMovimiento.objects.get_or_create(nombre='Devuelto')
        self._contador_responsables = 0

    # -- Prestamo -----------------------------------------------------------

    def _crear_prestamo(self):
        from users.models import Usuario
        self._contador_responsables += 1
        responsable = Usuario.objects.create(
            username=f'responsable_clean_test_{self._contador_responsables}',
            codigo=f'RESP-CLEAN-{self._contador_responsables}',
        )
        reserva = Reserva.objects.create(
            fecha_reserva=timezone.now(),
            estado=EstadoReserva.objects.get_or_create(nombre='Aprobada')[0],
        )
        return Prestamo.objects.create(
            reserva=reserva, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )

    def test_fecha_devolucion_posterior_a_entrega_es_valida(self):
        prestamo = self._crear_prestamo()
        prestamo.fecha_devolucion = prestamo.fecha_entrega + timedelta(hours=1)
        prestamo.full_clean()

    def test_fecha_devolucion_anterior_a_entrega_es_invalida(self):
        prestamo = self._crear_prestamo()
        prestamo.fecha_devolucion = prestamo.fecha_entrega - timedelta(hours=1)
        with self.assertRaises(ValidationError):
            prestamo.full_clean()

    def _crear_reserva_con_solicitud(self, cedula):
        """A diferencia de _crear_prestamo (cuya Reserva no tiene
        SolicitudReserva asociada), esta sí — es lo que tiene_prestamo_activo()
        usa para identificar al solicitante de un préstamo nuevo."""
        laboratorio = Laboratorio.objects.get_or_create(
            nombre='Lab Clean Test', defaults={'ubicacion': 'X'},
        )[0]
        reserva = Reserva.objects.create(
            fecha_reserva=timezone.now(),
            estado=EstadoReserva.objects.get_or_create(nombre='Aprobada')[0],
        )
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante',
            cedula=cedula,
            laboratorio=laboratorio,
            fecha_reserva=timezone.now(),
            reserva=reserva,
        )
        return reserva

    def test_prestamo_activo_bloquea_segundo(self):
        responsable = Usuario.objects.create(username='responsable_activo_test')
        reserva_1 = self._crear_reserva_con_solicitud('111222333')
        Prestamo.objects.create(
            reserva=reserva_1, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )

        reserva_2 = self._crear_reserva_con_solicitud('111222333')
        segundo_prestamo = Prestamo(
            reserva=reserva_2, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )

        with self.assertRaises(ValidationError):
            segundo_prestamo.full_clean()

    def test_prestamo_de_otro_usuario_no_se_bloquea(self):
        responsable = Usuario.objects.create(username='responsable_otro_test')
        reserva_1 = self._crear_reserva_con_solicitud('111222333')
        Prestamo.objects.create(
            reserva=reserva_1, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )

        reserva_2 = self._crear_reserva_con_solicitud('999888777')
        otro_prestamo = Prestamo(
            reserva=reserva_2, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )

        otro_prestamo.full_clean()

    def test_prestamo_activo_no_bloquea_tras_devolucion(self):
        responsable = Usuario.objects.create(username='responsable_devuelto_test')
        reserva_1 = self._crear_reserva_con_solicitud('111222333')
        prestamo_1 = Prestamo.objects.create(
            reserva=reserva_1, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )
        prestamo_1.estado = EstadoPrestamo.objects.get_or_create(nombre='Devuelto')[0]
        prestamo_1.save()

        reserva_2 = self._crear_reserva_con_solicitud('111222333')
        nuevo_prestamo = Prestamo(
            reserva=reserva_2, responsable=responsable,
            estado=EstadoPrestamo.objects.get_or_create(nombre='Activo')[0],
        )

        nuevo_prestamo.full_clean()

    # -- PrestamoItem -------------------------------------------------------

    def test_item_no_duplicado_en_prestamo_es_valido(self):
        prestamo = self._crear_prestamo()
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario.objects.create(
            codigo='ITEM-CLEAN-001', insumo=insumo, estado=self.estado_disponible,
        )
        prestamo_item = PrestamoItem(prestamo=prestamo, item_inventario=item)
        prestamo_item.full_clean()

    def test_item_duplicado_en_mismo_prestamo_es_invalido(self):
        prestamo = self._crear_prestamo()
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario.objects.create(
            codigo='ITEM-CLEAN-002', insumo=insumo, estado=self.estado_disponible,
        )
        PrestamoItem.objects.create(prestamo=prestamo, item_inventario=item)

        duplicado = PrestamoItem(prestamo=prestamo, item_inventario=item)
        with self.assertRaises(ValidationError):
            duplicado.full_clean()

    def test_actualizar_el_mismo_prestamo_item_no_falla(self):
        prestamo = self._crear_prestamo()
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario.objects.create(
            codigo='ITEM-CLEAN-003', insumo=insumo, estado=self.estado_disponible,
        )
        prestamo_item = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=item)

        prestamo_item.full_clean()

    # -- InspeccionItem -----------------------------------------------------

    def test_inspeccion_de_item_del_mismo_prestamo_es_valida(self):
        prestamo = self._crear_prestamo()
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario.objects.create(
            codigo='ITEM-CLEAN-004', insumo=insumo, estado=self.estado_disponible,
        )
        prestamo_item = PrestamoItem.objects.create(prestamo=prestamo, item_inventario=item)

        inspeccion = InspeccionItem(prestamo=prestamo, prestamo_item=prestamo_item)
        inspeccion.full_clean()

    def test_inspeccion_de_item_de_otro_prestamo_es_invalida(self):
        prestamo_1 = self._crear_prestamo()
        prestamo_2 = self._crear_prestamo()
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario.objects.create(
            codigo='ITEM-CLEAN-005', insumo=insumo, estado=self.estado_disponible,
        )
        prestamo_item_de_1 = PrestamoItem.objects.create(prestamo=prestamo_1, item_inventario=item)

        inspeccion_cruzada = InspeccionItem(prestamo=prestamo_2, prestamo_item=prestamo_item_de_1)
        with self.assertRaises(ValidationError):
            inspeccion_cruzada.full_clean()
