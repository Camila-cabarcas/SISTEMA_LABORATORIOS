"""
Tests HTTP del dashboard por rol (dashboard/views.py):
  - Administrador: sección general (todos los labs) + filtro ?lab=<id>.
  - Laboratorio: mismas cifras, fijas a sus laboratorios asignados.
"""
import pytest
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario
from laboratorio.models import Laboratorio
from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db

URL = '/'


def _item(codigo, insumo, estado='Disponible'):
    return ItemInventario.objects.create(
        codigo=codigo, insumo=insumo, laboratorio=insumo.laboratorio,
        estado=EstadoItem.objects.get(nombre=estado),
    )


def _reserva(laboratorio, usuario, estado='Pendiente', n=0):
    reserva = Reserva.objects.create(
        usuario=usuario, fecha_reserva=timezone.now(),
        estado=EstadoReserva.objects.get(nombre=estado),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre='Ana', cedula=f'10{n}',
        laboratorio=laboratorio, fecha_reserva=timezone.now(), reserva=reserva,
    )
    return reserva


@pytest.fixture
def datos(catalogos, laboratorio, usuario_admin):
    """Química: 2 insumos (Multímetro con stock bajo), 4 ítems (uno por
    estado), 1 reserva pendiente, 1 préstamo activo.
    Física: 1 insumo con 1 ítem disponible, 1 reserva pendiente."""
    fisica = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 1')

    multimetro = Insumo.objects.create(nombre='Multímetro', laboratorio=laboratorio, stock_minimo=2)
    for codigo, estado in [('Q-1', 'Disponible'), ('Q-2', 'Prestado'), ('Q-3', 'Dañado'), ('Q-4', 'Perdido')]:
        _item(codigo, multimetro, estado)
    Insumo.objects.create(nombre='Probeta', laboratorio=laboratorio)

    pendulo = Insumo.objects.create(nombre='Péndulo', laboratorio=fisica, stock_minimo=0)
    _item('F-1', pendulo)

    _reserva(laboratorio, usuario_admin, n=1)
    _reserva(fisica, usuario_admin, n=2)
    aprobada = _reserva(laboratorio, usuario_admin, 'Aprobada', n=3)
    Prestamo.objects.create(
        reserva=aprobada, responsable=usuario_admin,
        estado=EstadoPrestamo.objects.get(nombre='Activo'),
    )
    return {'quimica': laboratorio, 'fisica': fisica}


def _estados(stats):
    return {e['clave']: e['valor'] for e in stats['estados']}


class TestAdmin:

    def test_general_combina_todos_los_labs(self, cliente_autenticado, datos):
        resp = cliente_autenticado.get(URL)
        assert resp.status_code == 200
        general = resp.context['general']
        assert general['total_insumos'] == 3
        assert general['total_items'] == 5
        assert _estados(general) == {'disponible': 2, 'prestado': 1, 'danado': 1, 'extraviado': 1}
        assert general['reservas_pendientes'] == 2
        assert general['prestamos_activos'] == 1
        assert [i.nombre for i in general['stock_bajo']] == ['Multímetro']
        assert resp.context['por_lab'] is None

    def test_filtro_por_lab(self, cliente_autenticado, datos):
        resp = cliente_autenticado.get(URL, {'lab': datos['fisica'].id})
        por_lab = resp.context['por_lab']
        assert resp.context['lab_seleccionado'] == datos['fisica']
        assert por_lab['total_insumos'] == 1
        assert por_lab['total_items'] == 1
        assert por_lab['reservas_pendientes'] == 1
        assert por_lab['prestamos_activos'] == 0
        assert por_lab['stock_bajo'] == []
        # La sección general no cambia con el filtro.
        assert resp.context['general']['total_items'] == 5

    def test_lab_invalido_se_ignora(self, cliente_autenticado, datos):
        resp = cliente_autenticado.get(URL, {'lab': 'abc'})
        assert resp.status_code == 200
        assert resp.context['por_lab'] is None


class TestLaboratorio:

    def test_solo_ve_su_lab(self, client, usuario_laboratorista, datos):
        client.force_login(usuario_laboratorista)
        resp = client.get(URL)
        stats = resp.context['stats']
        assert stats['total_insumos'] == 2
        assert stats['total_items'] == 4
        assert stats['reservas_pendientes'] == 1
        assert stats['prestamos_activos'] == 1
        assert 'general' not in resp.context
        assert b'dash-lab' not in resp.content  # sin dropdown de filtro

    def test_sin_lab_asignado(self, client, usuario_laboratorista, datos):
        datos['quimica'].encargados.clear()
        client.force_login(usuario_laboratorista)
        resp = client.get(URL)
        assert resp.status_code == 200
        assert resp.context['stats'] is None
