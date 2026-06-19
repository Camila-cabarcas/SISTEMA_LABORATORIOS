"""
views.py — solicitudes
Vistas públicas de solicitud para estudiante y profesor, APIs de insumos y cursos, y página de confirmación.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Q
from users.models import Usuario
from users.decorators import rol_requerido
from inventario.models import Insumo
from .models import SolicitudReserva, Curso, SolicitudInsumo
from .forms import EstudianteSolicitudForm, ProfesorSolicitudForm, CursoForm


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
        es_libre = request.POST.get('reserva_libre') == '1'

        if es_libre:
            from laboratorio.models import Laboratorio, Modulo
            from datetime import datetime as dt

            nombre          = request.POST.get('nombre', '').strip()
            cedula          = request.POST.get('cedula', '').strip()
            nombre_grupo    = request.POST.get('nombre_grupo', '').strip()
            cantidad_str    = request.POST.get('cantidad_asistentes', '').strip()
            descripcion     = request.POST.get('descripcion_actividad', '').strip()
            lab_id          = request.POST.get('laboratorio', '')
            fecha_str       = request.POST.get('fecha_reserva', '')
            hora_ini_str    = request.POST.get('hora_inicio', '')
            hora_fin_str    = request.POST.get('hora_fin', '')
            observaciones   = request.POST.get('observaciones', '')
            necesita_modulo = request.POST.get('necesita_modulo') == 'on'

            errores_libres = []

            if not nombre:
                errores_libres.append('El nombre del profesor es requerido.')
            if not cedula or not cedula.isdigit():
                errores_libres.append('La cédula es requerida y debe contener solo números.')
            if not nombre_grupo:
                errores_libres.append('El nombre del grupo o actividad es requerido.')
            if not cantidad_str or not cantidad_str.isdigit() or int(cantidad_str) < 1:
                errores_libres.append('La cantidad de asistentes debe ser un número positivo.')
            if not descripcion:
                errores_libres.append('La descripción de la actividad es requerida.')
            if not lab_id:
                errores_libres.append('Selecciona un laboratorio.')
            if not fecha_str:
                errores_libres.append('Selecciona una fecha.')
            if not hora_ini_str:
                errores_libres.append('Selecciona la hora de inicio.')
            if not hora_fin_str:
                errores_libres.append('Selecciona la hora de fin.')

            if not errores_libres:
                try:
                    laboratorio     = Laboratorio.objects.get(id=int(lab_id))
                    fecha_dt        = dt.strptime(fecha_str, '%Y-%m-%d')
                    hora_inicio_obj = dt.strptime(hora_ini_str, '%H:%M').time()
                    hora_fin_obj    = dt.strptime(hora_fin_str, '%H:%M').time()
                    cantidad        = int(cantidad_str)

                    from django.db.models import Q
                    partes = nombre.split()
                    query = Q()
                    for p in partes:
                        query |= (Q(first_name__icontains=p) |
                                  Q(last_name__icontains=p)  |
                                  Q(username__icontains=p))
                    usuario = Usuario.objects.filter(query, rol__nombre='Docente').first()

                    solicitud = SolicitudReserva(
                        tipo_solicitante='profesor',
                        nombre=nombre,
                        cedula=cedula,
                        programa=nombre_grupo,
                        reserva_libre=True,
                        descripcion_actividad=descripcion,
                        cantidad_asistentes_libre=cantidad,
                        laboratorio=laboratorio,
                        fecha_reserva=fecha_dt,
                        hora_inicio=hora_inicio_obj,
                        hora_fin=hora_fin_obj,
                        necesita_modulo=necesita_modulo,
                        observaciones=observaciones,
                        usuario=usuario,
                    )
                    solicitud.save()

                    if necesita_modulo:
                        modulos = Modulo.objects.filter(
                            laboratorio=laboratorio,
                            disponible=True
                        )[:cantidad]
                        solicitud.modulos_asignados.set(modulos)

                    ids_str       = request.POST.get('insumos_ids', '')
                    cantidades_str = request.POST.get('insumos_cantidades', '')
                    if ids_str:
                        from inventario.models import Insumo as InsumoModel
                        ids       = [int(x) for x in ids_str.split(',') if x.strip().isdigit()]
                        cantidades = [int(x) for x in cantidades_str.split(',') if x.strip().isdigit()]
                        for insumo_id, cant in zip(ids, cantidades):
                            try:
                                insumo_obj = InsumoModel.objects.get(id=insumo_id)
                                SolicitudInsumo.objects.create(
                                    solicitud=solicitud,
                                    insumo=insumo_obj,
                                    cantidad=cant
                                )
                            except InsumoModel.DoesNotExist:
                                pass

                    solicitud.crear_reserva()
                    return redirect('/solicitudes/exitosa/?tipo=profesor')

                except Exception as e:
                    errores_libres.append(f'Error al procesar la solicitud: {e}')

            return render(request, 'solicitudes/profesor.html', {
                'form': ProfesorSolicitudForm(),
                'errores_libres': errores_libres,
                'post_data': request.POST,
            })

        else:
            # Flujo normal — sin cambios
            form = ProfesorSolicitudForm(request.POST)
            if form.is_valid():
                try:
                    solicitud = form.save()
                    try:
                        solicitud.crear_reserva()
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


# ── Gestión de cursos ────────────────────────────────────────────────────────

@rol_requerido('Administrador', 'Encargado')
def lista_cursos(request):
    q = request.GET.get('q', '').strip()
    cursos = Curso.objects.select_related('profesor').order_by('codigo')
    if q:
        cursos = cursos.filter(
            Q(nombre__icontains=q)              |
            Q(codigo__icontains=q)              |
            Q(profesor__first_name__icontains=q) |
            Q(profesor__last_name__icontains=q)
        )
    return render(request, 'solicitudes/lista_cursos.html', {
        'cursos': cursos,
        'q': q,
    })


@rol_requerido('Administrador', 'Encargado')
def crear_curso(request):
    if request.method == 'POST':
        form = CursoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_cursos')
    else:
        form = CursoForm()
    return render(request, 'solicitudes/crear_curso.html', {'form': form})


@rol_requerido('Administrador', 'Encargado')
def editar_curso(request, id):
    curso = get_object_or_404(Curso, id=id)
    if request.method == 'POST':
        form = CursoForm(request.POST, instance=curso)
        if form.is_valid():
            form.save()
            return redirect('lista_cursos')
    else:
        form = CursoForm(instance=curso)
    return render(request, 'solicitudes/editar_curso.html', {
        'form': form,
        'curso': curso,
    })


@rol_requerido('Administrador', 'Encargado')
def eliminar_curso(request, id):
    curso = get_object_or_404(Curso, id=id)
    if request.method == 'POST':
        curso.delete()
        return redirect('lista_cursos')
    return render(request, 'solicitudes/eliminar_curso.html', {'curso': curso})