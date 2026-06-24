"""
forms.py — users
Formularios para crear y editar usuarios del sistema (UsuarioForm, EditarUsuarioForm,
ProfesorForm y EditarProfesorForm) y gestión de ProgramaAcademico.
"""
from django import forms
from .models import Usuario, ProgramaAcademico


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

    programa = forms.ModelChoiceField(
        queryset=ProgramaAcademico.objects.filter(activo=True),
        required=False,
        empty_label='-- Selecciona un programa --',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

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
        }

    def clean_programa(self):
        programa = self.cleaned_data.get('programa')
        return programa.nombre if programa else ''


class EditarProfesorForm(forms.ModelForm):

    programa = forms.ModelChoiceField(
        queryset=ProgramaAcademico.objects.filter(activo=True),
        required=False,
        empty_label='-- Selecciona un programa --',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email', 'codigo', 'programa']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'email':      forms.EmailInput(attrs={'class': 'form-control'}),
            'codigo':     forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.programa:
            prog = ProgramaAcademico.objects.filter(
                nombre=self.instance.programa
            ).first()
            if prog:
                self.initial['programa'] = prog.pk

    def clean_programa(self):
        programa = self.cleaned_data.get('programa')
        return programa.nombre if programa else ''


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
