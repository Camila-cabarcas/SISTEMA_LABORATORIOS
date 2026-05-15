from django.contrib import admin
from .models import EstadoReserva, Reserva, ReservaInsumo


admin.site.register(EstadoReserva)
admin.site.register(Reserva)
admin.site.register(ReservaInsumo)