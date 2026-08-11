"""
tests.py — prestamos
Prueba de FinalizarInspeccionService: un ítem marcado 'no_entregado' en la
inspección de devolución debe quedar en estado "Perdido" en ItemInventario
(antes no cambiaba de estado — ver inspeccionar_prestamo_service.py).
"""
from django.test import TestCase
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario, TipoMovimiento
from prestamos.models import EstadoPrestamo, InspeccionItem, Prestamo, PrestamoItem
from prestamos.services.inspeccionar_prestamo_service import FinalizarInspeccionService
from reservas.models import EstadoReserva, Reserva
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
