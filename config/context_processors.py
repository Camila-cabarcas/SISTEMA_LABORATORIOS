def notificaciones_admin(request):
    if not request.user.is_authenticated:
        return {}
    try:
        rol = request.user.rol.nombre
    except Exception:
        return {}
    if rol not in ('Administrador', 'Laboratorio'):
        return {}
    from solicitudes.models import SolicitudRegistroProfesor, SolicitudRegistroCurso
    return {
        'notif_profesores': SolicitudRegistroProfesor.objects.filter(
            estado='pendiente'
        ).count(),
        'notif_cursos': SolicitudRegistroCurso.objects.filter(
            estado='pendiente',
            solicitud_profesor__estado='aprobada'
        ).count(),
    }
