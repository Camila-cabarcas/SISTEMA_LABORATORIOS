"""
Vistas de la sección Personal (laboratorio/views_personal.py): lo que pasa
al usar cada pantalla, los mensajes de error del servicio (sin 500), las URLs
viejas eliminadas, el menú por rol y el admin de Usuarios.
La matriz de permisos completa está en test_matriz_personal.py.
"""
import pytest
from django.contrib import admin
from django.urls import reverse

from laboratorio.models import AsignacionMonitor, FichaMonitor, Laboratorio
from prestamos.models import Prestamo
from reservas.models import Reserva
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db

CLAVE_ADMIN = 'ClaveAdmin!123'
CLAVE = 'ClaveInicial123'


@pytest.fixture
def lab_b(db):
    return Laboratorio.objects.create(nombre='Laboratorio B', ubicacion='Bloque B')


@pytest.fixture
def admin_cliente(client, usuario_admin):
    usuario_admin.set_admin_password(CLAVE_ADMIN)
    client.force_login(usuario_admin)
    return client


@pytest.fixture
def lab_cliente(client, usuario_laboratorista):
    client.force_login(usuario_laboratorista)
    return client


def _cuenta_laboratorista(laboratorio, username='lina', email='lina@udea.edu.co'):
    cuenta = Usuario.objects.create_user(
        username=username, password=CLAVE, email=email, first_name='Lina', last_name='Mora',
        rol=Rol.objects.get(nombre='Laboratorista'))
    laboratorio.laboratoristas.add(cuenta)
    return cuenta


def _ficha(laboratorio, nombre='Ana'):
    ficha = FichaMonitor.objects.create(nombre=nombre, apellido='Ruiz')
    ficha.laboratorios.add(laboratorio)
    return ficha


def _mensajes(respuesta):
    return [str(m) for m in respuesta.context['messages']] if respuesta.context else []


# ── URLs eliminadas ─────────────────────────────────────────────────────

@pytest.mark.parametrize('ruta', [
    '/laboratorio/laboratoristas/',
    '/laboratorio/laboratoristas/crear/',
    '/laboratorio/laboratoristas/1/',
    '/laboratorio/laboratoristas/1/editar/',
    '/laboratorio/laboratoristas/1/eliminar/',
    '/laboratorio/laboratoristas/1/toggle/',
    '/laboratorio/laboratoristas/1/toggle-tipo/',
    '/laboratorio/{lab}/encargados/',
    '/laboratorio/{lab}/laboratoristas/',
    '/laboratorio/{lab}/tiene-encargado/',
])
def test_urls_viejas_dan_404(admin_cliente, laboratorio, ruta):
    assert admin_cliente.get(ruta.format(lab=laboratorio.id)).status_code == 404


def test_tiene_encargado_api_ya_no_responde_sin_login(client, laboratorio):
    assert client.get(f'/laboratorio/{laboratorio.id}/tiene-encargado/').status_code == 404


# ── Lista ───────────────────────────────────────────────────────────────

