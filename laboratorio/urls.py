"""
urls.py — laboratorio
Rutas de la app laboratorio: CRUD de laboratorios, mapa de módulos, eventos y APIs de disponibilidad.
"""
from django.urls import path
from .views import (
    lista_laboratorios,
    crear_laboratorio,
    detalle_laboratorio,
    editar_laboratorio,
    eliminar_laboratorio,
    reservas_laboratorio,
    prestamos_laboratorio,
    disponibilidad_laboratorio,
    eventos_laboratorio,
    crear_evento,
    eliminar_evento,
    mapa_laboratorio,
    toggle_modulo,
    estado_modulos_api,
    modulos_disponibles_api,
    gestionar_encargados,
)

urlpatterns = [
    path('', lista_laboratorios, name='lista_laboratorios'),
    path('crear/', crear_laboratorio, name='crear_laboratorio'),
    path('<int:id>/', detalle_laboratorio, name='detalle_laboratorio'),
    path('<int:id>/editar/', editar_laboratorio, name='editar_laboratorio'),
    path('<int:id>/eliminar/', eliminar_laboratorio, name='eliminar_laboratorio'),
    path('<int:id>/reservas/', reservas_laboratorio, name='reservas_laboratorio'),
    path('<int:id>/prestamos/', prestamos_laboratorio, name='prestamos_laboratorio'),
    path('<int:id>/disponibilidad/', disponibilidad_laboratorio, name='disponibilidad_laboratorio'),
    path('<int:id>/eventos/', eventos_laboratorio, name='eventos_laboratorio'),
    path('<int:id>/eventos/crear/', crear_evento, name='crear_evento'),
    path('eventos/<int:id>/eliminar/', eliminar_evento, name='eliminar_evento'),
    path('<int:id>/mapa/', mapa_laboratorio, name='mapa_laboratorio'),
    path('<int:lab_id>/modulo/<int:mod_id>/toggle/', toggle_modulo, name='toggle_modulo'),
    path('<int:id>/modulos/estado/', estado_modulos_api, name='estado_modulos_api'),
    path('<int:id>/modulos/disponibles/', modulos_disponibles_api, name='modulos_disponibles_api'),
    path('<int:lab_id>/encargados/', gestionar_encargados, name='gestionar_encargados'),
]