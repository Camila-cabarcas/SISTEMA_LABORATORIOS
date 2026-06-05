from django import forms
from .models import SolicitudReserva, Curso, SolicitudInsumo
from inventario.models import Insumo


class EstudianteSolicitudForm(forms.ModelForm):
    insumos = forms.ModelMultipleChoiceField(
        queryset=Insumo.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Insumos requeridos'
    )

    class Meta:
        model = SolicitudReserva
        fields = ['laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin', 'necesita_modulo', 'observaciones']
        widgets = {
            'laboratorio': forms.Select(attrs={'class': 'form-select'}),
            'fecha_reserva': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date'
                }
            ),
            'hora_inicio': forms.TimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'time'
                }
            ),
            'hora_fin': forms.TimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'time'
                }
            ),
            'necesita_modulo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'observaciones': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Observaciones (opcional)'
                }
            ),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.tipo_solicitante = 'estudiante'
        self.instance.usuario = user

        # Hacer campos requeridos
        self.fields['laboratorio'].required = True
        self.fields['fecha_reserva'].required = True
        self.fields['hora_inicio'].required = True
        self.fields['hora_fin'].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.usuario = self.user
        instance.tipo_solicitante = 'estudiante'
        instance.clean()

        if commit:
            instance.save()
            self._guardar_insumos(instance)

        return instance

    def _guardar_insumos(self, instance):
        insumos = self.cleaned_data.get('insumos', [])
        SolicitudInsumo.objects.filter(solicitud=instance).delete()
        for insumo in insumos:
            SolicitudInsumo.objects.create(
                solicitud=instance,
                insumo=insumo,
                cantidad=1
            )


class ProfesorSolicitudForm(forms.ModelForm):
    insumos = forms.ModelMultipleChoiceField(
        queryset=Insumo.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Insumos requeridos'
    )

    class Meta:
        model = SolicitudReserva
        fields = ['nombre', 'cedula', 'curso', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin', 'necesita_modulo', 'observaciones']
        widgets = {
            'nombre': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Nombre completo'
                }
            ),
            'cedula': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Cédula'
                }
            ),
            'curso': forms.Select(attrs={'class': 'form-select'}),
            'laboratorio': forms.Select(attrs={'class': 'form-select'}),
            'fecha_reserva': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date'
                }
            ),
            'hora_inicio': forms.TimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'time'
                }
            ),
            'hora_fin': forms.TimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'time'
                }
            ),
            'necesita_modulo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'observaciones': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Observaciones (opcional)'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.tipo_solicitante = 'profesor'
        self.fields['nombre'].required = True
        self.fields['cedula'].required = True
        self.fields['curso'].required = True
        self.fields['laboratorio'].required = True
        self.fields['fecha_reserva'].required = True
        self.fields['hora_inicio'].required = True
        self.fields['hora_fin'].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.tipo_solicitante = 'profesor'
        instance.clean()

        if commit:
            instance.save()
            self._guardar_insumos(instance)
            instance.asignar_modulos_automaticamente()

        return instance

    def _guardar_insumos(self, instance):
        insumos = self.cleaned_data.get('insumos', [])
        SolicitudInsumo.objects.filter(solicitud=instance).delete()
        for insumo in insumos:
            SolicitudInsumo.objects.create(
                solicitud=instance,
                insumo=insumo,
                cantidad=1
            )
