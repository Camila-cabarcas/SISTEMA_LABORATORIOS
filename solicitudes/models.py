from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from users.models import Usuario
from laboratorio.models import Laboratorio, Modulo, HorarioLaboratorio
from inventario.models import Insumo
from reservas.models import Reserva


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
    programa = models.CharField(max_length=200, blank=True)

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
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)

    necesita_modulo = models.BooleanField(default=True)

    observaciones = models.TextField(blank=True)

    modulos_asignados = models.ManyToManyField(
        Modulo,
        blank=True,
        related_name='solicitudes'
    )

    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitud'
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def clean(self):
        errors = {}

        # Validación de profesor
        if self.tipo_solicitante == 'profesor':
            if not self.nombre or not self.cedula:
                errors['nombre'] = 'Nombre y cédula son requeridos para profesores.'

            if self.nombre:
                from django.db.models import Q
                partes_nombre = self.nombre.split()
                query = Q()
                for parte in partes_nombre:
                    query |= Q(first_name__icontains=partes_nombre) | Q(last_name__icontains=parte)

                usuarios = Usuario.objects.filter(query, rol__nombre='Docente')

                if not usuarios.exists():
                    errors['nombre'] = f'No se encontró un profesor registrado con el nombre "{self.nombre}".'
                else:
                    self.usuario = usuarios.first()

        # Validación de horario
        if self.hora_inicio is not None and self.hora_fin is not None:
            # Validar que hora_fin > hora_inicio
            if self.hora_fin <= self.hora_inicio:
                errors['hora_fin'] = 'La hora de fin debe ser posterior a la hora de inicio.'

            # Validar duración
            duracion = self._calcular_duracion()
            if duracion < timedelta(hours=2):
                errors['hora_fin'] = 'El préstamo debe ser mínimo 2 horas.'

            # Máximo 8 horas para profesores, 4 para estudiantes
            max_horas = 8 if self.tipo_solicitante == 'profesor' else 4
            if duracion > timedelta(hours=max_horas):
                errors['hora_fin'] = f'El préstamo no puede exceder {max_horas} horas.'

            # Validar dentro del horario del laboratorio
            if self.laboratorio and self.fecha_reserva:
                self._validar_horario_laboratorio(errors)

        if errors:
            raise ValidationError(errors)

    def _calcular_duracion(self):
        if self.hora_inicio is not None and self.hora_fin is not None:
            from datetime import datetime
            inicio = datetime.combine(self.fecha_reserva.date(), self.hora_inicio)
            fin = datetime.combine(self.fecha_reserva.date(), self.hora_fin)
            return fin - inicio
        return timedelta(0)

    def _validar_horario_laboratorio(self, errors):
        from django.utils import timezone
        from datetime import datetime

        fecha = self.fecha_reserva.date()
        dia_semana = fecha.strftime('%A').lower()

        dia_map = {
            'monday': 'lunes',
            'tuesday': 'martes',
            'wednesday': 'miercoles',
            'thursday': 'jueves',
            'friday': 'viernes',
            'saturday': 'sabado',
            'sunday': 'domingo',
        }

        dia_nombre = dia_map.get(dia_semana)

        horarios = HorarioLaboratorio.objects.filter(
            laboratorio=self.laboratorio,
            dia=dia_nombre,
            bloqueado=False
        )

        if not horarios.exists():
            errors['fecha_reserva'] = f'El laboratorio no está disponible los {dia_nombre}s.'
            return

        horario = horarios.first()
        
        # Validación defensiva para asegurar que las variables existan antes del formateo
        if self.hora_inicio and self.hora_fin and horario:
            if self.hora_inicio < horario.hora_inicio or self.hora_fin > horario.hora_fin:
                errors['hora_inicio'] = (
                    f'Las horas deben estar dentro del horario disponible: '
                    f'{horario.hora_inicio.strftime("%H:%M")} - {horario.hora_fin.strftime("%H:%M")}'
                )

    def asignar_modulos_automaticamente(self):
        if self.tipo_solicitante == 'profesor' and self.curso:
            cantidad_necesaria = self.curso.cantidad_estudiantes

            modulos_disponibles = Modulo.objects.filter(
                laboratorio=self.laboratorio,
                disponibles=True
            )[:cantidad_necesaria]

            if modulos_disponibles.count() < cantidad_necesaria:
                raise ValidationError(
                    f'No hay suficientes módulos disponibles. '
                    f'Se necesitan {cantidad_necesaria}, hay {modulos_disponibles.count()}.'
                )

            self.modulos_asignados.set(modulos_disponibles)

    def crear_reserva(self):
        """Crear una Reserva a partir de esta SolicitudReserva"""
        from datetime import datetime
        from reservas.models import EstadoReserva, ReservaInsumo

        # No crear si ya existe reserva
        if self.reserva:
            return self.reserva

        # Obtener estado "Pendiente"
        estado_pendiente = EstadoReserva.objects.filter(nombre='Pendiente').first()
        if not estado_pendiente:
            raise ValueError('No existe estado "Pendiente" en EstadoReserva')

        # Calcular fecha_reserva como datetime (combinando fecha y hora_inicio)
        fecha_base = datetime.combine(self.fecha_reserva.date(), self.hora_inicio or datetime.min.time())

        # Crear Reserva
        reserva = Reserva.objects.create(
            usuario=self.usuario,
            fecha_reserva=fecha_base,
            estado=estado_pendiente
        )

        # Crear ReservaInsumo para cada insumo
        for solicitud_insumo in self.insumos.all():
            ReservaInsumo.objects.create(
                reserva=reserva,
                insumo=solicitud_insumo.insumo,
                cantidad=solicitud_insumo.cantidad
            )

        # Guardar referencia a la reserva
        self.reserva = reserva
        self.save(update_fields=['reserva'])

        return reserva

    def __str__(self):
        if self.tipo_solicitante == 'profesor':
            return f"Solicitud Profesor - {self.nombre} ({self.curso})"
        
        # Evita errores si el usuario llega a ser nulo (null=True en el modelo)
        if self.usuario:
            return f"Solicitud Estudiante - {self.usuario.username}"
        return f"Solicitud Estudiante Anónimo - ID {self.id}"


class SolicitudInsumo(models.Model):
    solicitud = models.ForeignKey(
        SolicitudReserva,
        on_delete=models.CASCADE,
        related_name='insumos'
    )

    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.CASCADE
    )

    cantidad = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.solicitud.id} - {self.insumo.nombre} x{self.cantidad}"