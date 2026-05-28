from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Reserva, ReservaInsumo, EstadoReserva
from .forms import ReservaForm, ReservaInsumoForm
from datetime import datetime
from laboratorio.models import HorarioLaboratorio
from django.http import JsonResponse
from datetime import datetime, timedelta


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def lista_reservas(request):

    rol = request.user.rol.nombre if request.user.rol else None

    if rol in ['Administrador', 'Encargado']:
        reservas = Reserva.objects.all().order_by('-fecha_creacion')
    else:
        reservas = Reserva.objects.filter(
            usuario=request.user
        ).order_by('-fecha_creacion')

    return render(
        request,
        'reservas/lista.html',
        {
            'reservas': reservas,
            'now': datetime.now()
        }
    )


@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def crear_reserva(request):

    if request.method == 'POST':

        form = ReservaForm(request.POST)

        if form.is_valid():

            fecha_reserva = form.cleaned_data['fecha_reserva']

            # Obtener el día de la semana en español
            dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            dia = dias[fecha_reserva.weekday()]
            hora = fecha_reserva.time()

            # Verificar si hay horario disponible
            horario_disponible = HorarioLaboratorio.objects.filter(
                dia=dia,
                hora_inicio__lte=hora,
                hora_fin__gte=hora,
                bloqueado=False
            ).exists()

            horario_bloqueado = HorarioLaboratorio.objects.filter(
                dia=dia,
                hora_inicio__lte=hora,
                hora_fin__gte=hora,
                bloqueado=True
            ).exists()

            if not horario_disponible or horario_bloqueado:
                form.add_error(
                    'fecha_reserva',
                    'No hay disponibilidad en el laboratorio para ese horario.'
                )
            else:
                reserva = form.save(commit=False)
                reserva.usuario = request.user
                rol = request.user.rol.nombre if request.user.rol else None
                if rol in ['Administrador', 'Encargado']:
                    reserva.estado = EstadoReserva.objects.get(nombre='Aprobada')
                else:
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

@rol_requerido('Administrador', 'Encargado')
def reservas_para_prestamo(request):

    reservas = Reserva.objects.filter(
        estado__nombre='Aprobada',
        prestamo__isnull=True
    ).order_by('-fecha_creacion')

    return render(
        request,
        'reservas/para_prestamo.html',
        {
            'reservas': reservas
        }
    )

@rol_requerido('Administrador', 'Encargado', 'Docente', 'Estudiante')
def horarios_disponibles(request):

    # Generar slots para las próximas 4 semanas
    slots = []
    hoy = datetime.now()

    dias_semana = {
        'lunes': 0, 'martes': 1, 'miercoles': 2,
        'jueves': 3, 'viernes': 4, 'sabado': 5
    }

    horarios = HorarioLaboratorio.objects.all()

    for semana in range(4):
        for horario in horarios:
            dia_num = dias_semana.get(horario.dia)
            if dia_num is None:
                continue

            # Calcular la fecha de ese día en esta semana
            dias_hasta = (dia_num - hoy.weekday()) % 7
            fecha = hoy + timedelta(days=dias_hasta + semana * 7)

            inicio = datetime.combine(fecha.date(), horario.hora_inicio)
            fin = datetime.combine(fecha.date(), horario.hora_fin)

            slots.append({
                'title': 'Bloqueado' if horario.bloqueado else 'Disponible',
                'start': inicio.strftime('%Y-%m-%dT%H:%M:%S'),
                'end': fin.strftime('%Y-%m-%dT%H:%M:%S'),
                'color': '#dc3545' if horario.bloqueado else '#28a745',
                'bloqueado': horario.bloqueado,
                'motivo': horario.motivo_bloqueo if horario.bloqueado else ''
            })

    return JsonResponse(slots, safe=False)