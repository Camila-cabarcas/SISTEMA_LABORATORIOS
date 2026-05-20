from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Prestamo, PrestamoItem
from inventario.models import MovimientoInventario, TipoMovimiento, EstadoItem


@receiver(post_save, sender=PrestamoItem)
def registrar_movimiento_item(sender, instance, created, **kwargs):

    if not created:
        return

    tipo = TipoMovimiento.objects.get(nombre='Prestado')
    estado_prestado = EstadoItem.objects.get(nombre='Prestado')

    item = instance.item_inventario
    item.estado = estado_prestado
    item._desde_prestamo = True
    item.save()

    MovimientoInventario.objects.create(
        item_inventario=item,
        usuario=instance.prestamo.responsable,
        tipo_movimiento=tipo,
        observacion=f'Préstamo #{instance.prestamo.pk} - Activo'
    )


@receiver(post_save, sender=Prestamo)
def registrar_movimiento_estado(sender, instance, created, **kwargs):

    if created:
        return

    mapa_estados = {
        'DEVUELTO': ('Devuelto', 'Disponible'),
        'RETRASADO': ('Prestado', 'Prestado'),
    }

    estado_nombre = instance.estado.nombre.upper()

    if estado_nombre not in mapa_estados:
        return

    tipo_nombre, estado_item_nombre = mapa_estados[estado_nombre]
    tipo = TipoMovimiento.objects.get(nombre=tipo_nombre)
    estado_item = EstadoItem.objects.get(nombre=estado_item_nombre)

    items = PrestamoItem.objects.filter(prestamo=instance)

    for prestamo_item in items:

        item = prestamo_item.item_inventario
        item.estado = estado_item
        item._desde_prestamo = True
        item.save()

        MovimientoInventario.objects.create(
            item_inventario=item,
            usuario=instance.responsable,
            tipo_movimiento=tipo,
            observacion=f'Préstamo #{instance.pk} - {instance.estado.nombre}'
        )