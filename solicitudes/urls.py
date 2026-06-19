"""
urls.py — solicitudes
Rutas de la app solicitudes: formularios públicos, APIs de insumos/cursos y gestión de cursos.
"""
from django.urls import path
from .views import (
    solicitud_estudiante,
    solicitud_profesor,
    lista_solicitudes,
    api_insumos,
    buscar_insumos,
    cursos_profesor,
    solicitud_exitosa,
    lista_cursos,
    crear_curso,
    editar_curso,
    eliminar_curso,
)

urlpatterns = [
    path('estudiante/', solicitud_estudiante, name='solicitud_estudiante'),
    path('profesor/', solicitud_profesor, name='solicitud_profesor'),
    path('exitosa/', solicitud_exitosa, name='solicitud_exitosa'),
    path('', lista_solicitudes, name='lista_solicitudes'),
    path('api/insumos/', api_insumos, name='api_insumos'),
    path('buscar-insumos/', buscar_insumos, name='buscar_insumos'),
    path('cursos-profesor/', cursos_profesor, name='cursos_profesor'),
    # Gestión de cursos
    path('cursos/', lista_cursos, name='lista_cursos'),
    path('cursos/crear/', crear_curso, name='crear_curso'),
    path('cursos/<int:id>/editar/', editar_curso, name='editar_curso'),
    path('cursos/<int:id>/eliminar/', eliminar_curso, name='eliminar_curso'),
]