"""
helpers.py — users
Control de acceso por laboratorio para las vistas de reservas/ y prestamos/
que un usuario rol='Laboratorio' solo debe poder ver/actuar sobre lo que
pertenece a su(s) laboratorio(s) — Administrador sigue viendo/actuando
sobre todo (ver docs/auditoria_seguridad_codigo.md, CRÍTICO #2).

No hay un campo Laboratorio.usuario_laboratorio ni una relación 1-a-1 entre
Usuario y Laboratorio: la real es Laboratorio.encargados (ManyToMany) — un
mismo Usuario rol='Laboratorio' puede ser encargado de más de un
laboratorio, y un laboratorio puede tener más de un encargado. Por eso
estos helpers reutilizan es_laboratorista_del_laboratorio
(laboratorio/models.py), la función que ya calcula esto correctamente y que
ya usan EditarInsumosReservaService y laboratorio/views.py::_check_lab_access
— no se reimplementa la lógica acá para no terminar con dos criterios de
"es laboratorista de este lab" que puedan divergir.

Tampoco se usa `Usuario.is_staff` para distinguir Administrador: ese flag de
Django no es el sistema de roles de esta app (ver users.models.Rol /
users.decorators.rol_requerido) — algunas cuentas Administrador lo tienen en
True por comodidad de acceso al admin de Django, pero no es la fuente de
verdad. La fuente de verdad es siempre `usuario.rol.nombre`.
"""
from django.core.exceptions import PermissionDenied

from laboratorio.models import Laboratorio, es_laboratorista_del_laboratorio


def es_administrador(usuario):
    return bool(
        usuario and usuario.is_authenticated and usuario.rol and usuario.rol.nombre == 'Administrador'
    )


def laboratorios_visibles(usuario):
    """None si `usuario` es Administrador — sin restricción, ve todo (el
    llamador debe interpretar None como "no filtrar"). Si no es
    Administrador, la lista de Laboratorio de los que es encargado.

    Raises:
        PermissionDenied: si no es Administrador y no tiene ningún
            laboratorio asignado — no tiene sentido mostrarle una lista
            vacía sin explicación quien de entrada no debería estar acá.
    """
    if es_administrador(usuario):
        return None

    labs = list(Laboratorio.objects.filter(encargados=usuario))
    if not labs:
        raise PermissionDenied('No tienes ningún laboratorio asignado.')
    return labs


def verificar_acceso_laboratorio(usuario, laboratorio):
    """Lanza PermissionDenied si `usuario` no puede operar sobre
    `laboratorio` — Administrador siempre puede; un usuario rol='Laboratorio'
    solo si `laboratorio` es uno de los suyos (o si `laboratorio` es None,
    p. ej. una Reserva sin SolicitudReserva vinculada — no hay forma de
    verificar pertenencia, así que se deniega por defecto)."""
    if es_administrador(usuario):
        return
    if not laboratorio or not es_laboratorista_del_laboratorio(usuario, laboratorio):
        raise PermissionDenied('No tienes acceso a este laboratorio.')


def laboratorio_de_reserva(reserva):
    """El Laboratorio de la SolicitudReserva vinculada a `reserva`, o None
    si no tiene ninguna (Reserva.solicitud es la relación inversa de
    SolicitudReserva.reserva, y puede no haber ninguna — p. ej. una Reserva
    creada directo en el admin)."""
    solicitud = reserva.solicitud.first()
    return solicitud.laboratorio if solicitud else None


def laboratorio_de_prestamo(prestamo):
    """El Laboratorio de la reserva de `prestamo` — ver laboratorio_de_reserva."""
    return laboratorio_de_reserva(prestamo.reserva)
