from django.contrib import admin
from .models import EstadoPrestamo, Prestamo, PrestamoItem


admin.site.register(EstadoPrestamo)
admin.site.register(Prestamo)
admin.site.register(PrestamoItem)