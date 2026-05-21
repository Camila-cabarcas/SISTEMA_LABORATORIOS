from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Usuario
from .forms import UsuarioForm, EditarUsuarioForm


@login_required
def lista_usuarios(request):

    usuarios = Usuario.objects.all().order_by('username')

    return render(
        request,
        'users/lista.html',
        {
            'usuarios': usuarios
        }
    )


@login_required
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


@login_required
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


@login_required
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