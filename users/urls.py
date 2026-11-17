"""
urls.py — users
Rutas de la app users: gestión de usuarios, profesores y página de acceso denegado.
"""
from django.urls import path
from .views import (
    lista_usuarios,
    crear_usuario,
    editar_usuario,
    desactivar_usuario,
    sin_permiso,
    cambiar_contrasena_admin,
    lista_profesores,
    detalle_profesor,
    editar_profesor,
    desactivar_profesor,
    lista_programas,
    crear_programa,
    editar_programa,
    eliminar_programa,
)

urlpatterns = [
    path('', lista_usuarios, name='lista_usuarios'),
    path('crear/', crear_usuario, name='crear_usuario'),
    path('<int:id>/editar/', editar_usuario, name='editar_usuario'),
    path('<int:id>/desactivar/', desactivar_usuario, name='desactivar_usuario'),
    path('sin-permiso/', sin_permiso, name='sin_permiso'),
    path('cambiar-contrasena-admin/', cambiar_contrasena_admin, name='cambiar_contrasena_admin'),
    # Profesores habilitados (sin cuenta, solo Administrador)
    path('profesores/', lista_profesores, name='lista_profesores'),
    path('profesores/<int:id>/', detalle_profesor, name='detalle_profesor'),
    path('profesores/<int:id>/editar/', editar_profesor, name='editar_profesor'),
    path('profesores/<int:id>/desactivar/', desactivar_profesor, name='desactivar_profesor'),
    # Programas académicos
    path('programas/', lista_programas, name='lista_programas'),
    path('programas/crear/', crear_programa, name='crear_programa'),
    path('programas/<int:id>/editar/', editar_programa, name='editar_programa'),
    path('programas/<int:id>/eliminar/', eliminar_programa, name='eliminar_programa'),
]