"""
views.py — laboratorio
Vistas para gestionar laboratorios, eventos, mapa visual de módulos y APIs de estado en tiempo real.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q, Subquery
from users.decorators import rol_requerido
from users.models import Usuario
from .models import Laboratorio, EventoLaboratorio, Laboratorista, LaboratoristaLab
from .forms import LaboratorioForm
from .services.modulo_service import ModuloEstadoService
from inventario.models import Insumo, ItemInventario, MovimientoInventario
from reservas.models import EstadoReserva, Reserva, ReservaInsumo
from prestamos.models import EstadoPrestamo, Prestamo, PrestamoItem
from solicitudes.models import SolicitudReserva


def _check_lab_access(request, laboratorio):
    """403 si el Encargado no tiene este laboratorio asignado."""
    if request.user.rol.nombre == 'Laboratorio':
        if not laboratorio.encargados.filter(id=request.user.id).exists():
            raise PermissionDenied


@rol_requerido('Administrador', 'Laboratorio')
def lista_laboratorios(request):
    if request.user.rol.nombre == 'Administrador':
        laboratorios = list(Laboratorio.objects.all())
    else:
        laboratorios = list(request.user.laboratorios_asignados.all())

    for lab in laboratorios:
        lab.encargado_principal = LaboratoristaLab.objects.filter(
            laboratorio=lab, tipo='encargado'
        ).select_related('laboratorista').first()

    from users.models import ProgramaAcademico
    programas_unicos = ProgramaAcademico.objects.filter(
        activo=True
    ).values_list('nombre', flat=True)

    return render(request, 'laboratorio/lista.html', {
        'laboratorios': laboratorios,
        'is_admin': request.user.rol.nombre == 'Administrador',
        'programas_unicos': programas_unicos,
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


# ── Detalle de laboratorio (pestañas Inventario / Reservas / Préstamos) ──────

POR_PAGINA_DETALLE = 10
TABS_DETALLE = ('inventario', 'reservas', 'prestamos')

# (valor del filtro = EstadoItem.nombre, etiqueta visible)
ESTADOS_ITEM_FILTRO = [
    ('Disponible', 'Disponible'),
    ('Prestado', 'Prestado'),
    ('Dañado', 'Dañado'),
    ('Perdido', 'Extraviado'),
]


def _querystring_sin(request, clave_pagina, tab):
    """GET actual sin la página de una pestaña y con tab=<tab>: base de sus
    enlaces de paginación, que así conservan los filtros de las otras."""
    params = request.GET.copy()
    params.pop(clave_pagina, None)
    params['tab'] = tab
    return params.urlencode()


def _insumos_del_laboratorio(laboratorio, busqueda='', estado=''):
    """Insumos del laboratorio (propios o con ítems activos en él), con los
    conteos por estado calculados SOLO sobre los ítems de este laboratorio
    (Insumo.stock_*() cuenta los ítems de todos los laboratorios)."""
    items_lab = ItemInventario.activos.filter(laboratorio=laboratorio)
    insumos = Insumo.objects.filter(
        Q(laboratorio=laboratorio) | Q(id__in=items_lab.values('insumo_id'))
    )
    if busqueda:
        insumos = insumos.filter(
            Q(nombre__icontains=busqueda) | Q(marca__icontains=busqueda) | Q(descripcion__icontains=busqueda)
        )
    if estado:
        insumos = insumos.filter(id__in=items_lab.filter(estado__nombre=estado).values('insumo_id'))

    del_lab = Q(items__laboratorio=laboratorio, items__deleted_at__isnull=True)
    return insumos.annotate(
        stock_total=Count('items', filter=del_lab),
        stock_disponible=Count('items', filter=del_lab & Q(items__estado__nombre='Disponible')),
        stock_prestado=Count('items', filter=del_lab & Q(items__estado__nombre='Prestado')),
        stock_danado=Count('items', filter=del_lab & Q(items__estado__nombre='Dañado')),
        stock_perdido=Count('items', filter=del_lab & Q(items__estado__nombre='Perdido')),
    ).order_by('nombre', 'id')


def _reservas_del_laboratorio(laboratorio, estado='', buscar=''):
    """Reservas hechas para el laboratorio (vía SolicitudReserva) o que
    reservan insumos con ítems en él (criterio de reservas_laboratorio)."""
    reservas = Reserva.objects.filter(
        Q(id__in=ReservaInsumo.objects.filter(
            insumo__items__laboratorio=laboratorio).values('reserva_id'))
        | Q(id__in=SolicitudReserva.objects.filter(
            laboratorio=laboratorio).values('reserva_id'))
    )
    if estado:
        reservas = reservas.filter(estado__nombre=estado)
    if buscar:
        reservas = reservas.filter(
            Q(codigo__icontains=buscar)
            | Q(usuario__username__icontains=buscar)
            | Q(usuario__first_name__icontains=buscar)
            | Q(usuario__last_name__icontains=buscar)
            | Q(id__in=SolicitudReserva.objects.filter(
                Q(nombre__icontains=buscar) | Q(cedula__icontains=buscar)).values('reserva_id'))
        )
    # Nombre/cédula de la solicitud pública (en ese flujo Reserva.usuario es
    # NULL) por subconsulta, sin JOIN que duplique filas.
    solicitud = SolicitudReserva.objects.filter(reserva=OuterRef('pk')).order_by('id')
    return reservas.select_related('usuario', 'estado').annotate(
        solicitante_nombre=Subquery(solicitud.values('nombre')[:1]),
        solicitante_cedula=Subquery(solicitud.values('cedula')[:1]),
    ).order_by('-fecha_reserva', '-id')


def _prestamos_del_laboratorio(laboratorio, estado=''):
    """Préstamos con ítems de este laboratorio (criterio de prestamos_laboratorio)."""
    prestamos = Prestamo.objects.filter(
        id__in=PrestamoItem.objects.filter(
            item_inventario__laboratorio=laboratorio).values('prestamo_id')
    )
    if estado:
        prestamos = prestamos.filter(estado__nombre=estado)
    return prestamos.select_related('responsable', 'estado').order_by('-fecha_entrega', '-id')


@rol_requerido('Administrador', 'Laboratorio')
def detalle_laboratorio(request, id):
    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)
    is_admin = request.user.rol.nombre == 'Administrador'

    cuenta_lab          = laboratorio.encargados.filter(username__startswith='lab_').first()
    encargado_principal = LaboratoristaLab.objects.filter(
        laboratorio=laboratorio, tipo='encargado'
    ).select_related('laboratorista').first()
    asignaciones_lab = laboratorio.asignaciones.select_related('laboratorista').all()

    tab = request.GET.get('tab', '')
    if tab not in TABS_DETALLE:
        tab = 'inventario'

    # Pestaña Inventario
    busqueda = request.GET.get('busqueda', '').strip()
    filtro_estado = request.GET.get('estado', '').strip()
    if filtro_estado not in dict(ESTADOS_ITEM_FILTRO):
        filtro_estado = ''
    insumos_page = Paginator(
        _insumos_del_laboratorio(laboratorio, busqueda, filtro_estado), POR_PAGINA_DETALLE
    ).get_page(request.GET.get('page'))

    # Pestaña Reservas
    filtro_estado_reserva = request.GET.get('r_estado', '').strip()
    busqueda_reserva = request.GET.get('r_buscar', '').strip()
    reservas_page = Paginator(
        _reservas_del_laboratorio(laboratorio, filtro_estado_reserva, busqueda_reserva), POR_PAGINA_DETALLE
    ).get_page(request.GET.get('r_page'))

    # Pestaña Préstamos
    filtro_estado_prestamo = request.GET.get('p_estado', '').strip()
    prestamos_page = Paginator(
        _prestamos_del_laboratorio(laboratorio, filtro_estado_prestamo), POR_PAGINA_DETALLE
    ).get_page(request.GET.get('p_page'))

    return render(request, 'laboratorio/detalle.html', {
        'laboratorio':        laboratorio,
        'is_admin':           is_admin,
        'encargados':         laboratorio.encargados.all(),
        'cuenta_lab':         cuenta_lab,
        'encargado_principal': encargado_principal,
        'asignaciones_lab':   asignaciones_lab,
        'cursos':             laboratorio.cursos.select_related('profesor').order_by('codigo'),
        'tab':                tab,

        'insumos_page':       insumos_page,
        'filtro_estado':      filtro_estado,
        'busqueda':           busqueda,
        'estados_item':       ESTADOS_ITEM_FILTRO,
        'qs_inventario':      _querystring_sin(request, 'page', 'inventario'),

        'reservas_page':      reservas_page,
        'filtro_estado_reserva': filtro_estado_reserva,
        'busqueda_reserva':   busqueda_reserva,
        'estados_reserva':    EstadoReserva.objects.order_by('nombre').values_list('nombre', flat=True),
        'qs_reservas':        _querystring_sin(request, 'r_page', 'reservas'),

        'prestamos_page':     prestamos_page,
        'filtro_estado_prestamo': filtro_estado_prestamo,
        'estados_prestamo':   EstadoPrestamo.objects.order_by('nombre').values_list('nombre', flat=True),
        'qs_prestamos':       _querystring_sin(request, 'p_page', 'prestamos'),
    })


@rol_requerido('Administrador', 'Laboratorio')
def modal_items_insumo(request, lab_id, insumo_id):
    """JSON con los ítems activos de `insumo_id` en el laboratorio `lab_id`
    y su último movimiento; lo consume el modal de la pestaña Inventario."""
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    _check_lab_access(request, laboratorio)
    insumo = get_object_or_404(Insumo, id=insumo_id)

    ultimo_mov = MovimientoInventario.objects.filter(
        item_inventario=OuterRef('pk')
    ).order_by('-fecha', '-id')
    items = (
        ItemInventario.activos.filter(laboratorio=laboratorio, insumo=insumo)
        .select_related('estado')
        .annotate(
            ultima_accion=Subquery(ultimo_mov.values('tipo_movimiento__nombre')[:1]),
            ultima_fecha=Subquery(ultimo_mov.values('fecha')[:1]),
        )
        .order_by('codigo')
    )

    return JsonResponse({
        'insumo': {'id': insumo.id, 'nombre': insumo.nombre},
        'items': [
            {
                'codigo': item.codigo,
                'estado': item.estado.nombre,
                'ultima_accion': item.ultima_accion or '',
                'ultima_fecha': item.ultima_fecha.isoformat() if item.ultima_fecha else None,
            }
            for item in items
        ],
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
    from datetime import date, datetime, time, timedelta
    from laboratorio.models import HistorialModulo

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
        solicitudes = ModuloEstadoService.solicitudes_del_laboratorio(
            laboratorio, fecha, hora_inicio_filtro, hora_fin_filtro,
        )
        modulo_solicitudes = ModuloEstadoService.agrupar_por_modulo(solicitudes)

        color_map = {'disponible': 'success', 'ocupado': 'danger', 'reservado': 'warning', 'inactivo': 'secondary'}

        for modulo in laboratorio.modulos.all():
            soles = modulo_solicitudes.get(modulo.id, [])
            estado = ModuloEstadoService.obtener_estado(modulo, soles, fecha)
            solicitud_info = None
            motivo = ''

            if estado == 'inactivo':
                # Si la inactivación fue programada para el futuro (ver
                # HistorialModulo) y `fecha` es anterior a que empiece, el
                # módulo se muestra disponible hoy en vez de inactivo — esto
                # es específico de este mapa, no forma parte del cálculo
                # genérico de ModuloEstadoService.
                registro_activo = HistorialModulo.objects.filter(
                    modulo=modulo,
                    fecha_fin__isnull=True
                ).first()

                if registro_activo:
                    fecha_inicio_registro = registro_activo.fecha_inicio.date()
                    if fecha <= fecha_inicio_registro - timedelta(days=1):
                        estado = 'disponible'
                    else:
                        motivo = registro_activo.motivo
                else:
                    motivo = modulo.motivo_no_disponible

            elif estado in ('ocupado', 'reservado'):
                sol_relevante = ModuloEstadoService.solicitud_relevante(soles, fecha)
                # solicitud_relevante solo devuelve None si `soles` está vacío,
                # y obtener_estado ya habría devuelto 'disponible' en ese caso
                # en vez de 'ocupado'/'reservado' — nunca None acá.
                assert sol_relevante is not None

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
                if estado == 'ocupado' and sol_relevante.reserva:
                    prestamo = Prestamo.objects.filter(
                        reserva=sol_relevante.reserva
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

            modulos_data.append({
                'modulo':    modulo,
                'estado':    estado,
                'color':     color_map[estado],
                'solicitud': solicitud_info,
                'motivo':    motivo,
            })
    else:
        for modulo in laboratorio.modulos.all():
            estado = ModuloEstadoService.obtener_estado(modulo, fecha=fecha)
            modulos_data.append({
                'modulo':    modulo,
                'estado':    estado,
                'color':     'secondary' if estado == 'inactivo' else 'success',
                'solicitud': None,
                'motivo':    modulo.motivo_no_disponible if estado == 'inactivo' else '',
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
    from .models import Modulo, HistorialModulo
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    _check_lab_access(request, laboratorio)
    modulo = get_object_or_404(Modulo, id=mod_id, laboratorio=laboratorio)

    if request.method == 'POST':
        disponible = request.POST.get('disponible') == 'true'
        motivo     = request.POST.get('motivo', '').strip()
        print(f"DEBUG toggle_modulo — disponible={disponible} motivo='{motivo}'")
        modulo.disponible           = disponible
        modulo.motivo_no_disponible = '' if disponible else motivo
        modulo.save()

        if not disponible:
            HistorialModulo.objects.create(
                modulo=modulo,
                motivo=motivo,
                registrado_por=request.user,
            )
        else:
            registro_activo = HistorialModulo.objects.filter(
                modulo=modulo,
                fecha_fin__isnull=True
            ).first()
            if registro_activo:
                from django.utils import timezone
                registro_activo.fecha_fin = timezone.now()
                registro_activo.save()

        return JsonResponse({
            'status':     'ok',
            'disponible': modulo.disponible,
            'motivo':     modulo.motivo_no_disponible,
        })

    return JsonResponse({'status': 'error'}, status=400)


@rol_requerido('Administrador', 'Laboratorio')
def estado_modulos_api(request, id):
    from datetime import date, datetime, time

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

    solicitudes = ModuloEstadoService.solicitudes_del_laboratorio(
        laboratorio, fecha, hora_inicio_filtro, hora_fin_filtro,
    )
    modulo_solicitudes = ModuloEstadoService.agrupar_por_modulo(solicitudes)

    color_map = {
        'disponible': 'success',
        'ocupado':    'danger',
        'reservado':  'warning',
        'inactivo':   'secondary',
    }

    resultado = {}
    for modulo in laboratorio.modulos.all():
        soles = modulo_solicitudes.get(modulo.id, [])
        estado = ModuloEstadoService.obtener_estado(modulo, soles, fecha)
        resultado[modulo.id] = {
            'estado': estado,
            'color':  color_map[estado],
        }

    return JsonResponse(resultado)


def _serializar_modulos_disponibles(laboratorio, fecha, incluir_zona=False):
    """Estado del día completo (sin distinguir 'ocupado ahora mismo') para
    cada módulo del laboratorio — compartido por modulos_disponibles_api y
    su variante pública."""
    solicitudes = ModuloEstadoService.solicitudes_del_laboratorio(laboratorio, fecha)
    modulo_solicitudes = ModuloEstadoService.agrupar_por_modulo(solicitudes)

    color_map = {'disponible': 'success', 'reservado': 'warning', 'inactivo': 'secondary'}

    modulos = []
    for modulo in laboratorio.modulos.all():
        soles = modulo_solicitudes.get(modulo.id, [])
        estado = ModuloEstadoService.obtener_estado(modulo, soles, fecha, evaluar_ahora=False)
        data = {
            'id':            modulo.id,
            'nombre':        modulo.nombre,
            'capacidad':     modulo.capacidad,
            'estado':        estado,
            'color':         color_map.get(estado, 'secondary'),
            'seleccionable': estado == 'disponible',
        }
        if incluir_zona:
            data['zona'] = modulo.zona
        modulos.append(data)

    return modulos


@rol_requerido('Administrador', 'Laboratorio')
def modulos_disponibles_api(request, id):
    from datetime import date, datetime

    laboratorio = get_object_or_404(Laboratorio, id=id)
    _check_lab_access(request, laboratorio)

    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha = date.today()

    return JsonResponse({'modulos': _serializar_modulos_disponibles(laboratorio, fecha)})


def modulos_disponibles_publica_api(request, id):
    """Igual que modulos_disponibles_api pero de acceso público (sin login),
    para el mapa de módulos del formulario público de estudiante."""
    from datetime import date, datetime

    laboratorio = get_object_or_404(Laboratorio, id=id)

    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        fecha = date.today()

    modulos = _serializar_modulos_disponibles(laboratorio, fecha, incluir_zona=True)
    return JsonResponse({'modulos': modulos})


@rol_requerido('Administrador', 'Laboratorio')
def historial_modulo(request, lab_id, mod_id):
    from .models import Modulo, HistorialModulo
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    _check_lab_access(request, laboratorio)
    modulo = get_object_or_404(Modulo, id=mod_id, laboratorio=laboratorio)
    historial = HistorialModulo.objects.filter(modulo=modulo)
    return render(request, 'laboratorio/historial_modulo.html', {
        'laboratorio': laboratorio,
        'modulo': modulo,
        'historial': historial,
    })


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
    errores           = []
    datos             = {}
    resp_sel          = ['prestamos', 'atencion', 'inventario']
    lab_ids_sel       = []
    encargado_ids_sel = []

    if request.method == 'POST':
        nombre            = request.POST.get('nombre', '').strip()
        apellido          = request.POST.get('apellido', '').strip()
        cedula            = request.POST.get('cedula', '').strip()
        correo            = request.POST.get('correo', '').strip()
        programa          = request.POST.get('programa', '').strip()
        responsabilidades = request.POST.getlist('responsabilidades')
        lab_ids           = request.POST.getlist('lab_ids')
        resp_sel          = responsabilidades
        lab_ids_sel       = [int(x) for x in lab_ids if x.isdigit()]
        encargado_ids_sel = [
            int(x) for x in lab_ids
            if x.isdigit() and request.POST.get(f'lab_tipo_{x}') == 'encargado'
        ]
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
            nuevo = Laboratorista.objects.create(
                nombre=nombre, apellido=apellido, cedula=cedula,
                correo=correo, programa=programa,
                responsabilidades=responsabilidades,
            )
            for lab_id in lab_ids:
                tipo       = request.POST.get(f'lab_tipo_{lab_id}', 'laboratorista')
                laboratorio = Laboratorio.objects.filter(id=lab_id).first()
                if laboratorio:
                    if tipo == 'encargado' and LaboratoristaLab.objects.filter(
                        laboratorio=laboratorio, tipo='encargado'
                    ).exists():
                        tipo = 'laboratorista'
                    LaboratoristaLab.objects.create(
                        laboratorista=nuevo,
                        laboratorio=laboratorio,
                        tipo=tipo,
                    )
            return redirect('lista_laboratoristas')

    return render(request, 'laboratorio/laboratoristas/crear_laboratorista.html', {
        'programas':                 ProgramaAcademico.objects.filter(activo=True),
        'laboratorios':              Laboratorio.objects.all(),
        'errores':                   errores,
        'datos':                     datos,
        'responsabilidades_choices': Laboratorista.RESPONSABILIDADES_CHOICES,
        'responsabilidades_sel':     resp_sel,
        'lab_ids_sel':               lab_ids_sel,
        'encargado_ids_sel':         encargado_ids_sel,
    })


@rol_requerido('Administrador')
def editar_laboratorista(request, id):
    from users.models import ProgramaAcademico
    laboratorista = get_object_or_404(Laboratorista, id=id)
    errores       = []
    resp_sel      = laboratorista.responsabilidades

    asignaciones_qs   = laboratorista.asignaciones.all()
    lab_ids_sel       = list(asignaciones_qs.values_list('laboratorio_id', flat=True))
    encargado_ids_sel = list(
        asignaciones_qs.filter(tipo='encargado').values_list('laboratorio_id', flat=True)
    )

    if request.method == 'POST':
        nombre            = request.POST.get('nombre', '').strip()
        apellido          = request.POST.get('apellido', '').strip()
        cedula            = request.POST.get('cedula', '').strip()
        correo            = request.POST.get('correo', '').strip()
        programa          = request.POST.get('programa', '').strip()
        responsabilidades = request.POST.getlist('responsabilidades')
        lab_ids           = request.POST.getlist('lab_ids')
        resp_sel          = responsabilidades
        lab_ids_sel       = [int(x) for x in lab_ids if x.isdigit()]
        encargado_ids_sel = [
            int(x) for x in lab_ids
            if x.isdigit() and request.POST.get(f'lab_tipo_{x}') == 'encargado'
        ]

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

            laboratorista.asignaciones.all().delete()
            for lab_id in lab_ids:
                tipo        = request.POST.get(f'lab_tipo_{lab_id}', 'laboratorista')
                laboratorio = Laboratorio.objects.filter(id=lab_id).first()
                if laboratorio:
                    if tipo == 'encargado' and LaboratoristaLab.objects.filter(
                        laboratorio=laboratorio, tipo='encargado'
                    ).exists():
                        tipo = 'laboratorista'
                    LaboratoristaLab.objects.create(
                        laboratorista=laboratorista,
                        laboratorio=laboratorio,
                        tipo=tipo,
                    )
            return redirect('lista_laboratoristas')

    return render(request, 'laboratorio/laboratoristas/editar_laboratorista.html', {
        'laboratorista':             laboratorista,
        'programas':                 ProgramaAcademico.objects.filter(activo=True),
        'laboratorios':              Laboratorio.objects.all(),
        'errores':                   errores,
        'responsabilidades_choices': Laboratorista.RESPONSABILIDADES_CHOICES,
        'responsabilidades_sel':     resp_sel,
        'lab_ids_sel':               lab_ids_sel,
        'encargado_ids_sel':         encargado_ids_sel,
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


def tiene_encargado_api(request, lab_id):
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    tiene = LaboratoristaLab.objects.filter(
        laboratorio=laboratorio, tipo='encargado'
    ).exists()
    return JsonResponse({'tiene_encargado': tiene})