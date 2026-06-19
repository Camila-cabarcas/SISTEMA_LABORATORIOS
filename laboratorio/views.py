"""
views.py — laboratorio
Vistas para gestionar laboratorios, eventos, mapa visual de módulos y APIs de estado en tiempo real.
"""
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


@rol_requerido('Administrador', 'Encargado')
def disponibilidad_laboratorio(request, id):

    laboratorio = get_object_or_404(Laboratorio, id=id)

    return render(
        request,
        'laboratorio/disponibilidad.html',
        {
            'laboratorio': laboratorio
        }
    )


@rol_requerido('Administrador', 'Encargado')
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


@rol_requerido('Administrador', 'Encargado')
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


@rol_requerido('Administrador', 'Encargado')
def eliminar_evento(request, id):

    evento = get_object_or_404(EventoLaboratorio, id=id)

    if request.method == 'POST':
        evento.delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Encargado')
def mapa_laboratorio(request, id):
    from datetime import date, datetime, time
    from solicitudes.models import SolicitudReserva

    laboratorio = get_object_or_404(Laboratorio, id=id)

    fecha_str       = request.GET.get('fecha', '')
    hora_inicio_str = request.GET.get('hora_inicio', '')
    hora_fin_str    = request.GET.get('hora_fin', '')

    filtro_valido = True
    error_filtro  = ''

    # Validar que los tres parámetros estén presentes
    if not (fecha_str and hora_inicio_str and hora_fin_str):
        filtro_valido = False
        if fecha_str or hora_inicio_str or hora_fin_str:
            error_filtro = "Debes seleccionar fecha, hora de inicio y hora de fin para ver el mapa."

    # Parsear fecha
    fecha = date.today()
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            filtro_valido = False
            error_filtro  = "Formato de fecha inválido."

    # Parsear horas
    hora_inicio_filtro = None
    hora_fin_filtro    = None
    if filtro_valido:
        try:
            if hora_inicio_str:
                h, m = hora_inicio_str.split(':')
                hora_inicio_filtro = time(int(h), int(m))
            if hora_fin_str:
                h, m = hora_fin_str.split(':')
                hora_fin_filtro = time(int(h), int(m))
        except (ValueError, AttributeError):
            filtro_valido = False
            error_filtro  = "Formato de hora inválido."

    # Validar hora_fin > hora_inicio
    if filtro_valido and hora_inicio_filtro and hora_fin_filtro:
        if hora_fin_filtro <= hora_inicio_filtro:
            filtro_valido = False
            error_filtro  = "La hora de fin debe ser posterior a la hora de inicio."

    modulos_data = []
    if filtro_valido:
        solicitudes = SolicitudReserva.objects.filter(
            laboratorio=laboratorio,
            fecha_reserva__date=fecha,
            reserva__estado__nombre__in=['Pendiente', 'Aprobada'],
            necesita_modulo=True,
        ).select_related(
            'reserva__estado', 'usuario'
        ).prefetch_related('modulos_asignados').filter(
            hora_inicio__lt=hora_fin_filtro,
            hora_fin__gt=hora_inicio_filtro,
        )

        modulo_solicitudes = {}
        for sol in solicitudes:
            for modulo in sol.modulos_asignados.all():
                modulo_solicitudes.setdefault(modulo.id, []).append(sol)

        for modulo in laboratorio.modulos.all():
            soles = modulo_solicitudes.get(modulo.id, [])

            if not modulo.disponible:
                estado         = 'inactivo'
                color          = 'secondary'
                solicitud_info = None
                motivo         = modulo.motivo_no_disponible

            elif soles:
                sol_activa = None
                for sol in soles:
                    if (sol.reserva and sol.reserva.estado
                            and sol.reserva.estado.nombre == 'Aprobada'):
                        sol_activa = sol
                        break

                sol_relevante = sol_activa if sol_activa else soles[0]
                estado = 'ocupado' if sol_activa else 'reservado'
                color  = 'danger'  if sol_activa else 'warning'
                motivo = ''

                if sol_relevante.nombre:
                    nombre_sol = sol_relevante.nombre
                elif sol_relevante.usuario:
                    nombre_sol = sol_relevante.usuario.get_full_name() or sol_relevante.usuario.username
                else:
                    nombre_sol = 'Desconocido'

                estado_reserva = (
                    sol_relevante.reserva.estado.nombre
                    if sol_relevante.reserva and sol_relevante.reserva.estado
                    else '—'
                )

                from prestamos.models import Prestamo
                prestamo_info = None
                if sol_activa and sol_activa.reserva:
                    prestamo = Prestamo.objects.filter(
                        reserva=sol_activa.reserva
                    ).select_related('estado').first()
                    if prestamo:
                        prestamo_info = {
                            'id':            prestamo.id,
                            'estado':        prestamo.estado.nombre if prestamo.estado else '—',
                            'fecha_entrega': prestamo.fecha_entrega.strftime('%d/%m/%Y %H:%M') if prestamo.fecha_entrega else '—',
                        }

                solicitud_info = {
                    'nombre':         nombre_sol,
                    'cedula':         sol_relevante.cedula,
                    'tipo':           sol_relevante.get_tipo_solicitante_display(),
                    'hora_inicio':    sol_relevante.hora_inicio.strftime('%H:%M') if sol_relevante.hora_inicio else '—',
                    'hora_fin':       sol_relevante.hora_fin.strftime('%H:%M')    if sol_relevante.hora_fin    else '—',
                    'estado_reserva': estado_reserva,
                    'reserva_id':     sol_relevante.reserva.id if sol_relevante.reserva else None,
                    'prestamo':       prestamo_info,
                    'prestamo_id':    prestamo_info['id'] if prestamo_info else None,
                }
            else:
                estado         = 'disponible'
                color          = 'success'
                solicitud_info = None
                motivo         = ''

            modulos_data.append({
                'modulo':    modulo,
                'estado':    estado,
                'color':     color,
                'solicitud': solicitud_info,
                'motivo':    motivo,
            })

    horas_disponibles = [
        f"{h:02d}:{m:02d}"
        for h in range(6, 19)
        for m in [0, 30]
        if not (h == 18 and m == 30)
    ]

    return render(request, 'laboratorio/mapa.html', {
        'laboratorio':        laboratorio,
        'modulos_data':       modulos_data,
        'fecha':              fecha.strftime('%Y-%m-%d'),
        'fecha_display':      fecha.strftime('%d/%m/%Y'),
        'es_admin':           request.user.rol.nombre in ['Administrador', 'Encargado'],
        'horas_disponibles':  horas_disponibles,
        'hora_inicio_filtro': hora_inicio_str,
        'hora_fin_filtro':    hora_fin_str,
        'filtro_valido':      filtro_valido,
        'error_filtro':       error_filtro,
    })

