"""
Fase 1 — login por usuario o correo y unicidad de cuentas:
- users.backends.UsuarioOCorreoBackend + users.forms.LoginForm
- Usuario.email único sin distinguir mayúsculas cuando no está vacío
  (UniqueConstraint condicional sobre Lower('email'))
- Usuario.codigo NULL en vez de '' (varios usuarios sin código)
"""
import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from users.forms import EditarUsuarioForm, LoginForm, UsuarioForm
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db

CLAVE = 'clave12345'


@pytest.fixture
def cuenta_con_correo(catalogos):
    return Usuario.objects.create_user(
        username='est_100', password=CLAVE, email='ana.perez@udea.edu.co',
        rol=Rol.objects.get(nombre='Estudiante'), codigo='100',
    )


def _login(client, identificador, clave=CLAVE):
    return client.post(reverse('login'), {'username': identificador, 'password': clave})


def _autenticado(client):
    return '_auth_user_id' in client.session


# ── Login ───────────────────────────────────────────────────────────────

class TestLogin:

    def test_etiqueta_del_campo(self, client):
        assert LoginForm().fields['username'].label == 'Usuario o correo'
        respuesta = client.get(reverse('login'))
        assert 'Usuario o correo' in respuesta.content.decode()

    def test_login_con_usuario_sigue_funcionando(self, client, usuario_admin):
        respuesta = _login(client, 'admin_test')
        assert respuesta.status_code == 302
        assert _autenticado(client)
        assert int(client.session['_auth_user_id']) == usuario_admin.id

    def test_login_con_correo(self, client, cuenta_con_correo):
        respuesta = _login(client, 'ana.perez@udea.edu.co')
        assert respuesta.status_code == 302
        assert int(client.session['_auth_user_id']) == cuenta_con_correo.id

    def test_login_con_correo_en_mayusculas(self, client, cuenta_con_correo):
        respuesta = _login(client, '  ANA.Perez@UdeA.edu.co ')
        assert respuesta.status_code == 302
        assert int(client.session['_auth_user_id']) == cuenta_con_correo.id

    def test_clave_incorrecta_con_usuario_no_entra(self, client, usuario_admin):
        respuesta = _login(client, 'admin_test', 'otra-clave')
        assert respuesta.status_code == 200
        assert not _autenticado(client)
        assert 'Usuario/correo o contraseña incorrectos.' in respuesta.content.decode()

    def test_clave_incorrecta_con_correo_no_entra(self, client, cuenta_con_correo):
        respuesta = _login(client, 'ana.perez@udea.edu.co', 'otra-clave')
        assert respuesta.status_code == 200
        assert not _autenticado(client)

    def test_correo_inexistente_no_entra(self, client, cuenta_con_correo):
        assert _login(client, 'nadie@udea.edu.co').status_code == 200
        assert not _autenticado(client)

    def test_usuario_inactivo_no_entra_con_correo(self, client, cuenta_con_correo):
        cuenta_con_correo.is_active = False
        cuenta_con_correo.save()
        assert _login(client, 'ana.perez@udea.edu.co').status_code == 200
        assert not _autenticado(client)

    def test_correo_de_una_cuenta_no_entra_con_clave_de_otra(self, client, usuario_admin, cuenta_con_correo):
        # La clave de admin_test no abre la cuenta del cuenta_con_correo.
        cuenta_con_correo.set_password('clave-del-cuenta_con_correo')
        cuenta_con_correo.save()
        assert _login(client, 'ana.perez@udea.edu.co', CLAVE).status_code == 200
        assert not _autenticado(client)


# ── Correo único ────────────────────────────────────────────────────────

class TestCorreoUnico:

    def _datos_usuario(self, **extra):
        datos = {
            'username': 'nuevo', 'first_name': 'Nuevo', 'last_name': 'Usuario',
            'email': 'ana.perez@udea.edu.co', 'codigo': '', 'programa': '',
            'rol': Rol.objects.get(nombre='Estudiante').id, 'password': CLAVE,
        }
        datos.update(extra)
        return datos

    def test_usuario_form_rechaza_correo_repetido(self, cuenta_con_correo):
        form = UsuarioForm(data=self._datos_usuario())
        assert not form.is_valid()
        assert 'Ya existe una cuenta con ese correo electrónico.' in form.non_field_errors()

    def test_editar_usuario_form_rechaza_correo_de_otro(self, cuenta_con_correo, usuario_estudiante):
        form = EditarUsuarioForm(
            data={'first_name': 'E', 'last_name': 'T', 'email': 'ana.perez@udea.edu.co',
                  'codigo': '', 'programa': '', 'rol': usuario_estudiante.rol_id},
            instance=usuario_estudiante,
        )
        assert not form.is_valid()
        assert 'Ya existe una cuenta con ese correo electrónico.' in form.non_field_errors()

    def test_editar_usuario_conserva_su_propio_correo(self, cuenta_con_correo):
        form = EditarUsuarioForm(
            data={'first_name': 'Ana', 'last_name': 'Pérez', 'email': 'ana.perez@udea.edu.co',
                  'codigo': '100', 'programa': '', 'rol': cuenta_con_correo.rol_id},
            instance=cuenta_con_correo,
        )
        assert form.is_valid(), form.errors

    def test_vista_crear_usuario_muestra_error_sin_500(self, client, usuario_admin, cuenta_con_correo):
        client.force_login(usuario_admin)
        respuesta = client.post(reverse('crear_usuario'), self._datos_usuario())
        assert respuesta.status_code == 200
        assert 'Ya existe una cuenta con ese correo electrónico.' in respuesta.content.decode()
        assert not Usuario.objects.filter(username='nuevo').exists()

    def test_varios_usuarios_sin_correo_conviven(self, catalogos):
        Usuario.objects.create_user(username='a', password=CLAVE)
        Usuario.objects.create_user(username='b', password=CLAVE)
        assert Usuario.objects.filter(email='').count() == 2


