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


# ══ Fase 2: mapear → validar → confirmar ══════════════════════════════════

URL_MAPEAR = '/inventario/importar/mapear/'
URL_VALIDAR = '/inventario/importar/validar/'
URL_CONFIRMAR = '/inventario/importar/confirmar/'

CSV_FASE2 = (
    'Código,Nombre,Marca,Estado\n'
    'MUL-01,Multímetro,Fluke,Bueno\n'
    'MUL-02,Multímetro,Fluke,\n'
    'OSC-01,Osciloscopio,Tek,Dañado\n'
    'MUL-01,Repetido,,\n'
    ',Sin código,,\n'
).encode()


@pytest.fixture
def subido(cliente_autenticado, laboratorio, catalogos):
    """Paso 1 hecho: el archivo ya está en la sesión."""
    _post(cliente_autenticado, laboratorio, contenido=CSV_FASE2)
    return cliente_autenticado


def _mapear(client, **por_indice):
    """POST del paso 2: col_<i>=<campo> (por defecto el mapeo de CSV_FASE2)."""
    datos = por_indice or {'col_0': 'codigo', 'col_1': 'nombre', 'col_2': 'marca', 'col_3': 'estado'}
    return client.post(URL_MAPEAR, datos)


class TestSesion:

    def test_paso_1_guarda_la_tabla_en_sesion(self, subido, laboratorio):
        datos = subido.session['importacion_inventario']
        assert datos['laboratorio_id'] == laboratorio.id
        assert datos['columnas'] == ['Código', 'Nombre', 'Marca', 'Estado']
        assert len(datos['filas']) == 5
        assert datos['mapeo'] == {'Código': 'codigo', 'Nombre': 'nombre', 'Marca': 'marca', 'Estado': 'estado'}

    def test_paso_1_muestra_boton_siguiente(self, cliente_autenticado, laboratorio):
        resp = _post(cliente_autenticado, laboratorio)
        assert URL_MAPEAR.encode() in resp.content

    @pytest.mark.parametrize('url', [URL_MAPEAR, URL_VALIDAR, URL_CONFIRMAR])
    def test_sin_archivo_en_sesion_vuelve_al_paso_1(self, cliente_autenticado, url):
        resp = cliente_autenticado.get(url)
        assert resp.status_code == 302
        assert resp.url == URL

    def test_validar_sin_mapeo_confirmado_va_a_mapear(self, subido):
        resp = subido.get(URL_VALIDAR)
        assert resp.url == URL_MAPEAR

    def test_laboratorio_desactivado_entre_pasos(self, subido, laboratorio):
        laboratorio.activo = False
        laboratorio.save()
        resp = subido.get(URL_MAPEAR)
        assert resp.url == URL
        assert 'importacion_inventario' not in subido.session

    @pytest.mark.parametrize('url', [URL_MAPEAR, URL_VALIDAR, URL_CONFIRMAR])
    def test_solo_admin(self, client, usuario_laboratorista, url):
        client.force_login(usuario_laboratorista)
        resp = client.get(url)
        assert resp.status_code == 302
        assert resp.url != URL


class TestMapearView:

    def test_muestra_preview_y_desplegables(self, subido):
        resp = subido.get(URL_MAPEAR)
        assert resp.status_code == 200
        assert resp.context['paso'] == 2
        assert [c['campo'] for c in resp.context['columnas']] == ['codigo', 'nombre', 'marca', 'estado']
        assert len(resp.context['filas']) == 5
        html = resp.content.decode()
        assert 'name="col_0"' in html and 'name="col_3"' in html
        assert 'Osciloscopio' in html

    def test_guarda_el_mapeo_y_sigue_a_validar(self, subido):
        resp = _mapear(subido, col_0='codigo', col_1='nombre')  # Marca y Estado ignoradas
        assert resp.status_code == 302
        assert resp.url == URL_VALIDAR
        assert subido.session['importacion_inventario']['mapeo'] == {'Código': 'codigo', 'Nombre': 'nombre'}

    def test_mapeo_incompleto_muestra_errores(self, subido):
        resp = _mapear(subido, col_1='nombre')
        assert resp.status_code == 200
        assert any('Código' in e for e in resp.context['errores'])
        assert b'errores-mapeo' in resp.content
        assert not subido.session['importacion_inventario'].get('mapeo_confirmado')

    def test_campo_repetido_muestra_error(self, subido):
        resp = _mapear(subido, col_0='codigo', col_1='nombre', col_2='nombre')
        assert any('dos columnas' in e for e in resp.context['errores'])
        # Se conserva lo que eligió el usuario para que lo corrija.
        assert [c['campo'] for c in resp.context['columnas']][:3] == ['codigo', 'nombre', 'nombre']


