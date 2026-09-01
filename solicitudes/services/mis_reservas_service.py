"""
mis_reservas_service.py — solicitudes
Resuelve "¿esta persona es dueña de esta SolicitudReserva?" y busca todas
las solicitudes de una persona, para la sección de autoservicio "Mis
Reservas" (/solicitudes/) y las vistas de detalle/cancelación en reservas/.

No hay login de estudiante/profesor en este sistema (ver
solicitudes/views.py:solicitud_estudiante/solicitud_profesor — públicas,
anónimas): cédula es el único identificador que ya usa toda la app
(código de reserva, límite de solicitudes pendientes, etc.), pero por sí
sola es débil como "autenticación" (no es secreta). Por eso acá se exige
además el email registrado en la solicitud — el mismo que ya usa
utils.notificaciones_email para mandar los avisos — como segundo factor.
"""
from django.core.exceptions import PermissionDenied

from solicitudes.models import SolicitudReserva


class MisReservasService:

    @staticmethod
    def _emails_validos(solicitud):
        """Igual que utils.notificaciones_email._email_y_nombre: el email de
        la solicitud es la fuente preferida (obligatorio para estudiante y
        reserva libre); si no está, se acepta el de la cuenta Usuario del
        profesor (ProfesorSolicitudForm normal no pide email propio)."""
        emails = set()
        if solicitud.email:
            emails.add(solicitud.email.strip().lower())
        if solicitud.usuario and solicitud.usuario.email:
            emails.add(solicitud.usuario.email.strip().lower())
        return emails

    @staticmethod
    def es_propietario(solicitud, cedula, email):
        """True si `cedula` + `email` identifican a quien hizo `solicitud`."""
        if not solicitud:
            return False

        cedula = (cedula or '').strip()
        email = (email or '').strip().lower()
        if not cedula or not email:
            return False

        if (solicitud.cedula or '').strip() != cedula:
            return False

        return email in MisReservasService._emails_validos(solicitud)

    @staticmethod
    def verificar_propietario(solicitud, cedula, email):
        """Como es_propietario(), pero lanza PermissionDenied en vez de
        devolver False — para usar como guardia al inicio de una vista o de
        una acción (cancelar, etc.)."""
        if not MisReservasService.es_propietario(solicitud, cedula, email):
            raise PermissionDenied(
                'La cédula y el email no coinciden con esta reserva.'
            )

    @staticmethod
    def buscar(cedula, email):
        """Todas las SolicitudReserva de `cedula` que además tengan `email`
        entre sus emails válidos (ver _emails_validos) y ya tengan una
        Reserva asociada (crear_reserva() pudo fallar y dejarla sin una —
        "Mis Reservas" es sobre reservas, no sobre solicitudes crudas).
        Devuelve una lista (no queryset) porque el segundo filtro es en
        Python — no hay forma directa de expresar "coincide con
        solicitud.email O con solicitud.usuario.email" sin duplicar la
        resolución que ya vive en _emails_validos/utils.notificaciones_email."""
        cedula = (cedula or '').strip()
        email = (email or '').strip().lower()
        if not cedula or not email:
            return []

        candidatas = SolicitudReserva.objects.filter(
            cedula=cedula, reserva__isnull=False,
        ).select_related(
            'reserva__estado', 'laboratorio', 'usuario',
        ).order_by('-fecha_creacion')

        return [s for s in candidatas if email in MisReservasService._emails_validos(s)]
