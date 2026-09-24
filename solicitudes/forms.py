"""
forms.py — solicitudes
Formularios EstudianteSolicitudForm, ProfesorSolicitudForm y CursoForm.
"""
from datetime import date
from django import forms
from django.core.exceptions import ValidationError
from .models import SolicitudReserva, Curso, SolicitudInsumo
from inventario.models import Insumo
from laboratorio.models import Laboratorio

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

    email = forms.EmailField(
        label='Email Institucional',
        required=True,
        help_text='Debe ser @udea.edu.co',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'tucorreo@udea.edu.co',
        })
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
        fields = ['nombre', 'cedula', 'email', 'programa', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin', 'necesita_modulo', 'observaciones']
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

        self.fields['laboratorio'].queryset = Laboratorio.objects.filter(activo=True)
        self.fields['fecha_reserva'].widget.attrs['min'] = date.today().isoformat()

        # Cargar programas desde la base de datos
        from users.models import ProgramaAcademico
        self.fields['programa'].choices = (
            [('', '--- Selecciona un programa ---')] +
            [(p.nombre, p.nombre) for p in ProgramaAcademico.objects.filter(activo=True)]
        )

        # Hacer campos requeridos de forma segura
        campos_requeridos = ['nombre', 'cedula', 'programa', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin']
        for campo in campos_requeridos:
            if campo in self.fields:
                self.fields[campo].required = True

    def clean_email(self):
        email = self.cleaned_data.get('email', '')
        if email and not email.lower().endswith('@udea.edu.co'):
            raise ValidationError('El email debe ser institucional (@udea.edu.co).')
        return email

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
    # Opcional (a diferencia de EstudianteSolicitudForm): un profesor con
    # curso registrado queda vinculado a su cuenta Usuario y "Mis Reservas"
    # ya lo encuentra por usuario.email — pero si lo escribe acá, se guarda
    # en SolicitudReserva.email igual que en los demás flujos.
    email = forms.EmailField(
        label='Email Institucional',
        required=False,
        help_text='Debe ser @udea.edu.co',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'tucorreo@udea.edu.co',
        })
    )

    insumos_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    insumos_cantidades = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    modulos_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    class Meta:
        model = SolicitudReserva
        fields = ['nombre', 'cedula', 'email', 'curso', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin', 'necesita_modulo', 'observaciones']
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

        self.fields['laboratorio'].queryset = Laboratorio.objects.filter(activo=True)
        self.fields['fecha_reserva'].widget.attrs['min'] = date.today().isoformat()

        campos_requeridos = ['nombre', 'cedula', 'curso', 'laboratorio', 'fecha_reserva', 'hora_inicio', 'hora_fin']
        for campo in campos_requeridos:
            if campo in self.fields:
                self.fields[campo].required = True

    def clean_email(self):
        email = self.cleaned_data.get('email', '')
        if email and not email.lower().endswith('@udea.edu.co'):
            raise ValidationError('El email debe ser institucional (@udea.edu.co).')
        return email

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
            self._asignar_modulos(instance)

        return instance

    def _asignar_modulos(self, instance):
        """Usa los módulos elegidos manualmente en el mapa del formulario
        (modulos_ids) si el profesor seleccionó alguno; si no marcó
        necesita_modulo, no asigna nada; si lo marcó pero no eligió módulos
        específicos (JS deshabilitado, etc.), cae al reparto automático."""
        if not instance.necesita_modulo:
            return

        ids_str = (self.cleaned_data or {}).get('modulos_ids', '')
        if ids_str:
            from laboratorio.models import Modulo
            ids = [int(x) for x in ids_str.split(',') if x.strip().isdigit()]
            modulos = Modulo.objects.filter(
                id__in=ids,
                laboratorio=instance.laboratorio,
                disponible=True,
            )
            instance.modulos_asignados.set(modulos)
        else:
            instance.asignar_modulos_automaticamente()

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


class CursoForm(forms.ModelForm):

    class Meta:
        model = Curso
        fields = ['nombre', 'codigo', 'laboratorio', 'profesor', 'cantidad_estudiantes']
        widgets = {
            'nombre': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Nombre del curso'}
            ),
            'codigo': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Código único del curso'}
            ),
            'laboratorio': forms.Select(attrs={'class': 'form-select'}),
            'profesor': forms.Select(attrs={'class': 'form-select'}),
            'cantidad_estudiantes': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '1'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from users.models import Usuario
        self.fields['laboratorio'].queryset = Laboratorio.objects.filter(activo=True).order_by('nombre')
        self.fields['laboratorio'].empty_label = 'Sin laboratorio asignado'
        self.fields['profesor'].queryset = Usuario.objects.filter(
            rol__nombre='Docente', is_active=True
        ).order_by('last_name', 'first_name')
        self.fields['profesor'].label_from_instance = lambda obj: \
            f"{obj.get_full_name() or obj.username} — {obj.codigo or 'Sin cédula'}"