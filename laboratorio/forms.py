"""
forms.py — laboratorio
Formulario LaboratorioForm para crear y editar laboratorios.
"""
from django import forms
from .models import CategoriaModulo, Laboratorio
from users.models import ProgramaAcademico


class LaboratorioForm(forms.ModelForm):

    class Meta:

        model = Laboratorio

        fields = [
            'nombre',
            'ubicacion',
            'programa',
        ]

        widgets = {

            'nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre del laboratorio'
                }
            ),

            'ubicacion': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ubicación'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', '--- Sin programa ---')] + [
            (p.nombre, p.nombre)
            for p in ProgramaAcademico.objects.filter(activo=True)
        ]
        self.fields['programa'] = forms.ChoiceField(
            choices=choices,
            required=False
        )
        self.fields['programa'].widget.attrs.update({
            'class': 'form-select'
        })

class CategoriaModuloForm(forms.ModelForm):
    """Crear/editar una categoría de módulo (solo Administrador)."""

    class Meta:
        model = CategoriaModulo
        fields = ['nombre', 'color', 'forma', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 60}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
            'forma': forms.Select(attrs={'class': 'form-select'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {'activo': 'Activa (se puede asignar a módulos)'}


# ── Personal ────────────────────────────────────────────────────────────────
# Formularios solo de presentación: muestran los campos y convierten el POST.
# Las reglas (correo UdeA, usuario único, un laboratorio, una cuenta de
# monitor por laboratorio, permisos) las valida laboratorio/services/personal.py
# y la vista copia sus errores al formulario (ver views_personal._a_formulario).

_INPUT = {'class': 'form-control'}


class CuentaPersonalForm(forms.Form):
    """Cuenta de laboratorista o de monitor. La contraseña es obligatoria al
    crear; al editar, vacía = no se cambia."""

    username = forms.CharField(label='Nombre de usuario', max_length=150,
                               widget=forms.TextInput(attrs=_INPUT))
    email = forms.CharField(label='Correo institucional (@udea.edu.co)', max_length=254,
                            widget=forms.EmailInput(attrs=_INPUT))
    first_name = forms.CharField(label='Nombre', max_length=150, widget=forms.TextInput(attrs=_INPUT))
    last_name = forms.CharField(label='Apellido', max_length=150, widget=forms.TextInput(attrs=_INPUT))
    laboratorio = forms.ModelChoiceField(
        label='Laboratorio', queryset=Laboratorio.objects.order_by('nombre'),
        empty_label='-- Selecciona un laboratorio --', widget=forms.Select(attrs={'class': 'form-select'}),
    )
    password = forms.CharField(label='Contraseña inicial', strip=False,
                               widget=forms.PasswordInput(attrs={**_INPUT, 'autocomplete': 'new-password'}))

    def __init__(self, *args, editando=False, con_laboratorio=True, **kwargs):
        super().__init__(*args, **kwargs)
        if editando:
            self.fields['password'].required = False
            self.fields['password'].label = 'Nueva contraseña (vacía = no cambiar)'
        if not con_laboratorio:
            del self.fields['laboratorio']


class FichaMonitorForm(forms.Form):
    nombre = forms.CharField(max_length=100, widget=forms.TextInput(attrs=_INPUT))
    apellido = forms.CharField(max_length=100, widget=forms.TextInput(attrs=_INPUT))
    correo = forms.CharField(label='Correo (opcional)', required=False, max_length=254,
                             widget=forms.EmailInput(attrs=_INPUT))
    telefono = forms.CharField(label='Teléfono (opcional)', required=False, max_length=30,
                               widget=forms.TextInput(attrs=_INPUT))
    descripcion = forms.CharField(label='Descripción', required=False,
                                  widget=forms.Textarea(attrs={**_INPUT, 'rows': 3}))
    activo = forms.BooleanField(label='Activa', required=False, initial=True,
                                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))


class DescripcionLaboratorioForm(forms.Form):
    descripcion = forms.CharField(
        label='Descripción general', required=False,
        widget=forms.Textarea(attrs={**_INPUT, 'rows': 6}),
        help_text='Texto plano, sin formato.',
    )
