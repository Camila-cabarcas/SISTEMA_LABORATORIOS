"""
views.py — users
Vistas para listar, crear, editar y desactivar usuarios del sistema (solo Administrador),
profesores habilitados (sin cuenta, solo Administrador) y programas académicos.
"""
import logging

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q
from django.views.decorators.http import require_POST
from users.decorators import rol_requerido, requiere_contrasena_admin
from users.helpers import es_cuenta_de_personal
from .models import Usuario, ProgramaAcademico
from .forms import UsuarioForm, EditarUsuarioForm, ProgramaAcademicoForm

logger_acceso_admin = logging.getLogger('acceso_admin')


@rol_requerido('Administrador')
def lista_usuarios(request):

    usuarios = Usuario.objects.exclude(username__startswith='lab_').select_related('rol').order_by('username')

    return render(
        request,
        'users/lista.html',
        {
            'usuarios': usuarios
        }
    )


@rol_requerido('Administrador')
def crear_usuario(request):

    if request.method == 'POST':

        form = UsuarioForm(request.POST)

        if form.is_valid():

            usuario = form.save(commit=False)
            usuario.set_password(form.cleaned_data['password'])
            usuario.save()

            return redirect('lista_usuarios')

    else:

        form = UsuarioForm()

    return render(
        request,
        'users/crear.html',
        {
            'form': form
        }
    )


@rol_requerido('Administrador')
def editar_usuario(request, id):

    usuario = get_object_or_404(Usuario, id=id)

    if request.method == 'POST':

        form = EditarUsuarioForm(request.POST, instance=usuario)

        if form.is_valid():

            form.save()

            return redirect('lista_usuarios')

    else:

        form = EditarUsuarioForm(instance=usuario)

    return render(
        request,
        'users/editar.html',
        {
            'form': form,
            'usuario': usuario
        }
    )


def _rechazar_cuenta_de_personal(request, usuario):
    """Las cuentas Laboratorista y Monitor se dan de baja desde Personal
    (con contraseña admin, usando dar_de_baja_laboratorista o
    dar_de_baja_monitor, que además les quitan el laboratorio)."""
    return render(request, 'users/sin_permiso.html', {
        'mensaje': f'La cuenta "{usuario.username}" es de rol {usuario.rol.nombre}: '
                   f'se da de baja desde Personal, no desde aquí.',
    }, status=403)


@rol_requerido('Administrador')
def desactivar_usuario(request, id):
    """Las cuentas de Personal se rechazan ANTES de pedir la contraseña
    admin; las demás siguen el flujo de siempre."""
    usuario = get_object_or_404(Usuario.objects.select_related('rol'), id=id)
    if es_cuenta_de_personal(usuario):
        return _rechazar_cuenta_de_personal(request, usuario)
    return _desactivar_usuario_confirmado(request, id=id)


@requiere_contrasena_admin(
    titulo_accion='Desactivar',
    get_contexto=lambda r, *a, **kw: f"Usuario - {Usuario.objects.get(id=kw['id']).username}",
)
def _desactivar_usuario_confirmado(request, id):

    usuario = get_object_or_404(Usuario.objects.select_related('rol'), id=id)
    if es_cuenta_de_personal(usuario):  # por si cambió el rol entre los dos pasos
        return _rechazar_cuenta_de_personal(request, usuario)

    if request.method == 'POST':

        usuario.is_active = False
        usuario.save()

        messages.success(request, f'Usuario "{usuario.username}" desactivado.')
        return redirect('lista_usuarios')

    return render(
        request,
        'users/desactivar.html',
        {
            'usuario': usuario
        }
    )


def sin_permiso(request):
    return render(request, 'users/sin_permiso.html')


@rol_requerido('Administrador', 'Laboratorista')
def cambiar_contrasena_admin(request):
    """
    Permite crear o cambiar la contraseña admin (distinta de la de login).
    Exige la contraseña de login actual para confirmar identidad antes de
    guardar la nueva contraseña admin.
    """
    if request.method == 'POST':
        password_login = request.POST.get('password_login', '')
        password_admin_nueva = request.POST.get('password_admin_nueva', '')
        password_admin_confirma = request.POST.get('password_admin_confirma', '')

        if not request.user.check_password(password_login):
            messages.error(request, 'Contraseña de login incorrecta.')
        elif password_admin_nueva != password_admin_confirma:
            messages.error(request, 'Las contraseñas admin no coinciden.')
        elif len(password_admin_nueva) < 8:
            messages.error(request, 'La contraseña admin debe tener mínimo 8 caracteres.')
        else:
            request.user.set_admin_password(password_admin_nueva)
            logger_acceso_admin.info(
                '%s configuró/cambió su contraseña admin', request.user.username,
            )
            messages.success(request, 'Contraseña admin actualizada correctamente.')
            return redirect('cambiar_contrasena_admin')

    return render(request, 'users/cambiar_contrasena_admin.html')


