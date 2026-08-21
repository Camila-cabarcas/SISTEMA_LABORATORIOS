"""
tests.py — laboratorio
Tests para ModuloEstadoService (laboratorio/services/modulo_service.py):
la fuente única de verdad para el estado de un módulo, antes duplicada en
4 vistas de laboratorio/views.py.
"""
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from inventario.models import Insumo
from laboratorio.models import (
    EventoLaboratorio,
    HistorialModulo,
    HorarioLaboratorio,
    Laboratorio,
    Laboratorista,
    LaboratoristaLab,
    Modulo,
)
from laboratorio.services.modulo_service import ModuloEstadoService
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva


class ModuloEstadoServiceTests(TestCase):

    def setUp(self):
        self.laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Química',
            ubicacion='Bloque 5 - Piso 2',
        )
        self.modulo = Modulo.objects.create(
            nombre='Módulo 1',
            capacidad=4,
            laboratorio=self.laboratorio,
        )
        self.estado_pendiente = EstadoReserva.objects.create(nombre='Pendiente')
        self.estado_aprobada = EstadoReserva.objects.create(nombre='Aprobada')

    def _crear_solicitud(self, fecha, hora_inicio, hora_fin, estado_reserva):
        reserva = Reserva.objects.create(
            fecha_reserva=datetime.combine(fecha, hora_inicio),
            estado=estado_reserva,
        )
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante',
            nombre='Juan Pérez',
            cedula='123456789',
            laboratorio=self.laboratorio,
            fecha_reserva=datetime.combine(fecha, hora_inicio),
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            necesita_modulo=True,
            reserva=reserva,
        )
        solicitud.modulos_asignados.set([self.modulo])
        return solicitud

    def test_modulo_inactivo(self):
        self.modulo.disponible = False
        self.modulo.save()

        estado = ModuloEstadoService.obtener_estado(self.modulo, solicitudes_modulo=[], fecha=date.today())

        self.assertEqual(estado, 'inactivo')

    def test_modulo_sin_solicitudes_esta_disponible(self):
        estado = ModuloEstadoService.obtener_estado(self.modulo, solicitudes_modulo=[], fecha=date.today())

        self.assertEqual(estado, 'disponible')

    def test_modulo_con_reserva_activa_ahora_esta_ocupado(self):
        hoy = date.today()
        ahora = datetime.now().time()
        hora_inicio = (datetime.combine(hoy, ahora) - timedelta(minutes=30)).time()
        hora_fin = (datetime.combine(hoy, ahora) + timedelta(minutes=30)).time()

        solicitud = self._crear_solicitud(hoy, hora_inicio, hora_fin, self.estado_aprobada)
        soles = ModuloEstadoService.agrupar_por_modulo(
            SolicitudReserva.objects.filter(id=solicitud.id)
        ).get(self.modulo.id, [])

        estado = ModuloEstadoService.obtener_estado(self.modulo, solicitudes_modulo=soles, fecha=hoy)

        self.assertEqual(estado, 'ocupado')

    def test_modulo_con_reserva_futura_esta_reservado(self):
        manana = date.today() + timedelta(days=1)

        solicitud = self._crear_solicitud(
            manana, time(8, 0), time(10, 0), self.estado_aprobada,
        )
        soles = ModuloEstadoService.agrupar_por_modulo(
            SolicitudReserva.objects.filter(id=solicitud.id)
        ).get(self.modulo.id, [])

        estado = ModuloEstadoService.obtener_estado(self.modulo, solicitudes_modulo=soles, fecha=manana)

        self.assertEqual(estado, 'reservado')

    def test_reserva_pendiente_hoy_en_curso_no_es_ocupado(self):
        # Solo una reserva Aprobada (no Pendiente) puede poner un módulo en
        # 'ocupado' — Pendiente todavía no fue confirmada por un encargado.
        hoy = date.today()
        ahora = datetime.now().time()
        hora_inicio = (datetime.combine(hoy, ahora) - timedelta(minutes=30)).time()
        hora_fin = (datetime.combine(hoy, ahora) + timedelta(minutes=30)).time()

        solicitud = self._crear_solicitud(hoy, hora_inicio, hora_fin, self.estado_pendiente)
        soles = ModuloEstadoService.agrupar_por_modulo(
            SolicitudReserva.objects.filter(id=solicitud.id)
        ).get(self.modulo.id, [])

        estado = ModuloEstadoService.obtener_estado(self.modulo, solicitudes_modulo=soles, fecha=hoy)

        self.assertEqual(estado, 'reservado')

    def test_evaluar_ahora_false_nunca_devuelve_ocupado(self):
        hoy = date.today()
        ahora = datetime.now().time()
        hora_inicio = (datetime.combine(hoy, ahora) - timedelta(minutes=30)).time()
        hora_fin = (datetime.combine(hoy, ahora) + timedelta(minutes=30)).time()

        solicitud = self._crear_solicitud(hoy, hora_inicio, hora_fin, self.estado_aprobada)
        soles = ModuloEstadoService.agrupar_por_modulo(
            SolicitudReserva.objects.filter(id=solicitud.id)
        ).get(self.modulo.id, [])

        estado = ModuloEstadoService.obtener_estado(
            self.modulo, solicitudes_modulo=soles, fecha=hoy, evaluar_ahora=False,
        )

        self.assertEqual(estado, 'reservado')

    def test_modulo_inactivo_tiene_prioridad_sobre_reservas(self):
        self.modulo.disponible = False
        self.modulo.save()

        hoy = date.today()
        solicitud = self._crear_solicitud(hoy, time(8, 0), time(10, 0), self.estado_aprobada)
        soles = ModuloEstadoService.agrupar_por_modulo(
            SolicitudReserva.objects.filter(id=solicitud.id)
        ).get(self.modulo.id, [])

        estado = ModuloEstadoService.obtener_estado(self.modulo, solicitudes_modulo=soles, fecha=hoy)

        self.assertEqual(estado, 'inactivo')

    def test_solicitudes_del_laboratorio_y_agrupar_por_modulo_end_to_end(self):
        """Verifica el flujo completo (query + agrupación + estado) tal como
        lo usan las vistas, no solo obtener_estado en aislamiento."""
        hoy = date.today()
        self._crear_solicitud(hoy, time(8, 0), time(10, 0), self.estado_aprobada)

        solicitudes = ModuloEstadoService.solicitudes_del_laboratorio(self.laboratorio, hoy)
        agrupado = ModuloEstadoService.agrupar_por_modulo(solicitudes)
        estado = ModuloEstadoService.obtener_estado(
            self.modulo, agrupado.get(self.modulo.id, []), hoy, evaluar_ahora=False,
        )

        self.assertEqual(estado, 'reservado')

    def test_solicitud_relevante_prioriza_la_que_esta_en_curso(self):
        hoy = date.today()
        ahora = datetime.now().time()
        hora_inicio_actual = (datetime.combine(hoy, ahora) - timedelta(minutes=30)).time()
        hora_fin_actual = (datetime.combine(hoy, ahora) + timedelta(minutes=30)).time()

        self._crear_solicitud(hoy, time(6, 0), time(6, 30), self.estado_aprobada)
        activa = self._crear_solicitud(hoy, hora_inicio_actual, hora_fin_actual, self.estado_aprobada)

        soles = ModuloEstadoService.agrupar_por_modulo(
            SolicitudReserva.objects.filter(laboratorio=self.laboratorio, fecha_reserva__date=hoy)
        ).get(self.modulo.id, [])

        relevante = ModuloEstadoService.solicitud_relevante(soles, hoy)

        assert relevante is not None
        self.assertEqual(relevante.id, activa.id)


