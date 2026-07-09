from django.contrib import admin
from .models import Laboratorio, HorarioLaboratorio, EventoLaboratorio, Modulo
from .models import HistorialModulo

admin.site.register(Laboratorio)
admin.site.register(HorarioLaboratorio)
admin.site.register(EventoLaboratorio)
admin.site.register(Modulo)
admin.site.register(HistorialModulo)