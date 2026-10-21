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

class ImportarArchivoForm(forms.Form):
    """Fase 1 de la importación: archivo + laboratorio destino. La
    validación de formato/tamaño la hace ImportadorInventario.validar_archivo
    para que el formulario y el servicio usen exactamente las mismas reglas."""

    archivo = forms.FileField(
        label='Archivo',
        help_text='Excel (.xlsx), CSV (.csv) o PDF (.pdf) — máximo 5 MB.',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx,.xlsm,.csv,.pdf',
        }),
    )

    laboratorio = forms.ModelChoiceField(
        label='Laboratorio destino',
        queryset=None,
        empty_label='Selecciona un laboratorio…',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        from laboratorio.models import Laboratorio
        super().__init__(*args, **kwargs)
        self.fields['laboratorio'].queryset = Laboratorio.objects.filter(activo=True).order_by('nombre')

    def clean_archivo(self):
        from .services.importador import ImportacionError, ImportadorInventario

        archivo = self.cleaned_data['archivo']
        try:
            ImportadorInventario.validar_archivo(archivo)
        except ImportacionError as e:
            raise forms.ValidationError(str(e))
        return archivo
