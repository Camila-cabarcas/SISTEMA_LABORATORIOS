"""
solicitud_reserva_service.py — solicitudes
Centraliza la lógica de negocio de SolicitudReserva que antes vivía dispersa
entre solicitudes/views.py (solicitud_estudiante, solicitud_profesor) y sus
forms: validación de la solicitud "libre" (el único flujo que no pasaba por
un ModelForm/SolicitudReserva.clean()), creación, y — sin vista propia
todavía, pero expuesto para un futuro cliente de API — aprobar/rechazar/
cancelar la Reserva asociada a una solicitud.
"""
import logging
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from inventario.models import Insumo
from laboratorio.models import Laboratorio, Modulo
from reservas.models import EstadoReserva
from solicitudes.models import SolicitudInsumo, SolicitudReserva
from users.models import Usuario

logger = logging.getLogger(__name__)


class ValidarSolicitudReservaService:
    """
    Valida los campos crudos (strings, tal como llegan de un formulario/POST)
    de una solicitud de reserva "libre" — el único flujo de solicitudes que
    hoy NO pasa por un ModelForm/SolicitudReserva.clean() y por eso
    duplicaba esta misma validación a mano dentro de la vista
    solicitud_profesor.

    Solo valida presencia/formato básico (lo que antes vivía en la lista
    `errores_libres` ANTES del bloque try/except de construcción). No
    valida existencia del laboratorio ni convierte fecha/hora — eso lo hace
    CrearSolicitudReservaService.crear_libre, que (igual que antes) deja que
    cualquier error de ahí en adelante se propague como una excepción
    genérica, no como un error de validación de campo.
    """

    @staticmethod
    def validar(*, nombre, cedula, email, nombre_grupo, cantidad_asistentes_str, descripcion,
                laboratorio_id, fecha_str, hora_inicio_str, hora_fin_str):
        """
        Raises:
            ValidationError con la lista de mensajes (mismos textos que
            mostraba la vista antes).
        """
        errores = []

        if not nombre:
            errores.append('El nombre del profesor es requerido.')
        if not cedula or not cedula.isdigit():
            errores.append('La cédula es requerida y debe contener solo números.')
        if not email:
            errores.append('El email institucional es requerido.')
        elif not email.lower().endswith('@udea.edu.co'):
            errores.append('El email debe ser institucional (@udea.edu.co).')
        if not nombre_grupo:
            errores.append('El nombre del grupo o actividad es requerido.')
        if not cantidad_asistentes_str or not cantidad_asistentes_str.isdigit() or int(cantidad_asistentes_str) < 1:
            errores.append('La cantidad de asistentes debe ser un número positivo.')
        if not descripcion:
            errores.append('La descripción de la actividad es requerida.')
        if not laboratorio_id:
            errores.append('Selecciona un laboratorio.')
        if not fecha_str:
            errores.append('Selecciona una fecha.')
        else:
            try:
                if datetime.strptime(fecha_str, '%Y-%m-%d').date() < date.today():
                    errores.append('La fecha de reserva no puede ser anterior a hoy.')
            except ValueError:
                errores.append('Fecha inválida.')
        if not hora_inicio_str:
            errores.append('Selecciona la hora de inicio.')
        if not hora_fin_str:
            errores.append('Selecciona la hora de fin.')

        if errores:
            raise ValidationError(errores)


