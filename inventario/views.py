"""
views.py — inventario
Vistas para gestionar insumos, ítems físicos, movimientos de inventario e historial por ítem.
"""
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.views import View
from users.decorators import rol_requerido, requiere_contrasena_admin

logger_acceso_admin = logging.getLogger('acceso_admin')
logger_importacion = logging.getLogger(__name__)

from .models import (
    Insumo,
    ItemInventario,
    MovimientoInventario
)

from .forms import (
    ImportarArchivoForm,
    InsumoForm,
    ItemInventarioForm,
    MovimientoInventarioForm
)


# ── Layout con sidebar ────────────────────────────────────────────────────────
# Las cuatro secciones (Insumos, Crear insumo, Items, Movimientos) comparten
# templates/inventario/layout_sidebar.html, pero cada una sigue siendo su
# propia vista/URL con sus propios permisos: Insumos y Crear son solo
# Administrador; Items y Movimientos también los usa el rol Laboratorio.

POR_PAGINA = 15

_ACTIVO = Q(items__deleted_at__isnull=True)


def _insumos_con_stock():
    """Insumos con los conteos por estado anotados (una sola consulta, en
    vez de 4 métodos stock_*() por fila). Solo ítems activos (no
    soft-deleted), igual que Insumo.stock_*()."""
    return Insumo.objects.select_related('estado', 'laboratorio').annotate(
        total_count=Count('items', filter=_ACTIVO),
        cantidad_disponible_count=Count('items', filter=_ACTIVO & Q(items__estado__nombre='Disponible')),
        prestado_count=Count('items', filter=_ACTIVO & Q(items__estado__nombre='Prestado')),
        danado_count=Count('items', filter=_ACTIVO & Q(items__estado__nombre='Dañado')),
        perdido_count=Count('items', filter=_ACTIVO & Q(items__estado__nombre='Perdido')),
    )


def obtener_alertas_stock():
    """Insumos con stock mínimo configurado y disponibles <= mínimo.
    Independiente de búsquedas/filtros: la alerta es siempre global."""
    return [
        insumo for insumo in _insumos_con_stock().filter(stock_minimo__gt=0).order_by('nombre')
        if insumo.cantidad_disponible_count <= insumo.stock_minimo
    ]


def _contexto_sidebar(request, seccion):
    from users.helpers import es_administrador
    return {
        'seccion_activa': seccion,
        'es_admin_inventario': es_administrador(request.user),
        'alertas_stock': obtener_alertas_stock(),
        'total_insumos': Insumo.objects.count(),
        'total_items': ItemInventario.activos.count(),
        'total_movimientos': MovimientoInventario.objects.count(),
    }


def _querystring_sin_pagina(request):
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def _paginar(request, queryset):
    return Paginator(queryset, POR_PAGINA).get_page(request.GET.get('page'))


@rol_requerido('Administrador')
def inicio(request):
    """Sección Insumos (lista) y, con ?seccion=crear, Crear insumo."""
    seccion = 'crear' if request.GET.get('seccion') == 'crear' or request.method == 'POST' else 'insumos'

    if request.method == 'POST':
        form = InsumoForm(request.POST)
        if form.is_valid():
            insumo = form.save()
            messages.success(request, f'Insumo "{insumo.nombre}" creado.')
            return redirect('/inventario/')
    else:
        form = InsumoForm()

    contexto = _contexto_sidebar(request, seccion)
    contexto['form'] = form

    if seccion == 'insumos':
        from laboratorio.models import Laboratorio

        busqueda = request.GET.get('busqueda', '').strip()
        lab_id = request.GET.get('lab', '')
        solo_stock_bajo = request.GET.get('stock_bajo') == '1'

        insumos = _insumos_con_stock().order_by('nombre', 'id')
        if busqueda:
            insumos = insumos.filter(
                Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda) | Q(marca__icontains=busqueda)
            )
        if lab_id.isdigit():
            insumos = insumos.filter(laboratorio_id=lab_id)
        if solo_stock_bajo:
            insumos = insumos.filter(id__in=[i.id for i in contexto['alertas_stock']])

        contexto.update({
            'insumos': _paginar(request, insumos),
            'busqueda': busqueda,
            'lab_id': lab_id,
            'solo_stock_bajo': solo_stock_bajo,
            'laboratorios': Laboratorio.objects.order_by('nombre'),
            'qs': _querystring_sin_pagina(request),
        })

    return render(request, 'inventario/inicio.html', contexto)


