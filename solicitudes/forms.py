"""
forms.py — solicitudes
Formularios EstudianteSolicitudForm y ProfesorSolicitudForm con guardado de insumos y validación de cédula.
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import SolicitudReserva, Curso, SolicitudInsumo
from inventario.models import Insumo

CARRERAS_INGENIERIA = [
    ('', '--- Selecciona una carrera ---'),
    ('Ingeniería de Sistemas', 'Ingeniería de Sistemas'),
    ('Ingeniería Civil', 'Ingeniería Civil'),
    ('Ingeniería Eléctrica', 'Ingeniería Eléctrica'),
    ('Ingeniería Mecánica', 'Ingeniería Mecánica'),
    ('Ingeniería Industrial', 'Ingeniería Industrial'),
    ('Ingeniería de Software', 'Ingeniería de Software'),
    ('Ingeniería Química', 'Ingeniería Química'),
    ('Ingeniería Electrónica', 'Ingeniería Electrónica'),
    ('Ingeniería Ambiental', 'Ingeniería Ambiental'),
    ('Ingeniería de Telecomunicaciones', 'Ingeniería de Telecomunicaciones'),
]


class EstudianteSolicitudForm(forms.ModelForm):
    programa = forms.ChoiceField(
        choices=CARRERAS_INGENIERIA,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    insumos_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    insumos_cantidades = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    class Meta:
        model = SolicitudReserva
        fields = ['nombre', 'cedula', 'programa', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin', 'necesita_modulo', 'observaciones']
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
                    'placeholder': 'Número de identificación',
                    'type': 'number'
                }
            ),
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
        if user and user.is_authenticated:
            self.instance.usuario = user

        # Hacer campos requeridos de forma segura
        campos_requeridos = ['nombre', 'cedula', 'programa', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin']
        for campo in campos_requeridos:
            if campo in self.fields:
                self.fields[campo].required = True

    def clean(self):
        cleaned_data = super().clean() or {}

        # Validar que cédula sea solo números
        cedula = cleaned_data.get('cedula', '')
        if cedula and not str(cedula).isdigit():
            raise ValidationError({'cedula': 'La cédula debe contener solo números.'})

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user and self.user.is_authenticated:
            instance.usuario = self.user
        instance.tipo_solicitante = 'estudiante'
        instance.clean()

        if commit:
            instance.save()
            self._guardar_insumos(instance)

        return instance

    def _guardar_insumos(self, instance):
        cleaned_data = self.cleaned_data or {}
        ids_str = cleaned_data.get('insumos_ids', '')
        cantidades_str = cleaned_data.get('insumos_cantidades', '')

        if not ids_str:
            return

        try:
            ids = [int(id_num) for id_num in str(ids_str).split(',') if id_num]
            cantidades = [int(cant) for cant in str(cantidades_str).split(',') if cant]

            SolicitudInsumo.objects.filter(solicitud=instance).delete()

            for insumo_id, cantidad in zip(ids, cantidades):
                try:
                    insumo = Insumo.objects.get(id=insumo_id)
                    SolicitudInsumo.objects.create(
                        solicitud=instance,
                        insumo=insumo,
                        cantidad=cantidad
                    )
                except Insumo.DoesNotExist:
                    pass
        except (ValueError, AttributeError):
            pass


class ProfesorSolicitudForm(forms.ModelForm):
    insumos_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    insumos_cantidades = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
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
                    'placeholder': 'Cédula',
                    'type': 'number'
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

        campos_requeridos = ['nombre', 'cedula', 'curso', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin']
        for campo in campos_requeridos:
            if campo in self.fields:
                self.fields[campo].required = True

    def clean(self):
        cleaned_data = super().clean() or {}

        # Validar que cédula sea solo números
        cedula = cleaned_data.get('cedula', '')
        if cedula and not str(cedula).isdigit():
            raise ValidationError({'cedula': 'La cédula debe contener solo números.'})

        return cleaned_data

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
        cleaned_data = self.cleaned_data or {}
        ids_str = cleaned_data.get('insumos_ids', '')
        cantidades_str = cleaned_data.get('insumos_cantidades', '')

        if not ids_str:
            return

        try:
            ids = [int(id_num) for id_num in str(ids_str).split(',') if id_num]
            cantidades = [int(cant) for cant in str(cantidades_str).split(',') if cant]

            SolicitudInsumo.objects.filter(solicitud=instance).delete()

            for insumo_id, cantidad in zip(ids, cantidades):
                try:
                    insumo = Insumo.objects.get(id=insumo_id)
                    SolicitudInsumo.objects.create(
                        solicitud=instance,
                        insumo=insumo,
                        cantidad=cantidad
                    )
                except Insumo.DoesNotExist:
                    pass
        except (ValueError, AttributeError):
            pass