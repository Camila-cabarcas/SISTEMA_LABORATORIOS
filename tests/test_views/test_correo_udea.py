"""
Tests de la regla "solo correos @udea.edu.co" (users/validators.py) en todos
los campos de correo que CREAN datos, y de que las CONSULTAS (Mis Reservas,
detalle y cancelación del dueño) siguen encontrando reservas guardadas con
otro dominio.
"""
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from reservas.models import EstadoReserva, Reserva
from solicitudes.forms import EstudianteSolicitudForm, ProfesorSolicitudForm
from solicitudes.models import SolicitudRegistroProfesor, SolicitudReserva
from solicitudes.services.solicitud_reserva_service import ValidarSolicitudReservaService
from users.fields import CorreoUdeaField
from users.forms import UsuarioForm
from users.models import Rol, Usuario
from users.validators import MENSAJE_CORREO_UDEA, validar_correo_institucional, validar_correo_udea

pytestmark = pytest.mark.django_db

GMAIL = 'persona@gmail.com'
UDEA = 'persona@udea.edu.co'


# ── Validador ─────────────────────────────────────────────────────────────

class TestValidarCorreoUdea:

    @pytest.mark.parametrize('correo', ['x@udea.edu.co', 'X@UDEA.EDU.CO', '  x@udea.edu.co  '])
    def test_acepta(self, correo):
        validar_correo_udea(correo)  # no lanza

    @pytest.mark.parametrize('correo', [
        'x@gmail.com',
        'x@udea.edu.co.evil.com',
        'x@estudiantes.udea.edu.co',
        'x@y@udea.edu.co',
        '@udea.edu.co',
        'xudea.edu.co',
    ])
    def test_rechaza(self, correo):
        with pytest.raises(ValidationError) as e:
            validar_correo_udea(correo)
        assert e.value.messages == [MENSAJE_CORREO_UDEA]

    @pytest.mark.parametrize('vacio', ['', None])
    def test_vacio_lo_decide_required(self, vacio):
        validar_correo_udea(vacio)
        validar_correo_institucional(vacio)

    def test_institucional_tambien_exige_formato_de_correo(self):
        # Para vistas sin formulario de Django: lo que haría EmailField.
        with pytest.raises(ValidationError):
            validar_correo_institucional('mal correo@udea.edu.co')
        validar_correo_institucional(UDEA)

    def test_campo_de_formulario(self):
        campo = CorreoUdeaField()
        assert campo.clean(UDEA) == UDEA
        with pytest.raises(ValidationError):
            campo.clean(GMAIL)


# ── Formularios y vistas que crean datos ──────────────────────────────────

def _datos_estudiante(email, laboratorio):
    return {
        'nombre': 'Ana Torres', 'cedula': '111222333', 'email': email, 'programa': 'Ingeniería de Sistemas',
        'laboratorio': laboratorio.id, 'fecha_reserva': (date.today() + timedelta(days=1)).isoformat(),
        'hora_inicio': '08:00', 'hora_fin': '10:00', 'necesita_modulo': False, 'observaciones': '',
    }


class TestSolicitudEstudiante:

    def test_rechaza_gmail(self, catalogos, laboratorio):
        form = EstudianteSolicitudForm(None, _datos_estudiante(GMAIL, laboratorio))
        assert not form.is_valid()
        assert MENSAJE_CORREO_UDEA in form.errors['email']

    def test_acepta_udea(self, catalogos, laboratorio):
        form = EstudianteSolicitudForm(None, _datos_estudiante(UDEA, laboratorio))
        form.is_valid()
        assert 'email' not in form.errors


class TestSolicitudProfesor:

    def _form(self, email, laboratorio, curso):
        return ProfesorSolicitudForm({
            'nombre': 'Carlos Ramírez', 'cedula': '123456789', 'email': email, 'curso': curso.id,
            'laboratorio': laboratorio.id, 'fecha_reserva': (date.today() + timedelta(days=1)).isoformat(),
            'hora_inicio': '08:00', 'hora_fin': '10:00', 'necesita_modulo': False, 'observaciones': '',
        })

    def test_rechaza_gmail(self, catalogos, laboratorio, curso):
        form = self._form(GMAIL, laboratorio, curso)
        assert not form.is_valid()
        assert MENSAJE_CORREO_UDEA in form.errors['email']

    def test_acepta_udea(self, catalogos, laboratorio, curso):
        form = self._form(UDEA, laboratorio, curso)
        form.is_valid()
        assert 'email' not in form.errors


