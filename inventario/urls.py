"""
urls.py — inventario
Rutas de la app inventario: insumos, ítems físicos, movimientos e historial por ítem.
"""
from django.urls import path
from .views import (
    inicio,
    eliminar_insumo,
    editar_insumo,
    items_inventario,
    movimientos_inventario,
    historial_item,
    eliminar_item_inventario,
    ImportarInventarioView,
)

urlpatterns = [
    path('', inicio),
    path('eliminar/<int:id>/', eliminar_insumo),
    path('editar/<int:id>/', editar_insumo),
    path('items/', items_inventario),
    path('movimientos/', movimientos_inventario),
    path('items/<int:id>/historial/', historial_item),
    path('items/<int:id>/eliminar/', eliminar_item_inventario),
    path('importar/', ImportarInventarioView.as_view(), name='importar_inventario'),
]