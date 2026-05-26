from django import forms
from .models import Prestamo, PrestamoItem
from inventario.models import ItemInventario


class PrestamoForm(forms.ModelForm):

    class Meta:

        model = Prestamo

        fields = [
            'responsable',
        ]

        widgets = {
            'responsable': forms.Select(
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item_inventario'].queryset = ItemInventario.objects.filter(
            estado__nombre='Disponible'
        )