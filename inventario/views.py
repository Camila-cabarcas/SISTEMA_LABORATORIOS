from django.shortcuts import render, redirect
from django.db.models import Count, Q
from users.decorators import rol_requerido

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

    insumos = Insumo.objects.select_related('estado').annotate(
        cantidad_disponible_count=Count(
            'items',
            filter=Q(items__estado__nombre='Disponible')
        )
    )

    if busqueda:
        insumos = Insumo.objects.filter(nombre__icontains=busqueda)
    
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
def eliminar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)
    insumo.delete()
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


@rol_requerido('Administrador', 'Encargado')
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

    items = ItemInventario.objects.all()

    return render(
        request,
        'inventario/items.html',
        {
            'form': form,
            'items': items
        }
    )


@rol_requerido('Administrador', 'Encargado')
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

    movimientos = MovimientoInventario.objects.all().order_by('-fecha')

    return render(
        request,
        'inventario/movimientos.html',
        {
            'form': form,
            'movimientos': movimientos
        }
    )


@rol_requerido('Administrador', 'Encargado')
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


@rol_requerido('Administrador', 'Encargado')
def historial_item(request, id):

    item = ItemInventario.objects.get(id=id)

    movimientos = MovimientoInventario.objects.filter(
        item_inventario=item
    ).order_by('-fecha')

    return render(
        request,
        'inventario/historial_item.html',
        {
            'item': item,
            'movimientos': movimientos
        }
    )