class CrearSolicitudReservaService:
    """Crea una SolicitudReserva (y su Reserva asociada) para cada uno de
    los tres flujos de creación que hoy existen: estudiante, profesor con
    curso registrado, y profesor con actividad "libre" (sin curso)."""

    @staticmethod
    def crear_desde_estudiante(form, modulos_ids_str=''):
        """
        Args:
            form: EstudianteSolicitudForm ya validado (form.is_valid() == True).
            modulos_ids_str: valor crudo de 'modulos_ids' del POST (csv de
                ids; solo se usa el primero, igual que el flujo actual).

        Returns:
            (solicitud, reserva): reserva es None si crear_reserva() falla —
            se loguea el error y no se interrumpe el flujo, igual que hoy.
        """
        solicitud = form.save()

        if solicitud.necesita_modulo:
            ids = [int(x) for x in modulos_ids_str.split(',') if x.strip().isdigit()]
            if ids:
                modulos = Modulo.objects.filter(
                    id__in=ids[:1], laboratorio=solicitud.laboratorio, disponible=True,
                )
                solicitud.modulos_asignados.set(modulos)

        reserva = None
        try:
            reserva = solicitud.crear_reserva()
        except Exception as e:
            logger.error(
                "CrearSolicitudReservaService.crear_desde_estudiante | Error creando reserva | "
                "solicitud_id=%s | %s", solicitud.id, e,
            )

        return solicitud, reserva

    @staticmethod
    def crear_desde_profesor(form):
        """
        Args:
            form: ProfesorSolicitudForm ya validado. form.save() ya asigna
                insumos y módulos (ver ProfesorSolicitudForm._guardar_insumos/
                _asignar_modulos) y puede lanzar ValidationError si
                SolicitudReserva.clean() rechaza los datos — se deja
                propagar, la vista decide cómo mostrarlo.

        Returns:
            (solicitud, reserva): reserva es None si crear_reserva() falla
            (se loguea el error y no se interrumpe el flujo, igual que hoy).
        """
        solicitud = form.save()

        reserva = None
        try:
            reserva = solicitud.crear_reserva()
        except Exception as e:
            logger.error(
                "CrearSolicitudReservaService.crear_desde_profesor | Error creando reserva | "
                "solicitud_id=%s | %s", solicitud.id, e,
            )

        return solicitud, reserva

    @staticmethod
    @transaction.atomic
    def crear_libre(*, nombre, cedula, email, nombre_grupo, cantidad_asistentes_str, descripcion,
                     laboratorio_id, fecha_str, hora_inicio_str, hora_fin_str,
                     observaciones='', necesita_modulo=False,
                     modulos_ids_str='', insumos_ids_str='', insumos_cantidades_str=''):
        """
        Construye y guarda una SolicitudReserva "libre" (profesor invitado o
        actividad de grupo sin curso registrado) junto con sus módulos e
        insumos, y crea la Reserva asociada.

        Asume que ValidarSolicitudReservaService.validar ya pasó para estos
        mismos datos. No atrapa excepciones propias: cualquier error de aquí
        en adelante (laboratorio inexistente, formato de hora, etc.) se
        propaga tal cual — igual que en el código original, que envolvía
        todo este bloque en un único except genérico en la vista.

        Returns:
            (solicitud, reserva)
        """
        laboratorio = Laboratorio.objects.get(id=int(laboratorio_id))
        fecha_dt = datetime.strptime(fecha_str, '%Y-%m-%d')
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
        hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time()
        cantidad = int(cantidad_asistentes_str)

        partes = nombre.split()
        query = Q()
        for p in partes:
            query |= (Q(first_name__icontains=p) | Q(last_name__icontains=p) | Q(username__icontains=p))
        usuario = Usuario.objects.filter(query, rol__nombre='Docente').first()

        solicitud = SolicitudReserva(
            tipo_solicitante='profesor',
            nombre=nombre,
            cedula=cedula,
            email=email,
            programa=nombre_grupo,
            reserva_libre=True,
            descripcion_actividad=descripcion,
            cantidad_asistentes_libre=cantidad,
            laboratorio=laboratorio,
            fecha_reserva=fecha_dt,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            necesita_modulo=necesita_modulo,
            observaciones=observaciones,
            usuario=usuario,
        )

        # crear_libre no pasa por un ModelForm, así que SolicitudReserva.clean()
        # nunca se invoca aquí (ver docstring de la clase) — el límite de
        # solicitudes pendientes es una regla que sí queremos aplicar siempre,
        # así que se valida explícitamente en vez de agregar full_clean() acá
        # y arrastrar el resto de validaciones de clean() que este flujo
        # deliberadamente no aplica.
        if solicitud.limite_pendientes_alcanzado():
            raise ValidationError(
                'Ya tienes 2 reservas aprobadas. Debes esperar a que se '
                'completen o sean canceladas antes de crear una nueva.'
            )

        solicitud.save()

        if necesita_modulo:
            if modulos_ids_str:
                modulos_ids = [int(x) for x in modulos_ids_str.split(',') if x.strip().isdigit()]
                modulos = Modulo.objects.filter(id__in=modulos_ids, laboratorio=laboratorio, disponible=True)
            else:
                modulos = Modulo.objects.filter(laboratorio=laboratorio, disponible=True)[:cantidad]
            solicitud.modulos_asignados.set(modulos)

        if insumos_ids_str:
            ids = [int(x) for x in insumos_ids_str.split(',') if x.strip().isdigit()]
            cantidades = [int(x) for x in insumos_cantidades_str.split(',') if x.strip().isdigit()]
            for insumo_id, cant in zip(ids, cantidades):
                try:
                    insumo = Insumo.objects.get(id=insumo_id)
                    SolicitudInsumo.objects.create(solicitud=solicitud, insumo=insumo, cantidad=cant)
                except Insumo.DoesNotExist:
                    pass

        reserva = solicitud.crear_reserva()

        logger.info(
            "CrearSolicitudReservaService.crear_libre | solicitud_id=%s | reserva_id=%s",
            solicitud.id, reserva.id,
        )

        return solicitud, reserva


