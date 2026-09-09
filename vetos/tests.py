"""
tests.py — vetos
Cubre el modelo Veto (vigencia, acumulación, reglas de remoción), el
RegistrarVetoService (castigo por tipo + creación automática al devolver),
el bloqueo de reservas de un solicitante vetado, y las vistas de gestión.
"""
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventario.models import EstadoItem, TipoMovimiento
from laboratorio.models import HorarioLaboratorio, Laboratorio
from prestamos.models import EstadoPrestamo, InspeccionItem, Prestamo, PrestamoItem
from reservas.models import EstadoReserva, Reserva
from solicitudes.forms import EstudianteSolicitudForm
from solicitudes.models import SolicitudReserva
from solicitudes.services.solicitud_reserva_service import CrearSolicitudReservaService
from users.models import ProgramaAcademico, Rol, Usuario
from vetos.models import Veto
from vetos.services import RegistrarVetoService, consultar_bloqueo, mensaje_bloqueo


def _catalogos():
    for nombre in ['Administrador', 'Laboratorio', 'Estudiante', 'Docente']:
        Rol.objects.get_or_create(nombre=nombre)
    for nombre in ['Pendiente', 'Aprobada', 'Cancelada', 'Expirada']:
        EstadoReserva.objects.get_or_create(nombre=nombre)
    for nombre in ['Activo', 'En Inspección', 'Devuelto', 'Retrasado']:
        EstadoPrestamo.objects.get_or_create(nombre=nombre)
    for nombre in ['Disponible', 'Prestado', 'Dañado', 'Perdido']:
        EstadoItem.objects.get_or_create(nombre=nombre)
    for nombre in ['Prestado', 'Devuelto']:
        TipoMovimiento.objects.get_or_create(nombre=nombre)


# ── Modelo ────────────────────────────────────────────────────────────────

class VetoModelTests(TestCase):
    def setUp(self):
        _catalogos()

    def test_veto_activo_con_fecha_futura_esta_vigente(self):
        v = Veto.objects.create(
            cedula='111', tipo=Veto.RETRASO,
            fecha_fin=date.today() + timedelta(days=3),
        )
        self.assertTrue(v.esta_vigente)
        self.assertEqual(v.dias_restantes, 3)

    def test_veto_con_fecha_pasada_no_esta_vigente(self):
        v = Veto.objects.create(
            cedula='111', tipo=Veto.RETRASO,
            fecha_inicio=date.today() - timedelta(days=5),
            fecha_fin=date.today() - timedelta(days=1),
        )
        self.assertFalse(v.esta_vigente)
        self.assertEqual(v.dias_restantes, 0)

    def test_veto_resuelto_no_esta_vigente_aunque_la_fecha_no_haya_pasado(self):
        v = Veto.objects.create(
            cedula='111', tipo=Veto.RETRASO,
            fecha_fin=date.today() + timedelta(days=3),
            estado=Veto.RESUELTO,
        )
        self.assertFalse(v.esta_vigente)

    def test_veto_indefinido_esta_vigente(self):
        v = Veto.objects.create(cedula='111', tipo=Veto.DANO, fecha_fin=None)
        self.assertTrue(v.esta_vigente)
        self.assertTrue(v.es_indefinido)
        self.assertIsNone(v.dias_restantes)

    def test_clean_exige_identificar_al_sancionado(self):
        v = Veto(tipo=Veto.NO_CANCELO)
        with self.assertRaises(ValidationError):
            v.full_clean()

    def test_puede_remover_laboratorista(self):
        lab = Usuario(username='lab', rol=Rol.objects.get(nombre='Laboratorio'))
        self.assertTrue(Veto(tipo=Veto.NO_CANCELO).puede_remover(lab))
        self.assertTrue(Veto(tipo=Veto.RETRASO).puede_remover(lab))
        self.assertFalse(Veto(tipo=Veto.DANO).puede_remover(lab))
        self.assertFalse(Veto(tipo=Veto.FALTA_INSUMO).puede_remover(lab))

    def test_puede_remover_administrador_cualquier_tipo(self):
        adm = Usuario(username='adm', rol=Rol.objects.get(nombre='Administrador'))
        for tipo, _ in Veto.TIPO_CHOICES:
            self.assertTrue(Veto(tipo=tipo).puede_remover(adm))

    def test_calcular_dias_no_cancelo_agrava_por_reincidencia(self):
        self.assertEqual(Veto.calcular_dias_no_cancelo(cedula='999'), 1)
        Veto.objects.create(cedula='999', tipo=Veto.NO_CANCELO,
                            fecha_fin=date.today() + timedelta(days=1))
        self.assertEqual(Veto.calcular_dias_no_cancelo(cedula='999'), 1)
        Veto.objects.create(cedula='999', tipo=Veto.NO_CANCELO,
                            fecha_fin=date.today() + timedelta(days=1))
        # Con esta serían 3 → castigo agravado.
        self.assertEqual(Veto.calcular_dias_no_cancelo(cedula='999'), 7)


