from django.db import models
from django.utils import timezone
from datetime import timedelta


class EstadoReserva(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre


class Reserva(models.Model):
    usuario = models.ForeignKey(
    'users.Usuario',
    on_delete=models.CASCADE,
    null=True,
    blank=True
)

    fecha_reserva = models.DateTimeField()

    hora_limite_retiro = models.DateTimeField(
        null=True,
        blank=True
    )

    fecha_devolucion = models.DateTimeField(
        null=True,
        blank=True
    )

    estado = models.ForeignKey(
        EstadoReserva,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.hora_limite_retiro = self.fecha_reserva + timedelta(minutes=30)
        if not self.fecha_devolucion:
            self.fecha_devolucion = self.fecha_reserva + timedelta(hours=2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Reserva {self.pk}"


class ReservaInsumo(models.Model):
    reserva = models.ForeignKey(
        'reservas.Reserva',
        on_delete=models.CASCADE
    )

    insumo = models.ForeignKey(
        'inventario.Insumo',
        on_delete=models.CASCADE
    )

    cantidad = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.insumo.nombre}"
    
