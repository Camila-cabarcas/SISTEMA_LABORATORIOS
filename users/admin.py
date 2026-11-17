from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .forms import limitar_campo_rol
from .helpers import es_cuenta_de_personal
from .models import Usuario, Rol

MENSAJE_SOLO_PERSONAL = ('cuentas de laboratorista o de monitor ({}): se dan de baja '
                         'o se eliminan desde Personal')


# Laboratorista y Monitor solo se asignan desde Personal (ver
# users.forms.limitar_campo_rol): el admin de Django no los ofrece y, si la
# cuenta ya los tiene, muestra el rol bloqueado.

class UsuarioAdminChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limitar_campo_rol(self)


class UsuarioAdminCreationForm(AdminUserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limitar_campo_rol(self)


class UsuarioAdmin(UserAdmin):
    form = UsuarioAdminChangeForm
    add_form = UsuarioAdminCreationForm

    fieldsets = UserAdmin.fieldsets + (  # type: ignore
        ('Información adicional', {
            'fields': ('codigo', 'programa', 'rol')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (  # type: ignore
        ('Información adicional', {
            'fields': ('codigo', 'programa', 'rol')
        }),
    )

    # ── Cuentas de Personal: sin borrado ni desactivación directos ─────────
    # Para las demás cuentas el admin funciona igual que siempre.

    def has_delete_permission(self, request, obj=None):
        if es_cuenta_de_personal(obj):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        campos = tuple(super().get_readonly_fields(request, obj))
        if es_cuenta_de_personal(obj):
            campos += ('is_active',)
        return campos

    def get_deleted_objects(self, objs, request):
        """También cubre la acción masiva «Eliminar seleccionados»: si la
        selección incluye cuentas de Personal, Django muestra que no se
        pueden borrar y rechaza el POST."""
        borrados, conteo, permisos_faltantes, protegidos = super().get_deleted_objects(objs, request)
        de_personal = [u.username for u in objs if es_cuenta_de_personal(u)]
        if de_personal:
            permisos_faltantes = set(permisos_faltantes)
            permisos_faltantes.add(MENSAJE_SOLO_PERSONAL.format(', '.join(sorted(de_personal))))
        return borrados, conteo, permisos_faltantes, protegidos


admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Rol)
