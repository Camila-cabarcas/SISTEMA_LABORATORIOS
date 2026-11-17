"""
Servicio de Personal (laboratorio/services/personal.py), etapa 2:
cuentas de laboratorista y de monitor, baja y borrado, descripción del
laboratorio, el chequeo de cuentas activas sin laboratorio, y que la
pantalla genérica de usuarios y el admin de Django no asignen los roles
Laboratorista ni Monitor.
"""
import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from inventario.models import ItemInventario, MovimientoInventario, TipoMovimiento
from laboratorio.models import AsignacionLaboratorista, AsignacionMonitor, Laboratorio
from laboratorio.services import personal
from laboratorio.services.personal import DatosPersonalInvalidos, SinPermisoPersonal
from prestamos.models import InspeccionItem, Prestamo
from reservas.models import Reserva
from users.forms import EditarUsuarioForm, UsuarioForm
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db

CLAVE = 'ClaveInicial123'


def _datos(**extra):
    datos = {
        'username': 'lab_quimica', 'email': 'lab.quimica@udea.edu.co',
        'first_name': 'Lina', 'last_name': 'Mora', 'password': CLAVE,
    }
    datos.update(extra)
    return datos


@pytest.fixture
def otro_laboratorio(db):
    return Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 9')


@pytest.fixture
def laboratorista(usuario_admin, laboratorio):
    return personal.crear_laboratorista(_datos(), laboratorio, usuario_admin)


def _laboratorios(usuario):
    return list(usuario.laboratorios_asignados.all())


# ── Crear laboratorista ─────────────────────────────────────────────────

class TestCrearLaboratorista:

    def test_crea_cuenta_activa_con_un_laboratorio(self, usuario_admin, laboratorio):
        cuenta = personal.crear_laboratorista(_datos(), laboratorio, usuario_admin)
        cuenta.refresh_from_db()
        assert cuenta.rol.nombre == 'Laboratorista'
        assert cuenta.is_active
        assert cuenta.email == 'lab.quimica@udea.edu.co'
        assert (cuenta.first_name, cuenta.last_name) == ('Lina', 'Mora')
        assert cuenta.check_password(CLAVE)
        assert _laboratorios(cuenta) == [laboratorio]

    def test_entra_con_su_correo(self, client, usuario_admin, laboratorio):
        personal.crear_laboratorista(_datos(), laboratorio, usuario_admin)
        client.post(reverse('login'), {'username': 'LAB.Quimica@udea.edu.co', 'password': CLAVE})
        assert '_auth_user_id' in client.session

    @pytest.mark.parametrize('correo', ['lina@gmail.com', 'lina@udea.edu.co.evil.com', 'no-es-correo'])
    def test_rechaza_correo_fuera_de_udea(self, usuario_admin, laboratorio, correo):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_laboratorista(_datos(email=correo), laboratorio, usuario_admin)
        assert 'email' in error.value.errores
        assert not Usuario.objects.filter(username='lab_quimica').exists()

    def test_correo_es_obligatorio(self, usuario_admin, laboratorio):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_laboratorista(_datos(email=''), laboratorio, usuario_admin)
        assert error.value.errores['email'] == ['El correo es obligatorio.']

    @pytest.mark.parametrize('campo', ['username', 'first_name', 'last_name', 'password'])
    def test_campos_obligatorios(self, usuario_admin, laboratorio, campo):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_laboratorista(_datos(**{campo: ''}), laboratorio, usuario_admin)
        assert campo in error.value.errores

    def test_rechaza_usuario_repetido_sin_distinguir_mayusculas(self, usuario_admin, laboratorio, laboratorista):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_laboratorista(
                _datos(username='LAB_Quimica', email='otra@udea.edu.co'), laboratorio, usuario_admin)
        assert error.value.errores['username'] == ['Ya existe una cuenta con ese nombre de usuario.']

    def test_rechaza_correo_repetido_sin_distinguir_mayusculas(self, usuario_admin, laboratorio, laboratorista):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_laboratorista(
                _datos(username='otro', email='LAB.QUIMICA@udea.edu.co'), laboratorio, usuario_admin)
        assert 'Ya existe una cuenta con ese correo electrónico.' in str(error.value)

    def test_rechaza_sin_laboratorio_y_no_crea_nada(self, usuario_admin):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_laboratorista(_datos(), None, usuario_admin)
        assert error.value.errores == {'laboratorio': ['Selecciona un laboratorio.']}
        assert not Usuario.objects.filter(username='lab_quimica').exists()

    def test_un_laboratorio_puede_tener_varios_laboratoristas(self, usuario_admin, laboratorio, laboratorista):
        segundo = personal.crear_laboratorista(
            _datos(username='lab_quimica_2', email='lab2@udea.edu.co'), laboratorio, usuario_admin)
        assert set(laboratorio.laboratoristas.all()) == {laboratorista, segundo}

    @pytest.mark.parametrize('quien', ['usuario_laboratorista', 'usuario_monitor'])
    def test_solo_el_administrador(self, request, laboratorio, quien):
        actor = request.getfixturevalue(quien)
        with pytest.raises(SinPermisoPersonal) as error:
            personal.crear_laboratorista(_datos(), laboratorio, actor)
        assert isinstance(error.value, PermissionDenied)  # sin capturar → 403, no 500


