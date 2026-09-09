from django.contrib import admin
from django.utils import timezone

from .models import Veto


@admin.register(Veto)
class VetoAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'quien', 'get_tipo_display', 'estado', 'vigente',
        'fecha_inicio', 'fecha_fin', 'creado_por', 'fecha_creacion',
    )
    list_filter = ('tipo', 'estado', 'fecha_inicio')
    search_fields = ('cedula', 'usuario__username', 'usuario__first_name',
                     'usuario__last_name', 'motivo')
    readonly_fields = ('fecha_creacion', 'fecha_resolucion', 'resuelto_por')
    autocomplete_fields = ('usuario',)
    date_hierarchy = 'fecha_creacion'
    actions = ('accion_marcar_resuelto', 'accion_marcar_pagado')

    fieldsets = (
        ('Sancionado', {'fields': ('cedula', 'usuario')}),
        ('Infracción', {'fields': ('tipo', 'estado', 'motivo')}),
        ('Bloqueo', {'fields': ('fecha_inicio', 'fecha_fin')}),
        ('Origen', {'fields': ('reserva', 'prestamo')}),
        ('Auditoría', {'fields': ('creado_por', 'fecha_creacion',
                                  'resuelto_por', 'fecha_resolucion')}),
    )

    @admin.display(description='Sancionado')
    def quien(self, obj):
        return obj.usuario.username if obj.usuario_id else (obj.cedula or '—')

    @admin.display(boolean=True, description='¿Bloquea hoy?')
    def vigente(self, obj):
        return obj.esta_vigente

    def _resolver(self, request, queryset, pagado):
        n = 0
        for veto in queryset:
            if veto.estado == Veto.ACTIVO:
                veto.estado = Veto.PAGADO if pagado else Veto.RESUELTO
                veto.resuelto_por = request.user
                veto.fecha_resolucion = timezone.now()
                veto.save(update_fields=['estado', 'resuelto_por', 'fecha_resolucion'])
                n += 1
        self.message_user(request, f'{n} veto(s) actualizados.')

    @admin.action(description='Marcar como RESUELTO (levantar bloqueo)')
    def accion_marcar_resuelto(self, request, queryset):
        self._resolver(request, queryset, pagado=False)

    @admin.action(description='Marcar como PAGADO / repuesto (levantar bloqueo)')
    def accion_marcar_pagado(self, request, queryset):
        self._resolver(request, queryset, pagado=True)
