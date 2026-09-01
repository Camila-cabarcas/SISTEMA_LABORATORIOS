"""
Tests para MisReservasService (solicitudes/services/mis_reservas_service.py):
la identificación "cédula + email" que sostiene todo el autoservicio Mis
Reservas (no hay login de estudiante/profesor en este sistema).
"""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from solicitudes.services.mis_reservas_service import MisReservasService

pytestmark = pytest.mark.django_db


def _solicitud_con_reserva(laboratorio, cedula='111222333', email='ana@udea.edu.co', usuario=None):
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now() + timedelta(days=1),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    return SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula, email=email, usuario=usuario,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
    )


class TestEsPropietario:

    def test_cedula_y_email_correctos(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        assert MisReservasService.es_propietario(solicitud, '111222333', 'ana@udea.edu.co') is True

    def test_email_es_insensible_a_mayusculas(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        assert MisReservasService.es_propietario(solicitud, '111222333', 'ANA@UDEA.EDU.CO') is True

    def test_cedula_incorrecta(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        assert MisReservasService.es_propietario(solicitud, '999999999', 'ana@udea.edu.co') is False

    def test_email_incorrecto(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        assert MisReservasService.es_propietario(solicitud, '111222333', 'otro@udea.edu.co') is False

    def test_cedula_o_email_vacios(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        assert MisReservasService.es_propietario(solicitud, '', 'ana@udea.edu.co') is False
        assert MisReservasService.es_propietario(solicitud, '111222333', '') is False

    def test_solicitud_none(self):
        assert MisReservasService.es_propietario(None, '111222333', 'ana@udea.edu.co') is False

    def test_acepta_email_del_usuario_si_la_solicitud_no_tiene_email_propio(
        self, laboratorio, usuario_admin, catalogos,
    ):
        # Caso ProfesorSolicitudForm normal: solicitud.email queda vacío,
        # el email válido es el de la cuenta Usuario del docente.
        usuario_admin.email = 'docente@udea.edu.co'
        usuario_admin.save()
        solicitud = _solicitud_con_reserva(laboratorio, email='', usuario=usuario_admin)

        assert MisReservasService.es_propietario(solicitud, '111222333', 'docente@udea.edu.co') is True


class TestVerificarPropietario:

    def test_lanza_permission_denied_si_no_coincide(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        with pytest.raises(PermissionDenied):
            MisReservasService.verificar_propietario(solicitud, '111222333', 'otro@udea.edu.co')

    def test_no_lanza_si_coincide(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        MisReservasService.verificar_propietario(solicitud, '111222333', 'ana@udea.edu.co')


class TestBuscar:

    def test_encuentra_solicitudes_de_la_cedula_y_email(self, laboratorio, catalogos):
        solicitud = _solicitud_con_reserva(laboratorio)

        resultado = MisReservasService.buscar('111222333', 'ana@udea.edu.co')

        assert resultado == [solicitud]

    def test_no_encuentra_con_email_distinto(self, laboratorio, catalogos):
        _solicitud_con_reserva(laboratorio)

        assert MisReservasService.buscar('111222333', 'otro@udea.edu.co') == []

    def test_no_incluye_solicitudes_de_otra_cedula(self, laboratorio, catalogos):
        _solicitud_con_reserva(laboratorio, cedula='111222333', email='ana@udea.edu.co')
        _solicitud_con_reserva(laboratorio, cedula='999999999', email='ana@udea.edu.co')

        resultado = MisReservasService.buscar('111222333', 'ana@udea.edu.co')

        assert len(resultado) == 1
        assert resultado[0].cedula == '111222333'

    def test_ignora_solicitudes_sin_reserva_asociada(self, laboratorio, catalogos):
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', cedula='111222333', email='ana@udea.edu.co',
            laboratorio=laboratorio, fecha_reserva=timezone.now() + timedelta(days=1),
        )

        assert MisReservasService.buscar('111222333', 'ana@udea.edu.co') == []

    def test_cedula_o_email_vacios_devuelve_lista_vacia(self):
        assert MisReservasService.buscar('', 'ana@udea.edu.co') == []
        assert MisReservasService.buscar('111222333', '') == []
