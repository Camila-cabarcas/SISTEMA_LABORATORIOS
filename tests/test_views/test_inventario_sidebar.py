"""
Tests HTTP del inventario reorganizado con sidebar (templates/inventario/
layout_sidebar.html): secciones Insumos (/inventario/), Crear insumo
(/inventario/?seccion=crear), Items (/inventario/items/) y Movimientos
(/inventario/movimientos/), con las alertas de stock bajo siempre visibles.
"""
import pytest

from inventario.models import EstadoItem, Insumo, ItemInventario, MovimientoInventario, TipoMovimiento
from laboratorio.models import Laboratorio

pytestmark = pytest.mark.django_db

URL_INSUMOS = '/inventario/'
URL_CREAR = '/inventario/?seccion=crear'
URL_ITEMS = '/inventario/items/'
URL_MOVIMIENTOS = '/inventario/movimientos/'


def _insumo(nombre, laboratorio=None, **extra):
    extra.setdefault('descripcion', f'{nombre} de prueba')
    return Insumo.objects.create(nombre=nombre, laboratorio=laboratorio, **extra)


def _item(codigo, insumo, laboratorio=None, estado='Disponible'):
    return ItemInventario.objects.create(
        codigo=codigo, insumo=insumo, laboratorio=laboratorio,
        estado=EstadoItem.objects.get(nombre=estado),
    )


@pytest.fixture
def inventario(catalogos, laboratorio, usuario_admin):
    """Multímetro: 1 disponible / 1 prestado / 1 dañado / 1 perdido (+1
    eliminado), stock mínimo 2 → alerta. Cable: 3 disponibles, mínimo 1."""
    multimetro = _insumo('Multímetro', laboratorio, marca='Fluke', stock_minimo=2)
    _item('MUL-1', multimetro, laboratorio)
    _item('MUL-2', multimetro, laboratorio, 'Prestado')
    _item('MUL-3', multimetro, laboratorio, 'Dañado')
    _item('MUL-4', multimetro, laboratorio, 'Perdido')
    _item('MUL-BORRADO', multimetro, laboratorio).soft_delete()

    cable = _insumo('Cable', laboratorio, stock_minimo=1)
    for n in range(3):
        _item(f'CAB-{n}', cable, laboratorio)

    MovimientoInventario.objects.create(
        item_inventario=ItemInventario.objects.get(codigo='MUL-2'), usuario=usuario_admin,
        tipo_movimiento=TipoMovimiento.objects.get(nombre='Prestado'), observacion='Préstamo de prueba',
    )
    return {'multimetro': multimetro, 'cable': cable}


@pytest.fixture
def cliente_laboratorista(client, usuario_laboratorista):
    client.force_login(usuario_laboratorista)
    return client


# ── Sidebar ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('url', [URL_INSUMOS, URL_CREAR, URL_ITEMS, URL_MOVIMIENTOS])
def test_sidebar_con_las_cuatro_secciones_para_admin(cliente_autenticado, catalogos, url):
    contenido = cliente_autenticado.get(url).content.decode()

    assert 'id="secciones-inventario"' in contenido
    for href, texto in [('/inventario/', 'Insumos'), ('/inventario/?seccion=crear', 'Crear insumo'),
                        ('/inventario/items/', 'Items'), ('/inventario/movimientos/', 'Movimientos')]:
        assert f'href="{href}"' in contenido
        assert texto in contenido


@pytest.mark.parametrize('url, seccion', [
    (URL_INSUMOS, 'insumos'), (URL_CREAR, 'crear'), (URL_ITEMS, 'items'), (URL_MOVIMIENTOS, 'movimientos'),
])
def test_marca_la_seccion_activa(cliente_autenticado, catalogos, url, seccion):
    response = cliente_autenticado.get(url)

    assert response.context['seccion_activa'] == seccion
    assert response.content.decode().count('aria-current="page"') == 1


def test_contadores_del_sidebar(cliente_autenticado, inventario):
    ctx = cliente_autenticado.get(URL_INSUMOS).context

    # 7 ítems activos (el eliminado no cuenta), 2 insumos, 1 movimiento.
    assert (ctx['total_insumos'], ctx['total_items'], ctx['total_movimientos']) == (2, 7, 1)


