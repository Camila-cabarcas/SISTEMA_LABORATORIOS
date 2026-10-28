"""
Tests HTTP de las categorías de módulo: cómo se ven en cada lugar donde
aparecen módulos (mapa, editor, APIs de los formularios de reserva, detalle
de reserva, historial, admin) y la gestión de categorías (solo Administrador).
"""
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from laboratorio.models import CategoriaModulo, Laboratorio, Modulo
from users.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def cats(db):
    # Nombres distintos de las categorías que siembra la migración.
    return {
        'pc': CategoriaModulo.objects.create(nombre='Equipo PC', color='#20c997', forma='computador'),
        'torno': CategoriaModulo.objects.create(nombre='Torno', color='#fd7e14', forma='maquinaria'),
        'banco': CategoriaModulo.objects.create(nombre='Banco', color='#6610f2', forma='rombo'),
    }


@pytest.fixture
def modulos(laboratorio, cats):
    """PC 1 (Equipo PC), Torno 1 (Torno), Mesa X (sin categoría)."""
    return {
        'pc': Modulo.objects.create(nombre='PC 1', capacidad=1, laboratorio=laboratorio, categoria=cats['pc'],
                                    posicion_x=20, posicion_y=20),
        'torno': Modulo.objects.create(nombre='Torno 1', capacidad=2, laboratorio=laboratorio, categoria=cats['torno'],
                                       posicion_x=200, posicion_y=20),
        'sin': Modulo.objects.create(nombre='Mesa X', capacidad=4, laboratorio=laboratorio, posicion_x=400, posicion_y=20),
    }


def _mapa(cliente, laboratorio, **params):
    return cliente.get(reverse('mapa_laboratorio', args=[laboratorio.id]), params)


def _usuario(rol, username):
    return Usuario.objects.create_user(username=username, password='clave12345',
                                       rol=Rol.objects.get(nombre=rol), codigo=username.upper())


# ── Mapa ──────────────────────────────────────────────────────────────────

class TestMapa:

    def test_cada_modulo_lleva_color_y_forma_de_su_categoria(self, cliente_autenticado, laboratorio, modulos):
        html = _mapa(cliente_autenticado, laboratorio).content.decode()
        assert 'data-categoria-nombre="Equipo PC"' in html
        assert 'data-categoria-color="#20c997"' in html
        assert 'data-categoria-forma="computador"' in html
        assert 'data-categoria-forma="maquinaria"' in html
        # El dibujo lo hace el JS compartido con esos datos.
        assert 'js/modulo_figura.js' in html
        assert 'css/modulo_figura.css' in html
        assert 'ModuloFigura.crear' in html

    def test_modulo_sin_categoria_no_trae_datos_de_categoria(self, cliente_autenticado, laboratorio, modulos):
        # Sin data-categoria-*, ModuloFigura usa el estilo por defecto: gris, forma original.
        html = _mapa(cliente_autenticado, laboratorio).content.decode()
        bloque = html.split(f'data-id="{modulos["sin"].id}"')[1].split('></div>')[0]
        assert 'data-categoria' not in bloque
        assert "color: '#6c757d', forma: 'cuadrado'" in open('static/js/modulo_figura.js', encoding='utf-8').read()

    def test_leyenda_con_las_categorias_del_laboratorio(self, cliente_autenticado, laboratorio, modulos, cats):
        resp = _mapa(cliente_autenticado, laboratorio)
        html = resp.content.decode()
        assert [c.nombre for c in resp.context['categorias_lab']] == ['Equipo PC', 'Torno']
        assert resp.context['hay_sin_categoria'] is True
        leyenda = html.split('id="leyenda-categorias"')[1].split('</div>')[0]
        assert 'Equipo PC' in leyenda and 'Torno' in leyenda and 'Sin categoría' in leyenda
        assert 'Banco' not in leyenda  # no la usa ningún módulo de este lab
        assert 'forma-computador" style="--cat-color: #20c997;"' in leyenda
        assert 'forma-cuadrado" style="--cat-color: #6c757d;"' in leyenda

    def test_leyenda_no_incluye_categorias_de_otro_laboratorio(self, cliente_autenticado, laboratorio, modulos, cats):
        otro = Laboratorio.objects.create(nombre='Física', ubicacion='B1')
        Modulo.objects.create(nombre='Ajeno', capacidad=1, laboratorio=otro, categoria=cats['banco'])
        resp = _mapa(cliente_autenticado, laboratorio)
        assert cats['banco'] not in resp.context['categorias_lab']

    def test_leyenda_de_disponibilidad_con_puntos(self, cliente_autenticado, laboratorio, modulos):
        hoy = date.today().strftime('%Y-%m-%d')
        html = _mapa(cliente_autenticado, laboratorio, fecha=hoy, hora_inicio='08:00', hora_fin='09:00').content.decode()
        assert 'id="leyenda-estados"' in html
        assert '<span class="punto bg-danger"></span>Ocupado' in html

    def test_filtro_por_categoria(self, cliente_autenticado, laboratorio, modulos, cats):
        def ids(**p):
            return [i['modulo'].id for i in _mapa(cliente_autenticado, laboratorio, **p).context['modulos_data']]
        assert ids(categoria=cats['pc'].id) == [modulos['pc'].id]
        assert ids(categoria='sin') == [modulos['sin'].id]
        assert len(ids()) == 3
        html = _mapa(cliente_autenticado, laboratorio).content.decode()
        assert 'id="filtro-categoria"' in html

    def test_filtro_con_categoria_que_el_lab_no_usa_se_ignora(self, cliente_autenticado, laboratorio, modulos, cats):
        resp = _mapa(cliente_autenticado, laboratorio, categoria=cats['banco'].id)
        assert resp.context['categoria_filtro'] == ''
        assert len(resp.context['modulos_data']) == 3

    def test_modal_tiene_fila_categoria(self, cliente_autenticado, laboratorio, modulos):
        assert 'id="modal-categoria"' in _mapa(cliente_autenticado, laboratorio).content.decode()

    def test_lab_sin_categorias_no_muestra_filtro(self, cliente_autenticado, laboratorio):
        Modulo.objects.create(nombre='A', capacidad=1, laboratorio=laboratorio)
        html = _mapa(cliente_autenticado, laboratorio).content.decode()
        assert 'id="filtro-categoria"' not in html
        assert 'Sin categoría' in html  # leyenda: todos en gris