class AprobarSolicitudReservaService:
    """
    Aprueba la Reserva asociada a una SolicitudReserva.

    No existe hoy una vista de solicitudes que exponga esta acción —
    aprobar/cancelar hoy solo viven en reservas/views.py, operando
    directamente sobre la Reserva. Este service la expone a nivel de
    solicitud para que un futuro cliente de API que solo conoce el
    solicitud_id no necesite conocer el modelo Reserva por dentro. Replica
    la misma regla de negocio que reservas/views.py:aprobar_reserva: una
    reserva libre solo puede aprobarla un Administrador.
    """

    @staticmethod
    def aprobar(solicitud_id, usuario):
        try:
            solicitud = SolicitudReserva.objects.select_related('reserva__estado').get(id=solicitud_id)
        except SolicitudReserva.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_id} no existe.')

        if not solicitud.reserva:
            raise ValidationError('Esta solicitud todavía no tiene una reserva asociada.')

        if solicitud.reserva_libre and (not usuario.rol or usuario.rol.nombre != 'Administrador'):
            raise ValidationError('Esta reserva libre solo puede ser aprobada por un Administrador.')

        reserva = solicitud.reserva
        reserva.estado = EstadoReserva.objects.get(nombre='Aprobada')
        reserva.save()

        logger.info(
            "AprobarSolicitudReservaService.aprobar | solicitud_id=%s | reserva_id=%s | usuario=%s",
            solicitud.id, reserva.id, getattr(usuario, 'username', None),
        )

        from utils.notificaciones_email import notificar_reserva_aprobada
        notificar_reserva_aprobada(reserva)

        return reserva


class RechazarSolicitudReservaService:
    """
    Rechaza una SolicitudReserva cuya Reserva todavía está Pendiente.

    En este sistema no existe un estado 'Rechazada' separado de 'Cancelada'
    (ver reservas.models.EstadoReserva) — rechazar también deja la reserva
    en 'Cancelada', igual que CancelarSolicitudReservaService, pero se
    expone como una operación con nombre propio porque semánticamente es
    distinta (declinar algo que nunca se aprobó) y solo aplica si la reserva
    sigue Pendiente — a diferencia de cancelar, que no tiene esa restricción.
    """

    @staticmethod
    def rechazar(solicitud_id):
        try:
            solicitud = SolicitudReserva.objects.select_related('reserva__estado').get(id=solicitud_id)
        except SolicitudReserva.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_id} no existe.')

        if not solicitud.reserva:
            raise ValidationError('Esta solicitud todavía no tiene una reserva asociada.')

        if solicitud.reserva.estado.nombre != 'Pendiente':
            raise ValidationError('Solo se puede rechazar una solicitud cuya reserva está Pendiente.')

        reserva = solicitud.reserva
        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        logger.info(
            "RechazarSolicitudReservaService.rechazar | solicitud_id=%s | reserva_id=%s",
            solicitud.id, reserva.id,
        )

        return reserva


class CancelarSolicitudReservaService:
    """
    Cancela la Reserva asociada a una SolicitudReserva, sin importar su
    estado actual — replica reservas/views.py:cancelar_reserva (que no
    tiene ninguna restricción de estado previo), expuesto a nivel de
    solicitud.
    """

    @staticmethod
    def cancelar(solicitud_id):
        try:
            solicitud = SolicitudReserva.objects.select_related('reserva').get(id=solicitud_id)
        except SolicitudReserva.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_id} no existe.')

        if not solicitud.reserva:
            raise ValidationError('Esta solicitud todavía no tiene una reserva asociada.')

        reserva = solicitud.reserva
        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        logger.info(
            "CancelarSolicitudReservaService.cancelar | solicitud_id=%s | reserva_id=%s",
            solicitud.id, reserva.id,
        )

        return reserva
