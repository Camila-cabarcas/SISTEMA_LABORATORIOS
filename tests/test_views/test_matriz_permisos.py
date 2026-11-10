"""
Matriz de permisos de la fase 1: Administrador, Laboratorista y Monitor
contra cada acción. Laboratorista y Monitor están asignados a `laboratorio`
(Laboratorio.laboratoristas / Laboratorio.monitores); `otro_lab` no es de ninguno.
"""
from datetime import date, timedelta

import pytest
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario
from laboratorio.models import Laboratorio
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from vetos.models import Veto

pytestmark = pytest.mark.django_db

ROLES = ['admin', 'laboratorista', 'monitor']
CLAVE_ADMIN = 'ClaveAdmin!123'


@pytest.fixture
def otro_lab(db):
    return Laboratorio.objects.create(nombre='Lab Ajeno', ubicacion='Bloque 9')


@pytest.fixture
def usuarios(usuario_admin, usuario_laboratorista, usuario_monitor):
    for u in (usuario_admin, usuario_laboratorista, usuario_monitor):
        u.set_admin_password(CLAVE_ADMIN)
    return {'admin': usuario_admin, 'laboratorista': usuario_laboratorista, 'monitor': usuario_monitor}


@pytest.fixture
def como(client, usuarios):
    def _login(rol):
        client.force_login(usuarios[rol])
        return client
    return _login


def _reserva(laboratorio, tipo='estudiante', estado='Aprobada'):
    ahora = timezone.now()
    reserva = Reserva.objects.create(
        fecha_reserva=ahora - timedelta(minutes=10),
        hora_limite_retiro=ahora + timedelta(hours=1),
        fecha_devolucion=ahora + timedelta(hours=2),
        estado=EstadoReserva.objects.get(nombre=estado),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante=tipo, nombre='Ana', cedula='111222333', email='ana@udea.edu.co',
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
    )
    return reserva


def _item(laboratorio, codigo):
    insumo = Insumo.objects.create(nombre=f'Insumo {codigo}', laboratorio=laboratorio)
    return ItemInventario.objects.create(
        codigo=codigo, insumo=insumo, laboratorio=laboratorio,
        estado=EstadoItem.objects.get(nombre='Disponible'),
    )


def _es_sin_permiso(resp):
    return resp.status_code == 302 and resp.url.endswith('/usuarios/sin-permiso/')


# ── Matriz: rol × acción ────────────────────────────────────────────────────

@pytest.mark.parametrize('rol', ROLES)
def test_ver_prestamos(como, rol):
    assert como(rol).get('/prestamos/').status_code == 200


@pytest.mark.parametrize('rol', ROLES)
def test_crear_prestamo(como, rol, laboratorio):
    reserva = _reserva(laboratorio)
    assert como(rol).get(f'/prestamos/crear/{reserva.id}/').status_code == 200


@pytest.mark.parametrize('rol', ROLES)
def test_crear_reserva(como, rol):
    assert como(rol).get('/reservas/crear/').status_code == 200


@pytest.mark.parametrize('rol, permitido', [('admin', True), ('laboratorista', True), ('monitor', False)])
def test_aprobar_reserva(como, rol, permitido, laboratorio):
    reserva = _reserva(laboratorio)
    resp = como(rol).get(f'/reservas/{reserva.id}/aprobar/')
    if permitido:
        assert resp.status_code == 200
    else:
        assert _es_sin_permiso(resp)


@pytest.mark.parametrize('rol, permitido', [('admin', True), ('laboratorista', True), ('monitor', False)])
def test_importar_inventario(como, rol, permitido):
    resp = como(rol).get('/inventario/importar/')
    if permitido:
        assert resp.status_code == 200
    else:
        assert _es_sin_permiso(resp)


