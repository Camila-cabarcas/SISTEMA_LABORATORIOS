from django.urls import path
from .views import (
    lista_prestamos,
    crear_prestamo,
    detalle_prestamo,
    cambiar_estado_prestamo
)

urlpatterns = [
    path('', lista_prestamos, name='lista_prestamos'),
    path('crear/', crear_prestamo, name='crear_prestamo'),
    path('<int:id>/', detalle_prestamo, name='detalle_prestamo'),
    path('<int:id>/estado/', cambiar_estado_prestamo, name='cambiar_estado_prestamo'),
]
