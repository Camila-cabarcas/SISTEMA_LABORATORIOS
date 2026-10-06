"""
views.py — dashboard
Página de inicio con estadísticas por rol:
  - Administrador: sección general (todos los laboratorios) + sección
    filtrable por laboratorio (?lab=<id>).
  - Laboratorio: las mismas tarjetas, fijas a sus laboratorios asignados.
  - Docente / Estudiante: sus últimas reservas.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render

from inventario.models import Insumo, ItemInventario
from inventario.views import _insumos_con_stock
from laboratorio.models import Laboratorio
from prestamos.models import Prestamo
from reservas.models import Reserva


# (clave en el contexto, nombre de EstadoItem, etiqueta, ícono, color)
# "Extraviado" en la UI corresponde al EstadoItem 'Perdido'.
ESTADOS_ITEM = [
    ('disponible', 'Disponible', 'Disponibles', 'fa-circle-check', 'ok'),
    ('prestado', 'Prestado', 'Prestados', 'fa-hand-holding', 'warn'),
    ('danado', 'Dañado', 'Dañados', 'fa-screwdriver-wrench', 'bad'),
    ('extraviado', 'Perdido', 'Extraviados', 'fa-circle-question', 'bad'),
]


def _estadisticas(lab_ids=None):
    """Conteos del dashboard. lab_ids=None → todos los laboratorios;
    una lista → solo esos (vacía → todo en cero)."""
    insumos = Insumo.objects.all()
    items = ItemInventario.activos.all()
    prestamos = Prestamo.objects.all()
    reservas = Reserva.objects.all()
    stock = _insumos_con_stock().filter(stock_minimo__gt=0)

    if lab_ids is not None:
        insumos = insumos.filter(laboratorio_id__in=lab_ids)
        items = items.filter(laboratorio_id__in=lab_ids)
        # Préstamos y reservas llegan al laboratorio vía la SolicitudReserva.
        prestamos = prestamos.filter(reserva__solicitud__laboratorio_id__in=lab_ids).distinct()
        reservas = reservas.filter(solicitud__laboratorio_id__in=lab_ids).distinct()
        stock = stock.filter(laboratorio_id__in=lab_ids)

    conteo_items = items.aggregate(
        total=Count('id'),
        **{clave: Count('id', filter=Q(estado__nombre=estado)) for clave, estado, *_ in ESTADOS_ITEM},
    )
    total_items = conteo_items['total']

    estados = [
        {
            'clave': clave,
            'etiqueta': etiqueta,
            'icono': icono,
            'color': color,
            'valor': conteo_items[clave],
            'porcentaje': round(conteo_items[clave] * 100 / total_items) if total_items else 0,
        }
        for clave, _, etiqueta, icono, color in ESTADOS_ITEM
    ]

    stock_bajo = [
        insumo for insumo in stock.order_by('laboratorio__nombre', 'nombre')
        if insumo.cantidad_disponible_count <= insumo.stock_minimo
    ]

    return {
        'total_insumos': insumos.count(),
        'total_items': total_items,
        'estados': estados,
        'prestamos_activos': prestamos.filter(estado__nombre='Activo').count(),
        'prestamos_retrasados': prestamos.filter(estado__nombre='Retrasado').count(),
        'reservas_pendientes': reservas.filter(estado__nombre='Pendiente').count(),
        'stock_bajo': stock_bajo,
    }


@login_required
def dashboard(request):
    rol = request.user.rol.nombre if request.user.rol else None
    context = {'rol': rol}

    if rol == 'Administrador':
        laboratorios = Laboratorio.objects.order_by('nombre')
        lab_id = request.GET.get('lab', '')
        lab_seleccionado = laboratorios.filter(id=lab_id).first() if lab_id.isdigit() else None

        context.update({
            'general': _estadisticas(),
            'laboratorios': laboratorios,
            'lab_seleccionado': lab_seleccionado,
            'por_lab': _estadisticas([lab_seleccionado.id]) if lab_seleccionado else None,
        })

    elif rol == 'Laboratorio':
        mis_labs = list(Laboratorio.objects.filter(encargados=request.user).order_by('nombre'))
        context.update({
            'mis_labs': mis_labs,
            'varios_labs': len(mis_labs) > 1,
            'stats': _estadisticas([lab.id for lab in mis_labs]) if mis_labs else None,
        })

    elif rol in ['Docente', 'Estudiante']:
        context['mis_reservas'] = Reserva.objects.filter(
            usuario=request.user
        ).select_related('estado').order_by('-fecha_creacion')[:5]

    return render(request, 'dashboard/dashboard.html', context)
