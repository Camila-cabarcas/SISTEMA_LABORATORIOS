"""
Tests HTTP para laboratorio/views.py::detalle_laboratorio (/laboratorio/<id>/)
reorganizado en pestañas Inventario / Reservas / Préstamos, y para el
endpoint JSON del modal de ítems (modal_items_insumo).
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario, MovimientoInventario, TipoMovimiento
from laboratorio.models import Laboratorio
from prestamos.models import EstadoPrestamo, Prestamo, PrestamoItem
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


def _url(laboratorio):
    return f'/laboratorio/{laboratorio.id}/'


def _insumo(nombre, laboratorio=None, **extra):
    return Insumo.objects.create(nombre=nombre, descripcion=f'{nombre} de prueba', laboratorio=laboratorio, **extra)


def _item(codigo, insumo, laboratorio, estado='Disponible'):
    return ItemInventario.objects.create(
        codigo=codigo, insumo=insumo, laboratorio=laboratorio,
        estado=EstadoItem.objects.get(nombre=estado),
    )


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


# ── Estructura / pestañas ─────────────────────────────────────────────────────

def test_renderiza_secciones_fijas_y_tres_pestanas(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(_url(laboratorio))

    assert response.status_code == 200
    contenido = response.content.decode()
    for texto in ['Información general', 'Personal asignado', 'Cursos asignados',
                  'id="tab-inventario"', 'id="tab-reservas"', 'id="tab-prestamos"',
                  'id="modal-items"', 'js/laboratorio_detalle.js']:
        assert texto in contenido
    assert 'Ítems en este laboratorio' not in contenido


def test_pestana_inventario_activa_por_defecto(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(_url(laboratorio))

    assert response.context['tab'] == 'inventario'
    assert 'id="tab-inventario" class="tab-pane fade show active"' in response.content.decode()


@pytest.mark.parametrize('tab', ['reservas', 'prestamos'])
def test_parametro_tab_activa_esa_pestana(cliente_autenticado, laboratorio, tab):
    response = cliente_autenticado.get(_url(laboratorio), {'tab': tab})

    contenido = response.content.decode()
    assert f'id="tab-{tab}" class="tab-pane fade show active"' in contenido
    assert 'id="tab-inventario" class="tab-pane fade show active"' not in contenido


def test_tab_invalido_vuelve_a_inventario(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'xyz'})

    assert response.context['tab'] == 'inventario'


# ── Pestaña Inventario ───────────────────────────────────────────────────────

def test_inventario_agrupa_por_insumo_con_conteos_del_laboratorio(cliente_autenticado, laboratorio, inventario):
    response = cliente_autenticado.get(_url(laboratorio))

    insumos = {i.nombre: i for i in response.context['insumos_page']}
    assert set(insumos) == {'Multímetro', 'Osciloscopio'}
    mul = insumos['Multímetro']
    assert (mul.stock_total, mul.stock_disponible, mul.stock_prestado, mul.stock_danado, mul.stock_perdido) == (5, 2, 1, 1, 1)
    assert insumos['Osciloscopio'].stock_total == 1
    assert 'MUL-1' not in response.content.decode()  # la tabla ya no lista ítems sueltos


def test_insumo_sin_items_del_laboratorio_aparece_en_cero(cliente_autenticado, laboratorio, catalogos):
    _insumo('Pipeta', laboratorio)

    response = cliente_autenticado.get(_url(laboratorio))

    [pipeta] = list(response.context['insumos_page'])
    assert pipeta.stock_total == 0


def test_buscador_de_insumos(cliente_autenticado, laboratorio, inventario):
    response = cliente_autenticado.get(_url(laboratorio), {'busqueda': 'osci'})
    assert [i.nombre for i in response.context['insumos_page']] == ['Osciloscopio']

    response = cliente_autenticado.get(_url(laboratorio), {'busqueda': 'fluke'})  # por marca
    assert [i.nombre for i in response.context['insumos_page']] == ['Multímetro']

    response = cliente_autenticado.get(_url(laboratorio), {'busqueda': 'no-existe'})
    assert list(response.context['insumos_page']) == []
    assert 'No hay insumos que coincidan con los filtros.' in response.content.decode()


@pytest.mark.parametrize('estado, esperados', [
    ('Disponible', ['Multímetro', 'Osciloscopio']),
    ('Prestado', ['Multímetro']),
    ('Dañado', ['Multímetro']),
    ('Perdido', ['Multímetro']),
])
def test_filtro_por_estado(cliente_autenticado, laboratorio, inventario, estado, esperados):
    response = cliente_autenticado.get(_url(laboratorio), {'estado': estado})

    assert [i.nombre for i in response.context['insumos_page']] == esperados
    assert response.context['filtro_estado'] == estado


def test_filtro_por_estado_mantiene_conteos_completos(cliente_autenticado, laboratorio, inventario):
    response = cliente_autenticado.get(_url(laboratorio), {'estado': 'Prestado'})

    [mul] = list(response.context['insumos_page'])
    assert mul.stock_total == 5  # el filtro elige insumos, no recorta sus conteos


def test_filtro_por_estado_invalido_se_ignora(cliente_autenticado, laboratorio, inventario):
    response = cliente_autenticado.get(_url(laboratorio), {'estado': 'Mantenimiento'})

    assert response.context['filtro_estado'] == ''
    assert len(response.context['insumos_page']) == 2


def test_paginacion_inventario_10_por_pagina(cliente_autenticado, laboratorio, catalogos):
    for n in range(23):
        _insumo(f'Insumo {n:02d}', laboratorio)

    pagina_1 = cliente_autenticado.get(_url(laboratorio))
    pagina_3 = cliente_autenticado.get(_url(laboratorio), {'page': 3})

    assert len(pagina_1.context['insumos_page']) == 10
    assert pagina_1.context['insumos_page'].paginator.num_pages == 3
    assert [i.nombre for i in pagina_3.context['insumos_page']] == ['Insumo 20', 'Insumo 21', 'Insumo 22']
    assert 'href="?tab=inventario&page=2"' in pagina_1.content.decode()


def test_paginacion_conserva_filtros(cliente_autenticado, laboratorio, catalogos):
    for n in range(12):
        _insumo(f'Cable {n:02d}', laboratorio)

    response = cliente_autenticado.get(_url(laboratorio), {'busqueda': 'cable', 'page': 2})

    assert len(response.context['insumos_page']) == 2
    assert 'busqueda=cable' in response.context['qs_inventario']
    assert 'page=' not in response.context['qs_inventario']


def test_pagina_fuera_de_rango_muestra_la_ultima(cliente_autenticado, laboratorio, inventario):
    response = cliente_autenticado.get(_url(laboratorio), {'page': 99})

    assert response.status_code == 200
    assert response.context['insumos_page'].number == 1


# ── Modal de ítems (JSON) ────────────────────────────────────────────────────

def test_fila_de_insumo_apunta_al_endpoint_del_modal(cliente_autenticado, laboratorio, inventario):
    contenido = cliente_autenticado.get(_url(laboratorio)).content.decode()

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


# ── Pestaña Reservas ─────────────────────────────────────────────────────────

def _reserva_publica(laboratorio, nombre, cedula, estado='Pendiente', dias=1):
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now() + timedelta(days=dias),
        estado=EstadoReserva.objects.get(nombre=estado),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre=nombre, cedula=cedula,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
    )
    return reserva


def test_pestana_reservas_lista_las_del_laboratorio(cliente_autenticado, catalogos, laboratorio, otro_laboratorio):
    propia = _reserva_publica(laboratorio, 'Ana Ruiz', '111')
    _reserva_publica(otro_laboratorio, 'Luis Mora', '222')

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas'})

    assert [r.id for r in response.context['reservas_page']] == [propia.id]
    contenido = response.content.decode()
    assert 'Ana Ruiz' in contenido
    assert 'Luis Mora' not in contenido
    assert f'href="/reservas/{propia.id}/"' in contenido


def test_pestana_reservas_incluye_reservas_de_insumos_del_lab(cliente_autenticado, reserva_con_prestamo, laboratorio):
    from reservas.models import ReservaInsumo
    ReservaInsumo.objects.create(reserva=reserva_con_prestamo.reserva, insumo=reserva_con_prestamo.item.insumo, cantidad=1)

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas'})

    assert [r.id for r in response.context['reservas_page']] == [reserva_con_prestamo.reserva.id]


def test_reservas_filtro_por_estado(cliente_autenticado, catalogos, laboratorio):
    _reserva_publica(laboratorio, 'Ana Ruiz', '111', 'Pendiente')
    aprobada = _reserva_publica(laboratorio, 'Luis Mora', '222', 'Aprobada')

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas', 'r_estado': 'Aprobada'})

    assert [r.id for r in response.context['reservas_page']] == [aprobada.id]


@pytest.mark.parametrize('termino', ['ana', 'RUIZ', '111'])
def test_reservas_filtro_por_estudiante(cliente_autenticado, catalogos, laboratorio, termino):
    ana = _reserva_publica(laboratorio, 'Ana Ruiz', '111')
    _reserva_publica(laboratorio, 'Luis Mora', '222')

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas', 'r_buscar': termino})

    assert [r.id for r in response.context['reservas_page']] == [ana.id]


def test_reservas_paginacion(cliente_autenticado, catalogos, laboratorio):
    for n in range(12):
        _reserva_publica(laboratorio, f'Estudiante {n}', f'C{n}', dias=n + 1)

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas', 'r_page': 2})

    assert response.context['reservas_page'].number == 2
    assert len(response.context['reservas_page']) == 2


def test_reservas_vacia_muestra_mensaje(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas'})

    assert 'No hay reservas para este laboratorio.' in response.content.decode()


# ── Pestaña Préstamos ────────────────────────────────────────────────────────

def test_pestana_prestamos_lista_los_del_laboratorio(cliente_autenticado, reserva_con_prestamo, laboratorio):
    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'prestamos'})

    prestamo = reserva_con_prestamo.prestamo
    assert [p.id for p in response.context['prestamos_page']] == [prestamo.id]
    assert f'href="/prestamos/{prestamo.id}/"' in response.content.decode()


def test_prestamos_de_otro_lab_no_aparecen(cliente_autenticado, reserva_con_prestamo, otro_laboratorio):
    response = cliente_autenticado.get(_url(otro_laboratorio), {'tab': 'prestamos'})

    assert list(response.context['prestamos_page']) == []
    assert 'No hay préstamos con ítems de este laboratorio.' in response.content.decode()


def test_prestamos_filtro_por_estado(cliente_autenticado, reserva_con_prestamo, laboratorio):
    activo = cliente_autenticado.get(_url(laboratorio), {'tab': 'prestamos', 'p_estado': 'Activo'})
    devuelto = cliente_autenticado.get(_url(laboratorio), {'tab': 'prestamos', 'p_estado': 'Devuelto'})

    assert len(activo.context['prestamos_page']) == 1
    assert list(devuelto.context['prestamos_page']) == []


def test_prestamos_paginacion(cliente_autenticado, usuario_admin, laboratorio, insumo, catalogos):
    for n in range(11):
        reserva = Reserva.objects.create(
            usuario=usuario_admin, fecha_reserva=timezone.now() + timedelta(days=n),
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
        )
        prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Devuelto'),
        )
        PrestamoItem.objects.create(prestamo=prestamo, item_inventario=_item(f'IT-{n}', insumo, laboratorio))

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'prestamos', 'p_page': 2})

    assert response.context['prestamos_page'].paginator.count == 11
    assert len(response.context['prestamos_page']) == 1


# ── Filtros independientes entre pestañas ─────────────────────────────────────

def test_filtros_de_una_pestana_no_afectan_a_otra(cliente_autenticado, catalogos, laboratorio, inventario):
    _reserva_publica(laboratorio, 'Ana Ruiz', '111')

    response = cliente_autenticado.get(_url(laboratorio), {'tab': 'reservas', 'r_buscar': 'zzz', 'busqueda': 'osci'})

    assert list(response.context['reservas_page']) == []
    assert [i.nombre for i in response.context['insumos_page']] == ['Osciloscopio']
    assert 'r_buscar=zzz' in response.context['qs_inventario']
