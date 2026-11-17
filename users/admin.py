from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .forms import limitar_campo_rol
from .models import Usuario, Rol


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


admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Rol)
