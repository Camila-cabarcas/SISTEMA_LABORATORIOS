"""
prestamo_stock_service.py — prestamos
Valida disponibilidad de stock de un Insumo ANTES de dejar que se elija para
un préstamo, con un mensaje de error claro cuando no queda ninguno.

El descuento real de stock (Disponible → Prestado) y su reintegro
(Prestado → Disponible/Dañado/Perdido, según cómo se devolvió) ya los maneja
prestamos.services.mutacion_inventario_service.MutacionInventarioService,
disparado automáticamente por prestamos/signals.py apenas se crea un
PrestamoItem o cambia el estado de un Prestamo — este service no duplica esa
mutación, solo la validación previa que hoy no existía como paso explícito.
"""
from django.core.exceptions import ValidationError


class PrestamoStockService:

    @staticmethod
    def hay_disponible(insumo, cantidad=1):
        """True si `insumo` tiene al menos `cantidad` ítems en estado
        Disponible (ver Insumo.stock_disponible)."""
        return insumo.stock_disponible() >= cantidad

    @staticmethod
    def validar_disponibilidad(insumo, cantidad=1):
        """Como hay_disponible(), pero lanza ValidationError con un mensaje
        listo para mostrar al usuario en vez de devolver un bool — para usar
        como guardia al inicio de una vista/service que va a crear un
        préstamo."""
        disponible = insumo.stock_disponible()
        if disponible < cantidad:
            raise ValidationError(
                f'Sin stock disponible de "{insumo.nombre}". '
                f'Disponible ahora mismo: {disponible}. '
                f'Intenta de nuevo más tarde o elige otro insumo.'
            )
