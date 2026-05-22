from django import forms
from .models import Insumo
from .models import (
    ItemInventario,
    MovimientoInventario
)


class InsumoForm(forms.ModelForm):

    class Meta:

        model = Insumo

        fields = [
            'nombre',
            'descripcion',
            'estado'
        ]

        widgets = {

            'nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre'
                }
            ),

            'descripcion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Descripción'
                }
            ),

            'estado': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            )
        }


class ItemInventarioForm(forms.ModelForm):

    class Meta:

        model = ItemInventario

        fields = [
            'codigo',
            'insumo',
            'estado',
            'laboratorio'
        ]

        widgets = {

            'codigo': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Código'
                }
            ),

            'insumo': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'estado': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'laboratorio': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            )
        }

class MovimientoInventarioForm(forms.ModelForm):

    class Meta:

        model = MovimientoInventario

        fields = [
        'item_inventario',
        'tipo_movimiento',
        'observacion'
]

        widgets = {

            'item_inventario': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),


            'tipo_movimiento': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'observacion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Observación'
                }
            )
        }