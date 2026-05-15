from django.db import models
from users.models import Usuario
from inventario.models import Insumo


class EstadoReserva(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre


class Reserva(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE
    )

    fecha_reserva = models.DateTimeField()

    estado = models.ForeignKey(
        EstadoReserva,
        on_delete=models.CASCADE
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reserva {self.id}"


class ReservaInsumo(models.Model):
    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.CASCADE
    )

    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.CASCADE
    )

    cantidad = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.insumo.nombre}"