@pytest.mark.parametrize('rol, levanta', [('admin', True), ('laboratorista', True), ('monitor', False)])
@pytest.mark.parametrize('tipo', [Veto.DANO, Veto.FALTA_INSUMO])
def test_levantar_veto_de_dano_o_falta(como, rol, levanta, tipo, laboratorio):
    veto = Veto.objects.create(cedula='111222333', tipo=tipo, fecha_fin=None,
                               reserva=_reserva(laboratorio))
    como(rol).post(f'/vetos/{veto.id}/remover/', {'pagado': '1'})
    veto.refresh_from_db()
    assert (veto.estado != Veto.ACTIVO) is levanta


@pytest.mark.parametrize('rol, levanta', [('admin', True), ('laboratorista', False), ('monitor', False)])
@pytest.mark.parametrize('tipo', [Veto.RETRASO, Veto.NO_CANCELO])
def test_levantar_veto_de_atraso_o_no_cancelo(como, rol, levanta, tipo, laboratorio):
    veto = Veto.objects.create(cedula='111222333', tipo=tipo,
                               fecha_fin=date.today() + timedelta(days=3),
                               reserva=_reserva(laboratorio))
    como(rol).post(f'/vetos/{veto.id}/remover/')
    veto.refresh_from_db()
    assert (veto.estado != Veto.ACTIVO) is levanta


def test_laboratorista_no_levanta_veto_de_dano_de_otro_laboratorio(como, otro_lab):
    veto = Veto.objects.create(cedula='111222333', tipo=Veto.DANO, fecha_fin=None,
                               reserva=_reserva(otro_lab))
    resp = como('laboratorista').post(f'/vetos/{veto.id}/remover/', follow=True)
    veto.refresh_from_db()
    assert veto.estado == Veto.ACTIVO
    assert 'laboratorios que tienes asignados' in resp.content.decode()


@pytest.mark.parametrize('rol, status', [('admin', 200), ('laboratorista', 403), ('monitor', 403)])
def test_editar_mapa(como, rol, status, laboratorio):
    assert como(rol).get(f'/laboratorio/{laboratorio.id}/editar-mapa/').status_code == status


@pytest.mark.parametrize('rol, borra', [('admin', True), ('laboratorista', True), ('monitor', False)])
def test_eliminar_item_de_su_laboratorio(como, rol, borra, laboratorio):
    item = _item(laboratorio, f'PROPIO-{rol}')
    resp = como(rol).post(f'/inventario/items/{item.id}/eliminar/', {'admin_password': CLAVE_ADMIN})
    item.refresh_from_db()
    assert item.is_deleted() is borra
    if rol == 'monitor':
        assert resp.status_code == 403


@pytest.mark.parametrize('rol, borra', [('admin', True), ('laboratorista', False), ('monitor', False)])
def test_eliminar_item_de_otro_laboratorio(como, rol, borra, otro_lab):
    item = _item(otro_lab, f'AJENO-{rol}')
    como(rol).post(f'/inventario/items/{item.id}/eliminar/', {'admin_password': CLAVE_ADMIN})
    item.refresh_from_db()
    assert item.is_deleted() is borra


@pytest.mark.parametrize('url', [
    '/vetos/', '/laboratorio/categorias/', '/usuarios/', '/inventario/',
    '/prestamos/exportar-excel/',
])
def test_monitor_no_entra_a_secciones_ajenas(como, url):
    assert _es_sin_permiso(como('monitor').get(url))


# ── Monitor: solo reservas de estudiantes, en sus laboratorios ─────────────

def test_monitor_solo_ve_reservas_de_estudiantes(como, laboratorio, otro_lab):
    de_estudiante = _reserva(laboratorio, tipo='estudiante')
    de_profesor = _reserva(laboratorio, tipo='profesor')
    de_otro_lab = _reserva(otro_lab, tipo='estudiante')

    resp = como('monitor').get('/reservas/')
    ids = {r.id for r in resp.context['reservas']}
    assert ids == {de_estudiante.id}
    assert de_profesor.id not in ids and de_otro_lab.id not in ids


