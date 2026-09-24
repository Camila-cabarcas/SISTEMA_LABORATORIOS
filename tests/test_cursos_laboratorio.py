"""
Tests de la relación Curso ↔ Laboratorio: el campo Curso.laboratorio, la
columna/filtro de laboratorio en /solicitudes/cursos/ y el management
command asignar_cursos_labs.
"""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from laboratorio.models import Laboratorio
from solicitudes.forms import CursoForm
from solicitudes.management.commands.asignar_cursos_labs import generar_codigos
from solicitudes.models import Curso
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def docente(catalogos):
    return Usuario.objects.create_user(
        username='docente_test', password='clave12345',
        rol=Rol.objects.get(nombre='Docente'), codigo='DOC_TEST_001',
        first_name='Ana', last_name='Gómez',
    )


@pytest.fixture
def labs_reales(db):
    """Mismos nombres que los laboratorios de la BD real."""
    return {
        'mecanica': Laboratorio.objects.create(nombre='LAB-Mecanica', ubicacion='B1'),
        'ondas': Laboratorio.objects.create(nombre='Laboratorio de ondas', ubicacion='B2'),
        'sistemas': Laboratorio.objects.create(nombre='Lab de Ingenieria de sistemas', ubicacion='B3'),
    }


def _curso(docente, codigo, laboratorio=None, nombre='Curso'):
    return Curso.objects.create(
        nombre=nombre, codigo=codigo, profesor=docente,
        cantidad_estudiantes=30, laboratorio=laboratorio,
    )


# ── Modelo / formulario ─────────────────────────────────────────────────────

def test_asignar_curso_a_laboratorio(docente, laboratorio):
    curso = _curso(docente, 'QUIM-101')
    curso.laboratorio = laboratorio
    curso.save()

    curso.refresh_from_db()
    assert curso.laboratorio == laboratorio
    assert list(laboratorio.cursos.all()) == [curso]


def test_str_muestra_laboratorio(docente, laboratorio):
    assert str(_curso(docente, 'QUIM-101', laboratorio, 'Química')) == 'QUIM-101 - Química (Laboratorio de Química)'
    assert str(_curso(docente, 'FIS-101', None, 'Física')) == 'FIS-101 - Física'


def test_curso_form_permite_asignar_laboratorio(docente, laboratorio):
    form = CursoForm(data={
        'nombre': 'Química', 'codigo': 'QUIM-101', 'profesor': docente.id,
        'cantidad_estudiantes': 25, 'laboratorio': laboratorio.id,
    })

    assert form.is_valid(), form.errors
    assert form.save().laboratorio == laboratorio


def test_curso_form_laboratorio_es_opcional(docente):
    form = CursoForm(data={
        'nombre': 'Química', 'codigo': 'QUIM-101', 'profesor': docente.id,
        'cantidad_estudiantes': 25, 'laboratorio': '',
    })

    assert form.is_valid(), form.errors
    assert form.save().laboratorio is None


# ── Vista lista_cursos ──────────────────────────────────────────────────────

def test_lista_cursos_muestra_laboratorio(cliente_autenticado, docente, laboratorio):
    _curso(docente, 'QUIM-101', laboratorio)

    response = cliente_autenticado.get('/solicitudes/cursos/')

    assert response.status_code == 200
    contenido = response.content.decode()
    assert '<th>Laboratorio</th>' in contenido
    assert 'Laboratorio de Química' in contenido


def test_lista_cursos_filtra_por_laboratorio(cliente_autenticado, docente, labs_reales):
    _curso(docente, 'MECAN-101', labs_reales['mecanica'])
    _curso(docente, 'ONDAS-101', labs_reales['ondas'])
    _curso(docente, 'LIBRE-101', None)

    response = cliente_autenticado.get('/solicitudes/cursos/', {'laboratorio': labs_reales['ondas'].id})
    assert [c.codigo for c in response.context['cursos']] == ['ONDAS-101']

    response = cliente_autenticado.get('/solicitudes/cursos/', {'laboratorio': 'ninguno'})
    assert [c.codigo for c in response.context['cursos']] == ['LIBRE-101']

    response = cliente_autenticado.get('/solicitudes/cursos/')
    assert len(response.context['cursos']) == 3


def test_lista_cursos_ignora_filtro_invalido(cliente_autenticado, docente, laboratorio):
    _curso(docente, 'QUIM-101', laboratorio)

    response = cliente_autenticado.get('/solicitudes/cursos/', {'laboratorio': 'abc'})

    assert response.status_code == 200
    assert len(response.context['cursos']) == 1
    assert response.context['laboratorio_id'] == ''


# ── Management command ──────────────────────────────────────────────────────

def test_generar_codigos():
    codigos = generar_codigos(['Mecánica I', 'Mecánica II', 'Termodinámica', 'Ondas y Óptica'])

    assert codigos == {
        'Mecánica I': 'MECAN-101',
        'Mecánica II': 'MECAN-102',
        'Termodinámica': 'TERMO-101',
        'Ondas y Óptica': 'ONDAS-101',
    }


def test_command_crea_cursos_por_laboratorio(docente, labs_reales):
    call_command('asignar_cursos_labs', stdout=StringIO())

    assert Curso.objects.count() == 9
    mecanica = Curso.objects.get(codigo='MECAN-101')
    assert mecanica.nombre == 'Mecánica I'
    assert mecanica.laboratorio == labs_reales['mecanica']
    assert mecanica.profesor == docente
    assert 20 <= mecanica.cantidad_estudiantes <= 50
    assert set(labs_reales['ondas'].cursos.values_list('nombre', flat=True)) == {
        'Ondas y Óptica', 'Electromagnetismo',
    }
    assert set(labs_reales['sistemas'].cursos.values_list('nombre', flat=True)) == {
        'Sistemas Digitales', 'Microprocesadores', 'Telecomunicaciones', 'Redes',
    }


def test_command_es_idempotente(docente, labs_reales):
    call_command('asignar_cursos_labs', stdout=StringIO())
    antes = list(Curso.objects.order_by('codigo').values_list(
        'codigo', 'nombre', 'profesor_id', 'cantidad_estudiantes', 'laboratorio_id'))

    salida = StringIO()
    call_command('asignar_cursos_labs', stdout=salida)

    despues = list(Curso.objects.order_by('codigo').values_list(
        'codigo', 'nombre', 'profesor_id', 'cantidad_estudiantes', 'laboratorio_id'))
    assert despues == antes
    assert 'Cursos creados: 0 | laboratorio actualizado: 0 | sin cambios: 9' in salida.getvalue()


def test_command_corrige_laboratorio_de_curso_existente(docente, labs_reales):
    _curso(docente, 'MECAN-101', None, 'Mecánica I')

    call_command('asignar_cursos_labs', stdout=StringIO())

    assert Curso.objects.get(codigo='MECAN-101').laboratorio == labs_reales['mecanica']


def test_command_omite_laboratorios_inexistentes(docente, db):
    Laboratorio.objects.create(nombre='LAB-Mecanica', ubicacion='B1')
    salida = StringIO()

    call_command('asignar_cursos_labs', stdout=salida)

    assert set(Curso.objects.values_list('codigo', flat=True)) == {'MECAN-101', 'MECAN-102', 'TERMO-101'}
    assert 'Laboratorio no encontrado' in salida.getvalue()


def test_command_sin_docentes_falla(labs_reales, catalogos):
    with pytest.raises(CommandError):
        call_command('asignar_cursos_labs', stdout=StringIO())
    assert Curso.objects.count() == 0
