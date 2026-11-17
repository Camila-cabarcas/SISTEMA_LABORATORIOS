"""
Fase 2, etapa 1 — migraciones de profesores:
- solicitudes.0010 / 0011: modelo Profesor y ajustes de SolicitudRegistroProfesor
  (cédula única solo entre solicitudes pendientes o aprobadas);
- solicitudes.0012: cuentas Docente → Profesor, cursos → profesor_registro,
  descarte de e2e_profesor;
- users.0008: cuentas Docente inactivas y sin rol, rol Docente borrado.
"""
import importlib

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from solicitudes.models import Profesor, SolicitudRegistroProfesor

ANTES = [('solicitudes', '0011_ajustes_registro_profesor'), ('users', '0007_email_unico_sin_mayusculas')]
TRAS_0012 = [('solicitudes', '0012_docentes_a_profesores'), ('users', '0007_email_unico_sin_mayusculas')]
TRAS_0008 = [('users', '0008_quitar_rol_docente')]
INICIO = [('solicitudes', '0009_curso_laboratorio'), ('users', '0007_email_unico_sin_mayusculas')]

DatosInvalidos = importlib.import_module('solicitudes.migrations.0012_docentes_a_profesores').DatosInvalidos


def _migrar(destino):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    # Las últimas de reservas y prestamos (ya aplicadas, no cambian nada) para
    # tener Reserva y Prestamo en el estado.
    destino = [*destino, *executor.loader.graph.leaf_nodes('reservas'), *executor.loader.graph.leaf_nodes('prestamos')]
    executor.migrate(destino)
    return executor.loader.project_state(destino).apps


def _limpiar_y_migrar_al_final(apps=None):
    """Borra lo creado por el test y deja la BD de pruebas en la última
    migración (si quedaran cuentas Docente o cursos, la 0012 los convertiría
    o fallaría). Primero pasa a ANTES y borra con ESOS modelos históricos:
    estados más viejos (p. ej. solicitudes.0009) traen un Laboratorio con
    tablas que ya no existen y el borrado en cascada fallaría."""
    apps = _migrar(ANTES)
    for app, modelo in [('solicitudes', 'Curso'), ('solicitudes', 'Profesor'), ('reservas', 'Reserva'),
                        ('users', 'Usuario'), ('users', 'Rol')]:
        try:
            apps.get_model(app, modelo).objects.all().delete()
        except LookupError:  # Profesor no existe en estados anteriores a la 0010
            pass
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


def _aplicada(app, nombre):
    return (app, nombre) in MigrationRecorder(connection).applied_migrations()


def _datos(apps):
    """Las 3 cuentas Docente como en db.sqlite3, con 3 cursos cada una, una
    reserva de doc_123456789 y una cuenta Administrador (no se toca)."""
    Rol = apps.get_model('users', 'Rol')
    Usuario = apps.get_model('users', 'Usuario')
    Curso = apps.get_model('solicitudes', 'Curso')
    Reserva = apps.get_model('reservas', 'Reserva')
    docente = Rol.objects.create(nombre='Docente')
    admin = Rol.objects.create(nombre='Administrador')

    def cuenta(username, codigo, nombre, apellido, email, programa, activa=True, rol=docente):
        return Usuario.objects.create(username=username, codigo=codigo, first_name=nombre, last_name=apellido,
                                      email=email, programa=programa, is_active=activa, rol=rol)

    juliana = cuenta('doc_123456789', '123456789', 'Juliana', 'Garcia', 'Juliana.Garcia@udea.edu.co', 'Química')
    kali = cuenta('doc_333333', '333333', 'kali', 'uchis', 'kaly@gmail.com', 'Alimentos')
    e2e = cuenta('e2e_profesor', 'E2E-PROF', 'Profesor', 'E2E', '', '', activa=False)
    cuenta('jefe', 'JEFE', 'Jefe', 'Admin', 'jefe@udea.edu.co', '', rol=admin)

    for prefijo, profesor in (('JUL', juliana), ('KAL', kali), ('E2E', e2e)):
        for i in range(3):
            Curso.objects.create(nombre=f'{prefijo} {i}', codigo=f'{prefijo}-{i}', profesor=profesor,
                                 cantidad_estudiantes=20)
    Reserva.objects.create(usuario=juliana, fecha_reserva=timezone.now(), codigo='R-JULIANA')
    return {'juliana': juliana.id, 'kali': kali.id, 'e2e': e2e.id}


