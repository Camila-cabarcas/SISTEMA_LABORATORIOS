"""
views.py — prestamos
Vistas para listar, crear, ver detalle, cambiar estado y marcar como devuelto un préstamo.
"""
from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Prestamo, PrestamoItem, EstadoPrestamo
from .forms import PrestamoForm, CambiarEstadoPrestamoForm, PrestamoItemForm


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
        items_disponibles = ItemInventario.objects.filter(
            insumo=ri.insumo,
            estado__nombre='Disponible'
        )
        items_por_insumo[ri] = items_disponibles

    if request.method == 'POST':

        prestamo = Prestamo.objects.create(
            reserva=reserva,
            responsable=request.user,
            estado=EstadoPrestamo.objects.get(nombre='Activo')
        )

        # Guardar los ítems seleccionados
        items_seleccionados = request.POST.getlist('items')
        for item_id in items_seleccionados:
            item = ItemInventario.objects.get(id=item_id)
            PrestamoItem.objects.create(
                prestamo=prestamo,
                item_inventario=item
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

    return render(
        request,
        'prestamos/detalle.html',
        {
            'prestamo': prestamo,
            'items': items,
            'form': form
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
def marcar_devuelto(request, id):

    from datetime import datetime

    prestamo = get_object_or_404(Prestamo, id=id)

    if request.method == 'POST':

        estado_devuelto = EstadoPrestamo.objects.get(nombre='Devuelto')
        prestamo.estado = estado_devuelto
        prestamo.fecha_devolucion = datetime.now()
        prestamo.save()

        return redirect('detalle_prestamo', id=prestamo.pk)

    return redirect('detalle_prestamo', id=prestamo.pk)