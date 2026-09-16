"""
forms.py — prestamos
Formularios PrestamoForm, CambiarEstadoPrestamoForm y PrestamoItemForm.
"""
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
    """Formulario para agregar un ítem a un préstamo ya creado (ver
    prestamos/views.py:detalle_prestamo). El queryset se restringe a ítems
    Disponible por la misma razón que crear_prestamo filtra los suyos: un
    ítem Prestado/Dañado/Perdido no debe poder agregarse a un préstamo —
    el signal que corre al crear el PrestamoItem lo pasaría a 'Prestado' sin
    importar en qué estado estuviera, lo que permitiría prestarlo dos veces
    a la vez."""

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
        self.fields['item_inventario'].queryset = ItemInventario.activos.filter(
            estado__nombre='Disponible'
        )