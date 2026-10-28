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


# ══ Fase 2: mapeo, validación y guardado ══════════════════════════════════

MAPEO = {'Código': 'codigo', 'Nombre': 'nombre', 'Marca': 'marca', 'Estado': 'estado', 'Stock mínimo': 'stock_minimo'}
CABECERA = 'Código,Nombre,Marca,Estado,Stock mínimo\n'


def _importador_csv(cuerpo, cabecera=CABECERA):
    return ImportadorInventario(_subir('inv.csv', (cabecera + cuerpo).encode('utf-8')))


def _validar(cuerpo, laboratorio, mapeo=MAPEO, cabecera=CABECERA):
    return _importador_csv(cuerpo, cabecera).validar(mapeo, laboratorio).resumen()


def _mensajes(lista):
    return [x['mensaje'] for x in lista]


class TestMapeo:

    COLUMNAS = ['Código', 'Nombre', 'Marca']

    def test_mapeo_valido(self):
        assert ImportadorInventario.validar_mapeo({'Código': 'codigo', 'Nombre': 'nombre'}, self.COLUMNAS) == []

    def test_faltan_obligatorios(self):
        errores = ImportadorInventario.validar_mapeo({'Marca': 'marca'}, self.COLUMNAS)
        assert any('Nombre' in e for e in errores)
        assert any('Código' in e for e in errores)

    def test_campo_en_dos_columnas(self):
        errores = ImportadorInventario.validar_mapeo(
            {'Código': 'codigo', 'Nombre': 'nombre', 'Marca': 'nombre'}, self.COLUMNAS,
        )
        assert errores == ['El campo Nombre está asignado a dos columnas: "Nombre" y "Marca".']

    def test_campo_o_columna_desconocidos(self):
        errores = ImportadorInventario.validar_mapeo(
            {'Código': 'codigo', 'Nombre': 'nombre', 'Marca': 'precio', 'Fantasma': 'marca'}, self.COLUMNAS,
        )
        assert 'Campo desconocido para la columna "Marca".' in errores
        assert 'La columna "Fantasma" no existe en el archivo.' in errores

    def test_mapeo_manual_reasigna_columnas(self, catalogos, laboratorio):
        # La columna "Serial" no se detecta como Código por nombre exacto en
        # este archivo, pero el usuario puede asignarla a mano.
        cabecera = 'Equipo,Serial\n'
        resumen = _validar('Pipeta,X-1\n', laboratorio, mapeo={'Equipo': 'nombre', 'Serial': 'codigo'}, cabecera=cabecera)
        assert resumen['items'][0]['codigo'] == 'X-1'
        assert resumen['items'][0]['insumo'] == 'Pipeta'

    def test_columnas_ignoradas_no_se_usan(self, catalogos, laboratorio):
        mapeo = {'Código': 'codigo', 'Nombre': 'nombre'}  # Marca ignorada
        resumen = _validar('A-1,Pipeta,Brand,,\n', laboratorio, mapeo=mapeo)
        assert resumen['insumos_nuevos'][0]['marca'] == ''


