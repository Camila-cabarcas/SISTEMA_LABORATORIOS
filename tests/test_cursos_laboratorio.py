"""
Tests de la relación Curso ↔ Laboratorio: el campo Curso.laboratorio, la
columna/filtro de laboratorio en /solicitudes/cursos/, el management
command asignar_cursos_labs y la sección de cursos en el detalle del laboratorio.
"""
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from laboratorio.models import Laboratorio
from solicitudes.forms import CursoForm
from solicitudes.management.commands.asignar_cursos_labs import generar_codigos
from solicitudes.models import Curso, Profesor

pytestmark = pytest.mark.django_db


@pytest.fixture
def profesor(catalogos):
    """Profesor sin cuenta (fase 2: ya no hay cuentas Docente)."""
    return Profesor.objects.create(nombre='Ana', apellido='Gómez', cedula='1001')


@pytest.fixture
def labs_reales(db):
    """Mismos nombres que los laboratorios de la BD real."""
    return {
        'mecanica': Laboratorio.objects.create(nombre='LAB-Mecanica', ubicacion='B1'),
        'ondas': Laboratorio.objects.create(nombre='Laboratorio de ondas', ubicacion='B2'),
        'sistemas': Laboratorio.objects.create(nombre='Lab de Ingenieria de sistemas', ubicacion='B3'),
    }


def _curso(profesor, codigo, laboratorio=None, nombre='Curso'):
    return Curso.objects.create(
        nombre=nombre, codigo=codigo, profesor=profesor,
        cantidad_estudiantes=30, laboratorio=laboratorio,
    )


# ── Modelo / formulario ─────────────────────────────────────────────────────

def test_asignar_curso_a_laboratorio(profesor, laboratorio):
    curso = _curso(profesor, 'QUIM-101')
    curso.laboratorio = laboratorio
    curso.save()

    curso.refresh_from_db()
    assert curso.laboratorio == laboratorio
    assert list(laboratorio.cursos.all()) == [curso]


def test_fixture_curso(curso):
    assert curso.profesor.activo
    assert curso.laboratorio is None


def test_curso_form_rechaza_profesor_inactivo(profesor):
    profesor.activo = False
    profesor.save()
    form = CursoForm(data={
        'nombre': 'Química', 'codigo': 'QUIM-101', 'profesor': profesor.id,
        'cantidad_estudiantes': 25, 'laboratorio': '',
    })
    assert not form.is_valid()
    assert form.errors['profesor'] == ['Selecciona un profesor activo.']


def test_curso_form_guarda_en_profesor(profesor):
    form = CursoForm(data={
        'nombre': 'Química', 'codigo': 'QUIM-101', 'profesor': profesor.id,
        'cantidad_estudiantes': 25, 'laboratorio': '',
    })
    assert form.is_valid(), form.errors
    curso = form.save()
    assert curso.profesor == profesor


def test_str_muestra_laboratorio(profesor, laboratorio):
    assert str(_curso(profesor, 'QUIM-101', laboratorio, 'Química')) == 'QUIM-101 - Química (Laboratorio de Química)'
    assert str(_curso(profesor, 'FIS-101', None, 'Física')) == 'FIS-101 - Física'


def test_curso_form_permite_asignar_laboratorio(profesor, laboratorio):
    form = CursoForm(data={
        'nombre': 'Química', 'codigo': 'QUIM-101', 'profesor': profesor.id,
        'cantidad_estudiantes': 25, 'laboratorio': laboratorio.id,
    })

    assert form.is_valid(), form.errors
    assert form.save().laboratorio == laboratorio


def test_curso_form_laboratorio_es_opcional(profesor):
    form = CursoForm(data={
        'nombre': 'Química', 'codigo': 'QUIM-101', 'profesor': profesor.id,
        'cantidad_estudiantes': 25, 'laboratorio': '',
    })

    assert form.is_valid(), form.errors
    assert form.save().laboratorio is None


# ── Vista lista_cursos ──────────────────────────────────────────────────────

def test_lista_cursos_muestra_laboratorio(cliente_autenticado, profesor, laboratorio):
    _curso(profesor, 'QUIM-101', laboratorio)

    response = cliente_autenticado.get('/solicitudes/cursos/')

    assert response.status_code == 200
    contenido = response.content.decode()
    assert '<th>Laboratorio</th>' in contenido
    assert 'Laboratorio de Química' in contenido


