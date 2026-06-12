from django.urls import path
from .views import (
    solicitud_estudiante,
    solicitud_profesor,
    lista_solicitudes,
    api_insumos,
    buscar_insumos,
    cursos_profesor,
    solicitud_exitosa,
)

urlpatterns = [
    path('estudiante/', solicitud_estudiante, name='solicitud_estudiante'),
    path('profesor/', solicitud_profesor, name='solicitud_profesor'),
    path('exitosa/', solicitud_exitosa, name='solicitud_exitosa'),
    path('', lista_solicitudes, name='lista_solicitudes'),
    path('api/insumos/', api_insumos, name='api_insumos'),
    path('buscar-insumos/', buscar_insumos, name='buscar_insumos'),
    path('cursos-profesor/', cursos_profesor, name='cursos_profesor'),
]