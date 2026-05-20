from django.urls import path
from .views import (
    lista_reservas,
    crear_reserva,
    detalle_reserva,
    cancelar_reserva,
    aprobar_reserva
)

urlpatterns = [
    path('', lista_reservas, name='lista_reservas'),
    path('crear/', crear_reserva, name='crear_reserva'),
    path('<int:id>/', detalle_reserva, name='detalle_reserva'),
    path('<int:id>/cancelar/', cancelar_reserva, name='cancelar_reserva'),
    path('<int:id>/aprobar/', aprobar_reserva, name='aprobar_reserva'),
]