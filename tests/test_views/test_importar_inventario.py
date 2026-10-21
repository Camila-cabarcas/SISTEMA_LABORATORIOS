"""
Tests HTTP de /inventario/importar/ (ImportarInventarioView, fase 1):
permisos, formulario, preview y errores. La fase 1 nunca escribe en la BD.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from inventario.models import Insumo, ItemInventario

pytestmark = pytest.mark.django_db

URL = '/inventario/importar/'

CSV = 'Código,Nombre,Marca,Cantidad\nMUL-01,Multímetro,Fluke,3\nOSC-01,Osciloscopio,Tek,1\n'.encode()


def _post(client, laboratorio, nombre='inv.csv', contenido=CSV):
    datos = {'archivo': SimpleUploadedFile(nombre, contenido)}
    if laboratorio is not None:
        datos['laboratorio'] = laboratorio.id
    return client.post(URL, datos)


class TestPermisos:

    def test_admin_ve_el_formulario(self, cliente_autenticado):
        resp = cliente_autenticado.get(URL)
        assert resp.status_code == 200
        assert resp.context['seccion_activa'] == 'importar'
        assert b'form-importar' in resp.content

    def test_laboratorista_no_puede(self, client, usuario_laboratorista):
        client.force_login(usuario_laboratorista)
        resp = client.get(URL)
        assert resp.status_code == 302
        assert 'login' not in resp.url

    def test_anonimo_va_al_login(self, client):
        resp = client.get(URL)
        assert resp.status_code == 302
        assert 'login' in resp.url

    def test_link_en_el_sidebar_solo_para_admin(self, cliente_autenticado):
        assert b'/inventario/importar/' in cliente_autenticado.get('/inventario/items/').content


class TestPreview:

    def test_csv_muestra_preview(self, cliente_autenticado, laboratorio):
        resp = _post(cliente_autenticado, laboratorio)
        assert resp.status_code == 200
        preview = resp.context['preview']
        assert preview['laboratorio'] == laboratorio
        assert preview['total_filas'] == 2
        assert preview['mapeo'] == {'Código': 'codigo', 'Nombre': 'nombre', 'Marca': 'marca', 'Cantidad': 'cantidad'}
        assert 'Osciloscopio' in resp.content.decode()

    def test_no_guarda_nada(self, cliente_autenticado, laboratorio):
        _post(cliente_autenticado, laboratorio)
        assert not Insumo.objects.exists()
        assert not ItemInventario.objects.exists()

    def test_laboratorio_inactivo_no_se_ofrece(self, cliente_autenticado, laboratorio):
        laboratorio.activo = False
        laboratorio.save()
        resp = _post(cliente_autenticado, laboratorio)
        assert resp.context['preview'] is None
        assert 'laboratorio' in resp.context['form'].errors


class TestErrores:

    def test_sin_laboratorio(self, cliente_autenticado):
        resp = _post(cliente_autenticado, None)
        assert resp.context['preview'] is None
        assert 'laboratorio' in resp.context['form'].errors

    def test_sin_archivo(self, cliente_autenticado, laboratorio):
        resp = cliente_autenticado.post(URL, {'laboratorio': laboratorio.id})
        assert 'archivo' in resp.context['form'].errors

    def test_extension_invalida(self, cliente_autenticado, laboratorio):
        resp = _post(cliente_autenticado, laboratorio, 'inv.docx', b'algo')
        assert 'Formato no soportado' in resp.context['form'].errors['archivo'][0]
        assert 'is-invalid' in resp.content.decode()

    def test_excel_corrupto_muestra_error(self, cliente_autenticado, laboratorio):
        resp = _post(cliente_autenticado, laboratorio, 'inv.xlsx', b'no es un excel')
        assert resp.status_code == 200
        assert resp.context['preview'] is None
        assert 'Excel' in resp.context['error']
        assert b'error-importacion' in resp.content

    def test_error_inesperado_no_rompe_la_pagina(self, cliente_autenticado, laboratorio, monkeypatch):
        from inventario.services.importador import ImportadorInventario

        def falla(self, *a, **k):
            raise RuntimeError('boom')

        monkeypatch.setattr(ImportadorInventario, 'preview', falla)
        resp = _post(cliente_autenticado, laboratorio)
        assert resp.status_code == 200
        assert 'No se pudo procesar el archivo' in resp.context['error']
