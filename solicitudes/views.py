"""
views.py — solicitudes
Vistas públicas de solicitud para estudiante y profesor, APIs de insumos y cursos, y página de confirmación.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from users.models import Usuario
from inventario.models import Insumo
from .models import SolicitudReserva, Curso
from .forms import EstudianteSolicitudForm, ProfesorSolicitudForm


def solicitud_estudiante(request):
    if request.method == 'POST':
        form = EstudianteSolicitudForm(None, request.POST)
        if form.is_valid():
            solicitud = form.save()
            try:
                reserva = solicitud.crear_reserva()
            except Exception as e:
                print(f"Error creando reserva: {e}")
            return redirect('/solicitudes/exitosa/?tipo=estudiante')
        else:
            print(f"DEBUG: form inválido, errores={form.errors}")
    else:
        form = EstudianteSolicitudForm(None)

    return render(request, 'solicitudes/estudiante.html', {'form': form})


def solicitud_profesor(request):
    if request.method == 'POST':
        form = ProfesorSolicitudForm(request.POST)
        if form.is_valid():
            try:
                solicitud = form.save()
                try:
                    reserva = solicitud.crear_reserva()
                except Exception as e:
                    print(f"ERROR crear_reserva profesor: {e}")
                return redirect('/solicitudes/exitosa/?tipo=profesor')
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, 'message') else str(e))
    else:
        form = ProfesorSolicitudForm()

    return render(request, 'solicitudes/profesor.html', {'form': form})


def cursos_profesor(request):
    nombre = request.GET.get('nombre', '').strip()
    cedula = request.GET.get('cedula', '').strip()

    if not nombre:
        return JsonResponse({'error': 'Por favor ingresa el nombre del profesor', 'cursos': []})

    docentes = Usuario.objects.filter(rol__nombre='Docente')
    usuarios = []
    for usuario in docentes:
        nombre_lower = nombre.lower()
        if (nombre_lower in usuario.first_name.lower() or
            nombre_lower in usuario.last_name.lower() or
            nombre_lower in usuario.username.lower() or
            nombre_lower in usuario.get_full_name().lower()):
            usuarios.append(usuario)

    if not usuarios:
        return JsonResponse({
            'error': f'No se encontró ningún docente con nombre "{nombre}".',
            'cursos': []
        })

    usuario = None
    if cedula:
        usuario = next((u for u in usuarios if u.codigo == cedula), None)
        if not usuario:
            nombres_encontrados = ', '.join([u.get_full_name() or u.username for u in usuarios[:3]])
            return JsonResponse({
                'error': f'La cédula "{cedula}" no coincide. Docentes encontrados: {nombres_encontrados}',
                'cursos': []
            })
    else:
        usuario = usuarios[0]

    if not usuario:
        return JsonResponse({'error': 'No se pudo identificar al profesor', 'cursos': []})

    cursos = Curso.objects.filter(profesor=usuario).order_by('codigo')
    cursos_data = [
        {
            'id': c.id,
            'nombre': c.nombre,
            'codigo': c.codigo,
            'cantidad_estudiantes': c.cantidad_estudiantes,
        }
        for c in cursos
    ]

    return JsonResponse({
        'cursos': cursos_data,
        'profesor': usuario.get_full_name() or usuario.username,
        'total': len(cursos_data)
    })


@login_required
def lista_solicitudes(request):
    return redirect('lista_reservas')


def solicitud_exitosa(request):
    tipo = request.GET.get('tipo', 'estudiante')
    return render(request, 'solicitudes/solicitud_exitosa.html', {'tipo': tipo})


def api_insumos(request):
    insumos = Insumo.objects.all()
    data = [
        {'id': i.id, 'nombre': i.nombre, 'cantidad_disponible': i.cantidad_disponible()}
        for i in insumos
    ]
    return JsonResponse(data, safe=False)


def buscar_insumos(request):
    from inventario.models import ItemInventario, EstadoItem

    q = request.GET.get('q', '').strip()
    insumos = Insumo.objects.filter(nombre__icontains=q) if q else Insumo.objects.all()

    results = []
    for i in insumos:
        estado_disponible = EstadoItem.objects.filter(nombre='Disponible').first()
        cantidad_disponible = 0
        if estado_disponible:
            cantidad_disponible = ItemInventario.objects.filter(
                insumo=i, estado=estado_disponible
            ).count()

        results.append({
            'id': i.id,
            'text': i.nombre if cantidad_disponible > 0 else f"{i.nombre} (No disponible)",
            'cantidad_disponible': cantidad_disponible,
            'disabled': cantidad_disponible == 0
        })

    return JsonResponse({'results': results})