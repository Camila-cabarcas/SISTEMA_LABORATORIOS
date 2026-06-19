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
            'encargado',
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

            'encargado': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'programa': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Programa académico'
                }
            ),
        }