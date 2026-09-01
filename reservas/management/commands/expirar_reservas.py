"""
expirar_reservas.py — reservas
Management command que marca como "Expiradas" las reservas Pendiente cuya
hora_limite_retiro ya pasó.

LEGACY: antes también expiraba reservas Aprobada, porque una reserva nacía
Pendiente y quedaba así hasta que un laboratorista la aprobaba a mano — ese
"aprobada pero nadie la retiró" era un caso real. Desde que
SolicitudReserva.crear_reserva() aprueba automáticamente al crear (ver ese
método), toda reserva nueva nace directamente en "Aprobada" y el estado
"Pendiente" ya no lo genera el flujo normal — por eso este comando dejó de
tocar "Aprobada": bajo auto-aprobación ya no hay forma de distinguir "se
aprobó y no se retiró a tiempo" de "se aprobó y se está usando", así que
intentar expirarlas de nuevo terminaría cancelando reservas legítimas en uso.
El filtro por "Pendiente" se deja igual (no se toca EstadoReserva.Expirada
ni se borra el estado) por si alguna reserva vieja o creada por otra vía
(admin, importación) todavía queda en ese estado — es un no-op esperado en
el flujo normal de hoy, no un bug.
"""
from django.core.management.base import BaseCommand
from datetime import datetime
from reservas.models import Reserva, EstadoReserva


class Command(BaseCommand):

    help = 'Expira reservas Pendiente que pasaron su límite de retiro (legacy — ver docstring del módulo)'

    def handle(self, *args, **kwargs):

        estado_expirada = EstadoReserva.objects.get(nombre='Expirada')

        reservas_expiradas = Reserva.objects.filter(
            estado__nombre='Pendiente',
            hora_limite_retiro__lt=datetime.now()
        )

        cantidad = reservas_expiradas.count()

        reservas_expiradas.update(estado=estado_expirada)

        self.stdout.write(
            f'{cantidad} reservas expiradas.'
        )