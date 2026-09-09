"""
forms.py — vetos
Formulario para que un Laboratorista registre manualmente un veto de tipo
"No canceló y dejó pasar el préstamo" (infracción A). El resto de tipos
(RETRASO, DANO, FALTA_INSUMO) se crean automáticamente al finalizar la
inspección de una devolución — ver vetos.services.RegistrarVetoService.
"""
from django import forms


class VetoNoCanceloForm(forms.Form):
    cedula = forms.CharField(
        max_length=50,
        label='Cédula del solicitante',
        widget=forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric'}),
    )
    motivo = forms.CharField(
        required=False,
        label='Detalle (opcional)',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                     'placeholder': 'Contexto de la infracción...'}),
    )

    def clean_cedula(self):
        cedula = self.cleaned_data['cedula'].strip()
        if not cedula:
            raise forms.ValidationError('La cédula es requerida.')
        return cedula
