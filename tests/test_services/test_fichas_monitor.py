"""
Fichas de monitor (personas sin cuenta) en laboratorio/services/personal.py,
y los permisos de Personal en users/helpers.py.
"""
import pytest
from django.core.exceptions import PermissionDenied

from laboratorio.models import FichaMonitor, Laboratorio
from laboratorio.services import personal
from laboratorio.services.personal import DatosPersonalInvalidos, SinPermisoPersonal
from users.helpers import (
    puede_administrar_personal,
    puede_editar_descripcion,
    puede_gestionar_fichas,
    puede_ver_personal,
)
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db

DATOS = {'nombre': 'Ana', 'apellido': 'Ruiz', 'correo': 'ana.ruiz@gmail.com',
         'telefono': '300 123 4567', 'descripcion': 'Monitora de la jornada de la tarde.'}


@pytest.fixture
def otro_laboratorio(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')


@pytest.fixture
def laboratorista_ajeno(otro_laboratorio, catalogos):
    """Laboratorista de `otro_laboratorio`, no de `laboratorio`."""
    cuenta = Usuario.objects.create_user(
        username='lab_fisica', password='x', rol=Rol.objects.get(nombre='Laboratorista'))
    otro_laboratorio.laboratoristas.add(cuenta)
    return cuenta


@pytest.fixture
def ficha(usuario_laboratorista, laboratorio):
    return personal.agregar_ficha(DATOS, laboratorio, usuario_laboratorista)


def _labs(ficha):
    return set(ficha.laboratorios.all())


# ── Agregar ─────────────────────────────────────────────────────────────

class TestAgregar:

    def test_el_laboratorista_agrega_en_su_laboratorio(self, usuario_laboratorista, laboratorio):
        ficha = personal.agregar_ficha(DATOS, laboratorio, usuario_laboratorista)
        assert _labs(ficha) == {laboratorio}
        assert ficha.creado_por == usuario_laboratorista
        assert (ficha.nombre, ficha.apellido, ficha.telefono) == ('Ana', 'Ruiz', '300 123 4567')
        assert ficha.activo

    def test_el_administrador_agrega_en_cualquiera(self, usuario_admin, otro_laboratorio):
        ficha = personal.agregar_ficha(DATOS, otro_laboratorio, usuario_admin)
        assert _labs(ficha) == {otro_laboratorio}

    def test_correo_de_cualquier_dominio_y_opcional(self, usuario_admin, laboratorio):
        con_gmail = personal.agregar_ficha(DATOS, laboratorio, usuario_admin)
        sin_correo = personal.agregar_ficha({**DATOS, 'correo': '', 'telefono': ''}, laboratorio, usuario_admin)
        assert con_gmail.correo == 'ana.ruiz@gmail.com'
        assert sin_correo.correo == ''

    def test_correo_con_formato_invalido_se_rechaza(self, usuario_admin, laboratorio):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.agregar_ficha({**DATOS, 'correo': 'no-es-correo'}, laboratorio, usuario_admin)
        assert 'correo' in error.value.errores

    @pytest.mark.parametrize('campo', ['nombre', 'apellido'])
    def test_nombre_y_apellido_obligatorios(self, usuario_admin, laboratorio, campo):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.agregar_ficha({**DATOS, campo: '  '}, laboratorio, usuario_admin)
        assert campo in error.value.errores
        assert not FichaMonitor.objects.exists()

    def test_el_laboratorista_no_agrega_en_otro_laboratorio(self, usuario_laboratorista, otro_laboratorio):
        with pytest.raises(SinPermisoPersonal):
            personal.agregar_ficha(DATOS, otro_laboratorio, usuario_laboratorista)
        assert not FichaMonitor.objects.exists()

    def test_el_monitor_no_agrega(self, usuario_monitor, laboratorio):
        with pytest.raises(SinPermisoPersonal) as error:
            personal.agregar_ficha(DATOS, laboratorio, usuario_monitor)
        assert isinstance(error.value, PermissionDenied)


# ── Varios laboratorios ─────────────────────────────────────────────────

class TestVariosLaboratorios:

    def test_una_ficha_en_dos_laboratorios(self, usuario_admin, ficha, laboratorio, otro_laboratorio):
        personal.vincular_ficha_a_laboratorio(ficha, otro_laboratorio, usuario_admin)
        assert _labs(ficha) == {laboratorio, otro_laboratorio}
        assert ficha in laboratorio.fichas_monitor.all()
        assert ficha in otro_laboratorio.fichas_monitor.all()

    def test_el_laboratorista_del_destino_vincula_a_su_laboratorio(
            self, ficha, laboratorista_ajeno, laboratorio, otro_laboratorio):
        personal.vincular_ficha_a_laboratorio(ficha, otro_laboratorio, laboratorista_ajeno)
        assert _labs(ficha) == {laboratorio, otro_laboratorio}

    def test_el_laboratorista_no_vincula_a_un_laboratorio_ajeno(
            self, ficha, usuario_laboratorista, otro_laboratorio, laboratorio):
        with pytest.raises(SinPermisoPersonal):
            personal.vincular_ficha_a_laboratorio(ficha, otro_laboratorio, usuario_laboratorista)
        assert _labs(ficha) == {laboratorio}

    def test_editar_desde_un_laboratorio_se_ve_en_el_otro(
            self, usuario_admin, ficha, usuario_laboratorista, otro_laboratorio):
        personal.vincular_ficha_a_laboratorio(ficha, otro_laboratorio, usuario_admin)
        personal.editar_ficha(ficha, {**DATOS, 'telefono': '311 000 0000'}, usuario_laboratorista)
        assert otro_laboratorio.fichas_monitor.get().telefono == '311 000 0000'

    def test_quitar_de_uno_no_afecta_al_otro(self, usuario_admin, ficha, laboratorio, otro_laboratorio):
        personal.vincular_ficha_a_laboratorio(ficha, otro_laboratorio, usuario_admin)
        borrada = personal.quitar_ficha_de_laboratorio(ficha, laboratorio, usuario_admin)
        assert borrada is False
        assert FichaMonitor.objects.filter(pk=ficha.pk).exists()
        assert _labs(ficha) == {otro_laboratorio}
        assert not laboratorio.fichas_monitor.exists()

    def test_se_borra_al_quedar_sin_laboratorios(self, usuario_laboratorista, ficha, laboratorio):
        borrada = personal.quitar_ficha_de_laboratorio(ficha, laboratorio, usuario_laboratorista)
        assert borrada is True
        assert not FichaMonitor.objects.filter(pk=ficha.pk).exists()

    def test_quitar_de_un_laboratorio_donde_no_esta(self, usuario_admin, ficha, otro_laboratorio):
        with pytest.raises(DatosPersonalInvalidos):
            personal.quitar_ficha_de_laboratorio(ficha, otro_laboratorio, usuario_admin)
        assert FichaMonitor.objects.filter(pk=ficha.pk).exists()


# ── Permisos sobre fichas ajenas ────────────────────────────────────────

class TestPermisos:

    def test_el_laboratorista_no_edita_fichas_de_otro_laboratorio(
            self, usuario_admin, otro_laboratorio, usuario_laboratorista):
        ajena = personal.agregar_ficha(DATOS, otro_laboratorio, usuario_admin)
        with pytest.raises(SinPermisoPersonal):
            personal.editar_ficha(ajena, {**DATOS, 'nombre': 'Cambiado'}, usuario_laboratorista)
        ajena.refresh_from_db()
        assert ajena.nombre == 'Ana'

    def test_el_laboratorista_no_quita_fichas_de_otro_laboratorio(
            self, usuario_admin, otro_laboratorio, usuario_laboratorista):
        ajena = personal.agregar_ficha(DATOS, otro_laboratorio, usuario_admin)
        with pytest.raises(SinPermisoPersonal):
            personal.quitar_ficha_de_laboratorio(ajena, otro_laboratorio, usuario_laboratorista)
        assert _labs(ajena) == {otro_laboratorio}

    def test_el_monitor_no_edita_ni_quita(self, ficha, usuario_monitor, laboratorio):
        with pytest.raises(SinPermisoPersonal):
            personal.editar_ficha(ficha, {**DATOS, 'nombre': 'X'}, usuario_monitor)
        with pytest.raises(SinPermisoPersonal):
            personal.quitar_ficha_de_laboratorio(ficha, laboratorio, usuario_monitor)
        assert FichaMonitor.objects.filter(pk=ficha.pk).exists()

    def test_el_administrador_edita_y_quita_cualquiera(self, usuario_admin, ficha, laboratorio):
        personal.editar_ficha(ficha, {**DATOS, 'nombre': 'Andrea'}, usuario_admin)
        assert FichaMonitor.objects.get(pk=ficha.pk).nombre == 'Andrea'
        assert personal.quitar_ficha_de_laboratorio(ficha, laboratorio, usuario_admin) is True


class TestHelpers:
    """users/helpers.py: permisos fijos por rol de la sección Personal."""

    @pytest.mark.parametrize('helper', [puede_ver_personal, puede_gestionar_fichas, puede_editar_descripcion])
    def test_por_rol_y_laboratorio(self, helper, usuario_admin, usuario_laboratorista, usuario_monitor,
                                   usuario_estudiante, laboratorio, otro_laboratorio):
        assert helper(usuario_admin, laboratorio) and helper(usuario_admin, otro_laboratorio)
        assert helper(usuario_laboratorista, laboratorio)
        assert not helper(usuario_laboratorista, otro_laboratorio)
        assert not helper(usuario_monitor, laboratorio)
        assert not helper(usuario_estudiante, laboratorio)

    def test_anonimo_no_puede(self, laboratorio):
        from django.contrib.auth.models import AnonymousUser
        anonimo = AnonymousUser()
        assert not puede_ver_personal(anonimo, laboratorio)
        assert not puede_gestionar_fichas(anonimo, laboratorio)
        assert not puede_editar_descripcion(anonimo, laboratorio)
        assert not puede_administrar_personal(anonimo)

    def test_solo_el_administrador_administra_cuentas(self, usuario_admin, usuario_laboratorista, usuario_monitor):
        assert puede_administrar_personal(usuario_admin)
        assert not puede_administrar_personal(usuario_laboratorista)
        assert not puede_administrar_personal(usuario_monitor)
