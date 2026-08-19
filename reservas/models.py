"""
models.py — reservas
Define Reserva, ReservaInsumo y EstadoReserva; calcula hora_limite_retiro y fecha_devolucion al guardar.
"""
from django.core.exceptions import ValidationError
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

    codigo = models.CharField(max_length=50, unique=True, blank=True, default='')

    def clean(self):
        if self.fecha_devolucion and self.fecha_reserva and self.fecha_devolucion <= self.fecha_reserva:
            raise ValidationError({
                'fecha_devolucion': 'La fecha de devolución debe ser posterior a la fecha de reserva.'
            })

        if self.tiene_solapamiento_con_aprobada():
            raise ValidationError(
                'Ya tienes otra reserva aprobada que se solapa con este horario.'
            )

    def tiene_solapamiento_con_aprobada(self):
        """True si self.usuario ya tiene otra Reserva en estado "Aprobada"
        cuyo rango [fecha_reserva, fecha_devolucion) se solapa con el de
        esta. Solo aplica a reservas nuevas, y solo si se puede identificar
        al usuario: self.usuario queda vacío para solicitantes sin cuenta de
        Usuario registrada (ver SolicitudReserva.crear_reserva(), que busca
        por cédula) — en ese caso no hay forma de detectar el solapamiento."""
        if self.pk is not None or not self.usuario_id or not self.fecha_reserva:
            return False

        fin = self.fecha_devolucion or self.fecha_reserva

        conflictos = Reserva.objects.filter(
            usuario_id=self.usuario_id,
            estado__nombre='Aprobada',
            fecha_reserva__date=self.fecha_reserva.date(),
        )

        for otra in conflictos:
            otra_fin = otra.fecha_devolucion or otra.fecha_reserva
            if self.fecha_reserva < otra_fin and otra.fecha_reserva < fin:
                return True
        return False

    def generar_codigo(self):
        solicitud = self.solicitud.first()
        cedula = solicitud.cedula if solicitud else 'SIN'

        lab = solicitud.laboratorio if solicitud and solicitud.laboratorio else None
        if lab:
            palabras = [w for w in lab.nombre.split() if w]
            siglas = ''.join(word[0].upper() for word in palabras)[:6]
        else:
            siglas = 'LAB'

        numero = str(self.id).zfill(3)
        return f"{cedula}-{siglas}-R{numero}"

    def save(self, *args, **kwargs):
        self.hora_limite_retiro = self.fecha_reserva + timedelta(minutes=30)
        if not self.fecha_devolucion:
            self.fecha_devolucion = self.fecha_reserva + timedelta(hours=2)
        super().save(*args, **kwargs)

        necesita_regenerar = not self.codigo or (
            self.codigo.startswith('SIN-') and self.solicitud.first()
        )
        if necesita_regenerar:
            self.codigo = self.generar_codigo()
            super().save(update_fields=['codigo'])

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

    def clean(self):
        if self.cantidad is not None and self.cantidad < 1:
            raise ValidationError({'cantidad': 'La cantidad debe ser al menos 1.'})

    def __str__(self):
        return f"{self.insumo.nombre}"
    
