"""
urls.py — reservas
Rutas de la app reservas: listado, creación, detalle, aprobación, cancelación y horarios disponibles.
"""
from django.urls import path
from .views import (
    lista_reservas,
    crear_reserva,
    detalle_reserva,
    cancelar_reserva,
    aprobar_reserva,
    reservas_para_prestamo,
    horarios_disponibles,
    eliminar_insumo_reserva,
    exportar_reservas_excel,
)

urlpatterns = [
    path('', lista_reservas, name='lista_reservas'),
    path('crear/', crear_reserva, name='crear_reserva'),
    path('exportar-excel/', exportar_reservas_excel, name='exportar_reservas_excel'),
    path('para-prestamo/', reservas_para_prestamo, name='reservas_para_prestamo'),
    path('horarios/', horarios_disponibles, name='horarios_disponibles'),
    path('<int:id>/', detalle_reserva, name='detalle_reserva'),
    path('<int:id>/cancelar/', cancelar_reserva, name='cancelar_reserva'),
    path('<int:id>/aprobar/', aprobar_reserva, name='aprobar_reserva'),
    path('<int:reserva_id>/insumo/<int:insumo_id>/eliminar/', eliminar_insumo_reserva, name='eliminar_insumo_reserva'),
]