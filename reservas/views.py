"""
views.py — reservas
Vistas para listar, crear manualmente, aprobar, cancelar y gestionar reservas e insumos asociados.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from users.decorators import rol_requerido
from .models import Reserva, ReservaInsumo, EstadoReserva
from .forms import ReservaForm, ReservaInsumoForm
from .services.editar_insumos_service import EditarInsumosReservaService
from laboratorio.models import HorarioLaboratorio
from django.http import JsonResponse
from django.core.paginator import Paginator
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)


@rol_requerido('Administrador', 'Laboratorio')
def lista_reservas(request):
    from django.utils import timezone
    from django.db.models import Q
    from laboratorio.models import Laboratorio

    ahora = timezone.now()
    estado_expirada = EstadoReserva.objects.filter(nombre='Expirada').first()
    estado_pendiente = EstadoReserva.objects.filter(nombre='Pendiente').first()

    # Auto-expiración en línea, espejo de reservas/management/commands/
    # expirar_reservas.py — solo toca "Pendiente" (ver el docstring de ese
    # comando sobre por qué "Aprobada" ya no se expira acá bajo
    # auto-aprobación). En el flujo normal de hoy esto es un no-op: nada
    # nuevo nace Pendiente.
    if estado_expirada and estado_pendiente:
        Reserva.objects.filter(
            estado=estado_pendiente,
            hora_limite_retiro__lt=ahora
        ).update(estado=estado_expirada)

    estado_filtro = request.GET.get('estado', '')
    nombre_cedula = request.GET.get('buscar', '').strip()
    tipo_filtro   = request.GET.get('tipo', '')
    fecha_inicio  = request.GET.get('fecha_inicio', '')
    fecha_fin     = request.GET.get('fecha_fin', '')
    reserva_libre = request.GET.get('reserva_libre', '')
    lab_filtro    = request.GET.get('lab', '')
    listas_prestamo = request.GET.get('listas_prestamo', '')

    laboratorios = Laboratorio.objects.all()

    reservas = Reserva.objects.all().order_by('-fecha_reserva')

    if estado_filtro:
        reservas = reservas.filter(estado__nombre=estado_filtro)

    if nombre_cedula:
        reservas = reservas.filter(
            Q(solicitud__cedula__icontains=nombre_cedula) |
            Q(solicitud__nombre__icontains=nombre_cedula) |
            Q(codigo__icontains=nombre_cedula)
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

    if lab_filtro:
        reservas = reservas.filter(
            solicitud__laboratorio__id=lab_filtro
        ).distinct()

    if listas_prestamo:
        reservas = reservas.filter(
            estado__nombre='Aprobada',
            prestamo__isnull=True,
            fecha_reserva__lte=ahora,
            hora_limite_retiro__gte=ahora,
        )

    paginator   = Paginator(reservas, 15)
    page_number = request.GET.get('page', 1)
    page_obj    = paginator.get_page(page_number)

    return render(request, 'reservas/lista.html', {
        'reservas':      page_obj,
        'page_obj':      page_obj,
        'now':           ahora,
        'estado_filtro': estado_filtro,
        'nombre_cedula': nombre_cedula,
        'tipo_filtro':   tipo_filtro,
        'fecha_inicio':  fecha_inicio,
        'fecha_fin':     fecha_fin,
        'reserva_libre': reserva_libre,
        'laboratorios':  laboratorios,
        'lab_filtro':    lab_filtro,
        'listas_prestamo': listas_prestamo,
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
        logger.info(f"crear_reserva | iniciando | usuario={request.user.email}")

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
        email         = request.POST.get('email', '').strip()

        profesor_invitado = tipo == 'profesor' and request.POST.get('profesor_invitado') == '1'

        # SolicitudReserva no tiene un campo email propio; para no perder el
        # dato de contacto del profesor invitado, lo dejamos registrado en
        # observaciones en vez de descartarlo silenciosamente.
        if profesor_invitado and email:
            observaciones = f"Email de contacto: {email}\n{observaciones}".strip()

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

            curso = None
            usuario = None
            if tipo == 'profesor' and profesor_invitado:
                # Profesor invitado/externo: se usan nombre/cédula/email tal
                # cual los dio el encargado, sin buscarlo ni vincularlo a
                # ningún Usuario ni Curso registrado.
                pass
            else:
                curso = Curso.objects.filter(id=curso_id).first() if curso_id else None
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
                    reserva_libre=profesor_invitado,
                    laboratorio=laboratorio,
                    fecha_reserva=fecha_dt,
                    hora_inicio=hora_inicio_obj,
                    hora_fin=hora_fin_obj,
                    necesita_modulo=necesita,
                    observaciones=observaciones,
                )

                try:
                    from reservas.services.crear_reserva_service import CrearReservaService

                    solicitud.save()

                    modulos_ids_str = request.POST.get('modulos_ids', '')
                    modulos_ids = (
                        [int(x) for x in modulos_ids_str.split(',') if x.strip().isdigit()]
                        if modulos_ids_str else None
                    )

                    reserva = CrearReservaService().ejecutar(
                        solicitud_id=solicitud.id,
                        usuario=request.user,
                        modulos_ids=modulos_ids,
                    )

                    insumos_ids        = request.POST.get('insumos_ids', '')
                    insumos_cantidades = request.POST.get('insumos_cantidades', '')

                    if insumos_ids and reserva:
                        from inventario.models import Insumo
                        from reservas.models import ReservaInsumo
                        ids        = [x for x in insumos_ids.split(',') if x.strip()]
                        cantidades = [x for x in insumos_cantidades.split(',') if x.strip()]
                        for i, insumo_id in enumerate(ids):
                            try:
                                insumo   = Insumo.objects.get(id=insumo_id)
                                cantidad = int(cantidades[i]) if i < len(cantidades) else 1
                                ReservaInsumo.objects.create(
                                    reserva=reserva,
                                    insumo=insumo,
                                    cantidad=cantidad
                                )
                            except Exception:
                                pass

                    logger.info(f"crear_reserva | reserva_id={reserva.id} creada | usuario={request.user.email}")

                    return redirect('detalle_reserva', id=reserva.pk)
                except Exception as e:
                    logger.error(f"Error en crear_reserva | {str(e)} | usuario={request.user.email}")
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
    from django.utils import timezone

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

    ahora = timezone.now()
    puede_crear_prestamo = (
        reserva.estado.nombre == 'Aprobada' and
        not reserva.prestamo_set.exists() and
        reserva.fecha_reserva <= ahora <= reserva.hora_limite_retiro
    )
    puede_editar_insumos = EditarInsumosReservaService.puede_editar(reserva, request.user)

    # SolicitudReserva no tiene un campo email propio: para profesores
    # invitados, crear_reserva lo guarda como la primera línea de
    # observaciones ("Email de contacto: ..."). Lo separamos aquí para
    # mostrarlo como campo propio y no duplicarlo dentro de Observaciones.
    solicitante = reserva.solicitud.first()
    email_solicitante = ''
    observaciones_solicitante = solicitante.observaciones if solicitante else ''
    prefijo_email = 'Email de contacto: '
    if solicitante and observaciones_solicitante.startswith(prefijo_email):
        primera_linea, _, resto = observaciones_solicitante.partition('\n')
        email_solicitante = primera_linea[len(prefijo_email):].strip()
        observaciones_solicitante = resto.strip()

    return render(request, 'reservas/detalle.html', {
        'reserva': reserva,
        'insumos': insumos,
        'form':    form,
        'now':     ahora,
        'fecha_vencida': ahora > reserva.fecha_devolucion if reserva.fecha_devolucion else False,
        'puede_crear_prestamo': puede_crear_prestamo,
        'puede_editar_insumos': puede_editar_insumos,
        'email_solicitante': email_solicitante,
        'observaciones_solicitante': observaciones_solicitante,
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
    reserva = get_object_or_404(Reserva, id=id)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'cancelar':
            reserva.estado = EstadoReserva.objects.get(nombre='Cancelada')
            reserva.save()
        return redirect('detalle_reserva', id=reserva.pk)

    return render(request, 'reservas/aprobar.html', {'reserva': reserva})


@rol_requerido('Administrador', 'Laboratorio')
def exportar_reservas_excel(request):
    if request.method != 'POST':
        return redirect('lista_reservas')

    import io
    from datetime import date

    from django.http import FileResponse

    from utils.excel_export import export_reservas_excel

    reservas = Reserva.objects.select_related('estado').prefetch_related(
        'solicitud', 'solicitud__laboratorio', 'solicitud__modulos_asignados'
    ).order_by('-fecha_reserva')

    estado_filtro = request.POST.get('estado', '')
    fecha_inicio  = request.POST.get('fecha_inicio', '')
    fecha_fin     = request.POST.get('fecha_fin', '')

    if estado_filtro:
        reservas = reservas.filter(estado__nombre=estado_filtro)
    if fecha_inicio:
        reservas = reservas.filter(fecha_reserva__date__gte=fecha_inicio)
    if fecha_fin:
        reservas = reservas.filter(fecha_reserva__date__lte=fecha_fin)

    logger.info(f"exportar_reservas_excel | usuario={request.user.email}")

    wb = export_reservas_excel(reservas)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f'reservas_{date.today().isoformat()}.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


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


@rol_requerido('Administrador', 'Laboratorio')
def editar_insumos_reserva(request, id):
    """Permite a un laboratorista (solo del laboratorio de esta reserva, o a
    un Administrador) agregar/quitar/cambiar la cantidad de los insumos de
    una Reserva Aprobada mientras todavía no exista un Prestamo asociado —
    fecha/hora, laboratorio y módulos no se tocan acá. Ver
    EditarInsumosReservaService para las reglas de acceso y validación."""
    reserva = get_object_or_404(Reserva, id=id)
    laboratorio = EditarInsumosReservaService.verificar_acceso(reserva, request.user)

    insumos_actuales = ReservaInsumo.objects.filter(reserva=reserva).select_related('insumo')
    errores = []

    if request.method == 'POST':
        ids_str        = request.POST.get('insumos_ids', '')
        cantidades_str = request.POST.get('insumos_cantidades', '')
        ids            = [x for x in ids_str.split(',') if x.strip()]
        cantidades     = [x for x in cantidades_str.split(',') if x.strip()]

        items = []
        if len(ids) != len(cantidades):
            errores = ['Datos de insumos inválidos.']
        else:
            try:
                items = [
                    {'insumo_id': int(insumo_id), 'cantidad': int(cantidad)}
                    for insumo_id, cantidad in zip(ids, cantidades)
                ]
            except ValueError:
                errores = ['Datos de insumos inválidos.']

        if not errores:
            try:
                EditarInsumosReservaService.guardar(reserva, request.user, items)
                return redirect('detalle_reserva', id=reserva.pk)
            except ValidationError as e:
                errores = e.messages

    return render(request, 'reservas/editar_insumos.html', {
        'reserva':          reserva,
        'laboratorio':      laboratorio,
        'insumos_actuales': insumos_actuales,
        'errores':          errores,
    })