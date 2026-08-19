"""
models.py — solicitudes
Define SolicitudReserva, SolicitudInsumo y Curso; contiene la lógica de validación de reglas de negocio
y el método crear_reserva() que genera la Reserva asociada en estado "Pendiente".
"""
from django.db import models
from django.core.exceptions import ValidationError, NON_FIELD_ERRORS
from django.db.models import Q
from datetime import timedelta, date, time
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

    def clean(self):
        errors = {}
        if self.cantidad_estudiantes is not None and self.cantidad_estudiantes < 1:
            errors['cantidad_estudiantes'] = 'La cantidad de estudiantes debe ser al menos 1.'
        if self.profesor_id and (not self.profesor.rol or self.profesor.rol.nombre != 'Docente'):
            errors['profesor'] = 'El profesor debe tener rol Docente.'
        if errors:
            raise ValidationError(errors)

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
    email = models.EmailField(blank=True, default='')
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

    reserva_libre = models.BooleanField(default=False)
    descripcion_actividad = models.CharField(max_length=500, blank=True, default='')
    cantidad_asistentes_libre = models.PositiveIntegerField(null=True, blank=True)

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

        if self.fecha_reserva and self.fecha_reserva.date() < date.today():
            errors['fecha_reserva'] = 'La fecha de reserva no puede ser anterior a hoy.'

        # Validación de profesor
        if self.tipo_solicitante == 'profesor':
            if not self.nombre or not self.cedula:
                errors['nombre'] = 'Nombre y cédula son requeridos para profesores.'

            if self.nombre:
                partes_nombre = self.nombre.split()
                query = Q()
                for parte in partes_nombre:
                    query |= Q(first_name__icontains=parte) | Q(last_name__icontains=parte) | Q(username__icontains=parte)

                usuarios = Usuario.objects.filter(query, rol__nombre='Docente')

                if not usuarios.exists():
                    errors['nombre'] = f'No se encontró un profesor registrado con el nombre "{self.nombre}".'
                else:
                    self.usuario = usuarios.first()

        # Validación de horario
        if self.hora_inicio is not None and self.hora_fin is not None:

            # Reservas que empiezan a las 16:00 o después siempre terminan
            # exactamente a las 18:00 (cierre del laboratorio) sin importar
            # cuánto haya pedido el solicitante ni la duración resultante
            # (puede quedar en minutos) — así una solicitud tardía sigue
            # siendo válida en vez de chocar con el mínimo de 2 horas de
            # más abajo, que solo aplica antes de las 16:00.
            solicitud_tardia = self.hora_inicio >= time(16, 0)
            if solicitud_tardia:
                self.hora_fin = time(18, 0)

            if self.hora_fin <= self.hora_inicio:
                errors['hora_fin'] = 'La hora de fin debe ser posterior a la hora de inicio.'

            duracion = self._calcular_duracion()

            if not solicitud_tardia and duracion < timedelta(hours=2):
                errors['hora_fin'] = 'El préstamo debe ser mínimo 2 horas.'

            max_horas = 8 if self.tipo_solicitante == 'profesor' else 4
            if duracion > timedelta(hours=max_horas):
                errors['hora_fin'] = f'El préstamo no puede exceder {max_horas} horas.'

            if self.laboratorio and self.fecha_reserva:
                self._validar_horario_laboratorio(errors)

            # Validar horas acumuladas en el día
            if self.fecha_reserva and not errors.get('hora_fin'):
                fecha = self.fecha_reserva.date()

                solicitudes_mismo_dia = SolicitudReserva.objects.filter(
                    fecha_reserva__date=fecha
                ).exclude(pk=self.pk if self.pk else None)

                if self.tipo_solicitante == 'estudiante' and self.cedula:
                    solicitudes_mismo_dia = solicitudes_mismo_dia.filter(
                        cedula=self.cedula,
                        tipo_solicitante='estudiante'
                    )
                elif self.tipo_solicitante == 'profesor' and self.usuario:
                    solicitudes_mismo_dia = solicitudes_mismo_dia.filter(
                        usuario=self.usuario,
                        tipo_solicitante='profesor'
                    )
                else:
                    solicitudes_mismo_dia = solicitudes_mismo_dia.none()

                horas_usadas = timedelta(0)
                for s in solicitudes_mismo_dia:
                    if s.hora_inicio and s.hora_fin:
                        horas_usadas += s._calcular_duracion()

                total = horas_usadas + duracion
                limite = timedelta(hours=max_horas)

                if total > limite:
                    restante = limite - horas_usadas
                    horas_r = restante.seconds // 3600
                    minutos_r = (restante.seconds % 3600) // 60
                    errors['hora_fin'] = (
                        f'Ya tienes reservas este día. '
                        f'El límite es {max_horas}h por día. '
                        f'Tiempo disponible restante: {horas_r}h {minutos_r}min.'
                    )

        if self.limite_pendientes_alcanzado():
            errors[NON_FIELD_ERRORS] = (
                'Ya tienes 2 reservas pendientes. Debes esperar a que sean '
                'aprobadas o canceladas antes de crear una nueva.'
            )

        if errors:
            raise ValidationError(errors)

    def limite_pendientes_alcanzado(self):
        """True si el solicitante (identificado por cédula si es estudiante,
        o por usuario si es profesor — mismo criterio que la validación de
        horas acumuladas por día de arriba) ya tiene 2 o más solicitudes
        cuya Reserva sigue en estado "Pendiente". Solo aplica a solicitudes
        nuevas: una ya guardada no cuenta contra su propio límite."""
        if self.pk is not None:
            return False

        if self.tipo_solicitante == 'estudiante' and self.cedula:
            filtro = Q(cedula=self.cedula, tipo_solicitante='estudiante')
        elif self.tipo_solicitante == 'profesor' and self.usuario_id:
            filtro = Q(usuario_id=self.usuario_id, tipo_solicitante='profesor')
        else:
            return False

        return SolicitudReserva.objects.filter(
            filtro, reserva__estado__nombre='Pendiente'
        ).count() >= 2

    def _calcular_duracion(self):
        if self.hora_inicio is not None and self.hora_fin is not None:
            from datetime import datetime
            inicio = datetime.combine(self.fecha_reserva.date(), self.hora_inicio)
            fin = datetime.combine(self.fecha_reserva.date(), self.hora_fin)
            return fin - inicio
        return timedelta(0)

    def _validar_horario_laboratorio(self, errors):
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

        if self.hora_inicio and self.hora_fin and horario:
            if self.hora_inicio < horario.hora_inicio or self.hora_fin > horario.hora_fin:
                errors['hora_inicio'] = (
                    f'Las horas deben estar dentro del horario disponible: '
                    f'{horario.hora_inicio.strftime("%H:%M")} - {horario.hora_fin.strftime("%H:%M")}'
                )

    def asignar_modulos_automaticamente(self):
        if self.tipo_solicitante == 'profesor' and self.necesita_modulo and self.curso:
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

    def crear_reserva(self):
        from datetime import datetime
        from reservas.models import EstadoReserva, ReservaInsumo
        from users.models import Usuario

        if self.reserva:
            return self.reserva

        estado_pendiente = EstadoReserva.objects.filter(nombre='Pendiente').first()
        if not estado_pendiente:
            raise ValueError('No existe estado "Pendiente" en EstadoReserva')

        usuario = Usuario.objects.filter(codigo=self.cedula).first()

        fecha_base = datetime.combine(
            self.fecha_reserva.date(),
            self.hora_inicio or datetime.min.time()
        )

        fecha_devolucion = None
        if self.hora_fin:
            fecha_devolucion = datetime.combine(
                self.fecha_reserva.date(),
                self.hora_fin
            )

        reserva = Reserva.objects.create(
            usuario=usuario,
            fecha_reserva=fecha_base,
            fecha_devolucion=fecha_devolucion,
            estado=estado_pendiente
        )

        for solicitud_insumo in self.insumos.all():
            ReservaInsumo.objects.create(
                reserva=reserva,
                insumo=solicitud_insumo.insumo,
                cantidad=solicitud_insumo.cantidad
            )

        self.reserva = reserva
        self.save(update_fields=['reserva'])

        return reserva

    def __str__(self):
        if self.tipo_solicitante == 'profesor':
            if self.reserva_libre:
                return f"Solicitud Libre - {self.nombre} ({self.programa or 'Sin grupo'})"
            return f"Solicitud Profesor - {self.nombre} ({self.curso})"
        if self.usuario:
            return f"Solicitud Estudiante - {self.usuario.username}"
        return f"Solicitud Estudiante Anónimo - ID {self.id}"


