"""
models.py — prestamos
Define Prestamo, PrestamoItem y EstadoPrestamo, vinculados a una reserva aprobada y a ítems de inventario.
"""
from django.core.exceptions import ValidationError
from django.db import models
from users.models import Usuario
from reservas.models import Reserva
from inventario.models import ItemInventario


class EstadoPrestamo(models.Model):
    # unique=True: ver el mismo comentario en reservas.models.EstadoReserva —
    # el código depende de .get(nombre='Activo') (y equivalentes) en muchos
    # lugares; una fila duplicada rompería todos esos .get().
    nombre = models.CharField(max_length=50, unique=True)

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

    # Evita reenviar el aviso de atraso en cada corrida de
    # enviar_recordatorios_devolucion (que puede correr cada hora) — se pone
    # en True la primera vez que se notifica un atraso para este préstamo.
    email_atraso_enviado = models.BooleanField(default=False)

    ESTADOS_ACTIVOS = ['Activo', 'Retrasado', 'En Inspección']

    def clean(self):
        if self.fecha_devolucion and self.fecha_entrega and self.fecha_devolucion < self.fecha_entrega:
            raise ValidationError({
                'fecha_devolucion': 'La fecha de devolución no puede ser anterior a la fecha de entrega.'
            })

        if self.tiene_prestamo_activo():
            raise ValidationError(
                'Este usuario ya tiene un préstamo activo. No puede tener 2 préstamos simultáneos.'
            )

    def tiene_prestamo_activo(self):
        """True si el solicitante de self.reserva (identificado por su
        SolicitudReserva — usuario si es profesor, cédula si es estudiante)
        ya tiene otro préstamo sin devolver. Solo aplica a préstamos nuevos:
        cambiar el estado de un préstamo existente no debe autobloquearse."""
        if self.pk is not None or not self.reserva_id:
            return False

        solicitud = self.reserva.solicitud.first()
        if not solicitud:
            return False

        if solicitud.usuario_id:
            filtro = {'reserva__solicitud__usuario_id': solicitud.usuario_id}
        elif solicitud.cedula:
            filtro = {'reserva__solicitud__cedula': solicitud.cedula}
        else:
            return False

        return Prestamo.objects.filter(
            estado__nombre__in=self.ESTADOS_ACTIVOS, **filtro
        ).exists()

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

    def clean(self):
        if self.prestamo_id and self.item_inventario_id:
            ya_existe = PrestamoItem.objects.filter(
                prestamo_id=self.prestamo_id, item_inventario_id=self.item_inventario_id,
            ).exclude(pk=self.pk).exists()
            if ya_existe:
                raise ValidationError('Este ítem ya está en el préstamo.')

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

    def clean(self):
        if self.prestamo_item_id and self.prestamo_id:
            if self.prestamo_item.prestamo_id != self.prestamo_id:
                raise ValidationError('El ítem de préstamo no pertenece a este préstamo.')

    def __str__(self):
        return f"{self.prestamo_item} — {self.get_estado_inspeccion_display()}"