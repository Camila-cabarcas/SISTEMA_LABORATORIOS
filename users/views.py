"""
views.py — users
Vistas para listar, crear, editar y desactivar usuarios del sistema (solo Administrador),
y gestión completa de profesores (Administrador o Encargado).
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from users.decorators import rol_requerido
from .models import Usuario, Rol
from .forms import UsuarioForm, EditarUsuarioForm, ProfesorForm, EditarProfesorForm


@rol_requerido('Administrador')
def lista_usuarios(request):

    usuarios = Usuario.objects.all().order_by('username')

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

@rol_requerido('Administrador', 'Encargado')
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
    return render(request, 'usuarios/lista_profesores.html', {
        'profesores': profesores,
        'q': q,
    })


@rol_requerido('Administrador', 'Encargado')
def crear_profesor(request):
    if request.method == 'POST':
        form = ProfesorForm(request.POST)
        if form.is_valid():
            profesor = form.save(commit=False)
            profesor.set_password(form.cleaned_data['password'])
            profesor.rol = Rol.objects.filter(nombre='Docente').first()
            profesor.save()
            return redirect('lista_profesores')
    else:
        form = ProfesorForm()
    return render(request, 'usuarios/crear_profesor.html', {'form': form})


@rol_requerido('Administrador', 'Encargado')
def detalle_profesor(request, id):
    from solicitudes.models import Curso
    profesor = get_object_or_404(Usuario, id=id, rol__nombre='Docente')
    cursos = Curso.objects.filter(profesor=profesor).order_by('codigo')
    return render(request, 'usuarios/detalle_profesor.html', {
        'profesor': profesor,
        'cursos': cursos,
    })


@rol_requerido('Administrador', 'Encargado')
def editar_profesor(request, id):
    profesor = get_object_or_404(Usuario, id=id, rol__nombre='Docente')
    if request.method == 'POST':
        form = EditarProfesorForm(request.POST, instance=profesor)
        if form.is_valid():
            form.save()
            return redirect('detalle_profesor', id=profesor.id)
    else:
        form = EditarProfesorForm(instance=profesor)
    return render(request, 'usuarios/editar_profesor.html', {
        'form': form,
        'profesor': profesor,
    })