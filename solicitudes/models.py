"""
models.py — solicitudes
Define SolicitudReserva, SolicitudInsumo y Curso; contiene la lógica de validación de reglas de negocio
y el método crear_reserva() que genera la Reserva asociada en estado "Pendiente".
"""
import logging

from django.db import models
from django.core.exceptions import ValidationError, NON_FIELD_ERRORS
from django.db.models import Q
from datetime import timedelta, date, time
from users.models import Usuario
from laboratorio.models import Laboratorio, Modulo, HorarioLaboratorio
from inventario.models import Insumo
from reservas.models import Reserva

logger = logging.getLogger(__name__)


class Profesor(models.Model):
    """Profesor habilitado, SIN cuenta en el sistema (reemplaza a las cuentas
    de rol Docente, ver migraciones solicitudes.0012 y users.0008). Se
    identifica por cédula: la usan los cursos (Curso.profesor) y,
    más adelante, la importación de cursos y las reservas públicas."""

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20, unique=True)
    correo = models.EmailField(blank=True, default='')
    programa = models.CharField(max_length=200, blank=True, default='')
    activo = models.BooleanField(default=True)
    solicitud_origen = models.ForeignKey(
        'solicitudes.SolicitudRegistroProfesor', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='profesores_creados',
    )
    # Solo rastro de la migración desde la cuenta Docente (permite
    # deshacerla). No da acceso a nada.
    cuenta_anterior = models.ForeignKey(
        'users.Usuario', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='profesores_migrados',
    )

    class Meta:
        ordering = ['apellido', 'nombre']
        verbose_name = 'Profesor'
        verbose_name_plural = 'Profesores'

    def __str__(self):
        return f'{self.nombre} {self.apellido} ({self.cedula})'

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'.strip()

    @classmethod
    def buscar_activo(cls, cedula):
        """El Profesor activo con esa cédula, o None. Para reservas de curso
        y la API pública de cursos."""
        cedula = (cedula or '').strip()
        if not cedula:
            return None
        return cls.objects.filter(cedula=cedula, activo=True).first()


class Curso(models.Model):
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=50, unique=True)
    # El Profesor (sin cuenta) del curso. PROTECT: no se puede borrar un
    # profesor que tenga cursos. Hasta la fase 2 era una cuenta Docente; ver
    # migraciones solicitudes.0010-0013.
    profesor = models.ForeignKey(
        Profesor, on_delete=models.PROTECT, related_name='cursos',
    )
    cantidad_estudiantes = models.PositiveIntegerField()
    laboratorio = models.ForeignKey(
        Laboratorio,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cursos',
    )

    def clean(self):
        errors = {}
        if self.cantidad_estudiantes is not None and self.cantidad_estudiantes < 1:
            errors['cantidad_estudiantes'] = 'La cantidad de estudiantes debe ser al menos 1.'
        # Que haya profesor lo exige el campo (obligatorio); aquí, que esté activo.
        if self.profesor_id and not self.profesor.activo:
            errors['profesor'] = 'El profesor seleccionado no está activo.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        if self.laboratorio_id:
            return f"{self.codigo} - {self.nombre} ({self.laboratorio.nombre})"
        return f"{self.codigo} - {self.nombre}"