class TestLista:

    def test_admin_ve_todos_los_laboratorios_con_su_personal(self, admin_cliente, laboratorio, lab_b):
        _cuenta_laboratorista(lab_b, 'lab_b', 'lab.b@udea.edu.co')
        _ficha(laboratorio, 'Ana')
        contenido = admin_cliente.get(reverse('personal')).content.decode()
        assert 'Laboratorio B' in contenido and laboratorio.nombre in contenido
        assert 'lab_b' in contenido
        assert 'Ana Ruiz' in contenido
        assert contenido.count('Este laboratorio no tiene cuenta de monitor.') == 2

    def test_laboratorista_solo_ve_su_laboratorio(self, lab_cliente, laboratorio, lab_b):
        _ficha(laboratorio, 'Ana')
        _ficha(lab_b, 'Beto')
        contenido = lab_cliente.get(reverse('personal')).content.decode()
        assert laboratorio.nombre in contenido
        assert 'Laboratorio B' not in contenido
        assert 'Ana Ruiz' in contenido
        assert 'Beto Ruiz' not in contenido
        # Sin acciones sobre cuentas.
        assert '/laboratorio/personal/laboratoristas/crear/' not in contenido
        assert '/laboratorio/personal/monitores/crear/' not in contenido

    def test_aviso_de_cuentas_activas_sin_laboratorio(self, admin_cliente, catalogos):
        Usuario.objects.create_user(username='huerfana', password='x', rol=Rol.objects.get(nombre='Laboratorista'))
        contenido = admin_cliente.get(reverse('personal')).content.decode()
        assert 'id="avisos-personal"' in contenido
        assert 'huerfana' in contenido

    def test_sin_avisos_si_todo_esta_bien(self, admin_cliente, usuario_laboratorista):
        assert 'id="avisos-personal"' not in admin_cliente.get(reverse('personal')).content.decode()


# ── Crear y editar laboratorista ────────────────────────────────────────

class TestCrearLaboratorista:

    def _datos(self, laboratorio, **extra):
        return {'username': 'lina', 'email': 'lina@udea.edu.co', 'first_name': 'Lina', 'last_name': 'Mora',
                'laboratorio': laboratorio.id, 'password': CLAVE, **extra}

    def test_queda_con_un_laboratorio_y_correo_udea(self, admin_cliente, laboratorio):
        respuesta = admin_cliente.post(reverse('crear_laboratorista'), self._datos(laboratorio))
        assert respuesta.status_code == 302
        cuenta = Usuario.objects.get(username='lina')
        assert cuenta.email == 'lina@udea.edu.co'
        assert cuenta.rol.nombre == 'Laboratorista' and cuenta.is_active
        assert list(cuenta.laboratorios_asignados.all()) == [laboratorio]

    def test_el_laboratorista_no_puede_crearla(self, lab_cliente, laboratorio):
        respuesta = lab_cliente.post(reverse('crear_laboratorista'), self._datos(laboratorio))
        assert respuesta.status_code == 403
        assert 'Solo el Administrador' in respuesta.content.decode()
        assert not Usuario.objects.filter(username='lina').exists()

    def test_errores_del_servicio_se_muestran_en_el_formulario(self, admin_cliente, laboratorio):
        _cuenta_laboratorista(laboratorio)
        respuesta = admin_cliente.post(reverse('crear_laboratorista'),
                                       self._datos(laboratorio, username='otra', email='LINA@udea.edu.co'))
        assert respuesta.status_code == 200
        assert 'Ya existe una cuenta con ese correo electrónico.' in respuesta.content.decode()

    def test_sin_laboratorio_no_crea(self, admin_cliente, laboratorio):
        datos = self._datos(laboratorio)
        datos['laboratorio'] = ''
        respuesta = admin_cliente.post(reverse('crear_laboratorista'), datos)
        assert respuesta.status_code == 200
        assert 'laboratorio' in respuesta.context['form'].errors
        assert not Usuario.objects.filter(username='lina').exists()

    def test_editar_cambia_de_laboratorio(self, admin_cliente, laboratorio, lab_b):
        cuenta = _cuenta_laboratorista(laboratorio)
        respuesta = admin_cliente.post(reverse('editar_laboratorista', args=[cuenta.id]), {
            'username': 'lina', 'email': 'lina@udea.edu.co', 'first_name': 'Lina', 'last_name': 'Mora',
            'laboratorio': lab_b.id, 'password': ''})
        assert respuesta.status_code == 302
        assert list(cuenta.laboratorios_asignados.all()) == [lab_b]
        cuenta.refresh_from_db()
        assert cuenta.check_password(CLAVE)  # contraseña vacía = no cambia

    def test_editar_con_error_no_cambia_nada(self, admin_cliente, laboratorio, lab_b):
        cuenta = _cuenta_laboratorista(laboratorio)
        respuesta = admin_cliente.post(reverse('editar_laboratorista', args=[cuenta.id]), {
            'username': 'lina', 'email': 'lina@gmail.com', 'first_name': 'Lina', 'last_name': 'Mora',
            'laboratorio': lab_b.id, 'password': ''})
        assert respuesta.status_code == 200
        assert list(cuenta.laboratorios_asignados.all()) == [laboratorio]


