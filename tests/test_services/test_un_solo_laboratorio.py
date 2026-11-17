"""
Regla de la fase Personal (laboratorio.0024), sobre los modelos actuales:
- una cuenta Laboratorista está en a lo sumo UN laboratorio;
- una cuenta Monitor está en un solo laboratorio y cada laboratorio tiene a
  lo sumo una cuenta de monitor.
Que una cuenta Laboratorista activa tenga AL MENOS uno lo valida el servicio
de Personal (etapa 2), no la base.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from laboratorio.models import AsignacionLaboratorista, AsignacionMonitor, FichaMonitor, Laboratorio
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def segundo_laboratorio(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')


def _cuenta(username, rol):
    return Usuario.objects.create_user(username=username, password='x', rol=Rol.objects.get(nombre=rol))


class TestLaboratorista:

    def test_segundo_laboratorio_se_rechaza_en_la_base(
            self, usuario_laboratorista, laboratorio, segundo_laboratorio):
        with pytest.raises(IntegrityError), transaction.atomic():
            segundo_laboratorio.laboratoristas.add(usuario_laboratorista)
        assert list(usuario_laboratorista.laboratorios_asignados.all()) == [laboratorio]

    def test_full_clean_da_mensaje_claro(self, usuario_laboratorista, segundo_laboratorio):
        asignacion = AsignacionLaboratorista(laboratorio=segundo_laboratorio, usuario=usuario_laboratorista)
        with pytest.raises(ValidationError) as error:
            asignacion.full_clean()
        assert 'Esta cuenta ya tiene un laboratorio asignado.' in str(error.value)

    def test_volver_a_agregar_el_mismo_laboratorio_no_duplica(self, usuario_laboratorista, laboratorio):
        laboratorio.laboratoristas.add(usuario_laboratorista)
        assert AsignacionLaboratorista.objects.filter(usuario=usuario_laboratorista).count() == 1

    def test_cambiar_de_laboratorio_quitando_el_anterior(
            self, usuario_laboratorista, laboratorio, segundo_laboratorio):
        with transaction.atomic():
            laboratorio.laboratoristas.remove(usuario_laboratorista)
            segundo_laboratorio.laboratoristas.add(usuario_laboratorista)
        assert list(usuario_laboratorista.laboratorios_asignados.all()) == [segundo_laboratorio]

    def test_borrar_el_laboratorio_libera_la_cuenta(
            self, usuario_laboratorista, laboratorio, segundo_laboratorio):
        laboratorio.delete()
        segundo_laboratorio.laboratoristas.add(usuario_laboratorista)
        assert list(usuario_laboratorista.laboratorios_asignados.all()) == [segundo_laboratorio]

    def test_cuenta_inactiva_puede_quedar_sin_laboratorio(self, catalogos):
        cuenta = _cuenta('lab_baja', 'Laboratorista')
        cuenta.is_active = False
        cuenta.save()
        assert not cuenta.laboratorios_asignados.exists()


class TestMonitor:

    def test_cuenta_monitor_no_puede_estar_en_dos_laboratorios(
            self, usuario_monitor, segundo_laboratorio):
        with pytest.raises(IntegrityError), transaction.atomic():
            segundo_laboratorio.monitores.add(usuario_monitor)

    def test_laboratorio_no_puede_tener_dos_cuentas_de_monitor(self, usuario_monitor, laboratorio):
        otra = _cuenta('monitor_2', 'Monitor')
        with pytest.raises(IntegrityError), transaction.atomic():
            laboratorio.monitores.add(otra)
        assert list(laboratorio.monitores.all()) == [usuario_monitor]

    def test_full_clean_da_mensaje_claro(self, usuario_monitor, laboratorio):
        otra = _cuenta('monitor_2', 'Monitor')
        with pytest.raises(ValidationError) as error:
            AsignacionMonitor(laboratorio=laboratorio, usuario=otra).full_clean()
        assert 'Este laboratorio ya tiene una cuenta de monitor.' in str(error.value)

    def test_cada_laboratorio_con_su_propia_cuenta_de_monitor(
            self, usuario_monitor, laboratorio, segundo_laboratorio):
        otra = _cuenta('monitor_2', 'Monitor')
        segundo_laboratorio.monitores.add(otra)
        assert AsignacionMonitor.objects.count() == 2


class TestModelosNuevos:

    def test_descripcion_del_laboratorio_es_opcional(self, laboratorio):
        assert laboratorio.descripcion == ''
        laboratorio.descripcion = 'Laboratorio de electrónica básica.'
        laboratorio.full_clean()
        laboratorio.save()
        laboratorio.refresh_from_db()
        assert laboratorio.descripcion == 'Laboratorio de electrónica básica.'

    def test_ficha_de_monitor_en_varios_laboratorios(self, laboratorio, segundo_laboratorio, usuario_admin):
        ficha = FichaMonitor.objects.create(nombre='Ana', apellido='Ruiz', creado_por=usuario_admin)
        ficha.laboratorios.add(laboratorio, segundo_laboratorio)
        assert set(laboratorio.fichas_monitor.all()) == {ficha}
        assert set(segundo_laboratorio.fichas_monitor.all()) == {ficha}
        assert str(ficha) == 'Ana Ruiz'

    def test_ficha_acepta_correo_de_cualquier_dominio(self, laboratorio):
        ficha = FichaMonitor(nombre='Ana', apellido='Ruiz', correo='ana@gmail.com')
        ficha.full_clean()
