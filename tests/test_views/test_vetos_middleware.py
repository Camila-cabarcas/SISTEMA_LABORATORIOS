"""
Tests de VetosAutomaticosMiddleware (vetos/middleware.py): genera los vetos
NO_CANCELO pendientes durante las requests, como mucho una vez cada
VETOS_AUTO_INTERVALO_MINUTOS, sin cron externo.
"""
from datetime import datetime, timedelta

import pytest
from django.core.cache import cache

from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from vetos.models import Veto
from vetos.services import GenerarVetosNoCanceloService

pytestmark = pytest.mark.django_db

URL = '/login/'  # cualquier página sirve; esta no requiere sesión


@pytest.fixture
def activo(settings):
    settings.VETOS_AUTO_INTERVALO_MINUTOS = 10
    cache.clear()
    yield
    cache.clear()


def _no_show(laboratorio, cedula):
    """Reserva Aprobada sin préstamo cuyo límite de retiro venció hace 1 h."""
    fecha = datetime.now() - timedelta(hours=1, minutes=30)
    reserva = Reserva.objects.create(
        fecha_reserva=fecha, estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre='Ana', cedula=cedula,
        laboratorio=laboratorio, fecha_reserva=fecha, reserva=reserva,
    )
    return reserva


def test_una_request_genera_el_veto(client, catalogos, laboratorio, activo):
    reserva = _no_show(laboratorio, '111')

    assert client.get(URL).status_code == 200

    veto = Veto.objects.get()
    assert veto.tipo == Veto.NO_CANCELO
    assert veto.reserva == reserva


def test_respeta_el_intervalo(client, catalogos, laboratorio, activo):
    _no_show(laboratorio, '111')
    client.get(URL)

    # Vence otra reserva dentro del intervalo: todavía no se revisa.
    _no_show(laboratorio, '222')
    client.get(URL)
    assert Veto.objects.count() == 1

    # Pasó el intervalo (expira la marca en caché): la siguiente request la toma.
    cache.delete(GenerarVetosNoCanceloService.CACHE_KEY_ULTIMA_EJECUCION)
    client.get(URL)
    assert set(Veto.objects.values_list('cedula', flat=True)) == {'111', '222'}


def test_desactivado_con_intervalo_cero(client, catalogos, laboratorio, settings):
    settings.VETOS_AUTO_INTERVALO_MINUTOS = 0
    cache.clear()
    _no_show(laboratorio, '111')

    client.get(URL)

    assert not Veto.objects.exists()


def test_no_corre_en_archivos_estaticos(client, catalogos, laboratorio, activo):
    _no_show(laboratorio, '111')

    client.get('/static/css/theme.css')

    assert not Veto.objects.exists()


def test_un_error_no_rompe_la_request(client, catalogos, laboratorio, activo, monkeypatch):
    def falla(**kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(GenerarVetosNoCanceloService, 'ejecutar', staticmethod(falla))

    assert client.get(URL).status_code == 200


def test_el_veto_existe_antes_de_que_corra_la_vista(client, catalogos, laboratorio, activo, usuario_admin):
    # El middleware corre antes de la vista: la misma request en que se
    # detecta el no-show ya lista el veto recién creado.
    _no_show(laboratorio, '111')
    client.force_login(usuario_admin)

    resp = client.get('/vetos/')

    assert [v.cedula for v in resp.context['page_obj']] == ['111']
