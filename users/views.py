from django.shortcuts import render, redirect, get_object_or_404
from users.decorators import rol_requerido
from .models import Usuario
from .forms import UsuarioForm, EditarUsuarioForm


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