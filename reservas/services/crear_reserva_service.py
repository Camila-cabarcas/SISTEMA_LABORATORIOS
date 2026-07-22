"""
crear_reserva_service.py — reservas
Orquesta la creación de una Reserva a partir de una SolicitudReserva ya guardada.
"""
from django.core.exceptions import ValidationError

from reservas.models import EstadoReserva
from solicitudes.models import SolicitudReserva
from laboratorio.models import Modulo


class CrearReservaService:

    def ejecutar(self, solicitud_id, usuario, modulos_ids=None):
        try:
            solicitud = SolicitudReserva.objects.get(id=solicitud_id)
        except SolicitudReserva.DoesNotExist:
            raise ValidationError(f'La solicitud {solicitud_id} no existe.')

        if solicitud.reserva_id:
            raise ValidationError('Esta solicitud ya tiene una reserva asociada.')

        if modulos_ids and solicitud.necesita_modulo:
            modulos = Modulo.objects.filter(
                id__in=modulos_ids,
                laboratorio=solicitud.laboratorio
            )
            solicitud.modulos_asignados.set(modulos)

        reserva = solicitud.crear_reserva()

        # Reservas libres/de estudiante no tienen un Usuario vinculado en la
        # solicitud; usamos al usuario que ejecuta la acción como respaldo.
        if not reserva.usuario and usuario:
            reserva.usuario = usuario

        reserva.estado = EstadoReserva.objects.get(nombre='Aprobada')
        reserva.save()

        return reserva
