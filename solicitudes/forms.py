from django import forms
from .models import SolicitudReserva, Curso


class EstudianteSolicitudForm(forms.ModelForm):
    class Meta:
        model = SolicitudReserva
        fields = ['laboratorio', 'fecha_reserva', 'observaciones']
        widgets = {
            'laboratorio': forms.Select(attrs={'class': 'form-select'}),
            'fecha_reserva': forms.DateTimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local'
                }
            ),
            'observaciones': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Observaciones (opcional)'
                }
            ),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.instance.tipo_solicitante = 'estudiante'
        self.instance.usuario = user

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.usuario = self.user
        instance.tipo_solicitante = 'estudiante'
        if commit:
            instance.save()
        return instance


class ProfesorSolicitudForm(forms.ModelForm):
    class Meta:
        model = SolicitudReserva
        fields = ['nombre', 'cedula', 'curso', 'laboratorio', 'fecha_reserva', 'observaciones']
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
            'fecha_reserva': forms.DateTimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local'
                }
            ),
            'observaciones': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Observaciones (opcional)'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.tipo_solicitante = 'profesor'
        self.fields['nombre'].required = True
        self.fields['cedula'].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.tipo_solicitante = 'profesor'
        instance.clean()

        if commit:
            instance.save()
            instance.asignar_modulos_automaticamente()

        return instance
