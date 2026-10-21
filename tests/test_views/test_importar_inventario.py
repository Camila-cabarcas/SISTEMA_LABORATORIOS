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


# ══ Cancelar (retrocede un paso) ═══════════════════════════════════════════

URL_CANCELAR = '/inventario/importar/cancelar/'
SESION = 'importacion_inventario'
MAPEO_DETECTADO = {'Código': 'codigo', 'Nombre': 'nombre', 'Marca': 'marca', 'Estado': 'estado'}


def _cancelar(client, paso, **kwargs):
    return client.post(URL_CANCELAR, {'paso': paso}, **kwargs)


class TestBotonCancelar:

    def test_en_importar_junto_a_siguiente(self, cliente_autenticado, laboratorio):
        html = _post(cliente_autenticado, laboratorio).content.decode()
        bloque = html.split('btn-siguiente-mapear')[0].rsplit('<div', 1)[1]
        assert 'btn-cancelar-importacion' in bloque
        assert 'name="paso" value="importar"' in html

    def test_importar_sin_archivo_no_muestra_cancelar(self, cliente_autenticado):
        assert b'btn-cancelar-importacion' not in cliente_autenticado.get(URL).content

    def test_en_mapear_dentro_del_form_pero_envia_el_de_cancelar(self, subido):
        html = subido.get(URL_MAPEAR).content.decode()
        form_mapear = html.split('id="form-mapear"')[1].split('</form>')[0]
        assert 'form="form-cancelar-importacion"' in form_mapear
        assert 'name="paso" value="mapear"' in html

    def test_en_validar_junto_a_guardar(self, subido):
        _mapear(subido)
        html = subido.get(URL_VALIDAR).content.decode()
        assert 'btn-cancelar-importacion' in html
        assert 'name="paso" value="validar"' in html
        assert html.count('id="form-cancelar-importacion"') == 1


class TestCancelarEnImportar:

    def test_se_queda_en_importar_con_el_formulario_vacio(self, subido):
        resp = _cancelar(subido, 'importar', follow=True)

        assert resp.redirect_chain == [(URL, 302)]
        assert resp.context['paso'] == 1
        assert resp.context['preview'] is None
        assert 'Archivo descartado' in resp.content.decode()
        assert SESION not in subido.session

    def test_puede_subir_otro_archivo(self, subido, laboratorio):
        _cancelar(subido, 'importar')
        resp = _post(subido, laboratorio, contenido='Código,Nombre\nZ-1,Probeta\n'.encode())
        assert resp.context['preview']['filas'] == [['Z-1', 'Probeta']]
        assert subido.session[SESION]['columnas'] == ['Código', 'Nombre']

    def test_borra_tambien_un_reporte_anterior(self, subido, laboratorio):
        _mapear(subido)
        subido.post(URL_CONFIRMAR)
        _post(subido, laboratorio, contenido=CSV_FASE2)
        _cancelar(subido, 'importar')
        assert 'importacion_inventario_resultado' not in subido.session

    def test_sin_paso_equivale_a_importar(self, subido):
        resp = subido.post(URL_CANCELAR)
        assert resp.url == URL
        assert SESION not in subido.session


class TestCancelarEnMapear:

    def test_vuelve_a_importar_con_el_archivo_cargado(self, subido):
        resp = _cancelar(subido, 'mapear', follow=True)

        assert resp.redirect_chain == [(URL, 302)]
        assert resp.context['paso'] == 1
        preview = resp.context['preview']
        assert preview['total_filas'] == 5
        assert 'Osciloscopio' in resp.content.decode()
        # Desde ahí puede seguir con el mismo archivo.
        assert b'btn-siguiente-mapear' in resp.content

    def test_limpia_el_mapeo(self, subido):
        _mapear(subido, col_0='nombre', col_1='codigo')  # mapeo hecho a mano
        _cancelar(subido, 'mapear')

        datos = subido.session[SESION]
        assert datos['mapeo'] == MAPEO_DETECTADO  # vuelve al detectado
        assert 'mapeo_confirmado' not in datos
        assert subido.get(URL_VALIDAR).url == URL_MAPEAR

    def test_conserva_laboratorio_elegido(self, subido, laboratorio):
        resp = _cancelar(subido, 'mapear', follow=True)
        assert resp.context['preview']['laboratorio'] == laboratorio
        assert resp.context['form'].initial['laboratorio'] == laboratorio


