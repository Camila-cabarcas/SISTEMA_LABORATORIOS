"""
models.py — laboratorio
Define Laboratorio, HorarioLaboratorio, EventoLaboratorio y Modulo con sus estados de disponibilidad.
"""
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from laboratorio.services.posiciones_mapa import (
    ALTO_MODULO, ANCHO_MODULO, LIENZO_EDITOR_ALTO, LIENZO_EDITOR_ANCHO, se_solapan,
)


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


def es_laboratorista_del_laboratorio(usuario, laboratorio):
    """True si `usuario` es el Usuario (rol='Laboratorio') asignado como
    encargado de `laboratorio` — mismo criterio que
    laboratorio.views._check_lab_access, expuesto acá para reutilizar desde
    otras apps (p. ej. reservas) sin depender de esa vista. Un Administrador
    NO cuenta como laboratorista de un laboratorio puntual: quien necesite
    que Administrador también pase debe chequearlo aparte."""
    if not laboratorio or not usuario or not usuario.is_authenticated:
        return False
    if not usuario.rol or usuario.rol.nombre != 'Laboratorio':
        return False
    return laboratorio.encargados.filter(id=usuario.id).exists()


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

    def clean(self):
        if self.hora_inicio and self.hora_fin and self.hora_fin <= self.hora_inicio:
            raise ValidationError({
                'hora_fin': 'La hora de fin debe ser posterior a la hora de inicio.'
            })

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
        null=True,
        blank=True,
    )

    def clean(self):
        if self.inicio and self.fin and self.fin <= self.inicio:
            raise ValidationError({
                'fin': 'La hora de fin debe ser posterior a la hora de inicio.'
            })

    def __str__(self):
        return f"{self.titulo} - {self.inicio}"


class CategoriaModulo(models.Model):
    """Tipo de módulo (Mesa, Computador, Maquinaria...). Define cómo se dibuja
    el módulo en el mapa, el editor y los formularios de reserva: el color
    rellena la figura y la forma decide la figura (ver
    templates/laboratorio/partials/modulo_figura.html y static/js/modulo_figura.js).

    No se borra si tiene módulos (Modulo.categoria es PROTECT): se desactiva.
    Las 3 categorías base las siembra la migración 0018_sembrar_categorias.
    """
    CUADRADO = 'cuadrado'
    CIRCULO = 'circulo'
    ROMBO = 'rombo'
    TRIANGULO = 'triangulo'
    COMPUTADOR = 'computador'
    MAQUINARIA = 'maquinaria'

    FORMA_CHOICES = [
        (CUADRADO, 'Módulo (forma original)'),
        (COMPUTADOR, 'Computador'),
        (MAQUINARIA, 'Maquinaria'),
        (CIRCULO, 'Círculo'),
        (ROMBO, 'Rombo'),
        (TRIANGULO, 'Triángulo'),
    ]

    # Estilo de un módulo sin categoría.
    COLOR_SIN_CATEGORIA = '#6c757d'
    FORMA_SIN_CATEGORIA = CUADRADO

    nombre = models.CharField(max_length=60, unique=True)
    color = models.CharField(
        max_length=7,
        default='#0d6efd',
        validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'El color debe ser hexadecimal, p. ej. #0d6efd.')],
    )
    forma = models.CharField(max_length=20, choices=FORMA_CHOICES, default=CUADRADO)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría de módulo'
        verbose_name_plural = 'Categorías de módulo'

    def clean(self):
        if self.nombre:
            self.nombre = self.nombre.strip()
            repetida = CategoriaModulo.objects.filter(nombre__iexact=self.nombre).exclude(pk=self.pk)
            if repetida.exists():
                raise ValidationError({'nombre': 'Ya existe una categoría con ese nombre.'})
        if self.color:
            self.color = self.color.lower()

    def __str__(self):
        return self.nombre


