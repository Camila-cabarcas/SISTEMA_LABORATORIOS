"""
urls.py — prestamos
Rutas de la app prestamos: listado, creación por reserva, detalle, cambio de estado
e inspección/devolución.
"""
from django.urls import path
from .views import (
    lista_prestamos,
    crear_prestamo,
    detalle_prestamo,
    cambiar_estado_prestamo,
    iniciar_inspeccion,
    inspeccionar_prestamo,
    marcar_devuelto,
    exportar_prestamos_excel,
    exportar_inspecciones_excel,
)

urlpatterns = [
    path('', lista_prestamos, name='lista_prestamos'),
    path('crear/', crear_prestamo, name='crear_prestamo'),
    path('exportar-excel/', exportar_prestamos_excel, name='exportar_prestamos_excel'),
    path('exportar-inspecciones-excel/', exportar_inspecciones_excel, name='exportar_inspecciones_excel'),
    path('<int:id>/', detalle_prestamo, name='detalle_prestamo'),
    path('<int:id>/estado/', cambiar_estado_prestamo, name='cambiar_estado_prestamo'),
    path('crear/<int:reserva_id>/', crear_prestamo, name='crear_prestamo'),
    path('<int:id>/iniciar-inspeccion/', iniciar_inspeccion, name='iniciar_inspeccion'),
    path('<int:id>/inspeccionar/', inspeccionar_prestamo, name='inspeccionar_prestamo'),
    path('<int:id>/marcar-devuelto/', marcar_devuelto, name='marcar_devuelto'),
]
