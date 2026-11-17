def notificaciones_admin(request):
    if not request.user.is_authenticated:
        return {}
    try:
        rol = request.user.rol.nombre
    except Exception:
        return {}
    if rol not in ('Administrador', 'Laboratorista'):
        return {}
    from solicitudes.models import SolicitudRegistroProfesor, SolicitudRegistroCurso
    return {
        'notif_profesores': SolicitudRegistroProfesor.objects.filter(
            estado='pendiente'
        ).count(),
        'notif_cursos': SolicitudRegistroCurso.objects.filter(
            estado='pendiente'
        ).count(),
    }


def menu_personal(request):
    """`ver_personal`: si el menú muestra «Personal». Mismo criterio que la
    sección (users.helpers.puede_ver_personal): el Administrador siempre; el
    laboratorista si tiene laboratorio (el suyo); el Monitor y los demás
    roles nunca."""
    usuario = getattr(request, 'user', None)
    if usuario is None or not usuario.is_authenticated:
        return {'ver_personal': False}
    from users.helpers import es_administrador, es_laboratorista, puede_ver_personal
    if es_administrador(usuario):
        return {'ver_personal': True}
    if es_laboratorista(usuario):
        laboratorio = usuario.laboratorios_asignados.first()
        return {'ver_personal': laboratorio is not None and puede_ver_personal(usuario, laboratorio)}
    return {'ver_personal': False}
