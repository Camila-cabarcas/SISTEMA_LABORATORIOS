from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ItemInventario, MovimientoInventario, TipoMovimiento


@receiver(post_save, sender=ItemInventario)
def registrar_cambio_estado(sender, instance, created, **kwargs):

    if created:
        return

    # Evita loop cuando el signal de préstamos actualiza el ítem
    if getattr(instance, '_desde_prestamo', False):
        return

    mapa_estados = {
        'DAÑADO': 'Dañado',
        'MANTENIMIENTO': 'Mantenimiento',
        'BAJA': 'Baja',
    }

    estado_nombre = instance.estado.nombre.upper()

    if estado_nombre not in mapa_estados:
        return

    try:
        tipo = TipoMovimiento.objects.get(
            nombre=mapa_estados[estado_nombre]
        )

        MovimientoInventario.objects.create(
            item_inventario=instance,
            usuario=instance.updated_by,
            tipo_movimiento=tipo,
            observacion=f'Estado del ítem cambiado a {instance.estado.nombre}'
        )

    except Exception as e:
        print(f'ERROR en signal: {e}')