# ── Editor ────────────────────────────────────────────────────────────────

class TestEditor:

    def test_modulos_con_figura_de_su_categoria(self, cliente_autenticado, laboratorio, modulos):
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        assert 'modulo-figura forma-computador" style="--cat-color: #20c997;"' in html
        assert 'fa-desktop' in html
        assert 'modulo-figura forma-maquinaria" style="--cat-color: #fd7e14;"' in html
        assert 'fa-gears' in html

    def test_modulo_sin_categoria_gris_forma_original(self, cliente_autenticado, laboratorio, modulos):
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        bloque = html.split(f'data-id="{modulos["sin"].id}"')[1].split('</div>')[0]
        assert 'modulo-figura forma-cuadrado" style="--cat-color: #6c757d;"' in bloque

    def test_drag_and_drop_igual(self, cliente_autenticado, laboratorio, modulos):
        # El contenedor arrastrable conserva su posición tal cual; la figura va adentro.
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        assert 'style="left: 20px; top: 20px;"' in html
        assert 'js/editar_mapa.js' in html

    def test_leyenda(self, cliente_autenticado, laboratorio, modulos):
        html = cliente_autenticado.get(reverse('editar_mapa', args=[laboratorio.id])).content.decode()
        leyenda = html.split('id="leyenda-categorias"')[1].split('</div>')[0]
        assert 'Equipo PC' in leyenda and 'Torno' in leyenda and 'Sin categoría' in leyenda


# ── APIs y formularios de reserva ─────────────────────────────────────────

class TestApisYFormularios:

    @pytest.mark.parametrize('nombre_url, autenticado', [
        ('modulos_disponibles_api', True),
        ('modulos_disponibles_publica_api', False),
    ])
    def test_api_incluye_categoria(self, client, cliente_autenticado, laboratorio, modulos, cats, nombre_url, autenticado):
        cliente = cliente_autenticado if autenticado else client
        data = cliente.get(reverse(nombre_url, args=[laboratorio.id])).json()
        por_nombre = {m['nombre']: m for m in data['modulos']}
        assert por_nombre['PC 1']['categoria'] == {
            'id': cats['pc'].id, 'nombre': 'Equipo PC', 'color': '#20c997', 'forma': 'computador',
        }
        assert por_nombre['Mesa X']['categoria'] is None
        assert [c['nombre'] for c in data['categorias']] == ['Equipo PC', 'Torno']
        assert data['hay_sin_categoria'] is True

    def test_formulario_interno_dibuja_categorias(self, cliente_autenticado):
        html = cliente_autenticado.get('/reservas/crear/').content.decode()
        assert 'id="leyenda-categorias-form"' in html
        assert 'js/modulo_figura.js' in html and 'css/modulo_figura.css' in html
        assert 'ModuloFigura.crear' in html

    @pytest.mark.parametrize('nombre_url, sufijo', [
        ('solicitud_estudiante', '-est'),
        ('solicitud_profesor', '-prof'),
    ])
    def test_formularios_publicos_dibujan_categorias(self, client, catalogos, nombre_url, sufijo):
        html = client.get(reverse(nombre_url)).content.decode()
        assert f'id="leyenda-categorias-form{sufijo}"' in html
        assert 'js/modulo_figura.js' in html and 'css/modulo_figura.css' in html
        assert 'ModuloFigura.crear' in html

    def test_profesor_selecciona_por_clase_seleccionado(self, client, catalogos):
        html = client.get(reverse('solicitud_profesor')).content.decode()
        assert ".modulo-form-seat.seleccionado" in html
        assert ".modulo-form-seat.bg-primary" not in html