# ── Baja y eliminación ──────────────────────────────────────────────────

class TestBaja:

    def test_get_muestra_la_confirmacion(self, admin_cliente, laboratorio):
        cuenta = _cuenta_laboratorista(laboratorio)
        contenido = admin_cliente.get(reverse('baja_laboratorista', args=[cuenta.id])).content.decode()
        assert 'desactiva la cuenta' in contenido
        assert laboratorio.nombre in contenido

    def test_sin_contrasena_pide_la_contrasena_y_no_cambia(self, admin_cliente, laboratorio):
        cuenta = _cuenta_laboratorista(laboratorio)
        respuesta = admin_cliente.post(reverse('baja_laboratorista', args=[cuenta.id]))
        assert respuesta.status_code == 200
        assert 'name="admin_password"' in respuesta.content.decode()
        cuenta.refresh_from_db()
        assert cuenta.is_active

    def test_contrasena_incorrecta_rechaza(self, admin_cliente, laboratorio):
        cuenta = _cuenta_laboratorista(laboratorio)
        respuesta = admin_cliente.post(reverse('baja_laboratorista', args=[cuenta.id]), {'admin_password': 'mal'})
        assert 'Contraseña incorrecta.' in respuesta.content.decode()
        cuenta.refresh_from_db()
        assert cuenta.is_active

    def test_con_contrasena_desactiva_y_quita_el_laboratorio(self, admin_cliente, laboratorio):
        cuenta = _cuenta_laboratorista(laboratorio)
        respuesta = admin_cliente.post(reverse('baja_laboratorista', args=[cuenta.id]),
                                       {'admin_password': CLAVE_ADMIN}, follow=True)
        cuenta.refresh_from_db()
        assert cuenta.is_active is False
        assert not cuenta.laboratorios_asignados.exists()
        assert any('dada de baja' in m for m in _mensajes(respuesta))

    def test_baja_de_monitor_libera_el_laboratorio(self, admin_cliente, laboratorio, usuario_monitor):
        admin_cliente.post(reverse('baja_monitor', args=[usuario_monitor.id]), {'admin_password': CLAVE_ADMIN})
        usuario_monitor.refresh_from_db()
        assert usuario_monitor.is_active is False
        assert not AsignacionMonitor.objects.filter(laboratorio=laboratorio).exists()


class TestEliminar:

    def test_con_datos_asociados_rechaza_con_mensaje_y_sin_pedir_contrasena(
            self, admin_cliente, laboratorio, reserva_con_prestamo):
        cuenta = _cuenta_laboratorista(laboratorio)
        Prestamo.objects.filter(pk=reserva_con_prestamo.prestamo.pk).update(responsable=cuenta)
        Reserva.objects.filter(pk=reserva_con_prestamo.reserva.pk).update(usuario=cuenta)
        respuesta = admin_cliente.post(reverse('eliminar_laboratorista', args=[cuenta.id]), follow=True)
        mensajes = ' '.join(_mensajes(respuesta))
        assert 'No se puede eliminar la cuenta "lina"' in mensajes
        assert '1 préstamos' in mensajes and '1 reservas' in mensajes
        assert 'Dala de baja en su lugar.' in mensajes
        assert Usuario.objects.filter(pk=cuenta.pk).exists()

    def test_sin_datos_y_con_contrasena_la_borra(self, admin_cliente, laboratorio):
        cuenta = _cuenta_laboratorista(laboratorio)
        admin_cliente.post(reverse('eliminar_laboratorista', args=[cuenta.id]), {'admin_password': CLAVE_ADMIN})
        assert not Usuario.objects.filter(pk=cuenta.pk).exists()

    def test_get_no_permitido(self, admin_cliente, laboratorio):
        cuenta = _cuenta_laboratorista(laboratorio)
        assert admin_cliente.get(reverse('eliminar_laboratorista', args=[cuenta.id])).status_code == 405


