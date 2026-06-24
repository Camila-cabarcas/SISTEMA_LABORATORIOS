"""
forms.py — laboratorio
Formulario LaboratorioForm para crear y editar laboratorios.
"""
from django import forms
from .models import Laboratorio


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

            'programa': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Programa académico'
                }
            ),
        }