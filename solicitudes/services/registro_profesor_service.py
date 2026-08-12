"""
registro_profesor_service.py — solicitudes
Centraliza la lógica de negocio de SolicitudRegistroProfesor y
SolicitudRegistroCurso que antes vivía dentro de solicitudes/views.py
(registro_profesor_publico, detalle_solicitud_profesor).
"""
import logging
import secrets

from django.core.exceptions import ValidationError

from solicitudes.models import Curso, SolicitudRegistroCurso, SolicitudRegistroProfesor
from users.models import Rol, Usuario

logger = logging.getLogger(__name__)


class CrearSolicitudRegistroProfesorService:
    """Valida y crea una SolicitudRegistroProfesor junto con los
    SolicitudRegistroCurso asociados — misma validación que antes vivía a
    mano en registro_profesor_publico."""

    @staticmethod
    def crear(*, nombre, apellido, cedula, correo, programa,
              nombres_curso, codigos_curso, cantidades_curso):
        """
        Args:
            nombres_curso, codigos_curso, cantidades_curso: listas paralelas
                (una fila por curso), tal como llegan de
                request.POST.getlist(...).

        Raises:
            ValidationError con la lista de mensajes de error.

        Returns:
            SolicitudRegistroProfesor ya creada, con sus cursos.
        """
        errores = []

        if not nombre:
            errores.append('El nombre es requerido.')
        if not apellido:
            errores.append('El apellido es requerido.')
        if not cedula:
            errores.append('La cédula es requerida.')
        elif not cedula.isdigit():
            errores.append('La cédula debe contener solo números.')
        elif SolicitudRegistroProfesor.objects.filter(
            cedula=cedula, estado__in=['pendiente', 'aprobada']
        ).exists():
            errores.append(f'Ya existe una solicitud pendiente o aprobada con la cédula {cedula}.')

        cursos_validos = []
        for i, (nombre_c, codigo_c, cantidad_c) in enumerate(
            zip(nombres_curso, codigos_curso, cantidades_curso), 1
        ):
            nombre_c = nombre_c.strip()
            codigo_c = codigo_c.strip()
            cantidad_c = cantidad_c.strip()
            if not nombre_c and not codigo_c and not cantidad_c:
                continue
            if not nombre_c:
                errores.append(f'Falta el nombre en el curso {i}.')
            elif not codigo_c:
                errores.append(f'Falta el código en el curso {i}.')
            elif not cantidad_c:
                errores.append(f'Falta la cantidad de estudiantes en el curso {i}.')
            elif not cantidad_c.isdigit() or int(cantidad_c) < 1:
                errores.append(f'La cantidad del curso {i} debe ser un número positivo.')
            else:
                cursos_validos.append({
                    'nombre': nombre_c,
                    'codigo': codigo_c,
                    'cantidad_estudiantes': int(cantidad_c),
                })

        if not cursos_validos and not [e for e in errores if 'curso' in e.lower()]:
            errores.append('Debes agregar al menos un curso.')

        if errores:
            raise ValidationError(errores)

        solicitud = SolicitudRegistroProfesor.objects.create(
            nombre=nombre, apellido=apellido, cedula=cedula, correo=correo, programa=programa,
        )
        for curso in cursos_validos:
            SolicitudRegistroCurso.objects.create(solicitud_profesor=solicitud, **curso)

        logger.info(
            "CrearSolicitudRegistroProfesorService.crear | solicitud_id=%s | cedula=%s | cursos=%s",
            solicitud.id, cedula, len(cursos_validos),
        )

        return solicitud


