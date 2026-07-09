"""
forms.py — laboratorio
Formulario LaboratorioForm para crear y editar laboratorios.
"""
from django import forms
from .models import Laboratorio
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