@pytest.mark.django_db
class TestValidacionFase2:

    def test_simula_sin_guardar(self, catalogos, laboratorio):
        from inventario.models import Insumo, ItemInventario

        resumen = _validar('A-1,Pipeta,Brand,Disponible,2\nA-2,Pipeta,Brand,,\nB-1,Bureta,,Dañado,\n', laboratorio)

        assert [i['nombre'] for i in resumen['insumos_nuevos']] == ['Pipeta', 'Bureta']
        assert resumen['insumos_nuevos'][0]['items'] == 2
        assert resumen['insumos_nuevos'][0]['stock_minimo'] == 2
        assert [i['codigo'] for i in resumen['items']] == ['A-1', 'A-2', 'B-1']
        assert [i['estado'] for i in resumen['items']] == ['Disponible', 'Disponible', 'Dañado']
        assert resumen['errores'] == resumen['saltadas'] == []
        assert resumen['filas_saltadas'] == 0
        assert not Insumo.objects.exists()
        assert not ItemInventario.objects.exists()

    def test_numero_de_fila_es_el_del_archivo(self, catalogos, laboratorio):
        # Encabezado en la línea 1, una línea en blanco: el error es de la línea 4.
        resumen = _validar('A-1,Pipeta,,,\n\n,Bureta,,,\n', laboratorio)
        assert _mensajes(resumen['errores']) == ['Fila 4: Código vacío']

    # ── Campos requeridos ──
    def test_nombre_vacio(self, catalogos, laboratorio):
        resumen = _validar('A-1,Pipeta,,,\nA-2,,,,\n', laboratorio)
        assert _mensajes(resumen['errores']) == ['Fila 3: Nombre vacío']
        assert len(resumen['items']) == 1

    def test_nombre_y_codigo_vacios_dan_dos_errores(self, catalogos, laboratorio):
        resumen = _validar('A-1,Pipeta,,,\n,,Brand,,\n', laboratorio)
        assert _mensajes(resumen['errores']) == ['Fila 3: Nombre vacío', 'Fila 3: Código vacío']
        assert resumen['filas_saltadas'] == 1

    def test_textos_demasiado_largos(self, catalogos, laboratorio):
        resumen = _validar(f'{"C" * 51},{"N" * 101},{"M" * 101},,\n', laboratorio)
        assert _mensajes(resumen['errores']) == [
            'Fila 2: Nombre demasiado largo (máx. 100 caracteres)',
            'Fila 2: Código demasiado largo (máx. 50 caracteres)',
            'Fila 2: Marca demasiado larga (máx. 100 caracteres)',
        ]

    # ── Duplicados ──
    def test_codigo_duplicado_en_el_archivo(self, catalogos, laboratorio):
        resumen = _validar('A-1,Pipeta,,,\nA-2,Pipeta,,,\na-1,Bureta,,,\n', laboratorio)
        assert _mensajes(resumen['saltadas']) == [
            'Fila 4: Código duplicado "a-1" (ya existe en el archivo, fila 2)',
        ]
        assert [i['codigo'] for i in resumen['items']] == ['A-1', 'A-2']
        # Bureta solo tenía la fila duplicada: no se crea.
        assert [i['nombre'] for i in resumen['insumos_nuevos']] == ['Pipeta']
        assert resumen['filas_saltadas'] == 1

    def test_codigo_que_ya_existe_en_el_sistema(self, catalogos, laboratorio):
        from inventario.models import EstadoItem, Insumo, ItemInventario

        insumo = Insumo.objects.create(nombre='Viejo', descripcion='x', laboratorio=laboratorio)
        item = ItemInventario.objects.create(codigo='A-1', insumo=insumo, estado=EstadoItem.objects.get(nombre='Disponible'))
        item.soft_delete()  # aunque esté eliminado, el código sigue ocupado

        resumen = _validar('A-1,Pipeta,,,\nA-2,Pipeta,,,\n', laboratorio)
        assert _mensajes(resumen['saltadas']) == ['Fila 2: Código "A-1" ya existe en el sistema']
        assert [i['codigo'] for i in resumen['items']] == ['A-2']

    def test_insumo_existente_se_reutiliza(self, catalogos, laboratorio):
        from inventario.models import Insumo

        Insumo.objects.create(nombre='Pipeta', descripcion='x', laboratorio=laboratorio, marca='Original')
        resumen = _validar('A-1,pipeta,Otra,,\n', laboratorio)
        assert resumen['insumos_nuevos'] == []
        assert resumen['insumos_existentes'][0]['nombre'] == 'Pipeta'
        assert resumen['insumos_existentes'][0]['items'] == 1

    def test_mismo_nombre_en_otro_laboratorio_es_otro_insumo(self, catalogos, laboratorio):
        from inventario.models import Insumo
        from laboratorio.models import Laboratorio

        otro = Laboratorio.objects.create(nombre='Física', ubicacion='B1')
        Insumo.objects.create(nombre='Pipeta', descripcion='x', laboratorio=otro)
        resumen = _validar('A-1,Pipeta,,,\n', laboratorio)
        assert [i['nombre'] for i in resumen['insumos_nuevos']] == ['Pipeta']

    # ── Laboratorio ──
    def test_columna_laboratorio(self, catalogos, laboratorio):
        from laboratorio.models import Laboratorio

        Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='B1')
        mapeo = {'Código': 'codigo', 'Nombre': 'nombre', 'Lab': 'laboratorio'}
        resumen = _validar(
            'A-1,Pipeta,laboratorio de fisica\nA-2,Pipeta,\nA-3,Pipeta,Lab Fantasma\n',
            laboratorio, mapeo=mapeo, cabecera='Código,Nombre,Lab\n',
        )
        assert [(i['codigo'], i['laboratorio']) for i in resumen['items']] == [
            ('A-1', 'Laboratorio de Física'),
            ('A-2', 'Laboratorio de Química'),  # vacía → el elegido al subir
        ]
        assert _mensajes(resumen['errores']) == ['Fila 4: Laboratorio no válido ("Lab Fantasma")']
        # Mismo nombre, laboratorios distintos → dos insumos.
        assert len(resumen['insumos_nuevos']) == 2

    def test_laboratorio_inactivo_no_es_valido(self, catalogos, laboratorio):
        from laboratorio.models import Laboratorio

        Laboratorio.objects.create(nombre='Cerrado', ubicacion='B9', activo=False)
        resumen = _validar('A-1,Pipeta,Cerrado\n', laboratorio,
                           mapeo={'Código': 'codigo', 'Nombre': 'nombre', 'Lab': 'laboratorio'},
                           cabecera='Código,Nombre,Lab\n')
        assert _mensajes(resumen['errores']) == ['Fila 2: Laboratorio no válido ("Cerrado")']

    # ── Estado ──
    @pytest.mark.parametrize('texto, esperado', [
        ('', 'Disponible'), ('disponible', 'Disponible'), ('Bueno', 'Disponible'),
        ('DAÑADO', 'Dañado'), ('malo', 'Dañado'), ('Extraviado', 'Perdido'),
    ])
    def test_estados_reconocidos(self, catalogos, laboratorio, texto, esperado):
        resumen = _validar(f'A-1,Pipeta,,{texto},\n', laboratorio)
        assert resumen['items'][0]['estado'] == esperado

    def test_estado_desconocido_es_error_y_no_se_crea(self, catalogos, laboratorio):
        from inventario.models import EstadoItem

        resumen = _validar('A-1,Pipeta,,Regular,\n', laboratorio)
        assert resumen['errores'][0]['mensaje'].startswith('Fila 2: Estado no válido ("Regular"). Usa: ')
        assert not EstadoItem.objects.filter(nombre='Regular').exists()

    def test_estado_prestado_no_se_importa(self, catalogos, laboratorio):
        resumen = _validar('A-1,Pipeta,,Prestado,\n', laboratorio)
        assert 'Prestado' in resumen['errores'][0]['mensaje']
        assert resumen['items'] == []

    # ── Stock mínimo ──
    @pytest.mark.parametrize('valor, esperado', [('', 0), ('0', 0), ('5', 5), ('5.0', 5)])
    def test_stock_minimo_valido(self, catalogos, laboratorio, valor, esperado):
        resumen = _validar(f'A-1,Pipeta,,,{valor}\n', laboratorio)
        assert resumen['insumos_nuevos'][0]['stock_minimo'] == esperado

    @pytest.mark.parametrize('valor', ['-1', 'tres', '2.5'])
    def test_stock_minimo_invalido(self, catalogos, laboratorio, valor):
        resumen = _validar(f'A-1,Pipeta,,,{valor}\n', laboratorio)
        assert _mensajes(resumen['errores']) == [
            f'Fila 2: Stock mínimo inválido ("{valor}"): debe ser un número entero mayor o igual a 0'
        ]

    # ── Cantidad ──
    def test_cantidad_genera_codigos(self, catalogos, laboratorio):
        resumen = _validar('MUL,Multímetro,3\n', laboratorio,
                           mapeo={'Código': 'codigo', 'Nombre': 'nombre', 'Cant': 'cantidad'},
                           cabecera='Código,Nombre,Cant\n')
        assert [i['codigo'] for i in resumen['items']] == ['MUL-1', 'MUL-2', 'MUL-3']

    def test_cantidad_invalida(self, catalogos, laboratorio):
        resumen = _validar('MUL,Multímetro,0\n', laboratorio,
                           mapeo={'Código': 'codigo', 'Nombre': 'nombre', 'Cant': 'cantidad'},
                           cabecera='Código,Nombre,Cant\n')
        assert 'Cantidad inválida' in resumen['errores'][0]['mensaje']


