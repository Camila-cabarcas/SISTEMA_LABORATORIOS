from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Prestamo, PrestamoItem
from inventario.models import MovimientoInventario, TipoMovimiento


@receiver(post_save, sender=Prestamo)
def registrar_movimiento(sender, instance, created, **kwargs):

    mapa_estados = {
        'ACTIVO': 'Prestado',
        'DEVUELTO': 'Devuelto',
        'RETRASADO': 'Prestado',
    }

    estado_nombre = instance.estado.nombre.upper()

    if estado_nombre not in mapa_estados:
        return

    tipo = TipoMovimiento.objects.get(
        nombre=mapa_estados[estado_nombre]
    )

    items = PrestamoItem.objects.filter(prestamo=instance)

    for prestamo_item in items:

        MovimientoInventario.objects.create(
            item_inventario=prestamo_item.item_inventario,
            usuario=instance.responsable,
            tipo_movimiento=tipo,
            observacion=f'Préstamo #{instance.pk} - {instance.estado.nombre}'
        )