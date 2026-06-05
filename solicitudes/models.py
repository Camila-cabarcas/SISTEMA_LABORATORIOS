from django.db import models
from django.core.exceptions import ValidationError
from users.models import Usuario
from laboratorio.models import Laboratorio, Modulo


class Curso(models.Model):
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=50, unique=True)
    profesor = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        limit_choices_to={'rol__nombre': 'Docente'}
    )
    cantidad_estudiantes = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class SolicitudReserva(models.Model):
    TIPO_SOLICITANTE_CHOICES = [
        ('estudiante', 'Estudiante'),
        ('profesor', 'Profesor'),
    ]

    tipo_solicitante = models.CharField(
        max_length=20,
        choices=TIPO_SOLICITANTE_CHOICES,
        default='estudiante'
    )

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    nombre = models.CharField(max_length=200, blank=True)
    cedula = models.CharField(max_length=50, blank=True)

    curso = models.ForeignKey(
        Curso,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE
    )

    fecha_reserva = models.DateTimeField()
    observaciones = models.TextField(blank=True)

    modulos_asignados = models.ManyToManyField(
        Modulo,
        blank=True,
        related_name='solicitudes'
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.tipo_solicitante == 'profesor':
            if not self.nombre or not self.cedula:
                raise ValidationError('Nombre y cédula son requeridos para profesores.')

            try:
                usuario = Usuario.objects.get(
                    first_name__icontains=self.nombre,
                    rol__nombre='Docente'
                )
                self.usuario = usuario
            except Usuario.DoesNotExist:
                raise ValidationError(
                    f'No se encontró un profesor registrado con el nombre "{self.nombre}".'
                )
            except Usuario.MultipleObjectsReturned:
                raise ValidationError(
                    f'Múltiples usuarios encontrados con nombre "{self.nombre}". '
                    'Por favor, sea más específico.'
                )

    def asignar_modulos_automaticamente(self):
        if self.tipo_solicitante == 'profesor' and self.curso:
            cantidad_necesaria = self.curso.cantidad_estudiantes

            modulos_disponibles = Modulo.objects.filter(
                laboratorio=self.laboratorio,
                disponible=True
            )[:cantidad_necesaria]

            if modulos_disponibles.count() < cantidad_necesaria:
                raise ValidationError(
                    f'No hay suficientes módulos disponibles. '
                    f'Se necesitan {cantidad_necesaria}, hay {modulos_disponibles.count()}.'
                )

            self.modulos_asignados.set(modulos_disponibles)

    def __str__(self):
        if self.tipo_solicitante == 'profesor':
            return f"Solicitud Profesor - {self.nombre} ({self.curso})"
        return f"Solicitud Estudiante - {self.usuario.username}"