class TestCancelarEnValidar:

    def test_vuelve_a_mapear(self, subido):
        _mapear(subido)
        resp = _cancelar(subido, 'validar', follow=True)

        assert resp.redirect_chain == [(URL_MAPEAR, 302)]
        assert resp.context['paso'] == 2

    def test_limpia_la_validacion_pero_conserva_el_mapeo(self, subido):
        _mapear(subido, col_0='codigo', col_1='nombre')  # Marca y Estado ignoradas
        _cancelar(subido, 'validar')

        datos = subido.session[SESION]
        assert 'mapeo_confirmado' not in datos
        assert datos['mapeo'] == {'Código': 'codigo', 'Nombre': 'nombre'}
        # Hay que volver a pasar por Mapear para validar o guardar.
        assert subido.get(URL_VALIDAR).url == URL_MAPEAR
        assert subido.post(URL_CONFIRMAR).url == URL_MAPEAR

    def test_mapear_muestra_el_mapeo_conservado(self, subido):
        _mapear(subido, col_0='codigo', col_1='nombre')
        resp = _cancelar(subido, 'validar', follow=True)
        assert [c['campo'] for c in resp.context['columnas']] == ['codigo', 'nombre', '', '']


class TestCancelarGeneral:

    @pytest.mark.parametrize('paso', ['importar', 'mapear', 'validar'])
    def test_nunca_guarda_nada(self, subido, paso):
        from inventario.models import Insumo, ItemInventario

        _mapear(subido)
        _cancelar(subido, paso)
        assert not Insumo.objects.exists()
        assert not ItemInventario.objects.exists()

    @pytest.mark.parametrize('paso', ['mapear', 'validar'])
    def test_sin_archivo_en_sesion_va_a_importar(self, cliente_autenticado, paso):
        resp = _cancelar(cliente_autenticado, paso)
        assert resp.url == URL

    def test_paso_desconocido(self, subido):
        assert _cancelar(subido, 'otro').status_code == 400
        assert SESION in subido.session

    def test_no_toca_el_resto_de_la_sesion(self, subido):
        session = subido.session
        session['otra_cosa'] = 'se queda'
        session.save()
        _cancelar(subido, 'importar')
        assert subido.session['otra_cosa'] == 'se queda'

    def test_get_no_cancela(self, subido):
        assert subido.get(URL_CANCELAR).status_code == 405
        assert SESION in subido.session

    def test_solo_admin(self, client, usuario_laboratorista):
        client.force_login(usuario_laboratorista)
        resp = _cancelar(client, 'importar')
        assert resp.status_code == 302
        assert resp.url != URL


class TestImportarConArchivoEnSesion:
    """GET /inventario/importar/ muestra el archivo que ya está en la sesión."""

    def test_muestra_la_vista_previa(self, subido):
        resp = subido.get(URL)
        assert resp.context['preview']['archivo'] == 'inv.csv'
        assert resp.context['preview']['total_filas'] == 5

    def test_conserva_los_avisos_del_archivo(self, cliente_autenticado, laboratorio):
        _post(cliente_autenticado, laboratorio, contenido='Placa,Marca\nA-1,Fluke\n'.encode())
        avisos = cliente_autenticado.get(URL).context['preview']['advertencias']
        assert len([a for a in avisos if 'Nombre' in a]) == 1  # sin duplicar

    def test_laboratorio_desactivado_descarta_el_archivo(self, subido, laboratorio):
        laboratorio.activo = False
        laboratorio.save()
        resp = subido.get(URL)
        assert resp.context['preview'] is None
        assert SESION not in subido.session