class Division(models.Model):
    """Zona rectangular (salón) dentro de la sala de un laboratorio.

    Opcional: un laboratorio tiene de 0 a MAX_POR_LABORATORIO. Las
    coordenadas están en el mismo sistema que Modulo.posicion_x/y (píxeles
    del editor de mapa). Un módulo pertenece a la división que contiene su
    centro — lo calcula laboratorio.services.divisiones al guardar el mapa.
    """
    MAX_POR_LABORATORIO = 4
    # Cabe al menos un módulo con margen (tamaño en posiciones_mapa).
    ANCHO_MINIMO = ANCHO_MODULO + 20
    ALTO_MINIMO = ALTO_MODULO + 20
    TAMANO_MAXIMO = 4000

    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE,
        related_name='divisiones',
    )
    nombre = models.CharField(max_length=60)
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    ancho = models.IntegerField(default=300)
    alto = models.IntegerField(default=200)

    class Meta:
        ordering = ['nombre', 'id']
        verbose_name = 'División'
        verbose_name_plural = 'Divisiones'
        constraints = [
            models.UniqueConstraint(fields=['laboratorio', 'nombre'], name='division_nombre_laboratorio_unico'),
        ]

    def clean(self):
        errores = self.errores_de_datos()
        if self.laboratorio_id:
            otras = Division.objects.filter(laboratorio_id=self.laboratorio_id).exclude(pk=self.pk)
            if otras.count() >= self.MAX_POR_LABORATORIO:
                errores['laboratorio'] = (
                    f'Un laboratorio puede tener como máximo {self.MAX_POR_LABORATORIO} divisiones.'
                )
        if errores:
            raise ValidationError(errores)

    def errores_de_datos(self) -> dict[str, str]:
        """Errores de nombre, posición y tamaño ({campo: mensaje}), sin el
        máximo por laboratorio — el guardado del mapa valida ese máximo
        sobre el conjunto final completo, no división por división."""
        errores = {}
        if not (self.nombre or '').strip():
            errores['nombre'] = 'La división necesita un nombre.'
        if (self.x or 0) < 0 or (self.y or 0) < 0:
            errores['x'] = 'La división no puede salir del lienzo (coordenadas negativas).'
        elif ((self.x or 0) + (self.ancho or 0) > LIENZO_EDITOR_ANCHO
              or (self.y or 0) + (self.alto or 0) > LIENZO_EDITOR_ALTO):
            errores['x'] = (
                f'La división no puede salir del lienzo ({LIENZO_EDITOR_ANCHO}×{LIENZO_EDITOR_ALTO} px).'
            )
        if self.ancho is not None and not self.ANCHO_MINIMO <= self.ancho <= self.TAMANO_MAXIMO:
            errores['ancho'] = f'El ancho debe estar entre {self.ANCHO_MINIMO} y {self.TAMANO_MAXIMO} px.'
        if self.alto is not None and not self.ALTO_MINIMO <= self.alto <= self.TAMANO_MAXIMO:
            errores['alto'] = f'El alto debe estar entre {self.ALTO_MINIMO} y {self.TAMANO_MAXIMO} px.'
        return errores

    def contiene(self, x, y):
        """True si el punto (x, y) cae dentro del rectángulo (bordes incluidos
        a la izquierda/arriba, excluidos a la derecha/abajo)."""
        return self.x <= x < self.x + self.ancho and self.y <= y < self.y + self.alto

    @property
    def rect(self):
        return (self.x, self.y, self.ancho, self.alto)

    def se_superpone(self, otra):
        return se_solapan(self.rect, otra.rect)

    def __str__(self):
        return f"{self.nombre} ({self.laboratorio.nombre})"


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
    # Posición en el mapa (drag & drop), en píxeles.
    posicion_x = models.IntegerField(default=0, help_text="Posición X en píxeles")
    posicion_y = models.IntegerField(default=0, help_text="Posición Y en píxeles")
    # Opcional; la asigna el guardado del editor de mapa según la posición
    # (ver laboratorio.services.divisiones). Borrar la división no borra el
    # módulo: queda sin división.
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modulos',
    )
    # Opcional: sin categoría se dibuja gris con la forma original. PROTECT:
    # una categoría con módulos no se puede borrar (se desactiva).
    categoria = models.ForeignKey(
        CategoriaModulo,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='modulos',
    )

    def clean(self):
        if self.capacidad is not None and self.capacidad < 1:
            raise ValidationError({'capacidad': 'La capacidad debe ser al menos 1.'})
        if self.division_id and self.laboratorio_id and self.division.laboratorio_id != self.laboratorio_id:
            raise ValidationError({'division': 'La división debe ser del mismo laboratorio que el módulo.'})

    @property
    def nombre_con_division(self):
        """'Mesa 3 · Salón A', o solo 'Mesa 3' sin división."""
        return f'{self.nombre} · {self.division.nombre}' if self.division_id else self.nombre

    @property
    def descripcion_completa(self):
        """'Mesa 3 · Computador · Salón A' — omite categoría/división si no tiene."""
        partes = [self.nombre]
        if self.categoria_id:
            partes.append(self.categoria.nombre)
        if self.division_id:
            partes.append(self.division.nombre)
        return ' · '.join(partes)

    @property
    def color_categoria(self):
        return self.categoria.color if self.categoria_id else CategoriaModulo.COLOR_SIN_CATEGORIA

    @property
    def forma_categoria(self):
        return self.categoria.forma if self.categoria_id else CategoriaModulo.FORMA_SIN_CATEGORIA

    def __str__(self):
        base = f"{self.nombre} ({self.laboratorio.nombre})"
        return f"{base} — {self.categoria.nombre}" if self.categoria_id else base


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

    def clean(self):
        validas = {clave for clave, _ in self.RESPONSABILIDADES_CHOICES}
        invalidas = set(self.responsabilidades or []) - validas
        if invalidas:
            raise ValidationError({
                'responsabilidades': f'Responsabilidad(es) no válida(s): {", ".join(sorted(invalidas))}.'
            })

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

    def clean(self):
        if self.tipo == 'encargado':
            ya_tiene_encargado = LaboratoristaLab.objects.filter(
                laboratorio=self.laboratorio, tipo='encargado',
            ).exclude(pk=self.pk).exists()
            if ya_tiene_encargado:
                raise ValidationError('Este laboratorio ya tiene un encargado.')

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

    def clean(self):
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({
                'fecha_fin': 'La fecha de fin no puede ser anterior a la fecha de inicio.'
            })

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