from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Rol


class UsuarioAdmin(UserAdmin):
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