# ── 0012: cuentas Docente → Profesor ────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_0012_convierte_docentes_y_copia_cursos_sin_perdida():
    apps = _migrar(ANTES)
    ids = _datos(apps)
    try:
        apps = _migrar(TRAS_0012)
        Profesor = apps.get_model('solicitudes', 'Profesor')
        Curso = apps.get_model('solicitudes', 'Curso')

        juliana = Profesor.objects.get(cedula='123456789')
        assert (juliana.nombre, juliana.apellido, juliana.correo, juliana.programa) == (
            'Juliana', 'Garcia', 'Juliana.Garcia@udea.edu.co', 'Química')
        assert juliana.cuenta_anterior_id == ids['juliana'] and juliana.activo
        kali = Profesor.objects.get(cedula='333333')
        assert kali.correo == 'kaly@gmail.com'  # se conserva tal cual
        assert Profesor.objects.count() == 2

        # Cada curso conserva su profesor, ahora en profesor_registro.
        assert Curso.objects.count() == 6
        for curso in Curso.objects.all():
            assert curso.profesor_registro.cuenta_anterior_id == curso.profesor_id
        assert set(juliana.cursos.values_list('codigo', flat=True)) == {'JUL-0', 'JUL-1', 'JUL-2'}
        assert set(kali.cursos.values_list('codigo', flat=True)) == {'KAL-0', 'KAL-1', 'KAL-2'}
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0012_descarta_e2e_profesor_y_sus_cursos_sin_borrar_la_cuenta():
    apps = _migrar(ANTES)
    ids = _datos(apps)
    try:
        apps = _migrar(TRAS_0012)
        Curso = apps.get_model('solicitudes', 'Curso')
        assert not Curso.objects.filter(codigo__startswith='E2E-').exists()
        assert not apps.get_model('solicitudes', 'Profesor').objects.filter(cedula='E2E-PROF').exists()
        assert apps.get_model('users', 'Usuario').objects.filter(id=ids['e2e']).exists()
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0012_si_e2e_profesor_tiene_datos_falla_sin_cambiar_nada():
    apps = _migrar(ANTES)
    ids = _datos(apps)
    apps.get_model('reservas', 'Reserva').objects.create(
        usuario_id=ids['e2e'], fecha_reserva=timezone.now(), codigo='R-E2E')
    try:
        with pytest.raises(DatosInvalidos) as error:
            _migrar(TRAS_0012)
        assert '"e2e_profesor" tiene datos asociados (1 reservas)' in str(error.value)
        assert not _aplicada('solicitudes', '0012_docentes_a_profesores')
        assert apps.get_model('solicitudes', 'Curso').objects.count() == 9
        assert apps.get_model('solicitudes', 'Profesor').objects.count() == 0
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0012_curso_con_profesor_invalido_falla_sin_cambiar_nada():
    apps = _migrar(ANTES)
    _datos(apps)
    Usuario = apps.get_model('users', 'Usuario')
    apps.get_model('solicitudes', 'Curso').objects.create(
        nombre='Raro', codigo='RARO-1', profesor=Usuario.objects.get(username='jefe'), cantidad_estudiantes=5)
    try:
        with pytest.raises(DatosInvalidos) as error:
            _migrar(TRAS_0012)
        assert 'RARO-1 (profesor: jefe)' in str(error.value)
        assert 'no se cambió nada' in str(error.value)
        assert not _aplicada('solicitudes', '0012_docentes_a_profesores')
        # Atómica: ni siquiera el descarte de e2e_profesor quedó aplicado.
        Curso = apps.get_model('solicitudes', 'Curso')
        assert Curso.objects.count() == 10
        assert Curso.objects.filter(codigo__startswith='E2E-').count() == 3
        assert apps.get_model('solicitudes', 'Profesor').objects.count() == 0
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0012_docente_sin_cedula_falla_con_mensaje_claro():
    apps = _migrar(ANTES)
    _datos(apps)
    apps.get_model('users', 'Usuario').objects.filter(username='doc_333333').update(codigo=None)
    try:
        with pytest.raises(DatosInvalidos) as error:
            _migrar(TRAS_0012)
        assert 'no tienen cédula' in str(error.value) and 'doc_333333' in str(error.value)
        assert not _aplicada('solicitudes', '0012_docentes_a_profesores')
    finally:
        _limpiar_y_migrar_al_final(apps)