# ── Editar y cambiar de laboratorio ─────────────────────────────────────

class TestEditarLaboratorista:

    def test_edita_datos_y_conserva_la_clave_si_no_se_envia(self, usuario_admin, laboratorista):
        personal.editar_laboratorista(
            laboratorista, _datos(first_name='Lucía', email='lucia@udea.edu.co', password=''), usuario_admin)
        laboratorista.refresh_from_db()
        assert laboratorista.first_name == 'Lucía'
        assert laboratorista.email == 'lucia@udea.edu.co'
        assert laboratorista.check_password(CLAVE)

    def test_cambia_la_clave_si_se_envia(self, usuario_admin, laboratorista):
        personal.editar_laboratorista(laboratorista, _datos(password='NuevaClave456'), usuario_admin)
        laboratorista.refresh_from_db()
        assert laboratorista.check_password('NuevaClave456')

    def test_rechaza_correo_fuera_de_udea(self, usuario_admin, laboratorista):
        with pytest.raises(DatosPersonalInvalidos):
            personal.editar_laboratorista(laboratorista, _datos(email='lina@gmail.com'), usuario_admin)
        laboratorista.refresh_from_db()
        assert laboratorista.email == 'lab.quimica@udea.edu.co'

    def test_no_edita_cuentas_de_otro_rol(self, usuario_admin, usuario_estudiante):
        with pytest.raises(DatosPersonalInvalidos):
            personal.editar_laboratorista(usuario_estudiante, _datos(), usuario_admin)

    def test_solo_el_administrador(self, usuario_laboratorista, laboratorista):
        with pytest.raises(SinPermisoPersonal):
            personal.editar_laboratorista(laboratorista, _datos(first_name='X'), usuario_laboratorista)


class TestCambiarLaboratorio:

    def test_queda_con_uno_solo_el_nuevo(self, usuario_admin, laboratorista, otro_laboratorio):
        personal.cambiar_laboratorio(laboratorista, otro_laboratorio, usuario_admin)
        assert _laboratorios(laboratorista) == [otro_laboratorio]
        assert AsignacionLaboratorista.objects.filter(usuario=laboratorista).count() == 1

    def test_al_mismo_laboratorio_no_duplica(self, usuario_admin, laboratorista, laboratorio):
        personal.cambiar_laboratorio(laboratorista, laboratorio, usuario_admin)
        assert _laboratorios(laboratorista) == [laboratorio]

    def test_sin_laboratorio_se_rechaza_y_conserva_el_actual(self, usuario_admin, laboratorista, laboratorio):
        with pytest.raises(DatosPersonalInvalidos):
            personal.cambiar_laboratorio(laboratorista, None, usuario_admin)
        assert _laboratorios(laboratorista) == [laboratorio]

    def test_solo_el_administrador(self, usuario_laboratorista, laboratorista, otro_laboratorio):
        with pytest.raises(SinPermisoPersonal):
            personal.cambiar_laboratorio(laboratorista, otro_laboratorio, usuario_laboratorista)


