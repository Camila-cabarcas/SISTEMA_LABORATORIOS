"""
models.py — prestamos
Define Prestamo, PrestamoItem y EstadoPrestamo, vinculados a una reserva aprobada y a ítems de inventario.
"""
from django.db import models
from users.models import Usuario
from reservas.models import Reserva
from inventario.models import ItemInventario


class EstadoPrestamo(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre


class Prestamo(models.Model):
    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.CASCADE
    )

    responsable = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE
    )

    estado = models.ForeignKey(
        EstadoPrestamo,
        on_delete=models.CASCADE
    )

    fecha_entrega = models.DateTimeField(auto_now_add=True)

    fecha_devolucion = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Prestamo {self.pk}"


class PrestamoItem(models.Model):
    prestamo = models.ForeignKey(
        Prestamo,
        on_delete=models.CASCADE
    )

    item_inventario = models.ForeignKey(
        ItemInventario,
        on_delete=models.CASCADE
    )

    def __str__(self):
        return self.item_inventario.codigo