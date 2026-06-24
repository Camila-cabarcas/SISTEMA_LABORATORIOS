"""
models.py — laboratorio
Define Laboratorio, HorarioLaboratorio, EventoLaboratorio y Modulo con sus estados de disponibilidad.
"""
from django.db import models


class Laboratorio(models.Model):

    nombre = models.CharField(max_length=100)
    ubicacion = models.CharField(max_length=200)

    encargados = models.ManyToManyField(
        'users.Usuario',
        blank=True,
        limit_choices_to={'rol__nombre': 'Encargado'},
        related_name='laboratorios_asignados',
        verbose_name='Encargados',
    )

    programa = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.nombre


class HorarioLaboratorio(models.Model):

    DIAS = [
        ('lunes', 'Lunes'),
        ('martes', 'Martes'),
        ('miercoles', 'Miércoles'),
        ('jueves', 'Jueves'),
        ('viernes', 'Viernes'),
        ('sabado', 'Sábado'),
    ]

    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE,
        related_name='horarios'
    )

    dia = models.CharField(max_length=20, choices=DIAS)

    hora_inicio = models.TimeField()

    hora_fin = models.TimeField()

    bloqueado = models.BooleanField(default=False)

    motivo_bloqueo = models.CharField(
        max_length=200,
        blank=True
    )

    def __str__(self):
        return f"{self.laboratorio.nombre} - {self.dia} {self.hora_inicio}-{self.hora_fin}"


class EventoLaboratorio(models.Model):

    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE,
        related_name='eventos'
    )

    titulo = models.CharField(max_length=200)

    inicio = models.DateTimeField()

    fin = models.DateTimeField()

    bloqueado = models.BooleanField(default=True)

    creado_por = models.ForeignKey(
        'users.Usuario',
        on_delete=models.SET_NULL,
        null=True
    )

    def __str__(self):
        return f"{self.titulo} - {self.inicio}"


class Modulo(models.Model):

    nombre = models.CharField(max_length=100)
    capacidad = models.PositiveIntegerField()
    disponible = models.BooleanField(default=True)
    motivo_no_disponible = models.CharField(  # ← nuevo
        max_length=300,
        blank=True,
        default=''
    )
    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE,
        related_name='modulos'
    )

    def __str__(self):
        return f"{self.nombre} ({self.laboratorio.nombre})"


class Laboratorista(models.Model):
    RESPONSABILIDADES_CHOICES = [
        ('prestamos',     'Gestión de préstamos'),
        ('atencion',      'Atención a estudiantes y profesores'),
        ('inventario',    'Control de inventario'),
        ('mantenimiento', 'Mantenimiento de equipos'),
        ('apertura',      'Apertura y cierre del laboratorio'),
        ('movimientos',   'Registro de movimientos'),
        ('supervision',   'Supervisión de prácticas'),
    ]

    nombre    = models.CharField(max_length=100)
    apellido  = models.CharField(max_length=100)
    cedula    = models.CharField(max_length=20, unique=True)
    correo    = models.EmailField(blank=True, default='')
    programa  = models.CharField(max_length=200, blank=True, default='')
    responsabilidades = models.JSONField(default=list, blank=True)
    laboratorios = models.ManyToManyField(
        Laboratorio,
        blank=True,
        related_name='laboratoristas',
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"