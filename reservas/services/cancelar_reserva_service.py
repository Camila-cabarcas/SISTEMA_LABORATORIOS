"""
cancelar_reserva_service.py — reservas
Cancela una Reserva por dos caminos distintos, con reglas de negocio
distintas:

- cancelar_propietario: autoservicio del propio solicitante (identificado
  por cédula+email — ver solicitudes.services.mis_reservas_service), con
  las restricciones normales (Aprobada, sin Prestamo, al menos 2 horas antes
  de fecha_reserva).
- cancelar_admin: un laboratorista/Administrador cancela sin esas
  restricciones (por eso exige un motivo — es una anulación fuera de las
  reglas normales, y el motivo queda en el log y en el email al
  solicitante), para casos que el autoservicio no cubre (reserva ya venció
  su ventana de 2 horas, hay que corregir un error, etc.).

Cancelar solo cambia Reserva.estado — no toca ReservaInsumo ni
modulos_asignados. "Liberar capacidad para otros" no necesita código propio:
limite_pendientes_alcanzado() y los chequeos de solapamiento de Reserva.clean()
ya solo cuentan reservas en estado Aprobada/Pendiente, así que una reserva
Cancelada deja de contar automáticamente.
"""
import logging
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from reservas.models import EstadoReserva
from solicitudes.services.mis_reservas_service import MisReservasService

logger = logging.getLogger(__name__)


class CancelarReservaService:

    HORAS_LIMITE = 2

    @staticmethod
    def _validar_estado_y_prestamo(reserva):
        if not reserva.estado or reserva.estado.nombre != 'Aprobada':
            raise ValidationError('Solo se puede cancelar una reserva en estado Aprobada.')

        if reserva.prestamo_set.exists():
            raise ValidationError(
                'Esta reserva ya tiene un préstamo asociado; no se puede cancelar.'
            )

    @staticmethod
    def limite_cancelacion(reserva):
        """Momento a partir del cual el propietario ya no puede cancelar por
        su cuenta (HORAS_LIMITE antes de fecha_reserva)."""
        return reserva.fecha_reserva - timedelta(hours=CancelarReservaService.HORAS_LIMITE)

    @staticmethod
    def puede_cancelar_propietario(reserva):
        """True si un dueño identificado podría cancelar `reserva` ahora
        mismo (sin verificar todavía identidad ni cédula/email) — para
        decidir si mostrar el botón "Cancelar" en la UI."""
        try:
            CancelarReservaService._validar_estado_y_prestamo(reserva)
        except ValidationError:
            return False
        return timezone.now() < CancelarReservaService.limite_cancelacion(reserva)

    @staticmethod
    def cancelar_propietario(reserva, cedula, email):
        """Raises:
            PermissionDenied: cédula/email no coinciden con la solicitud.
            ValidationError: estado inválido, ya hay Prestamo, o ya pasó el
                límite de HORAS_LIMITE horas antes de fecha_reserva.
        """
        solicitud = reserva.solicitud.first()
        MisReservasService.verificar_propietario(solicitud, cedula, email)

        CancelarReservaService._validar_estado_y_prestamo(reserva)

        if timezone.now() >= CancelarReservaService.limite_cancelacion(reserva):
            raise ValidationError(
                f'Muy tarde para cancelar: debe hacerse con al menos '
                f'{CancelarReservaService.HORAS_LIMITE} horas de anticipación a la fecha de la reserva.'
            )

        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        logger.info(
            'CancelarReservaService.cancelar_propietario | reserva_id=%s | cedula=%s | '
            'cancelada por el propio solicitante',
            reserva.id, cedula,
        )

        try:
            from utils.notificaciones_email import notificar_cancelacion
            notificar_cancelacion(reserva, cancelada_por='estudiante')
        except Exception:
            logger.exception(
                'CancelarReservaService.cancelar_propietario | error notificando | reserva_id=%s',
                reserva.id,
            )

        return reserva

    @staticmethod
    def cancelar_admin(reserva, usuario, motivo):
        """Raises: ValidationError si no se indica motivo o la reserva ya
        está Cancelada (no tiene sentido "cancelar" dos veces)."""
        motivo = (motivo or '').strip()
        if not motivo:
            raise ValidationError('Debes indicar un motivo para cancelar la reserva.')

        if reserva.estado and reserva.estado.nombre == 'Cancelada':
            raise ValidationError('Esta reserva ya está Cancelada.')

        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        logger.info(
            'CancelarReservaService.cancelar_admin | reserva_id=%s | usuario=%s | motivo=%s',
            reserva.id, getattr(usuario, 'username', None), motivo,
        )

        try:
            from utils.notificaciones_email import notificar_cancelacion
            notificar_cancelacion(reserva, cancelada_por='laboratorista', motivo=motivo)
        except Exception:
            logger.exception(
                'CancelarReservaService.cancelar_admin | error notificando | reserva_id=%s',
                reserva.id,
            )

        return reserva
