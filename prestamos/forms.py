from django import forms
from .models import Prestamo, PrestamoItem


class PrestamoForm(forms.ModelForm):

    class Meta:

        model = Prestamo

        fields = [
            'reserva',
            'responsable',
            'estado',
        ]

        widgets = {

            'reserva': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'responsable': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'estado': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),
        }


class CambiarEstadoPrestamoForm(forms.ModelForm):

    class Meta:

        model = Prestamo

        fields = ['estado']

        widgets = {
            'estado': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            )
        }


class PrestamoItemForm(forms.ModelForm):

    class Meta:

        model = PrestamoItem

        fields = ['item_inventario']

        widgets = {
            'item_inventario': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            )
        }