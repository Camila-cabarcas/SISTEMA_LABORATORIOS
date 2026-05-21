from django import forms
from .models import Reserva, ReservaInsumo


class ReservaForm(forms.ModelForm):

    class Meta:

        model = Reserva

        fields = [
            'fecha_reserva',
        ]

        widgets = {
            'fecha_reserva': forms.DateTimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local'
                }
            ),
        }


class ReservaInsumoForm(forms.ModelForm):

    class Meta:

        model = ReservaInsumo

        fields = [
            'insumo',
            'cantidad',
        ]

        widgets = {

            'insumo': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'cantidad': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1
                }
            ),
        }