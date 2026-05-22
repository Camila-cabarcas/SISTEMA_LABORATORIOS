from django.db import models

class TipoMovimiento(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre

class EstadoItem(models.Model):
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

    def cantidad_disponible(self):
        return self.items.filter(
            estado__nombre='Disponible'
        ).count()

    def stock_minimo_alcanzado(self):
        if self.stock_minimo == 0:
            return False
        return self.cantidad_disponible() <= self.stock_minimo

    def __str__(self):
        return self.nombre
    
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
    