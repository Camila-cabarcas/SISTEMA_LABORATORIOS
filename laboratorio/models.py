from django.db import models


class Laboratorio(models.Model):

    nombre = models.CharField(max_length=100)
    ubicacion = models.CharField(max_length=200)

    encargado = models.ForeignKey(
        'users.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
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