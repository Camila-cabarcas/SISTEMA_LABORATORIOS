"""
forms.py — inventario
Formularios InsumoForm, ItemInventarioForm y MovimientoInventarioForm.
"""
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
            'laboratorio',
            'descripcion',
            'marca',
            'stock_minimo',
            'estado',
        ]

        widgets = {

            'nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre'
                }
            ),

            'laboratorio': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'descripcion': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Descripción'
                }
            ),

            'marca': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Marca (opcional)'
                }
            ),

            'stock_minimo': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': '0'
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
                    'placeholder': 'Información'
                }
            )
        }

        labels = {
            'observacion': 'Información',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mismos nombres visibles que la tabla (TipoMovimiento.etiqueta).
        self.fields['tipo_movimiento'].label_from_instance = lambda tipo: tipo.etiqueta