"""
urls.py — prestamos
Rutas de la app prestamos: listado, creación por reserva, detalle, cambio de estado y devolución.
"""
from django.urls import path
from .views import (
    lista_prestamos,
    crear_prestamo,
    detalle_prestamo,
    cambiar_estado_prestamo,
    marcar_devuelto
)

urlpatterns = [
    path('', lista_prestamos, name='lista_prestamos'),
    path('crear/', crear_prestamo, name='crear_prestamo'),
    path('<int:id>/', detalle_prestamo, name='detalle_prestamo'),
    path('<int:id>/estado/', cambiar_estado_prestamo, name='cambiar_estado_prestamo'),
    path('crear/<int:reserva_id>/', crear_prestamo, name='crear_prestamo'),
    path('<int:id>/devolver/', marcar_devuelto, name='marcar_devuelto'),
]