@pytest.mark.parametrize('url', [URL_ITEMS, URL_MOVIMIENTOS])
def test_laboratorista_ve_items_y_movimientos_sin_secciones_de_admin(cliente_laboratorista, catalogos, url):
    response = cliente_laboratorista.get(url)

    assert response.status_code == 200
    contenido = response.content.decode()
    assert 'href="/inventario/items/"' in contenido
    assert 'href="/inventario/?seccion=crear"' not in contenido
    assert 'Crear insumo' not in contenido


@pytest.mark.parametrize('url', [URL_INSUMOS, URL_CREAR])
def test_laboratorista_no_accede_a_insumos_ni_crear(cliente_laboratorista, catalogos, url):
    response = cliente_laboratorista.get(url)

    assert response.status_code == 302
    assert 'sin' in response.url  # redirect('sin_permiso')


# ── Alertas de stock bajo ────────────────────────────────────────────────────

@pytest.mark.parametrize('url', [URL_INSUMOS, URL_CREAR, URL_ITEMS, URL_MOVIMIENTOS])
def test_alertas_siempre_visibles(cliente_autenticado, inventario, url):
    contenido = cliente_autenticado.get(url).content.decode()

    assert 'id="alertas-stock"' in contenido
    assert 'Insumos con stock bajo (1)' in contenido
    assert '<strong>Multímetro</strong>' in contenido


def test_alertas_calculo(cliente_autenticado, inventario):
    alertas = cliente_autenticado.get(URL_INSUMOS).context['alertas_stock']

    # Multímetro: 1 disponible <= mínimo 2 → alerta. Cable: 3 > 1 → no.
    assert [i.nombre for i in alertas] == ['Multímetro']
    assert alertas[0].cantidad_disponible_count == 1


def test_alertas_ignoran_stock_minimo_cero(cliente_autenticado, catalogos):
    _insumo('Sin mínimo', stock_minimo=0)  # 0 disponibles, pero sin mínimo configurado

    response = cliente_autenticado.get(URL_INSUMOS)

    assert response.context['alertas_stock'] == []
    assert 'id="alertas-stock"' not in response.content.decode()


def test_alertas_no_dependen_de_la_busqueda(cliente_autenticado, inventario):
    response = cliente_autenticado.get(URL_INSUMOS, {'busqueda': 'Cable'})

    assert [i.nombre for i in response.context['insumos']] == ['Cable']
    assert [i.nombre for i in response.context['alertas_stock']] == ['Multímetro']


# ── Sección Insumos ──────────────────────────────────────────────────────────

def test_insumos_conteos_por_estado(cliente_autenticado, inventario):
    insumos = {i.nombre: i for i in cliente_autenticado.get(URL_INSUMOS).context['insumos']}
    mul = insumos['Multímetro']

    assert (mul.total_count, mul.cantidad_disponible_count, mul.prestado_count,
            mul.danado_count, mul.perdido_count) == (4, 1, 1, 1, 1)


def test_insumos_no_muestra_formulario_de_crear(cliente_autenticado, inventario):
    contenido = cliente_autenticado.get(URL_INSUMOS).content.decode()

    assert 'action="/inventario/?seccion=crear"' not in contenido
    assert 'En Préstamo' in contenido


@pytest.mark.parametrize('busqueda, esperado', [('multí', 'Multímetro'), ('fluke', 'Multímetro'), ('cable de', 'Cable')])
def test_insumos_buscador_por_nombre_marca_y_descripcion(cliente_autenticado, inventario, busqueda, esperado):
    response = cliente_autenticado.get(URL_INSUMOS, {'busqueda': busqueda})

    assert [i.nombre for i in response.context['insumos']] == [esperado]


def test_insumos_filtro_por_laboratorio(cliente_autenticado, inventario):
    otro = Laboratorio.objects.create(nombre='Física', ubicacion='B1')
    _insumo('Osciloscopio', otro)

    response = cliente_autenticado.get(URL_INSUMOS, {'lab': otro.id})

    assert [i.nombre for i in response.context['insumos']] == ['Osciloscopio']


def test_insumos_filtro_solo_stock_bajo(cliente_autenticado, inventario):
    response = cliente_autenticado.get(URL_INSUMOS, {'stock_bajo': '1'})

    assert [i.nombre for i in response.context['insumos']] == ['Multímetro']


