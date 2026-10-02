"""
models.py — inventario
Define Insumo, ItemInventario, MovimientoInventario y los modelos de estado (EstadoItem, EstadoInsumo, TipoMovimiento).
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

class TipoMovimiento(models.Model):
    # unique=True: ver el comentario en reservas.models.EstadoReserva — el
    # código depende de .get(nombre='Prestado') (y equivalentes) en varios
    # lugares; una fila duplicada rompería esos .get().
    nombre = models.CharField(max_length=50, unique=True)

    # Nombre visible para el usuario. Solo presentación: `nombre` NO se
    # renombra en la BD porque el código lo busca literal (.get(nombre=...)
    # en prestamos/services/mutacion_inventario_service.py, inventario/
    # signals.py, crear_insumos_por_lab...). Tipos no listados se muestran
    # con su nombre tal cual.
    ETIQUETAS = {
        'Registro inicial': 'Creación',
        'Prestado':         'Préstamo',
        'Devuelto':         'Devolución',
        'Dañado':           'Reporte de daño',
        'Mantenimiento':    'Envío a mantenimiento',
        'Baja':             'Baja del inventario',
    }

    @classmethod
    def etiqueta_de(cls, nombre):
        return cls.ETIQUETAS.get(nombre, nombre)

    @property
    def etiqueta(self):
        return self.etiqueta_de(self.nombre)

    def __str__(self):
        return self.nombre

class EstadoItem(models.Model):
    # unique=True: mismo motivo — .get(nombre='Disponible') se usa en
    # decenas de lugares (validar préstamos, listar stock, etc.).
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre

class EstadoInsumo(models.Model):
    # unique=True: mismo motivo que los estados de arriba.
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    # Antes unique=True a secas: un mismo nombre ("Multímetro", "Cables...")
    # es realista en más de un laboratorio, así que la unicidad ahora es por
    # (nombre, laboratorio) — ver Meta.constraints. laboratorio es opcional
    # (null=True) para no romper insumos existentes que no pertenecen a
    # ninguno en particular.
    nombre = models.CharField(max_length=100)

    laboratorio = models.ForeignKey(
        'laboratorio.Laboratorio',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='insumos',
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['nombre', 'laboratorio'],
                name='insumo_nombre_laboratorio_unico',
            ),
        ]

    def _items_activos(self):
        """Ítems no eliminados (soft-delete) de este insumo — misma base que
        ItemInventario.activos, ver su comentario."""
        return self.items.filter(deleted_at__isnull=True)

    def cantidad_disponible(self):
        return self._items_activos().filter(estado__nombre='Disponible').count()

    # Alias explícito pedido por el diagnóstico de stock — mismo resultado
    # que cantidad_disponible(): "Total - Prestados - Dañados - Perdidos" es
    # matemáticamente lo mismo que contar directo los 'Disponible', porque
    # ItemInventario.estado es un FK obligatorio y esos 4 estados particionan
    # el conjunto de ítems activos (cada ítem está en exactamente uno).
    def stock_disponible(self):
        return self.cantidad_disponible()

    def stock_total(self):
        return self._items_activos().count()

    def stock_prestado(self):
        return self._items_activos().filter(estado__nombre='Prestado').count()

    def stock_danado(self):
        return self._items_activos().filter(estado__nombre='Dañado').count()

    def stock_perdido(self):
        return self._items_activos().filter(estado__nombre='Perdido').count()

    def stock_minimo_alcanzado(self):
        if self.stock_minimo == 0:
            return False
        return self.cantidad_disponible() <= self.stock_minimo

    def clean(self):
        if self.stock_minimo is not None and self.stock_minimo < 0:
            raise ValidationError({'stock_minimo': 'El stock mínimo no puede ser negativo.'})

    def __str__(self):
        if self.laboratorio_id:
            return f"{self.nombre} ({self.laboratorio.nombre})"
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

    def clean(self):
        if self.codigo is not None and not self.codigo.strip():
            raise ValidationError({'codigo': 'El código no puede estar vacío.'})

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
    