class AprobarSolicitudRegistroProfesorService:
    """Aprueba o rechaza una SolicitudRegistroProfesor pendiente. Aprobar
    crea el Usuario Docente correspondiente, con una contraseña aleatoria
    (el profesor no usa el sistema con esta cuenta directamente)."""

    @staticmethod
    def aprobar(solicitud_id):
        try:
            solicitud = SolicitudRegistroProfesor.objects.get(id=solicitud_id)
        except SolicitudRegistroProfesor.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_id} no existe.')

        if solicitud.estado != 'pendiente':
            raise ValidationError('Esta solicitud ya fue procesada.')

        cedula = solicitud.cedula
        base = f"doc_{cedula}"
        username = base
        counter = 2
        while Usuario.objects.filter(username=username).exists():
            username = f"{base}_{counter}"
            counter += 1

        usuario = Usuario(
            username=username,
            first_name=solicitud.nombre,
            last_name=solicitud.apellido,
            email=solicitud.correo,
            codigo=solicitud.cedula,
            programa=solicitud.programa,
            is_active=True,
        )
        usuario.set_password(secrets.token_urlsafe(16))
        usuario.rol = Rol.objects.filter(nombre='Docente').first()
        usuario.save()

        solicitud.usuario_creado = usuario
        solicitud.estado = 'aprobada'
        solicitud.save()

        logger.info(
            "AprobarSolicitudRegistroProfesorService.aprobar | solicitud_id=%s | usuario_id=%s",
            solicitud.id, usuario.id,
        )

        return solicitud

    @staticmethod
    def rechazar(solicitud_id):
        try:
            solicitud = SolicitudRegistroProfesor.objects.get(id=solicitud_id)
        except SolicitudRegistroProfesor.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_id} no existe.')

        if solicitud.estado != 'pendiente':
            raise ValidationError('Esta solicitud ya fue procesada.')

        solicitud.estado = 'rechazada'
        solicitud.save()
        solicitud.cursos_solicitados.update(estado='rechazada')

        logger.info("AprobarSolicitudRegistroProfesorService.rechazar | solicitud_id=%s", solicitud.id)

        return solicitud


class AprobarCursoService:
    """Aprueba o rechaza un SolicitudRegistroCurso individual de una
    solicitud de profesor ya aprobada. Aprobar crea el Curso real, asociado
    al Usuario Docente que dejó AprobarSolicitudRegistroProfesorService."""

    @staticmethod
    def aprobar(solicitud_profesor_id, curso_id):
        try:
            solicitud = SolicitudRegistroProfesor.objects.get(id=solicitud_profesor_id)
        except SolicitudRegistroProfesor.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_profesor_id} no existe.')

        if solicitud.estado != 'aprobada':
            raise ValidationError('La solicitud del profesor todavía no está aprobada.')

        try:
            solicitud_curso = SolicitudRegistroCurso.objects.get(id=curso_id, solicitud_profesor=solicitud)
        except SolicitudRegistroCurso.DoesNotExist:
            raise ValidationError(f'El curso {curso_id} no existe en esta solicitud.')

        if solicitud_curso.estado != 'pendiente' or not solicitud.usuario_creado:
            raise ValidationError('Este curso ya fue procesado.')

        curso = Curso.objects.create(
            nombre=solicitud_curso.nombre,
            codigo=solicitud_curso.codigo,
            cantidad_estudiantes=solicitud_curso.cantidad_estudiantes,
            profesor=solicitud.usuario_creado,
        )
        solicitud_curso.curso_creado = curso
        solicitud_curso.estado = 'aprobada'
        solicitud_curso.save()

        logger.info(
            "AprobarCursoService.aprobar | solicitud_curso_id=%s | curso_id=%s",
            solicitud_curso.id, curso.id,
        )

        return curso

    @staticmethod
    def rechazar(solicitud_profesor_id, curso_id):
        try:
            solicitud = SolicitudRegistroProfesor.objects.get(id=solicitud_profesor_id)
        except SolicitudRegistroProfesor.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_profesor_id} no existe.')

        if solicitud.estado != 'aprobada':
            raise ValidationError('La solicitud del profesor todavía no está aprobada.')

        try:
            solicitud_curso = SolicitudRegistroCurso.objects.get(id=curso_id, solicitud_profesor=solicitud)
        except SolicitudRegistroCurso.DoesNotExist:
            raise ValidationError(f'El curso {curso_id} no existe en esta solicitud.')

        if solicitud_curso.estado != 'pendiente':
            raise ValidationError('Este curso ya fue procesado.')

        solicitud_curso.estado = 'rechazada'
        solicitud_curso.save()

        logger.info("AprobarCursoService.rechazar | solicitud_curso_id=%s", solicitud_curso.id)

        return solicitud_curso