def test_insumos_paginacion(cliente_autenticado, catalogos):
    for n in range(20):
        _insumo(f'Insumo {n:02d}')

    pagina_2 = cliente_autenticado.get(URL_INSUMOS, {'page': 2, 'busqueda': 'Insumo'})

    assert pagina_2.context['insumos'].paginator.count == 20
    assert len(pagina_2.context['insumos']) == 5
    assert 'href="?busqueda=Insumo&page=1"' in pagina_2.content.decode()


# ── Sección Crear insumo ─────────────────────────────────────────────────────

def test_crear_muestra_formulario_sin_tabla(cliente_autenticado, catalogos):
    contenido = cliente_autenticado.get(URL_CREAR).content.decode()

    assert 'action="/inventario/?seccion=crear"' in contenido
    assert 'name="nombre"' in contenido
    assert 'Stock Total' not in contenido


def test_crear_insumo_valido_redirige_a_la_lista(cliente_autenticado, laboratorio):
    response = cliente_autenticado.post(URL_CREAR, {
        'nombre': 'Pipeta', 'laboratorio': laboratorio.id, 'descripcion': 'Pipeta de 10ml',
        'marca': '', 'stock_minimo': 2, 'estado': '',
    }, follow=True)

    assert response.redirect_chain == [('/inventario/', 302)]
    assert Insumo.objects.filter(nombre='Pipeta', laboratorio=laboratorio).exists()
    assert 'Insumo &quot;Pipeta&quot; creado.' in response.content.decode()


def test_crear_insumo_invalido_vuelve_al_formulario_con_errores(cliente_autenticado, catalogos):
    response = cliente_autenticado.post(URL_CREAR, {'nombre': '', 'descripcion': '', 'stock_minimo': 0})

    assert response.status_code == 200
    assert response.context['seccion_activa'] == 'crear'
    assert response.context['form'].errors
    assert 'invalid-feedback' in response.content.decode()
    assert not Insumo.objects.exists()


# ── Sección Items ────────────────────────────────────────────────────────────

def test_items_filtros(cliente_autenticado, inventario):
    prestado = EstadoItem.objects.get(nombre='Prestado')

    por_estado = cliente_autenticado.get(URL_ITEMS, {'estado': prestado.id})
    por_busqueda = cliente_autenticado.get(URL_ITEMS, {'busqueda': 'CAB'})
    por_insumo = cliente_autenticado.get(URL_ITEMS, {'insumo': inventario['multimetro'].id})

    assert [i.codigo for i in por_estado.context['items']] == ['MUL-2']
    assert [i.codigo for i in por_busqueda.context['items']] == ['CAB-0', 'CAB-1', 'CAB-2']
    assert [i.codigo for i in por_insumo.context['items']] == ['MUL-1', 'MUL-2', 'MUL-3', 'MUL-4']


def test_items_ultima_accion(cliente_autenticado, inventario):
    items = {i.codigo: i for i in cliente_autenticado.get(URL_ITEMS).context['items']}

    assert items['MUL-2'].ultimo_movimiento.tipo_movimiento.nombre == 'Prestado'
    assert items['MUL-1'].ultimo_movimiento is None


def test_items_paginacion(cliente_autenticado, catalogos):
    insumo = _insumo('Tornillo')
    for n in range(18):
        _item(f'T-{n:02d}', insumo)

    response = cliente_autenticado.get(URL_ITEMS, {'page': 2})

    assert len(response.context['items']) == 3
    assert response.context['items'].paginator.num_pages == 2


def test_items_formulario_registrar_plegado_salvo_con_errores(cliente_autenticado, catalogos):
    normal = cliente_autenticado.get(URL_ITEMS).content.decode()
    con_error = cliente_autenticado.post(URL_ITEMS, {'codigo': ''}).content.decode()

    assert 'class="collapse  mb-3" id="form-registrar-item"' in normal
    assert 'class="collapse show mb-3" id="form-registrar-item"' in con_error


# ── Sección Movimientos ──────────────────────────────────────────────────────

