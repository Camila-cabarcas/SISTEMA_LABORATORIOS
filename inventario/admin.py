from django.contrib import admin
from .models import (
    EstadoItem,
    Insumo,
    ItemInventario,
    MovimientoInventario,
    TipoMovimiento
)


admin.site.register(EstadoItem)
admin.site.register(Insumo)
admin.site.register(ItemInventario)
admin.site.register(MovimientoInventario)
admin.site.register(TipoMovimiento)