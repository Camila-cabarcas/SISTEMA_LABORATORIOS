"""
views.py — laboratorio
Vistas para gestionar laboratorios, eventos, mapa visual de módulos y APIs de estado en tiempo real.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from users.decorators import rol_requerido
from users.models import Usuario
from .models import Laboratorio, EventoLaboratorio, Laboratorista, LaboratoristaLab
from .forms import LaboratorioForm
from inventario.models import ItemInventario
from reservas.models import ReservaInsumo
from prestamos.models import PrestamoItem


def _check_lab_access(request, laboratorio):
    """403 si el Encargado no tiene este laboratorio asignado."""
    if request.user.rol.nombre == 'Laboratorio':
        if not laboratorio.encargados.filter(id=request.user.id).exists():
            raise PermissionDenied


@rol_requerido('Administrador', 'Laboratorio')
def lista_laboratorios(request):
    if request.user.rol.nombre == 'Administrador':
        laboratorios = Laboratorio.objects.all()
    else:
        laboratorios = request.user.laboratorios_asignados.all()

    return render(request, 'laboratorio/lista.html', {
        'laboratorios': laboratorios,
        'is_admin': request.user.rol.nombre == 'Administrador',
    })


@rol_requerido('Administrador')
def crear_laboratorio(request):
    if request.method == 'POST':
        form = LaboratorioForm(request.POST)
        cuenta_username  = request.POST.get('cuenta_username', '').strip()
        cuenta_password  = request.POST.get('cuenta_password', '').strip()
        cuenta_password2 = request.POST.get('cuenta_password2', '').strip()

        errores = []
        if not cuenta_username:
            errores.append('El usuario de la cuenta es requerido.')
        if not cuenta_password:
            errores.append('La contraseña es requerida.')
        if cuenta_password and cuenta_password != cuenta_password2:
            errores.append('Las contraseñas no coinciden.')
        if cuenta_username and Usuario.objects.filter(username=cuenta_username).exists():
            errores.append('Ese nombre de usuario ya está en uso.')

        if form.is_valid() and not errores:
            laboratorio = form.save()
            from users.models import Rol
            usuario_lab = Usuario.objects.create_user(
                username=cuenta_username,
                password=cuenta_password,
                first_name=laboratorio.nombre,
                rol=Rol.objects.get(nombre='Laboratorio'),
                codigo=cuenta_username,
            )
            laboratorio.encargados.add(usuario_lab)
            from django.contrib import messages
            messages.success(request, f"Laboratorio creado. Cuenta: {cuenta_username}")
            return redirect('detalle_laboratorio', id=laboratorio.id)

        return render(request, 'laboratorio/crear.html', {
            'form':      form,
            'errores':   errores,
            'post_data': request.POST,
        })
    else:
        form = LaboratorioForm()

    return render(request, 'laboratorio/crear.html', {'form': form})


@rol_requerido('Administrador', 'Laboratorio')
def detalle_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)
    items = ItemInventario.objects.filter(laboratorio=laboratorio)
    is_admin = request.user.rol.nombre == 'Administrador'

    cuenta_lab          = laboratorio.encargados.filter(username__startswith='lab_').first()
    encargado_principal = LaboratoristaLab.objects.filter(
        laboratorio=laboratorio, tipo='encargado'
    ).select_related('laboratorista').first()
    asignaciones_lab = laboratorio.asignaciones.select_related('laboratorista').all()

    return render(request, 'laboratorio/detalle.html', {
        'laboratorio':        laboratorio,
        'items':              items,
        'is_admin':           is_admin,
        'encargados':         laboratorio.encargados.all(),
        'cuenta_lab':         cuenta_lab,
        'encargado_principal': encargado_principal,
        'asignaciones_lab':   asignaciones_lab,
    })


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

    return render(request, 'laboratorio/editar.html', {
        'form': form,
        'laboratorio': laboratorio,
    })


@rol_requerido('Administrador')
def eliminar_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)

    if request.method == 'POST':
        laboratorio.delete()
        return redirect('lista_laboratorios')

    return render(request, 'laboratorio/eliminar.html', {'laboratorio': laboratorio})


@rol_requerido('Administrador', 'Laboratorio')
def reservas_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

    reservas_insumos = ReservaInsumo.objects.filter(
        insumo__items__laboratorio=laboratorio
    ).select_related('reserva', 'insumo').distinct()

    reservas = set()
    for ri in reservas_insumos:
        reservas.add(ri.reserva)

    return render(request, 'laboratorio/reservas.html', {
        'laboratorio': laboratorio,
        'reservas':    list(reservas),
    })


@rol_requerido('Administrador', 'Laboratorio')
def prestamos_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

    prestamos_items = PrestamoItem.objects.filter(
        item_inventario__laboratorio=laboratorio
    ).select_related('prestamo', 'item_inventario').distinct()

    prestamos = set()
    for pi in prestamos_items:
        prestamos.add(pi.prestamo)

    return render(request, 'laboratorio/prestamos.html', {
        'laboratorio': laboratorio,
        'prestamos':   list(prestamos),
    })


@rol_requerido('Administrador', 'Laboratorio')
def disponibilidad_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

    return render(request, 'laboratorio/disponibilidad.html', {'laboratorio': laboratorio})


@rol_requerido('Administrador', 'Laboratorio')
def eventos_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)
    eventos = EventoLaboratorio.objects.filter(laboratorio=laboratorio)

    data = []
    for evento in eventos:
        data.append({
            'id':       evento.id,
            'title':    evento.titulo,
            'start':    evento.inicio.strftime('%Y-%m-%dT%H:%M:%S'),
            'end':      evento.fin.strftime('%Y-%m-%dT%H:%M:%S'),
            'color':    '#dc3545' if evento.bloqueado else '#28a745',
            'bloqueado': evento.bloqueado,
        })

    return JsonResponse(data, safe=False)


@rol_requerido('Administrador', 'Laboratorio')
def crear_evento(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

    if request.method == 'POST':
        titulo    = request.POST.get('titulo')
        inicio    = request.POST.get('inicio')
        fin       = request.POST.get('fin')
        bloqueado = request.POST.get('bloqueado') == 'true'

        EventoLaboratorio.objects.create(
            laboratorio=laboratorio,
            titulo=titulo,
            inicio=inicio,
            fin=fin,
            bloqueado=bloqueado,
            creado_por=request.user,
        )
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Laboratorio')
def eliminar_evento(request, id):
    evento = get_object_or_404(EventoLaboratorio, id=id)
    _check_lab_access(request, evento.laboratorio)

    if request.method == 'POST':
        evento.delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Laboratorio')
def mapa_laboratorio(request, id):
    from datetime import date, datetime, time
    from solicitudes.models import SolicitudReserva

    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

    fecha_str       = request.GET.get('fecha', '')
    hora_inicio_str = request.GET.get('hora_inicio', '')
    hora_fin_str    = request.GET.get('hora_fin', '')

    filtro_valido = True
    error_filtro  = ''

    if not (fecha_str and hora_inicio_str and hora_fin_str):
        filtro_valido = False
        if fecha_str or hora_inicio_str or hora_fin_str:
            error_filtro = "Debes seleccionar fecha, hora de inicio y hora de fin para ver el mapa."

    fecha = date.today()
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            filtro_valido = False
            error_filtro  = "Formato de fecha inválido."

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
        'es_admin':           request.user.rol.nombre in ['Administrador', 'Laboratorio'],
        'horas_disponibles':  horas_disponibles,
        'hora_inicio_filtro': hora_inicio_str,
        'hora_fin_filtro':    hora_fin_str,
        'filtro_valido':      filtro_valido,
        'error_filtro':       error_filtro,
    })


@rol_requerido('Administrador', 'Laboratorio')
def toggle_modulo(request, lab_id, mod_id):
    from .models import Modulo
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    _check_lab_access(request, laboratorio)
    modulo = get_object_or_404(Modulo, id=mod_id, laboratorio=laboratorio)

    if request.method == 'POST':
        disponible = request.POST.get('disponible') == 'true'
        motivo     = request.POST.get('motivo', '').strip()
        modulo.disponible           = disponible
        modulo.motivo_no_disponible = '' if disponible else motivo
        modulo.save()
        return JsonResponse({
            'status':     'ok',
            'disponible': modulo.disponible,
            'motivo':     modulo.motivo_no_disponible,
        })

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Laboratorio')
def estado_modulos_api(request, id):
    from datetime import date, datetime, time
    from django.utils import timezone
    from solicitudes.models import SolicitudReserva

    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

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

    es_hoy      = (fecha == date.today())
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
            'ocupado':    'danger',
            'reservado':  'warning',
            'inactivo':   'secondary',
        }
        resultado[modulo.id] = {
            'estado': estado,
            'color':  color_map[estado],
        }

    return JsonResponse(resultado)


@rol_requerido('Administrador', 'Laboratorio')
def modulos_disponibles_api(request, id):
    from datetime import date, datetime
    from solicitudes.models import SolicitudReserva

    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

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
            'reservado':  'warning',
            'inactivo':   'secondary',
        }
        modulos.append({
            'id':          modulo.id,
            'nombre':      modulo.nombre,
            'capacidad':   modulo.capacidad,
            'estado':      estado,
            'color':       color_map.get(estado, 'secondary'),
            'seleccionable': estado == 'disponible',
        })

    return JsonResponse({'modulos': modulos})


@rol_requerido('Administrador')
def gestionar_encargados(request, lab_id):
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    cuenta_lab = laboratorio.encargados.filter(username__startswith='lab_').first()

    return render(request, 'laboratorio/gestionar_encargados.html', {
        'laboratorio': laboratorio,
        'cuenta_lab':  cuenta_lab,
    })


@rol_requerido('Administrador')
def asignar_laboratorista(request, lab_id):
    from django.contrib import messages
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'asignar':
            laboratorista_id = request.POST.get('laboratorista_id')
            tipo             = request.POST.get('tipo', 'laboratorista')
            laboratorista    = get_object_or_404(Laboratorista, id=laboratorista_id)

            if tipo == 'encargado' and LaboratoristaLab.objects.filter(
                laboratorio=laboratorio, tipo='encargado'
            ).exists():
                messages.error(request, "Este laboratorio ya tiene un encargado.")
                return redirect('asignar_laboratorista', lab_id=lab_id)

            LaboratoristaLab.objects.create(
                laboratorista=laboratorista,
                laboratorio=laboratorio,
                tipo=tipo,
            )
            messages.success(request, "Laboratorista asignado correctamente.")

        elif accion == 'desasignar':
            asignacion_id = request.POST.get('asignacion_id')
            asignacion    = get_object_or_404(LaboratoristaLab, id=asignacion_id)

            if asignacion.tipo == 'encargado':
                messages.error(request,
                    "No puedes desasignar al encargado. "
                    "Primero asigna otro encargado para reemplazarlo.")
                return redirect('asignar_laboratorista', lab_id=lab_id)

            asignacion.delete()
            messages.success(request, "Laboratorista desasignado correctamente.")

        elif accion == 'cambiar_tipo':
            asignacion_id = request.POST.get('asignacion_id')
            nuevo_tipo    = request.POST.get('nuevo_tipo')
            asignacion    = get_object_or_404(LaboratoristaLab, id=asignacion_id)

            if nuevo_tipo == 'encargado' and LaboratoristaLab.objects.filter(
                laboratorio=laboratorio, tipo='encargado'
            ).exclude(id=asignacion.id).exists():
                messages.error(request, "Este laboratorio ya tiene un encargado.")
                return redirect('asignar_laboratorista', lab_id=lab_id)

            asignacion.tipo = nuevo_tipo
            asignacion.save()
            messages.success(request, "Tipo actualizado correctamente.")

        return redirect('asignar_laboratorista', lab_id=lab_id)

    disponibles = Laboratorista.objects.filter(activo=True).exclude(
        asignaciones__laboratorio=laboratorio
    )
    asignados = LaboratoristaLab.objects.filter(
        laboratorio=laboratorio
    ).select_related('laboratorista')

    return render(request, 'laboratorio/asignar_laboratorista.html', {
        'laboratorio': laboratorio,
        'disponibles': disponibles,
        'asignados':   asignados,
    })


# ── Laboratoristas ─────────────────────────────────────────────

@rol_requerido('Administrador')
def lista_laboratoristas(request):
    from django.db.models import Q
    q = request.GET.get('q', '').strip()
    qs = Laboratorista.objects.filter(activo=True).prefetch_related(
        'asignaciones__laboratorio'
    )
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) |
            Q(apellido__icontains=q) |
            Q(cedula__icontains=q)
        )
    return render(request, 'laboratorio/laboratoristas/lista_laboratoristas.html', {
        'laboratoristas': qs,
        'q': q,
    })


@rol_requerido('Administrador')
def crear_laboratorista(request):
    from users.models import ProgramaAcademico
    errores  = []
    datos    = {}
    resp_sel = ['prestamos', 'atencion', 'inventario']

    if request.method == 'POST':
        nombre            = request.POST.get('nombre', '').strip()
        apellido          = request.POST.get('apellido', '').strip()
        cedula            = request.POST.get('cedula', '').strip()
        correo            = request.POST.get('correo', '').strip()
        programa          = request.POST.get('programa', '').strip()
        responsabilidades = request.POST.getlist('responsabilidades')
        resp_sel          = responsabilidades
        datos = {
            'nombre': nombre, 'apellido': apellido, 'cedula': cedula,
            'correo': correo, 'programa': programa,
        }

        if not nombre:
            errores.append('El nombre es requerido.')
        if not apellido:
            errores.append('El apellido es requerido.')
        if not cedula:
            errores.append('La cédula es requerida.')
        elif Laboratorista.objects.filter(cedula=cedula).exists():
            errores.append('Ya existe un laboratorista con esa cédula.')

        if not errores:
            Laboratorista.objects.create(
                nombre=nombre, apellido=apellido, cedula=cedula,
                correo=correo, programa=programa,
                responsabilidades=responsabilidades,
            )
            return redirect('lista_laboratoristas')

    return render(request, 'laboratorio/laboratoristas/crear_laboratorista.html', {
        'programas':                 ProgramaAcademico.objects.filter(activo=True),
        'errores':                   errores,
        'datos':                     datos,
        'responsabilidades_choices': Laboratorista.RESPONSABILIDADES_CHOICES,
        'responsabilidades_sel':     resp_sel,
    })


@rol_requerido('Administrador')
def editar_laboratorista(request, id):
    from users.models import ProgramaAcademico
    laboratorista = get_object_or_404(Laboratorista, id=id)
    errores       = []
    resp_sel      = laboratorista.responsabilidades

    if request.method == 'POST':
        nombre            = request.POST.get('nombre', '').strip()
        apellido          = request.POST.get('apellido', '').strip()
        cedula            = request.POST.get('cedula', '').strip()
        correo            = request.POST.get('correo', '').strip()
        programa          = request.POST.get('programa', '').strip()
        responsabilidades = request.POST.getlist('responsabilidades')
        resp_sel          = responsabilidades

        if not nombre:
            errores.append('El nombre es requerido.')
        if not apellido:
            errores.append('El apellido es requerido.')
        if not cedula:
            errores.append('La cédula es requerida.')
        elif Laboratorista.objects.filter(cedula=cedula).exclude(id=id).exists():
            errores.append('Ya existe un laboratorista con esa cédula.')

        if not errores:
            laboratorista.nombre            = nombre
            laboratorista.apellido          = apellido
            laboratorista.cedula            = cedula
            laboratorista.correo            = correo
            laboratorista.programa          = programa
            laboratorista.responsabilidades = responsabilidades
            laboratorista.save()
            return redirect('lista_laboratoristas')

    return render(request, 'laboratorio/laboratoristas/editar_laboratorista.html', {
        'laboratorista':             laboratorista,
        'programas':                 ProgramaAcademico.objects.filter(activo=True),
        'errores':                   errores,
        'responsabilidades_choices': Laboratorista.RESPONSABILIDADES_CHOICES,
        'responsabilidades_sel':     resp_sel,
    })


@rol_requerido('Administrador')
def eliminar_laboratorista(request, id):
    laboratorista = get_object_or_404(Laboratorista, id=id)

    if request.method == 'POST':
        laboratorista.delete()
        return redirect('lista_laboratoristas')

    return render(request, 'laboratorio/laboratoristas/confirmar_eliminar_laboratorista.html', {
        'laboratorista': laboratorista,
    })


@rol_requerido('Administrador')
def detalle_laboratorista(request, id):
    laboratorista = get_object_or_404(Laboratorista, id=id)
    asignaciones  = laboratorista.asignaciones.select_related('laboratorio')
    return render(request, 'laboratorio/laboratoristas/detalle_laboratorista.html', {
        'laboratorista':             laboratorista,
        'responsabilidades_choices': Laboratorista.RESPONSABILIDADES_CHOICES,
        'asignaciones':              asignaciones,
    })


@rol_requerido('Administrador')
def toggle_laboratorista(request, id):
    laboratorista = get_object_or_404(Laboratorista, id=id)
    if request.method == 'POST':
        laboratorista.activo = not laboratorista.activo
        laboratorista.save()
    return redirect('detalle_laboratorista', id=id)


@rol_requerido('Administrador')
def toggle_tipo_laboratorista(request, id):
    return redirect('detalle_laboratorista', id=id)