def test_movimientos_lista_y_paginacion(cliente_autenticado, inventario, usuario_admin):
    tipo = TipoMovimiento.objects.get(nombre='Devuelto')
    item = ItemInventario.objects.get(codigo='MUL-1')
    for _ in range(16):
        MovimientoInventario.objects.create(item_inventario=item, usuario=usuario_admin, tipo_movimiento=tipo)

    pagina_1 = cliente_autenticado.get(URL_MOVIMIENTOS)
    pagina_2 = cliente_autenticado.get(URL_MOVIMIENTOS, {'page': 2})

    assert pagina_1.context['movimientos'].paginator.count == 17
    assert len(pagina_1.context['movimientos']) == 15
    assert len(pagina_2.context['movimientos']) == 2
    assert 'id="form-registrar-movimiento"' in pagina_1.content.decode()


# ── Nombres visibles de los tipos de movimiento ──────────────────────────────

@pytest.mark.parametrize('nombre_bd, etiqueta', [
    ('Registro inicial', 'Creación'),
    ('Prestado', 'Préstamo'),
    ('Devuelto', 'Devolución'),
    ('Dañado', 'Reporte de daño'),
    ('Mantenimiento', 'Envío a mantenimiento'),
    ('Baja', 'Baja del inventario'),
    ('Tipo nuevo', 'Tipo nuevo'),  # sin etiqueta: se muestra tal cual
])
def test_etiqueta_de_tipo_movimiento(nombre_bd, etiqueta):
    assert TipoMovimiento.etiqueta_de(nombre_bd) == etiqueta
    assert TipoMovimiento(nombre=nombre_bd).etiqueta == etiqueta


def test_tabla_movimientos_muestra_etiquetas_y_detalles_del_cambio(cliente_autenticado, inventario, usuario_admin):
    item = ItemInventario.objects.get(codigo='MUL-1')
    MovimientoInventario.objects.create(
        item_inventario=item, usuario=usuario_admin,
        tipo_movimiento=TipoMovimiento.objects.get_or_create(nombre='Registro inicial')[0],
        observacion='Alta inicial.',
    )

    contenido = cliente_autenticado.get(URL_MOVIMIENTOS).content.decode()
    tabla = contenido.split('<table')[1]

    assert '<th>Detalles del cambio</th>' in tabla
    assert '<th>Observación</th>' not in tabla
    assert '<td>Creación</td>' in tabla
    assert '<td>Préstamo</td>' in tabla
    assert '<td>Registro inicial</td>' not in tabla
    assert '<td>Prestado</td>' not in tabla
    assert 'Alta inicial.' in tabla  # los detalles se muestran igual


def test_solo_cambia_la_presentacion_no_la_bd(cliente_autenticado, inventario):
    antes = list(TipoMovimiento.objects.order_by('id').values_list('nombre', flat=True))

    cliente_autenticado.get(URL_MOVIMIENTOS)
    cliente_autenticado.get(URL_ITEMS)

    assert list(TipoMovimiento.objects.order_by('id').values_list('nombre', flat=True)) == antes
    # El código que busca por nombre sigue funcionando.
    assert TipoMovimiento.objects.get(nombre='Prestado').etiqueta == 'Préstamo'


def test_filtro_de_movimientos_sigue_funcionando(cliente_autenticado, inventario):
    response = cliente_autenticado.get(URL_MOVIMIENTOS, {'insumo': inventario['multimetro'].id})

    assert [m.tipo_movimiento.nombre for m in response.context['movimientos']] == ['Prestado']


def test_items_ultima_accion_con_etiqueta(cliente_autenticado, inventario):
    contenido = cliente_autenticado.get(URL_ITEMS).content.decode()

    assert 'Préstamo' in contenido.split('<table')[1]


def test_historial_item_usa_etiquetas(cliente_autenticado, inventario):
    item = ItemInventario.objects.get(codigo='MUL-2')

    contenido = cliente_autenticado.get(f'/inventario/items/{item.id}/historial/').content.decode()

    assert '<th>Detalles del cambio</th>' in contenido
    assert '<td>Préstamo</td>' in contenido


def test_formulario_registrar_movimiento_usa_etiquetas(cliente_autenticado, inventario):
    form = cliente_autenticado.get(URL_MOVIMIENTOS).context['form']

    opciones = [label for _, label in form.fields['tipo_movimiento'].choices]
    assert 'Préstamo' in opciones and 'Devolución' in opciones
    assert 'Prestado' not in opciones
    assert form.fields['observacion'].label == 'Detalles del cambio'
