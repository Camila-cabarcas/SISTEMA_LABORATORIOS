"""
Fase 2, etapa 2 — profesores sin cuenta:
- aprobar / rechazar SolicitudRegistroProfesor (registro_profesor_service):
  crea o reactiva un Profesor, nunca una cuenta; permisos por laboratorio;
  correos de aprobado y rechazado;
- formulario público de registro (sin contraseña, sin cursos, correo UdeA);
- reservas de curso: solo un Profesor ACTIVO, buscado por cédula (formulario
  público y reserva interna), y los límites por profesor calculados por cédula;
- API pública cursos-profesor/ por cédula.
"""
from datetime import date, datetime, time, timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from laboratorio.models import HorarioLaboratorio, Laboratorio
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import Curso, Profesor, SolicitudRegistroProfesor, SolicitudReserva
from solicitudes.services.registro_profesor_service import (
    aprobar_registro_profesor,
    rechazar_registro_profesor,
)
from users.helpers import puede_resolver_solicitud_profesor
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def otro_laboratorio(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')


def _solicitud(cedula='123123123', laboratorio=None, correo='pedro@udea.edu.co', **extra):
    return SolicitudRegistroProfesor.objects.create(
        nombre='Pedro', apellido='Suárez', cedula=cedula, correo=correo,
        programa='Ingeniería', laboratorio_interes=laboratorio, **extra,
    )


# ── Aprobar ─────────────────────────────────────────────────────────────

class TestAprobar:

    def test_crea_profesor_sin_cuenta(self, usuario_admin, django_capture_on_commit_callbacks):
        usuarios_antes = Usuario.objects.count()
        solicitud = _solicitud()
        with django_capture_on_commit_callbacks(execute=True):
            solicitud = aprobar_registro_profesor(solicitud, usuario_admin)

        profesor = Profesor.objects.get(cedula='123123123')
        assert (profesor.nombre, profesor.apellido, profesor.correo, profesor.programa) == (
            'Pedro', 'Suárez', 'pedro@udea.edu.co', 'Ingeniería')
        assert profesor.activo and profesor.solicitud_origen == solicitud
        assert profesor.cuenta_anterior is None
        # Sin cuenta y sin contraseña.
        assert Usuario.objects.count() == usuarios_antes
        assert solicitud.usuario_creado is None
        assert not Usuario.objects.filter(codigo='123123123').exists()

    def test_marca_estado_quien_y_cuando(self, usuario_admin):
        solicitud = aprobar_registro_profesor(_solicitud(), usuario_admin)
        solicitud.refresh_from_db()
        assert solicitud.estado == 'aprobada'
        assert solicitud.profesor.cedula == '123123123'
        assert solicitud.resuelto_por == usuario_admin
        assert solicitud.fecha_resolucion is not None

    def test_misma_cedula_reactiva_y_no_duplica(self, usuario_admin):
        existente = Profesor.objects.create(nombre='Viejo', apellido='Nombre', cedula='123123123',
                                            correo='viejo@gmail.com', activo=False)
        solicitud = aprobar_registro_profesor(_solicitud(), usuario_admin)

        assert Profesor.objects.filter(cedula='123123123').count() == 1
        existente.refresh_from_db()
        assert existente.activo
        assert (existente.nombre, existente.correo) == ('Pedro', 'pedro@udea.edu.co')
        assert solicitud.profesor == existente

    def test_aprobar_dos_veces_la_misma_solicitud_falla(self, usuario_admin):
        solicitud = aprobar_registro_profesor(_solicitud(), usuario_admin)
        with pytest.raises(ValidationError):
            aprobar_registro_profesor(solicitud, usuario_admin)


# ── Rechazar ────────────────────────────────────────────────────────────

class TestRechazar:

    def test_guarda_motivo_quien_y_cuando_sin_crear_profesor(self, usuario_admin):
        solicitud = rechazar_registro_profesor(_solicitud(), usuario_admin, '  Cédula no coincide.  ')
        solicitud.refresh_from_db()
        assert solicitud.estado == 'rechazada'
        assert solicitud.motivo_rechazo == 'Cédula no coincide.'
        assert solicitud.resuelto_por == usuario_admin
        assert solicitud.fecha_resolucion is not None
        assert solicitud.profesor is None
        assert not Profesor.objects.exists()

    def test_tras_rechazo_la_cedula_puede_volver_a_solicitar(self, usuario_admin):
        rechazar_registro_profesor(_solicitud(), usuario_admin, 'x')
        nueva = _solicitud()  # la restricción solo cuenta pendientes/aprobadas
        assert nueva.estado == 'pendiente'


# ── Permisos ────────────────────────────────────────────────────────────

class TestPermisos:

    def test_laboratorista_aprueba_las_de_su_laboratorio(self, usuario_laboratorista, laboratorio):
        solicitud = aprobar_registro_profesor(_solicitud(laboratorio=laboratorio), usuario_laboratorista)
        assert solicitud.estado == 'aprobada'

    def test_laboratorista_aprueba_las_sin_laboratorio(self, usuario_laboratorista):
        solicitud = aprobar_registro_profesor(_solicitud(laboratorio=None), usuario_laboratorista)
        assert solicitud.estado == 'aprobada'

    def test_laboratorista_no_resuelve_las_de_otro_laboratorio(self, usuario_laboratorista, otro_laboratorio):
        solicitud = _solicitud(laboratorio=otro_laboratorio)
        with pytest.raises(PermissionDenied):
            aprobar_registro_profesor(solicitud, usuario_laboratorista)
        with pytest.raises(PermissionDenied):
            rechazar_registro_profesor(solicitud, usuario_laboratorista, 'x')
        solicitud.refresh_from_db()
        assert solicitud.estado == 'pendiente'
        assert not Profesor.objects.exists()

    @pytest.mark.parametrize('fixture', ['usuario_monitor', 'usuario_estudiante'])
    def test_monitor_y_otros_roles_no_pueden(self, request, fixture, laboratorio):
        actor = request.getfixturevalue(fixture)
        for solicitud in (_solicitud('1', laboratorio=laboratorio), _solicitud('2', laboratorio=None)):
            assert not puede_resolver_solicitud_profesor(actor, solicitud)
            with pytest.raises(PermissionDenied):
                aprobar_registro_profesor(solicitud, actor)

    def test_administrador_resuelve_todas(self, usuario_admin, otro_laboratorio):
        assert puede_resolver_solicitud_profesor(usuario_admin, _solicitud('1', laboratorio=otro_laboratorio))
        assert puede_resolver_solicitud_profesor(usuario_admin, _solicitud('2'))

    def test_lista_del_laboratorista_filtra_por_laboratorio(
            self, client, usuario_laboratorista, laboratorio, otro_laboratorio):
        propia = _solicitud('1', laboratorio=laboratorio)
        sin_lab = _solicitud('2')
        _solicitud('3', laboratorio=otro_laboratorio)
        client.force_login(usuario_laboratorista)
        respuesta = client.get(reverse('lista_solicitudes_profesores'))
        assert respuesta.status_code == 200
        assert set(respuesta.context['solicitudes']) == {propia, sin_lab}

    def test_detalle_de_otro_laboratorio_da_403(self, client, usuario_laboratorista, otro_laboratorio):
        ajena = _solicitud(laboratorio=otro_laboratorio)
        client.force_login(usuario_laboratorista)
        url = reverse('detalle_solicitud_profesor', args=[ajena.id])
        assert client.get(url).status_code == 403
        assert client.post(url, {'accion': 'aprobar_profesor'}).status_code == 403
        ajena.refresh_from_db()
        assert ajena.estado == 'pendiente'

    def test_vista_rechazar_guarda_motivo(self, client, usuario_laboratorista, laboratorio):
        solicitud = _solicitud(laboratorio=laboratorio)
        client.force_login(usuario_laboratorista)
        client.post(reverse('detalle_solicitud_profesor', args=[solicitud.id]),
                    {'accion': 'rechazar_profesor', 'motivo': 'Datos incompletos'})
        solicitud.refresh_from_db()
        assert (solicitud.estado, solicitud.motivo_rechazo) == ('rechazada', 'Datos incompletos')
        assert solicitud.resuelto_por == usuario_laboratorista


# ── Correos ─────────────────────────────────────────────────────────────

class TestCorreos:

    def test_al_aprobar_se_avisa_al_profesor(self, usuario_admin, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            aprobar_registro_profesor(_solicitud(), usuario_admin)
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ['pedro@udea.edu.co']
        assert 'aprobado' in mail.outbox[0].subject

    def test_al_rechazar_se_avisa_con_el_motivo(self, usuario_admin, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            rechazar_registro_profesor(_solicitud(), usuario_admin, 'Cédula no coincide')
        assert len(mail.outbox) == 1
        assert 'rechazada' in mail.outbox[0].subject
        assert 'Cédula no coincide' in mail.outbox[0].alternatives[0][0]

    def test_sin_correo_no_se_manda(self, usuario_admin, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            aprobar_registro_profesor(_solicitud('1', correo=''), usuario_admin)
            rechazar_registro_profesor(_solicitud('2', correo=''), usuario_admin, 'x')
        assert mail.outbox == []

    def test_un_error_de_correo_no_interrumpe(self, usuario_admin, monkeypatch, django_capture_on_commit_callbacks):
        def falla(*args, **kwargs):
            raise RuntimeError('SendGrid caído')
        monkeypatch.setattr('utils.notificaciones_email.enviar_email_html', falla)

        with django_capture_on_commit_callbacks(execute=True):
            aprobada = aprobar_registro_profesor(_solicitud('1'), usuario_admin)
            rechazada = rechazar_registro_profesor(_solicitud('2'), usuario_admin, 'x')

        aprobada.refresh_from_db()
        rechazada.refresh_from_db()
        assert aprobada.estado == 'aprobada' and Profesor.objects.filter(cedula='1').exists()
        assert rechazada.estado == 'rechazada'


# ── Formulario público de registro ──────────────────────────────────────

class TestFormularioPublico:
    URL = '/solicitudes/registro-profesor/'

    def _datos(self, **extra):
        return {'nombre': 'Pedro', 'apellido': 'Suárez', 'cedula': '321321321',
                'correo': 'pedro@udea.edu.co', 'programa': '', **extra}

    def test_no_pide_contrasena_ni_cursos(self, client):
        respuesta = client.post(self.URL, self._datos())
        assert respuesta.status_code == 302
        solicitud = SolicitudRegistroProfesor.objects.get(cedula='321321321')
        assert solicitud.estado == 'pendiente'
        assert solicitud.cursos_solicitados.count() == 0
        assert 'type="password"' not in client.get(self.URL).content.decode()

    def test_exige_correo_udea(self, client):
        respuesta = client.post(self.URL, self._datos(correo='pedro@gmail.com'))
        assert respuesta.status_code == 200
        assert any('@udea.edu.co' in e for e in respuesta.context['errores'])
        assert not SolicitudRegistroProfesor.objects.exists()

    def test_exige_correo(self, client):
        respuesta = client.post(self.URL, self._datos(correo=''))
        assert 'El correo institucional es requerido.' in respuesta.context['errores']

    def test_laboratorio_de_interes_opcional(self, client, laboratorio):
        client.post(self.URL, self._datos(laboratorio_interes=laboratorio.id))
        assert SolicitudRegistroProfesor.objects.get().laboratorio_interes == laboratorio


# ── Reservas de curso por cédula ────────────────────────────────────────

@pytest.fixture
def profesor_con_curso(db):
    profesor = Profesor.objects.create(nombre='Carlos', apellido='Ramirez', cedula='999888777',
                                       correo='carlos@udea.edu.co')
    curso = Curso.objects.create(nombre='Física General', codigo='FIS-101',
                                 profesor=profesor, cantidad_estudiantes=20)
    return profesor, curso


def _post_reserva_interna(cliente, laboratorio, cedula, curso=None, **extra):
    datos = {
        'tipo_solicitante': 'profesor', 'nombre': 'Carlos Ramirez', 'cedula': cedula,
        'curso': curso.id if curso else '', 'laboratorio': laboratorio.id,
        'fecha': (date.today() + timedelta(days=2)).isoformat(),
        'hora_inicio': '08:00', 'hora_fin': '10:00', 'observaciones': '', 'email': '',
    }
    datos.update(extra)
    return cliente.post('/reservas/crear/', datos)


class TestReservaInterna:

    def test_profesor_activo_por_cedula(self, cliente_autenticado, laboratorio, profesor_con_curso):
        _, curso = profesor_con_curso
        respuesta = _post_reserva_interna(cliente_autenticado, laboratorio, '999888777', curso)
        assert respuesta.status_code == 302
        solicitud = SolicitudReserva.objects.get(cedula='999888777')
        assert solicitud.usuario_id is None  # sin cuenta

    def test_profesor_inactivo_no(self, cliente_autenticado, laboratorio, profesor_con_curso):
        profesor, curso = profesor_con_curso
        profesor.activo = False
        profesor.save()
        respuesta = _post_reserva_interna(cliente_autenticado, laboratorio, '999888777', curso)
        assert respuesta.status_code == 200
        assert 'no está activo' in respuesta.content.decode()
        assert not SolicitudReserva.objects.exists()

    def test_cedula_no_registrada_no(self, cliente_autenticado, laboratorio, profesor_con_curso):
        respuesta = _post_reserva_interna(cliente_autenticado, laboratorio, '111000111')
        assert 'No hay un profesor habilitado' in respuesta.content.decode()
        assert not SolicitudReserva.objects.exists()

    def test_invitado_no_necesita_estar_registrado(self, cliente_autenticado, laboratorio):
        respuesta = _post_reserva_interna(cliente_autenticado, laboratorio, '444555666', profesor_invitado='1')
        assert respuesta.status_code == 302
        assert SolicitudReserva.objects.get(cedula='444555666').reserva_libre

    def test_cuenta_docente_vieja_no_se_liga_a_la_reserva(self, cliente_autenticado, laboratorio,
                                                         profesor_con_curso, catalogos):
        # Tras users.0008 las cuentas Docente quedan inactivas con codigo = cédula.
        viejo = Usuario.objects.create_user(username='doc_999888777', password='x', codigo='999888777',
                                            is_active=False)
        _, curso = profesor_con_curso
        _post_reserva_interna(cliente_autenticado, laboratorio, '999888777', curso)
        solicitud = SolicitudReserva.objects.get(cedula='999888777')
        assert solicitud.usuario_id is None
        # La reserva interna se liga a quien la crea (el operador), nunca a la cuenta vieja.
        assert solicitud.reserva is not None and solicitud.reserva.usuario_id != viejo.id


# ── Límites por profesor, por cédula ────────────────────────────────────

class TestLimitesPorCedula:

    def _solicitud_aprobada(self, laboratorio, cedula, dias):
        estado = EstadoReserva.objects.get(nombre='Aprobada')
        inicio = datetime.combine(date.today() + timedelta(days=dias), time(8))  # USE_TZ=False
        reserva = Reserva.objects.create(fecha_reserva=inicio, fecha_devolucion=inicio + timedelta(hours=2),
                                         estado=estado)
        return SolicitudReserva.objects.create(
            tipo_solicitante='profesor', nombre='Carlos', cedula=cedula, laboratorio=laboratorio,
            fecha_reserva=inicio, hora_inicio=time(8), hora_fin=time(10), reserva=reserva,
        )

    def test_maximo_dos_aprobadas_por_cedula(self, laboratorio, catalogos):
        self._solicitud_aprobada(laboratorio, '999888777', 3)
        self._solicitud_aprobada(laboratorio, '999888777', 4)
        nueva = SolicitudReserva(tipo_solicitante='profesor', nombre='Carlos', cedula='999888777',
                                 laboratorio=laboratorio)
        otra_cedula = SolicitudReserva(tipo_solicitante='profesor', nombre='Otro', cedula='111',
                                       laboratorio=laboratorio)
        assert nueva.limite_pendientes_alcanzado()
        assert not otra_cedula.limite_pendientes_alcanzado()

    def test_choque_mismo_dia_mismo_laboratorio_por_cedula(self, laboratorio, profesor_con_curso, catalogos):
        _, curso = profesor_con_curso
        previa = self._solicitud_aprobada(laboratorio, '999888777', 3)
        previa.curso = curso
        previa.save()
        nueva = SolicitudReserva.objects.create(
            tipo_solicitante='profesor', nombre='Carlos', cedula='999888777', curso=curso,
            laboratorio=laboratorio, fecha_reserva=previa.fecha_reserva, hora_inicio=time(14), hora_fin=time(16),
        )
        with pytest.raises(ValidationError) as error:
            nueva.crear_reserva()
        assert 'Solo puedes hacer 1 reserva por día' in str(error.value)


# ── Correo de la reserva de curso ───────────────────────────────────────

def test_reserva_de_curso_sin_correo_avisa_al_correo_del_profesor(laboratorio, profesor_con_curso, catalogos):
    from utils.notificaciones_email import _email_y_nombre

    _, curso = profesor_con_curso
    solicitud = SolicitudReserva(tipo_solicitante='profesor', nombre='', cedula='999888777',
                                 email='', curso=curso, laboratorio=laboratorio)
    assert _email_y_nombre(solicitud) == ('carlos@udea.edu.co', 'Carlos Ramirez')


# ── API pública cursos-profesor/ ────────────────────────────────────────

class TestApiCursosProfesor:
    URL = '/solicitudes/cursos-profesor/'

    def test_devuelve_los_cursos_del_profesor_por_cedula(self, client, profesor_con_curso):
        _, curso = profesor_con_curso
        Curso.objects.create(nombre='Otro', codigo='OTRO-1', cantidad_estudiantes=5,
                             profesor=Profesor.objects.create(nombre='X', apellido='Y', cedula='5'))
        datos = client.get(self.URL, {'cedula': '999888777'}).json()
        assert [c['codigo'] for c in datos['cursos']] == ['FIS-101']
        assert datos['profesor'] == 'Carlos Ramirez'

    def test_inactivo_no_devuelve_cursos(self, client, profesor_con_curso):
        profesor, _ = profesor_con_curso
        profesor.activo = False
        profesor.save()
        datos = client.get(self.URL, {'cedula': '999888777'}).json()
        assert datos['cursos'] == [] and 'no está activo' in datos['error']

    def test_ya_no_busca_por_nombre(self, client, profesor_con_curso):
        datos = client.get(self.URL, {'nombre': 'Carlos Ramirez'}).json()
        assert datos['cursos'] == []
        assert 'cédula' in datos['error']


# ── Seed de pruebas de carga ────────────────────────────────────────────

def test_seed_locust_crea_profesor_de_prueba_con_curso(catalogos):
    from io import StringIO

    from django.core.management import call_command

    call_command('seed_locust', stdout=StringIO())
    profesor = Profesor.objects.get(cedula='900000001')
    assert profesor.activo
    assert list(profesor.cursos.values_list('codigo', flat=True)) == ['CURSO-E2E-101']
    assert not Rol.objects.filter(nombre='Docente', usuario__isnull=False).exists()
    assert not Usuario.objects.filter(username='e2e_profesor').exists()
