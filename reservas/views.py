from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Reserva, ReservaInsumo, EstadoReserva
from .forms import ReservaForm, ReservaInsumoForm


@login_required
def lista_reservas(request):

    reservas = Reserva.objects.all().order_by('-fecha_creacion')

    return render(
        request,
        'reservas/lista.html',
        {
            'reservas': reservas
        }
    )


@login_required
def crear_reserva(request):

    if request.method == 'POST':

        form = ReservaForm(request.POST)

        if form.is_valid():

            reserva = form.save(commit=False)
            reserva.estado = EstadoReserva.objects.get(nombre='Pendiente')
            reserva.save()

            return redirect('detalle_reserva', id=reserva.pk)

    else:

        form = ReservaForm()

    return render(
        request,
        'reservas/crear.html',
        {
            'form': form
        }
    )


@login_required
def detalle_reserva(request, id):

    reserva = get_object_or_404(Reserva, id=id)
    insumos = ReservaInsumo.objects.filter(reserva=reserva)

    if request.method == 'POST':

        form = ReservaInsumoForm(request.POST)

        if form.is_valid():

            insumo = form.save(commit=False)
            insumo.reserva = reserva
            insumo.save()

            return redirect('detalle_reserva', id=reserva.pk)

    else:

        form = ReservaInsumoForm()

    return render(
        request,
        'reservas/detalle.html',
        {
            'reserva': reserva,
            'insumos': insumos,
            'form': form
        }
    )


@login_required
def cancelar_reserva(request, id):

    reserva = get_object_or_404(Reserva, id=id)

    if request.method == 'POST':

        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()

        return redirect('lista_reservas')

    return render(
        request,
        'reservas/cancelar.html',
        {
            'reserva': reserva
        }
    )

@login_required
def aprobar_reserva(request, id):

    reserva = get_object_or_404(Reserva, id=id)

    if request.method == 'POST':

        accion = request.POST.get('accion')

        if accion == 'aprobar':
            reserva.estado = EstadoReserva.objects.get(nombre='Aprobada')

        elif accion == 'cancelar':
            reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')

        reserva.save()

        return redirect('detalle_reserva', id=reserva.pk)

    return render(
        request,
        'reservas/aprobar.html',
        {
            'reserva': reserva
        }
    )