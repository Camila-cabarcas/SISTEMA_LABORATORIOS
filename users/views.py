"""
views.py — users
Vistas para listar, crear, editar y desactivar usuarios del sistema (solo Administrador),
y gestión completa de profesores (Administrador o Encargado).
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from users.decorators import rol_requerido
from .models import Usuario, Rol, ProgramaAcademico
from .forms import UsuarioForm, EditarUsuarioForm, ProfesorForm, EditarProfesorForm, ProgramaAcademicoForm


@rol_requerido('Administrador')
def lista_usuarios(request):

    usuarios = Usuario.objects.exclude(username__startswith='lab_').order_by('username')

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


@rol_requerido('Administrador')
def desactivar_usuario(request, id):

    usuario = get_object_or_404(Usuario, id=id)

    if request.method == 'POST':

        usuario.is_active = False
        usuario.save()

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


# ── Gestión de profesores ────────────────────────────────────────────────────

@rol_requerido('Administrador', 'Laboratorio')
def lista_profesores(request):
    q = request.GET.get('q', '').strip()
    profesores = Usuario.objects.filter(rol__nombre='Docente').order_by('last_name', 'first_name')
    if q:
        profesores = profesores.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q)  |
            Q(codigo__icontains=q)     |
            Q(username__icontains=q)
        )
    return render(request, 'profesores/lista_profesores.html', {
        'profesores': profesores,
        'q': q,
    })


@rol_requerido('Administrador', 'Laboratorio')
def crear_profesor(request):
    import secrets
    import string

    if request.method == 'POST':
        form = ProfesorForm(request.POST)
        if form.is_valid():
            profesor = form.save(commit=False)

            # Username automático: "doc_<cedula>", con sufijo si ya existe
            cedula = form.cleaned_data['codigo']
            base   = f"doc_{cedula}"
            username = base
            counter  = 2
            while Usuario.objects.filter(username=username).exists():
                username = f"{base}_{counter}"
                counter += 1
            profesor.username = username
            profesor.email = form.cleaned_data.get('email', '')

            # Contraseña aleatoria — el profesor no usa el sistema
            alphabet = string.ascii_letters + string.digits
            profesor.set_password(''.join(secrets.choice(alphabet) for _ in range(16)))

            profesor.rol       = Rol.objects.filter(nombre='Docente').first()
            profesor.is_active = True
            profesor.save()
            return redirect('lista_profesores')
    else:
        form = ProfesorForm()
    programas = ProgramaAcademico.objects.filter(activo=True)
    return render(request, 'profesores/crear_profesor.html', {'form': form, 'programas': programas})


@rol_requerido('Administrador', 'Laboratorio')
def detalle_profesor(request, id):
    from solicitudes.models import Curso
    profesor = get_object_or_404(Usuario, id=id, rol__nombre='Docente')
    cursos = Curso.objects.filter(profesor=profesor).order_by('codigo')
    return render(request, 'profesores/detalle_profesor.html', {
        'profesor': profesor,
        'cursos': cursos,
    })


@rol_requerido('Administrador', 'Laboratorio')
def editar_profesor(request, id):
    profesor = get_object_or_404(Usuario, id=id, rol__nombre='Docente')
    if request.method == 'POST':
        form = EditarProfesorForm(request.POST, instance=profesor)
        if form.is_valid():
            form.save()
            return redirect('detalle_profesor', id=profesor.id)
    else:
        form = EditarProfesorForm(instance=profesor)
    programas = ProgramaAcademico.objects.filter(activo=True)
    return render(request, 'profesores/editar_profesor.html', {
        'form': form,
        'profesor': profesor,
        'programas': programas,
    })


@rol_requerido('Administrador')
def toggle_profesor(request, id):
    profesor = get_object_or_404(Usuario, id=id, rol__nombre='Docente')
    if request.method == 'POST':
        profesor.is_active = not profesor.is_active
        profesor.save()
    return redirect('detalle_profesor', id=id)


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
            programa.delete()
            return redirect('lista_programas')
    return render(request, 'programas/confirmar_eliminar_programa.html', {
        'programa': programa,
        'error': error,
    })