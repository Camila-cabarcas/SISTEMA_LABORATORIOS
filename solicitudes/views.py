"""
views.py — solicitudes
Vistas públicas de solicitud para estudiante y profesor, APIs de insumos y cursos, y página de confirmación.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from users.models import Usuario, ProgramaAcademico
from users.decorators import rol_requerido, requiere_contrasena_admin
from inventario.models import Insumo
from laboratorio.models import Laboratorio
from .models import SolicitudReserva, Curso, SolicitudRegistroProfesor
from .forms import EstudianteSolicitudForm, ProfesorSolicitudForm, CursoForm
from .services.solicitud_reserva_service import CrearSolicitudReservaService, ValidarSolicitudReservaService
from .services.registro_profesor_service import (
    AprobarCursoService,
    AprobarSolicitudRegistroProfesorService,
    CrearSolicitudRegistroProfesorService,
)
from .services.mis_reservas_service import MisReservasService

logger = logging.getLogger(__name__)


def solicitud_estudiante(request):
    if request.method == 'POST':
        form = EstudianteSolicitudForm(None, request.POST)
        if form.is_valid():
            CrearSolicitudReservaService.crear_desde_estudiante(
                form, modulos_ids_str=request.POST.get('modulos_ids', ''),
            )
            return redirect('/solicitudes/exitosa/?tipo=estudiante')
        else:
            logger.debug("solicitud_estudiante | form inválido | errores=%s", form.errors)
    else:
        form = EstudianteSolicitudForm(None)

    programas = ProgramaAcademico.objects.filter(activo=True)
    return render(request, 'solicitudes/estudiante.html', {'form': form, 'programas': programas})


def solicitud_profesor(request):
    if request.method == 'POST':
        es_libre = request.POST.get('reserva_libre') == '1'

        if es_libre:
            datos_libres = dict(
                nombre=request.POST.get('nombre', '').strip(),
                cedula=request.POST.get('cedula', '').strip(),
                email=request.POST.get('email', '').strip(),
                nombre_grupo=request.POST.get('nombre_grupo', '').strip(),
                cantidad_asistentes_str=request.POST.get('cantidad_asistentes', '').strip(),
                descripcion=request.POST.get('descripcion_actividad', '').strip(),
                laboratorio_id=request.POST.get('laboratorio', ''),
                fecha_str=request.POST.get('fecha_reserva', ''),
                hora_inicio_str=request.POST.get('hora_inicio', ''),
                hora_fin_str=request.POST.get('hora_fin', ''),
                observaciones=request.POST.get('observaciones', ''),
                necesita_modulo=request.POST.get('necesita_modulo') == 'on',
                modulos_ids_str=request.POST.get('modulos_ids', ''),
                insumos_ids_str=request.POST.get('insumos_ids', ''),
                insumos_cantidades_str=request.POST.get('insumos_cantidades', ''),
            )

            errores_libres = []
            try:
                ValidarSolicitudReservaService.validar(
                    nombre=datos_libres['nombre'],
                    cedula=datos_libres['cedula'],
                    email=datos_libres['email'],
                    nombre_grupo=datos_libres['nombre_grupo'],
                    cantidad_asistentes_str=datos_libres['cantidad_asistentes_str'],
                    descripcion=datos_libres['descripcion'],
                    laboratorio_id=datos_libres['laboratorio_id'],
                    fecha_str=datos_libres['fecha_str'],
                    hora_inicio_str=datos_libres['hora_inicio_str'],
                    hora_fin_str=datos_libres['hora_fin_str'],
                )
            except ValidationError as e:
                errores_libres = list(e.messages)
            else:
                try:
                    CrearSolicitudReservaService.crear_libre(**datos_libres)
                    return redirect('/solicitudes/exitosa/?tipo=profesor')
                except Exception as e:
                    errores_libres = [f'Error al procesar la solicitud: {e}']

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
                    CrearSolicitudReservaService.crear_desde_profesor(form)
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


def lista_solicitudes(request):
    """Página pública /solicitudes/ con dos pestañas: "Crear Reserva" (los
    formularios de siempre, en /solicitudes/estudiante/ y /solicitudes/
    profesor/ — esta pestaña solo enlaza a ellos, no los reimplementa) y
    "Mis Reservas", autoservicio para ver/cancelar una reserva ya hecha.

    Sin login (no existe cuenta de estudiante en este sistema — ver
    solicitud_estudiante/solicitud_profesor arriba, ambas públicas): "Mis
    Reservas" identifica al dueño por cédula + email (ver
    MisReservasService), los mismos datos que ya se piden al crear la
    solicitud. Antes esta vista tenía @login_required y solo redirigía a
    lista_reservas (la lista de reservas de Administrador/Laboratorio) — se
    quita el decorador porque el público real de esta pestaña (estudiantes,
    profesores) nunca tiene sesión iniciada."""
    cedula = request.GET.get('cedula', '').strip()
    email = request.GET.get('email', '').strip()
    buscado = bool(cedula and email)

    solicitudes_encontradas = []
    error_busqueda = ''
    if buscado:
        solicitudes_encontradas = MisReservasService.buscar(cedula, email)
        if not solicitudes_encontradas:
            error_busqueda = 'No encontramos reservas con esa cédula y ese email.'

    estado_filtro = request.GET.get('estado', '')
    q = request.GET.get('q', '').strip()

    from reservas.services.cancelar_reserva_service import CancelarReservaService
    from reservas.services.estado_prestamo_service import ObtenerEstadoPrestamoService

    filas = []
    for solicitud in solicitudes_encontradas:
        reserva = solicitud.reserva
        if estado_filtro and (not reserva.estado or reserva.estado.nombre != estado_filtro):
            continue
        if q:
            q_lower = q.lower()
            coincide_codigo = q_lower in (reserva.codigo or '').lower()
            coincide_lab = solicitud.laboratorio and q_lower in solicitud.laboratorio.nombre.lower()
            if not coincide_codigo and not coincide_lab:
                continue
        filas.append({
            'solicitud': solicitud,
            'reserva': reserva,
            'estado_prestamo': ObtenerEstadoPrestamoService.obtener(reserva),
            'puede_cancelar': CancelarReservaService.puede_cancelar_propietario(reserva),
        })

    paginator = Paginator(filas, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'solicitudes/lista.html', {
        'buscado': buscado,
        'cedula': cedula,
        'email': email,
        'error_busqueda': error_busqueda,
        'page_obj': page_obj,
        'estado_filtro': estado_filtro,
        'q': q,
    })


def solicitud_exitosa(request):
    tipo = request.GET.get('tipo', 'estudiante')
    return render(request, 'solicitudes/solicitud_exitosa.html', {'tipo': tipo})


def registro_profesor_publico(request):
    errores = []
    post_data = {}

    if request.method == 'POST':
        post_data = request.POST

        try:
            CrearSolicitudRegistroProfesorService.crear(
                nombre=request.POST.get('nombre', '').strip(),
                apellido=request.POST.get('apellido', '').strip(),
                cedula=request.POST.get('cedula', '').strip(),
                correo=request.POST.get('correo', '').strip(),
                programa=request.POST.get('programa', '').strip(),
                nombres_curso=request.POST.getlist('curso_nombre'),
                codigos_curso=request.POST.getlist('curso_codigo'),
                cantidades_curso=request.POST.getlist('curso_cantidad'),
            )
            return redirect('/solicitudes/exitosa/?tipo=registro_profesor')
        except ValidationError as e:
            errores = list(e.messages)

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
    solicitud = get_object_or_404(SolicitudRegistroProfesor, id=id)

    if request.method == 'POST':
        accion = request.POST.get('accion')
        curso_id = request.POST.get('curso_id')

        try:
            if accion == 'aprobar_profesor':
                AprobarSolicitudRegistroProfesorService.aprobar(id)
            elif accion == 'rechazar_profesor':
                AprobarSolicitudRegistroProfesorService.rechazar(id)
            elif accion == 'aprobar_curso':
                AprobarCursoService.aprobar(id, curso_id)
            elif accion == 'rechazar_curso':
                AprobarCursoService.rechazar(id, curso_id)
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))

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
            cantidad_disponible = ItemInventario.activos.filter(
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

@rol_requerido('Administrador', 'Laboratorio')
def lista_cursos(request):
    q = request.GET.get('q', '').strip()
    laboratorio_id = request.GET.get('laboratorio', '').strip()
    cursos = Curso.objects.select_related('profesor', 'laboratorio').order_by('codigo')
    if q:
        cursos = cursos.filter(
            Q(nombre__icontains=q)              |
            Q(codigo__icontains=q)              |
            Q(profesor__first_name__icontains=q) |
            Q(profesor__last_name__icontains=q)
        )
    if laboratorio_id == 'ninguno':
        cursos = cursos.filter(laboratorio__isnull=True)
    elif laboratorio_id.isdigit():
        cursos = cursos.filter(laboratorio_id=int(laboratorio_id))
    else:
        laboratorio_id = ''
    return render(request, 'solicitudes/lista_cursos.html', {
        'cursos': cursos,
        'q': q,
        'laboratorios': Laboratorio.objects.order_by('nombre'),
        'laboratorio_id': laboratorio_id,
    })


@rol_requerido('Administrador', 'Laboratorio')
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


@rol_requerido('Administrador', 'Laboratorio')
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


@rol_requerido('Administrador', 'Laboratorio')
@requiere_contrasena_admin(
    titulo_accion='Eliminar',
    get_contexto=lambda r, *a, **kw: f"Curso - {Curso.objects.get(id=kw['id']).nombre}",
)
def eliminar_curso(request, id):
    curso = get_object_or_404(Curso, id=id)
    if request.method == 'POST':
        nombre = curso.nombre
        curso.delete()
        messages.success(request, f'Curso "{nombre}" eliminado.')
        return redirect('lista_cursos')
    return render(request, 'solicitudes/eliminar_curso.html', {'curso': curso})