# ── users.0008: quitar el rol Docente ───────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_0008_cuentas_docente_quedan_inactivas_sin_rol_y_sin_borrar():
    apps = _migrar(ANTES)
    ids = _datos(apps)
    try:
        apps = _migrar(TRAS_0008)
        Usuario = apps.get_model('users', 'Usuario')
        for clave in ('juliana', 'kali', 'e2e'):
            cuenta = Usuario.objects.get(id=ids[clave])
            assert cuenta.is_active is False
            assert cuenta.rol_id is None
        assert not apps.get_model('users', 'Rol').objects.filter(nombre='Docente').exists()
        # Nada se borró: la reserva sigue ligada a la cuenta, la cuenta admin intacta.
        assert apps.get_model('reservas', 'Reserva').objects.get(codigo='R-JULIANA').usuario_id == ids['juliana']
        jefe = Usuario.objects.get(username='jefe')
        assert jefe.is_active and jefe.rol.nombre == 'Administrador'
        assert Usuario.objects.count() == 4
    finally:
        _limpiar_y_migrar_al_final(apps)


# ── Reversa ─────────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_reversa_completa_restaura_rol_y_reactiva_las_cuentas():
    apps = _migrar(ANTES)
    ids = _datos(apps)
    try:
        _migrar(TRAS_0008)
        apps = _migrar(INICIO)  # deshace users.0008, 0012, 0011 y 0010
        Usuario = apps.get_model('users', 'Usuario')
        for clave in ('juliana', 'kali'):
            cuenta = Usuario.objects.get(id=ids[clave])
            assert cuenta.is_active is True
            assert cuenta.rol.nombre == 'Docente'
        # La cuenta descartada no tiene Profesor: queda inactiva y sin rol.
        e2e = Usuario.objects.get(id=ids['e2e'])
        assert e2e.is_active is False and e2e.rol_id is None
        # Los cursos convertidos siguen con su cuenta; los de e2e no vuelven.
        Curso = apps.get_model('solicitudes', 'Curso')
        assert Curso.objects.count() == 6
        assert set(Curso.objects.values_list('profesor_id', flat=True)) == {ids['juliana'], ids['kali']}
        assert 'solicitudes_profesor' not in connection.introspection.table_names()
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_reversa_de_0012_vacia_profesor_registro_y_borra_los_profesores_creados():
    apps = _migrar(ANTES)
    _datos(apps)
    try:
        _migrar(TRAS_0012)
        apps = _migrar(ANTES)
        assert apps.get_model('solicitudes', 'Profesor').objects.count() == 0
        assert not apps.get_model('solicitudes', 'Curso').objects.filter(profesor_registro__isnull=False).exists()
    finally:
        _limpiar_y_migrar_al_final(apps)


# ── Restricciones (modelos actuales) ────────────────────────────────────


@pytest.mark.django_db
def test_cedula_de_profesor_es_unica():
    Profesor.objects.create(nombre='Ana', apellido='Ruiz', cedula='123')
    with pytest.raises(IntegrityError), transaction.atomic():
        Profesor.objects.create(nombre='Otra', apellido='Persona', cedula='123')


def _solicitud(estado, cedula='999'):
    return SolicitudRegistroProfesor.objects.create(nombre='Ana', apellido='Ruiz', cedula=cedula, estado=estado)