# ── Otras vistas con módulos ──────────────────────────────────────────────

def _reserva_con_modulo(laboratorio, modulo):
    from reservas.models import EstadoReserva, Reserva
    from solicitudes.models import SolicitudReserva

    reserva = Reserva.objects.create(fecha_reserva=timezone.now() + timedelta(days=1),
                                     estado=EstadoReserva.objects.get(nombre='Aprobada'))
    solicitud = SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre='Ana', cedula='123', email='ana@udea.edu.co',
        laboratorio=laboratorio, fecha_reserva=reserva.fecha_reserva, reserva=reserva, necesita_modulo=True,
    )
    solicitud.modulos_asignados.set([modulo])
    return reserva


class TestOtrasVistas:

    def test_detalle_de_reserva(self, cliente_autenticado, laboratorio, modulos, catalogos):
        reserva = _reserva_con_modulo(laboratorio, modulos['pc'])
        html = cliente_autenticado.get(f'/reservas/{reserva.id}/').content.decode()
        assert 'PC 1 · Equipo PC' in html
        assert 'forma-computador" style="--cat-color: #20c997;"' in html

    def test_detalle_de_reserva_modulo_sin_categoria(self, cliente_autenticado, laboratorio, modulos, catalogos):
        reserva = _reserva_con_modulo(laboratorio, modulos['sin'])
        html = cliente_autenticado.get(f'/reservas/{reserva.id}/').content.decode()
        assert 'forma-cuadrado" style="--cat-color: #6c757d;"' in html
        assert 'title="Sin categoría"' in html

    def test_detalles_del_propietario(self, client, laboratorio, modulos, catalogos):
        reserva = _reserva_con_modulo(laboratorio, modulos['torno'])
        html = client.get(f'/reservas/{reserva.id}/detalles/',
                          {'cedula': '123', 'email': 'ana@udea.edu.co'}).content.decode()
        assert 'Torno 1 · Torno' in html

    def test_historial_del_modulo(self, cliente_autenticado, laboratorio, modulos):
        url = reverse('historial_modulo', args=[laboratorio.id, modulos['pc'].id])
        assert 'Categoría: Equipo PC' in cliente_autenticado.get(url).content.decode()
        url = reverse('historial_modulo', args=[laboratorio.id, modulos['sin'].id])
        assert 'Categoría: Sin categoría' in cliente_autenticado.get(url).content.decode()

    def test_admin_de_modulo_tiene_selector_y_filtro(self, client, laboratorio, modulos, cats):
        admin = Usuario.objects.create_superuser('root', 'root@x.co', 'clave12345', codigo='ROOT')
        client.force_login(admin)
        html = client.get('/admin/laboratorio/modulo/', {'categoria__id__exact': cats['pc'].id}).content.decode()
        assert 'PC 1' in html and 'Torno 1' not in html
        form = client.get(f'/admin/laboratorio/modulo/{modulos["pc"].id}/change/').content.decode()
        assert 'name="categoria"' in form

    def test_admin_ofrece_solo_categorias_activas_mas_la_actual(self, laboratorio, modulos, cats):
        from laboratorio.admin import ModuloAdminForm

        cats['pc'].activo = False
        cats['pc'].save()
        cats['banco'].activo = False
        cats['banco'].save()

        nuevo = ModuloAdminForm()
        assert cats['pc'] not in nuevo.fields['categoria'].queryset
        assert cats['torno'] in nuevo.fields['categoria'].queryset

        existente = ModuloAdminForm(instance=modulos['pc'])  # ya tiene "Equipo PC" (inactiva)
        assert cats['pc'] in existente.fields['categoria'].queryset
        assert cats['banco'] not in existente.fields['categoria'].queryset


# ── Gestión de categorías ─────────────────────────────────────────────────

URL_LISTA = '/laboratorio/categorias/'


