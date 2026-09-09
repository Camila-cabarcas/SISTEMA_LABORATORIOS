"""
services.py — vetos
Lógica de negocio de los vetos:

- RegistrarVetoService: crea vetos, de forma manual (Laboratorista registra un
  "no canceló") o automática (al finalizar la inspección de una devolución con
  atraso, daño o falta de ítems).
- consultar_bloqueo / mensaje_bloqueo: usados por SolicitudReserva.clean() y
  los flujos de creación de reserva para rechazar a un solicitante vetado.
"""
import logging

from vetos.models import Veto

logger = logging.getLogger(__name__)


def identidad_de_reserva(reserva):
    """(cedula, usuario) del solicitante de `reserva`, sacados de su
    SolicitudReserva — misma pareja de identificadores que usa el resto del
    sistema. Devuelve ('', None) si no se puede resolver."""
    if reserva is None:
        return '', None
    solicitud = reserva.solicitud.first()
    if solicitud is None:
        return '', None
    return (solicitud.cedula or ''), solicitud.usuario


def consultar_bloqueo(*, cedula=None, usuario=None):
    """El Veto vigente más relevante para esta persona, o None. 'Más
    relevante' = el que la libera más tarde; los indefinidos (hasta
    reponer/pagar) ganan sobre los que tienen fecha."""
    vigentes = list(Veto.vigentes_para(cedula=cedula, usuario=usuario))
    if not vigentes:
        return None

    indefinidos = [v for v in vigentes if v.fecha_fin is None]
    if indefinidos:
        return indefinidos[0]
    return max(vigentes, key=lambda v: v.fecha_fin)


def mensaje_bloqueo(veto):
    """Texto que se le muestra al solicitante bloqueado."""
    if veto.fecha_fin is None:
        hasta = 'que repongas o pagues el insumo pendiente'
    else:
        hasta = f"el {veto.fecha_fin.strftime('%d/%m/%Y')}"
    motivo = veto.motivo or veto.get_tipo_display()
    return f"Estás bloqueado hasta {hasta}. Razón: {motivo}"


