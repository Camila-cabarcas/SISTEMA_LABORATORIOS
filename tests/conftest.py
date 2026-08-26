"""
conftest.py — fixtures compartidas para toda la suite de tests.
"""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from inventario.models import EstadoItem, Insumo, ItemInventario, TipoMovimiento
from laboratorio.models import Laboratorio
from prestamos.models import EstadoPrestamo, Prestamo, PrestamoItem
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import Curso, SolicitudReserva
from users.models import Rol, Usuario


@pytest.fixture
def catalogos(db):
    """
    Crea las filas de catálogo (Rol/Estado/TipoMovimiento) que el código de
    modelos, vistas y señales asume que ya existen en la base de datos.
    """
    for nombre in ['Administrador', 'Laboratorio', 'Estudiante', 'Docente']:
        Rol.objects.get_or_create(nombre=nombre)
    for nombre in ['Pendiente', 'Aprobada', 'Cancelada', 'Expirada']:
        EstadoReserva.objects.get_or_create(nombre=nombre)
    for nombre in ['Activo', 'En Inspección', 'Devuelto', 'Retrasado']:
        EstadoPrestamo.objects.get_or_create(nombre=nombre)
    for nombre in ['Disponible', 'Prestado', 'Dañado', 'Perdido']:
        EstadoItem.objects.get_or_create(nombre=nombre)
    for nombre in ['Prestado', 'Devuelto']:
        TipoMovimiento.objects.get_or_create(nombre=nombre)


@pytest.fixture
def usuario_admin(catalogos):
    rol = Rol.objects.get(nombre='Administrador')
    return Usuario.objects.create_user(
        username='admin_test',
        password='clave12345',
        rol=rol,
    )


@pytest.fixture
def usuario_estudiante(catalogos):
    rol = Rol.objects.get(nombre='Estudiante')
    return Usuario.objects.create_user(
        username='estudiante_test',
        password='clave12345',
        rol=rol,
    )


@pytest.fixture
def usuario_laboratorista(laboratorio, catalogos):
    """Usuario rol='Laboratorio' asignado como encargado de `laboratorio`
    (ver Laboratorio.encargados / laboratorio.models.es_laboratorista_del_laboratorio)."""
    rol = Rol.objects.get(nombre='Laboratorio')
    usuario = Usuario.objects.create_user(
        username='laboratorista_test',
        password='clave12345',
        rol=rol,
        # codigo explícito: Usuario.codigo es unique=True pero blank=True, y
        # el valor por defecto ('') colisiona con otros Usuario creados sin
        # codigo (p. ej. usuario_admin) si ambos fixtures se usan en el
        # mismo test.
        codigo='LAB_TEST_001',
    )
    laboratorio.encargados.add(usuario)
    return usuario


@pytest.fixture
def laboratorio(db):
    return Laboratorio.objects.create(
        nombre='Laboratorio de Química',
        ubicacion='Bloque 5 - Piso 2',
    )


@pytest.fixture
def curso(db):
    return Curso.objects.create(
        codigo='QUIM101',
        nombre='Química General',
        docente='Prof. Pérez',
    )


@pytest.fixture
def insumo(db):
    return Insumo.objects.create(
        nombre='Vaso precipitado',
        descripcion='Vaso de vidrio de 250ml',
        stock_minimo=1,
    )


@pytest.fixture
def solicitud_valida(laboratorio):
    """SolicitudReserva ya guardada y lista para convertir a Reserva."""
    manana = timezone.now().date() + timedelta(days=1)
    return SolicitudReserva.objects.create(
        tipo_solicitante='estudiante',
        nombre='Juan Pérez',
        cedula='123456789',
        laboratorio=laboratorio,
        fecha_reserva=datetime.combine(manana, time(8, 0)),
        hora_inicio=time(8, 0),
        hora_fin=time(10, 0),
    )


@pytest.fixture
def reserva_con_prestamo(usuario_admin, laboratorio, insumo, catalogos):
    """Reserva Aprobada + Prestamo Activo + un PrestamoItem con su ItemInventario."""
    estado_aprobada = EstadoReserva.objects.get(nombre='Aprobada')
    reserva = Reserva.objects.create(
        usuario=usuario_admin,
        fecha_reserva=timezone.now(),
        estado=estado_aprobada,
    )

    estado_disponible = EstadoItem.objects.get(nombre='Disponible')
    item = ItemInventario.objects.create(
        codigo='ITEM-001',
        insumo=insumo,
        estado=estado_disponible,
        laboratorio=laboratorio,
    )

    estado_activo = EstadoPrestamo.objects.get(nombre='Activo')
    prestamo = Prestamo.objects.create(
        reserva=reserva,
        responsable=usuario_admin,
        estado=estado_activo,
    )

    # Crear el PrestamoItem dispara una señal que pasa el item a 'Prestado';
    # refrescamos para que el objeto en memoria refleje ese estado real.
    prestamo_item = PrestamoItem.objects.create(
        prestamo=prestamo,
        item_inventario=item,
    )
    item.refresh_from_db()

    return SimpleNamespace(
        reserva=reserva,
        prestamo=prestamo,
        item=item,
        prestamo_item=prestamo_item,
    )


@pytest.fixture
def cliente_autenticado(client, usuario_admin):
    client.force_login(usuario_admin)
    return client
