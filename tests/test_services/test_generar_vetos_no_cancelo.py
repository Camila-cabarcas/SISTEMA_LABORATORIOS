"""
Tests del veto NO_CANCELO automático: GenerarVetosNoCanceloService
(vetos/services.py) y el comando generar_vetos_no_cancelo.

Regla: reserva "Aprobada", sin Prestamo, con hora_limite_retiro
(fecha_reserva + 30 min) ya vencida dentro de la ventana → un veto
NO_CANCELO (1 día; 7 desde el 3er NO_CANCELO), nunca dos por la misma reserva.
"""
from datetime import date, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from prestamos.models import EstadoPrestamo, Prestamo
from reservas.models import EstadoReserva, Reserva
from solicitudes.models import SolicitudReserva
from vetos.models import Veto
from vetos.services import GenerarVetosNoCanceloService, RegistrarVetoService

pytestmark = pytest.mark.django_db

AHORA = datetime(2026, 10, 5, 12, 0)


def _reserva(laboratorio, *, limite_hace, estado='Aprobada', cedula='111222333', usuario=None):
    """Reserva cuyo hora_limite_retiro fue `limite_hace` antes de AHORA
    (negativo = todavía no vence), con su SolicitudReserva."""
    fecha_reserva = AHORA - limite_hace - timedelta(minutes=30)
    reserva = Reserva.objects.create(
        fecha_reserva=fecha_reserva,
        estado=EstadoReserva.objects.get(nombre=estado),
    )
    SolicitudReserva.objects.create(
        tipo_solicitante='estudiante', nombre='Ana Gómez', cedula=cedula, usuario=usuario,
        laboratorio=laboratorio, fecha_reserva=fecha_reserva, reserva=reserva,
    )
    return reserva


def _ejecutar(**kwargs):
    return GenerarVetosNoCanceloService.ejecutar(ahora=AHORA, **kwargs)


# ── Cuándo SÍ se genera ───────────────────────────────────────────────────

class TestGenera:

    def test_aprobada_sin_prestamo_vencida(self, catalogos, laboratorio):
        reserva = _reserva(laboratorio, limite_hace=timedelta(hours=1))

        resumen = _ejecutar()

        assert len(resumen['creados']) == 1
        veto = Veto.objects.get()
        assert veto.tipo == Veto.NO_CANCELO
        assert veto.estado == Veto.ACTIVO
        assert veto.reserva == reserva
        assert veto.cedula == '111222333'
        assert veto.creado_por is None
        assert veto.fecha_fin == date.today() + timedelta(days=1)
        assert 'automáticamente' in veto.motivo
        assert '1 día(s)' in veto.motivo

    def test_vencida_por_un_minuto(self, catalogos, laboratorio):
        _reserva(laboratorio, limite_hace=timedelta(minutes=1))
        assert len(_ejecutar()['creados']) == 1

    def test_guarda_usuario_si_el_solicitante_tiene_cuenta(self, catalogos, laboratorio, usuario_estudiante):
        _reserva(laboratorio, limite_hace=timedelta(hours=1), cedula='', usuario=usuario_estudiante)
        _ejecutar()
        veto = Veto.objects.get()
        assert veto.usuario == usuario_estudiante
        assert veto.cedula == ''

    def test_el_veto_bloquea_al_solicitante(self, catalogos, laboratorio):
        _reserva(laboratorio, limite_hace=timedelta(hours=1))
        _ejecutar()
        assert Veto.vigentes_para(cedula='111222333').exists()


# ── Cuándo NO se genera ───────────────────────────────────────────────────

class TestNoGenera:

    def test_limite_aun_no_vence(self, catalogos, laboratorio):
        _reserva(laboratorio, limite_hace=-timedelta(minutes=10))
        assert _ejecutar()['creados'] == []
        assert not Veto.objects.exists()

    def test_si_retiro_a_tiempo(self, catalogos, laboratorio, usuario_admin):
        reserva = _reserva(laboratorio, limite_hace=timedelta(hours=1))
        Prestamo.objects.create(
            reserva=reserva, responsable=usuario_admin,
            estado=EstadoPrestamo.objects.get(nombre='Devuelto'),
        )
        assert _ejecutar()['creados'] == []

    @pytest.mark.parametrize('estado', ['Cancelada', 'Pendiente', 'Expirada'])
    def test_si_no_esta_aprobada(self, catalogos, laboratorio, estado):
        _reserva(laboratorio, limite_hace=timedelta(hours=1), estado=estado)
        assert _ejecutar()['creados'] == []

    def test_fuera_de_la_ventana(self, catalogos, laboratorio):
        # No-shows históricos (antes de que existiera el proceso) no se vetan.
        _reserva(laboratorio, limite_hace=timedelta(hours=49))
        assert _ejecutar()['creados'] == []

    def test_ventana_configurable(self, catalogos, laboratorio):
        _reserva(laboratorio, limite_hace=timedelta(hours=49))
        assert len(_ejecutar(horas=72)['creados']) == 1

    def test_sin_solicitante_identificable(self, catalogos, laboratorio):
        reserva = Reserva.objects.create(
            fecha_reserva=AHORA - timedelta(hours=2),
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
        )
        resumen = _ejecutar()
        assert resumen['creados'] == []
        assert resumen['sin_identidad'] == [reserva]
        assert not Veto.objects.exists()

    def test_dry_run_no_crea(self, catalogos, laboratorio):
        reserva = _reserva(laboratorio, limite_hace=timedelta(hours=1))
        resumen = _ejecutar(dry_run=True)
        assert resumen['creados'] == [reserva]
        assert not Veto.objects.exists()


