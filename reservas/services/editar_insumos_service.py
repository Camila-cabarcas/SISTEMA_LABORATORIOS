"""
editar_insumos_service.py — reservas
Permite a un laboratorista editar la lista de insumos (agregar/quitar/cambiar
cantidad) de una Reserva Aprobada, mientras todavía no exista un Prestamo
asociado — una vez hay Prestamo, los ítems ya se entregaron físicamente y la
lista de insumos deja de poder tocarse. Solo insumos: fecha/hora, laboratorio
y módulos de la SolicitudReserva no se pueden cambiar desde acá.
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from inventario.models import Insumo
from laboratorio.models import es_laboratorista_del_laboratorio
from reservas.models import ReservaInsumo

logger = logging.getLogger(__name__)


class EditarInsumosReservaService:

    @staticmethod
    def _laboratorio_de(reserva):
        solicitud = reserva.solicitud.first()
        return solicitud.laboratorio if solicitud else None

    @staticmethod
    def verificar_acceso(reserva, usuario):
        """Lanza PermissionDenied si `usuario` no puede editar los insumos
        de `reserva` ahora mismo. Devuelve el Laboratorio de la reserva
        (o None) para que la vista no tenga que resolverlo de nuevo."""
        es_admin = bool(usuario.rol and usuario.rol.nombre == 'Administrador')
        laboratorio = EditarInsumosReservaService._laboratorio_de(reserva)

        if not es_admin:
            if not es_laboratorista_del_laboratorio(usuario, laboratorio):
                raise PermissionDenied('No eres laboratorista de este laboratorio.')

        if not reserva.estado or reserva.estado.nombre != 'Aprobada':
            raise PermissionDenied(
                'Solo se pueden editar los insumos de una reserva Aprobada.'
            )

        if reserva.prestamo_set.exists():
            raise PermissionDenied(
                'Los insumos de esta reserva ya fueron entregados; no se pueden editar.'
            )

        return laboratorio

    @staticmethod
    def puede_editar(reserva, usuario):
        try:
            EditarInsumosReservaService.verificar_acceso(reserva, usuario)
            return True
        except PermissionDenied:
            return False

    @staticmethod
    def _validar_items(items):
        """items: lista de dicts {'insumo_id': int, 'cantidad': int} con la
        lista COMPLETA deseada de insumos (no un diff). Devuelve la lista
        limpia [{'insumo': Insumo, 'cantidad': int}, ...] o lanza
        ValidationError con todos los mensajes acumulados."""
        vistos = set()
        limpios = []
        errores = []

        for item in items:
            insumo_id = item.get('insumo_id')
            cantidad = item.get('cantidad')

            if insumo_id in vistos:
                errores.append('No puedes agregar el mismo insumo dos veces en la lista.')
                continue
            vistos.add(insumo_id)

            if not isinstance(cantidad, int) or cantidad < 1:
                errores.append('La cantidad debe ser al menos 1.')
                continue

            insumo = Insumo.objects.filter(id=insumo_id).first()
            if not insumo:
                errores.append('Uno de los insumos seleccionados ya no existe.')
                continue

            disponible = insumo.cantidad_disponible()
            if cantidad > disponible:
                errores.append(
                    f'Stock insuficiente para "{insumo.nombre}": pediste {cantidad}, '
                    f'hay {disponible} disponible(s).'
                )
                continue

            limpios.append({'insumo': insumo, 'cantidad': cantidad})

        if errores:
            raise ValidationError(errores)

        return limpios

    @staticmethod
    def _calcular_diferencias(actuales, nuevos):
        """actuales/nuevos: dict {insumo_id: {'insumo':, 'cantidad':}}.
        Devuelve (agregados, quitados, cambiados), cada uno una lista de
        dicts lista para auditoría/email."""
        agregados, quitados, cambiados = [], [], []

        for insumo_id, item in nuevos.items():
            if insumo_id not in actuales:
                agregados.append({'insumo': item['insumo'], 'cantidad': item['cantidad']})
            elif actuales[insumo_id]['cantidad'] != item['cantidad']:
                cambiados.append({
                    'insumo': item['insumo'],
                    'cantidad_anterior': actuales[insumo_id]['cantidad'],
                    'cantidad_nueva': item['cantidad'],
                })

        for insumo_id, item in actuales.items():
            if insumo_id not in nuevos:
                quitados.append({'insumo': item['insumo'], 'cantidad': item['cantidad']})

        return agregados, quitados, cambiados

    @staticmethod
    @transaction.atomic
    def guardar(reserva, usuario, items):
        """
        Reemplaza la lista de ReservaInsumo de `reserva` por `items`
        (lista completa deseada, no un diff) tras validar acceso, stock,
        cantidades y duplicados. Registra auditoría en el log y notifica al
        estudiante por email si algo cambió.

        Returns: (agregados, quitados, cambiados).
        Raises: PermissionDenied (acceso/estado), ValidationError (datos).
        """
        EditarInsumosReservaService.verificar_acceso(reserva, usuario)

        limpios = EditarInsumosReservaService._validar_items(items)

        actuales = {
            ri.insumo_id: {'insumo': ri.insumo, 'cantidad': ri.cantidad}
            for ri in ReservaInsumo.objects.filter(reserva=reserva).select_related('insumo')
        }
        nuevos = {item['insumo'].id: item for item in limpios}

        agregados, quitados, cambiados = EditarInsumosReservaService._calcular_diferencias(
            actuales, nuevos,
        )

        ReservaInsumo.objects.filter(reserva=reserva).delete()
        for item in limpios:
            ReservaInsumo.objects.create(
                reserva=reserva, insumo=item['insumo'], cantidad=item['cantidad'],
            )

        logger.info(
            'EditarInsumosReservaService.guardar | Laboratorista %s modificó insumos de reserva %s '
            '| agregados=%s | quitados=%s | cambiados=%s',
            usuario.username, reserva.id,
            [(a['insumo'].nombre, a['cantidad']) for a in agregados],
            [(q['insumo'].nombre, q['cantidad']) for q in quitados],
            [(c['insumo'].nombre, c['cantidad_anterior'], c['cantidad_nueva']) for c in cambiados],
        )

        if agregados or quitados or cambiados:
            try:
                from utils.notificaciones_email import notificar_cambios_o_prestamo_listo
                notificar_cambios_o_prestamo_listo(
                    reserva, tipo='cambios',
                    agregados=agregados, quitados=quitados, cambiados=cambiados,
                )
            except Exception:
                logger.exception(
                    'EditarInsumosReservaService.guardar | error notificando modificación | reserva_id=%s',
                    reserva.id,
                )

        return agregados, quitados, cambiados
