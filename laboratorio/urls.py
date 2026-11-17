"""
urls.py — laboratorio
Rutas de la app laboratorio: CRUD de laboratorios, mapa de módulos, eventos,
APIs de disponibilidad y la sección Personal (views_personal.py).
"""
from django.urls import path
from . import views_categorias, views_personal
from .views import (
    lista_laboratorios,
    crear_laboratorio,
    detalle_laboratorio,
    modal_items_insumo,
    editar_laboratorio,
    eliminar_laboratorio,
    reservas_laboratorio,
    prestamos_laboratorio,
    disponibilidad_laboratorio,
    eventos_laboratorio,
    crear_evento,
    eliminar_evento,
    mapa_laboratorio,
    editar_mapa_laboratorio,
    guardar_mapa_laboratorio,
    toggle_modulo,
    historial_modulo,
    estado_modulos_api,
    modulos_disponibles_api,
    modulos_disponibles_publica_api,
)

urlpatterns = [
    path('', lista_laboratorios, name='lista_laboratorios'),
    path('crear/', crear_laboratorio, name='crear_laboratorio'),
    path('categorias/', views_categorias.lista_categorias, name='lista_categorias_modulo'),
    path('categorias/crear/', views_categorias.crear_categoria, name='crear_categoria_modulo'),
    path('categorias/<int:id>/editar/', views_categorias.editar_categoria, name='editar_categoria_modulo'),
    path('categorias/<int:id>/toggle/', views_categorias.toggle_categoria, name='toggle_categoria_modulo'),
    path('categorias/<int:id>/eliminar/', views_categorias.eliminar_categoria, name='eliminar_categoria_modulo'),

    # Personal
    path('personal/', views_personal.lista_personal, name='personal'),
    path('personal/laboratoristas/crear/', views_personal.crear_laboratorista, name='crear_laboratorista'),
    path('personal/laboratoristas/<int:id>/editar/', views_personal.editar_laboratorista, name='editar_laboratorista'),
    path('personal/laboratoristas/<int:id>/baja/', views_personal.baja_laboratorista, name='baja_laboratorista'),
    path('personal/laboratoristas/<int:id>/eliminar/', views_personal.eliminar_laboratorista, name='eliminar_laboratorista'),
    path('personal/monitores/crear/', views_personal.crear_monitor, name='crear_monitor'),
    path('personal/monitores/<int:id>/editar/', views_personal.editar_monitor, name='editar_monitor'),
    path('personal/monitores/<int:id>/baja/', views_personal.baja_monitor, name='baja_monitor'),
    path('personal/fichas/crear/', views_personal.crear_ficha, name='crear_ficha'),
    path('personal/fichas/<int:id>/editar/', views_personal.editar_ficha, name='editar_ficha'),
    path('personal/fichas/<int:id>/quitar/', views_personal.quitar_ficha, name='quitar_ficha'),
    path('personal/fichas/<int:id>/vincular/', views_personal.vincular_ficha, name='vincular_ficha'),
    path('<int:lab_id>/descripcion/editar/', views_personal.editar_descripcion, name='editar_descripcion'),

    path('<int:id>/', detalle_laboratorio, name='detalle_laboratorio'),
    path('<int:lab_id>/insumos/<int:insumo_id>/items/', modal_items_insumo, name='modal_items_insumo'),
    path('<int:id>/editar/', editar_laboratorio, name='editar_laboratorio'),
    path('<int:id>/eliminar/', eliminar_laboratorio, name='eliminar_laboratorio'),
    path('<int:id>/reservas/', reservas_laboratorio, name='reservas_laboratorio'),
    path('<int:id>/prestamos/', prestamos_laboratorio, name='prestamos_laboratorio'),
    path('<int:id>/disponibilidad/', disponibilidad_laboratorio, name='disponibilidad_laboratorio'),
    path('<int:id>/eventos/', eventos_laboratorio, name='eventos_laboratorio'),
    path('<int:id>/eventos/crear/', crear_evento, name='crear_evento'),
    path('eventos/<int:id>/eliminar/', eliminar_evento, name='eliminar_evento'),
    path('<int:id>/mapa/', mapa_laboratorio, name='mapa_laboratorio'),
    path('<int:lab_id>/editar-mapa/', editar_mapa_laboratorio, name='editar_mapa'),
    path('<int:lab_id>/guardar-mapa/', guardar_mapa_laboratorio, name='guardar_mapa'),
    path('<int:lab_id>/modulo/<int:mod_id>/toggle/', toggle_modulo, name='toggle_modulo'),
    path('<int:lab_id>/modulo/<int:mod_id>/historial/', historial_modulo, name='historial_modulo'),
    path('<int:id>/modulos/estado/', estado_modulos_api, name='estado_modulos_api'),
    path('<int:id>/modulos/disponibles/', modulos_disponibles_api, name='modulos_disponibles_api'),
    path('<int:id>/modulos/disponibles-publica/', modulos_disponibles_publica_api, name='modulos_disponibles_publica_api'),
]
