from django.urls import path
from .views import (
    lista_usuarios,
    crear_usuario,
    editar_usuario,
    desactivar_usuario
)

urlpatterns = [
    path('', lista_usuarios, name='lista_usuarios'),
    path('crear/', crear_usuario, name='crear_usuario'),
    path('<int:id>/editar/', editar_usuario, name='editar_usuario'),
    path('<int:id>/desactivar/', desactivar_usuario, name='desactivar_usuario'),
]