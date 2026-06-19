"""
urls.py — users
Rutas de la app users: gestión de usuarios y página de acceso denegado.
"""
from django.urls import path
from .views import (
    lista_usuarios,
    crear_usuario,
    editar_usuario,
    desactivar_usuario,
    sin_permiso
)

urlpatterns = [
    path('', lista_usuarios, name='lista_usuarios'),
    path('crear/', crear_usuario, name='crear_usuario'),
    path('<int:id>/editar/', editar_usuario, name='editar_usuario'),
    path('<int:id>/desactivar/', desactivar_usuario, name='desactivar_usuario'),
    path('sin-permiso/', sin_permiso, name='sin_permiso'),
]