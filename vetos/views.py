"""
views.py — vetos
Gestión de vetos para Administrador y Laboratorio: listar los vigentes,
registrar manualmente un "no canceló", y levantar un veto (según las reglas
de Veto.puede_remover).
"""
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from users.decorators import rol_requerido
from .forms import VetoNoCanceloForm
from .models import Veto
from .services import RegistrarVetoService

logger = logging.getLogger(__name__)


@rol_requerido('Administrador', 'Laboratorio')
def lista_vetos(request):
    estado = request.GET.get('estado', Veto.ACTIVO)
    tipo = request.GET.get('tipo', '')
    q = request.GET.get('q', '').strip()

    vetos = Veto.objects.select_related('usuario', 'creado_por', 'resuelto_por')

    if estado:
        vetos = vetos.filter(estado=estado)
    if tipo:
        vetos = vetos.filter(tipo=tipo)
    if q:
        vetos = vetos.filter(
            Q(cedula__icontains=q) | Q(usuario__username__icontains=q)
        )

    paginator = Paginator(vetos, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'vetos/lista.html', {
        'page_obj': page_obj,
        'estado': estado,
        'tipo': tipo,
        'q': q,
        'ESTADO_CHOICES': Veto.ESTADO_CHOICES,
        'TIPO_CHOICES': Veto.TIPO_CHOICES,
    })


@rol_requerido('Administrador', 'Laboratorio')
def crear_veto(request):
    """Registro manual de un veto por "no canceló y dejó pasar el préstamo"
    (infracción A). El castigo (1 día, o 7 por reincidencia) lo calcula
    RegistrarVetoService."""
    reserva = None
    reserva_id = request.GET.get('reserva') or request.POST.get('reserva')
    if reserva_id:
        from reservas.models import Reserva
        reserva = Reserva.objects.filter(id=reserva_id).first()

    if request.method == 'POST':
        form = VetoNoCanceloForm(request.POST)
        if form.is_valid():
            veto = RegistrarVetoService.registrar_no_cancelo(
                reserva=reserva,
                cedula=form.cleaned_data['cedula'],
                creado_por=request.user,
                motivo=form.cleaned_data['motivo'],
            )
            messages.success(
                request,
                f'Veto registrado. Bloqueado hasta el '
                f'{veto.fecha_fin.strftime("%d/%m/%Y")}.',
            )
            return redirect('vetos:lista')
    else:
        inicial = {}
        if reserva:
            cedula, _ = _identidad(reserva)
            inicial['cedula'] = cedula
        form = VetoNoCanceloForm(initial=inicial)

    return render(request, 'vetos/crear.html', {'form': form, 'reserva': reserva})


@rol_requerido('Administrador', 'Laboratorio')
def remover_veto(request, id):
    veto = get_object_or_404(Veto, id=id)

    if not veto.puede_remover(request.user):
        messages.error(
            request,
            'No tienes permiso para levantar este veto. Los vetos por daño o '
            'falta de insumo solo los puede levantar un Administrador tras '
            'verificar la reposición.',
        )
        return redirect('vetos:lista')

    if request.method == 'POST':
        pagado = request.POST.get('pagado') == '1'
        veto.resolver(request.user, pagado=pagado)
        logger.info(
            'remover_veto | veto_id=%s | por=%s | pagado=%s',
            veto.id, request.user.username, pagado,
        )
        messages.success(request, 'Veto levantado.')
        return redirect('vetos:lista')

    return render(request, 'vetos/remover.html', {'veto': veto})


def _identidad(reserva):
    from .services import identidad_de_reserva
    return identidad_de_reserva(reserva)
