from django.urls import path
from .views import (
    solicitud_estudiante,
    solicitud_profesor,
    lista_solicitudes,
    api_insumos,
    buscar_insumos
)

urlpatterns = [
    path('estudiante/', solicitud_estudiante, name='solicitud_estudiante'),
    path('profesor/', solicitud_profesor, name='solicitud_profesor'),
    path('', lista_solicitudes, name='lista_solicitudes'),
    path('api/insumos/', api_insumos, name='api_insumos'),
    path('buscar-insumos/', buscar_insumos, name='buscar_insumos'),
]
