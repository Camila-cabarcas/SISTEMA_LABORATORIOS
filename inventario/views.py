"""
views.py — inventario
Vistas para gestionar insumos, ítems físicos, movimientos de inventario e historial por ítem.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Q
from users.decorators import rol_requerido, requiere_contrasena_admin

logger_acceso_admin = logging.getLogger('acceso_admin')

from .models import (
    Insumo,
    ItemInventario,
    MovimientoInventario
)

from .forms import (
    InsumoForm,
    ItemInventarioForm,
    MovimientoInventarioForm
)


@rol_requerido('Administrador')
def inicio(request):

    if request.method == 'POST':

        form = InsumoForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('/inventario/')

    else:
        form = InsumoForm()

    busqueda = request.GET.get('busqueda')

    insumos = Insumo.objects.select_related('estado', 'laboratorio').annotate(
        cantidad_disponible_count=Count(
            'items',
            filter=Q(items__estado__nombre='Disponible', items__deleted_at__isnull=True)
        )
    )

    if busqueda:
        insumos = insumos.filter(nombre__icontains=busqueda)
    
    alertas_stock = [
        insumo for insumo in insumos
        if insumo.stock_minimo > 0 and
        insumo.cantidad_disponible_count <= insumo.stock_minimo
    ]
    

    return render(
        request,
        'inventario/inicio.html',
        {
            'insumos': insumos,
            'form': form,
            'alertas_stock': alertas_stock
        }
    )


@rol_requerido('Administrador')
@requiere_contrasena_admin(
    titulo_accion='Eliminar',
    get_contexto=lambda r, *a, **kw: f"Insumo - {Insumo.objects.get(id=kw['id']).nombre}",
)
def eliminar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)
    nombre = insumo.nombre
    insumo.delete()
    messages.success(request, f'Insumo "{nombre}" eliminado.')
    return redirect('/inventario/')


@rol_requerido('Administrador')
def editar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)

    if request.method == 'POST':

        form = InsumoForm(request.POST, instance=insumo)

        if form.is_valid():
            form.save()
            return redirect('/inventario/')

    else:
        form = InsumoForm(instance=insumo)

    return render(
        request,
        'inventario/editar.html',
        {
            'form': form
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def items_inventario(request):

    if request.method == 'POST':

        form = ItemInventarioForm(request.POST)

        if form.is_valid():

            item = form.save(commit=False)
            item.updated_by = request.user
            item.save()

            return redirect('/inventario/items/')

    else:
        form = ItemInventarioForm()

    items = ItemInventario.activos.select_related(
        'insumo', 'estado', 'laboratorio',
    ).order_by('insumo__nombre', 'codigo')

    insumo_id = request.GET.get('insumo', '')
    if insumo_id:
        items = items.filter(insumo_id=insumo_id)

    # SQLite no soporta distinct(field_names) (eso es solo Postgres), así
    # que la última acción por ítem se arma a mano: se recorre ordenado por
    # fecha descendente y se queda solo la primera fila vista por ítem. Se
    # cuelga como atributo de cada item (en vez de un dict aparte) para que
    # el template la lea directo con item.ultimo_movimiento.
    ultimos_por_item = {}
    movimientos_recientes = MovimientoInventario.objects.filter(
        item_inventario__in=items,
    ).select_related('tipo_movimiento').order_by('-fecha')
    for m in movimientos_recientes:
        ultimos_por_item.setdefault(m.item_inventario_id, m)

    items = list(items)
    for item in items:
        item.ultimo_movimiento = ultimos_por_item.get(item.id)

    return render(
        request,
        'inventario/items.html',
        {
            'form': form,
            'items': items,
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def movimientos_inventario(request):

    if request.method == 'POST':

        form = MovimientoInventarioForm(request.POST)

        if form.is_valid():

            movimiento = form.save(commit=False)
            movimiento.usuario = request.user
            movimiento.save()

            return redirect('/inventario/movimientos/')

    else:
        form = MovimientoInventarioForm()

    movimientos = MovimientoInventario.objects.select_related(
        'item_inventario__insumo', 'item_inventario__laboratorio', 'usuario', 'tipo_movimiento',
    ).order_by('-fecha')

    insumo_id   = request.GET.get('insumo', '')
    lab_id      = request.GET.get('lab', '')
    usuario_id  = request.GET.get('usuario', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin    = request.GET.get('fecha_fin', '')

    if insumo_id:
        movimientos = movimientos.filter(item_inventario__insumo_id=insumo_id)
    if lab_id:
        movimientos = movimientos.filter(item_inventario__laboratorio_id=lab_id)
    if usuario_id:
        movimientos = movimientos.filter(usuario_id=usuario_id)
    if fecha_inicio:
        movimientos = movimientos.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        movimientos = movimientos.filter(fecha__date__lte=fecha_fin)

    from laboratorio.models import Laboratorio
    from users.models import Usuario

    return render(
        request,
        'inventario/movimientos.html',
        {
            'form': form,
            'movimientos': movimientos,
            'insumos': Insumo.objects.order_by('nombre'),
            'laboratorios': Laboratorio.objects.order_by('nombre'),
            'usuarios': Usuario.objects.filter(
                id__in=MovimientoInventario.objects.values_list('usuario_id', flat=True).distinct()
            ).order_by('username'),
            'insumo_id': insumo_id,
            'lab_id': lab_id,
            'usuario_id': usuario_id,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def editar_item(request, id):

    item = ItemInventario.objects.get(id=id)

    if request.method == 'POST':

        form = ItemInventarioForm(request.POST, instance=item)

        if form.is_valid():

            item = form.save(commit=False)
            item.updated_by = request.user
            item.save()

            return redirect('/inventario/items/')

    else:
        form = ItemInventarioForm(instance=item)

    return render(
        request,
        'inventario/editar_item.html',
        {
            'form': form,
            'item': item
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def historial_item(request, id):
    # .objects (no .activos): un ítem eliminado (soft-delete) debe seguir
    # siendo consultable acá — ese es justamente el punto de no borrarlo de
    # verdad.
    item = get_object_or_404(ItemInventario, id=id)

    prestamos = item.prestamoitem_set.select_related(
        'prestamo', 'prestamo__estado'
    ).prefetch_related('inspecciones').order_by('-id')

    movimientos = MovimientoInventario.objects.filter(
        item_inventario=item
    ).select_related('tipo_movimiento').order_by('-fecha')

    return render(
        request,
        'inventario/historial_item.html',
        {
            'item': item,
            'prestamos': prestamos,
            'movimientos': movimientos,
        }
    )


# requiere_contrasena_admin ya exige estar autenticado y tener rol
# Administrador/Laboratorio (ver users/decorators.py) — no hace falta
# apilar rol_requerido encima, a diferencia de eliminar_insumo, que ya
# traía su propio rol_requerido de antes y se dejó tal cual.
@requiere_contrasena_admin(
    titulo_accion='Eliminar',
    get_contexto=lambda r, *a, **kw: f"Item - {ItemInventario.objects.get(id=kw['id']).codigo}",
)
def eliminar_item_inventario(request, id):
    """
    Soft-delete de un ItemInventario: marca deleted_at en vez de borrar la
    fila. PrestamoItem/MovimientoInventario/InspeccionItem cuelgan de este
    ítem con on_delete=CASCADE — un delete() de verdad se llevaría por
    delante el historial de préstamos e inspecciones de este ítem
    específico, no solo el ítem. El soft-delete evita eso: el ítem
    desaparece de las listas y de la selección para nuevos préstamos, pero
    su historial sigue accesible en historial_item.
    """
    item = get_object_or_404(ItemInventario, id=id)

    if item.is_deleted():
        messages.info(request, f'Item "{item.codigo}" ya estaba eliminado.')
        return redirect('/inventario/items/')

    codigo = item.codigo
    insumo = item.insumo.nombre

    item.soft_delete()

    logger_acceso_admin.info(
        'Admin %s marcó como eliminado el item %s (%s)', request.user.username, codigo, insumo,
    )

    messages.success(request, f'Item "{codigo}" eliminado correctamente.')
    return redirect('/inventario/items/')