def test_monitor_no_abre_reserva_de_profesor(como, laboratorio):
    de_profesor = _reserva(laboratorio, tipo='profesor')
    resp = como('monitor').get(f'/reservas/{de_profesor.id}/')
    assert resp.status_code == 403


def test_monitor_abre_reserva_de_estudiante_sin_boton_de_aprobar(como, laboratorio):
    reserva = _reserva(laboratorio, tipo='estudiante', estado='Pendiente')
    resp = como('monitor').get(f'/reservas/{reserva.id}/')
    assert resp.status_code == 200
    assert f'/reservas/{reserva.id}/aprobar/' not in resp.content.decode()
    assert f'/reservas/{reserva.id}/cancelar-admin/' in resp.content.decode()


def test_monitor_crea_reserva_siempre_como_estudiante(como, laboratorio, monkeypatch):
    """Aunque el POST diga 'profesor', el Monitor solo crea reservas de estudiante."""
    capturado = {}

    class _ServicioFalso:
        def ejecutar(self, solicitud_id, usuario, modulos_ids=None):
            capturado['tipo'] = SolicitudReserva.objects.get(id=solicitud_id).tipo_solicitante
            raise RuntimeError('corte del test')

    monkeypatch.setattr(
        'reservas.services.crear_reserva_service.CrearReservaService', _ServicioFalso,
    )
    manana = date.today() + timedelta(days=1)
    como('monitor').post('/reservas/crear/', {
        'tipo_solicitante': 'profesor', 'nombre': 'Ana', 'cedula': '999',
        'laboratorio': laboratorio.id, 'fecha': manana.isoformat(),
        'hora_inicio': '08:00', 'hora_fin': '09:00',
    })
    assert capturado.get('tipo') == 'estudiante'


def test_monitor_no_crea_reserva_en_otro_laboratorio(como, otro_lab):
    manana = date.today() + timedelta(days=1)
    resp = como('monitor').post('/reservas/crear/', {
        'tipo_solicitante': 'estudiante', 'nombre': 'Ana', 'cedula': '999',
        'laboratorio': otro_lab.id, 'fecha': manana.isoformat(),
        'hora_inicio': '08:00', 'hora_fin': '09:00',
    })
    assert 'No tienes acceso a ese laboratorio.' in resp.content.decode()
    assert not SolicitudReserva.objects.filter(laboratorio=otro_lab).exists()


def test_monitor_sin_laboratorio_no_ve_reservas(client, catalogos):
    from users.models import Rol, Usuario
    suelto = Usuario.objects.create_user(
        username='monitor_suelto', password='x', codigo='MON-SUELTO',
        rol=Rol.objects.get(nombre='Monitor'),
    )
    client.force_login(suelto)
    assert client.get('/reservas/').status_code == 403


# ── Monitor: inventario solo consulta ───────────────────────────────────────

@pytest.mark.parametrize('url', ['/inventario/items/', '/inventario/movimientos/'])
def test_monitor_consulta_inventario_sin_formularios(como, url):
    resp = como('monitor').get(url)
    assert resp.status_code == 200
    assert f'action="{url}"' not in resp.content.decode()


@pytest.mark.parametrize('url', ['/inventario/items/', '/inventario/movimientos/'])
def test_monitor_no_registra_en_inventario(como, url):
    assert _es_sin_permiso(como('monitor').post(url, {}))


# ── Menús ──────────────────────────────────────────────────────────────────

def test_menu_laboratorista_tiene_vetos_e_importar(como):
    html = como('laboratorista').get('/prestamos/').content.decode()
    assert 'href="/vetos/"' in html
    assert 'href="/inventario/importar/"' in html


def test_menu_monitor_sin_vetos_importar_ni_aprobar(como):
    html = como('monitor').get('/prestamos/').content.decode()
    assert 'href="/prestamos/"' in html
    assert 'href="/reservas/"' in html
    assert 'href="/inventario/items/"' in html
    assert 'href="/vetos/"' not in html
    assert 'href="/inventario/importar/"' not in html
    assert '/aprobar/' not in html
    assert 'Contraseña admin' not in html