@rol_requerido('Administrador', 'Encargado')
def toggle_modulo(request, lab_id, mod_id):
    from .models import Modulo
    modulo = get_object_or_404(Modulo, id=mod_id, laboratorio__id=lab_id)

    if request.method == 'POST':
        disponible = request.POST.get('disponible') == 'true'
        motivo     = request.POST.get('motivo', '').strip()
        modulo.disponible            = disponible
        modulo.motivo_no_disponible  = '' if disponible else motivo
        modulo.save()
        return JsonResponse({
            'status':     'ok',
            'disponible': modulo.disponible,
            'motivo':     modulo.motivo_no_disponible,
        })

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Encargado')
def estado_modulos_api(request, id):
    from datetime import date, datetime, time
    from django.utils import timezone
    from solicitudes.models import SolicitudReserva

    laboratorio = get_object_or_404(Laboratorio, id=id)
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha = date.today()

    hora_inicio_str = request.GET.get('hora_inicio', '')
    hora_fin_str    = request.GET.get('hora_fin', '')

    hora_inicio_filtro = None
    hora_fin_filtro    = None
    try:
        if hora_inicio_str:
            h, m = hora_inicio_str.split(':')
            hora_inicio_filtro = time(int(h), int(m))
        if hora_fin_str:
            h, m = hora_fin_str.split(':')
            hora_fin_filtro = time(int(h), int(m))
    except (ValueError, AttributeError):
        return JsonResponse({'error': 'Formato de hora inválido.'}, status=400)

    if hora_inicio_filtro and hora_fin_filtro and hora_fin_filtro <= hora_inicio_filtro:
        return JsonResponse({'error': 'La hora de fin debe ser posterior a la hora de inicio.'}, status=400)

    solicitudes = SolicitudReserva.objects.filter(
        laboratorio=laboratorio,
        fecha_reserva__date=fecha,
        reserva__estado__nombre__in=['Pendiente', 'Aprobada'],
        necesita_modulo=True,
    ).prefetch_related('modulos_asignados').select_related('reserva__estado')

    if hora_inicio_filtro and hora_fin_filtro:
        solicitudes = solicitudes.filter(
            hora_inicio__lt=hora_fin_filtro,
            hora_fin__gt=hora_inicio_filtro,
        )

    modulo_solicitudes = {}
    for sol in solicitudes:
        for modulo in sol.modulos_asignados.all():
            modulo_solicitudes.setdefault(modulo.id, []).append(sol)

    es_hoy = (fecha == date.today())
    hora_actual = timezone.now().time()

    resultado = {}
    for modulo in laboratorio.modulos.all():
        soles = modulo_solicitudes.get(modulo.id, [])
        if not modulo.disponible:
            estado = 'inactivo'
        elif soles:
            sol_activa = None
            if hora_inicio_filtro and hora_fin_filtro:
                for sol in soles:
                    if (sol.reserva and sol.reserva.estado
                            and sol.reserva.estado.nombre == 'Aprobada'):
                        sol_activa = sol
                        break
            elif es_hoy:
                for sol in soles:
                    if sol.hora_inicio and sol.hora_fin and sol.hora_inicio <= hora_actual <= sol.hora_fin:
                        sol_activa = sol
                        break
            estado = 'ocupado' if sol_activa else 'reservado'
        else:
            estado = 'disponible'

        color_map = {
            'disponible': 'success',
            'ocupado': 'danger',
            'reservado': 'warning',
            'inactivo': 'secondary',
        }
        resultado[modulo.id] = {
            'estado': estado,
            'color': color_map[estado],
        }

    return JsonResponse(resultado)


