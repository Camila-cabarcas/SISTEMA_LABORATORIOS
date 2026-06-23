"""
forms.py — users
Formularios para crear y editar usuarios del sistema (UsuarioForm, EditarUsuarioForm,
ProfesorForm y EditarProfesorForm).
"""
from django import forms
from .models import Usuario


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


class ProfesorForm(forms.ModelForm):

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email', 'codigo', 'programa']
        widgets = {
            'first_name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Nombre'}
            ),
            'last_name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Apellido'}
            ),
            'email': forms.EmailInput(
                attrs={'class': 'form-control', 'placeholder': 'Correo electrónico'}
            ),
            'codigo': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Cédula'}
            ),
            'programa': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Programa académico'}
            ),
        }


class EditarProfesorForm(forms.ModelForm):

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email', 'codigo', 'programa']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'codigo':     forms.TextInput(attrs={'class': 'form-control'}),
            'programa':   forms.TextInput(attrs={'class': 'form-control'}),
        }


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