def test_lista_cursos_filtra_por_laboratorio(cliente_autenticado, profesor, labs_reales):
    _curso(profesor, 'MECAN-101', labs_reales['mecanica'])
    _curso(profesor, 'ONDAS-101', labs_reales['ondas'])
    _curso(profesor, 'LIBRE-101', None)

    response = cliente_autenticado.get('/solicitudes/cursos/', {'laboratorio': labs_reales['ondas'].id})
    assert [c.codigo for c in response.context['cursos']] == ['ONDAS-101']

    response = cliente_autenticado.get('/solicitudes/cursos/', {'laboratorio': 'ninguno'})
    assert [c.codigo for c in response.context['cursos']] == ['LIBRE-101']

    response = cliente_autenticado.get('/solicitudes/cursos/')
    assert len(response.context['cursos']) == 3


def test_lista_cursos_ignora_filtro_invalido(cliente_autenticado, profesor, laboratorio):
    _curso(profesor, 'QUIM-101', laboratorio)

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


def test_command_crea_cursos_por_laboratorio(profesor, labs_reales):
    call_command('asignar_cursos_labs', stdout=StringIO())

    assert Curso.objects.count() == 9
    mecanica = Curso.objects.get(codigo='MECAN-101')
    assert mecanica.nombre == 'Mecánica I'
    assert mecanica.laboratorio == labs_reales['mecanica']
    assert mecanica.profesor == profesor
    assert 20 <= mecanica.cantidad_estudiantes <= 50
    assert set(labs_reales['ondas'].cursos.values_list('nombre', flat=True)) == {
        'Ondas y Óptica', 'Electromagnetismo',
    }
    assert set(labs_reales['sistemas'].cursos.values_list('nombre', flat=True)) == {
        'Sistemas Digitales', 'Microprocesadores', 'Telecomunicaciones', 'Redes',
    }


def test_command_es_idempotente(profesor, labs_reales):
    call_command('asignar_cursos_labs', stdout=StringIO())
    antes = list(Curso.objects.order_by('codigo').values_list(
        'codigo', 'nombre', 'profesor_id', 'cantidad_estudiantes', 'laboratorio_id'))

    salida = StringIO()
    call_command('asignar_cursos_labs', stdout=salida)

    despues = list(Curso.objects.order_by('codigo').values_list(
        'codigo', 'nombre', 'profesor_id', 'cantidad_estudiantes', 'laboratorio_id'))
    assert despues == antes
    assert 'Cursos creados: 0 | laboratorio actualizado: 0 | sin cambios: 9' in salida.getvalue()


def test_command_corrige_laboratorio_de_curso_existente(profesor, labs_reales):
    _curso(profesor, 'MECAN-101', None, 'Mecánica I')

    call_command('asignar_cursos_labs', stdout=StringIO())

    assert Curso.objects.get(codigo='MECAN-101').laboratorio == labs_reales['mecanica']


def test_command_omite_laboratorios_inexistentes(profesor, db):
    Laboratorio.objects.create(nombre='LAB-Mecanica', ubicacion='B1')
    salida = StringIO()

    call_command('asignar_cursos_labs', stdout=salida)

    assert set(Curso.objects.values_list('codigo', flat=True)) == {'MECAN-101', 'MECAN-102', 'TERMO-101'}
    assert 'Laboratorio no encontrado' in salida.getvalue()


def test_command_sin_docentes_falla(labs_reales, catalogos):
    with pytest.raises(CommandError):
        call_command('asignar_cursos_labs', stdout=StringIO())
    assert Curso.objects.count() == 0


# ── Detalle de laboratorio ──────────────────────────────────────────────────

def test_detalle_laboratorio_incluye_cursos_en_contexto(cliente_autenticado, profesor, labs_reales):
    mecanica = labs_reales['mecanica']
    _curso(profesor, 'MECAN-102', mecanica, 'Mecánica II')
    _curso(profesor, 'MECAN-101', mecanica, 'Mecánica I')
    _curso(profesor, 'ONDAS-101', labs_reales['ondas'], 'Ondas y Óptica')

    response = cliente_autenticado.get(f'/laboratorio/{mecanica.id}/?seccion=cursos')

    assert response.status_code == 200
    assert [c.codigo for c in response.context['cursos']] == ['MECAN-101', 'MECAN-102']


def test_detalle_laboratorio_renderiza_tabla_de_cursos(cliente_autenticado, profesor, laboratorio):
    _curso(profesor, 'QUIM-101', laboratorio, 'Química General')

    contenido = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/?seccion=cursos').content.decode()

    assert 'Cursos asignados' in contenido
    assert '<td>QUIM-101</td>' in contenido
    assert '<td>Química General</td>' in contenido
    assert '<td>Ana Gómez</td>' in contenido
    assert '<td>30</td>' in contenido
    assert 'No hay cursos asignados' not in contenido


def test_detalle_laboratorio_sin_cursos_muestra_mensaje(cliente_autenticado, laboratorio):
    response = cliente_autenticado.get(f'/laboratorio/{laboratorio.id}/?seccion=cursos')

    assert list(response.context['cursos']) == []
    assert 'No hay cursos asignados a este laboratorio.' in response.content.decode()
