from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from users.decorators import rol_requerido
from .models import Laboratorio, EventoLaboratorio
from .forms import LaboratorioForm
from inventario.models import ItemInventario
from reservas.models import ReservaInsumo
from prestamos.models import PrestamoItem


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


@rol_requerido('Administrador')
def eliminar_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    if request.method == 'POST':

        laboratorio.delete()
        return redirect('lista_laboratorios')

    return render(
        request,
        'laboratorio/eliminar.html',
        {
            'laboratorio': laboratorio
        }
    )


@rol_requerido('Administrador', 'Encargado')
def reservas_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    reservas_insumos = ReservaInsumo.objects.filter(
        insumo__items__laboratorio=laboratorio
    ).select_related('reserva', 'insumo').distinct()

    reservas = set()
    for ri in reservas_insumos:
        reservas.add(ri.reserva)

    return render(
        request,
        'laboratorio/reservas.html',
        {
            'laboratorio': laboratorio,
            'reservas': list(reservas)
        }
    )


@rol_requerido('Administrador', 'Encargado')
def prestamos_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    prestamos_items = PrestamoItem.objects.filter(
        item_inventario__laboratorio=laboratorio
    ).select_related('prestamo', 'item_inventario').distinct()

    prestamos = set()
    for pi in prestamos_items:
        prestamos.add(pi.prestamo)

    return render(
        request,
        'laboratorio/prestamos.html',
        {
            'laboratorio': laboratorio,
            'prestamos': list(prestamos)
        }
    )


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def disponibilidad_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    return render(
        request,
        'laboratorio/disponibilidad.html',
        {
            'laboratorio': laboratorio
        }
    )


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def eventos_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)
    eventos = EventoLaboratorio.objects.filter(laboratorio=laboratorio)

    data = []
    for evento in eventos:
        data.append({
            'id': evento.id,
            'title': evento.titulo,
            'start': evento.inicio.strftime('%Y-%m-%dT%H:%M:%S'),
            'end': evento.fin.strftime('%Y-%m-%dT%H:%M:%S'),
            'color': '#dc3545' if evento.bloqueado else '#28a745',
            'bloqueado': evento.bloqueado,
        })

    return JsonResponse(data, safe=False)


@rol_requerido('Administrador', 'Encargado', 'Docente')
def crear_evento(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    if request.method == 'POST':

        titulo = request.POST.get('titulo')
        inicio = request.POST.get('inicio')
        fin = request.POST.get('fin')
        bloqueado = request.POST.get('bloqueado') == 'true'

        EventoLaboratorio.objects.create(
            laboratorio=laboratorio,
            titulo=titulo,
            inicio=inicio,
            fin=fin,
            bloqueado=bloqueado,
            creado_por=request.user
        )

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Encargado', 'Docente')
def eliminar_evento(request, id):

    evento = get_object_or_404(EventoLaboratorio, id=id)

    if request.method == 'POST':
        evento.delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=400)