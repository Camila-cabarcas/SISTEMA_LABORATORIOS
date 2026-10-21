"""
Tests de ImportadorInventario (inventario/services/importador.py), fase 1:
lectura de Excel/CSV/PDF, detección de encabezados y columnas, preview y
errores de archivo inválido. No toca la base de datos.
"""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from inventario.services.importador import (
    ImportacionError,
    ImportadorInventario,
    detectar_columnas,
    normalizar,
)


# ── Helpers para fabricar archivos ────────────────────────────────────────

def _subir(nombre, contenido):
    return SimpleUploadedFile(nombre, contenido)


def _xlsx(filas_por_hoja):
    """{'Hoja': [[...], ...]} → bytes de un .xlsx."""
    wb = Workbook()
    wb.remove(wb.active)
    for titulo, filas in filas_por_hoja.items():
        ws = wb.create_sheet(titulo)
        for fila in filas:
            ws.append(fila)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _pdf_con_tabla(filas, paginas=1):
    """PDF mínimo (sin librerías) con `filas` dibujadas como tabla con
    bordes en cada página — lo que pdfplumber detecta como tabla."""
    ancho_col, alto_fila, x0, y_top = 120, 20, 50, 750
    n_cols = len(filas[0])

    def stream():
        ops = ['0.5 w']
        for i in range(len(filas) + 1):
            y = y_top - i * alto_fila
            ops.append(f'{x0} {y} m {x0 + n_cols * ancho_col} {y} l S')
        for j in range(n_cols + 1):
            x = x0 + j * ancho_col
            ops.append(f'{x} {y_top} m {x} {y_top - len(filas) * alto_fila} l S')
        for i, fila in enumerate(filas):
            for j, texto in enumerate(fila):
                x = x0 + j * ancho_col + 4
                y = y_top - (i + 1) * alto_fila + 6
                ops.append(f'BT /F1 9 Tf {x} {y} Td ({texto}) Tj ET')
        return '\n'.join(ops).encode('latin-1')

    contenido = stream()
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        None,  # Pages, se arma abajo
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length %d >>\nstream\n' % len(contenido) + contenido + b'\nendstream',
    ]
    kids = []
    for _ in range(paginas):
        objetos.append(
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
            b'/Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>'
        )
        kids.append(f'{len(objetos)} 0 R')
    objetos[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {paginas} >>'.encode()

    salida = io.BytesIO()
    salida.write(b'%PDF-1.4\n')
    offsets = []
    for n, obj in enumerate(objetos, start=1):
        offsets.append(salida.tell())
        salida.write(b'%d 0 obj\n' % n + obj + b'\nendobj\n')
    xref = salida.tell()
    salida.write(b'xref\n0 %d\n0000000000 65535 f \n' % (len(objetos) + 1))
    for off in offsets:
        salida.write(b'%010d 00000 n \n' % off)
    salida.write(b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objetos) + 1, xref))
    return salida.getvalue()


ENCABEZADO = ['Código', 'Nombre', 'Marca', 'Cantidad']
FILAS = [
    ['MUL-01', 'Multímetro digital', 'Fluke', 3],
    ['OSC-01', 'Osciloscopio', 'Tektronix', 1],
]


def _preview(nombre, contenido):
    return ImportadorInventario(_subir(nombre, contenido)).preview()


# ── Detección de columnas ─────────────────────────────────────────────────