class TestGestionCategorias:

    def test_lista(self, cliente_autenticado, cats, modulos):
        resp = cliente_autenticado.get(URL_LISTA)
        assert resp.status_code == 200
        por_nombre = {c.nombre: c for c in resp.context['categorias']}
        assert por_nombre['Equipo PC'].total_modulos == 1
        assert por_nombre['Banco'].total_modulos == 0

    def test_crear(self, cliente_autenticado):
        resp = cliente_autenticado.post('/laboratorio/categorias/crear/',
                                        {'nombre': 'Proyector', 'color': '#6F42C1', 'forma': 'triangulo', 'activo': 'on'})
        assert resp.status_code == 302
        cat = CategoriaModulo.objects.get(nombre='Proyector')
        assert (cat.color, cat.forma, cat.activo) == ('#6f42c1', 'triangulo', True)

    def test_crear_invalido(self, cliente_autenticado, cats):
        resp = cliente_autenticado.post('/laboratorio/categorias/crear/',
                                        {'nombre': 'banco', 'color': 'rojo', 'forma': 'cuadrado'})
        assert resp.status_code == 200
        errores = resp.context['form'].errors
        assert 'nombre' in errores and 'color' in errores

    def test_editar_nombre_color_forma(self, cliente_autenticado, cats):
        cat = cats['banco']
        resp = cliente_autenticado.post(f'/laboratorio/categorias/{cat.id}/editar/',
                                        {'nombre': 'Banco óptico', 'color': '#000000', 'forma': 'circulo', 'activo': 'on'})
        assert resp.status_code == 302
        cat.refresh_from_db()
        assert (cat.nombre, cat.color, cat.forma) == ('Banco óptico', '#000000', 'circulo')

    def test_desactivar_y_activar(self, cliente_autenticado, cats):
        cat = cats['banco']
        cliente_autenticado.post(f'/laboratorio/categorias/{cat.id}/toggle/')
        cat.refresh_from_db()
        assert cat.activo is False
        cliente_autenticado.post(f'/laboratorio/categorias/{cat.id}/toggle/')
        cat.refresh_from_db()
        assert cat.activo is True

    def test_no_se_puede_borrar_categoria_con_modulos(self, cliente_autenticado, cats, modulos):
        resp = cliente_autenticado.post(f'/laboratorio/categorias/{cats["pc"].id}/eliminar/', follow=True)
        assert CategoriaModulo.objects.filter(id=cats['pc'].id).exists()
        assert 'No se puede eliminar' in resp.content.decode()
        modulos['pc'].refresh_from_db()
        assert modulos['pc'].categoria == cats['pc']

    def test_boton_eliminar_deshabilitado_si_tiene_modulos(self, cliente_autenticado, cats, modulos):
        html = cliente_autenticado.get(URL_LISTA).content.decode()
        assert 'title="Tiene módulos asignados: desactívala en su lugar"' in html

    def test_borrar_categoria_sin_modulos(self, cliente_autenticado, cats):
        resp = cliente_autenticado.post(f'/laboratorio/categorias/{cats["banco"].id}/eliminar/')
        assert resp.status_code == 302
        assert not CategoriaModulo.objects.filter(id=cats['banco'].id).exists()

    def test_eliminar_por_get_no_permitido(self, cliente_autenticado, cats):
        assert cliente_autenticado.get(f'/laboratorio/categorias/{cats["banco"].id}/eliminar/').status_code == 405
        assert CategoriaModulo.objects.filter(id=cats['banco'].id).exists()

    def test_link_en_el_menu_del_administrador(self, cliente_autenticado):
        assert 'href="/laboratorio/categorias/"' in cliente_autenticado.get(URL_LISTA).content.decode()

    @pytest.mark.parametrize('rol', ['Laboratorio', 'Docente', 'Estudiante'])
    @pytest.mark.parametrize('metodo, url_fmt', [
        ('get', '/laboratorio/categorias/'),
        ('get', '/laboratorio/categorias/crear/'),
        ('post', '/laboratorio/categorias/crear/'),
        ('get', '/laboratorio/categorias/{id}/editar/'),
        ('post', '/laboratorio/categorias/{id}/toggle/'),
        ('post', '/laboratorio/categorias/{id}/eliminar/'),
    ])
    def test_solo_administrador(self, client, catalogos, cats, rol, metodo, url_fmt):
        client.force_login(_usuario(rol, f'u_{rol.lower()}'))
        url = url_fmt.format(id=cats['banco'].id)
        datos = {'nombre': 'Hack', 'color': '#000000', 'forma': 'cuadrado'} if metodo == 'post' else None
        resp = getattr(client, metodo)(url, datos) if datos else getattr(client, metodo)(url)

        assert resp.status_code == 302
        assert resp.url == reverse('sin_permiso')
        cats['banco'].refresh_from_db()
        assert cats['banco'].activo is True
        assert not CategoriaModulo.objects.filter(nombre='Hack').exists()
        assert CategoriaModulo.objects.filter(id=cats['banco'].id).exists()

    def test_anonimo_va_al_login(self, client):
        resp = client.get(URL_LISTA)
        assert resp.status_code == 302
        assert 'login' in resp.url
