from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Prestamo, PrestamoItem
from .forms import PrestamoForm, CambiarEstadoPrestamoForm, PrestamoItemForm
from .models import Prestamo, PrestamoItem, EstadoPrestamo


@login_required
def lista_prestamos(request):

    prestamos = Prestamo.objects.all().order_by('-fecha_entrega')

    return render(
        request,
        'prestamos/lista.html',
        {
            'prestamos': prestamos
        }
    )


@login_required
def crear_prestamo(request):

    if request.method == 'POST':

        form = PrestamoForm(request.POST)

        if form.is_valid():

            prestamo = form.save(commit=False)
            prestamo.estado = EstadoPrestamo.objects.get(nombre='Activo')
            prestamo.save()

            return redirect('detalle_prestamo', id=prestamo.pk)

    else:

        form = PrestamoForm()

    return render(
        request,
        'prestamos/crear.html',
        {
            'form': form
        }
    )


@login_required
def detalle_prestamo(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)
    items = PrestamoItem.objects.filter(prestamo=prestamo)

    if request.method == 'POST':

        form = PrestamoItemForm(request.POST)

        if form.is_valid():

            item_inventario = form.cleaned_data['item_inventario']

            # Verifica que el ítem no esté ya en este préstamo
            if PrestamoItem.objects.filter(
                prestamo=prestamo,
                item_inventario=item_inventario
            ).exists():
                form.add_error('item_inventario', 'Este ítem ya está en el préstamo.')

            else:
                item = form.save(commit=False)
                item.prestamo = prestamo
                item.save()
                return redirect('detalle_prestamo', id=prestamo.pk)

    else:

        form = PrestamoItemForm()

    return render(
        request,
        'prestamos/detalle.html',
        {
            'prestamo': prestamo,
            'items': items,
            'form': form
        }
    )


@login_required
def cambiar_estado_prestamo(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)

    if request.method == 'POST':

        form = CambiarEstadoPrestamoForm(request.POST, instance=prestamo)

        if form.is_valid():

            form.save()

            return redirect('detalle_prestamo', id=prestamo.pk)

    else:

        form = CambiarEstadoPrestamoForm(instance=prestamo)

    return render(
        request,
        'prestamos/cambiar_estado.html',
        {
            'prestamo': prestamo,
            'form': form
        }
    )