from django.urls import path
from .views import (
    lista_laboratorios,
    crear_laboratorio,
    editar_laboratorio,
    detalle_laboratorio,
    eliminar_laboratorio,
    reservas_laboratorio,
    prestamos_laboratorio
)

urlpatterns = [
    path('', lista_laboratorios, name='lista_laboratorios'),
    path('crear/', crear_laboratorio, name='crear_laboratorio'),
    path('<int:id>/', detalle_laboratorio, name='detalle_laboratorio'),
    path('<int:id>/editar/', editar_laboratorio, name='editar_laboratorio'),
    path('<int:id>/eliminar/', eliminar_laboratorio, name='eliminar_laboratorio'),
    path('<int:id>/reservas/', reservas_laboratorio, name='reservas_laboratorio'),
    path('<int:id>/prestamos/', prestamos_laboratorio, name='prestamos_laboratorio'),
]