# ── Idempotencia ─────────────────────────────────────────────────────────

class TestIdempotencia:

    def test_segunda_corrida_no_duplica(self, catalogos, laboratorio):
        _reserva(laboratorio, limite_hace=timedelta(hours=1))
        _ejecutar()
        assert _ejecutar()['creados'] == []
        assert Veto.objects.count() == 1

    def test_no_duplica_veto_manual_de_la_misma_reserva(self, catalogos, laboratorio, usuario_laboratorista):
        reserva = _reserva(laboratorio, limite_hace=timedelta(hours=1))
        RegistrarVetoService.registrar_no_cancelo(reserva=reserva, creado_por=usuario_laboratorista)
        assert _ejecutar()['creados'] == []
        assert Veto.objects.count() == 1

    def test_no_revive_un_veto_ya_levantado(self, catalogos, laboratorio, usuario_admin):
        _reserva(laboratorio, limite_hace=timedelta(hours=1))
        _ejecutar()
        Veto.objects.get().resolver(usuario_admin)
        assert _ejecutar()['creados'] == []

    def test_otro_tipo_de_veto_en_la_reserva_no_impide_el_no_cancelo(self, catalogos, laboratorio):
        reserva = _reserva(laboratorio, limite_hace=timedelta(hours=1))
        Veto.objects.create(cedula='111222333', tipo=Veto.RETRASO, reserva=reserva,
                            fecha_fin=date.today() + timedelta(days=2))
        assert len(_ejecutar()['creados']) == 1


# ── Duración / reincidencia ──────────────────────────────────────────────

class TestDuracion:

    def _dias(self, veto):
        return (veto.fecha_fin - veto.fecha_inicio).days

    def test_tercera_infraccion_agrava_a_7_dias(self, catalogos, laboratorio):
        for horas in (3, 2, 1):
            _reserva(laboratorio, limite_hace=timedelta(hours=horas))

        creados = _ejecutar()['creados']

        assert [self._dias(v) for v in creados] == [1, 1, 7]
        assert '7 día(s)' in creados[-1].motivo

    def test_reincidencia_cuenta_vetos_previos_ya_resueltos(self, catalogos, laboratorio, usuario_admin):
        for _ in range(2):
            Veto.objects.create(cedula='111222333', tipo=Veto.NO_CANCELO, estado=Veto.RESUELTO,
                                fecha_fin=date.today())
        _reserva(laboratorio, limite_hace=timedelta(hours=1))

        veto = _ejecutar()['creados'][0]
        assert self._dias(veto) == 7

    def test_reincidencia_es_por_persona(self, catalogos, laboratorio):
        for n, horas in enumerate((3, 2, 1)):
            _reserva(laboratorio, limite_hace=timedelta(hours=horas), cedula=f'99900{n}')

        assert [self._dias(v) for v in _ejecutar()['creados']] == [1, 1, 1]


# ── Robustez ─────────────────────────────────────────────────────────────

def test_error_en_una_reserva_no_detiene_las_demas(catalogos, laboratorio, monkeypatch):
    mala = _reserva(laboratorio, limite_hace=timedelta(hours=2), cedula='000')
    _reserva(laboratorio, limite_hace=timedelta(hours=1), cedula='111')

    original = RegistrarVetoService.registrar_no_cancelo

    def falla_para_000(**kwargs):
        if kwargs['cedula'] == '000':
            raise RuntimeError('boom')
        return original(**kwargs)

    monkeypatch.setattr(RegistrarVetoService, 'registrar_no_cancelo', staticmethod(falla_para_000))

    resumen = _ejecutar()
    assert resumen['errores'] == [mala]
    assert len(resumen['creados']) == 1
    assert Veto.objects.get().cedula == '111'


# ── Management command ───────────────────────────────────────────────────

class TestComando:

    def _reserva_reciente(self, laboratorio):
        # El comando usa la hora real: límite vencido hace 1 hora.
        fecha = datetime.now() - timedelta(hours=1, minutes=30)
        reserva = Reserva.objects.create(
            fecha_reserva=fecha, estado=EstadoReserva.objects.get(nombre='Aprobada'),
        )
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', nombre='Ana', cedula='555',
            laboratorio=laboratorio, fecha_reserva=fecha, reserva=reserva,
        )
        return reserva

    def test_crea_y_reporta(self, catalogos, laboratorio):
        self._reserva_reciente(laboratorio)
        out = StringIO()
        call_command('generar_vetos_no_cancelo', stdout=out)
        assert Veto.objects.filter(tipo=Veto.NO_CANCELO).count() == 1
        assert '1 vetos NO_CANCELO creados.' in out.getvalue()

    def test_dry_run(self, catalogos, laboratorio):
        reserva = self._reserva_reciente(laboratorio)
        out = StringIO()
        call_command('generar_vetos_no_cancelo', '--dry-run', stdout=out)
        assert not Veto.objects.exists()
        assert '1 se vetarían.' in out.getvalue()
        assert reserva.codigo in out.getvalue()

    def test_opcion_horas(self, catalogos, laboratorio):
        self._reserva_reciente(laboratorio)
        call_command('generar_vetos_no_cancelo', '--horas', '0', stdout=StringIO())
        assert not Veto.objects.exists()
