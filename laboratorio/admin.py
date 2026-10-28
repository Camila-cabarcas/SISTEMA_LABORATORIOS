from django.contrib import admin
from django import forms
from .models import CategoriaModulo, Division, Laboratorio, HorarioLaboratorio, EventoLaboratorio, Modulo
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
@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    # El máximo por laboratorio lo valida Division.clean() (el ModelForm del
    # admin llama a full_clean()).
    list_display = ('nombre', 'laboratorio', 'x', 'y', 'ancho', 'alto')
    list_filter = ('laboratorio',)


@admin.register(CategoriaModulo)
class CategoriaModuloAdmin(admin.ModelAdmin):
    # Borrar una categoría con módulos falla por PROTECT; se desactiva (activo=False).
    list_display = ('nombre', 'color', 'forma', 'activo')
    list_filter = ('activo', 'forma')


class ModuloAdminForm(forms.ModelForm):
    """Selector de categoría: solo las activas, más la que el módulo ya tenga
    (aunque se haya desactivado), para no perderla al guardar."""

    class Meta:
        model = Modulo
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        activas = CategoriaModulo.objects.filter(activo=True)
        if self.instance.categoria_id:
            activas = activas | CategoriaModulo.objects.filter(pk=self.instance.categoria_id)
        self.fields['categoria'].queryset = activas.distinct()


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    form = ModuloAdminForm
    list_display = ('nombre', 'laboratorio', 'categoria', 'division', 'capacidad', 'disponible')
    list_filter = ('laboratorio', 'categoria', 'division', 'disponible')
    list_select_related = ('laboratorio', 'categoria', 'division')
admin.site.register(HistorialModulo)
