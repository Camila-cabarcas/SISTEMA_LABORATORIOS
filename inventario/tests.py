"""
tests.py — inventario
Prueba de eliminar_item_inventario (soft-delete): protegida por contraseña
admin, bloqueada para roles fuera de Administrador/Laboratorio (ambos
autorizados — ver users.decorators.ROLES_ACCION_CRITICA), y confirma que un
ItemInventario se MARCA como eliminado (deleted_at) sin borrar la fila ni su
historial de préstamos — a diferencia del delete() físico de antes, que
borraba en cascada PrestamoItem/InspeccionItem/MovimientoInventario.
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.transaction import atomic
from django.test import TestCase, Client
from django.utils import timezone

from inventario.models import EstadoInsumo, EstadoItem, Insumo, ItemInventario, TipoMovimiento
from prestamos.forms import PrestamoItemForm
from prestamos.models import EstadoPrestamo, Prestamo, PrestamoItem
from reservas.models import EstadoReserva, Reserva
from users.models import Rol, Usuario


class EliminarItemInventarioTests(TestCase):

    def setUp(self):
        rol_admin = Rol.objects.get_or_create(nombre='Administrador')[0]
        rol_lab = Rol.objects.get_or_create(nombre='Laboratorio')[0]
        rol_docente = Rol.objects.get_or_create(nombre='Docente')[0]

        self.admin = Usuario.objects.create_user(
            username='admin_test', password='pass123', codigo='ADMIN-TEST-001', rol=rol_admin,
        )
        self.admin.set_admin_password('AdminPass!123')

        self.laboratorista = Usuario.objects.create_user(
            username='lab_test', password='pass123', codigo='LAB-TEST-001', rol=rol_lab,
        )
        self.laboratorista.set_admin_password('LabPass!123')

        self.docente = Usuario.objects.create_user(
            username='docente_test', password='pass123', codigo='DOC-TEST-001', rol=rol_docente,
        )

        self.estado_disponible = EstadoItem.objects.get_or_create(nombre='Disponible')[0]
        self.insumo = Insumo.objects.create(nombre='Insumo Test Eliminar Item', descripcion='Para tests')
        self.item = ItemInventario.objects.create(
            codigo='TEST-001', insumo=self.insumo, estado=self.estado_disponible,
        )

        self.client = Client()

    def test_rol_no_autorizado_bloqueado(self):
        """Un rol fuera de Administrador/Laboratorio (p.ej. Docente) recibe 403
        de inmediato, sin llegar a ver el formulario de contraseña."""
        self.client.login(username='docente_test', password='pass123')
        response = self.client.get(f'/inventario/items/{self.item.id}/eliminar/')
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_deleted())

    def test_laboratorio_autorizado_ve_formulario(self):
        """Laboratorio SÍ está autorizado — el objetivo del pedido dice
        explícitamente 'Solo Administrador/Laboratorio pueden acceder'."""
        self.client.login(username='lab_test', password='pass123')
        response = self.client.get(f'/inventario/items/{self.item.id}/eliminar/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Contraseña admin', response.content.decode())

    def test_admin_sin_contrasena_ve_formulario_con_contexto(self):
        self.client.login(username='admin_test', password='pass123')
        response = self.client.get(f'/inventario/items/{self.item.id}/eliminar/')
        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode()
        self.assertIn('Contraseña admin', contenido)
        self.assertIn('Item - TEST-001', contenido)

    def test_admin_contrasena_incorrecta(self):
        self.client.login(username='admin_test', password='pass123')
        response = self.client.post(
            f'/inventario/items/{self.item.id}/eliminar/',
            {'admin_password': 'ContraseñaMala!123'},
            follow=True,
        )
        self.assertIn('incorrecta', response.content.decode().lower())
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_deleted())

    def test_admin_contrasena_correcta_soft_delete(self):
        """Contraseña correcta → el ítem se MARCA eliminado, no se borra."""
        self.client.login(username='admin_test', password='pass123')
        response = self.client.post(
            f'/inventario/items/{self.item.id}/eliminar/',
            {'admin_password': 'AdminPass!123'},
            follow=True,
        )
        self.assertIn('eliminado', response.content.decode().lower())

        # La fila sigue existiendo — no fue delete() físico.
        self.assertTrue(ItemInventario.objects.filter(id=self.item.id).exists())
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_deleted())
        self.assertIsNotNone(self.item.deleted_at)

    def test_laboratorio_contrasena_correcta_soft_delete(self):
        """Confirma de punta a punta que Laboratorio también puede completar
        la acción, no solo ver el formulario."""
        self.client.login(username='lab_test', password='pass123')
        self.client.post(
            f'/inventario/items/{self.item.id}/eliminar/',
            {'admin_password': 'LabPass!123'},
            follow=True,
        )
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_deleted())

    def test_eliminar_item_ya_eliminado_es_idempotente(self):
        """Repetir la eliminación no falla ni pisa deleted_at con una fecha nueva."""
        self.item.soft_delete()
        deleted_at_original = self.item.deleted_at

        self.client.login(username='admin_test', password='pass123')
        response = self.client.post(
            f'/inventario/items/{self.item.id}/eliminar/',
            {'admin_password': 'AdminPass!123'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.deleted_at, deleted_at_original)

    def test_item_eliminado_no_aparece_en_activos(self):
        self.item.soft_delete()
        self.assertFalse(ItemInventario.activos.filter(id=self.item.id).exists())
        self.assertTrue(ItemInventario.objects.filter(id=self.item.id).exists())

    def test_item_eliminado_no_aparece_en_lista(self):
        self.item.soft_delete()
        self.client.login(username='admin_test', password='pass123')
        response = self.client.get('/inventario/items/')
        self.assertNotIn(self.item.codigo, response.content.decode())

    def test_item_eliminado_no_seleccionable_para_prestamo(self):
        """Un ítem soft-deleted, aunque su estado siga siendo 'Disponible',
        no debe poder elegirse para un préstamo nuevo."""
        self.item.soft_delete()
        queryset = PrestamoItemForm().fields['item_inventario'].queryset
        self.assertNotIn(self.item, queryset)

    def test_historial_accesible_tras_eliminar(self):
        """El historial sigue siendo consultable después de eliminar — ese
        es el punto del soft-delete."""
        self.item.soft_delete()
        self.client.login(username='admin_test', password='pass123')
        response = self.client.get(f'/inventario/items/{self.item.id}/historial/')
        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode().lower()
        self.assertIn('eliminado', contenido)
        self.assertIn(self.item.codigo.lower(), contenido)

    def test_no_borra_historial_de_prestamos(self):
        """El problema original: delete() físico borraba en cascada
        PrestamoItem. Con soft-delete, ese historial debe seguir intacto."""
        # prestamos.signals cambia el ítem a estado 'Prestado' y crea un
        # MovimientoInventario al guardar un PrestamoItem — necesita ambas
        # filas de catálogo, que no crea ninguna migración ni seed_e2e (ver
        # prestamos/tests.py, mismo hallazgo).
        EstadoItem.objects.get_or_create(nombre='Prestado')
        TipoMovimiento.objects.get_or_create(nombre='Prestado')

        estado_aprobada = EstadoReserva.objects.get_or_create(nombre='Aprobada')[0]
        reserva = Reserva.objects.create(fecha_reserva=timezone.now(), estado=estado_aprobada)

        estado_activo = EstadoPrestamo.objects.get_or_create(nombre='Activo')[0]
        prestamo = Prestamo.objects.create(reserva=reserva, responsable=self.admin, estado=estado_activo)

        PrestamoItem.objects.create(prestamo=prestamo, item_inventario=self.item)

        self.item.soft_delete()

        self.assertTrue(PrestamoItem.objects.filter(item_inventario=self.item).exists())


class ModelosCleanValidationTests(TestCase):
    """clean() de Insumo e ItemInventario."""

    def setUp(self):
        self.estado_disponible = EstadoItem.objects.get_or_create(nombre='Disponible')[0]

    # -- Insumo -------------------------------------------------------------

    def test_insumo_stock_minimo_no_negativo_es_valido(self):
        insumo = Insumo(nombre='Multímetro', descripcion='Para tests', stock_minimo=0)
        insumo.full_clean()

    def test_insumo_stock_minimo_negativo_es_invalido(self):
        insumo = Insumo(nombre='Multímetro', descripcion='Para tests', stock_minimo=-1)
        with self.assertRaises(ValidationError):
            insumo.full_clean()

    # -- ItemInventario ---------------------------------------------------

    def test_item_codigo_no_vacio_es_valido(self):
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario(codigo='ITEM-001', insumo=insumo, estado=self.estado_disponible)
        item.full_clean()

    def test_item_codigo_solo_espacios_es_invalido(self):
        # CharField(blank=False) por sí solo no rechaza un string de solo
        # espacios — clean() sí lo hace.
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        item = ItemInventario(codigo='   ', insumo=insumo, estado=self.estado_disponible)
        with self.assertRaises(ValidationError):
            item.full_clean()


class EstadosUnicidadTests(TestCase):
    """EstadoItem.nombre, EstadoInsumo.nombre y TipoMovimiento.nombre con
    unique=True — ver docs/auditoria_seguridad_codigo.md, CRÍTICO #4. El
    código llama .get(nombre='Disponible')/.get(nombre='Prestado') (y
    equivalentes) en muchos lugares; una fila duplicada rompería todos con
    MultipleObjectsReturned."""

    def test_estado_item_duplicado_lanza_integrity_error(self):
        EstadoItem.objects.create(nombre='Disponible')

        with self.assertRaises(IntegrityError):
            with atomic():
                EstadoItem.objects.create(nombre='Disponible')

        self.assertEqual(EstadoItem.objects.filter(nombre='Disponible').count(), 1)

    def test_estado_insumo_duplicado_lanza_integrity_error(self):
        EstadoInsumo.objects.create(nombre='Activo')

        with self.assertRaises(IntegrityError):
            with atomic():
                EstadoInsumo.objects.create(nombre='Activo')

        self.assertEqual(EstadoInsumo.objects.filter(nombre='Activo').count(), 1)

    def test_tipo_movimiento_duplicado_lanza_integrity_error(self):
        TipoMovimiento.objects.create(nombre='Prestado')

        with self.assertRaises(IntegrityError):
            with atomic():
                TipoMovimiento.objects.create(nombre='Prestado')

        self.assertEqual(TipoMovimiento.objects.filter(nombre='Prestado').count(), 1)

    def test_full_clean_tambien_rechaza_el_duplicado(self):
        # 'Perdido' no sirve acá: la migración 0005_estadoitem_perdido ya
        # sembró esa fila, así que el primer create() de abajo colisionaría
        # con esa, no con el duplicado que el test quiere provocar.
        EstadoItem.objects.create(nombre='Estado de prueba único')

        duplicado = EstadoItem(nombre='Estado de prueba único')
        with self.assertRaises(ValidationError):
            duplicado.full_clean()

    def test_get_por_nombre_sigue_devolviendo_un_unico_resultado(self):
        EstadoItem.objects.create(nombre='Dañado')

        encontrado = EstadoItem.objects.get(nombre='Dañado')
        self.assertEqual(encontrado.nombre, 'Dañado')


class VistasInventarioMejoradasTests(TestCase):
    """Smoke tests HTTP de las 3 vistas de listado (insumos, items,
    movimientos) tras agregar laboratorio/desglose de stock/filtros — sobre
    todo para atrapar errores de template (etiquetas mal cerradas, filtros
    inexistentes) que un test de unidad sobre el modelo no vería."""

    def setUp(self):
        from laboratorio.models import Laboratorio

        rol_admin = Rol.objects.get_or_create(nombre='Administrador')[0]
        self.admin = Usuario.objects.create_user(
            username='admin_vistas_inv', password='pass123', codigo='ADMIN-VISTAS-INV', rol=rol_admin,
        )
        self.laboratorio = Laboratorio.objects.create(nombre='Laboratorio de Mecánica', ubicacion='Bloque 1')

        estado_disponible = EstadoItem.objects.get_or_create(nombre='Disponible')[0]
        EstadoItem.objects.get_or_create(nombre='Prestado')
        EstadoItem.objects.get_or_create(nombre='Dañado')
        EstadoItem.objects.get_or_create(nombre='Perdido')

        self.insumo = Insumo.objects.create(
            nombre='Martillo', laboratorio=self.laboratorio, descripcion='Para tests', stock_minimo=1,
        )
        self.item = ItemInventario.objects.create(
            codigo='MART-001', insumo=self.insumo, estado=estado_disponible, laboratorio=self.laboratorio,
        )

        tipo = TipoMovimiento.objects.get_or_create(nombre='Registro inicial')[0]
        from inventario.models import MovimientoInventario
        MovimientoInventario.objects.create(
            item_inventario=self.item, usuario=self.admin, tipo_movimiento=tipo,
            observacion='Alta inicial.',
        )

        self.client = Client()
        self.client.login(username='admin_vistas_inv', password='pass123')

    def test_lista_insumos_muestra_desglose_y_laboratorio(self):
        response = self.client.get('/inventario/')

        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode()
        self.assertIn('Martillo', contenido)
        self.assertIn(self.laboratorio.nombre, contenido)
        self.assertIn('En Préstamo', contenido)
        self.assertIn('Extraviado', contenido)

    def test_lista_insumos_busqueda_no_rompe_alertas_de_stock(self):
        # stock_minimo=1 con 1 ítem Disponible: dispara alertas_stock. Antes
        # de la corrección, buscar (?busqueda=...) perdía la anotación
        # cantidad_disponible_count y esto lanzaba AttributeError.
        response = self.client.get('/inventario/', {'busqueda': 'Mart'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('Martillo', response.content.decode())

    def test_lista_items_muestra_laboratorio_y_ultima_accion(self):
        response = self.client.get('/inventario/items/')

        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode()
        self.assertIn('MART-001', contenido)
        self.assertIn(self.laboratorio.nombre, contenido)
        self.assertIn('Creación', contenido)  # TipoMovimiento 'Registro inicial', ver TipoMovimiento.ETIQUETAS

    def test_lista_movimientos_con_filtros(self):
        response = self.client.get('/inventario/movimientos/', {
            'insumo': self.insumo.id,
            'lab': self.laboratorio.id,
            'usuario': self.admin.id,
        })

        self.assertEqual(response.status_code, 200)
        contenido = response.content.decode()
        self.assertIn('MART-001', contenido)
        self.assertIn('Creación', contenido)  # TipoMovimiento 'Registro inicial'

    def test_lista_movimientos_filtro_sin_resultados(self):
        # 'MART-001' igual aparece en la página (el <select> del formulario
        # "Registrar Movimiento" lista todos los ítems sin filtrar) — lo que
        # importa es que la TABLA filtrada quede vacía, no el resto de la
        # página.
        from laboratorio.models import Laboratorio
        otro_lab = Laboratorio.objects.create(nombre='Laboratorio de Física', ubicacion='Bloque 2')

        response = self.client.get('/inventario/movimientos/', {'lab': otro_lab.id})

        self.assertEqual(response.status_code, 200)
        self.assertIn('No hay movimientos con esos filtros.', response.content.decode())
