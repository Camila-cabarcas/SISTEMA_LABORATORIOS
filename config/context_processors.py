def notificaciones_admin(request):
    """`notif_profesores`: solicitudes de profesor PENDIENTES que el usuario
    puede resolver (Administrador: todas; Laboratorista: las de su
    laboratorio y las sin laboratorio). El Monitor y los demás roles no ven
    el contador. (El contador de cursos pedidos en el registro se quitó en
    la fase 2: los cursos ya no entran por el registro.)"""
    if not request.user.is_authenticated:
        return {}
    from users.helpers import filtrar_solicitudes_profesor_visibles, puede_ver_solicitudes_profesor
    if not puede_ver_solicitudes_profesor(request.user):
        return {}
    from solicitudes.models import SolicitudRegistroProfesor
    pendientes = SolicitudRegistroProfesor.objects.filter(estado='pendiente')
    return {
        'notif_profesores': filtrar_solicitudes_profesor_visibles(request.user, pendientes).count(),
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
