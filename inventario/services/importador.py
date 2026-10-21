"""
importador.py — inventario
Lectura de archivos de inventario (Excel, CSV o PDF) para importarlos.

Fase 1 — solo lectura: ImportadorInventario.preview() parsea el archivo,
encuentra la fila de encabezados, detecta qué columna corresponde a cada
campo del sistema (nombre, código, cantidad...) y devuelve las primeras
filas para mostrarlas. No escribe nada en la base de datos.

Formatos:
- .xlsx / .xlsm → pandas + openpyxl (primera hoja con datos).
- .csv         → pandas; separador (, ; tab |) y codificación (UTF-8 o
                 Latin-1, la típica de Excel en español) detectados solos.
- .pdf         → pdfplumber; une las tablas de todas las páginas. Un PDF
                 escaneado (imagen, sin texto) no tiene tablas que leer.
- .xls (Excel 97-2003) no se soporta: necesitaría xlrd; se pide guardarlo
  como .xlsx.
"""
import csv
import io
import os
import re
import unicodedata

import pandas as pd


class ImportacionError(Exception):
    """Archivo que no se puede leer. El mensaje se muestra tal cual al usuario."""


# ── Detección de columnas ─────────────────────────────────────────────────
# (campo, etiqueta, sinónimos ya normalizados). El orden importa: un campo
# se asigna a una sola columna, y 'stock minimo' tiene que ganarle a 'stock'
# (cantidad) antes de que cantidad lo reclame. 'Ítem' no es sinónimo de
# nombre a propósito: en los inventarios suele ser el número de fila.
CAMPOS = [
    ('stock_minimo', 'Stock mínimo', ['stock minimo', 'minimo', 'cantidad minima', 'stock min']),
    ('codigo', 'Código', ['codigo', 'cod', 'placa', 'serial', 'serie', 'no serie', 'numero de serie',
                          'numero inventario', 'no inventario', 'codigo inventario', 'referencia', 'ref']),
    ('nombre', 'Nombre', ['nombre', 'insumo', 'equipo', 'elemento', 'articulo', 'material',
                          'nombre del equipo', 'nombre insumo', 'producto']),
    ('descripcion', 'Descripción', ['descripcion', 'detalle', 'especificaciones', 'caracteristicas']),
    ('marca', 'Marca', ['marca', 'fabricante']),
    ('cantidad', 'Cantidad', ['cantidad', 'cant', 'unidades', 'existencias', 'stock']),
    ('estado', 'Estado', ['estado', 'condicion', 'estado fisico']),
]
ETIQUETAS_CAMPO = {campo: etiqueta for campo, etiqueta, _ in CAMPOS}


def normalizar(texto):
    """'  Código de Inventario: ' → 'codigo de inventario'."""
    texto = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode()
    texto = re.sub(r'[^a-z0-9]+', ' ', texto.lower())
    return texto.strip()


def detectar_columnas(columnas):
    """{nombre de columna original: campo del sistema} para las columnas
    reconocidas. Primero coincidencias exactas con un sinónimo; después,
    columnas que contienen un sinónimo como palabra ('Nombre del insumo'
    → nombre). Cada campo y cada columna se usan una sola vez."""
    normalizadas = {col: normalizar(col) for col in columnas}
    mapeo = {}

    def libres():
        return [c for c in columnas if c not in mapeo]

    for exacto in (True, False):
        for campo, _, sinonimos in CAMPOS:
            if campo in mapeo.values():
                continue
            for col in libres():
                norm = normalizadas[col]
                if exacto:
                    ok = norm in sinonimos
                else:
                    ok = any(re.search(rf'\b{re.escape(s)}\b', norm) for s in sinonimos)
                if ok:
                    mapeo[col] = campo
                    break
    return mapeo


# ── Lector ────────────────────────────────────────────────────────────────