@rol_requerido('Administrador', 'Encargado')
def modulos_disponibles_api(request, id):
    from datetime import date, datetime
    from solicitudes.models import SolicitudReserva

    laboratorio = get_object_or_404(Laboratorio, id=id)
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha = date.today()

    solicitudes = SolicitudReserva.objects.filter(
        laboratorio=laboratorio,
        fecha_reserva__date=fecha,
        reserva__estado__nombre__in=['Pendiente', 'Aprobada'],
        necesita_modulo=True,
    ).prefetch_related('modulos_asignados')

    modulos_ocupados = set()
    for sol in solicitudes:
        for m in sol.modulos_asignados.all():
            modulos_ocupados.add(m.id)

    modulos = []
    for modulo in laboratorio.modulos.all():
        if not modulo.disponible:
            estado = 'inactivo'
        elif modulo.id in modulos_ocupados:
            estado = 'reservado'
        else:
            estado = 'disponible'

        color_map = {
            'disponible': 'success',
            'reservado': 'warning',
            'inactivo': 'secondary',
        }
        modulos.append({
            'id': modulo.id,
            'nombre': modulo.nombre,
            'capacidad': modulo.capacidad,
            'estado': estado,
            'color': color_map.get(estado, 'secondary'),
            'seleccionable': estado == 'disponible',
        })

    return JsonResponse({'modulos': modulos})