class TestReservaLibreProfesor:
    """email_libre: la solicitud libre de profesor (sin formulario de Django)."""

    def _datos(self, email, laboratorio):
        return dict(
            nombre='Carlos Ramírez', cedula='123456789', email=email, nombre_grupo='Semillero',
            cantidad_asistentes_str='10', descripcion='Taller', laboratorio_id=str(laboratorio.id),
            fecha_str=(date.today() + timedelta(days=1)).isoformat(), hora_inicio_str='08:00', hora_fin_str='10:00',
        )

    def test_rechaza_gmail(self, laboratorio):
        with pytest.raises(ValidationError) as e:
            ValidarSolicitudReservaService.validar(**self._datos(GMAIL, laboratorio))
        assert MENSAJE_CORREO_UDEA in e.value.messages

    @pytest.mark.parametrize('correo', ['x@y@udea.edu.co', 'x@estudiantes.udea.edu.co'])
    def test_rechaza_variantes_que_el_endswith_viejo_dejaba_pasar_o_no(self, laboratorio, correo):
        with pytest.raises(ValidationError) as e:
            ValidarSolicitudReservaService.validar(**self._datos(correo, laboratorio))
        assert MENSAJE_CORREO_UDEA in e.value.messages

    def test_acepta_udea(self, laboratorio):
        try:
            ValidarSolicitudReservaService.validar(**self._datos(UDEA, laboratorio))
        except ValidationError as e:
            assert MENSAJE_CORREO_UDEA not in e.messages

    def test_vista_muestra_el_error(self, client, catalogos, laboratorio):
        datos = self._datos(GMAIL, laboratorio)
        resp = client.post('/solicitudes/profesor/', {
            'reserva_libre': '1', 'nombre': datos['nombre'], 'cedula': datos['cedula'], 'email': GMAIL,
            'nombre_grupo': 'Semillero', 'cantidad_asistentes': '10', 'descripcion_actividad': 'Taller',
            'laboratorio': laboratorio.id, 'fecha_reserva': datos['fecha_str'],
            'hora_inicio': '08:00', 'hora_fin': '10:00',
        })
        assert resp.status_code == 200
        assert MENSAJE_CORREO_UDEA in resp.context['errores_libres']
        assert not SolicitudReserva.objects.exists()


class TestRegistroProfesor:

    def _post(self, client, correo):
        return client.post('/solicitudes/registro-profesor/', {
            'nombre': 'Pedro', 'apellido': 'Suárez', 'cedula': '321321321', 'correo': correo,
            'programa': 'Ingeniería',
        })

    def test_rechaza_gmail(self, client, catalogos):
        resp = self._post(client, GMAIL)
        assert resp.status_code == 200
        assert MENSAJE_CORREO_UDEA in resp.content.decode()
        assert not SolicitudRegistroProfesor.objects.exists()

    def test_acepta_udea(self, client, catalogos):
        resp = self._post(client, UDEA)
        assert resp.status_code == 302
        assert SolicitudRegistroProfesor.objects.get(cedula='321321321').correo == UDEA


class TestCrearReserva:
    """Formulario de crear reserva (Administrador/Laboratorio), campo email."""

    def _post(self, cliente, email, laboratorio):
        return cliente.post('/reservas/crear/', {
            'tipo_solicitante': 'estudiante', 'nombre': 'Ana Torres', 'cedula': '111222333',
            'programa': 'Ingeniería', 'laboratorio': laboratorio.id,
            'fecha': (date.today() + timedelta(days=1)).isoformat(),
            'hora_inicio': '08:00', 'hora_fin': '10:00', 'email': email,
        })

    def test_rechaza_gmail(self, cliente_autenticado, catalogos, laboratorio):
        resp = self._post(cliente_autenticado, GMAIL, laboratorio)
        assert resp.status_code == 200
        assert MENSAJE_CORREO_UDEA in resp.context['errors']
        assert not SolicitudReserva.objects.exists()

    def test_acepta_udea(self, cliente_autenticado, catalogos, laboratorio):
        resp = self._post(cliente_autenticado, UDEA, laboratorio)
        errores = resp.context['errors'] if resp.status_code == 200 and resp.context else []
        assert MENSAJE_CORREO_UDEA not in errores


