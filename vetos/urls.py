from django.urls import path

from . import views

app_name = 'vetos'

urlpatterns = [
    path('', views.lista_vetos, name='lista'),
    path('crear/', views.crear_veto, name='crear'),
    path('<int:id>/remover/', views.remover_veto, name='remover'),
]