class ModelosCleanValidationTests(TestCase):
    """clean() de los modelos de laboratorio — reglas de negocio que antes
    solo vivían (algunas, duplicadas) en las vistas."""

    def setUp(self):
        self.laboratorio = Laboratorio.objects.create(nombre='Lab Clean Test', ubicacion='X')

    # -- HorarioLaboratorio -------------------------------------------------

    def test_horario_hora_fin_posterior_a_inicio_es_valido(self):
        horario = HorarioLaboratorio(
            laboratorio=self.laboratorio, dia='lunes',
            hora_inicio=time(8, 0), hora_fin=time(10, 0),
        )
        horario.full_clean()

    def test_horario_hora_fin_anterior_a_inicio_es_invalido(self):
        horario = HorarioLaboratorio(
            laboratorio=self.laboratorio, dia='lunes',
            hora_inicio=time(10, 0), hora_fin=time(8, 0),
        )
        with self.assertRaises(ValidationError):
            horario.full_clean()

    # -- EventoLaboratorio ----------------------------------------------------

    def test_evento_fin_posterior_a_inicio_es_valido(self):
        ahora = datetime.now()
        evento = EventoLaboratorio(
            laboratorio=self.laboratorio, titulo='Mantenimiento',
            inicio=ahora, fin=ahora + timedelta(hours=1),
        )
        evento.full_clean()

    def test_evento_fin_anterior_a_inicio_es_invalido(self):
        ahora = datetime.now()
        evento = EventoLaboratorio(
            laboratorio=self.laboratorio, titulo='Mantenimiento',
            inicio=ahora, fin=ahora - timedelta(hours=1),
        )
        with self.assertRaises(ValidationError):
            evento.full_clean()

    # -- Modulo -----------------------------------------------------------

    def test_modulo_capacidad_positiva_es_valida(self):
        modulo = Modulo(nombre='Módulo 1', capacidad=4, laboratorio=self.laboratorio)
        modulo.full_clean()

    def test_modulo_capacidad_cero_es_invalida(self):
        modulo = Modulo(nombre='Módulo 1', capacidad=0, laboratorio=self.laboratorio)
        with self.assertRaises(ValidationError):
            modulo.full_clean()

    # -- Laboratorista ------------------------------------------------------

    def test_laboratorista_responsabilidades_validas(self):
        laboratorista = Laboratorista(
            nombre='Juan', apellido='Pérez', cedula='1000000001',
            responsabilidades=['prestamos', 'inventario'],
        )
        laboratorista.full_clean()

    def test_laboratorista_responsabilidad_invalida(self):
        laboratorista = Laboratorista(
            nombre='Juan', apellido='Pérez', cedula='1000000002',
            responsabilidades=['prestamos', 'no_existe'],
        )
        with self.assertRaises(ValidationError):
            laboratorista.full_clean()

    # -- LaboratoristaLab -----------------------------------------------------

    def test_primer_encargado_es_valido(self):
        laboratorista = Laboratorista.objects.create(nombre='Juan', apellido='Pérez', cedula='1000000003')
        asignacion = LaboratoristaLab(
            laboratorista=laboratorista, laboratorio=self.laboratorio, tipo='encargado',
        )
        asignacion.full_clean()

    def test_segundo_encargado_es_invalido(self):
        laboratorista_1 = Laboratorista.objects.create(nombre='Juan', apellido='Pérez', cedula='1000000004')
        laboratorista_2 = Laboratorista.objects.create(nombre='Ana', apellido='Gómez', cedula='1000000005')
        LaboratoristaLab.objects.create(
            laboratorista=laboratorista_1, laboratorio=self.laboratorio, tipo='encargado',
        )

        asignacion_2 = LaboratoristaLab(
            laboratorista=laboratorista_2, laboratorio=self.laboratorio, tipo='encargado',
        )
        with self.assertRaises(ValidationError):
            asignacion_2.full_clean()

    def test_editar_al_mismo_encargado_no_falla(self):
        """full_clean() sobre un registro YA guardado no debe chocar consigo
        mismo (exclude(pk=self.pk))."""
        laboratorista = Laboratorista.objects.create(nombre='Juan', apellido='Pérez', cedula='1000000006')
        asignacion = LaboratoristaLab.objects.create(
            laboratorista=laboratorista, laboratorio=self.laboratorio, tipo='encargado',
        )
        asignacion.full_clean()

    def test_dos_laboratoristas_no_encargados_es_valido(self):
        laboratorista_1 = Laboratorista.objects.create(nombre='Juan', apellido='Pérez', cedula='1000000007')
        laboratorista_2 = Laboratorista.objects.create(nombre='Ana', apellido='Gómez', cedula='1000000008')
        LaboratoristaLab.objects.create(
            laboratorista=laboratorista_1, laboratorio=self.laboratorio, tipo='laboratorista',
        )
        asignacion_2 = LaboratoristaLab(
            laboratorista=laboratorista_2, laboratorio=self.laboratorio, tipo='laboratorista',
        )
        asignacion_2.full_clean()

    # -- HistorialModulo ----------------------------------------------------

    def test_historial_fecha_fin_posterior_es_valida(self):
        modulo = Modulo.objects.create(nombre='Módulo 1', capacidad=4, laboratorio=self.laboratorio)
        historial = HistorialModulo.objects.create(modulo=modulo, motivo='Mantenimiento')
        historial.fecha_fin = historial.fecha_inicio + timedelta(hours=1)
        historial.full_clean()

    def test_historial_fecha_fin_anterior_es_invalida(self):
        modulo = Modulo.objects.create(nombre='Módulo 1', capacidad=4, laboratorio=self.laboratorio)
        historial = HistorialModulo.objects.create(modulo=modulo, motivo='Mantenimiento')
        historial.fecha_fin = historial.fecha_inicio - timedelta(hours=1)
        with self.assertRaises(ValidationError):
            historial.full_clean()
