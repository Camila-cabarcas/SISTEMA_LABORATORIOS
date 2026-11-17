"""
Pantallas de profesores (fase 2, etapa 3): Profesores habilitados
(/usuarios/profesores/, solo Administrador, sin cuentas), solicitudes de
profesor (rechazo con motivo), registro público, menú, tablero sin panel
Docente y URLs eliminadas.
"""
import pytest
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse

from laboratorio.models import Laboratorio
from solicitudes.forms import CursoForm
from solicitudes.models import Curso, Profesor, SolicitudRegistroProfesor, validar_profesor_de_reserva
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def profesor(db):
    profesor = Profesor.objects.create(nombre='Ana', apellido='Ruiz', cedula='777',
                                       correo='kaly@gmail.com', programa='Química')
    Curso.objects.create(nombre='Química General', codigo='QUIM-1', profesor=profesor, cantidad_estudiantes=20)
    return profesor


@pytest.fixture
def admin_cliente(client, usuario_admin):
    client.force_login(usuario_admin)
    return client


# ── Profesores habilitados ──────────────────────────────────────────────

class TestProfesoresHabilitados:

    def test_lista_muestra_profesores_y_busca_por_cedula(self, admin_cliente, profesor):
        Profesor.objects.create(nombre='Luis', apellido='Pardo', cedula='888', activo=False)
        contenido = admin_cliente.get(reverse('lista_profesores')).content.decode()
        assert 'Ana Ruiz' in contenido and 'Luis Pardo' in contenido and 'Inactivo' in contenido
        respuesta = admin_cliente.get(reverse('lista_profesores'), {'q': '777'})
        assert [p.cedula for p in respuesta.context['profesores']] == ['777']

    def test_no_hay_boton_de_crear_cuenta(self, admin_cliente, profesor):
        contenido = admin_cliente.get(reverse('lista_profesores')).content.decode()
        assert '/usuarios/profesores/crear/' not in contenido
        assert 'Crear cuenta' not in contenido and 'Nuevo profesor' not in contenido

    def test_detalle_muestra_sus_cursos(self, admin_cliente, profesor):
        contenido = admin_cliente.get(reverse('detalle_profesor', args=[profesor.id])).content.decode()
        assert 'QUIM-1' in contenido and '777' in contenido

    def test_editar_cambia_datos_pero_no_la_cedula(self, admin_cliente, profesor):
        respuesta = admin_cliente.post(reverse('editar_profesor', args=[profesor.id]), {
            'nombre': 'Ana María', 'apellido': 'Ruiz', 'correo': 'ana.ruiz@udea.edu.co',
            'programa': '', 'cedula': '999'})
        assert respuesta.status_code == 302
        profesor.refresh_from_db()
        assert (profesor.nombre, profesor.correo, profesor.cedula) == ('Ana María', 'ana.ruiz@udea.edu.co', '777')

    def test_editar_conserva_un_correo_viejo_de_otro_dominio(self, admin_cliente, profesor):
        respuesta = admin_cliente.post(reverse('editar_profesor', args=[profesor.id]), {
            'nombre': 'Ana', 'apellido': 'Ruiz', 'correo': 'kaly@gmail.com', 'programa': 'Química'})
        assert respuesta.status_code == 302
        profesor.refresh_from_db()
        assert (profesor.correo, profesor.programa) == ('kaly@gmail.com', 'Química')

    def test_editar_no_crea_cuentas(self, admin_cliente, profesor):
        antes = Usuario.objects.count()
        admin_cliente.post(reverse('editar_profesor', args=[profesor.id]),
                           {'nombre': 'Ana', 'apellido': 'Ruiz', 'correo': '', 'programa': ''})
        assert Usuario.objects.count() == antes

    def test_desactivar_lo_saca_de_cursos_y_reservas(self, admin_cliente, client, profesor):
        respuesta = admin_cliente.post(reverse('desactivar_profesor', args=[profesor.id]))
        assert respuesta.status_code == 302
        profesor.refresh_from_db()
        assert profesor.activo is False
        # Ya no aparece en la búsqueda de reserva de curso ni al crear cursos.
        assert 'no está activo' in validar_profesor_de_reserva('777')
        datos = client.get('/solicitudes/cursos-profesor/', {'cedula': '777'}).json()
        assert datos['cursos'] == []
        assert profesor not in CursoForm().fields['profesor'].queryset
        # Sus cursos se conservan.
        assert profesor.cursos.count() == 1

    def test_desactivar_solo_por_post(self, admin_cliente, profesor):
        assert admin_cliente.get(reverse('desactivar_profesor', args=[profesor.id])).status_code == 405
        profesor.refresh_from_db()
        assert profesor.activo

    def test_laboratorista_no_ve_profesores_habilitados(self, client, usuario_laboratorista, profesor):
        client.force_login(usuario_laboratorista)
        respuesta = client.get(reverse('lista_profesores'))
        assert respuesta.status_code == 302 and respuesta['Location'] == reverse('sin_permiso')

    def test_crear_curso_preselecciona_al_profesor(self, admin_cliente, profesor):
        respuesta = admin_cliente.get(reverse('crear_curso'), {'profesor_id': profesor.id})
        assert respuesta.context['profesor_preseleccionado'] == profesor
        assert '777' in respuesta.content.decode()