@pytest.mark.django_db
@pytest.mark.parametrize('anterior, nueva, se_permite', [
    ('rechazada', 'pendiente', True),
    ('rechazada', 'rechazada', True),
    ('pendiente', 'pendiente', False),
    ('aprobada', 'pendiente', False),
    ('pendiente', 'aprobada', False),
])
def test_cedula_de_solicitud_unica_solo_entre_pendientes_y_aprobadas(anterior, nueva, se_permite):
    _solicitud(anterior)
    if se_permite:
        _solicitud(nueva)
        assert SolicitudRegistroProfesor.objects.filter(cedula='999').count() == 2
    else:
        with pytest.raises(IntegrityError), transaction.atomic():
            _solicitud(nueva)


@pytest.mark.django_db
def test_cedula_de_solicitud_repetida_da_mensaje_claro_en_full_clean():
    from django.core.exceptions import ValidationError

    _solicitud('pendiente')
    with pytest.raises(ValidationError) as error:
        SolicitudRegistroProfesor(nombre='Ana', apellido='Ruiz', cedula='999', estado='pendiente').full_clean()
    assert 'Ya existe una solicitud pendiente o aprobada con esta cédula.' in str(error.value)


# ── 0013: quitar el campo viejo Curso.profesor ──────────────────────────

TRAS_0013 = [('solicitudes', '0013_quitar_curso_profesor'), ('users', '0007_email_unico_sin_mayusculas')]
DatosInvalidos0013 = importlib.import_module('solicitudes.migrations.0013_quitar_curso_profesor').DatosInvalidos


def _columnas_curso():
    with connection.cursor() as cursor:
        return {c.name for c in connection.introspection.get_table_description(cursor, 'solicitudes_curso')}


@pytest.mark.django_db
def test_0013_la_base_queda_con_un_solo_campo_de_profesor():
    """Estado final: solicitudes_curso tiene profesor_id (→ Profesor) y ya no
    tiene profesor_registro_id."""
    columnas = _columnas_curso()
    assert 'profesor_id' in columnas
    assert 'profesor_registro_id' not in columnas
    from solicitudes.models import Curso
    campo = Curso._meta.get_field('profesor')
    assert campo.related_model is Profesor and not campo.null


@pytest.mark.django_db(transaction=True)
def test_0013_es_reversible_y_devuelve_la_cuenta_docente_al_campo_viejo():
    apps = _migrar(ANTES)
    ids = _datos(apps)
    try:
        apps = _migrar(TRAS_0013)
        Curso = apps.get_model('solicitudes', 'Curso')
        assert Curso.objects.count() == 6
        assert all(c.profesor.cuenta_anterior_id in (ids['juliana'], ids['kali']) for c in Curso.objects.all())
        assert 'profesor_registro_id' not in _columnas_curso()

        apps = _migrar(TRAS_0012)  # reversa de la 0013
        Curso = apps.get_model('solicitudes', 'Curso')
        assert {'profesor_id', 'profesor_registro_id'} <= _columnas_curso()
        for curso in Curso.objects.select_related('profesor_registro'):
            assert curso.profesor_id == curso.profesor_registro.cuenta_anterior_id
    finally:
        _limpiar_y_migrar_al_final(apps)


@pytest.mark.django_db(transaction=True)
def test_0013_curso_sin_profesor_falla_sin_cambiar_nada():
    apps = _migrar(ANTES)
    _datos(apps)
    try:
        apps = _migrar(TRAS_0012)
        apps.get_model('solicitudes', 'Curso').objects.create(
            nombre='Huérfano', codigo='HUER-1', cantidad_estudiantes=5)
        with pytest.raises(DatosInvalidos0013) as error:
            _migrar(TRAS_0013)
        assert 'HUER-1' in str(error.value) and 'no se cambió nada' in str(error.value)
        assert not _aplicada('solicitudes', '0013_quitar_curso_profesor')
        assert 'profesor_registro_id' in _columnas_curso()
    finally:
        _limpiar_y_migrar_al_final(apps)
