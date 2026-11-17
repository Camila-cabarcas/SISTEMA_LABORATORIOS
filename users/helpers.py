"""
helpers.py — users
Permisos por rol y control de acceso por laboratorio (ver
docs/auditoria_seguridad_codigo.md, CRÍTICO #2).

- Administrador: ve y actúa sobre todo.
- Laboratorista: solo en los laboratorios de Laboratorio.laboratoristas.
- Monitor: solo en los laboratorios de Laboratorio.monitores y, en reservas,
  solo las de estudiantes.

Una cuenta Laboratorista o Monitor está en un solo laboratorio (restricciones
de laboratorio.0024); un laboratorio puede tener varios laboratoristas y una
sola cuenta de monitor. Las relaciones siguen siendo ManyToMany, así que el
código que recorre "los laboratorios" de un usuario sigue sirviendo.
La pertenencia se calcula con es_laboratorista_del_laboratorio /
es_monitor_del_laboratorio (laboratorio/models.py) para no tener dos
criterios que puedan divergir.

No se usa `Usuario.is_staff` para distinguir Administrador: la fuente de
verdad es siempre `usuario.rol.nombre` (ver users/roles.py).
"""
from django.core.exceptions import PermissionDenied

from laboratorio.models import (
    Laboratorio,
    es_laboratorista_del_laboratorio,
    es_monitor_del_laboratorio,
)
from users.roles import (
    ADMINISTRADOR,
    LABORATORISTA,
    MONITOR,
    ROLES_ADMIN_PERSONAL,
    ROLES_DESCRIPCION_LAB,
    ROLES_FICHAS_MONITOR,
    ROLES_SOLICITUDES_PROFESOR,
    ROLES_SOLO_DESDE_PERSONAL,
)

TIPO_ESTUDIANTE = 'estudiante'


# ── Rol ──────────────────────────────────────────────────────────────────────

def nombre_rol(usuario):
    if not usuario or not usuario.is_authenticated or not usuario.rol:
        return None
    return usuario.rol.nombre


def es_administrador(usuario):
    return nombre_rol(usuario) == ADMINISTRADOR


def es_laboratorista(usuario):
    return nombre_rol(usuario) == LABORATORISTA


def es_monitor(usuario):
    return nombre_rol(usuario) == MONITOR


# ── Permisos por acción (los que no dependen solo del decorador) ────────────

def puede_gestionar_inventario(usuario):
    """Registrar ítems y movimientos. El Monitor solo consulta."""
    return es_administrador(usuario) or es_laboratorista(usuario)


def puede_importar_inventario(usuario):
    return es_administrador(usuario) or es_laboratorista(usuario)


def puede_importar_cursos(usuario):
    """Preparado para la importación de cursos (otra fase): mismos roles que
    la importación de inventario."""
    return es_administrador(usuario) or es_laboratorista(usuario)


def puede_aprobar_reservas(usuario):
    return es_administrador(usuario) or es_laboratorista(usuario)


# ── Personal ────────────────────────────────────────────────────────────────

def _en_su_laboratorio(usuario, laboratorio, roles):
    """True si el rol de `usuario` está en `roles` y, salvo el
    Administrador (que actúa en cualquier laboratorio), es laboratorista
    de `laboratorio`."""
    rol = nombre_rol(usuario)
    if rol not in roles:
        return False
    if rol == ADMINISTRADOR:
        return True
    return es_laboratorista_del_laboratorio(usuario, laboratorio)


def es_cuenta_de_personal(usuario):
    """Cuenta Laboratorista o Monitor (el usuario SOBRE el que se actúa, no
    quien actúa). Esas cuentas se dan de baja y se eliminan solo desde
    Personal (laboratorio/services/personal.py), que quita el laboratorio y
    protege los datos asociados: ni la pantalla genérica de usuarios ni el
    admin de Django las desactivan o borran directamente."""
    return bool(usuario is not None and getattr(usuario, 'rol_id', None)
                and usuario.rol.nombre in ROLES_SOLO_DESDE_PERSONAL)


def puede_administrar_personal(usuario):
    """Crear, editar y dar de baja cuentas de laboratorista y de monitor."""
    return nombre_rol(usuario) in ROLES_ADMIN_PERSONAL


def puede_ver_personal(usuario, laboratorio):
    """Sección Personal de `laboratorio`: el Administrador en cualquiera, el
    laboratorista en el suyo. El Monitor nunca."""
    return _en_su_laboratorio(usuario, laboratorio, ROLES_FICHAS_MONITOR)


def puede_gestionar_fichas(usuario, laboratorio):
    """Agregar, editar, vincular y quitar fichas de monitor en `laboratorio`."""
    return _en_su_laboratorio(usuario, laboratorio, ROLES_FICHAS_MONITOR)


