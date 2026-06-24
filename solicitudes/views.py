"""
views.py — solicitudes
Vistas públicas de solicitud para estudiante y profesor, APIs de insumos y cursos, y página de confirmación.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Q
from users.models import Usuario, ProgramaAcademico
from users.decorators import rol_requerido
from inventario.models import Insumo
from .models import SolicitudReserva, Curso, SolicitudInsumo, SolicitudRegistroProfesor, SolicitudRegistroCurso
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

    programas = ProgramaAcademico.objects.filter(activo=True)
    return render(request, 'solicitudes/estudiante.html', {'form': form, 'programas': programas})


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

            programas = ProgramaAcademico.objects.filter(activo=True)
            return render(request, 'solicitudes/profesor.html', {
                'form': ProfesorSolicitudForm(),
                'errores_libres': errores_libres,
                'post_data': request.POST,
                'programas': programas,
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

    programas = ProgramaAcademico.objects.filter(activo=True)
    return render(request, 'solicitudes/profesor.html', {'form': form, 'programas': programas})


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


def registro_profesor_publico(request):
    errores = []
    post_data = {}

    if request.method == 'POST':
        post_data = request.POST

        nombre   = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        cedula   = request.POST.get('cedula', '').strip()
        correo   = request.POST.get('correo', '').strip()
        programa = request.POST.get('programa', '').strip()

        nombres_curso    = request.POST.getlist('curso_nombre')
        codigos_curso    = request.POST.getlist('curso_codigo')
        cantidades_curso = request.POST.getlist('curso_cantidad')

        if not nombre:
            errores.append('El nombre es requerido.')
        if not apellido:
            errores.append('El apellido es requerido.')
        if not cedula:
            errores.append('La cédula es requerida.')
        elif not cedula.isdigit():
            errores.append('La cédula debe contener solo números.')
        elif SolicitudRegistroProfesor.objects.filter(
            cedula=cedula, estado__in=['pendiente', 'aprobada']
        ).exists():
            errores.append(
                f'Ya existe una solicitud pendiente o aprobada con la cédula {cedula}.'
            )

        cursos_validos = []
        for i, (nombre_c, codigo_c, cantidad_c) in enumerate(
            zip(nombres_curso, codigos_curso, cantidades_curso), 1
        ):
            nombre_c   = nombre_c.strip()
            codigo_c   = codigo_c.strip()
            cantidad_c = cantidad_c.strip()
            if not nombre_c and not codigo_c and not cantidad_c:
                continue
            if not nombre_c:
                errores.append(f'Falta el nombre en el curso {i}.')
            elif not codigo_c:
                errores.append(f'Falta el código en el curso {i}.')
            elif not cantidad_c:
                errores.append(f'Falta la cantidad de estudiantes en el curso {i}.')
            elif not cantidad_c.isdigit() or int(cantidad_c) < 1:
                errores.append(f'La cantidad del curso {i} debe ser un número positivo.')
            else:
                cursos_validos.append({
                    'nombre': nombre_c,
                    'codigo': codigo_c,
                    'cantidad_estudiantes': int(cantidad_c),
                })

        if not cursos_validos and not [e for e in errores if 'curso' in e.lower()]:
            errores.append('Debes agregar al menos un curso.')

        if not errores:
            solicitud = SolicitudRegistroProfesor.objects.create(
                nombre=nombre,
                apellido=apellido,
                cedula=cedula,
                correo=correo,
                programa=programa,
            )
            for curso in cursos_validos:
                SolicitudRegistroCurso.objects.create(
                    solicitud_profesor=solicitud,
                    **curso
                )
            return redirect('/solicitudes/exitosa/?tipo=registro_profesor')

    programas = ProgramaAcademico.objects.filter(activo=True)
    return render(request, 'solicitudes/registro_profesor.html', {
        'errores': errores,
        'post_data': post_data,
        'programas': programas,
    })


@rol_requerido('Administrador')
def lista_solicitudes_profesores(request):
    solicitudes = SolicitudRegistroProfesor.objects.all().order_by('-fecha_creacion')
    return render(request, 'solicitudes/lista_solicitudes_profesores.html', {
        'solicitudes': solicitudes,
    })


@rol_requerido('Administrador')
def detalle_solicitud_profesor(request, id):
    import secrets
    from users.models import Rol
    solicitud = get_object_or_404(SolicitudRegistroProfesor, id=id)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'aprobar_profesor' and solicitud.estado == 'pendiente':
            cedula   = solicitud.cedula
            base     = f"doc_{cedula}"
            username = base
            counter  = 2
            while Usuario.objects.filter(username=username).exists():
                username = f"{base}_{counter}"
                counter += 1

            usuario = Usuario(
                username=username,
                first_name=solicitud.nombre,
                last_name=solicitud.apellido,
                email=solicitud.correo,
                codigo=solicitud.cedula,
                programa=solicitud.programa,
                is_active=True,
            )
            usuario.set_password(secrets.token_urlsafe(16))
            usuario.rol = Rol.objects.filter(nombre='Docente').first()
            usuario.save()

            solicitud.usuario_creado = usuario
            solicitud.estado = 'aprobada'
            solicitud.save()

        elif accion == 'rechazar_profesor' and solicitud.estado == 'pendiente':
            solicitud.estado = 'rechazada'
            solicitud.save()
            solicitud.cursos_solicitados.update(estado='rechazada')

        elif accion == 'aprobar_curso' and solicitud.estado == 'aprobada':
            curso_id = request.POST.get('curso_id')
            solicitud_curso = get_object_or_404(
                SolicitudRegistroCurso, id=curso_id, solicitud_profesor=solicitud
            )
            if solicitud_curso.estado == 'pendiente' and solicitud.usuario_creado:
                curso = Curso.objects.create(
                    nombre=solicitud_curso.nombre,
                    codigo=solicitud_curso.codigo,
                    cantidad_estudiantes=solicitud_curso.cantidad_estudiantes,
                    profesor=solicitud.usuario_creado,
                )
                solicitud_curso.curso_creado = curso
                solicitud_curso.estado = 'aprobada'
                solicitud_curso.save()

        elif accion == 'rechazar_curso' and solicitud.estado == 'aprobada':
            curso_id = request.POST.get('curso_id')
            solicitud_curso = get_object_or_404(
                SolicitudRegistroCurso, id=curso_id, solicitud_profesor=solicitud
            )
            if solicitud_curso.estado == 'pendiente':
                solicitud_curso.estado = 'rechazada'
                solicitud_curso.save()

        return redirect('detalle_solicitud_profesor', id=id)

    cursos = solicitud.cursos_solicitados.all()
    return render(request, 'solicitudes/detalle_solicitud_profesor.html', {
        'solicitud': solicitud,
        'cursos': cursos,
    })


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
    profesor_id = request.GET.get('profesor_id') or request.POST.get('profesor_id')

    if request.method == 'POST':
        form = CursoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_cursos')
    else:
        initial = {'profesor': profesor_id} if profesor_id else {}
        form = CursoForm(initial=initial)

    profesor_preseleccionado = None
    if profesor_id:
        profesor_preseleccionado = Usuario.objects.filter(
            id=profesor_id, rol__nombre='Docente'
        ).first()

    return render(request, 'solicitudes/crear_curso.html', {
        'form': form,
        'profesor_id': profesor_id,
        'profesor_preseleccionado': profesor_preseleccionado,
    })


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