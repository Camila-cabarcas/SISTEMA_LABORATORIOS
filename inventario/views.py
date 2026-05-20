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
        insumos = Insumo.objects.filter(nombre__icontains=busqueda)
    else:
        insumos = Insumo.objects.all()

    # Insumos con stock bajo
    alertas_stock = [
        insumo for insumo in Insumo.objects.all()
        if insumo.stock_minimo_alcanzado()
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

            item = form.save(commit=False)
            item.created_by = request.user  # Captura quién lo creó
            item.save()                     # El signal se dispara aquí

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

@login_required
def movimientos_inventario(request):

    if request.method == 'POST':

        form = MovimientoInventarioForm(request.POST)

        if form.is_valid():

            movimiento = form.save(commit=False)  # No guardes aún
            movimiento.usuario = request.user      # Asigna el usuario logueado
            movimiento.save()                      # Ahora sí guarda

            return redirect('/inventario/movimientos/')

    else:

        form = MovimientoInventarioForm()

    movimientos = MovimientoInventario.objects.all().order_by('-fecha')  # Más recientes primero

    return render(
        request,
        'inventario/movimientos.html',
        {
            'form': form,
            'movimientos': movimientos
        }
    )

@login_required # type: ignore
def editar_item(request, id):

    item = ItemInventario.objects.get(id=id)

    if request.method == 'POST':

        form = ItemInventarioForm(request.POST, instance=item)

        if form.is_valid():

            item = form.save(commit=False)
            item.updated_by = request.user  # Quién hizo el cambio
            item.save()  # El signal se dispara aquí

            return redirect('/inventario/items/')
        

@login_required
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