# ── Cuenta de monitor ───────────────────────────────────────────────────

class TestMonitor:

    def _datos(self, laboratorio, username='monitor_a', email='monitor.a@udea.edu.co'):
        return {'username': username, 'email': email, 'first_name': 'Monitor', 'last_name': 'A',
                'laboratorio': laboratorio.id, 'password': CLAVE}

    def test_el_administrador_crea_la_cuenta(self, admin_cliente, lab_b):
        respuesta = admin_cliente.post(reverse('crear_monitor'), self._datos(lab_b))
        assert respuesta.status_code == 302
        assert list(lab_b.monitores.values_list('username', flat=True)) == ['monitor_a']

    def test_la_segunda_del_mismo_laboratorio_se_rechaza_con_mensaje(self, admin_cliente, lab_b):
        admin_cliente.post(reverse('crear_monitor'), self._datos(lab_b))
        respuesta = admin_cliente.post(reverse('crear_monitor'),
                                       self._datos(lab_b, 'monitor_otro', 'otro.monitor@udea.edu.co'))
        assert respuesta.status_code == 200
        assert 'Este laboratorio ya tiene una cuenta de monitor.' in respuesta.content.decode()
        assert not Usuario.objects.filter(username='monitor_otro').exists()

    def test_el_laboratorista_no_la_crea(self, lab_cliente, laboratorio):
        Laboratorio.monitores.through.objects.filter(laboratorio=laboratorio).delete()
        respuesta = lab_cliente.post(reverse('crear_monitor'), self._datos(laboratorio))
        assert respuesta.status_code == 403
        assert not Usuario.objects.filter(username='monitor_a').exists()


# ── Fichas ──────────────────────────────────────────────────────────────

class TestFichas:

    def test_el_laboratorista_agrega_en_su_laboratorio(self, lab_cliente, laboratorio, usuario_laboratorista):
        respuesta = lab_cliente.post(f"{reverse('crear_ficha')}?laboratorio={laboratorio.id}",
                                     {'nombre': 'Carla', 'apellido': 'Díaz', 'correo': 'carla@gmail.com', 'activo': 'on'})
        assert respuesta.status_code == 302
        ficha = FichaMonitor.objects.get(nombre='Carla')
        assert list(ficha.laboratorios.all()) == [laboratorio]
        assert ficha.creado_por == usuario_laboratorista

    def test_el_laboratorista_no_edita_fichas_de_otro_laboratorio(self, lab_cliente, lab_b):
        ficha = _ficha(lab_b, 'Beto')
        respuesta = lab_cliente.post(reverse('editar_ficha', args=[ficha.id]),
                                     {'nombre': 'Cambiado', 'apellido': 'X'})
        assert respuesta.status_code == 403
        ficha.refresh_from_db()
        assert ficha.nombre == 'Beto'

    def test_el_laboratorista_no_quita_fichas_de_otro_laboratorio(self, lab_cliente, lab_b):
        ficha = _ficha(lab_b, 'Beto')
        respuesta = lab_cliente.post(reverse('quitar_ficha', args=[ficha.id]), {'laboratorio_id': lab_b.id})
        assert respuesta.status_code == 403
        assert list(ficha.laboratorios.all()) == [lab_b]

    def test_quitar_la_ultima_la_borra_y_lo_dice(self, lab_cliente, laboratorio):
        ficha = _ficha(laboratorio)
        respuesta = lab_cliente.post(reverse('quitar_ficha', args=[ficha.id]),
                                     {'laboratorio_id': laboratorio.id}, follow=True)
        assert not FichaMonitor.objects.filter(pk=ficha.pk).exists()
        assert any('borrada' in m for m in _mensajes(respuesta))

    def test_quitar_de_un_laboratorio_donde_no_esta_muestra_mensaje(self, admin_cliente, laboratorio, lab_b):
        ficha = _ficha(laboratorio)
        respuesta = admin_cliente.post(reverse('quitar_ficha', args=[ficha.id]),
                                       {'laboratorio_id': lab_b.id}, follow=True)
        assert respuesta.status_code == 200
        assert 'La ficha no está en este laboratorio.' in _mensajes(respuesta)

    def test_admin_vincula_a_otro_laboratorio(self, admin_cliente, laboratorio, lab_b):
        ficha = _ficha(laboratorio)
        admin_cliente.post(reverse('vincular_ficha', args=[ficha.id]), {'laboratorio_id': lab_b.id})
        assert set(ficha.laboratorios.all()) == {laboratorio, lab_b}

    def test_ficha_con_correo_invalido_muestra_error(self, admin_cliente, laboratorio):
        respuesta = admin_cliente.post(f"{reverse('crear_ficha')}?laboratorio={laboratorio.id}",
                                       {'nombre': 'Carla', 'apellido': 'Díaz', 'correo': 'no-es-correo'})
        assert respuesta.status_code == 200
        assert respuesta.context['form'].errors['correo']


