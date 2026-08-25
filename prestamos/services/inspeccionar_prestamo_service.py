"""
inspeccionar_prestamo_service.py — prestamos
Orquesta el flujo de inspección de devolución: abrir la inspección (crear los
registros InspeccionItem) y finalizarla (actualizar inventario y marcar el
préstamo como Devuelto).
"""
import logging

from django.core.exceptions import ValidationError
from django.utils import timezone

from inventario.models import EstadoItem
from prestamos.models import Prestamo, PrestamoItem, InspeccionItem, EstadoPrestamo

logger = logging.getLogger(__name__)


class InspeccionarPrestamoService:

    def iniciar_inspeccion(self, prestamo_id, usuario=None):
        inspector = getattr(usuario, 'email', None)
        logger.info(f"InspeccionarPrestamoService.iniciar_inspeccion | prestamo_id={prestamo_id} | usuario={inspector}")

        try:
            prestamo = Prestamo.objects.get(id=prestamo_id)

            prestamo.estado = EstadoPrestamo.objects.get(nombre='En Inspección')
            prestamo.save()

            items = PrestamoItem.objects.filter(prestamo=prestamo)
            for item in items:
                InspeccionItem.objects.get_or_create(
                    prestamo=prestamo,
                    prestamo_item=item,
                    defaults={
                        'estado_inspeccion': 'bien',
                        'inspector': usuario,
                    }
                )

            logger.info(f"InspeccionarPrestamoService.iniciar_inspeccion | prestamo_id={prestamo_id} | estado=En Inspección | items={items.count()}")

            return prestamo
        except Exception as e:
            logger.error(f"Error en InspeccionarPrestamoService.iniciar_inspeccion | {str(e)} | prestamo_id={prestamo_id}")
            raise


class FinalizarInspeccionService:

    def finalizar(self, prestamo_id, inspecciones_dict=None):
        logger.info(f"FinalizarInspeccionService.finalizar | prestamo_id={prestamo_id}")

        try:
            prestamo = Prestamo.objects.get(id=prestamo_id)

            if inspecciones_dict is None:
                inspecciones = list(
                    InspeccionItem.objects.filter(prestamo=prestamo).select_related(
                        'prestamo_item__item_inventario__insumo'
                    )
                )
            else:
                inspecciones = list(inspecciones_dict.values())

            items_prestamo_ids = set(
                PrestamoItem.objects.filter(prestamo=prestamo).values_list('id', flat=True)
            )
            items_inspeccionados_ids = {insp.prestamo_item_id for insp in inspecciones}

            if items_inspeccionados_ids != items_prestamo_ids:
                raise ValidationError(
                    'Todos los ítems del préstamo deben estar inspeccionados antes de finalizar.'
                )

            estado_disponible = EstadoItem.objects.filter(nombre='Disponible').first()
            estado_danado = EstadoItem.objects.filter(nombre='Dañado').first()
            estado_perdido = EstadoItem.objects.filter(nombre='Perdido').first()

            for inspeccion in inspecciones:
                item_inventario = inspeccion.prestamo_item.item_inventario
                if inspeccion.estado_inspeccion == 'bien' and estado_disponible:
                    item_inventario.estado = estado_disponible
                    item_inventario.save()
                elif inspeccion.estado_inspeccion == 'danado' and estado_danado:
                    item_inventario.estado = estado_danado
                    item_inventario.save()
                elif inspeccion.estado_inspeccion == 'no_entregado' and estado_perdido:
                    item_inventario.estado = estado_perdido
                    item_inventario.save()
                    logger.info(
                        f"FinalizarInspeccionService.finalizar | "
                        f"item {item_inventario.codigo} marcado como Perdido | "
                        f"prestamo_id={prestamo_id}"
                    )

            prestamo.estado = EstadoPrestamo.objects.get(nombre='Devuelto')
            prestamo.fecha_devolucion = timezone.now()
            prestamo.save()

            resumen = {
                'bien': sum(1 for i in inspecciones if i.estado_inspeccion == 'bien'),
                'danado': sum(1 for i in inspecciones if i.estado_inspeccion == 'danado'),
                'no_entregado': sum(1 for i in inspecciones if i.estado_inspeccion == 'no_entregado'),
            }

            logger.info(f"FinalizarInspeccionService.finalizar | prestamo_id={prestamo_id} | estado=Devuelto | resumen={resumen}")

            try:
                from utils.notificaciones_email import notificar_devolucion_completada
                notificar_devolucion_completada(prestamo, inspecciones)
            except Exception:
                logger.exception(
                    "FinalizarInspeccionService.finalizar | error notificando devolución | prestamo_id=%s",
                    prestamo_id,
                )

            return {'prestamo': prestamo, 'resumen': resumen}
        except Exception as e:
            logger.error(f"Error en FinalizarInspeccionService.finalizar | {str(e)} | prestamo_id={prestamo_id}")
            raise
