"""
estado_prestamo_service.py — reservas
Traduce el Prestamo (si existe) vinculado a una Reserva a uno de 4 "buckets"
de estado pensados para mostrarle a quien hizo la reserva, sin que tenga que
entender el modelo Prestamo/EstadoPrestamo por dentro: SIN_PRESTAMO, ACTIVO,
DEVUELTO, RETRASADO. El estado real "En Inspección" (EstadoPrestamo, entre
que se marca la devolución y se completa la inspección) se agrupa bajo
ACTIVO para la vista simplificada de 4 estados — sigue "en curso" desde la
perspectiva de quien reservó — pero se conserva el nombre real en
`prestamo.estado.nombre` por si un template quiere distinguirlo.
"""


class ObtenerEstadoPrestamoService:

    SIN_PRESTAMO = 'sin_prestamo'
    ACTIVO = 'activo'
    DEVUELTO = 'devuelto'
    RETRASADO = 'retrasado'

    _BUCKET_POR_ESTADO = {
        'Activo': ACTIVO,
        'En Inspección': ACTIVO,
        'Devuelto': DEVUELTO,
        'Retrasado': RETRASADO,
    }

    @staticmethod
    def obtener(reserva):
        """Devuelve {'tipo': uno de los 4 buckets, 'prestamo': Prestamo|None}.
        Si una Reserva llegara a tener más de un Prestamo (no debería, pero
        el modelo no lo impide a nivel de BD), usa el más reciente por
        fecha_entrega."""
        prestamo = reserva.prestamo_set.select_related('estado').order_by('-fecha_entrega').first()

        if not prestamo:
            return {'tipo': ObtenerEstadoPrestamoService.SIN_PRESTAMO, 'prestamo': None}

        nombre_estado = prestamo.estado.nombre if prestamo.estado else ''
        tipo = ObtenerEstadoPrestamoService._BUCKET_POR_ESTADO.get(
            nombre_estado, ObtenerEstadoPrestamoService.ACTIVO,
        )
        return {'tipo': tipo, 'prestamo': prestamo}