# ── Descripción ─────────────────────────────────────────────────────────

class TestDescripcion:

    def test_el_laboratorista_edita_la_de_su_laboratorio(self, lab_cliente, laboratorio):
        respuesta = lab_cliente.post(reverse('editar_descripcion', args=[laboratorio.id]),
                                     {'descripcion': 'Química general y analítica.'})
        assert respuesta.status_code == 302
        assert respuesta['Location'].endswith('?seccion=descripcion')
        laboratorio.refresh_from_db()
        assert laboratorio.descripcion == 'Química general y analítica.'

    def test_de_otro_laboratorio_403(self, lab_cliente, lab_b):
        respuesta = lab_cliente.post(reverse('editar_descripcion', args=[lab_b.id]), {'descripcion': 'X'})
        assert respuesta.status_code == 403
        lab_b.refresh_from_db()
        assert lab_b.descripcion == ''

    def test_el_monitor_no_edita(self, client, usuario_monitor, laboratorio):
        client.force_login(usuario_monitor)
        assert client.get(reverse('editar_descripcion', args=[laboratorio.id])).status_code == 403


# ── Menú «Personal» ─────────────────────────────────────────────────────

class TestMenu:

    @pytest.mark.parametrize('fixture, lo_ve', [
        ('usuario_admin', True),
        ('usuario_laboratorista', True),
        ('usuario_monitor', False),
        ('usuario_estudiante', False),
    ])
    def test_por_rol(self, client, request, fixture, lo_ve):
        client.force_login(request.getfixturevalue(fixture))
        contenido = client.get('/laboratorio/personal/' if lo_ve else '/', follow=True).content.decode()
        assert ('data-menu="personal"' in contenido) is lo_ve

    def test_ya_no_aparece_laboratoristas(self, admin_cliente):
        contenido = admin_cliente.get(reverse('personal')).content.decode()
        assert 'href="/laboratorio/laboratoristas/"' not in contenido


# ── Crear laboratorio ya no crea cuenta lab_<x> ─────────────────────────