class ImportadorInventario:

    EXTENSIONES = ('.xlsx', '.xlsm', '.csv', '.pdf')
    TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB
    MAX_PAGINAS_PDF = 50
    FILAS_PREVIEW = 10
    # Hasta qué fila buscar el encabezado (los Excel de inventario suelen
    # traer título, logo o fecha arriba de la tabla).
    FILAS_BUSQUEDA_ENCABEZADO = 15

    def __init__(self, archivo):
        """`archivo`: UploadedFile de Django (o cualquier objeto con .name y .read())."""
        self.archivo = archivo
        self.nombre = os.path.basename(getattr(archivo, 'name', '') or '')
        self.extension = os.path.splitext(self.nombre)[1].lower()
        self.advertencias = []
        self._tabla = None

    # ── API pública ──────────────────────────────────────────────────
    @classmethod
    def validar_archivo(cls, archivo):
        """Chequeos baratos (extensión, tamaño, vacío) antes de parsear."""
        nombre = getattr(archivo, 'name', '') or ''
        extension = os.path.splitext(nombre)[1].lower()
        if extension == '.xls':
            raise ImportacionError(
                'Los archivos .xls (Excel 97-2003) no son compatibles. '
                'Ábrelo en Excel y guárdalo como .xlsx.'
            )
        if extension not in cls.EXTENSIONES:
            raise ImportacionError(
                f'Formato no soportado ("{extension or "sin extensión"}"). '
                'Usa Excel (.xlsx), CSV (.csv) o PDF (.pdf).'
            )
        tamano = getattr(archivo, 'size', None)
        if tamano is not None:
            if tamano == 0:
                raise ImportacionError('El archivo está vacío.')
            if tamano > cls.TAMANO_MAXIMO:
                raise ImportacionError(
                    f'El archivo pesa {tamano / 1024 / 1024:.1f} MB; el máximo es '
                    f'{cls.TAMANO_MAXIMO // 1024 // 1024} MB.'
                )

    def leer(self):
        """DataFrame (todo texto) con encabezados ya detectados y filas
        vacías descartadas. Lanza ImportacionError si no se puede leer."""
        if self._tabla is None:
            self.validar_archivo(self.archivo)
            contenido = self.archivo.read()
            if not contenido:
                raise ImportacionError('El archivo está vacío.')

            lector = {
                '.csv': self._leer_csv,
                '.pdf': self._leer_pdf,
            }.get(self.extension, self._leer_excel)
            crudo = lector(contenido)
            self._tabla = self._armar_tabla(crudo)
        return self._tabla

    def preview(self, n=FILAS_PREVIEW):
        tabla = self.leer()
        mapeo = detectar_columnas(list(tabla.columns))
        columnas = [
            {'nombre': col, 'campo': mapeo.get(col), 'etiqueta': ETIQUETAS_CAMPO.get(mapeo.get(col))}
            for col in tabla.columns
        ]
        faltantes = [ETIQUETAS_CAMPO[c] for c in ('nombre',) if c not in mapeo.values()]
        if faltantes:
            self.advertencias.append(
                'No se encontró una columna para: ' + ', '.join(faltantes)
                + '. Revisa que el archivo tenga encabezados.'
            )
        return {
            'archivo': self.nombre,
            'formato': self.extension.lstrip('.').upper(),
            'columnas': columnas,
            'mapeo': mapeo,
            'filas': tabla.head(n).values.tolist(),
            'total_filas': len(tabla),
            'advertencias': self.advertencias,
        }

    # ── Lectores por formato → DataFrame crudo (sin encabezado) ─────
    def _leer_excel(self, contenido):
        try:
            hojas = pd.read_excel(
                io.BytesIO(contenido), sheet_name=None, header=None, dtype=str, engine='openpyxl',
            )
        except Exception:
            raise ImportacionError(
                'No se pudo leer el archivo de Excel. Verifica que no esté dañado ni protegido con contraseña.'
            )
        con_datos = [(nombre, df) for nombre, df in hojas.items() if not df.dropna(how='all').empty]
        if not con_datos:
            raise ImportacionError('El archivo de Excel no tiene datos.')
        if len(con_datos) > 1:
            self.advertencias.append(
                f'El archivo tiene {len(con_datos)} hojas con datos; se usa solo la primera '
                f'("{con_datos[0][0]}").'
            )
        return con_datos[0][1]

    def _leer_csv(self, contenido):
        for codificacion in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue

        try:
            separador = csv.Sniffer().sniff(texto[:4096], delimiters=',;\t|').delimiter
        except csv.Error:
            separador = ','

        try:
            return pd.read_csv(
                io.StringIO(texto), sep=separador, header=None, dtype=str,
                skip_blank_lines=True, on_bad_lines='skip',
            )
        except pd.errors.EmptyDataError:
            raise ImportacionError('El archivo CSV no tiene datos.')
        except Exception:
            raise ImportacionError('No se pudo leer el archivo CSV. Verifica su formato.')

    def _leer_pdf(self, contenido):
        import pdfplumber

        filas = []
        try:
            with pdfplumber.open(io.BytesIO(contenido)) as pdf:
                paginas = pdf.pages
                if len(paginas) > self.MAX_PAGINAS_PDF:
                    self.advertencias.append(
                        f'El PDF tiene {len(paginas)} páginas; solo se leen las primeras '
                        f'{self.MAX_PAGINAS_PDF}.'
                    )
                for pagina in paginas[:self.MAX_PAGINAS_PDF]:
                    for tabla in pagina.extract_tables():
                        filas.extend(tabla)
        except Exception:
            raise ImportacionError(
                'No se pudo leer el PDF. Verifica que no esté dañado ni protegido con contraseña.'
            )

        if not filas:
            raise ImportacionError(
                'No se encontraron tablas en el PDF. Si es un documento escaneado (imagen), '
                'expórtalo a Excel o CSV.'
            )
        ancho = max(len(f) for f in filas)
        return pd.DataFrame([list(f) + [None] * (ancho - len(f)) for f in filas], dtype=str)

    # ── Limpieza común ──────────────────────────────────────────────
    def _armar_tabla(self, crudo):
        # astype(object) + where: con dtype str, pandas (3.x) vuelve a
        # convertir el None de _limpiar_celda en NaN — y NaN != NaN rompe
        # la comparación de encabezados repetidos y los nombres de columna.
        df = crudo.astype(object).map(self._limpiar_celda)
        df = df.astype(object).where(df.notna(), None)
        df = df.dropna(how='all').dropna(axis=1, how='all').reset_index(drop=True)
        if df.empty:
            raise ImportacionError('El archivo no tiene datos.')

        fila_encabezado = self._buscar_encabezado(df)
        if fila_encabezado > 0:
            self.advertencias.append(
                f'Se omitieron {fila_encabezado} fila(s) antes de los encabezados.'
            )
        encabezados = self._nombres_unicos(df.iloc[fila_encabezado].tolist())
        datos = df.iloc[fila_encabezado + 1:].copy()
        datos.columns = encabezados

        # PDF de varias páginas: cada página repite el encabezado de la tabla.
        repetidos = datos.apply(lambda fila: fila.tolist() == df.iloc[fila_encabezado].tolist(), axis=1)
        datos = datos[~repetidos] if len(datos) else datos

        datos = datos.dropna(how='all').dropna(axis=1, how='all').fillna('').reset_index(drop=True)
        if datos.empty:
            raise ImportacionError('El archivo solo tiene encabezados, sin filas de datos.')
        return datos

    @staticmethod
    def _limpiar_celda(valor):
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return None
        texto = re.sub(r'\s+', ' ', str(valor)).strip()
        if texto.lower() in ('', 'nan', 'none'):
            return None
        # "5.0" que pandas/Excel generan para enteros.
        if re.fullmatch(r'-?\d+\.0', texto):
            texto = texto[:-2]
        return texto

    def _buscar_encabezado(self, df):
        """Índice de la fila que más parece encabezado entre las primeras
        FILAS_BUSQUEDA_ENCABEZADO: la que más columnas reconocidas tiene;
        si ninguna reconoce nada, la primera con al menos la mitad de las
        celdas llenas y en texto."""
        candidatas = range(min(self.FILAS_BUSQUEDA_ENCABEZADO, len(df)))
        mejor, mejor_puntaje = None, 0
        for i in candidatas:
            celdas = [c for c in df.iloc[i].tolist() if c is not None]
            puntaje = len(detectar_columnas(celdas))
            if puntaje > mejor_puntaje:
                mejor, mejor_puntaje = i, puntaje
        if mejor is not None:
            return mejor

        ancho = df.shape[1]
        for i in candidatas:
            celdas = [c for c in df.iloc[i].tolist() if c is not None]
            if len(celdas) >= max(2, ancho / 2) and not any(re.fullmatch(r'[\d.,-]+', c) for c in celdas):
                return i
        return 0

    @staticmethod
    def _nombres_unicos(nombres):
        vistos = {}
        resultado = []
        for i, nombre in enumerate(nombres, start=1):
            nombre = nombre or f'Columna {i}'
            if nombre in vistos:
                vistos[nombre] += 1
                nombre = f'{nombre} ({vistos[nombre]})'
            else:
                vistos[nombre] = 1
            resultado.append(nombre)
        return resultado