def validar_profesor_de_reserva(cedula):
    """Mensaje de error si `cedula` no es de un Profesor ACTIVO, o None si
    lo es. Regla de las reservas de curso (fase 2): solo profesores
    habilitados, buscados por cédula — ya no se busca una cuenta Docente por
    nombre. La usan SolicitudReserva.clean() y la reserva interna
    (reservas/views.py)."""
    cedula = (cedula or '').strip()
    profesor = Profesor.objects.filter(cedula=cedula).first() if cedula else None
    if profesor is None:
        return f'No hay un profesor habilitado con la cédula "{cedula}".'
    if not profesor.activo:
        return f'El profesor con la cédula "{cedula}" no está activo.'
    return None


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

        # Validación de profesor. Reserva de curso: solo un Profesor ACTIVO,
        # buscado por cédula (el profesor no tiene cuenta). La reserva libre
        # (profesor invitado) no exige estar registrado.
        if self.tipo_solicitante == 'profesor':
            if not self.nombre or not self.cedula:
                errors['nombre'] = 'Nombre y cédula son requeridos para profesores.'
            elif not self.reserva_libre:
                error_profesor = validar_profesor_de_reserva(self.cedula)
                if error_profesor:
                    errors['cedula'] = error_profesor

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
                elif self.tipo_solicitante == 'profesor' and self.cedula:
                    # Por cédula: el profesor ya no tiene cuenta (fase 2).
                    solicitudes_mismo_dia = solicitudes_mismo_dia.filter(
                        cedula=self.cedula,
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
                'Ya tienes 2 reservas aprobadas. Debes esperar a que se '
                'completen o sean canceladas antes de crear una nueva.'
            )

        veto = self.veto_activo()
        if veto is not None:
            from vetos.services import mensaje_bloqueo
            errors[NON_FIELD_ERRORS] = mensaje_bloqueo(veto)

        if errors:
            raise ValidationError(errors)

    def veto_activo(self):
        """El Veto vigente que le impide a este solicitante crear una nueva
        reserva, o None. Identifica al solicitante por cédula (estudiante) o
        por usuario (profesor), mismo criterio que
        limite_pendientes_alcanzado(). Solo aplica a solicitudes nuevas —
        editar una ya guardada no se bloquea."""
        if self.pk is not None:
            return None
        if not self.cedula and not self.usuario_id:
            return None
        from vetos.services import consultar_bloqueo
        return consultar_bloqueo(cedula=self.cedula or None, usuario=self.usuario)

    def limite_pendientes_alcanzado(self):
        """True si el solicitante (identificado por cédula, sea estudiante o
        profesor — mismo criterio que la validación de horas acumuladas por
        día de arriba) ya tiene 2 o más solicitudes
        cuya Reserva sigue en estado "Aprobada" (las reservas se aprueban
        automáticamente al crearse — ver crear_reserva() — así que ya no
        existe un estado "Pendiente" intermedio contra el cual contar). Solo
        aplica a solicitudes nuevas: una ya guardada no cuenta contra su
        propio límite."""
        if self.pk is not None:
            return False

        if self.tipo_solicitante == 'estudiante' and self.cedula:
            filtro = Q(cedula=self.cedula, tipo_solicitante='estudiante')
        elif self.tipo_solicitante == 'profesor' and self.cedula:
            filtro = Q(cedula=self.cedula, tipo_solicitante='profesor')
        else:
            return False

        return SolicitudReserva.objects.filter(
            filtro, reserva__estado__nombre='Aprobada'
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

        estado_aprobada = EstadoReserva.objects.filter(nombre='Aprobada').first()
        if not estado_aprobada:
            raise ValueError('No existe estado "Aprobada" en EstadoReserva')

        # Quién es el solicitante, para los choques del mismo día y laboratorio:
        # - profesor: NO tiene cuenta (fase 2). La Reserva no se liga a ningún
        #   Usuario (las cuentas Docente viejas siguen existiendo, inactivas,
        #   con codigo = cédula, y no deben volver a usarse). En reservas de
        #   curso se identifica por la cédula de la solicitud; la reserva libre
        #   (invitado) no tenía ni tiene este chequeo.
        # - estudiante: su cuenta, si tiene una con esa cédula (sin cambios).
        if self.tipo_solicitante == 'profesor':
            usuario = None
            identidad = (Q(solicitud__cedula=self.cedula, solicitud__tipo_solicitante='profesor')
                         if self.cedula and not self.reserva_libre else None)
        else:
            usuario = Usuario.objects.filter(codigo=self.cedula).first()
            identidad = Q(usuario_id=usuario.id) if usuario else None

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

        # Reserva.clean() ya bloquea solapamientos del mismo usuario en
        # CUALQUIER laboratorio (no puede estar en dos lugares a la vez);
        # estos chequeos adicionales viven acá, no ahí, porque es el único
        # punto con acceso a self.laboratorio_id — Reserva no sabe en qué
        # laboratorio queda hasta que su SolicitudReserva se guarda
        # (chicken-and-egg). Si el choque es en otro laboratorio, lo sigue
        # bloqueando el chequeo genérico de Reserva.clean() más abajo.
        if identidad is not None:
            fin = fecha_devolucion or fecha_base
            reservas_mismo_dia_mismo_lab = Reserva.objects.filter(
                identidad,
                solicitud__laboratorio_id=self.laboratorio_id,
                estado__nombre__in=['Aprobada', 'Pendiente'],
                fecha_reserva__date=fecha_base.date(),
            ).distinct()

            # Solapamiento horario en el mismo laboratorio: mensaje
            # específico ("a esa hora").
            for otra in reservas_mismo_dia_mismo_lab:
                otra_fin = otra.fecha_devolucion or otra.fecha_reserva
                if fecha_base < otra_fin and otra.fecha_reserva < fin:
                    raise ValidationError(
                        f'Ya tienes una reserva a esa hora en {self.laboratorio.nombre}.'
                    )

            # Máximo 1 reserva por día en el mismo laboratorio, aunque no se
            # solapen en horario (p. ej. 10-12 y 14-16 el mismo día siguen
            # bloqueadas). El for de arriba ya trajo y cacheó el queryset,
            # así que este chequeo no dispara una consulta adicional.
            if reservas_mismo_dia_mismo_lab:
                raise ValidationError(
                    f'Solo puedes hacer 1 reserva por día en {self.laboratorio.nombre}.'
                )

        reserva = Reserva(
            usuario=usuario,
            fecha_reserva=fecha_base,
            fecha_devolucion=fecha_devolucion,
            estado=estado_aprobada
        )
        reserva.full_clean()
        reserva.save()

        for solicitud_insumo in self.insumos.all():
            ReservaInsumo.objects.create(
                reserva=reserva,
                insumo=solicitud_insumo.insumo,
                cantidad=solicitud_insumo.cantidad
            )

        self.reserva = reserva
        self.save(update_fields=['reserva'])

        try:
            from utils.notificaciones_email import notificar_reserva_creada_aprobada
            notificar_reserva_creada_aprobada(self)
        except Exception:
            logger.exception(
                'crear_reserva | error notificando reserva creada/aprobada | solicitud_id=%s', self.id,
            )

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
    # Única solo entre solicitudes pendientes o aprobadas (ver Meta): después
    # de un rechazo, la misma cédula puede volver a solicitar.
    cedula = models.CharField(max_length=20)
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
    laboratorio_interes = models.ForeignKey(
        Laboratorio, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='solicitudes_registro_profesor',
    )
    resuelto_por = models.ForeignKey(
        'users.Usuario', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='solicitudes_profesor_resueltas',
    )
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    motivo_rechazo = models.TextField(blank=True, default='')
    profesor = models.ForeignKey(
        Profesor, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='solicitudes',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cedula'],
                condition=Q(estado__in=['pendiente', 'aprobada']),
                name='solicitud_profesor_cedula_activa_unica',
                violation_error_message='Ya existe una solicitud pendiente o aprobada con esta cédula.',
            ),
        ]

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
