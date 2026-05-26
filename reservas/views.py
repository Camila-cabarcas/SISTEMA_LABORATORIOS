from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Reserva, ReservaInsumo, EstadoReserva
from .forms import ReservaForm, ReservaInsumoForm


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def lista_reservas(request):

    rol = request.user.rol.nombre if request.user.rol else None

    # Admin y Encargado ven todas las reservas
    if rol in ['Administrador', 'Encargado']:
        reservas = Reserva.objects.all().order_by('-fecha_creacion')
    else:
        # Docente y Estudiante solo ven las suyas
        reservas = Reserva.objects.filter(
            usuario=request.user
        ).order_by('-fecha_creacion')

    return render(
        request,
        'reservas/lista.html',
        {
            'reservas': reservas
        }
    )


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def crear_reserva(request):

    if request.method == 'POST':

        form = ReservaForm(request.POST)

        if form.is_valid():

            reserva = form.save(commit=False)
            reserva.usuario = request.user  # Asigna automáticamente
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


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
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


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
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


@rol_requerido('Administrador', 'Encargado')
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