class RegistrarVetoService:
    """Crea vetos aplicando el castigo que corresponde a cada tipo de
    infracción. Todos los métodos devuelven el Veto creado (o None si no
    había nada que sancionar)."""

    # ── Manual ─────────────────────────────────────────────────────────
    @staticmethod
    def registrar_no_cancelo(*, reserva=None, cedula=None, usuario=None,
                             creado_por=None, motivo=''):
        """Infracción A: el solicitante no canceló y dejó pasar el préstamo.
        1 día de bloqueo; 7 si acumula 3+ infracciones de este tipo."""
        if reserva is not None and not (cedula or usuario):
            cedula, usuario = identidad_de_reserva(reserva)
        cedula = cedula or ''
        if not cedula and usuario is None:
            raise ValueError('No se pudo identificar al solicitante del veto.')

        dias = Veto.calcular_dias_no_cancelo(cedula=cedula, usuario=usuario)
        veto = Veto(
            cedula=cedula,
            usuario=usuario,
            tipo=Veto.NO_CANCELO,
            fecha_fin=Veto._fecha_fin_desde_hoy(dias),
            reserva=reserva,
            creado_por=creado_por,
            motivo=motivo or (
                f'No canceló la reserva y dejó pasar el préstamo '
                f'({dias} día(s) de bloqueo).'
            ),
        )
        veto.full_clean()
        veto.save()
        logger.info(
            'RegistrarVetoService.registrar_no_cancelo | veto_id=%s | cedula=%s | dias=%s',
            veto.id, cedula, dias,
        )
        return veto

    # ── Automático (al finalizar la devolución) ───────────────────────
    @staticmethod
    def registrar_retraso(*, prestamo, dias_atraso, creado_por=None):
        """Infracción B: devolución tardía. 2 días de bloqueo por cada día
        de atraso."""
        if dias_atraso <= 0:
            return None
        cedula, usuario = identidad_de_reserva(prestamo.reserva)
        dias_bloqueo = dias_atraso * Veto.DIAS_BLOQUEO_POR_DIA_ATRASO
        veto = Veto(
            cedula=cedula,
            usuario=usuario,
            tipo=Veto.RETRASO,
            fecha_fin=Veto._fecha_fin_desde_hoy(dias_bloqueo),
            reserva=prestamo.reserva,
            prestamo=prestamo,
            creado_por=creado_por,
            motivo=(
                f'Devolución con {dias_atraso} día(s) de atraso '
                f'→ {dias_bloqueo} día(s) de bloqueo.'
            ),
        )
        veto.full_clean()
        veto.save()
        logger.info(
            'RegistrarVetoService.registrar_retraso | veto_id=%s | prestamo_id=%s | dias_atraso=%s',
            veto.id, prestamo.id, dias_atraso,
        )
        return veto

    @staticmethod
    def registrar_dano(*, prestamo, tipo=Veto.DANO, detalle='', creado_por=None):
        """Infracciones C y D: ítem dañado/extraviado o no entregado.
        Bloqueo indefinido (fecha_fin=None) hasta que un Administrador
        verifique la reposición o el pago."""
        cedula, usuario = identidad_de_reserva(prestamo.reserva)
        etiqueta = 'Insumo dañado o extraviado' if tipo == Veto.DANO else 'Falta de insumo'
        veto = Veto(
            cedula=cedula,
            usuario=usuario,
            tipo=tipo,
            fecha_fin=None,
            reserva=prestamo.reserva,
            prestamo=prestamo,
            creado_por=creado_por,
            motivo=(f'{etiqueta}. {detalle}'.strip()
                    + ' Bloqueado hasta reponer o pagar.'),
        )
        veto.full_clean()
        veto.save()
        logger.info(
            'RegistrarVetoService.registrar_dano | veto_id=%s | prestamo_id=%s | tipo=%s',
            veto.id, prestamo.id, tipo,
        )
        return veto

    # ── Orquestador ──────────────────────────────────────────────────
    @staticmethod
    def registrar_por_devolucion(prestamo, inspecciones=None):
        """Se llama al finalizar la inspección de una devolución. Crea los
        vetos que correspondan según:
        - atraso: prestamo.fecha_devolucion vs. reserva.fecha_devolucion,
        - daño/pérdida: inspecciones en estado 'danado',
        - falta: inspecciones en estado 'no_entregado'.
        Nunca levanta excepción hacia afuera: un fallo acá no debe abortar
        la devolución (se registra en el log)."""
        creados = []
        try:
            if inspecciones is None:
                from prestamos.models import InspeccionItem
                inspecciones = list(
                    InspeccionItem.objects.filter(prestamo=prestamo)
                )

            # B) Retraso
            reserva = prestamo.reserva
            esperada = getattr(reserva, 'fecha_devolucion', None)
            real = prestamo.fecha_devolucion
            if esperada and real and real > esperada:
                dias_atraso = (real.date() - esperada.date()).days
                if dias_atraso < 1:
                    dias_atraso = 1
                veto = RegistrarVetoService.registrar_retraso(
                    prestamo=prestamo, dias_atraso=dias_atraso,
                )
                if veto:
                    creados.append(veto)

            # C) Daño / extravío
            if any(i.estado_inspeccion == 'danado' for i in inspecciones):
                creados.append(RegistrarVetoService.registrar_dano(
                    prestamo=prestamo, tipo=Veto.DANO,
                    detalle='Detectado en la inspección de devolución.',
                ))

            # D) Falta de insumo (no entregado)
            if any(i.estado_inspeccion == 'no_entregado' for i in inspecciones):
                creados.append(RegistrarVetoService.registrar_dano(
                    prestamo=prestamo, tipo=Veto.FALTA_INSUMO,
                    detalle='Ítem(s) no entregado(s) en la devolución.',
                ))
        except Exception:
            logger.exception(
                'RegistrarVetoService.registrar_por_devolucion | error creando vetos | prestamo_id=%s',
                getattr(prestamo, 'id', None),
            )
        return creados