def puede_editar_descripcion(usuario, laboratorio):
    """Editar Laboratorio.descripcion de `laboratorio`."""
    return _en_su_laboratorio(usuario, laboratorio, ROLES_DESCRIPCION_LAB)


# ── Solicitudes de registro de profesor ─────────────────────────────────────

def puede_ver_solicitudes_profesor(usuario):
    """Entrar a la lista de solicitudes de registro de profesor."""
    return nombre_rol(usuario) in ROLES_SOLICITUDES_PROFESOR


def puede_resolver_solicitud_profesor(usuario, solicitud):
    """Aprobar o rechazar `solicitud` (SolicitudRegistroProfesor):
    - Administrador: todas;
    - Laboratorista: las de su laboratorio de interés y las que no tienen
      laboratorio de interés;
    - Monitor y demás roles: ninguna."""
    if solicitud.laboratorio_interes_id is None:
        return puede_ver_solicitudes_profesor(usuario)
    return _en_su_laboratorio(usuario, solicitud.laboratorio_interes, ROLES_SOLICITUDES_PROFESOR)


def filtrar_solicitudes_profesor_visibles(usuario, solicitudes):
    """Restringe un queryset de SolicitudRegistroProfesor a las que
    `usuario` puede resolver (mismo criterio que
    puede_resolver_solicitud_profesor). Vacío si no puede ver ninguna."""
    from django.db.models import Q

    if es_administrador(usuario):
        return solicitudes
    if not puede_ver_solicitudes_profesor(usuario):
        return solicitudes.none()
    return solicitudes.filter(
        Q(laboratorio_interes__isnull=True) | Q(laboratorio_interes__laboratoristas=usuario)
    ).distinct()


# ── Acceso por laboratorio ──────────────────────────────────────────────────

def laboratorios_visibles(usuario):
    """None si `usuario` es Administrador — sin restricción, ve todo (el
    llamador debe interpretar None como "no filtrar"). Si es Laboratorista o
    Monitor, la lista de laboratorios donde está asignado con ese rol.

    Raises:
        PermissionDenied: si no es Administrador y no tiene ningún
            laboratorio asignado.
    """
    if es_administrador(usuario):
        return None

    if es_laboratorista(usuario):
        labs = list(Laboratorio.objects.filter(laboratoristas=usuario))
    elif es_monitor(usuario):
        labs = list(Laboratorio.objects.filter(monitores=usuario))
    else:
        labs = []

    if not labs:
        raise PermissionDenied('No tienes ningún laboratorio asignado.')
    return labs


def tiene_acceso_laboratorio(usuario, laboratorio):
    if es_administrador(usuario):
        return True
    return (
        es_laboratorista_del_laboratorio(usuario, laboratorio)
        or es_monitor_del_laboratorio(usuario, laboratorio)
    )


def verificar_acceso_laboratorio(usuario, laboratorio):
    """Lanza PermissionDenied si `usuario` no puede operar sobre
    `laboratorio` — Administrador siempre puede; Laboratorista o Monitor
    solo si `laboratorio` es uno de los suyos (si `laboratorio` es None,
    p. ej. una Reserva sin SolicitudReserva vinculada, no hay forma de
    verificar pertenencia y se deniega)."""
    if not tiene_acceso_laboratorio(usuario, laboratorio):
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


# ── Acceso a reservas (Monitor: solo de estudiantes) ────────────────────────

def es_reserva_de_estudiante(reserva):
    solicitud = reserva.solicitud.first()
    return bool(solicitud and solicitud.tipo_solicitante == TIPO_ESTUDIANTE)


def verificar_acceso_reserva(usuario, reserva):
    """Acceso por laboratorio y, para el Monitor, además que la reserva sea
    de un estudiante. Lanza PermissionDenied si no."""
    verificar_acceso_laboratorio(usuario, laboratorio_de_reserva(reserva))
    if es_monitor(usuario) and not es_reserva_de_estudiante(reserva):
        raise PermissionDenied('Solo puedes gestionar reservas de estudiantes.')


def filtrar_reservas_visibles(usuario, reservas):
    """Restringe un queryset de Reserva a lo que `usuario` puede ver: sus
    laboratorios (salvo Administrador) y, si es Monitor, solo las de
    estudiantes. Lanza PermissionDenied si no tiene laboratorios."""
    labs = laboratorios_visibles(usuario)
    if labs is not None:
        reservas = reservas.filter(solicitud__laboratorio__in=labs)
    if es_monitor(usuario):
        reservas = reservas.filter(solicitud__tipo_solicitante=TIPO_ESTUDIANTE)
    return reservas.distinct()
