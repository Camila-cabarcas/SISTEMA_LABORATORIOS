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

    def __str__(self):
        return self.nombre


class ItemInventario(models.Model):
    codigo = models.CharField(max_length=50, unique=True)

    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.CASCADE
    )

    estado = models.ForeignKey(
        EstadoItem,
        on_delete=models.CASCADE
    )

    fecha_registro = models.DateTimeField(auto_now_add=True)

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
    