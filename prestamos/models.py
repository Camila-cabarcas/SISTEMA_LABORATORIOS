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

    codigo = models.CharField(max_length=50, unique=True, blank=True, default='')

    fecha_entrega = models.DateTimeField(auto_now_add=True)

    fecha_devolucion = models.DateTimeField(
        null=True,
        blank=True
    )

    def generar_codigo(self):
        from solicitudes.models import SolicitudReserva
        solicitud = self.reserva.solicitud.first()
        cedula = solicitud.cedula if solicitud else 'SIN'

        lab = None
        if solicitud and solicitud.laboratorio:
            lab = solicitud.laboratorio.nombre
        elif self.reserva and self.reserva.solicitud.first():
            lab = 'LAB'

        # Abreviar nombre del laboratorio (primeras letras de cada palabra)
        if lab:
            siglas = ''.join(
                word[0].upper()
                for word in lab.split()
                if word
            )[:6]
        else:
            siglas = 'LAB'

        numero = str(self.id).zfill(3)
        return f"{cedula}-{siglas}-P{numero}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = self.generar_codigo()
            super().save(update_fields=['codigo'])

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


class InspeccionItem(models.Model):

    ESTADO_CHOICES = [
        ('bien', 'Bien'),
        ('danado', 'Dañado'),
        ('no_entregado', 'No entregado'),
    ]

    prestamo = models.ForeignKey(
        Prestamo,
        on_delete=models.CASCADE,
        related_name='inspecciones'
    )

    prestamo_item = models.ForeignKey(
        PrestamoItem,
        on_delete=models.CASCADE,
        related_name='inspecciones'
    )

    estado_inspeccion = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='bien'
    )

    observaciones = models.TextField(blank=True, default='')

    inspector = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    fecha_inspeccion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_inspeccion']

    def __str__(self):
        return f"{self.prestamo_item} — {self.get_estado_inspeccion_display()}"