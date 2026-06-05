from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from users.decorators import rol_requerido
from users.models import Usuario
from inventario.models import Insumo
from .models import SolicitudReserva, Curso
from .forms import EstudianteSolicitudForm, ProfesorSolicitudForm


def solicitud_estudiante(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect('login')

        form = EstudianteSolicitudForm(request.user, request.POST)
        if form.is_valid():
            solicitud = form.save()
            try:
                solicitud.crear_reserva()
            except Exception as e:
                print(f"Error creando reserva: {e}")
            return redirect('lista_solicitudes')
    else:
        user = request.user if request.user.is_authenticated else None
        form = EstudianteSolicitudForm(user)

    return render(
        request,
        'solicitudes/estudiante.html',
        {'form': form, 'is_anonymous': not request.user.is_authenticated}
    )


def solicitud_profesor(request):
    if request.method == 'POST':
        form = ProfesorSolicitudForm(request.POST)
        if form.is_valid():
            solicitud = form.save()
            try:
                solicitud.crear_reserva()
            except Exception as e:
                print(f"Error creando reserva: {e}")
            return redirect('lista_solicitudes')
    else:
        form = ProfesorSolicitudForm()

    return render(
        request,
        'solicitudes/profesor.html',
        {'form': form}
    )


def cursos_profesor(request):
    """Retorna los cursos de un profesor basado en nombre y código (cédula)"""
    nombre = request.GET.get('nombre', '').strip()
    cedula = request.GET.get('cedula', '').strip()

    if not nombre:
        return JsonResponse({
            'error': 'Por favor ingresa el nombre del profesor',
            'cursos': []
        })

    # Buscar usuario que sea docente - búsqueda parcial e case-insensitive
    # Busca en first_name, last_name, username y full_name combinado
    docentes = Usuario.objects.filter(rol__nombre='Docente')

    usuarios = []
    for usuario in docentes:
        # Buscar si el nombre ingresado coincide con:
        # - first_name
        # - last_name
        # - username
        # - nombre completo (first_name + last_name)
        nombre_lower = nombre.lower()
        if (nombre_lower in usuario.first_name.lower() or
            nombre_lower in usuario.last_name.lower() or
            nombre_lower in usuario.username.lower() or
            nombre_lower in usuario.get_full_name().lower()):
            usuarios.append(usuario)

    if not usuarios:
        return JsonResponse({
            'error': f'No se encontró ningún docente con nombre "{nombre}". '
                     'Verifica que el nombre sea correcto.',
            'cursos': []
        })

    # Si se proporciona cédula, validar que coincida
    usuario = None
    if cedula:
        # Buscar por código (cédula) entre los usuarios encontrados
        usuario = next((u for u in usuarios if u.codigo == cedula), None)

        if not usuario:
            # Si la cédula no coincide, dar error específico
            nombres_encontrados = ', '.join([
                u.get_full_name() or u.username for u in usuarios[:3]
            ])
            return JsonResponse({
                'error': f'La cédula "{cedula}" no coincide con ningún docente. '
                         f'Docentes encontrados con nombre "{nombre}": {nombres_encontrados}',
                'cursos': []
            })
    else:
        # Si no hay cédula, tomar el primer usuario encontrado
        usuario = usuarios[0]

    if not usuario:
        return JsonResponse({
            'error': 'No se pudo identificar al profesor',
            'cursos': []
        })

    # Obtener cursos del profesor
    cursos = Curso.objects.filter(profesor=usuario).order_by('codigo')

    cursos_data = [
        {
            'id': c.id,
            'nombre': c.nombre,
            'codigo': c.codigo
        }
        for c in cursos
    ]

    profesor_nombre = usuario.get_full_name() or usuario.username

    return JsonResponse({
        'cursos': cursos_data,
        'profesor': profesor_nombre,
        'total': len(cursos_data)
    })


@login_required
def lista_solicitudes(request):
    solicitudes = SolicitudReserva.objects.all().order_by('-fecha_creacion')

    return render(
        request,
        'solicitudes/lista.html',
        {'solicitudes': solicitudes}
    )


def api_insumos(request):
    insumos = Insumo.objects.all()
    data = [
        {
            'id': i.id,
            'nombre': i.nombre,
            'cantidad_disponible': i.cantidad_disponible()
        }
        for i in insumos
    ]
    return JsonResponse(data, safe=False)


def buscar_insumos(request):
    from inventario.models import ItemInventario, EstadoItem

    q = request.GET.get('q', '').strip()

    if q:
        insumos = Insumo.objects.filter(nombre__icontains=q)
    else:
        insumos = Insumo.objects.all()

    results = []
    for i in insumos:
        # Calcular cantidad disponible como ItemInventario con estado Disponible
        estado_disponible = EstadoItem.objects.filter(nombre='Disponible').first()
        cantidad_disponible = 0
        if estado_disponible:
            cantidad_disponible = ItemInventario.objects.filter(
                insumo=i,
                estado=estado_disponible
            ).count()

        # Mostrar en el text según disponibilidad
        if cantidad_disponible > 0:
            text = i.nombre
        else:
            text = f"{i.nombre} (No disponible)"

        results.append({
            'id': i.id,
            'text': text,
            'cantidad_disponible': cantidad_disponible,
            'disabled': cantidad_disponible == 0
        })

    return JsonResponse({'results': results})