class TestLaboratoristas:
    """Cuentas de laboratorista desde Personal (/laboratorio/personal/...):
    el correo UdeA es OBLIGATORIO (antes, con el modelo de personas sin
    cuenta, era opcional)."""

    URL_CREAR = '/laboratorio/personal/laboratoristas/crear/'

    def _datos(self, correo, laboratorio, username='lina_mora'):
        return {'username': username, 'email': correo, 'first_name': 'Lina', 'last_name': 'Mora',
                'laboratorio': laboratorio.id, 'password': 'ClaveInicial123'}

    def test_crear_rechaza_gmail(self, cliente_autenticado, laboratorio):
        resp = cliente_autenticado.post(self.URL_CREAR, self._datos(GMAIL, laboratorio))
        assert resp.status_code == 200
        assert MENSAJE_CORREO_UDEA in resp.context['form'].errors['email']
        assert not Usuario.objects.filter(username='lina_mora').exists()

    def test_crear_acepta_udea(self, cliente_autenticado, laboratorio):
        resp = cliente_autenticado.post(self.URL_CREAR, self._datos(UDEA, laboratorio))
        assert resp.status_code == 302
        assert Usuario.objects.get(username='lina_mora').email == UDEA

    def test_crear_sin_correo_se_rechaza(self, cliente_autenticado, laboratorio):
        resp = cliente_autenticado.post(self.URL_CREAR, self._datos('', laboratorio))
        assert resp.status_code == 200
        assert 'email' in resp.context['form'].errors
        assert not Usuario.objects.filter(username='lina_mora').exists()

    def _cuenta(self, laboratorio, correo):
        cuenta = Usuario.objects.create_user(
            username='lina_mora', password='x', email=correo, first_name='Lina', last_name='Mora',
            rol=Rol.objects.get(nombre='Laboratorista'))
        laboratorio.laboratoristas.add(cuenta)
        return cuenta

    def test_editar_rechaza_gmail_y_no_guarda(self, cliente_autenticado, catalogos, laboratorio):
        cuenta = self._cuenta(laboratorio, UDEA)
        resp = cliente_autenticado.post(f'/laboratorio/personal/laboratoristas/{cuenta.id}/editar/',
                                        self._datos(GMAIL, laboratorio))
        assert resp.status_code == 200
        assert MENSAJE_CORREO_UDEA in resp.context['form'].errors['email']
        cuenta.refresh_from_db()
        assert cuenta.email == UDEA

    def test_editar_acepta_udea(self, cliente_autenticado, catalogos, laboratorio):
        cuenta = self._cuenta(laboratorio, 'lina.vieja@udea.edu.co')
        resp = cliente_autenticado.post(f'/laboratorio/personal/laboratoristas/{cuenta.id}/editar/',
                                        self._datos(UDEA, laboratorio))
        assert resp.status_code == 302
        cuenta.refresh_from_db()
        assert cuenta.email == UDEA


class TestUsuario:

    def test_modelo_rechaza_gmail_en_full_clean(self, catalogos):
        u = Usuario(username='u1', email=GMAIL, codigo='U1')
        with pytest.raises(ValidationError) as e:
            u.full_clean(exclude=['password'])
        assert 'email' in e.value.message_dict

    def test_modelo_acepta_udea_y_vacio(self, catalogos):
        Usuario(username='u1', email=UDEA, codigo='U1').full_clean(exclude=['password'])
        Usuario(username='u2', email='', codigo='U2').full_clean(exclude=['password'])

    @pytest.mark.parametrize('email, valido', [(GMAIL, False), (UDEA, True)])
    def test_formulario_de_usuario(self, catalogos, email, valido):
        # Los ModelForm de Usuario (UsuarioForm, EditarUsuarioForm) heredan el
        # validador del modelo (corre en is_valid); también el admin de Django.
        form = UsuarioForm({'username': 'ana', 'first_name': 'Ana', 'last_name': 'Ríos', 'email': email,
                            'codigo': '444555', 'programa': '', 'password': 'Clave12345',
                            'rol': Rol.objects.get(nombre='Estudiante').id})
        assert form.is_valid() is valido, form.errors
        if not valido:
            assert MENSAJE_CORREO_UDEA in form.errors['email']

    def test_superusuario_sin_correo_sigue_funcionando(self, catalogos):
        call_command('createsuperuser', interactive=False, username='root_sin_correo', email='', verbosity=0)
        root = Usuario.objects.get(username='root_sin_correo')
        assert root.is_superuser and root.email == ''


# ── Consultas: NO se validan (reservas viejas con otro dominio) ──────────

@pytest.fixture
def reserva_vieja_gmail(laboratorio, catalogos):
    """Reserva guardada antes de la regla, con correo @gmail.com."""
    reserva = Reserva.objects.create(
        fecha_reserva=timezone.now() + timedelta(days=3),
        estado=EstadoReserva.objects.get(nombre='Aprobada'),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre='Ana', cedula='555666777', email=GMAIL,
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
    )
    return reserva


class TestConsultasConCorreoViejo:

    def test_mis_reservas_encuentra_reserva_guardada_con_gmail(self, client, reserva_vieja_gmail):
        resp = client.get('/solicitudes/', {'cedula': '555666777', 'email': GMAIL})
        assert resp.status_code == 200
        assert resp.context['error_busqueda'] == ''
        assert [fila['reserva'].id for fila in resp.context['page_obj']] == [reserva_vieja_gmail.id]

    def test_detalle_del_dueno_sigue_funcionando(self, client, reserva_vieja_gmail):
        resp = client.get(f'/reservas/{reserva_vieja_gmail.id}/detalles/', {'cedula': '555666777', 'email': GMAIL})
        assert resp.status_code == 200

    def test_cancelar_del_dueno_reconoce_al_dueno(self, client, reserva_vieja_gmail):
        resp = client.get(f'/reservas/{reserva_vieja_gmail.id}/cancelar/', {'cedula': '555666777', 'email': GMAIL})
        assert resp.status_code != 403