ESTADO_SOLICITUD_REGISTRO = [
    ('pendiente', 'Pendiente'),
    ('aprobada', 'Aprobada'),
    ('rechazada', 'Rechazada'),
]


class SolicitudRegistroProfesor(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20, unique=True)
    correo = models.EmailField(blank=True, default='')
    programa = models.CharField(max_length=200, blank=True, default='')
    estado = models.CharField(
        max_length=20, choices=ESTADO_SOLICITUD_REGISTRO, default='pendiente'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    usuario_creado = models.ForeignKey(
        'users.Usuario', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='solicitud_registro'
    )

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.cedula})"


class SolicitudRegistroCurso(models.Model):
    solicitud_profesor = models.ForeignKey(
        SolicitudRegistroProfesor,
        on_delete=models.CASCADE,
        related_name='cursos_solicitados'
    )
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=50)
    cantidad_estudiantes = models.PositiveIntegerField()
    estado = models.CharField(
        max_length=20, choices=ESTADO_SOLICITUD_REGISTRO, default='pendiente'
    )
    curso_creado = models.ForeignKey(
        'solicitudes.Curso', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='solicitud_origen'
    )

    def clean(self):
        if self.cantidad_estudiantes is not None and self.cantidad_estudiantes < 1:
            raise ValidationError({
                'cantidad_estudiantes': 'La cantidad de estudiantes debe ser al menos 1.'
            })

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


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

    def clean(self):
        if self.cantidad is not None and self.cantidad < 1:
            raise ValidationError({'cantidad': 'La cantidad debe ser al menos 1.'})

    def __str__(self):
        return f"{self.solicitud.id} - {self.insumo.nombre} x{self.cantidad}"