class TestDeteccionColumnas:

    def test_normalizar(self):
        assert normalizar('  Código de Inventario: ') == 'codigo de inventario'

    def test_coincidencias_exactas(self):
        assert detectar_columnas(['Código', 'Nombre', 'Descripción', 'Marca', 'Cantidad', 'Estado']) == {
            'Código': 'codigo', 'Nombre': 'nombre', 'Descripción': 'descripcion',
            'Marca': 'marca', 'Cantidad': 'cantidad', 'Estado': 'estado',
        }

    def test_sinonimos_y_contiene(self):
        mapeo = detectar_columnas(['Placa', 'Nombre del insumo', 'Fabricante', 'Unidades'])
        assert mapeo == {'Placa': 'codigo', 'Nombre del insumo': 'nombre',
                         'Fabricante': 'marca', 'Unidades': 'cantidad'}

    def test_stock_minimo_no_se_confunde_con_cantidad(self):
        mapeo = detectar_columnas(['Stock', 'Stock mínimo', 'Nombre'])
        assert mapeo['Stock mínimo'] == 'stock_minimo'
        assert mapeo['Stock'] == 'cantidad'

    def test_item_no_es_nombre(self):
        # En los inventarios "Ítem" suele ser el número de fila.
        assert detectar_columnas(['Ítem', 'Equipo'])  == {'Equipo': 'nombre'}

    def test_cada_campo_una_sola_vez(self):
        mapeo = detectar_columnas(['Nombre', 'Insumo'])
        assert list(mapeo.values()).count('nombre') == 1

    def test_columnas_desconocidas_quedan_sin_asignar(self):
        assert detectar_columnas(['Ubicación', 'Responsable']) == {}


# ── CSV ───────────────────────────────────────────────────────────────────

class TestCSV:

    def test_coma_utf8(self):
        csv = 'Código,Nombre,Marca,Cantidad\nMUL-01,Multímetro,Fluke,3\nOSC-01,Osciloscopio,Tek,1\n'
        p = _preview('inv.csv', csv.encode('utf-8'))
        assert p['formato'] == 'CSV'
        assert [c['nombre'] for c in p['columnas']] == ENCABEZADO
        assert p['filas'][0] == ['MUL-01', 'Multímetro', 'Fluke', '3']
        assert p['total_filas'] == 2
        assert p['mapeo']['Nombre'] == 'nombre'

    def test_punto_y_coma_latin1_como_excel_en_espanol(self):
        csv = 'Código;Nombre;Descripción\nA-1;Pipeta;Vidrio 10 ml\n'
        p = _preview('inv.csv', csv.encode('cp1252'))
        assert [c['nombre'] for c in p['columnas']] == ['Código', 'Nombre', 'Descripción']
        assert p['filas'] == [['A-1', 'Pipeta', 'Vidrio 10 ml']]

    def test_utf8_con_bom(self):
        p = _preview('inv.csv', '﻿Nombre,Marca\nPipeta,Brand\n'.encode('utf-8'))
        assert p['columnas'][0]['nombre'] == 'Nombre'

    def test_preview_limita_a_10_filas(self):
        csv = 'Nombre,Cantidad\n' + ''.join(f'Insumo {i},{i}\n' for i in range(25))
        p = _preview('inv.csv', csv.encode())
        assert len(p['filas']) == 10
        assert p['total_filas'] == 25

    def test_descarta_filas_y_columnas_vacias(self):
        csv = 'Nombre,,Marca\nPipeta,,Brand\n,,\nBureta,,Pyrex\n'
        p = _preview('inv.csv', csv.encode())
        assert [c['nombre'] for c in p['columnas']] == ['Nombre', 'Marca']
        assert p['total_filas'] == 2

    def test_encabezados_duplicados_o_vacios(self):
        csv = 'Nombre,Nombre,\nA,B,C\n'
        p = _preview('inv.csv', csv.encode())
        assert [c['nombre'] for c in p['columnas']] == ['Nombre', 'Nombre (2)', 'Columna 3']

    def test_solo_encabezados(self):
        with pytest.raises(ImportacionError, match='solo tiene encabezados'):
            _preview('inv.csv', b'Nombre,Marca\n')

    def test_sin_columna_nombre_advierte(self):
        p = _preview('inv.csv', b'Placa,Marca\nA-1,Fluke\n')
        assert any('Nombre' in a for a in p['advertencias'])


# ── Excel ─────────────────────────────────────────────────────────────────

