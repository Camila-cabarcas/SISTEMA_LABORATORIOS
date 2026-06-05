from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from users.decorators import rol_requerido
from inventario.models import Insumo
from .models import SolicitudReserva
from .forms import EstudianteSolicitudForm, ProfesorSolicitudForm


def solicitud_estudiante(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect('login')

        form = EstudianteSolicitudForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_solicitudes')
    else:
        user = request.user if request.user.is_authenticated else None
        form = EstudianteSolicitudForm(user)

    return render(
        request,
        'solicitudes/estudiante.html',
        {'form': form, 'is_anonymous': not request.user.is_authenticated}
    )


def solicitud_profesor(request):
    if request.method == 'POST':
        form = ProfesorSolicitudForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_solicitudes')
    else:
        form = ProfesorSolicitudForm()

    return render(
        request,
        'solicitudes/profesor.html',
        {'form': form}
    )


@login_required
def lista_solicitudes(request):
    solicitudes = SolicitudReserva.objects.all().order_by('-fecha_creacion')

    return render(
        request,
        'solicitudes/lista.html',
        {'solicitudes': solicitudes}
    )


def api_insumos(request):
    insumos = Insumo.objects.all()
    data = [
        {
            'id': i.id,
            'nombre': i.nombre,
            'cantidad_disponible': i.cantidad_disponible()
        }
        for i in insumos
    ]
    return JsonResponse(data, safe=False)