# ── Dar de baja y eliminar ──────────────────────────────────────────────

def _asociar_prestamo_y_reserva(cuenta, reserva_con_prestamo):
    Reserva.objects.filter(pk=reserva_con_prestamo.reserva.pk).update(usuario=cuenta)
    Prestamo.objects.filter(pk=reserva_con_prestamo.prestamo.pk).update(responsable=cuenta)


class TestDarDeBaja:

    def test_desactiva_y_quita_el_laboratorio_sin_borrar_la_cuenta(self, usuario_admin, laboratorista):
        personal.dar_de_baja_laboratorista(laboratorista, usuario_admin)
        laboratorista.refresh_from_db()
        assert laboratorista.is_active is False
        assert _laboratorios(laboratorista) == []

    def test_no_borra_prestamos_ni_reservas(self, usuario_admin, laboratorista, reserva_con_prestamo):
        _asociar_prestamo_y_reserva(laboratorista, reserva_con_prestamo)
        personal.dar_de_baja_laboratorista(laboratorista, usuario_admin)
        assert Prestamo.objects.filter(responsable=laboratorista).count() == 1
        assert Reserva.objects.filter(usuario=laboratorista).count() == 1

    def test_la_cuenta_dada_de_baja_no_puede_entrar(self, client, usuario_admin, laboratorista):
        personal.dar_de_baja_laboratorista(laboratorista, usuario_admin)
        for identificador in ('lab_quimica', 'lab.quimica@udea.edu.co'):
            client.post(reverse('login'), {'username': identificador, 'password': CLAVE})
            assert '_auth_user_id' not in client.session

    def test_es_idempotente(self, usuario_admin, laboratorista):
        personal.dar_de_baja_laboratorista(laboratorista, usuario_admin)
        personal.dar_de_baja_laboratorista(laboratorista, usuario_admin)
        assert Usuario.objects.get(pk=laboratorista.pk).is_active is False

    def test_solo_el_administrador(self, usuario_laboratorista, laboratorista):
        with pytest.raises(SinPermisoPersonal):
            personal.dar_de_baja_laboratorista(laboratorista, usuario_laboratorista)
        laboratorista.refresh_from_db()
        assert laboratorista.is_active


def _con_prestamo(cuenta, datos):
    Prestamo.objects.filter(pk=datos.prestamo.pk).update(responsable=cuenta)
    return 'préstamos'


def _con_reserva(cuenta, datos):
    Reserva.objects.filter(pk=datos.reserva.pk).update(usuario=cuenta)
    return 'reservas'


def _con_movimiento(cuenta, datos):
    MovimientoInventario.objects.create(
        item_inventario=datos.item, usuario=cuenta, tipo_movimiento=TipoMovimiento.objects.first())
    return 'movimientos de inventario'


def _con_inspeccion(cuenta, datos):
    InspeccionItem.objects.create(prestamo=datos.prestamo, prestamo_item=datos.prestamo_item, inspector=cuenta)
    return 'inspecciones'


def _con_item_actualizado(cuenta, datos):
    # ItemInventario.updated_by es CASCADE: borrar la cuenta borraría el ítem.
    ItemInventario.objects.filter(pk=datos.item.pk).update(updated_by=cuenta)
    return '1 '