class TestExcel:

    def test_basico(self):
        p = _preview('inv.xlsx', _xlsx({'Inventario': [ENCABEZADO, *FILAS]}))
        assert p['formato'] == 'XLSX'
        assert [c['nombre'] for c in p['columnas']] == ENCABEZADO
        # Enteros sin ".0".
        assert p['filas'][0] == ['MUL-01', 'Multímetro digital', 'Fluke', '3']

    def test_encabezado_debajo_de_un_titulo(self):
        filas = [
            ['INVENTARIO LABORATORIO DE QUÍMICA'],
            ['Fecha: 2026-10-01'],
            [],
            ENCABEZADO,
            *FILAS,
        ]
        p = _preview('inv.xlsx', _xlsx({'Hoja1': filas}))
        assert [c['nombre'] for c in p['columnas']] == ENCABEZADO
        assert p['total_filas'] == 2
        assert any('omitieron' in a for a in p['advertencias'])

    def test_usa_la_primera_hoja_con_datos_y_avisa(self):
        archivo = _xlsx({'Vacía': [], 'Equipos': [ENCABEZADO, *FILAS], 'Otra': [['Nombre'], ['X']]})
        p = _preview('inv.xlsx', archivo)
        assert p['total_filas'] == 2
        assert any('"Equipos"' in a for a in p['advertencias'])

    def test_excel_sin_datos(self):
        with pytest.raises(ImportacionError, match='no tiene datos'):
            _preview('inv.xlsx', _xlsx({'Hoja1': []}))

    def test_excel_corrupto(self):
        with pytest.raises(ImportacionError, match='Excel'):
            _preview('inv.xlsx', b'esto no es un zip')


# ── PDF ───────────────────────────────────────────────────────────────────

class TestPDF:

    def test_tabla(self):
        filas = [['Codigo', 'Nombre', 'Marca'], ['MUL-01', 'Multimetro', 'Fluke'], ['OSC-01', 'Osciloscopio', 'Tek']]
        p = _preview('inv.pdf', _pdf_con_tabla(filas))
        assert p['formato'] == 'PDF'
        assert [c['nombre'] for c in p['columnas']] == ['Codigo', 'Nombre', 'Marca']
        assert p['filas'] == [['MUL-01', 'Multimetro', 'Fluke'], ['OSC-01', 'Osciloscopio', 'Tek']]

    def test_varias_paginas_no_repite_encabezado(self):
        filas = [['Nombre', 'Marca'], ['Pipeta', 'Brand']]
        p = _preview('inv.pdf', _pdf_con_tabla(filas, paginas=3))
        assert p['filas'] == [['Pipeta', 'Brand']] * 3

    def test_pdf_sin_tablas(self, monkeypatch):
        import pdfplumber

        class Pagina:
            def extract_tables(self):
                return []

        class PDF:
            pages = [Pagina()]
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(pdfplumber, 'open', lambda *_: PDF())
        with pytest.raises(ImportacionError, match='No se encontraron tablas'):
            _preview('inv.pdf', b'%PDF-1.4 algo')

    def test_pdf_corrupto(self):
        with pytest.raises(ImportacionError, match='PDF'):
            _preview('inv.pdf', b'no soy un pdf')


# ── Validación del archivo ───────────────────────────────────────────────

class TestValidacion:

    @pytest.mark.parametrize('nombre', ['inv.docx', 'inv.txt', 'inventario'])
    def test_extension_no_soportada(self, nombre):
        with pytest.raises(ImportacionError, match='Formato no soportado'):
            ImportadorInventario.validar_archivo(_subir(nombre, b'x'))

    def test_xls_viejo_pide_xlsx(self):
        with pytest.raises(ImportacionError, match='guárdalo como .xlsx'):
            ImportadorInventario.validar_archivo(_subir('inv.xls', b'x'))

    def test_archivo_vacio(self):
        with pytest.raises(ImportacionError, match='vacío'):
            ImportadorInventario.validar_archivo(_subir('inv.csv', b''))

    def test_archivo_muy_grande(self, monkeypatch):
        monkeypatch.setattr(ImportadorInventario, 'TAMANO_MAXIMO', 10)
        with pytest.raises(ImportacionError, match='máximo'):
            ImportadorInventario.validar_archivo(_subir('inv.csv', b'x' * 11))

    def test_extension_en_mayusculas(self):
        p = _preview('INV.CSV', b'Nombre\nPipeta\n')
        assert p['filas'] == [['Pipeta']]
