"""
views.py — prestamos
Vistas para listar, crear, ver detalle, cambiar estado y marcar como devuelto un préstamo.
"""
import logging

from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Prestamo, PrestamoItem, EstadoPrestamo, InspeccionItem
from .forms import PrestamoForm, CambiarEstadoPrestamoForm, PrestamoItemForm

logger = logging.getLogger(__name__)


@rol_requerido('Administrador', 'Laboratorio')
def lista_prestamos(request):
    from django.utils import timezone
    from django.core.paginator import Paginator
    from laboratorio.models import Laboratorio

    ahora = timezone.now()

    # Auto-marcar préstamos retrasados
    estado_retrasado = EstadoPrestamo.objects.filter(
        nombre='Retrasado'
    ).first()
    estado_activo = EstadoPrestamo.objects.filter(
        nombre='Activo'
    ).first()

    if estado_retrasado and estado_activo:
        Prestamo.objects.filter(
            estado=estado_activo,
            reserva__fecha_devolucion__lt=ahora
        ).update(estado=estado_retrasado)

    estado_filtro = request.GET.get('estado')
    fecha_inicio  = request.GET.get('fecha_inicio', '')
    fecha_fin     = request.GET.get('fecha_fin', '')
    lab_filtro    = request.GET.get('lab', '')

    laboratorios = Laboratorio.objects.all()

    prestamos = Prestamo.objects.all().order_by('-fecha_entrega')

    if estado_filtro:
        prestamos = prestamos.filter(estado__nombre=estado_filtro)

    if fecha_inicio:
        prestamos = prestamos.filter(fecha_entrega__date__gte=fecha_inicio)

    if fecha_fin:
        prestamos = prestamos.filter(fecha_entrega__date__lte=fecha_fin)

    if lab_filtro:
        prestamos = prestamos.filter(
            reserva__solicitud__laboratorio__id=lab_filtro
        ).distinct()

    paginator   = Paginator(prestamos, 15)
    page_number = request.GET.get('page', 1)
    page_obj    = paginator.get_page(page_number)

    return render(
        request,
        'prestamos/lista.html',
        {
            'prestamos':     page_obj,
            'page_obj':      page_obj,
            'estado_filtro': estado_filtro,
            'fecha_inicio':  fecha_inicio,
            'fecha_fin':     fecha_fin,
            'laboratorios':  laboratorios,
            'lab_filtro':    lab_filtro,
            'now':           ahora,
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def exportar_prestamos_excel(request):
    if request.method != 'POST':
        return redirect('lista_prestamos')

    import io
    from datetime import date

    from django.http import FileResponse

    from utils.excel_export import export_prestamos_excel

    prestamos = Prestamo.objects.select_related('estado', 'reserva').prefetch_related(
        'prestamoitem_set'
    ).order_by('-fecha_entrega')

    estado_filtro = request.POST.get('estado', '')
    fecha_inicio  = request.POST.get('fecha_inicio', '')
    fecha_fin     = request.POST.get('fecha_fin', '')

    if estado_filtro:
        prestamos = prestamos.filter(estado__nombre=estado_filtro)
    if fecha_inicio:
        prestamos = prestamos.filter(fecha_entrega__date__gte=fecha_inicio)
    if fecha_fin:
        prestamos = prestamos.filter(fecha_entrega__date__lte=fecha_fin)

    logger.info(f"exportar_prestamos_excel | usuario={request.user.email}")

    wb = export_prestamos_excel(prestamos)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f'prestamos_{date.today().isoformat()}.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@rol_requerido('Administrador', 'Laboratorio')
def exportar_inspecciones_excel(request):
    if request.method != 'POST':
        return redirect('lista_prestamos')

    import io
    from datetime import date

    from django.http import FileResponse

    from utils.excel_export import export_inspecciones_excel

    inspecciones = InspeccionItem.objects.select_related(
        'prestamo', 'prestamo_item__item_inventario'
    ).order_by('-fecha_inspeccion')

    logger.info(f"exportar_inspecciones_excel | usuario={request.user.email}")

    wb = export_inspecciones_excel(inspecciones)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f'inspecciones_{date.today().isoformat()}.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@rol_requerido('Administrador', 'Laboratorio')
def crear_prestamo(request, reserva_id):

    from reservas.models import Reserva, ReservaInsumo
    from inventario.models import ItemInventario, EstadoItem
    from datetime import datetime

    reserva = get_object_or_404(Reserva, id=reserva_id)

    if datetime.now() < reserva.fecha_reserva:
        return render(
            request,
            'prestamos/no_disponible.html',
            {'reserva': reserva, 'mensaje': 'antes'}
        )

    if datetime.now() > reserva.hora_limite_retiro:
        return render(
            request,
            'prestamos/no_disponible.html',
            {'reserva': reserva, 'mensaje': 'expirada'}
        )

    # Obtener ítems disponibles por insumo de la reserva
    insumos_reserva = ReservaInsumo.objects.filter(reserva=reserva)
    items_por_insumo = {}

    for ri in insumos_reserva:
        items_disponibles = ItemInventario.activos.filter(
            insumo=ri.insumo,
            estado__nombre='Disponible'
        )
        items_por_insumo[ri] = items_disponibles

    if request.method == 'POST':

        prestamo = Prestamo(
            reserva=reserva,
            responsable=request.user,
            estado=EstadoPrestamo.objects.get(nombre='Activo')
        )

        try:
            prestamo.full_clean()
        except ValidationError as e:
            return render(
                request,
                'prestamos/crear.html',
                {
                    'reserva': reserva,
                    'items_por_insumo': items_por_insumo,
                    'errores': e.messages,
                }
            )

        prestamo.save()

        # Guardar los ítems seleccionados. .activos (no .objects): un ítem
        # soft-deleted no debe poder prestarse aunque alguien arme el POST
        # a mano con su id — el formulario ya no lo ofrece, pero esto lo
        # bloquea también a ese nivel.
        items_seleccionados = request.POST.getlist('items')
        for item_id in items_seleccionados:
            item = ItemInventario.activos.filter(id=item_id).first()
            if not item:
                continue
            PrestamoItem.objects.create(
                prestamo=prestamo,
                item_inventario=item
            )

        try:
            from utils.notificaciones_email import notificar_cambios_o_prestamo_listo
            notificar_cambios_o_prestamo_listo(reserva, tipo='prestamo', prestamo=prestamo)
        except Exception:
            logger.exception(
                "notificar_cambios_o_prestamo_listo | error notificando | prestamo_id=%s", prestamo.id
            )

        return redirect('detalle_prestamo', id=prestamo.pk)

    return render(
        request,
        'prestamos/crear.html',
        {
            'reserva': reserva,
            'items_por_insumo': items_por_insumo
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def detalle_prestamo(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)
    items = PrestamoItem.objects.filter(prestamo=prestamo)

    if request.method == 'POST':

        form = PrestamoItemForm(request.POST)

        if form.is_valid():

            item_inventario = form.cleaned_data['item_inventario']

            if PrestamoItem.objects.filter(
                prestamo=prestamo,
                item_inventario=item_inventario
            ).exists():
                form.add_error('item_inventario', 'Este ítem ya está en el préstamo.')

            else:
                item = form.save(commit=False)
                item.prestamo = prestamo
                item.save()
                return redirect('detalle_prestamo', id=prestamo.pk)

    else:

        form = PrestamoItemForm()

    inspecciones_qs = InspeccionItem.objects.filter(prestamo=prestamo)
    inspecciones = {insp.prestamo_item_id: insp for insp in inspecciones_qs}

    return render(
        request,
        'prestamos/detalle.html',
        {
            'prestamo': prestamo,
            'items': items,
            'form': form,
            'inspecciones': inspecciones,
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def cambiar_estado_prestamo(request, id):

    from datetime import datetime

    prestamo = get_object_or_404(Prestamo, id=id)

    if request.method == 'POST':

        form = CambiarEstadoPrestamoForm(request.POST, instance=prestamo)

        if form.is_valid():

            prestamo = form.save(commit=False)

            # Si se devuelve, registra la fecha real
            if prestamo.estado.nombre == 'Devuelto':
                prestamo.fecha_devolucion = datetime.now()

            prestamo.save()

            return redirect('detalle_prestamo', id=prestamo.pk)

    else:

        form = CambiarEstadoPrestamoForm(instance=prestamo)

    return render(
        request,
        'prestamos/cambiar_estado.html',
        {
            'prestamo': prestamo,
            'form': form
        }
    )

@rol_requerido('Administrador', 'Laboratorio')
def iniciar_inspeccion(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)

    if request.method == 'POST':

        from .services.inspeccionar_prestamo_service import InspeccionarPrestamoService

        InspeccionarPrestamoService().iniciar_inspeccion(
            prestamo_id=prestamo.id,
            usuario=request.user,
        )

        return redirect('inspeccionar_prestamo', id=prestamo.pk)

    return redirect('detalle_prestamo', id=prestamo.pk)


@rol_requerido('Administrador', 'Laboratorio')
def inspeccionar_prestamo(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)
    items = PrestamoItem.objects.filter(prestamo=prestamo).select_related(
        'item_inventario', 'item_inventario__insumo'
    )

    if request.method == 'POST':

        for item in items:
            inspeccion, _ = InspeccionItem.objects.get_or_create(
                prestamo=prestamo,
                prestamo_item=item,
                defaults={'inspector': request.user}
            )
            inspeccion.estado_inspeccion = request.POST.get(
                f'estado_{item.id}', inspeccion.estado_inspeccion
            )
            inspeccion.observaciones = request.POST.get(f'observaciones_{item.id}', '').strip()
            inspeccion.inspector = request.user
            inspeccion.save()

        if request.POST.get('accion') == 'marcar_devuelto':
            return redirect('marcar_devuelto', id=prestamo.pk)

        return redirect('inspeccionar_prestamo', id=prestamo.pk)

    inspecciones_qs = InspeccionItem.objects.filter(prestamo=prestamo)
    inspecciones = {insp.prestamo_item_id: insp for insp in inspecciones_qs}

    return render(
        request,
        'prestamos/inspeccionar.html',
        {
            'prestamo': prestamo,
            'items': items,
            'inspecciones': inspecciones,
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def marcar_devuelto(request, id):

    prestamo = get_object_or_404(Prestamo, id=id)
    inspecciones = InspeccionItem.objects.filter(prestamo=prestamo).select_related(
        'prestamo_item__item_inventario__insumo'
    )

    if request.method == 'POST':
        logger.info(f"marcar_devuelto | iniciando | prestamo_id={prestamo.id} | usuario={request.user.email}")

        from .services.inspeccionar_prestamo_service import FinalizarInspeccionService

        try:
            FinalizarInspeccionService().finalizar(prestamo_id=prestamo.id)
        except Exception as e:
            logger.error(f"Error en marcar_devuelto | {str(e)} | prestamo_id={prestamo.id} | usuario={request.user.email}")
            raise

        logger.info(f"marcar_devuelto | prestamo_id={prestamo.id} marcado como Devuelto | usuario={request.user.email}")

        return redirect('detalle_prestamo', id=prestamo.pk)

    resumen = {
        'bien': inspecciones.filter(estado_inspeccion='bien').count(),
        'danado': inspecciones.filter(estado_inspeccion='danado').count(),
        'no_entregado': inspecciones.filter(estado_inspeccion='no_entregado').count(),
    }

    return render(
        request,
        'prestamos/confirmar_devolucion.html',
        {
            'prestamo': prestamo,
            'inspecciones': inspecciones,
            'resumen': resumen,
        }
    )