class TestEliminar:

    def test_sin_datos_asociados_se_borra(self, usuario_admin, laboratorista):
        pk = laboratorista.pk
        personal.eliminar_laboratorista(laboratorista, usuario_admin)
        assert not Usuario.objects.filter(pk=pk).exists()
        assert not AsignacionLaboratorista.objects.filter(usuario_id=pk).exists()

    @pytest.mark.parametrize('asociar', [
        _con_prestamo, _con_reserva, _con_movimiento, _con_inspeccion, _con_item_actualizado,
    ])
    def test_con_datos_asociados_se_rechaza_y_no_borra_nada(
            self, usuario_admin, laboratorista, reserva_con_prestamo, asociar):
        esperado = asociar(laboratorista, reserva_con_prestamo)
        antes = (Prestamo.objects.count(), Reserva.objects.count(),
                 MovimientoInventario.objects.count(), ItemInventario.objects.count())
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.eliminar_laboratorista(laboratorista, usuario_admin)
        assert esperado in str(error.value)
        assert 'Dala de baja en su lugar.' in str(error.value)
        assert Usuario.objects.filter(pk=laboratorista.pk).exists()
        assert (Prestamo.objects.count(), Reserva.objects.count(),
                MovimientoInventario.objects.count(), ItemInventario.objects.count()) == antes

    def test_solo_el_administrador(self, usuario_laboratorista, laboratorista):
        with pytest.raises(SinPermisoPersonal):
            personal.eliminar_laboratorista(laboratorista, usuario_laboratorista)
        assert Usuario.objects.filter(pk=laboratorista.pk).exists()


# ── Cuenta de monitor ───────────────────────────────────────────────────

def _datos_monitor(**extra):
    return _datos(**{'username': 'monitor_quimica', 'email': 'monitor.quimica@udea.edu.co',
                     'first_name': 'Monitor', 'last_name': 'Química', **extra})


class TestMonitor:

    def test_crea_la_cuenta_del_laboratorio(self, usuario_admin, laboratorio):
        cuenta = personal.crear_monitor_laboratorio(_datos_monitor(), laboratorio, usuario_admin)
        assert cuenta.rol.nombre == 'Monitor'
        assert cuenta.is_active
        assert list(cuenta.laboratorios_monitoreados.all()) == [laboratorio]

    def test_rechaza_la_segunda_cuenta_del_mismo_laboratorio(self, usuario_admin, laboratorio):
        personal.crear_monitor_laboratorio(_datos_monitor(), laboratorio, usuario_admin)
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_monitor_laboratorio(
                _datos_monitor(username='otro_monitor', email='otro.monitor@udea.edu.co'),
                laboratorio, usuario_admin)
        assert error.value.errores == {'laboratorio': ['Este laboratorio ya tiene una cuenta de monitor.']}
        assert not Usuario.objects.filter(username='otro_monitor').exists()

    def test_rechaza_correo_fuera_de_udea(self, usuario_admin, laboratorio):
        with pytest.raises(DatosPersonalInvalidos) as error:
            personal.crear_monitor_laboratorio(_datos_monitor(email='monitor@gmail.com'), laboratorio, usuario_admin)
        assert 'email' in error.value.errores
        assert not AsignacionMonitor.objects.filter(laboratorio=laboratorio).exists()

    def test_editar(self, usuario_admin, laboratorio):
        cuenta = personal.crear_monitor_laboratorio(_datos_monitor(), laboratorio, usuario_admin)
        personal.editar_monitor(cuenta, _datos_monitor(last_name='Química A', password=''), usuario_admin)
        cuenta.refresh_from_db()
        assert cuenta.last_name == 'Química A'
        assert cuenta.check_password(CLAVE)

    def test_dar_de_baja_libera_el_laboratorio(self, usuario_admin, laboratorio):
        cuenta = personal.crear_monitor_laboratorio(_datos_monitor(), laboratorio, usuario_admin)
        personal.dar_de_baja_monitor(cuenta, usuario_admin)
        cuenta.refresh_from_db()
        assert cuenta.is_active is False
        assert not cuenta.laboratorios_monitoreados.exists()
        nueva = personal.crear_monitor_laboratorio(
            _datos_monitor(username='monitor_quimica_2', email='monitor2@udea.edu.co'), laboratorio, usuario_admin)
        assert list(laboratorio.monitores.all()) == [nueva]

    def test_no_mezcla_roles(self, usuario_admin, laboratorista):
        with pytest.raises(DatosPersonalInvalidos):
            personal.dar_de_baja_monitor(laboratorista, usuario_admin)
        with pytest.raises(DatosPersonalInvalidos):
            personal.dar_de_baja_laboratorista(
                personal.crear_monitor_laboratorio(
                    _datos_monitor(), Laboratorio.objects.create(nombre='Lab M', ubicacion='M'), usuario_admin),
                usuario_admin)

    @pytest.mark.parametrize('quien', ['usuario_laboratorista', 'usuario_monitor'])
    def test_solo_el_administrador(self, request, quien):
        actor = request.getfixturevalue(quien)
        otro = Laboratorio.objects.create(nombre='Lab sin monitor', ubicacion='X')
        with pytest.raises(SinPermisoPersonal):
            personal.crear_monitor_laboratorio(_datos_monitor(), otro, actor)


