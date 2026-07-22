from django.contrib import admin
from .models import Curso, SolicitudReserva, SolicitudInsumo


class SolicitudInsumoInline(admin.TabularInline):
    model = SolicitudInsumo
    extra = 1


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'profesor', 'cantidad_estudiantes']
    search_fields = ['codigo', 'nombre']


@admin.register(SolicitudReserva)
class SolicitudReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo_solicitante', 'usuario', 'nombre', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin')
    list_filter = ('tipo_solicitante', 'laboratorio', 'fecha_creacion', 'necesita_modulo')
    search_fields = ('nombre', 'cedula', 'usuario__username')
    readonly_fields = ('fecha_creacion',)
    inlines = [SolicitudInsumoInline]
    fieldsets = (
        ('Información General', {
            'fields': ('tipo_solicitante', 'usuario', 'fecha_creacion')
        }),
        ('Datos Profesor', {
            'fields': ('nombre', 'cedula', 'curso'),
            'classes': ('collapse',)
        }),
        ('Reserva', {
            'fields': ('laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin', 'necesita_modulo', 'observaciones', 'modulos_asignados')
        }),
    )
