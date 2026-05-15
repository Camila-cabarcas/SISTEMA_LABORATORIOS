from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

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

@login_required
def inicio(request):

    if request.method == 'POST':

        form = InsumoForm(request.POST)

        if form.is_valid():

            form.save()

            return redirect('/inventario/')

    else:

        form = InsumoForm()

    busqueda = request.GET.get('busqueda')

    if busqueda:

        insumos = Insumo.objects.filter(
            nombre__icontains=busqueda
        )

    else:

        insumos = Insumo.objects.all()

    return render(
        request,
        'inventario/inicio.html',
        {
            'insumos': insumos,
            'form': form
        }
    )

            
@login_required
def eliminar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)

    insumo.delete()

    return redirect('/inventario/')


@login_required
def editar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)

    if request.method == 'POST':

        form = InsumoForm(
            request.POST,
            instance=insumo
        )

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

@login_required
def items_inventario(request):

    if request.method == 'POST':

        form = ItemInventarioForm(request.POST)

        if form.is_valid():

            movimiento = form.save(commit=False)

            movimiento.usuario = request.user

            movimiento.save()

            return redirect('/inventario/movimientos/')

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

@login_required
def movimientos_inventario(request):

    if request.method == 'POST':

        form = MovimientoInventarioForm(request.POST)

        if form.is_valid():

            form.save()

            return redirect('/inventario/movimientos/')

    else:

        form = MovimientoInventarioForm()

    movimientos = MovimientoInventario.objects.all()

    return render(
        request,
        'inventario/movimientos.html',
        {
            'form': form,
            'movimientos': movimientos
        }
    )