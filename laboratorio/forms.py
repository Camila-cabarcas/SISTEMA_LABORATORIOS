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
