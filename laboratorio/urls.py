from django.urls import path
from .views import (
    lista_laboratorios,
    crear_laboratorio,
    editar_laboratorio,
    detalle_laboratorio
)

urlpatterns = [
    path('', lista_laboratorios, name='lista_laboratorios'),
    path('crear/', crear_laboratorio, name='crear_laboratorio'),
    path('<int:id>/', detalle_laboratorio, name='detalle_laboratorio'),
    path('<int:id>/editar/', editar_laboratorio, name='editar_laboratorio'),
]