def test_crear_laboratorio_no_crea_cuenta(admin_cliente):
    usuarios_antes = Usuario.objects.count()
    respuesta = admin_cliente.post(reverse('crear_laboratorio'), {
        'nombre': 'Lab Nuevo', 'ubicacion': 'Bloque N', 'programa': '', 'activo': 'on',
        'cuenta_username': 'lab_nuevo', 'cuenta_password': 'x', 'cuenta_password2': 'x'})
    assert respuesta.status_code == 302
    nuevo = Laboratorio.objects.get(nombre='Lab Nuevo')
    assert Usuario.objects.count() == usuarios_antes
    assert not nuevo.laboratoristas.exists()


# ── Admin de Usuarios ───────────────────────────────────────────────────

@pytest.fixture
def superadmin_cliente(client, catalogos):
    jefe = Usuario.objects.create_superuser(
        username='jefe', password='x', email='jefe@udea.edu.co', rol=Rol.objects.get(nombre='Administrador'))
    client.force_login(jefe)
    return client


class TestAdminUsuarios:

    @pytest.mark.parametrize('fixture', ['usuario_laboratorista', 'usuario_monitor'])
    def test_no_permite_borrar_cuentas_de_personal(self, superadmin_cliente, request, fixture):
        cuenta = request.getfixturevalue(fixture)
        respuesta = superadmin_cliente.post(f'/admin/users/usuario/{cuenta.id}/delete/', {'post': 'yes'})
        assert respuesta.status_code == 403
        assert Usuario.objects.filter(pk=cuenta.pk).exists()

    def test_accion_masiva_no_borra_cuentas_de_personal(self, superadmin_cliente, usuario_laboratorista,
                                                         usuario_estudiante):
        respuesta = superadmin_cliente.post('/admin/users/usuario/', {
            'action': 'delete_selected', 'post': 'yes',
            '_selected_action': [usuario_laboratorista.id, usuario_estudiante.id]})
        assert respuesta.status_code == 403
        assert Usuario.objects.filter(pk=usuario_laboratorista.pk).exists()
        assert Usuario.objects.filter(pk=usuario_estudiante.pk).exists()

    @pytest.mark.parametrize('fixture', ['usuario_laboratorista', 'usuario_monitor'])
    def test_no_permite_desactivar_cuentas_de_personal(self, superadmin_cliente, request, fixture):
        cuenta = request.getfixturevalue(fixture)
        modelo_admin = admin.site._registry[Usuario]
        peticion = superadmin_cliente.get('/').wsgi_request
        assert 'is_active' in modelo_admin.get_readonly_fields(peticion, cuenta)

    def test_otras_cuentas_siguen_igual(self, superadmin_cliente, usuario_estudiante):
        modelo_admin = admin.site._registry[Usuario]
        peticion = superadmin_cliente.get('/').wsgi_request
        assert modelo_admin.has_delete_permission(peticion, usuario_estudiante)
        assert 'is_active' not in modelo_admin.get_readonly_fields(peticion, usuario_estudiante)
        superadmin_cliente.post(f'/admin/users/usuario/{usuario_estudiante.id}/delete/', {'post': 'yes'})
        assert not Usuario.objects.filter(pk=usuario_estudiante.pk).exists()


# ── seed_e2e ────────────────────────────────────────────────────────────

def test_seed_e2e_crea_laboratorista_v2_activo_con_un_laboratorio_sin_tocar_el_viejo(catalogos):
    from io import StringIO

    from django.core.management import call_command

    viejo = Usuario.objects.create_user(
        username='e2e_laboratorista', password='vieja', is_active=False, rol=Rol.objects.get(nombre='Laboratorista'))
    clave_vieja = viejo.password

    call_command('seed_e2e', stdout=StringIO())
    call_command('seed_e2e', stdout=StringIO())  # idempotente

    v2 = Usuario.objects.get(username='e2e_laboratorista_v2')
    assert v2.is_active and v2.rol.nombre == 'Laboratorista'
    assert v2.email == 'e2e.laboratorista@udea.edu.co'
    assert v2.check_password('E2eLab!2026')
    assert list(v2.laboratorios_asignados.values_list('nombre', flat=True)) == ['Laboratorio E2E']

    viejo.refresh_from_db()
    assert viejo.is_active is False and viejo.password == clave_vieja
    assert not viejo.laboratorios_asignados.exists()