@pytest.mark.django_db
class TestGuardar:

    CUERPO = 'A-1,Pipeta,Brand,,2\nA-2,Pipeta,Brand,Dañado,\nB-1,Bureta,,,\nA-1,Duplicada,,,\n,SinCodigo,,,\n'

    def test_crea_insumos_items_y_movimientos(self, catalogos, laboratorio, usuario_admin):
        from inventario.models import Insumo, ItemInventario, MovimientoInventario

        resultado = _importador_csv(self.CUERPO).guardar(MAPEO, laboratorio, usuario_admin)

        pipeta = Insumo.objects.get(nombre='Pipeta', laboratorio=laboratorio)
        assert pipeta.marca == 'Brand'
        assert pipeta.stock_minimo == 2
        assert pipeta.descripcion == 'Importado desde inv.csv'
        assert Insumo.objects.count() == 2

        items = {i.codigo: i for i in ItemInventario.objects.select_related('estado', 'insumo')}
        assert set(items) == {'A-1', 'A-2', 'B-1'}
        assert items['A-2'].estado.nombre == 'Dañado'
        assert items['A-1'].laboratorio == laboratorio
        assert items['A-1'].updated_by == usuario_admin

        movimientos = MovimientoInventario.objects.select_related('tipo_movimiento')
        assert movimientos.count() == 3
        assert {m.tipo_movimiento.nombre for m in movimientos} == {'Registro inicial'}
        assert MovimientoInventario.objects.get(item_inventario=items['B-1']).observacion == \
            'Importado desde inv.csv (fila 4).'

        resumen = resultado.resumen()
        assert resumen['filas_saltadas'] == 2
        assert _mensajes(resumen['saltadas']) == ['Fila 5: Código duplicado "A-1" (ya existe en el archivo, fila 2)']
        assert _mensajes(resumen['errores']) == ['Fila 6: Código vacío']

    def test_agrega_items_a_insumo_existente_sin_modificarlo(self, catalogos, laboratorio, usuario_admin):
        from inventario.models import Insumo

        existente = Insumo.objects.create(nombre='Pipeta', descripcion='Original', laboratorio=laboratorio,
                                          marca='Original', stock_minimo=7)
        _importador_csv('A-1,Pipeta,Otra,,1\n').guardar(MAPEO, laboratorio, usuario_admin)

        existente.refresh_from_db()
        assert (existente.marca, existente.stock_minimo, existente.descripcion) == ('Original', 7, 'Original')
        assert existente.items.count() == 1
        assert Insumo.objects.count() == 1

    def test_revalida_contra_la_bd_actual(self, catalogos, laboratorio, usuario_admin):
        # Entre "validar" y "guardar" alguien creó A-1: se salta, no revienta.
        from inventario.models import EstadoItem, Insumo, ItemInventario

        importador = _importador_csv('A-1,Pipeta,,,\nA-2,Pipeta,,,\n')
        assert len(importador.validar(MAPEO, laboratorio).plan_items) == 2

        otro = Insumo.objects.create(nombre='Otro', descripcion='x', laboratorio=laboratorio)
        ItemInventario.objects.create(codigo='A-1', insumo=otro, estado=EstadoItem.objects.get(nombre='Disponible'))

        resultado = importador.guardar(MAPEO, laboratorio, usuario_admin)
        assert [i['codigo'] for i in resultado.plan_items] == ['A-2']

    def test_todo_o_nada(self, catalogos, laboratorio, usuario_admin, monkeypatch):
        from inventario.models import Insumo, ItemInventario, MovimientoInventario

        crear = MovimientoInventario.objects.create
        llamadas = []

        def falla_en_el_segundo(**kwargs):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError('boom')
            return crear(**kwargs)

        monkeypatch.setattr(MovimientoInventario.objects, 'create', falla_en_el_segundo)
        with pytest.raises(RuntimeError):
            _importador_csv('A-1,Pipeta,,,\nA-2,Pipeta,,,\n').guardar(MAPEO, laboratorio, usuario_admin)

        assert not Insumo.objects.exists()
        assert not ItemInventario.objects.exists()

    def test_desde_sesion_reproduce_el_archivo(self, catalogos, laboratorio, usuario_admin):
        import json

        original = _importador_csv('A-1,Pipeta,Brand,Bueno,1\n\nB-1,Bureta,,,\n')
        datos = json.loads(json.dumps(original.datos_sesion(laboratorio.id)))  # como la sesión
        assert datos['mapeo'] == MAPEO
        assert datos['numeros_fila'] == [2, 4]

        resultado = ImportadorInventario.desde_sesion(datos).guardar(datos['mapeo'], laboratorio, usuario_admin)
        assert [i['fila'] for i in resultado.plan_items] == [2, 4]
