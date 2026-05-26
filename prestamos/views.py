from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Prestamo, PrestamoItem, EstadoPrestamo
from .forms import PrestamoForm, CambiarEstadoPrestamoForm, PrestamoItemForm


@rol_requerido('Administrador', 'Encargado')
def lista_prestamos(request):

    prestamos = Prestamo.objects.all().order_by('-fecha_entrega')

    return render(
        request,
        'prestamos/lista.html',
        {
            'prestamos': prestamos
        }
    )


@rol_requerido('Administrador', 'Encargado')
def crear_prestamo(request, reserva_id):

    from reservas.models import Reserva
    from datetime import datetime

    reserva = get_object_or_404(Reserva, id=reserva_id)

    # Verifica que ya llegó la hora de la reserva
    if datetime.now() < reserva.fecha_reserva:
        return render(
            request,
            'prestamos/no_disponible.html',
            {
                'reserva': reserva
            }
        )

    if request.method == 'POST':

        form = PrestamoForm(request.POST)

        if form.is_valid():

            prestamo = form.save(commit=False)
            prestamo.reserva = reserva
            prestamo.estado = EstadoPrestamo.objects.get(nombre='Activo')
            prestamo.save()

            return redirect('detalle_prestamo', id=prestamo.pk)

    else:

        form = PrestamoForm()

    return render(
        request,
        'prestamos/crear.html',
        {
            'form': form,
            'reserva': reserva
        }
    )


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def detalle_prestamo(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)
    items = PrestamoItem.objects.filter(prestamo=prestamo)

    if request.method == 'POST':

        form = PrestamoItemForm(request.POST)

        if form.is_valid():

            item_inventario = form.cleaned_data['item_inventario']

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


@rol_requerido('Administrador', 'Encargado')
def cambiar_estado_prestamo(request, id):

    from datetime import datetime

    prestamo = get_object_or_404(Prestamo, id=id)

    if request.method == 'POST':

        form = CambiarEstadoPrestamoForm(request.POST, instance=prestamo)

        if form.is_valid():

            prestamo = form.save(commit=False)

            # Si se devuelve, registra la fecha real
            if prestamo.estado.nombre == 'Devuelto':
                prestamo.fecha_devolucion = datetime.now()

            prestamo.save()

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