# ── Chequeo de solo lectura ─────────────────────────────────────────────

class TestCuentasActivasSinLaboratorio:

    def test_lista_solo_las_activas_sin_laboratorio(self, usuario_admin, laboratorista, usuario_monitor):
        rol_lab = Rol.objects.get(nombre='Laboratorista')
        rol_mon = Rol.objects.get(nombre='Monitor')
        huerfana = Usuario.objects.create_user(username='lab_huerfana', password='x', rol=rol_lab)
        monitor_huerfano = Usuario.objects.create_user(username='mon_huerfano', password='x', rol=rol_mon)
        Usuario.objects.create_user(username='lab_baja', password='x', rol=rol_lab, is_active=False)
        personal.dar_de_baja_laboratorista(
            personal.crear_laboratorista(_datos(username='lab_x', email='x@udea.edu.co'),
                                         laboratorista.laboratorios_asignados.get(), usuario_admin),
            usuario_admin)

        assert list(personal.cuentas_activas_sin_laboratorio()) == [huerfana, monitor_huerfano]

    def test_no_cambia_datos(self, catalogos):
        cuenta = Usuario.objects.create_user(
            username='lab_huerfana', password='x', rol=Rol.objects.get(nombre='Laboratorista'))
        list(personal.cuentas_activas_sin_laboratorio())
        cuenta.refresh_from_db()
        assert cuenta.is_active


# ── Descripción del laboratorio ─────────────────────────────────────────

class TestDescripcion:

    def test_el_administrador_edita_cualquier_laboratorio(self, usuario_admin, otro_laboratorio):
        personal.actualizar_descripcion_laboratorio(otro_laboratorio, '  Óptica y ondas.  ', usuario_admin)
        otro_laboratorio.refresh_from_db()
        assert otro_laboratorio.descripcion == 'Óptica y ondas.'

    def test_el_laboratorista_edita_el_suyo(self, usuario_laboratorista, laboratorio):
        personal.actualizar_descripcion_laboratorio(laboratorio, 'Química general.', usuario_laboratorista)
        laboratorio.refresh_from_db()
        assert laboratorio.descripcion == 'Química general.'

    def test_el_laboratorista_no_edita_otro(self, usuario_laboratorista, otro_laboratorio):
        with pytest.raises(SinPermisoPersonal):
            personal.actualizar_descripcion_laboratorio(otro_laboratorio, 'X', usuario_laboratorista)
        otro_laboratorio.refresh_from_db()
        assert otro_laboratorio.descripcion == ''

    @pytest.mark.parametrize('quien', ['usuario_monitor', 'usuario_estudiante'])
    def test_monitor_y_otros_roles_no_editan(self, request, laboratorio, quien):
        with pytest.raises(SinPermisoPersonal):
            personal.actualizar_descripcion_laboratorio(laboratorio, 'X', request.getfixturevalue(quien))

    def test_texto_plano_se_guarda_tal_cual(self, usuario_admin, laboratorio):
        texto = '<b>Equipos</b> & reactivos'
        personal.actualizar_descripcion_laboratorio(laboratorio, texto, usuario_admin)
        laboratorio.refresh_from_db()
        assert laboratorio.descripcion == texto