# ── Profesores habilitados (fase 2: sin cuenta) ─────────────────────────────
# Solo el Administrador. Lista, ver, editar (nombre, apellido, correo,
# programa) y desactivar. No se crean cuentas: un profesor se habilita al
# aprobar su solicitud de registro (o vino de la migración de las cuentas
# Docente).

@rol_requerido('Administrador')
def lista_profesores(request):
    from solicitudes.models import Profesor

    q = request.GET.get('q', '').strip()
    profesores = Profesor.objects.annotate(total_cursos=Count('cursos')).order_by('apellido', 'nombre')
    if q:
        profesores = profesores.filter(
            Q(nombre__icontains=q) | Q(apellido__icontains=q) | Q(cedula__icontains=q) | Q(correo__icontains=q)
        )
    return render(request, 'profesores/lista_profesores.html', {'profesores': profesores, 'q': q})


@rol_requerido('Administrador')
def detalle_profesor(request, id):
    from solicitudes.models import Curso, Profesor

    profesor = get_object_or_404(Profesor, id=id)
    cursos = Curso.objects.filter(profesor=profesor).select_related('laboratorio').order_by('codigo')
    return render(request, 'profesores/detalle_profesor.html', {'profesor': profesor, 'cursos': cursos})


@rol_requerido('Administrador')
def editar_profesor(request, id):
    from solicitudes.forms import ProfesorHabilitadoForm
    from solicitudes.models import Profesor

    profesor = get_object_or_404(Profesor, id=id)
    form = ProfesorHabilitadoForm(request.POST or None, instance=profesor)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Profesor "{profesor.nombre_completo}" actualizado.')
        return redirect('detalle_profesor', id=profesor.id)
    return render(request, 'profesores/editar_profesor.html', {'form': form, 'profesor': profesor})


@rol_requerido('Administrador')
@require_POST
def desactivar_profesor(request, id):
    """activo=False: deja de poder reservar cursos y de aparecer al crear
    cursos. Sus cursos y reservas se conservan."""
    from solicitudes.models import Profesor

    profesor = get_object_or_404(Profesor, id=id)
    if profesor.activo:
        profesor.activo = False
        profesor.save(update_fields=['activo'])
        messages.success(request, f'Profesor "{profesor.nombre_completo}" desactivado.')
    else:
        messages.info(request, f'El profesor "{profesor.nombre_completo}" ya estaba desactivado.')
    return redirect('detalle_profesor', id=profesor.id)


# ── Gestión de programas académicos ─────────────────────────────────────────

@rol_requerido('Administrador')
def lista_programas(request):
    from laboratorio.models import Laboratorio
    programas = ProgramaAcademico.objects.all()
    for p in programas:
        p.labs = Laboratorio.objects.filter(programa=p.nombre)
    return render(request, 'programas/lista_programas.html', {'programas': programas})


@rol_requerido('Administrador')
def crear_programa(request):
    if request.method == 'POST':
        form = ProgramaAcademicoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_programas')
    else:
        form = ProgramaAcademicoForm()
    return render(request, 'programas/crear_programa.html', {'form': form})


@rol_requerido('Administrador')
def editar_programa(request, id):
    programa = get_object_or_404(ProgramaAcademico, id=id)
    if request.method == 'POST':
        form = ProgramaAcademicoForm(request.POST, instance=programa)
        if form.is_valid():
            form.save()
            return redirect('lista_programas')
    else:
        form = ProgramaAcademicoForm(instance=programa)
    return render(request, 'programas/editar_programa.html', {
        'form': form,
        'programa': programa,
    })


@rol_requerido('Administrador')
@requiere_contrasena_admin(
    titulo_accion='Eliminar',
    get_contexto=lambda r, *a, **kw: f"Programa - {ProgramaAcademico.objects.get(id=kw['id']).nombre}",
)
def eliminar_programa(request, id):
    from solicitudes.models import SolicitudReserva, SolicitudRegistroProfesor
    programa = get_object_or_404(ProgramaAcademico, id=id)
    error = None
    if request.method == 'POST':
        if (Usuario.objects.filter(programa=programa.nombre).exists() or
                SolicitudReserva.objects.filter(programa=programa.nombre).exists() or
                SolicitudRegistroProfesor.objects.filter(programa=programa.nombre).exists()):
            error = 'No se puede eliminar: hay registros vinculados a este programa.'
        else:
            nombre = programa.nombre
            programa.delete()
            messages.success(request, f'Programa "{nombre}" eliminado.')
            return redirect('lista_programas')
    return render(request, 'programas/confirmar_eliminar_programa.html', {
        'programa': programa,
        'error': error,
    })