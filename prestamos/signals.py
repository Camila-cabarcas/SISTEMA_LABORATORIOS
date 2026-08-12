"""
signals.py — prestamos
Dispara MutacionInventarioService al crear un PrestamoItem o al cambiar el
estado de un Prestamo. La lógica de negocio (qué cambia en el inventario y
por qué) vive en prestamos/services/mutacion_inventario_service.py — estas
señales solo conectan el ciclo de vida del modelo con esa llamada explícita,
no contienen lógica propia.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Prestamo, PrestamoItem
from .services.mutacion_inventario_service import MutacionInventarioService


@receiver(post_save, sender=PrestamoItem)
def al_crear_prestamo_item(sender, instance, created, **kwargs):
    if created:
        MutacionInventarioService.marcar_item_en_prestamo(instance)


@receiver(post_save, sender=Prestamo)
def al_cambiar_estado_prestamo(sender, instance, created, **kwargs):
    if not created:
        MutacionInventarioService.procesar_cambio_estado_prestamo(instance)
