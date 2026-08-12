"""
mutacion_inventario_service.py — prestamos
Mueve a un service explícito las mutaciones de ItemInventario (cambio de
estado + registro de MovimientoInventario) que antes vivían implícitas
dentro de prestamos/signals.py, disparadas por post_save de PrestamoItem y
Prestamo. Las señales siguen existiendo como disparador (para no romper el
flujo actual de vistas, que solo hacen .save()/.create()), pero ahora solo
llaman a estos métodos — la lógica es explícita, invocable directamente y
testeable sin depender de que un post_save la dispare.
"""
import logging

from inventario.models import EstadoItem, MovimientoInventario, TipoMovimiento
from prestamos.models import InspeccionItem, PrestamoItem

logger = logging.getLogger(__name__)

MAPA_ESTADOS_PRESTAMO = {
    'DEVUELTO': ('Devuelto', 'Disponible'),
    'RETRASADO': ('Prestado', 'Prestado'),
}


class MutacionInventarioService:
    """Cambios de estado de ItemInventario y su registro de auditoría
    (MovimientoInventario) causados por el ciclo de vida de un préstamo."""

    @staticmethod
    def marcar_item_en_prestamo(prestamo_item):
        """
        Al crear un PrestamoItem: el ítem pasa a 'Prestado' y se registra el
        movimiento de entrega.

        Args:
            prestamo_item: PrestamoItem ya guardado.

        Returns:
            ItemInventario: el ítem, ya actualizado.
        """
        item = prestamo_item.item_inventario
        estado_prestado = EstadoItem.objects.get(nombre='Prestado')
        tipo = TipoMovimiento.objects.get(nombre='Prestado')

        item.estado = estado_prestado
        item._desde_prestamo = True
        item.save()

        MovimientoInventario.objects.create(
            item_inventario=item,
            usuario=prestamo_item.prestamo.responsable,
            tipo_movimiento=tipo,
            observacion=f'Préstamo #{prestamo_item.prestamo.pk} - Activo',
        )

        logger.info(
            "MutacionInventarioService.marcar_item_en_prestamo | item=%s | prestamo_id=%s",
            item.codigo, prestamo_item.prestamo_id,
        )

        return item

    @staticmethod
    def procesar_cambio_estado_prestamo(prestamo):
        """
        Al cambiar el estado de un Prestamo a Devuelto o Retrasado: actualiza
        el estado de cada ítem prestado y registra el movimiento
        correspondiente. Si el préstamo ya pasó por inspección (existe algún
        InspeccionItem para él), el estado de cada ítem ya fue asignado
        individualmente por FinalizarInspeccionService y no se sobreescribe
        aquí — solo se registra el movimiento de auditoría.

        Para cualquier otro estado del préstamo (Activo, En Inspección, ...)
        no hace nada: no todo cambio de estado de un préstamo mueve
        inventario.

        Args:
            prestamo: Prestamo ya guardado, con su estado actualizado.

        Returns:
            list[ItemInventario]: los ítems afectados (vacío si el estado del
            préstamo no dispara ninguna mutación de inventario).
        """
        estado_nombre = prestamo.estado.nombre.upper()
        if estado_nombre not in MAPA_ESTADOS_PRESTAMO:
            return []

        tipo_nombre, estado_item_nombre = MAPA_ESTADOS_PRESTAMO[estado_nombre]
        tipo = TipoMovimiento.objects.get(nombre=tipo_nombre)
        estado_item = EstadoItem.objects.get(nombre=estado_item_nombre)

        tiene_inspeccion = (
            estado_nombre == 'DEVUELTO'
            and InspeccionItem.objects.filter(prestamo=prestamo).exists()
        )

        items_afectados = []
        for prestamo_item in PrestamoItem.objects.filter(prestamo=prestamo):
            item = prestamo_item.item_inventario

            if not tiene_inspeccion:
                item.estado = estado_item
                item._desde_prestamo = True
                item.save()

            MovimientoInventario.objects.create(
                item_inventario=item,
                usuario=prestamo.responsable,
                tipo_movimiento=tipo,
                observacion=f'Préstamo #{prestamo.pk} - {prestamo.estado.nombre}',
            )
            items_afectados.append(item)

        logger.info(
            "MutacionInventarioService.procesar_cambio_estado_prestamo | prestamo_id=%s | "
            "estado=%s | items=%s | tiene_inspeccion=%s",
            prestamo.pk, prestamo.estado.nombre, len(items_afectados), tiene_inspeccion,
        )

        return items_afectados
