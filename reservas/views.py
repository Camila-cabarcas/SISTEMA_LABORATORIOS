"""
views.py — reservas
Vistas para listar, crear manualmente, aprobar, cancelar y gestionar reservas e insumos asociados.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from users.decorators import rol_requerido
from .models import Reserva, ReservaInsumo, EstadoReserva
from .forms import ReservaForm, ReservaInsumoForm
from laboratorio.models import HorarioLaboratorio
from django.http import JsonResponse
from django.core.paginator import Paginator
from datetime import datetime, timedelta, date


@rol_requerido('Administrador', 'Laboratorio')
def lista_reservas(request):
    from django.utils import timezone
    from django.db.models import Q

    ahora = timezone.now()
    estado_expirada = EstadoReserva.objects.filter(nombre='Expirada').first()
    estado_pendiente = EstadoReserva.objects.filter(nombre='Pendiente').first()

    if estado_expirada and estado_pendiente:
        Reserva.objects.filter(
            estado=estado_pendiente,
            hora_limite_retiro__lt=ahora
        ).update(estado=estado_expirada)

    estado_filtro = request.GET.get('estado', '')
    cedula_filtro = request.GET.get('cedula', '').strip()
    tipo_filtro   = request.GET.get('tipo', '')
    fecha_inicio  = request.GET.get('fecha_inicio', '')
    fecha_fin     = request.GET.get('fecha_fin', '')
    reserva_libre = request.GET.get('reserva_libre', '')

    reservas = Reserva.objects.all().order_by('-fecha_reserva')

    if estado_filtro:
        reservas = reservas.filter(estado__nombre=estado_filtro)

    if cedula_filtro:
        reservas = reservas.filter(
            Q(usuario__codigo__icontains=cedula_filtro) |
            Q(solicitud__cedula__icontains=cedula_filtro)
        ).distinct()

    if tipo_filtro:
        reservas = reservas.filter(
            solicitud__tipo_solicitante=tipo_filtro
        ).distinct()

    if fecha_inicio:
        reservas = reservas.filter(fecha_reserva__date__gte=fecha_inicio)

    if fecha_fin:
        reservas = reservas.filter(fecha_reserva__date__lte=fecha_fin)

    if reserva_libre == '1':
        reservas = reservas.filter(solicitud__reserva_libre=True)

    paginator   = Paginator(reservas, 15)
    page_number = request.GET.get('page', 1)
    page_obj    = paginator.get_page(page_number)

    return render(request, 'reservas/lista.html', {
        'reservas':      page_obj,
        'page_obj':      page_obj,
        'now':           ahora,
        'estado_filtro': estado_filtro,
        'cedula_filtro': cedula_filtro,
        'tipo_filtro':   tipo_filtro,
        'fecha_inicio':  fecha_inicio,
        'fecha_fin':     fecha_fin,
        'reserva_libre': reserva_libre,
    })


@rol_requerido('Administrador', 'Laboratorio')
def crear_reserva(request):
    from solicitudes.models import SolicitudReserva, Curso
    from laboratorio.models import Laboratorio
    from users.models import Usuario
    from django.db.models import Q

    from users.models import ProgramaAcademico
    laboratorios = Laboratorio.objects.all()
    programas = ProgramaAcademico.objects.filter(activo=True)

    if request.method == 'POST':
        tipo          = request.POST.get('tipo_solicitante', 'estudiante')
        nombre        = request.POST.get('nombre', '').strip()
        cedula        = request.POST.get('cedula', '').strip()
        programa      = request.POST.get('programa', '').strip()
        curso_id      = request.POST.get('curso', '')
        lab_id        = request.POST.get('laboratorio', '')
        fecha_str     = request.POST.get('fecha', '')
        hora_ini      = request.POST.get('hora_inicio', '')
        hora_fin      = request.POST.get('hora_fin', '')
        necesita      = request.POST.get('necesita_modulo') == 'on'
        observaciones = request.POST.get('observaciones', '')

        errors = []

        if not nombre:    errors.append('El nombre es requerido.')
        if not cedula:    errors.append('La cédula es requerida.')
        if not lab_id:    errors.append('Selecciona un laboratorio.')
        if not fecha_str: errors.append('Selecciona una fecha.')
        if not hora_ini:  errors.append('Selecciona la hora de inicio.')
        if not hora_fin:  errors.append('Selecciona la hora de fin.')

        fecha_obj = hora_inicio_obj = hora_fin_obj = None

        if fecha_str:
            try:
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Fecha inválida.')

        if hora_ini:
            try:
                hora_inicio_obj = datetime.strptime(hora_ini, '%H:%M').time()
            except ValueError:
                errors.append('Hora inicio inválida.')

        if hora_fin:
            try:
                hora_fin_obj = datetime.strptime(hora_fin, '%H:%M').time()
            except ValueError:
                errors.append('Hora fin inválida.')

        if tipo == 'profesor' and fecha_obj:
            if fecha_obj <= date.today():
                errors.append('El profesor debe reservar con al menos un día de anticipación.')

        if not errors:
            laboratorio = Laboratorio.objects.filter(id=lab_id).first()
            if not laboratorio:
                errors.append('Laboratorio no válido.')

            curso = Curso.objects.filter(id=curso_id).first() if curso_id else None

            usuario = None
            if tipo == 'profesor' and nombre:
                partes = nombre.split()
                query  = Q()
                for p in partes:
                    query |= (Q(first_name__icontains=p) |
                              Q(last_name__icontains=p)  |
                              Q(username__icontains=p))
                usuario = Usuario.objects.filter(query, rol__nombre='Docente').first()

            if fecha_obj and hora_inicio_obj and not errors:
                fecha_dt = datetime.combine(fecha_obj, hora_inicio_obj)

                solicitud = SolicitudReserva(
                    tipo_solicitante=tipo,
                    nombre=nombre,
                    cedula=cedula,
                    programa=programa,
                    curso=curso,
                    usuario=usuario,
                    laboratorio=laboratorio,
                    fecha_reserva=fecha_dt,
                    hora_inicio=hora_inicio_obj,
                    hora_fin=hora_fin_obj,
                    necesita_modulo=necesita,
                    observaciones=observaciones,
                )

                try:
                    solicitud.save()
                    modulos_ids_str = request.POST.get('modulos_ids', '')
                    if modulos_ids_str:
                        from laboratorio.models import Modulo
                        ids = [int(x) for x in modulos_ids_str.split(',') if x.strip().isdigit()]
                        modulos = Modulo.objects.filter(id__in=ids, laboratorio=laboratorio)
                        solicitud.modulos_asignados.set(modulos)
                    reserva = solicitud.crear_reserva()
                    reserva.estado = EstadoReserva.objects.get(nombre='Aprobada')
                    reserva.save()
                    return redirect('detalle_reserva', id=reserva.pk)
                except Exception as e:
                    errors.append(str(e))

        return render(request, 'reservas/crear.html', {
            'errors': errors,
            'laboratorios': laboratorios,
            'programas': programas,
            'post_data': request.POST,
        })

    return render(request, 'reservas/crear.html', {
        'laboratorios': laboratorios,
        'programas': programas,
    })


@rol_requerido('Administrador', 'Laboratorio')
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

    return render(request, 'reservas/detalle.html', {
        'reserva': reserva,
        'insumos': insumos,
        'form':    form
    })


@rol_requerido('Administrador', 'Laboratorio')
def cancelar_reserva(request, id):
    reserva = get_object_or_404(Reserva, id=id)

    if request.method == 'POST':
        reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()
        return redirect('lista_reservas')

    return render(request, 'reservas/cancelar.html', {'reserva': reserva})


@rol_requerido('Administrador', 'Laboratorio')
def aprobar_reserva(request, id):
    reserva    = get_object_or_404(Reserva, id=id)
    solicitud  = reserva.solicitud.all().first()
    es_libre   = bool(solicitud and solicitud.reserva_libre)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'aprobar' and es_libre and request.user.rol.nombre != 'Administrador':
            return render(request, 'reservas/aprobar.html', {
                'reserva':     reserva,
                'es_libre':    es_libre,
                'error_libre': 'Esta reserva libre solo puede ser aprobada por un Administrador.',
            })

        if accion == 'aprobar':
            reserva.estado = EstadoReserva.objects.get(nombre='Aprobada')
        elif accion == 'cancelar':
            reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
        reserva.save()
        return redirect('detalle_reserva', id=reserva.pk)

    return render(request, 'reservas/aprobar.html', {
        'reserva':  reserva,
        'es_libre': es_libre,
    })


@rol_requerido('Administrador', 'Laboratorio')
def reservas_para_prestamo(request):
    ahora = datetime.now()
    reservas = Reserva.objects.filter(
        estado__nombre='Aprobada',
        prestamo__isnull=True,
        hora_limite_retiro__gt=ahora,
        fecha_reserva__lte=ahora
    ).order_by('-fecha_creacion')

    return render(request, 'reservas/para_prestamo.html', {'reservas': reservas})


@rol_requerido('Administrador', 'Laboratorio')
def horarios_disponibles(request):
    slots = []
    hoy   = datetime.now()

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
            dias_hasta = (dia_num - hoy.weekday()) % 7
            fecha  = hoy + timedelta(days=dias_hasta + semana * 7)
            inicio = datetime.combine(fecha.date(), horario.hora_inicio)
            fin    = datetime.combine(fecha.date(), horario.hora_fin)

            slots.append({
                'title':     'Bloqueado' if horario.bloqueado else 'Disponible',
                'start':     inicio.strftime('%Y-%m-%dT%H:%M:%S'),
                'end':       fin.strftime('%Y-%m-%dT%H:%M:%S'),
                'color':     '#dc3545' if horario.bloqueado else '#28a745',
                'bloqueado': horario.bloqueado,
                'motivo':    horario.motivo_bloqueo if horario.bloqueado else ''
            })

    return JsonResponse(slots, safe=False)


@rol_requerido('Administrador', 'Laboratorio')
def eliminar_insumo_reserva(request, reserva_id, insumo_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    insumo  = get_object_or_404(ReservaInsumo, id=insumo_id, reserva=reserva)

    if request.method == 'POST':
        insumo.delete()
        if not ReservaInsumo.objects.filter(reserva=reserva).exists():
            reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
            reserva.save()
            return redirect('lista_reservas')
        return redirect('detalle_reserva', id=reserva_id)

    return render(request, 'reservas/confirmar_eliminar_insumo.html', {
        'reserva': reserva,
        'insumo':  insumo
    })