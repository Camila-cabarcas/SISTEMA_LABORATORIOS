"""
Tests HTTP (Client) para solicitudes/views.py::lista_solicitudes (/solicitudes/):
la pestaña "Crear Reserva" (enlaces a los formularios existentes) y "Mis
Reservas" (autoservicio por cédula + email).
"""
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva

pytestmark = pytest.mark.django_db


def _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', email='ana@udea.edu.co', fecha_reserva=None):
    reserva = Reserva.objects.create(
        fecha_reserva=fecha_reserva or (timezone.now() + timedelta(days=1)),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', cedula=cedula, email=email,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva,
        reserva=reserva,
    )
    return reserva


def test_no_requiere_login(client):
    # Antes tenía @login_required; el público real (estudiantes,
    # profesores) nunca tiene sesión iniciada en este sistema.
    response = client.get('/solicitudes/')

    assert response.status_code == 200


def test_pestana_crear_enlaza_a_los_formularios_existentes(client):
    response = client.get('/solicitudes/')

    contenido = response.content.decode()
    assert '/solicitudes/estudiante/' in contenido
    assert '/solicitudes/profesor/' in contenido


def test_sin_cedula_ni_email_no_busca(client, catalogos):
    response = client.get('/solicitudes/')

    assert response.status_code == 200
    assert response.context['buscado'] is False


def test_busca_por_cedula_y_email(client, laboratorio, catalogos):
    reserva = _reserva_aprobada_con_solicitud(laboratorio)

    response = client.get('/solicitudes/?cedula=111222333&email=ana@udea.edu.co')

    assert response.status_code == 200
    assert response.context['buscado'] is True
    contenido = response.content.decode()
    assert reserva.codigo in contenido


def test_busqueda_sin_resultados_muestra_error(client, catalogos):
    response = client.get('/solicitudes/?cedula=000000000&email=nadie@udea.edu.co')

    assert response.status_code == 200
    assert response.context['error_busqueda']


def test_no_muestra_reservas_de_otra_cedula(client, laboratorio, catalogos):
    _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', email='ana@udea.edu.co')
    otra = _reserva_aprobada_con_solicitud(laboratorio, cedula='999999999', email='otro@udea.edu.co')

    response = client.get('/solicitudes/?cedula=111222333&email=ana@udea.edu.co')

    assert otra.codigo not in response.content.decode()


def test_filtro_por_estado(client, laboratorio, catalogos):
    aprobada = _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', email='ana@udea.edu.co')
    cancelada = _reserva_aprobada_con_solicitud(
        laboratorio, cedula='111222333', email='ana@udea.edu.co',
    )
    cancelada.estado = EstadoReserva.objects.get(nombre='Cancelada')
    cancelada.save()

    response = client.get('/solicitudes/?cedula=111222333&email=ana@udea.edu.co&estado=Cancelada')

    contenido = response.content.decode()
    assert cancelada.codigo in contenido
    assert aprobada.codigo not in contenido


def test_filtro_por_codigo(client, laboratorio, catalogos):
    coincide = _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', email='ana@udea.edu.co')
    otra = _reserva_aprobada_con_solicitud(laboratorio, cedula='111222333', email='ana@udea.edu.co')

    response = client.get(f'/solicitudes/?cedula=111222333&email=ana@udea.edu.co&q={coincide.codigo}')

    contenido = response.content.decode()
    assert coincide.codigo in contenido
    assert otra.codigo not in contenido
