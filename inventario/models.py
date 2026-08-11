"""
models.py — inventario
Define Insumo, ItemInventario, MovimientoInventario y los modelos de estado (EstadoItem, EstadoInsumo, TipoMovimiento).
"""
from django.db import models
from django.utils import timezone

class TipoMovimiento(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre

class EstadoItem(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre
    
class EstadoInsumo(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    nombre = models.CharField(
        max_length=100,
        unique=True
    )

    descripcion = models.TextField(
        blank=False
    )

    marca = models.CharField(
        max_length=100,
        blank=True
    )

    stock_minimo = models.IntegerField(default=0)

    estado = models.ForeignKey(
        EstadoInsumo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    def cantidad_disponible(self):
        return self.items.filter(
            estado__nombre='Disponible',
            deleted_at__isnull=True,
        ).count()

    def stock_minimo_alcanzado(self):
        if self.stock_minimo == 0:
            return False
        return self.cantidad_disponible() <= self.stock_minimo

    def __str__(self):
        return self.nombre

    
class ItemInventarioActivoManager(models.Manager):
    """Solo ítems NO eliminados (soft-delete) — usar ItemInventario.activos
    en cualquier lugar que seleccione ítems para uso real (listas, formularios
    de préstamo, conteos de disponibilidad). `objects` sigue trayendo TODO,
    incluidos los eliminados, para auditoría/historial (p.ej. historial_item)."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class ItemInventario(models.Model):
    codigo = models.CharField(max_length=50, unique=True)

    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.CASCADE,
        related_name='items'
    )

    estado = models.ForeignKey(
        EstadoItem,
        on_delete=models.CASCADE
    )

    laboratorio = models.ForeignKey(
        'laboratorio.Laboratorio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)

    updated_by = models.ForeignKey(
        'users.Usuario',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    # Soft-delete: marcar eliminado sin borrar filas (PrestamoItem e
    # InspeccionItem cuelgan de este ítem con on_delete=CASCADE — borrarlo
    # de verdad se llevaría por delante el historial de préstamos).
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()       # todos, incluidos los eliminados (auditoría/historial)
    activos = ItemInventarioActivoManager()  # solo no eliminados (listas, selección para préstamos)

    def soft_delete(self):
        """Marca el ítem como eliminado sin borrar la fila ni su historial."""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def is_deleted(self):
        return self.deleted_at is not None

    def __str__(self):
        return self.codigo
    
class MovimientoInventario(models.Model):

    item_inventario = models.ForeignKey(
        ItemInventario,
        on_delete=models.CASCADE
    )

    usuario = models.ForeignKey(
        'users.Usuario',
        on_delete=models.CASCADE
    )

    tipo_movimiento = models.ForeignKey(
    TipoMovimiento,
    on_delete=models.CASCADE
)

    fecha = models.DateTimeField(auto_now_add=True)

    observacion = models.TextField(blank=True)

    def __str__(self):
        return self.tipo_movimiento.nombre
    