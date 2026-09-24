"""
Tests HTTP para laboratorio/views.py::detalle_laboratorio (/laboratorio/<id>/)
con sidebar de secciones (Personal / Cursos / Inventario) y enlaces a las
listas de reservas/préstamos filtradas por laboratorio, y para el endpoint
JSON del modal de ítems (modal_items_insumo).
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario, MovimientoInventario, TipoMovimiento
from laboratorio.models import Laboratorio, Laboratorista, LaboratoristaLab
from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import Curso, SolicitudReserva
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


def _url(laboratorio):
    return f'/laboratorio/{laboratorio.id}/'


def _get(cliente, laboratorio, **params):
    return cliente.get(_url(laboratorio), params)


def _insumo(nombre, laboratorio=None, **extra):
    return Insumo.objects.create(nombre=nombre, descripcion=f'{nombre} de prueba', laboratorio=laboratorio, **extra)


def _item(codigo, insumo, laboratorio, estado='Disponible'):
    return ItemInventario.objects.create(
        codigo=codigo, insumo=insumo, laboratorio=laboratorio,
        estado=EstadoItem.objects.get(nombre=estado),
    )


def _laboratorista(laboratorio, cedula, nombre='Pedro', tipo='laboratorista', activo=True):
    lab = Laboratorista.objects.create(
        nombre=nombre, apellido='Gil', cedula=cedula, correo=f'{cedula}@udea.edu.co', activo=activo,
    )
    LaboratoristaLab.objects.create(laboratorista=lab, laboratorio=laboratorio, tipo=tipo)
    return lab


@pytest.fixture
def otro_laboratorio(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 1')


@pytest.fixture
def inventario(catalogos, laboratorio, otro_laboratorio):
    """Multímetro: 2 disponibles, 1 prestado, 1 dañado, 1 perdido en `laboratorio`
    (+1 en otro lab y 1 eliminado, que NO deben contarse). Osciloscopio: 1 disponible."""
    multimetro = _insumo('Multímetro', laboratorio, marca='Fluke')
    _item('MUL-1', multimetro, laboratorio)
    _item('MUL-2', multimetro, laboratorio)
    _item('MUL-3', multimetro, laboratorio, 'Prestado')
    _item('MUL-4', multimetro, laboratorio, 'Dañado')
    _item('MUL-5', multimetro, laboratorio, 'Perdido')
    _item('MUL-OTRO', multimetro, otro_laboratorio)
    _item('MUL-BORRADO', multimetro, laboratorio).soft_delete()

    osciloscopio = _insumo('Osciloscopio')  # sin Insumo.laboratorio: llega por sus ítems
    _item('OSC-1', osciloscopio, laboratorio)

    _insumo('Balanza', otro_laboratorio)  # de otro lab: no debe aparecer
    return {'multimetro': multimetro, 'osciloscopio': osciloscopio}


# ── Sidebar y layout ──────────────────────────────────────────────────────────

def test_sidebar_se_renderiza_con_las_tres_secciones(cliente_autenticado, laboratorio):
    contenido = _get(cliente_autenticado, laboratorio).content.decode()

    assert 'id="secciones-lab"' in contenido
    for href, texto in [('?seccion=personal', 'Personal asignado'),
                        ('?seccion=cursos', 'Cursos asignados'),
                        ('?seccion=inventario', 'Inventario')]:
        assert f'href="{href}"' in contenido
        assert texto in contenido


def test_seccion_por_defecto_es_personal(cliente_autenticado, laboratorio):
    response = _get(cliente_autenticado, laboratorio)

    assert response.context['seccion_activa'] == 'personal'
    assert 'No hay laboratoristas asignados' in response.content.decode()


@pytest.mark.parametrize('seccion', ['personal', 'cursos', 'inventario'])
def test_boton_marca_la_seccion_activa(cliente_autenticado, laboratorio, seccion):
    response = _get(cliente_autenticado, laboratorio, seccion=seccion)

    assert response.context['seccion_activa'] == seccion
    contenido = response.content.decode()
    assert contenido.count('aria-current="page"') == 1
    enlace = contenido.split(f'href="?seccion={seccion}"')[1].split('>')[0]
    assert 'active' in enlace


def test_seccion_invalida_vuelve_a_personal(cliente_autenticado, laboratorio):
    response = _get(cliente_autenticado, laboratorio, seccion='xyz')

    assert response.context['seccion_activa'] == 'personal'


@pytest.mark.parametrize('seccion', ['personal', 'cursos', 'inventario'])
def test_informacion_general_siempre_visible(cliente_autenticado, laboratorio, seccion):
    laboratorio.programa = 'Ingeniería Química'
    laboratorio.save()

    contenido = _get(cliente_autenticado, laboratorio, seccion=seccion).content.decode()

    assert 'id="info-general"' in contenido
    assert 'Bloque 5 - Piso 2' in contenido
    assert 'Ingeniería Química' in contenido


def test_contadores_del_sidebar(cliente_autenticado, laboratorio, inventario, usuario_admin):
    _laboratorista(laboratorio, '100')
    _laboratorista(laboratorio, '200', activo=False)  # inactivo: no cuenta
    docente = Usuario.objects.create_user(
        username='doc', password='x', rol=Rol.objects.get(nombre='Docente'), codigo='DOC_1')
    Curso.objects.create(nombre='Química', codigo='QUIM-101', profesor=docente,
                         cantidad_estudiantes=20, laboratorio=laboratorio)

    ctx = _get(cliente_autenticado, laboratorio).context

    assert (ctx['total_personal'], ctx['total_cursos'], ctx['total_insumos']) == (1, 1, 2)


# ── Enlaces a Reservas / Préstamos ────────────────────────────────────────────

def test_enlaces_externos_llevan_filtro_de_lab_y_abren_en_nueva_pestana(cliente_autenticado, laboratorio):
    contenido = _get(cliente_autenticado, laboratorio).content.decode()

    for url in [f'/reservas/?lab={laboratorio.id}', f'/prestamos/?lab={laboratorio.id}']:
        assert f'href="{url}"' in contenido
        etiqueta = contenido.split(f'href="{url}"')[1].split('>')[0]
        assert 'target="_blank"' in etiqueta
        assert 'rel="noopener"' in etiqueta


def test_ya_no_hay_pestanas_de_reservas_ni_prestamos(cliente_autenticado, laboratorio):
    contenido = _get(cliente_autenticado, laboratorio).content.decode()

    assert 'tab-reservas' not in contenido
    assert 'tab-prestamos' not in contenido


def _reserva_en(laboratorio, nombre):
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now() + timedelta(days=1),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre=nombre, cedula='1',
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
    )
    return reserva


def test_lista_reservas_filtrada_por_lab(cliente_autenticado, catalogos, laboratorio, otro_laboratorio):
    propia = _reserva_en(laboratorio, 'Ana')
    _reserva_en(otro_laboratorio, 'Luis')

    response = cliente_autenticado.get('/reservas/', {'lab': laboratorio.id})

    assert [r.id for r in response.context['reservas']] == [propia.id]


def test_lista_prestamos_filtrada_por_lab(cliente_autenticado, usuario_admin, catalogos, laboratorio, otro_laboratorio):
    prestamos = {}
    for lab, nombre in [(laboratorio, 'Ana'), (otro_laboratorio, 'Luis')]:
        prestamos[lab.id] = Prestamo.objects.create(
            reserva=_reserva_en(lab, nombre), responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Activo'),
        )

    response = cliente_autenticado.get('/prestamos/', {'lab': laboratorio.id})

    assert [p.id for p in response.context['prestamos']] == [prestamos[laboratorio.id].id]


# ── Sección Personal ─────────────────────────────────────────────────────────

def test_seccion_personal_lista_laboratoristas_activos(cliente_autenticado, laboratorio):
    _laboratorista(laboratorio, '100', nombre='Pedro', tipo='encargado')
    _laboratorista(laboratorio, '200', nombre='Inactivo', activo=False)

    contenido = _get(cliente_autenticado, laboratorio, seccion='personal').content.decode()

    assert 'Pedro Gil' in contenido
    assert '100@udea.edu.co' in contenido
    assert 'Inactivo Gil' not in contenido
    assert '+ Asignar laboratorista' in contenido  # admin


def test_seccion_personal_no_muestra_cursos_ni_inventario(cliente_autenticado, laboratorio, inventario):
    contenido = _get(cliente_autenticado, laboratorio, seccion='personal').content.decode()

    assert 'Cursos asignados</h5>' not in contenido
    assert 'Multímetro' not in contenido
    assert 'id="modal-items"' not in contenido
    assert 'laboratorio_detalle.js' not in contenido


# ── Sección Cursos ───────────────────────────────────────────────────────────

def test_seccion_cursos_muestra_tabla(cliente_autenticado, catalogos, laboratorio):
    docente = Usuario.objects.create_user(
        username='doc', password='x', rol=Rol.objects.get(nombre='Docente'),
        codigo='DOC_1', first_name='Ana', last_name='Gómez')
    Curso.objects.create(nombre='Química General', codigo='QUIM-101', profesor=docente,
                         cantidad_estudiantes=30, laboratorio=laboratorio)

    contenido = _get(cliente_autenticado, laboratorio, seccion='cursos').content.decode()

    for texto in ['<td>QUIM-101</td>', '<td>Química General</td>', '<td>Ana Gómez</td>', '<td>30</td>']:
        assert texto in contenido
    assert 'No hay laboratoristas asignados' not in contenido


# ── Sección Inventario ───────────────────────────────────────────────────────

def test_seccion_inventario_agrupa_por_insumo_con_conteos_del_laboratorio(cliente_autenticado, laboratorio, inventario):
    response = _get(cliente_autenticado, laboratorio, seccion='inventario')

    insumos = {i.nombre: i for i in response.context['insumos_page']}
    assert set(insumos) == {'Multímetro', 'Osciloscopio'}
    mul = insumos['Multímetro']
    assert (mul.stock_total, mul.stock_disponible, mul.stock_prestado, mul.stock_danado, mul.stock_perdido) == (5, 2, 1, 1, 1)
    contenido = response.content.decode()
    assert 'id="modal-items"' in contenido
    assert 'js/laboratorio_detalle.js' in contenido


def test_otras_secciones_no_consultan_inventario_paginado(cliente_autenticado, laboratorio):
    assert 'insumos_page' not in _get(cliente_autenticado, laboratorio, seccion='cursos').context


def test_insumo_sin_items_del_laboratorio_aparece_en_cero(cliente_autenticado, laboratorio, catalogos):
    _insumo('Pipeta', laboratorio)

    [pipeta] = list(_get(cliente_autenticado, laboratorio, seccion='inventario').context['insumos_page'])

    assert pipeta.stock_total == 0


def test_buscador_de_insumos(cliente_autenticado, laboratorio, inventario):
    def nombres(busqueda):
        r = _get(cliente_autenticado, laboratorio, seccion='inventario', busqueda=busqueda)
        return [i.nombre for i in r.context['insumos_page']], r

    assert nombres('osci')[0] == ['Osciloscopio']
    assert nombres('fluke')[0] == ['Multímetro']  # por marca
    vacio, response = nombres('no-existe')
    assert vacio == []
    assert 'No hay insumos que coincidan con los filtros.' in response.content.decode()


@pytest.mark.parametrize('estado, esperados', [
    ('Disponible', ['Multímetro', 'Osciloscopio']),
    ('Prestado', ['Multímetro']),
    ('Dañado', ['Multímetro']),
    ('Perdido', ['Multímetro']),
])
def test_filtro_por_estado(cliente_autenticado, laboratorio, inventario, estado, esperados):
    response = _get(cliente_autenticado, laboratorio, seccion='inventario', estado=estado)

    assert [i.nombre for i in response.context['insumos_page']] == esperados
    assert response.context['filtro_estado'] == estado


def test_filtro_por_estado_mantiene_conteos_completos(cliente_autenticado, laboratorio, inventario):
    [mul] = list(_get(cliente_autenticado, laboratorio, seccion='inventario', estado='Prestado').context['insumos_page'])

    assert mul.stock_total == 5  # el filtro elige insumos, no recorta sus conteos


def test_filtro_por_estado_invalido_se_ignora(cliente_autenticado, laboratorio, inventario):
    response = _get(cliente_autenticado, laboratorio, seccion='inventario', estado='Mantenimiento')

    assert response.context['filtro_estado'] == ''
    assert len(response.context['insumos_page']) == 2


def test_formulario_de_inventario_conserva_la_seccion(cliente_autenticado, laboratorio):
    contenido = _get(cliente_autenticado, laboratorio, seccion='inventario').content.decode()

    assert '<input type="hidden" name="seccion" value="inventario">' in contenido


def test_paginacion_inventario_10_por_pagina(cliente_autenticado, laboratorio, catalogos):
    for n in range(23):
        _insumo(f'Insumo {n:02d}', laboratorio)

    pagina_1 = _get(cliente_autenticado, laboratorio, seccion='inventario')
    pagina_3 = _get(cliente_autenticado, laboratorio, seccion='inventario', page=3)

    assert len(pagina_1.context['insumos_page']) == 10
    assert pagina_1.context['insumos_page'].paginator.num_pages == 3
    assert [i.nombre for i in pagina_3.context['insumos_page']] == ['Insumo 20', 'Insumo 21', 'Insumo 22']
    assert 'href="?seccion=inventario&page=2"' in pagina_1.content.decode()


def test_paginacion_conserva_filtros(cliente_autenticado, laboratorio, catalogos):
    for n in range(12):
        _insumo(f'Cable {n:02d}', laboratorio)

    response = _get(cliente_autenticado, laboratorio, seccion='inventario', busqueda='cable', page=2)

    assert len(response.context['insumos_page']) == 2
    assert 'busqueda=cable' in response.context['qs_inventario']
    assert 'page=' not in response.context['qs_inventario']


def test_pagina_fuera_de_rango_muestra_la_ultima(cliente_autenticado, laboratorio, inventario):
    response = _get(cliente_autenticado, laboratorio, seccion='inventario', page=99)

    assert response.status_code == 200
    assert response.context['insumos_page'].number == 1


# ── Modal de ítems (JSON) ────────────────────────────────────────────────────

def test_fila_de_insumo_apunta_al_endpoint_del_modal(cliente_autenticado, laboratorio, inventario):
    contenido = _get(cliente_autenticado, laboratorio, seccion='inventario').content.decode()

    assert f'data-url="/laboratorio/{laboratorio.id}/insumos/{inventario["multimetro"].id}/items/"' in contenido


def test_modal_items_devuelve_items_del_insumo_en_el_laboratorio(cliente_autenticado, laboratorio, inventario):
    insumo = inventario['multimetro']

    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/insumos/{insumo.id}/items/')

    assert response.status_code == 200
    data = response.json()
    assert data['insumo'] == {'id': insumo.id, 'nombre': 'Multímetro'}
    assert [(i['codigo'], i['estado']) for i in data['items']] == [
        ('MUL-1', 'Disponible'), ('MUL-2', 'Disponible'), ('MUL-3', 'Prestado'),
        ('MUL-4', 'Dañado'), ('MUL-5', 'Perdido'),
    ]  # sin MUL-OTRO (otro lab) ni MUL-BORRADO (soft-delete)


def test_modal_items_incluye_ultima_accion(cliente_autenticado, usuario_admin, laboratorio, inventario):
    item = ItemInventario.objects.get(codigo='MUL-3')
    MovimientoInventario.objects.create(
        item_inventario=item, usuario=usuario_admin,
        tipo_movimiento=TipoMovimiento.objects.get(nombre='Prestado'),
    )

    data = cliente_autenticado.get(
        f'/laboratorio/{laboratorio.id}/insumos/{inventario["multimetro"].id}/items/').json()

    por_codigo = {i['codigo']: i for i in data['items']}
    assert por_codigo['MUL-3']['ultima_accion'] == 'Prestado'
    assert por_codigo['MUL-3']['ultima_fecha']
    assert por_codigo['MUL-1']['ultima_accion'] == ''
    assert por_codigo['MUL-1']['ultima_fecha'] is None


def test_modal_items_insumo_inexistente_404(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/insumos/999999/items/')

    assert response.status_code == 404


def test_modal_items_laboratorista_de_otro_lab_403(client, catalogos, laboratorio, otro_laboratorio, inventario):
    ajeno = Usuario.objects.create_user(
        username='lab_ajeno', password='clave12345',
        rol=Rol.objects.get(nombre='Laboratorio'), codigo='LAB_AJENO_001',
    )
    otro_laboratorio.encargados.add(ajeno)
    client.force_login(ajeno)

    response = client.get(f'/laboratorio/{laboratorio.id}/insumos/{inventario["multimetro"].id}/items/')

    assert response.status_code == 403


def test_modal_items_requiere_login(client, laboratorio, inventario):
    response = client.get(f'/laboratorio/{laboratorio.id}/insumos/{inventario["multimetro"].id}/items/')

    assert response.status_code == 302
