"""
modulo_service.py — laboratorio
Centraliza el cálculo del estado de un módulo (disponible/ocupado/reservado/
inactivo), antes duplicado de forma independiente en 4 vistas de
laboratorio/views.py (mapa_laboratorio, estado_modulos_api,
modulos_disponibles_api, modulos_disponibles_publica_api).
"""
from datetime import date

from django.utils import timezone

ESTADOS_RESERVA_OCUPAN_MODULO = ('Pendiente', 'Aprobada')


class ModuloEstadoService:
    """
    Determina el estado de un módulo a partir de las SolicitudReserva que lo
    tienen asignado en una fecha dada.

    Estados posibles: 'inactivo' | 'ocupado' | 'reservado' | 'disponible'.
    """

    @staticmethod
    def solicitudes_del_laboratorio(laboratorio, fecha, hora_inicio_filtro=None, hora_fin_filtro=None):
        """
        SolicitudReserva con reserva Pendiente/Aprobada que ocupan módulos de
        `laboratorio` en `fecha`. Si se pasan hora_inicio_filtro y
        hora_fin_filtro, se acota a las que se solapan con ese rango horario.
        """
        from solicitudes.models import SolicitudReserva

        qs = SolicitudReserva.objects.filter(
            laboratorio=laboratorio,
            fecha_reserva__date=fecha,
            reserva__estado__nombre__in=ESTADOS_RESERVA_OCUPAN_MODULO,
            necesita_modulo=True,
        ).select_related('reserva__estado', 'usuario').prefetch_related('modulos_asignados')

        if hora_inicio_filtro and hora_fin_filtro:
            qs = qs.filter(hora_inicio__lt=hora_fin_filtro, hora_fin__gt=hora_inicio_filtro)

        return qs

    @staticmethod
    def agrupar_por_modulo(solicitudes):
        """{modulo_id: [SolicitudReserva, ...]} a partir de un queryset/iterable
        ya obtenido con solicitudes_del_laboratorio."""
        agrupado = {}
        for sol in solicitudes:
            for modulo in sol.modulos_asignados.all():
                agrupado.setdefault(modulo.id, []).append(sol)
        return agrupado

    @classmethod
    def obtener_estado(cls, modulo, solicitudes_modulo=None, fecha=None, evaluar_ahora=True):
        """
        Args:
            modulo: instancia de Modulo.
            solicitudes_modulo: SolicitudReserva que ya ocupan este módulo en
                `fecha` (ver solicitudes_del_laboratorio + agrupar_por_modulo).
                None o lista vacía si no hay ninguna.
            fecha: fecha consultada (default: hoy).
            evaluar_ahora: si True (default), distingue 'ocupado' (una
                solicitud Aprobada en curso justo ahora) de 'reservado' (ocupa
                el módulo pero no en este instante). Si False, toda solicitud
                presente se reporta como 'reservado' — para endpoints que solo
                necesitan disponibilidad del día, sin granularidad de "ahora
                mismo".

        Returns:
            'disponible' | 'ocupado' | 'reservado' | 'inactivo'
        """
        if not modulo.disponible:
            return 'inactivo'

        soles = solicitudes_modulo or []
        if not soles:
            return 'disponible'

        fecha = fecha or date.today()
        if evaluar_ahora and cls._solicitud_en_curso(soles, fecha):
            return 'ocupado'

        return 'reservado'

    @classmethod
    def solicitud_relevante(cls, solicitudes_modulo, fecha=None):
        """
        De las solicitudes que ocupan un módulo, retorna la que está en curso
        ahora mismo si existe, o si no la primera. None si la lista está
        vacía. Útil para mostrar el detalle de quién ocupa el módulo.
        """
        if not solicitudes_modulo:
            return None

        fecha = fecha or date.today()
        if fecha == date.today():
            ahora = timezone.now().time()
            for sol in solicitudes_modulo:
                if cls._esta_en_curso(sol, ahora):
                    return sol

        return solicitudes_modulo[0]

    @classmethod
    def _solicitud_en_curso(cls, soles, fecha):
        if fecha != date.today():
            return False
        ahora = timezone.now().time()
        return any(cls._esta_en_curso(sol, ahora) for sol in soles)

    @staticmethod
    def _esta_en_curso(sol, ahora):
        return bool(
            sol.reserva and sol.reserva.estado
            and sol.reserva.estado.nombre == 'Aprobada'
            and sol.hora_inicio and sol.hora_fin
            and sol.hora_inicio <= ahora <= sol.hora_fin
        )
