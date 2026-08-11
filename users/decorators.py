"""
decorators.py — users
Decoradores que protegen vistas según el rol del usuario autenticado:
rol_requerido (control de acceso normal) y requiere_contrasena_admin
(control de acceso reforzado, con una segunda contraseña, para acciones
irreversibles como eliminar o desactivar registros).
"""
import logging

from django.shortcuts import redirect, render
from functools import wraps

logger_acceso_admin = logging.getLogger('acceso_admin')

# Roles reales del sistema (ver seed_e2e.py / users/models.py Rol) que
# pueden ejecutar acciones críticas. 'Encargado' no es un Rol propio en
# este sistema — el encargado de un laboratorio es un Usuario con
# rol='Laboratorio' (ver laboratorio.models.Laboratorio.encargados) —, así
# que "admin o encargado" se traduce aquí a estos dos nombres reales.
ROLES_ACCION_CRITICA = ('Administrador', 'Laboratorio')


def rol_requerido(*roles):
    def decorador(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.rol and request.user.rol.nombre in roles:
                return view_func(request, *args, **kwargs)
            return redirect('sin_permiso')
        return wrapper
    return decorador


def requiere_contrasena_admin(titulo_accion='Confirmar acción', get_contexto=None):
    """
    Exige la contraseña admin (distinta de la de login) antes de ejecutar
    la vista decorada — sin sesión temporal: cada solicitud vuelve a
    pedirla, no queda "recordada" entre acciones.

    Solo Administrador/Laboratorio pueden siquiera ver el formulario de
    contraseña; cualquier otro rol (o anónimo) recibe 403 de inmediato, sin
    llegar a ver el formulario ni la vista protegida.

    Args:
        titulo_accion: verbo que describe la acción ("Eliminar", "Desactivar"...),
            se muestra en el formulario de confirmación.
        get_contexto: función opcional `(request, *args, **kwargs) -> str` que
            describe QUÉ se va a afectar (p.ej. "Curso - Física 101"), para
            que quien confirma sepa exactamente sobre qué objeto está
            actuando antes de escribir la contraseña. Se evalúa ANTES de
            pedirla, con los mismos args/kwargs de la URL — típicamente una
            consulta de solo lectura al mismo objeto que la vista protegida
            vuelve a buscar por su cuenta (get_contexto NO reemplaza el
            get_object_or_404 de la vista, así que si el objeto no existe
            ésta debe seguir fallando con 404 normalmente). Si get_contexto
            lanza una excepción, se registra en el log y el formulario se
            muestra igual, sin el detalle del objeto, en vez de romper el
            flujo de confirmación por un problema que no es culpa de quien
            está confirmando.

    Los campos del POST original (si los había, p.ej. una acción que
    también necesita 'accion' o 'estado') se reenvían como campos ocultos
    en el formulario de contraseña, para que la vista protegida los siga
    viendo tal cual una vez confirmada la contraseña. Esto cubre vistas
    simples de una sola acción (eliminar, desactivar) de forma directa; una
    vista con varias acciones posibles elegidas en su propio GET (como
    aprobar_reserva) necesitaría además decidir esa acción ANTES de pedir
    la contraseña, así que no se decoró aquí — ver el resumen del cambio.

    Uso:
        @requiere_contrasena_admin(
            titulo_accion='Eliminar',
            get_contexto=lambda r, *a, **kw: f"Curso - {Curso.objects.get(id=kw['id']).nombre}",
        )
        def eliminar_curso(request, id):
            ...
    """
    def decorador(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            rol = request.user.rol.nombre if request.user.rol else None
            if rol not in ROLES_ACCION_CRITICA:
                logger_acceso_admin.warning(
                    'Acceso denegado: %s (rol=%s) intentó acceder a %s en %s',
                    request.user.username, rol, view_func.__name__, request.path,
                )
                return render(request, 'users/sin_permiso.html', status=403)

            contexto_objeto = None
            if get_contexto:
                try:
                    contexto_objeto = get_contexto(request, *args, **kwargs)
                except Exception:
                    logger_acceso_admin.warning(
                        'get_contexto falló para %s (args=%s kwargs=%s) — '
                        'se muestra el formulario sin detalle del objeto',
                        view_func.__name__, args, kwargs,
                    )

            etiqueta_registro = contexto_objeto or view_func.__name__

            campos_originales = {
                clave: valor for clave, valor in request.POST.items()
                if clave not in ('csrfmiddlewaretoken', 'admin_password')
            }

            contexto_base = {
                'titulo_accion': titulo_accion,
                'objeto': contexto_objeto,
                'campos_originales': campos_originales.items(),
            }

            if request.method == 'POST' and 'admin_password' in request.POST:
                password = request.POST.get('admin_password')

                if not request.user.tiene_admin_password():
                    logger_acceso_admin.warning(
                        '%s intentó %s (%s) pero no tiene contraseña admin configurada',
                        request.user.username, titulo_accion, etiqueta_registro,
                    )
                    return render(request, 'utils/confirmar_contrasena_admin.html', {
                        **contexto_base,
                        'error': 'Todavía no configuraste una contraseña admin. '
                                 'Ve a "Cambiar contraseña admin" para crearla.',
                    })

                if request.user.check_admin_password(password):
                    logger_acceso_admin.info(
                        'Acceso autorizado: %s realizó %s sobre %s en %s',
                        request.user.username, titulo_accion, etiqueta_registro, request.path,
                    )
                    return view_func(request, *args, **kwargs)

                logger_acceso_admin.warning(
                    'Contraseña admin INCORRECTA: %s intentó %s sobre %s en %s',
                    request.user.username, titulo_accion, etiqueta_registro, request.path,
                )
                return render(request, 'utils/confirmar_contrasena_admin.html', {
                    **contexto_base,
                    'error': 'Contraseña incorrecta.',
                })

            # GET, o primer POST todavía sin contraseña: mostrar el formulario.
            return render(request, 'utils/confirmar_contrasena_admin.html', contexto_base)
        return wrapper
    return decorador
