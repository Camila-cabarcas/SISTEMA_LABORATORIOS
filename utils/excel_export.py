"""
excel_export.py — utils
Construye archivos Excel (openpyxl) con formato profesional para reservas,
préstamos e inspecciones. Cada función arma un Workbook en memoria a partir
de un queryset/iterable ya filtrado; no sabe nada de HTTP ni escribe en
disco — las vistas (reservas/views.py, prestamos/views.py) lo envuelven en
un FileResponse.
"""
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ENCABEZADO_FILL = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
ENCABEZADO_FONT = Font(color='FFFFFF', bold=True)
FILA_ALTERNA_FILL = PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid')

_side = Side(style='thin', color='D9D9D9')
BORDE_SUTIL = Border(left=_side, right=_side, top=_side, bottom=_side)


def _construir_hoja(wb, titulo_hoja, columnas, filas):
    """Aplica el mismo formato (encabezado azul, filas alternadas, bordes
    sutiles, ancho automático y pie con timestamp) a cualquier hoja."""
    ws = wb.active
    ws.title = titulo_hoja

    ws.append(columnas)
    for celda in ws[1]:
        celda.fill = ENCABEZADO_FILL
        celda.font = ENCABEZADO_FONT
        celda.alignment = Alignment(horizontal='center', vertical='center')
        celda.border = BORDE_SUTIL

    for i, fila in enumerate(filas, start=2):
        ws.append(fila)
        relleno = FILA_ALTERNA_FILL if i % 2 == 0 else None
        for celda in ws[i]:
            celda.border = BORDE_SUTIL
            if relleno:
                celda.fill = relleno

    for col_idx, columna in enumerate(columnas, start=1):
        letra = get_column_letter(col_idx)
        largo_max = len(str(columna))
        for fila in filas:
            valor = fila[col_idx - 1]
            largo_max = max(largo_max, len(str(valor)) if valor is not None else 0)
        ws.column_dimensions[letra].width = min(largo_max + 4, 50)

    ws.freeze_panes = 'A2'

    fila_footer = ws.max_row + 2
    footer = ws.cell(
        row=fila_footer, column=1,
        value=f'Generado el {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    )
    footer.font = Font(italic=True, size=9, color='808080')

    return ws


def _nombre_solicitante(reserva):
    solicitud = next(iter(reserva.solicitud.all()), None)
    if solicitud:
        return solicitud, solicitud.nombre or '—'
    if reserva.usuario:
        return None, str(reserva.usuario)
    return None, '—'


def export_reservas_excel(reservas):
    """Columnas: ID, Solicitante, Laboratorio, Fecha, Estado, Módulos."""
    wb = Workbook()
    columnas = ['ID', 'Solicitante', 'Laboratorio', 'Fecha', 'Estado', 'Módulos']

    filas = []
    for reserva in reservas:
        solicitud, solicitante = _nombre_solicitante(reserva)
        if solicitud:
            laboratorio = solicitud.laboratorio.nombre if solicitud.laboratorio else '—'
            modulos = ', '.join(m.nombre for m in solicitud.modulos_asignados.all()) or '—'
        else:
            laboratorio = '—'
            modulos = '—'

        filas.append([
            reserva.id,
            solicitante,
            laboratorio,
            reserva.fecha_reserva.strftime('%Y-%m-%d %H:%M') if reserva.fecha_reserva else '—',
            reserva.estado.nombre if reserva.estado else '—',
            modulos,
        ])

    _construir_hoja(wb, 'Reservas', columnas, filas)
    return wb


def export_prestamos_excel(prestamos):
    """Columnas: ID, Reserva, Estado, Items (cantidad), Fecha Creación, Fecha Devolución."""
    wb = Workbook()
    columnas = ['ID', 'Reserva', 'Estado', 'Items (cantidad)', 'Fecha Creación', 'Fecha Devolución']

    filas = []
    for prestamo in prestamos:
        filas.append([
            prestamo.id,
            prestamo.reserva.codigo or f'#{prestamo.reserva_id}',
            prestamo.estado.nombre if prestamo.estado else '—',
            len(prestamo.prestamoitem_set.all()),
            prestamo.fecha_entrega.strftime('%Y-%m-%d %H:%M') if prestamo.fecha_entrega else '—',
            prestamo.fecha_devolucion.strftime('%Y-%m-%d %H:%M') if prestamo.fecha_devolucion else '—',
        ])

    _construir_hoja(wb, 'Préstamos', columnas, filas)
    return wb


def export_inspecciones_excel(inspecciones):
    """Columnas: ID Préstamo, Ítem, Estado Inspección."""
    wb = Workbook()
    columnas = ['ID Préstamo', 'Ítem', 'Estado Inspección']

    filas = []
    for insp in inspecciones:
        filas.append([
            insp.prestamo_id,
            insp.prestamo_item.item_inventario.codigo,
            insp.get_estado_inspeccion_display(),
        ])

    _construir_hoja(wb, 'Inspecciones', columnas, filas)
    return wb
