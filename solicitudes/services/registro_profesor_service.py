"""
registro_profesor_service.py — solicitudes
Registro público de profesor (fase 2): SolicitudRegistroProfesor es una
SOLICITUD SIN CUENTA. El profesor deja sus datos en un formulario público
(sin contraseña y sin cursos: los cursos vienen de la importación por cédula
de la fase 4). El Administrador, o el laboratorista del laboratorio de
interés (o de cualquiera si la solicitud no tiene laboratorio), la aprueba o
la rechaza.

- Aprobar crea o reactiva un Profesor con esa cédula. NO crea cuenta de
  usuario ni contraseña.
- Rechazar cambia el estado y guarda el motivo.
Ambos registran quién y cuándo, y avisan por correo al profesor si dejó
uno. Un error de correo NUNCA interrumpe la aprobación ni el rechazo.
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from solicitudes.models import Profesor, SolicitudRegistroProfesor
from users.helpers import puede_resolver_solicitud_profesor
from users.validators import validar_correo_institucional

logger = logging.getLogger(__name__)


class CrearSolicitudRegistroProfesorService:
    """Valida y crea una SolicitudRegistroProfesor (formulario público)."""

    @staticmethod
    def crear(*, nombre, apellido, cedula, correo, programa='', laboratorio_interes=None):
        """
        Args:
            laboratorio_interes: Laboratorio o None (opcional).

        Raises:
            ValidationError con la lista de mensajes de error.

        Returns:
            La SolicitudRegistroProfesor creada, en estado pendiente.
        """
        nombre, apellido = (nombre or '').strip(), (apellido or '').strip()
        cedula, correo, programa = (cedula or '').strip(), (correo or '').strip(), (programa or '').strip()
        errores = []

        if not nombre:
            errores.append('El nombre es requerido.')
        if not apellido:
            errores.append('El apellido es requerido.')
        if not correo:
            errores.append('El correo institucional es requerido.')
        else:
            try:
                validar_correo_institucional(correo)
            except ValidationError as e:
                errores.extend(e.messages)
        if not cedula:
            errores.append('La cédula es requerida.')
        elif not cedula.isdigit():
            errores.append('La cédula debe contener solo números.')
        elif SolicitudRegistroProfesor.objects.filter(
            cedula=cedula, estado__in=['pendiente', 'aprobada']
        ).exists():
            errores.append(f'Ya existe una solicitud pendiente o aprobada con la cédula {cedula}.')
        elif Profesor.objects.filter(cedula=cedula, activo=True).exists():
            errores.append(f'Ya hay un profesor habilitado con la cédula {cedula}.')

        if errores:
            raise ValidationError(errores)

        solicitud = SolicitudRegistroProfesor.objects.create(
            nombre=nombre, apellido=apellido, cedula=cedula, correo=correo, programa=programa,
            laboratorio_interes=laboratorio_interes,
        )
        logger.info('CrearSolicitudRegistroProfesorService.crear | solicitud_id=%s | cedula=%s',
                    solicitud.id, cedula)
        return solicitud


def _verificar(solicitud, usuario):
    if not puede_resolver_solicitud_profesor(usuario, solicitud):
        raise PermissionDenied('No puedes resolver esta solicitud de registro de profesor.')
    if solicitud.estado != 'pendiente':
        raise ValidationError('Esta solicitud ya fue procesada.')


def _avisar(funcion, solicitud):
    """Envía el correo después de confirmar la transacción; cualquier error
    queda solo en el log."""
    def enviar():
        try:
            funcion(solicitud)
        except Exception:
            logger.exception('%s | error enviando correo | solicitud_id=%s', funcion.__name__, solicitud.id)
    transaction.on_commit(enviar)


def aprobar_registro_profesor(solicitud, usuario):
    """Crea (o reactiva, si ya existe esa cédula) el Profesor, sin cuenta, y
    marca la solicitud como aprobada. Todo en una transacción.

    Raises:
        PermissionDenied: si `usuario` no puede resolver esta solicitud.
        ValidationError: si ya no está pendiente.
    """
    from utils.notificaciones_email import notificar_registro_profesor_aprobado

    with transaction.atomic():
        solicitud = SolicitudRegistroProfesor.objects.select_for_update().get(pk=solicitud.pk)
        _verificar(solicitud, usuario)

        profesor, creado = Profesor.objects.get_or_create(
            cedula=solicitud.cedula,
            defaults={'nombre': solicitud.nombre, 'apellido': solicitud.apellido},
        )
        profesor.nombre = solicitud.nombre
        profesor.apellido = solicitud.apellido
        profesor.correo = solicitud.correo
        profesor.programa = solicitud.programa
        profesor.activo = True
        if profesor.solicitud_origen_id is None:
            profesor.solicitud_origen = solicitud
        profesor.save()

        solicitud.profesor = profesor
        solicitud.estado = 'aprobada'
        solicitud.resuelto_por = usuario
        solicitud.fecha_resolucion = timezone.now()
        solicitud.save()

        _avisar(notificar_registro_profesor_aprobado, solicitud)

    logger.info('aprobar_registro_profesor | solicitud_id=%s | profesor_id=%s | %s',
                solicitud.id, profesor.id, 'creado' if creado else 'reactivado')
    return solicitud


def rechazar_registro_profesor(solicitud, usuario, motivo):
    """Marca la solicitud como rechazada con su motivo (obligatorio: se le
    envía al profesor). No crea Profesor.

    Raises:
        PermissionDenied: si `usuario` no puede resolver esta solicitud.
        ValidationError: si ya no está pendiente o falta el motivo.
    """
    from utils.notificaciones_email import notificar_registro_profesor_rechazado

    motivo = (motivo or '').strip()
    with transaction.atomic():
        solicitud = SolicitudRegistroProfesor.objects.select_for_update().get(pk=solicitud.pk)
        _verificar(solicitud, usuario)
        if not motivo:
            raise ValidationError('Escribe el motivo del rechazo.')

        solicitud.estado = 'rechazada'
        solicitud.motivo_rechazo = motivo
        solicitud.resuelto_por = usuario
        solicitud.fecha_resolucion = timezone.now()
        solicitud.save()

        _avisar(notificar_registro_profesor_rechazado, solicitud)

    logger.info('rechazar_registro_profesor | solicitud_id=%s', solicitud.id)
    return solicitud
