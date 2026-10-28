"""
Tests de CategoriaModulo (laboratorio/models.py), su migración de datos
(0018_sembrar_categorias) y cómo se describe un módulo con categoría.
"""
import importlib

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from laboratorio.models import CategoriaModulo, Division, Modulo

pytestmark = pytest.mark.django_db

migracion = importlib.import_module('laboratorio.migrations.0018_sembrar_categorias')


def _sembrar():
    migracion.sembrar_categorias(django_apps, None)


def _categoria(nombre='Proyector', color='#6f42c1', forma='circulo', **extra):
    return CategoriaModulo.objects.create(nombre=nombre, color=color, forma=forma, **extra)


# ── Migración de datos ────────────────────────────────────────────────────

class TestSembrarCategorias:

    def test_siembra_las_tres_categorias_base(self):
        CategoriaModulo.objects.all().delete()
        _sembrar()
        assert {(c.nombre, c.color, c.forma, c.activo) for c in CategoriaModulo.objects.all()} == {
            ('Mesa', '#0d6efd', 'cuadrado', True),         # azul, forma original
            ('Computador', '#198754', 'computador', True),  # verde
            ('Maquinaria', '#fd7e14', 'maquinaria', True),  # naranja
        }

    def test_es_idempotente(self):
        CategoriaModulo.objects.all().delete()
        _sembrar()
        _sembrar()
        _sembrar()
        assert CategoriaModulo.objects.count() == 3

    def test_no_pisa_cambios_del_administrador(self):
        CategoriaModulo.objects.all().delete()
        _sembrar()
        mesa = CategoriaModulo.objects.get(nombre='Mesa')
        mesa.color, mesa.forma, mesa.activo = '#000000', 'rombo', False
        mesa.save()

        _sembrar()

        mesa.refresh_from_db()
        assert (mesa.color, mesa.forma, mesa.activo) == ('#000000', 'rombo', False)

    def test_reconoce_nombres_sin_distinguir_mayusculas(self):
        CategoriaModulo.objects.all().delete()
        _categoria(nombre='MESA', color='#111111', forma='cuadrado')
        _sembrar()
        assert CategoriaModulo.objects.filter(nombre__iexact='mesa').count() == 1

    def test_la_migracion_ejecuta_la_siembra(self):
        operacion = migracion.Migration.operations[0]
        assert operacion.code is migracion.sembrar_categorias


# ── Modelo ────────────────────────────────────────────────────────────────

class TestCategoriaModulo:

    @pytest.mark.parametrize('color', ['azul', '#12345', '#GGGGGG', '0d6efd'])
    def test_color_debe_ser_hex(self, color):
        with pytest.raises(ValidationError) as e:
            CategoriaModulo(nombre='X', color=color, forma='cuadrado').full_clean()
        assert 'color' in e.value.message_dict

    def test_forma_debe_ser_valida(self):
        with pytest.raises(ValidationError) as e:
            CategoriaModulo(nombre='X', color='#123456', forma='estrella').full_clean()
        assert 'forma' in e.value.message_dict

    def test_nombre_unico_sin_distinguir_mayusculas(self):
        _categoria(nombre='Proyector')
        with pytest.raises(ValidationError) as e:
            CategoriaModulo(nombre='proyector', color='#123456', forma='cuadrado').full_clean()
        assert 'nombre' in e.value.message_dict

    def test_no_se_puede_borrar_con_modulos(self, laboratorio):
        cat = _categoria()
        Modulo.objects.create(nombre='M', capacidad=1, laboratorio=laboratorio, categoria=cat)
        with pytest.raises(ProtectedError):
            cat.delete()
        assert CategoriaModulo.objects.filter(id=cat.id).exists()

    def test_se_puede_borrar_sin_modulos(self):
        cat = _categoria()
        cat.delete()
        assert not CategoriaModulo.objects.filter(id=cat.id).exists()


class TestModuloConCategoria:

    def test_sin_categoria_usa_gris_y_forma_original(self, laboratorio):
        m = Modulo.objects.create(nombre='M', capacidad=1, laboratorio=laboratorio)
        assert m.color_categoria == '#6c757d'
        assert m.forma_categoria == 'cuadrado'

    def test_con_categoria_usa_su_color_y_forma(self, laboratorio):
        m = Modulo.objects.create(nombre='M', capacidad=1, laboratorio=laboratorio,
                                  categoria=_categoria(color='#6f42c1', forma='circulo'))
        assert (m.color_categoria, m.forma_categoria) == ('#6f42c1', 'circulo')

    def test_descripcion_completa(self, laboratorio):
        d = Division.objects.create(laboratorio=laboratorio, nombre='Salón A')
        cat = _categoria(nombre='Proyector')
        assert Modulo.objects.create(nombre='M1', capacidad=1, laboratorio=laboratorio,
                                     categoria=cat, division=d).descripcion_completa == 'M1 · Proyector · Salón A'
        assert Modulo.objects.create(nombre='M2', capacidad=1, laboratorio=laboratorio,
                                     categoria=cat).descripcion_completa == 'M2 · Proyector'
        assert Modulo.objects.create(nombre='M3', capacidad=1, laboratorio=laboratorio).descripcion_completa == 'M3'

    def test_str_incluye_la_categoria(self, laboratorio):
        m = Modulo.objects.create(nombre='M1', capacidad=1, laboratorio=laboratorio, categoria=_categoria(nombre='Proyector'))
        assert str(m) == 'M1 (Laboratorio de Química) — Proyector'
        sin = Modulo.objects.create(nombre='M2', capacidad=1, laboratorio=laboratorio)
        assert str(sin) == 'M2 (Laboratorio de Química)'


class TestExcel:

    def test_columna_modulos_incluye_categoria(self, laboratorio, catalogos):
        from django.utils import timezone

        from reservas.models import EstadoReserva, Reserva
        from solicitudes.models import SolicitudReserva
        from utils.excel_export import export_reservas_excel

        reserva = Reserva.objects.create(fecha_reserva=timezone.now(), estado=EstadoReserva.objects.get(nombre='Aprobada'))
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', nombre='Ana', cedula='1', laboratorio=laboratorio,
            fecha_reserva=reserva.fecha_reserva, reserva=reserva,
        )
        solicitud.modulos_asignados.set([
            Modulo.objects.create(nombre='PC 1', capacidad=1, laboratorio=laboratorio, categoria=_categoria(nombre='Proyector')),
        ])

        hoja = export_reservas_excel([reserva]).active
        valores = [c.value for fila in hoja.iter_rows() for c in fila]
        assert 'PC 1 · Proyector' in valores