@pytest.mark.parametrize('ruta', ['/usuarios/profesores/crear/', '/usuarios/profesores/1/toggle/'])
def test_urls_eliminadas_dan_404(admin_cliente, ruta):
    assert admin_cliente.get(ruta).status_code == 404
    assert admin_cliente.post(ruta).status_code == 404


# ── Solicitudes de profesor ─────────────────────────────────────────────

class TestSolicitudes:

    def test_laboratorista_ve_solo_las_suyas_y_las_sin_laboratorio(self, client, usuario_laboratorista, laboratorio):
        otro = Laboratorio.objects.create(nombre='Lab B', ubicacion='B')
        propia = SolicitudRegistroProfesor.objects.create(nombre='A', apellido='A', cedula='1', laboratorio_interes=laboratorio)
        sin_lab = SolicitudRegistroProfesor.objects.create(nombre='B', apellido='B', cedula='2')
        SolicitudRegistroProfesor.objects.create(nombre='C', apellido='C', cedula='3', laboratorio_interes=otro)
        client.force_login(usuario_laboratorista)
        respuesta = client.get(reverse('lista_solicitudes_profesores'))
        assert set(respuesta.context['solicitudes']) == {propia, sin_lab}

    def test_rechazo_sin_motivo_falla(self, admin_cliente):
        solicitud = SolicitudRegistroProfesor.objects.create(nombre='P', apellido='S', cedula='5')
        respuesta = admin_cliente.post(reverse('detalle_solicitud_profesor', args=[solicitud.id]),
                                       {'accion': 'rechazar_profesor', 'motivo': '   '}, follow=True)
        assert 'Escribe el motivo del rechazo.' in [str(m) for m in respuesta.context['messages']]
        solicitud.refresh_from_db()
        assert solicitud.estado == 'pendiente'

    def test_detalle_sin_cursos_y_con_motivo(self, admin_cliente):
        solicitud = SolicitudRegistroProfesor.objects.create(nombre='P', apellido='S', cedula='5')
        contenido = admin_cliente.get(reverse('detalle_solicitud_profesor', args=[solicitud.id])).content.decode()
        assert 'name="motivo"' in contenido
        assert 'aprobar_curso' not in contenido and 'Cursos Solicitados' not in contenido

    def test_registro_publico_sin_cursos_y_con_laboratorio(self, client, laboratorio):
        contenido = client.get(reverse('registro_profesor_publico')).content.decode()
        assert 'curso_nombre' not in contenido
        assert 'name="laboratorio_interes"' in contenido and laboratorio.nombre in contenido
        assert 'type="password"' not in contenido


# ── Menú y tablero ──────────────────────────────────────────────────────

@pytest.mark.parametrize('fixture, ve_solicitudes, ve_habilitados', [
    ('usuario_admin', True, True),
    ('usuario_laboratorista', True, False),
    ('usuario_monitor', False, False),
    ('usuario_estudiante', False, False),
])
def test_menu_por_rol(client, request, fixture, ve_solicitudes, ve_habilitados):
    client.force_login(request.getfixturevalue(fixture))
    contenido = client.get('/', follow=True).content.decode()
    assert ('data-menu="solicitudes-profesor"' in contenido) is ve_solicitudes
    assert ('data-menu="profesores-habilitados"' in contenido) is ve_habilitados
    assert 'href="/usuarios/profesores/"' not in contenido or ve_habilitados


def test_contador_del_laboratorista_solo_cuenta_las_suyas(client, usuario_laboratorista, laboratorio):
    otro = Laboratorio.objects.create(nombre='Lab B', ubicacion='B')
    SolicitudRegistroProfesor.objects.create(nombre='A', apellido='A', cedula='1', laboratorio_interes=laboratorio)
    SolicitudRegistroProfesor.objects.create(nombre='C', apellido='C', cedula='3', laboratorio_interes=otro)
    client.force_login(usuario_laboratorista)
    assert client.get('/').context['notif_profesores'] == 1


def test_tablero_sin_panel_docente(client, usuario_estudiante):
    client.force_login(usuario_estudiante)
    contenido = client.get('/').content.decode()
    assert '/reservas/crear/' not in contenido
    assert 'Tus reservas recientes' not in contenido
    assert 'mis_reservas' not in client.get('/').context


def test_plantilla_mis_reservas_del_tablero_ya_no_existe():
    with pytest.raises(TemplateDoesNotExist):
        get_template('dashboard/partials/mis_reservas.html')


def test_rol_docente_no_existe_en_el_catalogo(catalogos):
    assert not Rol.objects.filter(nombre='Docente').exists()
