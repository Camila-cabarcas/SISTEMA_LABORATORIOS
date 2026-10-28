"""
views_categorias.py — laboratorio
Gestión de categorías de módulo (CategoriaModulo), solo Administrador:
listar, crear, editar (nombre/color/forma), activar/desactivar y eliminar.

Eliminar solo se permite si la categoría no tiene módulos — Modulo.categoria
es PROTECT, así que la BD tampoco lo dejaría; para las que están en uso se
ofrece desactivarlas (dejan de ofrecerse al asignar, los módulos la conservan).
"""
import logging

from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from users.decorators import rol_requerido

from .forms import CategoriaModuloForm
from .models import CategoriaModulo

logger = logging.getLogger(__name__)

URL_LISTA = 'lista_categorias_modulo'


@rol_requerido('Administrador')
def lista_categorias(request):
    categorias = CategoriaModulo.objects.annotate(total_modulos=Count('modulos')).order_by('nombre')
    return render(request, 'laboratorio/categorias/lista.html', {'categorias': categorias})


@rol_requerido('Administrador')
def crear_categoria(request):
    form = CategoriaModuloForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        categoria = form.save()
        messages.success(request, f'Categoría "{categoria.nombre}" creada.')
        return redirect(URL_LISTA)
    return render(request, 'laboratorio/categorias/form.html', {'form': form, 'categoria': None})


@rol_requerido('Administrador')
def editar_categoria(request, id):
    categoria = get_object_or_404(CategoriaModulo, id=id)
    form = CategoriaModuloForm(request.POST or None, instance=categoria)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Categoría "{categoria.nombre}" actualizada.')
        return redirect(URL_LISTA)
    return render(request, 'laboratorio/categorias/form.html', {'form': form, 'categoria': categoria})


@rol_requerido('Administrador')
@require_POST
def toggle_categoria(request, id):
    categoria = get_object_or_404(CategoriaModulo, id=id)
    categoria.activo = not categoria.activo
    categoria.save(update_fields=['activo'])
    estado = 'activada' if categoria.activo else 'desactivada'
    messages.success(request, f'Categoría "{categoria.nombre}" {estado}.')
    return redirect(URL_LISTA)


@rol_requerido('Administrador')
@require_POST
def eliminar_categoria(request, id):
    categoria = get_object_or_404(CategoriaModulo, id=id)
    total = categoria.modulos.count()
    if total:
        messages.error(
            request,
            f'No se puede eliminar "{categoria.nombre}": tiene {total} módulo(s) asignado(s). '
            'Puedes desactivarla para que no se asigne a módulos nuevos.',
        )
        return redirect(URL_LISTA)
    try:
        categoria.delete()
    except ProtectedError:
        # Se le asignó un módulo entre el conteo y el borrado.
        messages.error(request, f'No se puede eliminar "{categoria.nombre}": tiene módulos asignados.')
        return redirect(URL_LISTA)
    logger.info('Categoría de módulo eliminada | usuario=%s | categoria=%s', request.user.username, categoria.nombre)
    messages.success(request, f'Categoría "{categoria.nombre}" eliminada.')
    return redirect(URL_LISTA)