class TestValidarView:

    def test_simula_y_resume(self, subido):
        from inventario.models import Insumo, ItemInventario

        _mapear(subido)
        resp = subido.get(URL_VALIDAR)
        resumen = resp.context['resumen']

        assert [i['nombre'] for i in resumen['insumos_nuevos']] == ['Multímetro', 'Osciloscopio']
        assert [i['codigo'] for i in resumen['items']] == ['MUL-01', 'MUL-02', 'OSC-01']
        assert [s['mensaje'] for s in resumen['saltadas']] == [
            'Fila 5: Código duplicado "MUL-01" (ya existe en el archivo, fila 2)',
        ]
        assert [e['mensaje'] for e in resumen['errores']] == ['Fila 6: Código vacío']
        html = resp.content.decode()
        assert 'Se guardarán 2 insumos nuevos' in html
        assert '3 ítems' in html
        assert '2 filas saltadas' in html
        assert not Insumo.objects.exists()
        assert not ItemInventario.objects.exists()

    def test_sin_items_validos_desactiva_guardar(self, cliente_autenticado, laboratorio, catalogos):
        _post(cliente_autenticado, laboratorio, contenido='Código,Nombre,Estado\nA-1,Pipeta,Regular\n'.encode())
        _mapear(cliente_autenticado, col_0='codigo', col_1='nombre', col_2='estado')
        html = cliente_autenticado.get(URL_VALIDAR).content.decode()
        assert 'disabled' in html.split('id="form-confirmar"')[1]


class TestConfirmarView:

    def test_guarda_y_muestra_reporte(self, subido, laboratorio, usuario_admin):
        from inventario.models import Insumo, ItemInventario, MovimientoInventario

        _mapear(subido)
        resp = subido.post(URL_CONFIRMAR)
        assert resp.status_code == 302
        assert resp.url == URL_CONFIRMAR

        assert set(Insumo.objects.values_list('nombre', flat=True)) == {'Multímetro', 'Osciloscopio'}
        assert set(ItemInventario.objects.values_list('codigo', flat=True)) == {'MUL-01', 'MUL-02', 'OSC-01'}
        assert ItemInventario.objects.get(codigo='OSC-01').estado.nombre == 'Dañado'
        assert MovimientoInventario.objects.filter(usuario=usuario_admin).count() == 3

        reporte = subido.get(URL_CONFIRMAR)
        assert reporte.status_code == 200
        resumen = reporte.context['resumen']
        assert resumen['laboratorio'] == laboratorio.nombre
        assert resumen['filas_saltadas'] == 2
        html = reporte.content.decode()
        assert 'Importación completada' in html
        assert 'Fila 6: Código vacío' in html

    def test_no_se_puede_importar_dos_veces(self, subido):
        from inventario.models import ItemInventario

        _mapear(subido)
        subido.post(URL_CONFIRMAR)
        assert 'importacion_inventario' not in subido.session

        resp = subido.post(URL_CONFIRMAR)  # doble clic / reenvío
        assert resp.url == URL
        assert ItemInventario.objects.count() == 3

    def test_recargar_el_reporte_no_reimporta(self, subido):
        from inventario.models import ItemInventario

        _mapear(subido)
        subido.post(URL_CONFIRMAR)
        subido.get(URL_CONFIRMAR)
        subido.get(URL_CONFIRMAR)
        assert ItemInventario.objects.count() == 3

    def test_error_al_guardar_no_deja_nada_y_vuelve_a_validar(self, subido, monkeypatch):
        from inventario.models import Insumo
        from inventario.services.importador import ImportadorInventario

        def falla(self, *a, **k):
            raise RuntimeError('boom')

        monkeypatch.setattr(ImportadorInventario, 'guardar', falla)
        _mapear(subido)
        resp = subido.post(URL_CONFIRMAR)
        assert resp.url == URL_VALIDAR
        assert not Insumo.objects.exists()
        # La importación sigue en curso para reintentar.
        assert 'importacion_inventario' in subido.session

    def test_subir_otro_archivo_limpia_el_reporte_anterior(self, subido, laboratorio):
        _mapear(subido)
        subido.post(URL_CONFIRMAR)
        _post(subido, laboratorio)
        assert 'importacion_inventario_resultado' not in subido.session
