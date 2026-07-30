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

    activo = models.BooleanField(default=True)

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
    ZONA_CHOICES = [
        ('izquierda', 'Zona Izquierda'),
        ('centro-top', 'Centro Superior'),
        ('centro-mid', 'Centro Medio'),
        ('centro-bot', 'Centro Inferior'),
        ('derecha', 'Zona Derecha'),
        ('inferior', 'Zona Inferior'),
    ]
    zona = models.CharField(max_length=20, choices=ZONA_CHOICES, default='centro-mid')
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
    activo    = models.BooleanField(default=True)

    class Meta:
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class LaboratoristaLab(models.Model):

    TIPO_CHOICES = [
        ('laboratorista', 'Laboratorista'),
        ('encargado',     'Encargado'),
    ]

    laboratorista = models.ForeignKey(
        Laboratorista,
        on_delete=models.CASCADE,
        related_name='asignaciones'
    )
    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE,
        related_name='asignaciones'
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default='laboratorista'
    )

    class Meta:
        unique_together = ('laboratorista', 'laboratorio')
        ordering = ['laboratorio', 'tipo']

    def __str__(self):
        return f"{self.laboratorista} — {self.laboratorio} ({self.tipo})"


class HistorialModulo(models.Model):

    modulo = models.ForeignKey(
        Modulo,
        on_delete=models.CASCADE,
        related_name='historial'
    )
    motivo = models.CharField(max_length=300)
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    registrado_por = models.ForeignKey(
        'users.Usuario',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='historial_modulos'
    )

    class Meta:
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f"{self.modulo.nombre} — {self.motivo} ({self.fecha_inicio.strftime('%d/%m/%Y')})"

    @property
    def duracion(self):
        from django.utils import timezone
        fin = self.fecha_fin or timezone.now()
        delta = fin - self.fecha_inicio
        dias = delta.days
        horas = delta.seconds // 3600
        if dias > 0:
            return f"{dias}d {horas}h"
        return f"{horas}h {(delta.seconds % 3600) // 60}m"