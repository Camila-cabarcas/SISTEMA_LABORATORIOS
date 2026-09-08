"""
Tests para users/helpers.py: el control de acceso por laboratorio
(es_administrador, laboratorios_visibles, verificar_acceso_laboratorio,
laboratorio_de_reserva, laboratorio_de_prestamo) que usan las vistas de
reservas/ y prestamos/ — ver docs/auditoria_seguridad_codigo.md, CRÍTICO #2.
"""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from laboratorio.models import Laboratorio
from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from users.helpers import (
    es_administrador,
    laboratorio_de_prestamo,
    laboratorio_de_reserva,
    laboratorios_visibles,
    verificar_acceso_laboratorio,
)
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


def _reserva_con_solicitud(laboratorio, cedula='111222333'):
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now() + timedelta(days=1),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva,
        reserva=reserva,
    )
    return reserva


class TestEsAdministrador:

    def test_true_para_administrador(self, usuario_admin):
        assert es_administrador(usuario_admin) is True

    def test_false_para_laboratorista(self, usuario_laboratorista):
        assert es_administrador(usuario_laboratorista) is False

    def test_false_para_anonimo(self):
        from django.contrib.auth.models import AnonymousUser

        assert es_administrador(AnonymousUser()) is False


class TestLaboratoriosVisibles:

    def test_administrador_ve_todo_sin_filtro(self, usuario_admin, laboratorio):
        assert laboratorios_visibles(usuario_admin) is None

    def test_laboratorista_ve_solo_los_suyos(self, usuario_laboratorista, laboratorio, catalogos):
        otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')

        visibles = laboratorios_visibles(usuario_laboratorista)

        assert visibles == [laboratorio]
        assert otro_laboratorio not in visibles

    def test_laboratorista_con_dos_labs_ve_ambos(self, usuario_laboratorista, laboratorio, catalogos):
        segundo_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')
        segundo_laboratorio.encargados.add(usuario_laboratorista)

        visibles = laboratorios_visibles(usuario_laboratorista)

        assert set(visibles) == {laboratorio, segundo_laboratorio}

    def test_laboratorista_sin_labs_lanza_permission_denied(self, catalogos):
        usuario = Usuario.objects.create_user(
            username='lab_sin_asignar', password='x', rol=Rol.objects.get(nombre='Laboratorio'),
        )

        with pytest.raises(PermissionDenied):
            laboratorios_visibles(usuario)


class TestVerificarAccesoLaboratorio:

    def test_administrador_siempre_pasa(self, usuario_admin, laboratorio):
        verificar_acceso_laboratorio(usuario_admin, laboratorio)  # no debe lanzar

    def test_laboratorista_de_ese_lab_pasa(self, usuario_laboratorista, laboratorio):
        verificar_acceso_laboratorio(usuario_laboratorista, laboratorio)  # no debe lanzar

    def test_laboratorista_de_otro_lab_lanza_permission_denied(self, usuario_laboratorista, catalogos):
        otro_laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')

        with pytest.raises(PermissionDenied):
            verificar_acceso_laboratorio(usuario_laboratorista, otro_laboratorio)

    def test_laboratorio_none_lanza_permission_denied(self, usuario_laboratorista):
        with pytest.raises(PermissionDenied):
            verificar_acceso_laboratorio(usuario_laboratorista, None)


class TestLaboratorioDeReservaYPrestamo:

    def test_laboratorio_de_reserva_con_solicitud(self, laboratorio, catalogos):
        reserva = _reserva_con_solicitud(laboratorio)

        assert laboratorio_de_reserva(reserva) == laboratorio

    def test_laboratorio_de_reserva_sin_solicitud_es_none(self, catalogos):
        reserva = Reserva.objects.create(
            fecha_reserva=timezone.now(), estado=EstadoReserva.objects.get(nombre='Aprobada'),
        )

        assert laboratorio_de_reserva(reserva) is None

    def test_laboratorio_de_prestamo(self, laboratorio, usuario_admin, catalogos):
        reserva = _reserva_con_solicitud(laboratorio)
        prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Activo'),
        )

        assert laboratorio_de_prestamo(prestamo) == laboratorio