class TestCorreoUnicoSinMayusculas:
    """El correo es único sin distinguir mayúsculas (Lower('email'))."""

    MENSAJE = 'Ya existe una cuenta con ese correo electrónico.'

    def test_base_de_datos_rechaza_mismo_correo_en_otras_mayusculas(self, catalogos):
        Usuario.objects.create_user(username='ana1', password=CLAVE, email='Ana@udea.edu.co')
        with pytest.raises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user(username='ana2', password=CLAVE, email='ana@udea.edu.co')
        assert Usuario.objects.filter(email__iexact='ana@udea.edu.co').count() == 1

    def test_usuario_form_rechaza_mismo_correo_en_otras_mayusculas(self, catalogos):
        Usuario.objects.create_user(username='ana1', password=CLAVE, email='Ana@udea.edu.co')
        form = UsuarioForm(data={
            'username': 'ana2', 'first_name': 'Ana', 'last_name': 'Dos',
            'email': 'ana@udea.edu.co', 'codigo': '', 'programa': '',
            'rol': Rol.objects.get(nombre='Estudiante').id, 'password': CLAVE,
        })
        assert not form.is_valid()
        assert self.MENSAJE in form.non_field_errors()

    def test_editar_usuario_form_rechaza_correo_de_otro_en_otras_mayusculas(
            self, cuenta_con_correo, usuario_estudiante):
        form = EditarUsuarioForm(
            data={'first_name': 'E', 'last_name': 'T', 'email': 'ANA.PEREZ@udea.edu.co',
                  'codigo': '', 'programa': '', 'rol': usuario_estudiante.rol_id},
            instance=usuario_estudiante,
        )
        assert not form.is_valid()
        assert self.MENSAJE in form.non_field_errors()

    def test_editar_usuario_puede_cambiar_mayusculas_de_su_propio_correo(self, cuenta_con_correo):
        form = EditarUsuarioForm(
            data={'first_name': 'Ana', 'last_name': 'Pérez', 'email': 'Ana.Perez@udea.edu.co',
                  'codigo': '100', 'programa': '', 'rol': cuenta_con_correo.rol_id},
            instance=cuenta_con_correo,
        )
        assert form.is_valid(), form.errors

    def test_vista_crear_usuario_muestra_error_sin_500(self, client, usuario_admin, cuenta_con_correo):
        client.force_login(usuario_admin)
        respuesta = client.post(reverse('crear_usuario'), {
            'username': 'ana2', 'first_name': 'Ana', 'last_name': 'Dos',
            'email': 'Ana.Perez@UDEA.edu.co', 'codigo': '', 'programa': '',
            'rol': Rol.objects.get(nombre='Estudiante').id, 'password': CLAVE,
        })
        assert respuesta.status_code == 200
        assert self.MENSAJE in respuesta.content.decode()
        assert not Usuario.objects.filter(username='ana2').exists()

    def test_login_con_correo_guardado_en_mayusculas(self, client, catalogos):
        ana = Usuario.objects.create_user(username='ana1', password=CLAVE, email='Ana@udea.edu.co')
        respuesta = _login(client, 'ana@UDEA.edu.co')
        assert respuesta.status_code == 302
        assert int(client.session['_auth_user_id']) == ana.id

    def test_dos_usuarios_con_correo_vacio_por_formulario(self, client, usuario_admin):
        client.force_login(usuario_admin)
        rol = Rol.objects.get(nombre='Estudiante').id
        for username, codigo in (('vacio_1', 'V1'), ('vacio_2', 'V2')):
            respuesta = client.post(reverse('crear_usuario'), {
                'username': username, 'first_name': 'X', 'last_name': 'Y',
                'email': '', 'codigo': codigo, 'programa': '', 'rol': rol, 'password': CLAVE,
            })
            assert respuesta.status_code == 302, respuesta.content.decode()[:500]
        assert Usuario.objects.filter(username__startswith='vacio_', email='').count() == 2


# ── Código vacío → NULL ─────────────────────────────────────────────────

class TestCodigoVacio:

    def test_dos_usuarios_sin_codigo_con_create_user(self, catalogos):
        a = Usuario.objects.create_user(username='a', password=CLAVE)
        b = Usuario.objects.create_user(username='b', password=CLAVE, codigo='')
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.codigo is None
        assert b.codigo is None

    def test_dos_usuarios_sin_codigo_con_el_formulario(self, client, usuario_admin):
        client.force_login(usuario_admin)
        rol = Rol.objects.get(nombre='Estudiante').id
        for username in ('sin_codigo_1', 'sin_codigo_2'):
            respuesta = client.post(reverse('crear_usuario'), {
                'username': username, 'first_name': 'X', 'last_name': 'Y',
                'email': '', 'codigo': '', 'programa': '', 'rol': rol, 'password': CLAVE,
            })
            assert respuesta.status_code == 302, respuesta.content.decode()[:500]
        codigos = list(Usuario.objects.filter(username__startswith='sin_codigo_')
                       .values_list('codigo', flat=True))
        assert codigos == [None, None]

    def test_lista_usuarios_no_muestra_none(self, client, usuario_admin):
        client.force_login(usuario_admin)
        contenido = client.get(reverse('lista_usuarios')).content.decode()
        assert '<td>None</td>' not in contenido
