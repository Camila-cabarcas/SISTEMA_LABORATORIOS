from django.urls import path
from .views import (
    inicio,
    eliminar_insumo,
    editar_insumo,
    items_inventario,
    movimientos_inventario,
    historial_item
)

urlpatterns = [
    path('', inicio),
    path('eliminar/<int:id>/', eliminar_insumo),
    path('editar/<int:id>/', editar_insumo),
    path('items/', items_inventario),
    path('movimientos/', movimientos_inventario),
    path('items/<int:id>/historial/', historial_item),
]