# ── Pantalla genérica de usuarios y admin de Django ─────────────────────

def _roles_ofrecidos(form):
    return set(form.fields['rol'].queryset.values_list('nombre', flat=True))


class TestFormularioGenerico:

    def test_crear_no_ofrece_laboratorista_ni_monitor(self, catalogos):
        roles = _roles_ofrecidos(UsuarioForm())
        assert 'Laboratorista' not in roles
        assert 'Monitor' not in roles
        assert {'Administrador', 'Estudiante', 'Docente'} <= roles

    @pytest.mark.parametrize('rol', ['Laboratorista', 'Monitor'])
    def test_crear_rechaza_esos_roles_por_post(self, client, usuario_admin, rol):
        client.force_login(usuario_admin)
        respuesta = client.post(reverse('crear_usuario'), {
            'username': 'intento', 'first_name': 'A', 'last_name': 'B', 'email': '',
            'codigo': '', 'programa': '', 'rol': Rol.objects.get(nombre=rol).id, 'password': CLAVE,
        })
        assert respuesta.status_code == 200
        assert not Usuario.objects.filter(username='intento').exists()

    def test_editar_otra_cuenta_no_puede_pasar_a_laboratorista(self, usuario_estudiante):
        form = EditarUsuarioForm(
            data={'first_name': 'E', 'last_name': 'T', 'email': '', 'codigo': '', 'programa': '',
                  'rol': Rol.objects.get(nombre='Laboratorista').id},
            instance=usuario_estudiante,
        )
        assert not form.is_valid()
        assert 'rol' in form.errors

    def test_editar_laboratorista_muestra_el_rol_bloqueado(self, usuario_laboratorista):
        form = EditarUsuarioForm(
            data={'first_name': 'Nuevo', 'last_name': 'Nombre', 'email': '', 'codigo': 'LAB_TEST_001',
                  'programa': '', 'rol': Rol.objects.get(nombre='Administrador').id},
            instance=usuario_laboratorista,
        )
        assert form.fields['rol'].disabled
        assert form.is_valid(), form.errors
        form.save()
        usuario_laboratorista.refresh_from_db()
        assert usuario_laboratorista.rol.nombre == 'Laboratorista'  # el POST no lo cambia
        assert usuario_laboratorista.first_name == 'Nuevo'


@pytest.fixture
def peticion_admin(rf, usuario_admin):
    request = rf.get('/')
    request.user = usuario_admin
    return request


class TestAdminDjango:

    def test_formulario_de_laboratorio_no_tiene_laboratoristas_ni_monitores(self):
        campos = admin.site._registry[Laboratorio].get_form(None).base_fields
        assert 'laboratoristas' not in campos
        assert 'monitores' not in campos

    def test_asignaciones_no_estan_registradas_en_el_admin(self):
        assert AsignacionLaboratorista not in admin.site._registry
        assert AsignacionMonitor not in admin.site._registry

    def test_alta_de_usuario_no_ofrece_laboratorista_ni_monitor(self, peticion_admin):
        modelo_admin = admin.site._registry[Usuario]
        form = modelo_admin.get_form(peticion_admin, None)()
        assert not {'Laboratorista', 'Monitor'} & _roles_ofrecidos(form)

    def test_cuenta_laboratorista_muestra_el_rol_bloqueado(self, peticion_admin, usuario_laboratorista):
        modelo_admin = admin.site._registry[Usuario]
        form = modelo_admin.get_form(peticion_admin, usuario_laboratorista)(instance=usuario_laboratorista)
        assert form.fields['rol'].disabled

    def test_otra_cuenta_no_puede_pasar_a_monitor(self, peticion_admin, usuario_estudiante):
        modelo_admin = admin.site._registry[Usuario]
        form = modelo_admin.get_form(peticion_admin, usuario_estudiante)(instance=usuario_estudiante)
        assert 'Monitor' not in _roles_ofrecidos(form)
