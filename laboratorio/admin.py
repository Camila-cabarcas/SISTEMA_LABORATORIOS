from django.contrib import admin
from django import forms
from .models import Laboratorio, HorarioLaboratorio, EventoLaboratorio, Modulo
from .models import HistorialModulo
from users.models import ProgramaAcademico


class LaboratorioAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', '--- Sin programa ---')] + [
            (p.nombre, p.nombre)
            for p in ProgramaAcademico.objects.filter(activo=True)
        ]
        self.fields['programa'] = forms.ChoiceField(
            choices=choices,
            required=False
        )

    class Meta:
        model = Laboratorio
        fields = '__all__'


class LaboratorioAdmin(admin.ModelAdmin):
    form = LaboratorioAdminForm
    list_display = ('nombre', 'ubicacion', 'activo')
    list_filter = ('activo',)


admin.site.register(Laboratorio, LaboratorioAdmin)
admin.site.register(HorarioLaboratorio)
admin.site.register(EventoLaboratorio)
admin.site.register(Modulo)
admin.site.register(HistorialModulo)
