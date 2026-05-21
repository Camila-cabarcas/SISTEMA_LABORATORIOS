from django.shortcuts import redirect
from functools import wraps


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