@rol_requerido('Administrador')
@requiere_contrasena_admin(
    titulo_accion='Eliminar',
    get_contexto=lambda r, *a, **kw: f"Insumo - {Insumo.objects.get(id=kw['id']).nombre}",
)
def eliminar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)
    nombre = insumo.nombre
    insumo.delete()
    messages.success(request, f'Insumo "{nombre}" eliminado.')
    return redirect('/inventario/')


@rol_requerido('Administrador')
def editar_insumo(request, id):

    insumo = Insumo.objects.get(id=id)

    if request.method == 'POST':

        form = InsumoForm(request.POST, instance=insumo)

        if form.is_valid():
            form.save()
            return redirect('/inventario/')

    else:
        form = InsumoForm(instance=insumo)

    return render(
        request,
        'inventario/editar.html',
        {
            'form': form
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def items_inventario(request):

    if request.method == 'POST':

        form = ItemInventarioForm(request.POST)

        if form.is_valid():

            item = form.save(commit=False)
            item.updated_by = request.user
            item.save()

            return redirect('/inventario/items/')

    else:
        form = ItemInventarioForm()

    from inventario.models import EstadoItem
    from laboratorio.models import Laboratorio

    items = ItemInventario.activos.select_related(
        'insumo', 'estado', 'laboratorio',
    ).order_by('insumo__nombre', 'codigo')

    insumo_id = request.GET.get('insumo', '')
    estado_id = request.GET.get('estado', '')
    lab_id = request.GET.get('lab', '')
    busqueda = request.GET.get('busqueda', '').strip()
    if insumo_id.isdigit():
        items = items.filter(insumo_id=insumo_id)
    if estado_id.isdigit():
        items = items.filter(estado_id=estado_id)
    if lab_id.isdigit():
        items = items.filter(laboratorio_id=lab_id)
    if busqueda:
        items = items.filter(Q(codigo__icontains=busqueda) | Q(insumo__nombre__icontains=busqueda))

    pagina = _paginar(request, items)

    # SQLite no soporta distinct(field_names) (eso es solo Postgres), así
    # que la última acción por ítem se arma a mano: se recorre ordenado por
    # fecha descendente y se queda solo la primera fila vista por ítem. Se
    # cuelga como atributo de cada item (en vez de un dict aparte) para que
    # el template la lea directo con item.ultimo_movimiento. Solo para los
    # ítems de la página visible.
    ultimos_por_item = {}
    movimientos_recientes = MovimientoInventario.objects.filter(
        item_inventario__in=[item.id for item in pagina],
    ).select_related('tipo_movimiento').order_by('-fecha')
    for m in movimientos_recientes:
        ultimos_por_item.setdefault(m.item_inventario_id, m)
    for item in pagina:
        item.ultimo_movimiento = ultimos_por_item.get(item.id)

    contexto = _contexto_sidebar(request, 'items')
    contexto.update({
        'form': form,
        'items': pagina,
        'insumos': Insumo.objects.order_by('nombre'),
        'estados': EstadoItem.objects.order_by('nombre'),
        'laboratorios': Laboratorio.objects.order_by('nombre'),
        'insumo_id': insumo_id,
        'estado_id': estado_id,
        'lab_id': lab_id,
        'busqueda': busqueda,
        'qs': _querystring_sin_pagina(request),
    })
    return render(request, 'inventario/items.html', contexto)


@rol_requerido('Administrador', 'Laboratorio')
def movimientos_inventario(request):

    if request.method == 'POST':

        form = MovimientoInventarioForm(request.POST)

        if form.is_valid():

            movimiento = form.save(commit=False)
            movimiento.usuario = request.user
            movimiento.save()

            return redirect('/inventario/movimientos/')

    else:
        form = MovimientoInventarioForm()

    movimientos = MovimientoInventario.objects.select_related(
        'item_inventario__insumo', 'item_inventario__laboratorio', 'usuario', 'tipo_movimiento',
    ).order_by('-fecha')

    insumo_id   = request.GET.get('insumo', '')
    lab_id      = request.GET.get('lab', '')
    usuario_id  = request.GET.get('usuario', '')
    fecha_inicio = request.GET.get('fecha_inicio', '')
    fecha_fin    = request.GET.get('fecha_fin', '')

    if insumo_id:
        movimientos = movimientos.filter(item_inventario__insumo_id=insumo_id)
    if lab_id:
        movimientos = movimientos.filter(item_inventario__laboratorio_id=lab_id)
    if usuario_id:
        movimientos = movimientos.filter(usuario_id=usuario_id)
    if fecha_inicio:
        movimientos = movimientos.filter(fecha__date__gte=fecha_inicio)
    if fecha_fin:
        movimientos = movimientos.filter(fecha__date__lte=fecha_fin)

    from laboratorio.models import Laboratorio
    from users.models import Usuario

    contexto = _contexto_sidebar(request, 'movimientos')
    contexto.update({
        'form': form,
        'movimientos': _paginar(request, movimientos),
        'insumos': Insumo.objects.order_by('nombre'),
        'laboratorios': Laboratorio.objects.order_by('nombre'),
        'usuarios': Usuario.objects.filter(
            id__in=MovimientoInventario.objects.values_list('usuario_id', flat=True).distinct()
        ).order_by('username'),
        'insumo_id': insumo_id,
        'lab_id': lab_id,
        'usuario_id': usuario_id,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'qs': _querystring_sin_pagina(request),
    })
    return render(request, 'inventario/movimientos.html', contexto)


@rol_requerido('Administrador', 'Laboratorio')
def editar_item(request, id):

    item = ItemInventario.objects.get(id=id)

    if request.method == 'POST':

        form = ItemInventarioForm(request.POST, instance=item)

        if form.is_valid():

            item = form.save(commit=False)
            item.updated_by = request.user
            item.save()

            return redirect('/inventario/items/')

    else:
        form = ItemInventarioForm(instance=item)

    return render(
        request,
        'inventario/editar_item.html',
        {
            'form': form,
            'item': item
        }
    )


@rol_requerido('Administrador', 'Laboratorio')
def historial_item(request, id):
    # .objects (no .activos): un ítem eliminado (soft-delete) debe seguir
    # siendo consultable acá — ese es justamente el punto de no borrarlo de
    # verdad.
    item = get_object_or_404(ItemInventario, id=id)

    prestamos = item.prestamoitem_set.select_related(
        'prestamo', 'prestamo__estado'
    ).prefetch_related('inspecciones').order_by('-id')

    movimientos = MovimientoInventario.objects.filter(
        item_inventario=item
    ).select_related('tipo_movimiento').order_by('-fecha')

    return render(
        request,
        'inventario/historial_item.html',
        {
            'item': item,
            'prestamos': prestamos,
            'movimientos': movimientos,
        }
    )


# requiere_contrasena_admin ya exige estar autenticado y tener rol
# Administrador/Laboratorio (ver users/decorators.py) — no hace falta
# apilar rol_requerido encima, a diferencia de eliminar_insumo, que ya
# traía su propio rol_requerido de antes y se dejó tal cual.
@requiere_contrasena_admin(
    titulo_accion='Eliminar',
    get_contexto=lambda r, *a, **kw: f"Item - {ItemInventario.objects.get(id=kw['id']).codigo}",
)
def eliminar_item_inventario(request, id):
    """
    Soft-delete de un ItemInventario: marca deleted_at en vez de borrar la
    fila. PrestamoItem/MovimientoInventario/InspeccionItem cuelgan de este
    ítem con on_delete=CASCADE — un delete() de verdad se llevaría por
    delante el historial de préstamos e inspecciones de este ítem
    específico, no solo el ítem. El soft-delete evita eso: el ítem
    desaparece de las listas y de la selección para nuevos préstamos, pero
    su historial sigue accesible en historial_item.
    """
    item = get_object_or_404(ItemInventario, id=id)

    if item.is_deleted():
        messages.info(request, f'Item "{item.codigo}" ya estaba eliminado.')
        return redirect('/inventario/items/')

    codigo = item.codigo
    insumo = item.insumo.nombre

    item.soft_delete()

    logger_acceso_admin.info(
        'Admin %s marcó como eliminado el item %s (%s)', request.user.username, codigo, insumo,
    )

    messages.success(request, f'Item "{codigo}" eliminado correctamente.')
    return redirect('/inventario/items/')

# ── Importar inventario desde archivo ─────────────────────────────────────────

# Cuatro pasos, cada uno su propia URL: Importar (subir + preview) →
# Mapear (columna → campo) → Validar (simulación) → Confirmar (guardar +
# reporte). La tabla parseada viaja en la sesión entre pasos, nunca en la BD.
#
# services.importador se importa dentro de los métodos: carga pandas, y
# este módulo lo importan otras apps (p. ej. el dashboard) que no deberían
# pagar ese costo al arrancar.

SESION_IMPORTACION = 'importacion_inventario'
SESION_RESULTADO = 'importacion_inventario_resultado'
URL_IMPORTAR = '/inventario/importar/'


PASOS_IMPORTACION = [(1, 'Subir archivo'), (2, 'Mapear columnas'), (3, 'Validar'), (4, 'Guardar')]


def _contexto_importar(request, paso):
    contexto = _contexto_sidebar(request, 'importar')
    contexto.update({'paso': paso, 'pasos_importacion': PASOS_IMPORTACION})
    return contexto


def _datos_importacion(request):
    """(datos de sesión, Laboratorio) del archivo en curso, o (None, None)
    si no hay importación en curso o su laboratorio ya no está activo."""
    from laboratorio.models import Laboratorio

    datos = request.session.get(SESION_IMPORTACION)
    if not datos:
        messages.warning(request, 'Primero sube un archivo para importar.')
        return None, None
    laboratorio = Laboratorio.objects.filter(id=datos.get('laboratorio_id'), activo=True).first()
    if laboratorio is None:
        request.session.pop(SESION_IMPORTACION, None)
        messages.error(request, 'El laboratorio elegido ya no es válido. Vuelve a subir el archivo.')
        return None, None
    return datos, laboratorio


@method_decorator(rol_requerido('Administrador'), name='dispatch')
class ImportarInventarioView(View):
    """Paso 1: sube un Excel/CSV/PDF + laboratorio destino y muestra la
    vista previa (primeras filas + columnas detectadas). Guarda la tabla en
    la sesión para los pasos siguientes; no escribe en la BD."""

    template_name = 'inventario/importar.html'

    def _render(self, request, form, preview=None, error=None):
        from .services.importador import ETIQUETAS_CAMPO

        contexto = _contexto_importar(request, 1)
        contexto.update({
            'form': form,
            'preview': preview,
            'error': error,
            'campos_sistema': ETIQUETAS_CAMPO,
        })
        return render(request, self.template_name, contexto)

    def get(self, request):
        return self._render(request, ImportarArchivoForm())

    def post(self, request):
        from .services.importador import ImportacionError, ImportadorInventario

        form = ImportarArchivoForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render(request, form)

        importador = ImportadorInventario(form.cleaned_data['archivo'])
        try:
            preview = importador.preview()
        except ImportacionError as e:
            return self._render(request, form, error=str(e))
        except Exception:
            logger_importacion.exception(
                'ImportarInventarioView | error inesperado leyendo %s', importador.nombre,
            )
            return self._render(
                request, form,
                error='No se pudo procesar el archivo. Verifica que sea un Excel, CSV o PDF válido.',
            )

        laboratorio = form.cleaned_data['laboratorio']
        preview['laboratorio'] = laboratorio
        request.session[SESION_IMPORTACION] = importador.datos_sesion(laboratorio.id)
        request.session.pop(SESION_RESULTADO, None)
        return self._render(request, form, preview=preview)


@method_decorator(rol_requerido('Administrador'), name='dispatch')
class MapearView(View):
    """Paso 2: un desplegable por columna para asignarle un campo del
    sistema (o ignorarla). Parte del mapeo detectado automáticamente."""

    template_name = 'inventario/mapear.html'

    def _render(self, request, datos, laboratorio, mapeo, errores=()):
        from .services.importador import CAMPOS_OBLIGATORIOS, ETIQUETAS_CAMPO, ImportadorInventario

        n = ImportadorInventario.FILAS_PREVIEW
        contexto = _contexto_importar(request, 2)
        contexto.update({
            'datos': datos,
            'laboratorio': laboratorio,
            'columnas': [
                {'indice': i, 'nombre': col, 'campo': mapeo.get(col, '')}
                for i, col in enumerate(datos['columnas'])
            ],
            'filas': list(zip(datos['numeros_fila'][:n], datos['filas'][:n])),
            'total_filas': len(datos['filas']),
            'campos_sistema': ETIQUETAS_CAMPO,
            'obligatorios': [ETIQUETAS_CAMPO[c] for c in CAMPOS_OBLIGATORIOS],
            'errores': errores,
        })
        return render(request, self.template_name, contexto)

    def get(self, request):
        datos, laboratorio = _datos_importacion(request)
        if datos is None:
            return redirect(URL_IMPORTAR)
        return self._render(request, datos, laboratorio, datos.get('mapeo', {}))

    def post(self, request):
        from .services.importador import ImportadorInventario

        datos, laboratorio = _datos_importacion(request)
        if datos is None:
            return redirect(URL_IMPORTAR)

        mapeo = {}
        for i, columna in enumerate(datos['columnas']):
            campo = request.POST.get(f'col_{i}', '').strip()
            if campo:
                mapeo[columna] = campo

        errores = ImportadorInventario.validar_mapeo(mapeo, datos['columnas'])
        if errores:
            return self._render(request, datos, laboratorio, mapeo, errores)

        datos['mapeo'] = mapeo
        datos['mapeo_confirmado'] = True
        request.session[SESION_IMPORTACION] = datos
        return redirect(f'{URL_IMPORTAR}validar/')


@method_decorator(rol_requerido('Administrador'), name='dispatch')
class ValidarView(View):
    """Paso 3: simula la importación (sin escribir) y muestra qué se
    creará, qué se salta por duplicado y los errores por fila."""

    template_name = 'inventario/validar.html'

    def get(self, request):
        from .services.importador import ImportadorInventario

        datos, laboratorio = _datos_importacion(request)
        if datos is None:
            return redirect(URL_IMPORTAR)
        if not datos.get('mapeo_confirmado'):
            return redirect(f'{URL_IMPORTAR}mapear/')

        resultado = ImportadorInventario.desde_sesion(datos).validar(datos['mapeo'], laboratorio)
        contexto = _contexto_importar(request, 3)
        contexto.update({
            'datos': datos,
            'laboratorio': laboratorio,
            'resumen': resultado.resumen(),
        })
        return render(request, self.template_name, contexto)


@method_decorator(rol_requerido('Administrador'), name='dispatch')
class ConfirmarView(View):
    """Paso 4: POST guarda en la BD (revalidando) y redirige a GET, que
    muestra el reporte final — así recargar la página no reimporta."""

    template_name = 'inventario/confirmar.html'

    def get(self, request):
        resumen = request.session.get(SESION_RESULTADO)
        if not resumen:
            return redirect(URL_IMPORTAR)
        contexto = _contexto_importar(request, 4)
        contexto['resumen'] = resumen
        return render(request, self.template_name, contexto)

    def post(self, request):
        from .services.importador import ImportadorInventario

        datos, laboratorio = _datos_importacion(request)
        if datos is None:
            return redirect(URL_IMPORTAR)
        if not datos.get('mapeo_confirmado'):
            return redirect(f'{URL_IMPORTAR}mapear/')

        importador = ImportadorInventario.desde_sesion(datos)
        try:
            resultado = importador.guardar(datos['mapeo'], laboratorio, request.user)
        except Exception:
            logger_importacion.exception(
                'ConfirmarView | error guardando la importación de %s', importador.nombre,
            )
            messages.error(
                request,
                'No se pudo guardar la importación; no se guardó ningún registro. '
                'Revisa la validación e inténtalo de nuevo.',
            )
            return redirect(f'{URL_IMPORTAR}validar/')

        resumen = resultado.resumen()
        resumen['laboratorio'] = laboratorio.nombre
        request.session.pop(SESION_IMPORTACION, None)
        request.session[SESION_RESULTADO] = resumen
        logger_importacion.info(
            'Importación de inventario | usuario=%s | archivo=%s | insumos_nuevos=%s | items=%s | filas_saltadas=%s',
            request.user.username, importador.nombre, len(resumen['insumos_nuevos']),
            len(resumen['items']), resumen['filas_saltadas'],
        )
        return redirect(f'{URL_IMPORTAR}confirmar/')