# ── Servicio ──────────────────────────────────────────────────────────────

class RegistrarVetoServiceTests(TestCase):
    def setUp(self):
        _catalogos()
        self.lab = Laboratorio.objects.create(nombre='Lab Q', ubicacion='B5')
        self.admin = Usuario.objects.create_user(
            username='admin_t', password='x', rol=Rol.objects.get(nombre='Administrador'),
            codigo='ADM1',
        )

    def _reserva_con_solicitud(self, cedula='111222333', fecha_devolucion=None):
        reserva = Reserva.objects.create(
            fecha_reserva=datetime(2026, 8, 1, 8, 0),
            fecha_devolucion=fecha_devolucion or datetime(2026, 8, 1, 10, 0),
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
        )
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', cedula=cedula,
            laboratorio=self.lab, fecha_reserva=reserva.fecha_reserva, reserva=reserva,
        )
        return reserva

    def test_registrar_no_cancelo_bloquea_un_dia(self):
        reserva = self._reserva_con_solicitud()
        veto = RegistrarVetoService.registrar_no_cancelo(
            reserva=reserva, creado_por=self.admin,
        )
        self.assertEqual(veto.tipo, Veto.NO_CANCELO)
        self.assertEqual(veto.fecha_fin, date.today() + timedelta(days=1))
        self.assertEqual(veto.cedula, '111222333')

    def test_registrar_retraso_dos_dias_por_dia_de_atraso(self):
        reserva = self._reserva_con_solicitud()
        prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=self.admin,
            estado=EstadoPrestamo.objects.get(nombre='Devuelto'),
        )
        veto = RegistrarVetoService.registrar_retraso(prestamo=prestamo, dias_atraso=3)
        self.assertEqual(veto.tipo, Veto.RETRASO)
        self.assertEqual(veto.fecha_fin, date.today() + timedelta(days=6))

    def test_registrar_dano_es_indefinido(self):
        reserva = self._reserva_con_solicitud()
        prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=self.admin,
            estado=EstadoPrestamo.objects.get(nombre='Devuelto'),
        )
        veto = RegistrarVetoService.registrar_dano(prestamo=prestamo, tipo=Veto.DANO)
        self.assertIsNone(veto.fecha_fin)
        self.assertTrue(veto.esta_vigente)

    def test_registrar_por_devolucion_crea_retraso_y_dano(self):
        # Devolución esperada 2026-08-01 10:00; real 2 días después.
        reserva = self._reserva_con_solicitud(
            fecha_devolucion=datetime(2026, 8, 1, 10, 0),
        )
        prestamo = Prestamo.objects.create(
            reserva=reserva, responsable=self.admin,
            estado=EstadoPrestamo.objects.get(nombre='Devuelto'),
        )
        prestamo.fecha_devolucion = datetime(2026, 8, 3, 10, 0)
        prestamo.save()

        item = PrestamoItem.objects.create(
            prestamo=prestamo,
            item_inventario=self._item(),
        )
        InspeccionItem.objects.create(
            prestamo=prestamo, prestamo_item=item, estado_inspeccion='danado',
        )

        creados = RegistrarVetoService.registrar_por_devolucion(prestamo)
        tipos = {v.tipo for v in creados}
        self.assertIn(Veto.RETRASO, tipos)
        self.assertIn(Veto.DANO, tipos)

    def _item(self):
        from inventario.models import Insumo, ItemInventario
        insumo = Insumo.objects.create(nombre='Beaker', descripcion='x', stock_minimo=0)
        return ItemInventario.objects.create(
            codigo=f'IT-{timezone.now().timestamp()}', insumo=insumo,
            estado=EstadoItem.objects.get(nombre='Disponible'), laboratorio=self.lab,
        )

    def test_consultar_bloqueo_y_mensaje(self):
        Veto.objects.create(cedula='abc', tipo=Veto.RETRASO,
                            fecha_fin=date.today() + timedelta(days=2),
                            motivo='Devolución tardía')
        veto = consultar_bloqueo(cedula='abc')
        self.assertIsNotNone(veto)
        self.assertIn('Devolución tardía', mensaje_bloqueo(veto))
        self.assertIsNone(consultar_bloqueo(cedula='sin-vetos'))


# ── Bloqueo de reservas ───────────────────────────────────────────────────

