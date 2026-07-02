from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from inventario.models import Insumo, ItemInventario
from prestamos.models import Prestamo
from reservas.models import Reserva


@login_required
def dashboard(request):

    context = {}

    rol = request.user.rol.nombre if request.user.rol else None

    if rol == 'Administrador':
        context['total_items'] = ItemInventario.objects.count()
        context['items_disponibles'] = ItemInventario.objects.filter(estado__nombre='Disponible').count()
        context['items_prestados'] = ItemInventario.objects.filter(estado__nombre='Prestado').count()
        context['prestamos_activos'] = Prestamo.objects.filter(estado__nombre='Activo').count()
        context['reservas_pendientes'] = Reserva.objects.filter(estado__nombre='Pendiente').count()
        context['alertas_stock'] = [
            insumo for insumo in Insumo.objects.all()
            if insumo.stock_minimo_alcanzado()
        ]

    elif rol == 'Laboratorio':
        context['prestamos_activos'] = Prestamo.objects.filter(estado__nombre='Activo').count()
        context['reservas_pendientes'] = Reserva.objects.filter(estado__nombre='Pendiente').count()

    elif rol in ['Docente', 'Estudiante']:
        context['mis_reservas'] = Reserva.objects.filter(
            usuario=request.user
        ).order_by('-fecha_creacion')[:5]

    context['rol'] = rol

    return render(request, 'dashboard.html', context)

