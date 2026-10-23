"""
importador.py — inventario
Lectura de archivos de inventario (Excel, CSV o PDF) para importarlos.

Flujo (ver las vistas Importar/Mapear/Validar/Confirmar en inventario.views):
1. preview(): parsea el archivo, encuentra la fila de encabezados, detecta qué
   columna corresponde a cada campo del sistema y devuelve las primeras filas.
   datos_sesion() guarda la tabla completa en la sesión (no en la BD).
2. El usuario corrige el mapeo columna → campo (validar_mapeo()).
3. validar(): simula la importación sin escribir nada — insumos e ítems que
   se crearían, filas saltadas por duplicadas y errores por fila.
4. guardar(): repite la validación contra la BD actual y crea todo en una
   sola transacción.

Reglas de importación: cada fila es un ítem físico (ItemInventario) — el
Código es su código único y el Nombre el del Insumo al que pertenece. Filas
con el mismo nombre (y laboratorio) comparten Insumo; si el Insumo ya existe
en ese laboratorio se reutiliza tal cual (no se modifican sus datos).

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
    ('laboratorio', 'Laboratorio', ['laboratorio', 'lab', 'sede']),
]
ETIQUETAS_CAMPO = {campo: etiqueta for campo, etiqueta, _ in CAMPOS}
CAMPOS_OBLIGATORIOS = ('nombre', 'codigo')


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
    # La tabla completa viaja en la sesión entre pasos.
    MAX_FILAS = 5000

    def __init__(self, archivo):
        """`archivo`: UploadedFile de Django (o cualquier objeto con .name y .read())."""
        self.archivo = archivo
        self.nombre = os.path.basename(getattr(archivo, 'name', '') or '')
        self.extension = os.path.splitext(self.nombre)[1].lower()
        self.advertencias = []
        self._tabla = None
        # Número de fila en el archivo original de cada fila de _tabla
        # (Excel/CSV: la fila de la hoja; PDF: la fila de la tabla extraída).
        self._numeros_fila = []

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
            if len(self._tabla) > self.MAX_FILAS:
                raise ImportacionError(
                    f'El archivo tiene {len(self._tabla)} filas; el máximo por importación es '
                    f'{self.MAX_FILAS}. Divídelo en varios archivos.'
                )
        return self._tabla

    def preview(self, n=FILAS_PREVIEW):
        tabla = self.leer()
        mapeo = detectar_columnas(list(tabla.columns))
        columnas = []
        for col in tabla.columns:
            campo = mapeo.get(col)
            columnas.append({
                'nombre': col,
                'campo': campo,
                'etiqueta': ETIQUETAS_CAMPO[campo] if campo else None,
            })
        faltantes = [ETIQUETAS_CAMPO[c] for c in ('nombre',) if c not in mapeo.values()]
        aviso = ('No se encontró una columna para: ' + ', '.join(faltantes)
                 + '. Revisa que el archivo tenga encabezados.')
        # desde_sesion() trae los avisos ya guardados: no repetirlo.
        if faltantes and aviso not in self.advertencias:
            self.advertencias.append(aviso)
        return {
            'archivo': self.nombre,
            'formato': self.extension.lstrip('.').upper(),
            'columnas': columnas,
            'mapeo': mapeo,
            'filas': tabla.head(n).values.tolist(),
            'numeros_fila': self._numeros_fila[:n],
            # (número de fila en el archivo, celdas) — para las plantillas.
            'filas_numeradas': list(zip(self._numeros_fila[:n], tabla.head(n).values.tolist())),
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
                # False: así el índice de cada fila es su línea en el archivo
                # (las vacías se descartan después, en _armar_tabla).
                skip_blank_lines=False, on_bad_lines='skip',
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
        # Sin reset_index: el índice original da el número de fila del archivo.
        df = df.dropna(how='all').dropna(axis=1, how='all')
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

        datos = datos.dropna(how='all').dropna(axis=1, how='all').fillna('')
        if datos.empty:
            raise ImportacionError('El archivo solo tiene encabezados, sin filas de datos.')
        self._numeros_fila = [int(i) + 1 for i in datos.index]
        return datos.reset_index(drop=True)

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

    # ── Sesión (entre pasos) ────────────────────────────────────────
    def datos_sesion(self, laboratorio_id):
        """Todo lo que los pasos siguientes necesitan, en tipos que la
        sesión puede serializar (JSON)."""
        tabla = self.leer()
        return {
            'archivo': self.nombre,
            'formato': self.extension.lstrip('.').upper(),
            'laboratorio_id': laboratorio_id,
            'columnas': list(tabla.columns),
            'filas': tabla.values.tolist(),
            'numeros_fila': self._numeros_fila,
            'mapeo': detectar_columnas(list(tabla.columns)),
            'advertencias': list(self.advertencias),
        }

    @classmethod
    def desde_sesion(cls, datos):
        importador = cls.__new__(cls)
        importador.archivo = None
        importador.nombre = datos['archivo']
        importador.extension = '.' + datos.get('formato', '').lower()
        importador.advertencias = list(datos.get('advertencias', []))
        importador._tabla = pd.DataFrame(datos['filas'], columns=datos['columnas'], dtype=object)
        importador._numeros_fila = list(datos['numeros_fila'])
        return importador

    # ── Mapeo ───────────────────────────────────────────────────────
    @staticmethod
    def validar_mapeo(mapeo, columnas):
        """Lista de errores (vacía = OK) de un mapeo {columna: campo}."""
        errores = []
        usados = {}
        for columna, campo in mapeo.items():
            if columna not in columnas:
                errores.append(f'La columna "{columna}" no existe en el archivo.')
            elif campo not in ETIQUETAS_CAMPO:
                errores.append(f'Campo desconocido para la columna "{columna}".')
            elif campo in usados:
                errores.append(
                    f'El campo {ETIQUETAS_CAMPO[campo]} está asignado a dos columnas: '
                    f'"{usados[campo]}" y "{columna}".'
                )
            else:
                usados[campo] = columna
        for campo in CAMPOS_OBLIGATORIOS:
            if campo not in usados:
                errores.append(f'Asigna una columna al campo obligatorio {ETIQUETAS_CAMPO[campo]}.')
        return errores

    # ── Validación (simulación) y guardado ──────────────────────────
    def validar(self, mapeo, laboratorio):
        """Simula la importación con `mapeo` ({columna: campo}) hacia
        `laboratorio` (el elegido al subir; una columna Laboratorio lo
        reemplaza fila por fila). No escribe nada."""
        return _Validacion(self, mapeo, laboratorio).ejecutar()

    def guardar(self, mapeo, laboratorio, usuario):
        """Valida de nuevo contra la BD actual (pudo cambiar desde el paso
        de validación) y crea insumos, ítems y su movimiento "Registro
        inicial" en una sola transacción: o se importa todo lo válido o
        nada. Devuelve el ResultadoImportacion."""
        from django.db import transaction

        from inventario.models import EstadoInsumo, Insumo, ItemInventario, MovimientoInventario, TipoMovimiento

        with transaction.atomic():
            resultado = self.validar(mapeo, laboratorio)
            estado_insumo = EstadoInsumo.objects.filter(nombre='Activo').first()
            tipo_registro, _ = TipoMovimiento.objects.get_or_create(nombre='Registro inicial')

            insumos = {}
            for clave, plan in resultado.plan_insumos.items():
                if plan['existente'] is not None:
                    insumos[clave] = plan['existente']
                    continue
                insumo = Insumo(
                    nombre=plan['nombre'],
                    laboratorio=plan['laboratorio'],
                    descripcion=plan['descripcion'] or f'Importado desde {self.nombre}',
                    marca=plan['marca'],
                    stock_minimo=plan['stock_minimo'],
                    estado=estado_insumo,
                )
                insumo.full_clean()
                insumo.save()
                insumos[clave] = insumo

            for plan in resultado.plan_items:
                item = ItemInventario.objects.create(
                    codigo=plan['codigo'],
                    insumo=insumos[plan['insumo']],
                    estado=plan['estado'],
                    laboratorio=plan['laboratorio'],
                    updated_by=usuario,
                )
                MovimientoInventario.objects.create(
                    item_inventario=item,
                    usuario=usuario,
                    tipo_movimiento=tipo_registro,
                    observacion=f'Importado desde {self.nombre} (fila {plan["fila"]}).',
                )
        return resultado


# ── Validación ────────────────────────────────────────────────────────────

# Texto normalizado del archivo → nombre del EstadoItem. Los estados nunca se
# crean desde la importación: el sistema busca nombres exactos
# (.get(nombre='Disponible'), etc.) y un estado inventado no tendría efecto.
# 'Prestado' no se acepta: un ítem prestado sin Prestamo quedaría colgado.
SINONIMOS_ESTADO = {
    'disponible': 'Disponible', 'bueno': 'Disponible', 'buen estado': 'Disponible',
    'bien': 'Disponible', 'nuevo': 'Disponible', 'operativo': 'Disponible',
    'funcional': 'Disponible', 'ok': 'Disponible', 'activo': 'Disponible',
    'danado': 'Dañado', 'malo': 'Dañado', 'mal estado': 'Dañado', 'averiado': 'Dañado',
    'defectuoso': 'Dañado', 'roto': 'Dañado',
    'mantenimiento': 'Mantenimiento', 'en mantenimiento': 'Mantenimiento', 'en reparacion': 'Mantenimiento',
    'baja': 'Baja', 'de baja': 'Baja', 'dado de baja': 'Baja',
    'perdido': 'Perdido', 'extraviado': 'Perdido',
}
ESTADO_POR_DEFECTO = 'Disponible'
MAX_CANTIDAD_POR_FILA = 200


class ResultadoImportacion:
    """Lo que hará (validar) o hizo (guardar) una importación.

    `plan_insumos` / `plan_items` son de uso interno de guardar() (tienen
    objetos de modelo); `resumen()` es la versión serializable que se
    muestra y se guarda en la sesión."""

    def __init__(self, archivo, total_filas):
        self.archivo = archivo
        self.total_filas = total_filas
        self.plan_insumos = {}   # (laboratorio_id, nombre casefold) → dict
        self.plan_items = []
        self.saltadas = []       # {'fila', 'mensaje'} — duplicados
        self.errores = []        # {'fila', 'mensaje'}
        self._filas_ok = set()

    def _aviso(self, lista, fila, mensaje):
        lista.append({'fila': fila, 'mensaje': f'Fila {fila}: {mensaje}'})

    @property
    def filas_saltadas(self):
        """Filas que no generan ningún ítem (por error o porque todos sus
        códigos estaban duplicados)."""
        con_problemas = {a['fila'] for a in self.saltadas + self.errores}
        return len(con_problemas - self._filas_ok)

    def resumen(self):
        items_por_insumo = {}
        for item in self.plan_items:
            items_por_insumo[item['insumo']] = items_por_insumo.get(item['insumo'], 0) + 1

        insumos_nuevos, insumos_existentes = [], []
        for clave, plan in self.plan_insumos.items():
            fila = {
                'nombre': plan['nombre'],
                'laboratorio': plan['laboratorio'].nombre,
                'marca': plan['marca'],
                'stock_minimo': plan['stock_minimo'],
                'items': items_por_insumo.get(clave, 0),
            }
            (insumos_existentes if plan['existente'] is not None else insumos_nuevos).append(fila)

        return {
            'archivo': self.archivo,
            'total_filas': self.total_filas,
            'insumos_nuevos': insumos_nuevos,
            'insumos_existentes': insumos_existentes,
            'items': [
                {'fila': i['fila'], 'codigo': i['codigo'], 'insumo': self.plan_insumos[i['insumo']]['nombre'],
                 'laboratorio': i['laboratorio'].nombre, 'estado': i['estado'].nombre}
                for i in self.plan_items
            ],
            'saltadas': self.saltadas,
            'errores': self.errores,
            'filas_saltadas': self.filas_saltadas,
        }


class _Validacion:

    def __init__(self, importador, mapeo, laboratorio):
        from inventario.models import EstadoItem, Insumo, ItemInventario
        from laboratorio.models import Laboratorio

        self.tabla = importador.leer()
        self.numeros_fila = importador._numeros_fila
        self.mapeo = mapeo
        self.laboratorio = laboratorio
        self.resultado = ResultadoImportacion(importador.nombre, len(self.tabla))

        self.labs_por_nombre = {normalizar(lab.nombre): lab for lab in Laboratorio.objects.filter(activo=True)}
        self.estados = {e.nombre: e for e in EstadoItem.objects.all()}
        # Códigos ya usados en el sistema, incluidos ítems eliminados
        # (soft-delete): la columna es unique=True igual.
        self.codigos_bd = {c.casefold() for c in ItemInventario.objects.values_list('codigo', flat=True)}
        self.insumos_bd = {
            (i.laboratorio_id, i.nombre.casefold()): i
            for i in Insumo.objects.filter(laboratorio__isnull=False)
        }
        self.codigos_archivo = {}  # código casefold → fila donde apareció primero

    def ejecutar(self):
        columna_de = {campo: columna for columna, campo in self.mapeo.items()}
        for posicion, fila in enumerate(self.tabla.to_dict('records')):
            numero = self.numeros_fila[posicion] if posicion < len(self.numeros_fila) else posicion + 1
            valores = {campo: str(fila.get(col) or '').strip() for campo, col in columna_de.items()}
            self._fila(numero, valores)
        return self.resultado

    def _fila(self, numero, v):
        r = self.resultado
        errores = []

        nombre = v.get('nombre', '')
        if not nombre:
            errores.append('Nombre vacío')
        elif len(nombre) > 100:
            errores.append('Nombre demasiado largo (máx. 100 caracteres)')

        codigo = v.get('codigo', '')
        if not codigo:
            errores.append('Código vacío')
        elif len(codigo) > 50:
            errores.append('Código demasiado largo (máx. 50 caracteres)')

        # laboratorio / stock_minimo / cantidad nunca quedan en None: el valor
        # leído va a una variable aparte y solo se asigna si es válido (si no,
        # se registra el error y la fila sale abajo, en `if errores`).
        laboratorio = self.laboratorio
        if v.get('laboratorio'):
            lab_fila = self.labs_por_nombre.get(normalizar(v['laboratorio']))
            if lab_fila is None:
                errores.append(f'Laboratorio no válido ("{v["laboratorio"]}")')
            else:
                laboratorio = lab_fila

        stock_minimo = 0
        if v.get('stock_minimo'):
            stock_leido = _entero(v['stock_minimo'])
            if stock_leido is None or stock_leido < 0:
                errores.append(
                    f'Stock mínimo inválido ("{v["stock_minimo"]}"): debe ser un número entero mayor o igual a 0'
                )
            else:
                stock_minimo = stock_leido

        estado = self._estado(v.get('estado', ''), errores)

        cantidad = 1
        if v.get('cantidad'):
            cantidad_leida = _entero(v['cantidad'])
            if cantidad_leida is None or not 1 <= cantidad_leida <= MAX_CANTIDAD_POR_FILA:
                errores.append(
                    f'Cantidad inválida ("{v["cantidad"]}"): debe ser un entero entre 1 y {MAX_CANTIDAD_POR_FILA}'
                )
            else:
                cantidad = cantidad_leida

        marca = v.get('marca', '')
        if len(marca) > 100:
            errores.append('Marca demasiado larga (máx. 100 caracteres)')

        if errores:
            for e in errores:
                r._aviso(r.errores, numero, e)
            return

        # Cantidad > 1 con un solo código: COD-1, COD-2, ...
        codigos = [codigo] if cantidad == 1 else [f'{codigo}-{i}' for i in range(1, cantidad + 1)]
        nuevos = []
        for c in codigos:
            clave = c.casefold()
            if clave in self.codigos_archivo:
                r._aviso(r.saltadas, numero,
                         f'Código duplicado "{c}" (ya existe en el archivo, fila {self.codigos_archivo[clave]})')
            elif clave in self.codigos_bd:
                r._aviso(r.saltadas, numero, f'Código "{c}" ya existe en el sistema')
            else:
                self.codigos_archivo[clave] = numero
                nuevos.append(c)
        if not nuevos:
            return

        clave_insumo = (laboratorio.id, nombre.casefold())
        if clave_insumo not in r.plan_insumos:
            existente = self.insumos_bd.get(clave_insumo)
            if existente is not None:
                # Se reutiliza tal cual: el reporte muestra sus datos, no los del archivo.
                nombre, marca, stock_minimo = existente.nombre, existente.marca, existente.stock_minimo
            r.plan_insumos[clave_insumo] = {
                'nombre': nombre,
                'laboratorio': laboratorio,
                'descripcion': v.get('descripcion', ''),
                'marca': marca,
                'stock_minimo': stock_minimo,
                'existente': existente,
            }
        for c in nuevos:
            r.plan_items.append({
                'fila': numero, 'codigo': c, 'insumo': clave_insumo,
                'laboratorio': laboratorio, 'estado': estado,
            })
        r._filas_ok.add(numero)

    def _estado(self, texto, errores):
        if texto and normalizar(texto) == 'prestado':
            errores.append('No se puede importar un ítem como Prestado (no tiene un préstamo asociado)')
            return None
        nombre = SINONIMOS_ESTADO.get(normalizar(texto)) if texto else ESTADO_POR_DEFECTO
        if nombre is None or nombre not in self.estados:
            validos = ', '.join(sorted(set(SINONIMOS_ESTADO.values()) & set(self.estados)))
            errores.append(f'Estado no válido ("{texto}"). Usa: {validos}')
            return None
        return self.estados[nombre]


def _entero(texto: str) -> int | None:
    """'5', '5.0', ' 5 ' → 5; cualquier otra cosa → None."""
    texto = texto.strip().replace(' ', '')
    if re.fullmatch(r'-?\d+(\.0+)?', texto):
        return int(float(texto))
    return None
