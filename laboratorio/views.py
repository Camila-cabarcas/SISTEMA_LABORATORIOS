from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Laboratorio
from .forms import LaboratorioForm
from inventario.models import ItemInventario


@rol_requerido('Administrador')
def lista_laboratorios(request):

    laboratorios = Laboratorio.objects.all()

    return render(
        request,
        'laboratorio/lista.html',
        {
            'laboratorios': laboratorios
        }
    )


@rol_requerido('Administrador')
def crear_laboratorio(request):

    if request.method == 'POST':

        form = LaboratorioForm(request.POST)

        if form.is_valid():

            form.save()

            return redirect('lista_laboratorios')

    else:

        form = LaboratorioForm()

    return render(
        request,
        'laboratorio/crear.html',
        {
            'form': form
        }
    )


@rol_requerido('Administrador', 'Encargado')
def detalle_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)
    items = ItemInventario.objects.filter(laboratorio=laboratorio)

    return render(
        request,
        'laboratorio/detalle.html',
        {
            'laboratorio': laboratorio,
            'items': items
        }
    )


@rol_requerido('Administrador')
def editar_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    if request.method == 'POST':

        form = LaboratorioForm(request.POST, instance=laboratorio)

        if form.is_valid():

            form.save()

            return redirect('lista_laboratorios')

    else:

        form = LaboratorioForm(instance=laboratorio)

    return render(
        request,
        'laboratorio/editar.html',
        {
            'form': form,
            'laboratorio': laboratorio
        }
    )