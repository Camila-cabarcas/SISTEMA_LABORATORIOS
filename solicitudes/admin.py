from django.contrib import admin
from .models import Curso, SolicitudReserva


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'profesor', 'cantidad_estudiantes')
    search_fields = ('codigo', 'nombre')
    list_filter = ('profesor',)


@admin.register(SolicitudReserva)
class SolicitudReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo_solicitante', 'usuario', 'nombre', 'laboratorio', 'fecha_reserva')
    list_filter = ('tipo_solicitante', 'laboratorio', 'fecha_creacion')
    search_fields = ('nombre', 'cedula', 'usuario__username')
    readonly_fields = ('fecha_creacion',)
    fieldsets = (
        ('Información General', {
            'fields': ('tipo_solicitante', 'usuario', 'fecha_creacion')
        }),
        ('Datos Profesor', {
            'fields': ('nombre', 'cedula', 'curso'),
            'classes': ('collapse',)
        }),
        ('Reserva', {
            'fields': ('laboratorio', 'fecha_reserva', 'observaciones', 'modulos_asignados')
        }),
    )