# ── Pantalla genérica de usuarios: sin desactivación directa ────────────

class TestDesactivarDesdeUsuarios:
    """/usuarios/<id>/desactivar/: las cuentas Laboratorista y Monitor se
    rechazan (403, sin pedir contraseña); las demás, igual que siempre."""

    @pytest.mark.parametrize('fixture', ['usuario_laboratorista', 'usuario_monitor'])
    def test_get_rechaza_sin_pedir_contrasena(self, admin_cliente, request, fixture):
        cuenta = request.getfixturevalue(fixture)
        respuesta = admin_cliente.get(reverse('desactivar_usuario', args=[cuenta.id]))
        contenido = respuesta.content.decode()
        assert respuesta.status_code == 403
        assert 'se da de baja desde Personal' in contenido
        assert 'name="admin_password"' not in contenido

    @pytest.mark.parametrize('fixture', ['usuario_laboratorista', 'usuario_monitor'])
    def test_post_con_contrasena_correcta_no_desactiva(self, admin_cliente, request, laboratorio, fixture):
        cuenta = request.getfixturevalue(fixture)
        respuesta = admin_cliente.post(reverse('desactivar_usuario', args=[cuenta.id]),
                                       {'admin_password': CLAVE_ADMIN})
        assert respuesta.status_code == 403
        cuenta.refresh_from_db()
        assert cuenta.is_active
        laboratorios = (cuenta.laboratorios_asignados if fixture == 'usuario_laboratorista'
                        else cuenta.laboratorios_monitoreados)
        assert list(laboratorios.all()) == [laboratorio]  # sigue con su laboratorio

    def test_cuenta_normal_pide_contrasena_y_se_desactiva(self, admin_cliente, usuario_estudiante):
        url = reverse('desactivar_usuario', args=[usuario_estudiante.id])
        assert 'name="admin_password"' in admin_cliente.get(url).content.decode()
        respuesta = admin_cliente.post(url, {'admin_password': CLAVE_ADMIN})
        assert respuesta.status_code == 302
        usuario_estudiante.refresh_from_db()
        assert usuario_estudiante.is_active is False

    def test_cuenta_normal_con_contrasena_incorrecta_no_se_desactiva(self, admin_cliente, usuario_estudiante):
        respuesta = admin_cliente.post(reverse('desactivar_usuario', args=[usuario_estudiante.id]),
                                       {'admin_password': 'mal'})
        assert 'Contraseña incorrecta.' in respuesta.content.decode()
        usuario_estudiante.refresh_from_db()
        assert usuario_estudiante.is_active

    def test_el_laboratorista_no_usa_la_pantalla_generica(self, lab_cliente, usuario_estudiante):
        respuesta = lab_cliente.get(reverse('desactivar_usuario', args=[usuario_estudiante.id]))
        assert respuesta.status_code == 302  # rol_requerido('Administrador') → sin_permiso
        usuario_estudiante.refresh_from_db()
        assert usuario_estudiante.is_active

    def test_lista_ofrece_dar_de_baja_en_personal_en_vez_de_desactivar(
            self, admin_cliente, usuario_laboratorista, usuario_monitor, usuario_estudiante):
        contenido = admin_cliente.get(reverse('lista_usuarios')).content.decode()
        assert f'/usuarios/{usuario_laboratorista.id}/desactivar/' not in contenido
        assert f'/usuarios/{usuario_monitor.id}/desactivar/' not in contenido
        assert reverse('baja_laboratorista', args=[usuario_laboratorista.id]) in contenido
        assert reverse('baja_monitor', args=[usuario_monitor.id]) in contenido
        assert f'/usuarios/{usuario_estudiante.id}/desactivar/' in contenido
