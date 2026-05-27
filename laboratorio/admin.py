from django.contrib import admin
from .models import Laboratorio, HorarioLaboratorio, EventoLaboratorio

admin.site.register(Laboratorio)
admin.site.register(HorarioLaboratorio)
admin.site.register(EventoLaboratorio)