class BloqueoReservaPorVetoTests(TestCase):
    def setUp(self):
        _catalogos()
        self.programa = ProgramaAcademico.objects.create(nombre='Ing. Sistemas')
        self.lab = Laboratorio.objects.create(nombre='Lab F', ubicacion='B3', activo=True)
        self.fecha = date.today() + timedelta(days=7)
        dia_map = {
            'monday': 'lunes', 'tuesday': 'martes', 'wednesday': 'miercoles',
            'thursday': 'jueves', 'friday': 'viernes', 'saturday': 'sabado', 'sunday': 'domingo',
        }
        HorarioLaboratorio.objects.create(
            laboratorio=self.lab, dia=dia_map[self.fecha.strftime('%A').lower()],
            hora_inicio=time(6, 0), hora_fin=time(20, 0), bloqueado=False,
        )

    def _form(self, cedula='111222333'):
        return EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres', 'cedula': cedula, 'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre, 'laboratorio': self.lab.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00', 'hora_fin': '10:00',
            'necesita_modulo': False, 'observaciones': '',
        })

    def test_estudiante_sin_veto_puede_reservar(self):
        self.assertTrue(self._form().is_valid())

    def test_estudiante_con_veto_activo_no_puede_reservar(self):
        Veto.objects.create(
            cedula='111222333', tipo=Veto.RETRASO,
            fecha_fin=date.today() + timedelta(days=5), motivo='Devolución tardía',
        )
        form = self._form()
        self.assertFalse(form.is_valid())
        msg = ' '.join(form.errors.get('__all__', []))
        self.assertIn('bloqueado', msg.lower())

    def test_veto_vencido_no_bloquea(self):
        Veto.objects.create(
            cedula='111222333', tipo=Veto.RETRASO,
            fecha_inicio=date.today() - timedelta(days=10),
            fecha_fin=date.today() - timedelta(days=1),
        )
        self.assertTrue(self._form().is_valid())

    def test_crear_libre_bloqueado_por_veto(self):
        from solicitudes.services.solicitud_reserva_service import CrearSolicitudReservaService
        Veto.objects.create(
            cedula='555', tipo=Veto.DANO, fecha_fin=None, motivo='Insumo dañado',
        )
        with self.assertRaises(ValidationError):
            CrearSolicitudReservaService.crear_libre(
                nombre='Carlos Ruiz', cedula='555', email='carlos@udea.edu.co',
                nombre_grupo='Semillero', cantidad_asistentes_str='5',
                descripcion='Taller', laboratorio_id=str(self.lab.id),
                fecha_str=self.fecha.isoformat(),
                hora_inicio_str='08:00', hora_fin_str='10:00',
            )


# ── Vistas ────────────────────────────────────────────────────────────────

class VetoViewsTests(TestCase):
    def setUp(self):
        _catalogos()
        self.lab = Laboratorio.objects.create(nombre='Lab Q', ubicacion='B5')
        self.admin = Usuario.objects.create_user(
            username='adm_v', password='clave12345',
            rol=Rol.objects.get(nombre='Administrador'), codigo='ADMV',
        )
        self.laboratorista = Usuario.objects.create_user(
            username='lab_v', password='clave12345',
            rol=Rol.objects.get(nombre='Laboratorio'), codigo='LABV',
        )

    def test_lista_vetos_muestra_vigentes(self):
        Veto.objects.create(cedula='111', tipo=Veto.RETRASO,
                            fecha_fin=date.today() + timedelta(days=2))
        self.client.force_login(self.admin)
        resp = self.client.get('/vetos/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Retraso en la devolución')

    def test_crear_veto_registra_no_cancelo(self):
        self.client.force_login(self.laboratorista)
        resp = self.client.post('/vetos/crear/', {'cedula': '222333', 'motivo': ''})
        self.assertEqual(resp.status_code, 302)
        veto = Veto.objects.get(cedula='222333')
        self.assertEqual(veto.tipo, Veto.NO_CANCELO)
        self.assertEqual(veto.fecha_fin, date.today() + timedelta(days=1))

    def test_laboratorista_no_puede_remover_veto_de_dano(self):
        veto = Veto.objects.create(cedula='111', tipo=Veto.DANO, fecha_fin=None)
        self.client.force_login(self.laboratorista)
        resp = self.client.post(f'/vetos/{veto.id}/remover/')
        self.assertEqual(resp.status_code, 302)
        veto.refresh_from_db()
        self.assertEqual(veto.estado, Veto.ACTIVO)

    def test_laboratorista_puede_remover_veto_de_retraso(self):
        veto = Veto.objects.create(cedula='111', tipo=Veto.RETRASO,
                                   fecha_fin=date.today() + timedelta(days=3))
        self.client.force_login(self.laboratorista)
        resp = self.client.post(f'/vetos/{veto.id}/remover/')
        self.assertEqual(resp.status_code, 302)
        veto.refresh_from_db()
        self.assertEqual(veto.estado, Veto.RESUELTO)
        self.assertEqual(veto.resuelto_por, self.laboratorista)

    def test_admin_puede_remover_veto_de_dano_como_pagado(self):
        veto = Veto.objects.create(cedula='111', tipo=Veto.DANO, fecha_fin=None)
        self.client.force_login(self.admin)
        resp = self.client.post(f'/vetos/{veto.id}/remover/', {'pagado': '1'})
        self.assertEqual(resp.status_code, 302)
        veto.refresh_from_db()
        self.assertEqual(veto.estado, Veto.PAGADO)
