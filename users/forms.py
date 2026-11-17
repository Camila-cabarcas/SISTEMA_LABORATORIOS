"""
forms.py — users
Formularios de login, de usuarios del sistema (UsuarioForm, EditarUsuarioForm)
y de ProgramaAcademico. Los profesores ya no tienen cuenta: su formulario es
solicitudes.forms.ProfesorHabilitadoForm.
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Usuario, ProgramaAcademico
from .roles import ROLES_SOLO_DESDE_PERSONAL

AYUDA_ROL_PERSONAL = 'Este rol se administra desde Personal.'


def limitar_campo_rol(form):
    """Los roles Laboratorista y Monitor solo se asignan desde Personal
    (llevan laboratorio y reglas propias). En la pantalla genérica de
    usuarios y en el admin de Django:
    - una cuenta que NO tiene esos roles no puede recibirlos;
    - una cuenta que YA los tiene muestra su rol bloqueado (campo
      deshabilitado: Django ignora lo que llegue por POST y conserva el
      valor actual)."""
    campo = form.fields.get('rol')
    if campo is None:
        return
    rol_actual = form.instance.rol if form.instance.pk and form.instance.rol_id else None
    if rol_actual is not None and rol_actual.nombre in ROLES_SOLO_DESDE_PERSONAL:
        campo.disabled = True
        campo.help_text = AYUDA_ROL_PERSONAL
    else:
        campo.queryset = campo.queryset.exclude(nombre__in=ROLES_SOLO_DESDE_PERSONAL)


class LoginForm(AuthenticationForm):
    """Login con usuario o correo en el mismo campo (lo resuelve
    users.backends.UsuarioOCorreoBackend)."""

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Usuario/correo o contraseña incorrectos.',
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        campo = self.fields['username']
        campo.label = 'Usuario o correo'
        # AuthenticationForm toma max_length del username (150); un correo
        # puede llegar a 254.
        campo.max_length = 254
        campo.widget.attrs['maxlength'] = 254
        campo.widget.attrs['autocomplete'] = 'username'


class UsuarioForm(forms.ModelForm):

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Contraseña'
            }
        )
    )

    class Meta:

        model = Usuario

        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'codigo',
            'programa',
            'rol',
            'password',
        ]

        widgets = {

            'username': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre de usuario'
                }
            ),

            'first_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre'
                }
            ),

            'last_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Apellido'
                }
            ),

            'email': forms.EmailInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Correo'
                }
            ),

            'codigo': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Código'
                }
            ),

            'programa': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Programa'
                }
            ),

            'rol': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limitar_campo_rol(self)


class EditarUsuarioForm(forms.ModelForm):

    class Meta:

        model = Usuario

        fields = [
            'first_name',
            'last_name',
            'email',
            'codigo',
            'programa',
            'rol',
        ]

        widgets = {

            'first_name': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'last_name': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'email': forms.EmailInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'codigo': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'programa': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),

            'rol': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limitar_campo_rol(self)


class ProgramaAcademicoForm(forms.ModelForm):

    class Meta:
        model = ProgramaAcademico
        fields = ['nombre', 'activo']
        widgets = {
            'nombre': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Nombre del programa'}
            ),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
