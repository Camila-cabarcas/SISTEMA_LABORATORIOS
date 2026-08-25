"""
tests.py — solicitudes
Tests para los services de solicitudes/services/ (solicitud_reserva_service.py
y registro_profesor_service.py): la lógica de negocio que antes vivía
dispersa en solicitudes/views.py y sus forms, ahora centralizada y probada
de forma independiente de las vistas HTTP.
"""
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from inventario.models import Insumo
from laboratorio.models import HorarioLaboratorio, Laboratorio, Modulo
from reservas.models import EstadoReserva, Reserva
from solicitudes.forms import EstudianteSolicitudForm, ProfesorSolicitudForm
from solicitudes.models import (
    Curso,
    SolicitudInsumo,
    SolicitudRegistroCurso,
    SolicitudRegistroProfesor,
    SolicitudReserva,
)
from solicitudes.services.registro_profesor_service import (
    AprobarCursoService,
    AprobarSolicitudRegistroProfesorService,
    CrearSolicitudRegistroProfesorService,
)
from solicitudes.services.solicitud_reserva_service import (
    AprobarSolicitudReservaService,
    CancelarSolicitudReservaService,
    CrearSolicitudReservaService,
    RechazarSolicitudReservaService,
    ValidarSolicitudReservaService,
)
from users.models import ProgramaAcademico, Rol, Usuario


def crear_catalogos():
    for nombre in ['Administrador', 'Laboratorio', 'Estudiante', 'Docente']:
        Rol.objects.get_or_create(nombre=nombre)
    for nombre in ['Pendiente', 'Aprobada', 'Cancelada', 'Expirada']:
        EstadoReserva.objects.get_or_create(nombre=nombre)


class ValidarSolicitudReservaServiceTests(TestCase):
    """Cubre la validación de la solicitud 'libre' — el flujo que antes NO
    pasaba por SolicitudReserva.clean() y duplicaba esta validación a mano
    en la vista."""

    def _datos_validos(self, **overrides):
        datos = dict(
            nombre='Carlos Ramírez',
            cedula='123456789',
            email='carlos@udea.edu.co',
            nombre_grupo='Semillero de Robótica',
            cantidad_asistentes_str='10',
            descripcion='Taller de robótica educativa',
            laboratorio_id='1',
            fecha_str=(date.today() + timedelta(days=1)).isoformat(),
            hora_inicio_str='08:00',
            hora_fin_str='10:00',
        )
        datos.update(overrides)
        return datos

    def test_datos_completos_no_lanza_error(self):
        # No debe lanzar ValidationError.
        ValidarSolicitudReservaService.validar(**self._datos_validos())

    def test_nombre_faltante(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(nombre=''))
        self.assertIn('El nombre del profesor es requerido.', ctx.exception.messages)

    def test_cedula_no_numerica(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(cedula='abc123'))
        self.assertIn('La cédula es requerida y debe contener solo números.', ctx.exception.messages)

    def test_email_faltante(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(email=''))
        self.assertIn('El email institucional es requerido.', ctx.exception.messages)

    def test_email_no_institucional(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(email='carlos@gmail.com'))
        self.assertIn('El email debe ser institucional (@udea.edu.co).', ctx.exception.messages)

    def test_cantidad_asistentes_invalida(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(cantidad_asistentes_str='0'))
        self.assertIn('La cantidad de asistentes debe ser un número positivo.', ctx.exception.messages)

    def test_fecha_pasada(self):
        ayer = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(fecha_str=ayer))
        self.assertIn('La fecha de reserva no puede ser anterior a hoy.', ctx.exception.messages)

    def test_fecha_formato_invalido(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(fecha_str='31-12-2026'))
        self.assertIn('Fecha inválida.', ctx.exception.messages)

    def test_faltan_laboratorio_y_horas(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(
                laboratorio_id='', hora_inicio_str='', hora_fin_str='',
            ))
        mensajes = ctx.exception.messages
        self.assertIn('Selecciona un laboratorio.', mensajes)
        self.assertIn('Selecciona la hora de inicio.', mensajes)
        self.assertIn('Selecciona la hora de fin.', mensajes)

    def test_acumula_varios_errores_a_la_vez(self):
        with self.assertRaises(ValidationError) as ctx:
            ValidarSolicitudReservaService.validar(**self._datos_validos(nombre='', cedula=''))
        self.assertEqual(len(ctx.exception.messages), 2)


class CrearSolicitudReservaServiceTests(TestCase):

    def setUp(self):
        crear_catalogos()
        self.programa = ProgramaAcademico.objects.create(nombre='Ingeniería de Sistemas')
        self.laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Física', ubicacion='Bloque 3', activo=True,
        )
        self.modulo = Modulo.objects.create(
            nombre='Módulo 1', capacidad=4, laboratorio=self.laboratorio,
        )

        # fecha/hora que satisfacen SolicitudReserva.clean(): día futuro,
        # dentro de un horario de laboratorio abierto, duración de 2h.
        self.fecha = date.today() + timedelta(days=7)
        self.dia_nombre = self._dia_es(self.fecha)
        HorarioLaboratorio.objects.create(
            laboratorio=self.laboratorio, dia=self.dia_nombre,
            hora_inicio=time(6, 0), hora_fin=time(20, 0), bloqueado=False,
        )

    @staticmethod
    def _dia_es(fecha):
        dia_map = {
            'monday': 'lunes', 'tuesday': 'martes', 'wednesday': 'miercoles',
            'thursday': 'jueves', 'friday': 'viernes', 'saturday': 'sabado', 'sunday': 'domingo',
        }
        return dia_map[fecha.strftime('%A').lower()]

    def test_crear_desde_estudiante_crea_solicitud_y_reserva(self):
        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        self.assertEqual(solicitud.tipo_solicitante, 'estudiante')
        assert reserva is not None
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.reserva_id, reserva.id)
        self.assertEqual(reserva.estado.nombre, 'Pendiente')
        self.assertEqual(solicitud.email, 'ana@udea.edu.co')

    def test_estudiante_sin_email_es_invalido(self):
        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': '',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_estudiante_email_no_institucional_es_invalido(self):
        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@gmail.com',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('El email debe ser institucional (@udea.edu.co).', form.errors['email'])

    def test_estudiante_email_udea_mayusculas_es_valido(self):
        # El dominio se compara sin distinguir mayúsculas/minúsculas.
        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'Ana.Torres@UDEA.EDU.CO',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        })

        self.assertTrue(form.is_valid(), form.errors)

    def test_notificacion_usa_email_de_la_solicitud_del_estudiante(self):
        # notificar_reserva_confirmada ya se prueba a fondo (con
        # mail.outbox) en tests/test_services/test_notificaciones_email.py;
        # acá solo interesa confirmar que _email_y_nombre resuelve al email
        # que el estudiante puso en el formulario, no a uno de un Usuario
        # (que ni siquiera existe para un estudiante anónimo como este).
        from utils.notificaciones_email import _email_y_nombre

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)
        assert reserva is not None

        email, _ = _email_y_nombre(solicitud)
        self.assertEqual(email, 'ana@udea.edu.co')

    def test_crear_desde_estudiante_bloqueada_por_solapamiento_con_aprobada(self):
        # El estudiante ya tiene una reserva Aprobada 09:00-11:00 ese día;
        # crear_reserva() debe rechazar (Reserva.clean()) una nueva que se
        # solape con ella, y CrearSolicitudReservaService lo absorbe
        # devolviendo reserva=None (igual que cualquier otro error al crear
        # la reserva — ver su docstring).
        Usuario.objects.create(username='ana_con_cuenta_test', codigo='111222333')
        Reserva.objects.create(
            usuario=Usuario.objects.get(codigo='111222333'),
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
            fecha_reserva=datetime.combine(self.fecha, time(9, 0)),
            fecha_devolucion=datetime.combine(self.fecha, time(11, 0)),
        )

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '10:00',
            'hora_fin': '12:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        self.assertIsNone(reserva)
        solicitud.refresh_from_db()
        self.assertIsNone(solicitud.reserva_id)

    def test_crear_desde_estudiante_bloqueada_por_solapamiento_mismo_laboratorio(self):
        # A diferencia del test anterior (reserva conflictiva sin
        # SolicitudReserva vinculada), acá SÍ se vincula al mismo
        # laboratorio, así que dispara el chequeo específico de
        # crear_reserva() — con su mensaje propio, no el genérico de
        # Reserva.clean().
        usuario = Usuario.objects.create(username='ana_lab_test', codigo='111222333')
        reserva_existente = Reserva.objects.create(
            usuario=usuario,
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
            fecha_reserva=datetime.combine(self.fecha, time(9, 0)),
            fecha_devolucion=datetime.combine(self.fecha, time(11, 0)),
        )
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', cedula='111222333', usuario=usuario,
            laboratorio=self.laboratorio, fecha_reserva=datetime.combine(self.fecha, time(9, 0)),
            hora_inicio=time(9, 0), hora_fin=time(11, 0), reserva=reserva_existente,
        )

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '10:00',
            'hora_fin': '12:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        with self.assertLogs('solicitudes.services.solicitud_reserva_service', level='ERROR') as ctx:
            solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        self.assertIsNone(reserva)
        self.assertIn(f'Ya tienes una reserva a esa hora en {self.laboratorio.nombre}', ctx.output[0])
        solicitud.refresh_from_db()
        self.assertIsNone(solicitud.reserva_id)

    def _crear_reserva_existente(self, cedula, laboratorio, hora_inicio, hora_fin, fecha=None):
        """Usuario + Reserva Aprobada + SolicitudReserva vinculada a
        `laboratorio`, para armar el escenario "ya tiene una reserva" que
        usan los tests de máximo 1 reserva/día/laboratorio."""
        fecha = fecha or self.fecha
        usuario, _ = Usuario.objects.get_or_create(
            codigo=cedula, defaults={'username': f'user_{cedula}'},
        )
        reserva = Reserva.objects.create(
            usuario=usuario,
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
            fecha_reserva=datetime.combine(fecha, hora_inicio),
            fecha_devolucion=datetime.combine(fecha, hora_fin),
        )
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', cedula=cedula, usuario=usuario,
            laboratorio=laboratorio, fecha_reserva=datetime.combine(fecha, hora_inicio),
            hora_inicio=hora_inicio, hora_fin=hora_fin, reserva=reserva,
        )
        return usuario

    def test_2_reservas_mismo_laboratorio_mismo_dia_sin_solapar_es_bloqueada(self):
        # 10:00-12:00 ya reservado; 14:00-16:00 el mismo día no se solapa,
        # pero el límite de 1 reserva/día/laboratorio la bloquea igual.
        self._crear_reserva_existente('111222333', self.laboratorio, time(10, 0), time(12, 0))

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '14:00',
            'hora_fin': '16:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        with self.assertLogs('solicitudes.services.solicitud_reserva_service', level='ERROR') as ctx:
            solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        self.assertIsNone(reserva)
        self.assertIn(f'Solo puedes hacer 1 reserva por día en {self.laboratorio.nombre}', ctx.output[0])

    def test_2_reservas_mismo_laboratorio_dias_distintos_es_permitida(self):
        # Mismo laboratorio, mismo horario, pero una semana después: no hay
        # límite de 1 reserva/día/laboratorio que cruce días distintos.
        self._crear_reserva_existente('111222333', self.laboratorio, time(10, 0), time(12, 0))

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': (self.fecha + timedelta(weeks=1)).isoformat(),
            'hora_inicio': '10:00',
            'hora_fin': '12:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        assert reserva is not None
        self.assertEqual(reserva.estado.nombre, 'Pendiente')

    def test_2_reservas_laboratorios_distintos_mismo_dia_es_permitida(self):
        # Lab B a las 10-12 ya reservado; Lab A (self.laboratorio) a las
        # 14-16 el mismo día no choca con el límite, que es por laboratorio.
        otro_laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Química', ubicacion='Bloque 5', activo=True,
        )
        self._crear_reserva_existente('111222333', otro_laboratorio, time(10, 0), time(12, 0))

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '14:00',
            'hora_fin': '16:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        assert reserva is not None
        self.assertEqual(reserva.estado.nombre, 'Pendiente')

    def test_crear_desde_estudiante_no_bloqueada_por_solapamiento_en_otro_laboratorio(self):
        # Mismo usuario, mismo horario, pero en un laboratorio distinto: no
        # debe chocar contra el chequeo específico de crear_reserva() — el
        # chequeo genérico de Reserva.clean() (cualquier laboratorio) sigue
        # sin poder pasarlo porque la reserva conflictiva no tiene
        # SolicitudReserva vinculada (self.reserva no existe en ese momento).
        otro_laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Química', ubicacion='Bloque 5', activo=True,
        )
        usuario = Usuario.objects.create(username='ana_otro_lab_test', codigo='111222333')
        reserva_existente = Reserva.objects.create(
            usuario=usuario,
            estado=EstadoReserva.objects.get(nombre='Aprobada'),
            fecha_reserva=datetime.combine(self.fecha, time(9, 0)),
            fecha_devolucion=datetime.combine(self.fecha, time(11, 0)),
        )
        SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', cedula='111222333', usuario=usuario,
            laboratorio=otro_laboratorio, fecha_reserva=datetime.combine(self.fecha, time(9, 0)),
            hora_inicio=time(9, 0), hora_fin=time(11, 0), reserva=reserva_existente,
        )

        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '10:00',
            'hora_fin': '12:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)

        # Sigue bloqueada — por el chequeo genérico de Reserva.clean(), no
        # por el de laboratorio específico.
        self.assertIsNone(reserva)

    def test_crear_desde_estudiante_asigna_modulo(self):
        form = EstudianteSolicitudForm(None, {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': True,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, _ = CrearSolicitudReservaService.crear_desde_estudiante(
            form, modulos_ids_str=str(self.modulo.id),
        )

        self.assertEqual(list(solicitud.modulos_asignados.all()), [self.modulo])

    def test_reserva_pendiente_limite_2(self):
        datos_base = {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        }

        # Dos solicitudes pendientes se crean sin problema (semanas distintas,
        # mismo día de la semana, para reutilizar el HorarioLaboratorio del
        # setUp sin chocar con el límite de horas acumuladas por día).
        for semanas in (0, 1):
            form = EstudianteSolicitudForm(None, dict(
                datos_base, fecha_reserva=(self.fecha + timedelta(weeks=semanas)).isoformat(),
            ))
            self.assertTrue(form.is_valid(), form.errors)
            _, reserva = CrearSolicitudReservaService.crear_desde_estudiante(form)
            assert reserva is not None  # ← Pylance entiende
            self.assertEqual(reserva.estado.nombre, 'Pendiente')

        # La tercera solicitud pendiente del mismo estudiante debe rechazarse.
        form_tercera = EstudianteSolicitudForm(None, dict(
            datos_base, fecha_reserva=(self.fecha + timedelta(weeks=2)).isoformat(),
        ))
        self.assertFalse(form_tercera.is_valid())
        errores = ' '.join(str(e) for e in form_tercera.errors.get('__all__', []))
        self.assertIn('Ya tienes 2 reservas pendientes', errores)

    def test_crear_desde_profesor_crea_solicitud_y_reserva(self):
        docente = Usuario.objects.create_user(
            username='profe_test', password='x', first_name='Carlos', last_name='Ramirez',
            rol=Rol.objects.get(nombre='Docente'),
        )
        curso = Curso.objects.create(
            nombre='Física General', codigo='FIS101', profesor=docente, cantidad_estudiantes=20,
        )
        form = ProfesorSolicitudForm({
            'nombre': 'Carlos Ramirez',
            'cedula': '999888777',
            'curso': curso.id,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'necesita_modulo': False,
            'observaciones': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

        solicitud, reserva = CrearSolicitudReservaService.crear_desde_profesor(form)

        self.assertEqual(solicitud.tipo_solicitante, 'profesor')
        assert reserva is not None
        self.assertEqual(solicitud.usuario_id, docente.id)

    def test_crear_libre_crea_solicitud_y_reserva(self):
        solicitud, reserva = CrearSolicitudReservaService.crear_libre(
            nombre='Laura Gómez',
            cedula='555666777',
            email='laura@udea.edu.co',
            nombre_grupo='Semillero de Robótica',
            cantidad_asistentes_str='5',
            descripcion='Taller abierto',
            laboratorio_id=str(self.laboratorio.id),
            fecha_str=self.fecha.isoformat(),
            hora_inicio_str='08:00',
            hora_fin_str='10:00',
        )

        self.assertTrue(solicitud.reserva_libre)
        self.assertEqual(solicitud.tipo_solicitante, 'profesor')
        assert reserva is not None
        self.assertEqual(reserva.estado.nombre, 'Pendiente')

    def test_crear_libre_asigna_modulos_automaticamente_sin_ids(self):
        modulo_2 = Modulo.objects.create(nombre='Módulo 2', capacidad=4, laboratorio=self.laboratorio)

        solicitud, _ = CrearSolicitudReservaService.crear_libre(
            nombre='Laura Gómez',
            cedula='555666777',
            email='laura@udea.edu.co',
            nombre_grupo='Semillero de Robótica',
            cantidad_asistentes_str='2',
            descripcion='Taller abierto',
            laboratorio_id=str(self.laboratorio.id),
            fecha_str=self.fecha.isoformat(),
            hora_inicio_str='08:00',
            hora_fin_str='10:00',
            necesita_modulo=True,
        )

        # cantidad_asistentes=2 -> se asignan hasta 2 módulos disponibles,
        # sin necesidad de especificar modulos_ids_str.
        self.assertEqual(solicitud.modulos_asignados.count(), 2)
        self.assertIn(self.modulo, solicitud.modulos_asignados.all())
        self.assertIn(modulo_2, solicitud.modulos_asignados.all())

    def test_crear_libre_asigna_insumos(self):
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')

        solicitud, _ = CrearSolicitudReservaService.crear_libre(
            nombre='Laura Gómez',
            cedula='555666777',
            email='laura@udea.edu.co',
            nombre_grupo='Semillero de Robótica',
            cantidad_asistentes_str='5',
            descripcion='Taller abierto',
            laboratorio_id=str(self.laboratorio.id),
            fecha_str=self.fecha.isoformat(),
            hora_inicio_str='08:00',
            hora_fin_str='10:00',
            insumos_ids_str=str(insumo.id),
            insumos_cantidades_str='3',
        )

        solicitud_insumo = solicitud.insumos.get()
        self.assertEqual(solicitud_insumo.insumo_id, insumo.id)
        self.assertEqual(solicitud_insumo.cantidad, 3)

    def test_crear_libre_laboratorio_inexistente_propaga_excepcion(self):
        # crear_libre no atrapa excepciones propias — se propagan tal cual,
        # igual que en la vista original (que las envolvía en un único
        # except genérico).
        with self.assertRaises(Laboratorio.DoesNotExist):
            CrearSolicitudReservaService.crear_libre(
                nombre='Laura Gómez',
                cedula='555666777',
                email='laura@udea.edu.co',
                nombre_grupo='Semillero de Robótica',
                cantidad_asistentes_str='5',
                descripcion='Taller abierto',
                laboratorio_id='999999',
                fecha_str=self.fecha.isoformat(),
                hora_inicio_str='08:00',
                hora_fin_str='10:00',
            )


class SolicitudReservaEstadoServiceTests(TestCase):
    """AprobarSolicitudReservaService / RechazarSolicitudReservaService /
    CancelarSolicitudReservaService — operan sobre la Reserva asociada a una
    SolicitudReserva. No hay hoy una vista que las use; se prueban de forma
    independiente como capacidad expuesta para un futuro cliente de API."""

    def setUp(self):
        crear_catalogos()
        self.laboratorio = Laboratorio.objects.create(nombre='Lab Test', ubicacion='X')
        self.admin = Usuario.objects.create_user(
            username='admin_test', password='x', codigo='ADMIN001',
            rol=Rol.objects.get(nombre='Administrador'),
        )
        self.encargado = Usuario.objects.create_user(
            username='encargado_test', password='x', codigo='ENC001',
            rol=Rol.objects.get(nombre='Laboratorio'),
        )

    def _crear_solicitud_con_reserva(self, reserva_libre=False, estado_reserva='Pendiente'):
        reserva = Reserva.objects.create(
            fecha_reserva=datetime.now(),
            estado=EstadoReserva.objects.get(nombre=estado_reserva),
        )
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante',
            nombre='Ana Torres',
            cedula='111222333',
            laboratorio=self.laboratorio,
            fecha_reserva=datetime.now(),
            reserva_libre=reserva_libre,
            reserva=reserva,
        )
        return solicitud, reserva

    # -- Aprobar --------------------------------------------------------

    def test_aprobar_cambia_estado_a_aprobada(self):
        solicitud, reserva = self._crear_solicitud_con_reserva()

        AprobarSolicitudReservaService.aprobar(solicitud.id, self.encargado)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Aprobada')

    def test_aprobar_solicitud_libre_requiere_administrador(self):
        solicitud, reserva = self._crear_solicitud_con_reserva(reserva_libre=True)

        with self.assertRaises(ValidationError):
            AprobarSolicitudReservaService.aprobar(solicitud.id, self.encargado)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Pendiente')

    def test_aprobar_solicitud_libre_administrador_si_puede(self):
        solicitud, reserva = self._crear_solicitud_con_reserva(reserva_libre=True)

        AprobarSolicitudReservaService.aprobar(solicitud.id, self.admin)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Aprobada')

    def test_aprobar_sin_reserva_lanza_error(self):
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', nombre='Ana', cedula='1',
            laboratorio=self.laboratorio, fecha_reserva=datetime.now(),
        )
        with self.assertRaises(ValidationError):
            AprobarSolicitudReservaService.aprobar(solicitud.id, self.admin)

    def test_aprobar_solicitud_inexistente_lanza_error(self):
        with self.assertRaises(ValidationError):
            AprobarSolicitudReservaService.aprobar(999999, self.admin)

    # -- Rechazar ---------------------------------------------------------

    def test_rechazar_pendiente_cambia_a_cancelada(self):
        solicitud, reserva = self._crear_solicitud_con_reserva()

        RechazarSolicitudReservaService.rechazar(solicitud.id)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Cancelada')

    def test_rechazar_no_pendiente_lanza_error(self):
        solicitud, reserva = self._crear_solicitud_con_reserva(estado_reserva='Aprobada')

        with self.assertRaises(ValidationError):
            RechazarSolicitudReservaService.rechazar(solicitud.id)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Aprobada')

    # -- Cancelar -----------------------------------------------------------

    def test_cancelar_desde_pendiente(self):
        solicitud, reserva = self._crear_solicitud_con_reserva(estado_reserva='Pendiente')

        CancelarSolicitudReservaService.cancelar(solicitud.id)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Cancelada')

    def test_cancelar_desde_aprobada(self):
        # A diferencia de rechazar, cancelar no exige que la reserva esté Pendiente.
        solicitud, reserva = self._crear_solicitud_con_reserva(estado_reserva='Aprobada')

        CancelarSolicitudReservaService.cancelar(solicitud.id)

        reserva.refresh_from_db()
        self.assertEqual(reserva.estado.nombre, 'Cancelada')


class CrearSolicitudRegistroProfesorServiceTests(TestCase):

    def _datos_validos(self, **overrides):
        datos = dict(
            nombre='Pedro', apellido='Suárez', cedula='123123123',
            correo='pedro@example.com', programa='Ingeniería',
            nombres_curso=['Cálculo I'], codigos_curso=['CAL101'], cantidades_curso=['30'],
        )
        datos.update(overrides)
        return datos

    def test_crear_exitoso(self):
        solicitud = CrearSolicitudRegistroProfesorService.crear(**self._datos_validos())

        self.assertEqual(solicitud.estado, 'pendiente')
        self.assertEqual(solicitud.cursos_solicitados.count(), 1)
        curso = solicitud.cursos_solicitados.first()
        self.assertEqual(curso.codigo, 'CAL101')

    def test_cedula_duplicada_pendiente_lanza_error(self):
        CrearSolicitudRegistroProfesorService.crear(**self._datos_validos())

        with self.assertRaises(ValidationError) as ctx:
            CrearSolicitudRegistroProfesorService.crear(**self._datos_validos(
                nombres_curso=['Cálculo II'], codigos_curso=['CAL102'], cantidades_curso=['25'],
            ))
        self.assertTrue(any('Ya existe una solicitud' in m for m in ctx.exception.messages))

    def test_curso_incompleto_lanza_error(self):
        with self.assertRaises(ValidationError) as ctx:
            CrearSolicitudRegistroProfesorService.crear(**self._datos_validos(
                nombres_curso=['Cálculo I'], codigos_curso=[''], cantidades_curso=['30'],
            ))
        self.assertTrue(any('código' in m for m in ctx.exception.messages))

    def test_sin_cursos_lanza_error(self):
        with self.assertRaises(ValidationError) as ctx:
            CrearSolicitudRegistroProfesorService.crear(**self._datos_validos(
                nombres_curso=[], codigos_curso=[], cantidades_curso=[],
            ))
        self.assertIn('Debes agregar al menos un curso.', ctx.exception.messages)

    def test_cedula_no_numerica_lanza_error(self):
        with self.assertRaises(ValidationError) as ctx:
            CrearSolicitudRegistroProfesorService.crear(**self._datos_validos(cedula='abc'))
        self.assertIn('La cédula debe contener solo números.', ctx.exception.messages)

    def test_no_crea_nada_si_hay_errores(self):
        with self.assertRaises(ValidationError):
            CrearSolicitudRegistroProfesorService.crear(**self._datos_validos(nombre=''))
        self.assertEqual(SolicitudRegistroProfesor.objects.count(), 0)


class AprobarSolicitudRegistroProfesorServiceTests(TestCase):

    def setUp(self):
        crear_catalogos()
        self.solicitud = SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='123123123', correo='p@example.com',
        )
        SolicitudRegistroCurso.objects.create(
            solicitud_profesor=self.solicitud, nombre='Cálculo I', codigo='CAL101',
            cantidad_estudiantes=30,
        )

    def test_aprobar_crea_usuario_docente(self):
        solicitud = AprobarSolicitudRegistroProfesorService.aprobar(self.solicitud.id)

        self.assertEqual(solicitud.estado, 'aprobada')
        self.assertIsNotNone(solicitud.usuario_creado)
        self.assertEqual(solicitud.usuario_creado.username, 'doc_123123123')
        self.assertEqual(solicitud.usuario_creado.rol.nombre, 'Docente')

    def test_aprobar_username_colision_agrega_sufijo(self):
        Usuario.objects.create_user(username='doc_123123123', password='x')

        solicitud = AprobarSolicitudRegistroProfesorService.aprobar(self.solicitud.id)

        self.assertEqual(solicitud.usuario_creado.username, 'doc_123123123_2')

    def test_aprobar_no_pendiente_lanza_error(self):
        AprobarSolicitudRegistroProfesorService.aprobar(self.solicitud.id)

        with self.assertRaises(ValidationError):
            AprobarSolicitudRegistroProfesorService.aprobar(self.solicitud.id)

    def test_aprobar_solicitud_inexistente_lanza_error(self):
        with self.assertRaises(ValidationError):
            AprobarSolicitudRegistroProfesorService.aprobar(999999)

    def test_rechazar_marca_estado_y_cursos(self):
        AprobarSolicitudRegistroProfesorService.rechazar(self.solicitud.id)

        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'rechazada')
        curso = self.solicitud.cursos_solicitados.first()
        self.assertEqual(curso.estado, 'rechazada')

    def test_rechazar_no_pendiente_lanza_error(self):
        AprobarSolicitudRegistroProfesorService.rechazar(self.solicitud.id)

        with self.assertRaises(ValidationError):
            AprobarSolicitudRegistroProfesorService.rechazar(self.solicitud.id)


class AprobarCursoServiceTests(TestCase):

    def setUp(self):
        crear_catalogos()
        self.solicitud = SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='123123123', correo='p@example.com',
        )
        self.solicitud_curso = SolicitudRegistroCurso.objects.create(
            solicitud_profesor=self.solicitud, nombre='Cálculo I', codigo='CAL101',
            cantidad_estudiantes=30,
        )

    def _aprobar_profesor(self):
        return AprobarSolicitudRegistroProfesorService.aprobar(self.solicitud.id)

    def test_aprobar_curso_requiere_solicitud_profesor_aprobada(self):
        with self.assertRaises(ValidationError):
            AprobarCursoService.aprobar(self.solicitud.id, self.solicitud_curso.id)

    def test_aprobar_crea_curso(self):
        self._aprobar_profesor()

        curso = AprobarCursoService.aprobar(self.solicitud.id, self.solicitud_curso.id)

        self.assertEqual(curso.codigo, 'CAL101')
        self.assertEqual(curso.profesor.username, 'doc_123123123')
        self.solicitud_curso.refresh_from_db()
        self.assertEqual(self.solicitud_curso.estado, 'aprobada')
        self.assertEqual(self.solicitud_curso.curso_creado_id, curso.id)

    def test_aprobar_curso_ya_procesado_lanza_error(self):
        self._aprobar_profesor()
        AprobarCursoService.aprobar(self.solicitud.id, self.solicitud_curso.id)

        with self.assertRaises(ValidationError):
            AprobarCursoService.aprobar(self.solicitud.id, self.solicitud_curso.id)

    def test_aprobar_curso_inexistente_lanza_error(self):
        self._aprobar_profesor()

        with self.assertRaises(ValidationError):
            AprobarCursoService.aprobar(self.solicitud.id, 999999)

    def test_rechazar_curso(self):
        self._aprobar_profesor()

        AprobarCursoService.rechazar(self.solicitud.id, self.solicitud_curso.id)

        self.solicitud_curso.refresh_from_db()
        self.assertEqual(self.solicitud_curso.estado, 'rechazada')
        self.assertIsNone(self.solicitud_curso.curso_creado)


class SolicitudesViewsHttpTests(TestCase):
    """Smoke tests HTTP end-to-end (Client real, URLs reales) para validar
    que el refactor de views.py a services no rompió la integración: nombres
    de campos POST, decoradores, redirects — no solo la lógica de los
    services en aislamiento."""

    def setUp(self):
        crear_catalogos()
        self.programa = ProgramaAcademico.objects.create(nombre='Ingeniería de Sistemas')
        self.laboratorio = Laboratorio.objects.create(
            nombre='Laboratorio de Física', ubicacion='Bloque 3', activo=True,
        )
        self.fecha = date.today() + timedelta(days=7)
        dia_map = {
            'monday': 'lunes', 'tuesday': 'martes', 'wednesday': 'miercoles',
            'thursday': 'jueves', 'friday': 'viernes', 'saturday': 'sabado', 'sunday': 'domingo',
        }
        HorarioLaboratorio.objects.create(
            laboratorio=self.laboratorio, dia=dia_map[self.fecha.strftime('%A').lower()],
            hora_inicio=time(6, 0), hora_fin=time(20, 0), bloqueado=False,
        )
        self.admin = Usuario.objects.create_user(
            username='admin_http_test', password='x', codigo='ADMHTTP1',
            rol=Rol.objects.get(nombre='Administrador'),
        )

    def test_solicitud_estudiante_post_crea_solicitud(self):
        response = self.client.post('/solicitudes/estudiante/', {
            'nombre': 'Ana Torres',
            'cedula': '111222333',
            'email': 'ana@udea.edu.co',
            'programa': self.programa.nombre,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SolicitudReserva.objects.filter(cedula='111222333').exists())

    def test_solicitud_profesor_normal_post_crea_solicitud(self):
        docente = Usuario.objects.create_user(
            username='profe_http_test', password='x', codigo='DOCHTTP1',
            first_name='Carlos', last_name='Ramirez', rol=Rol.objects.get(nombre='Docente'),
        )
        curso = Curso.objects.create(
            nombre='Física General', codigo='FIS-HTTP', profesor=docente, cantidad_estudiantes=20,
        )

        response = self.client.post('/solicitudes/profesor/', {
            'nombre': 'Carlos Ramirez',
            'cedula': '999888777',
            'curso': curso.id,
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SolicitudReserva.objects.filter(cedula='999888777', tipo_solicitante='profesor').exists()
        )

    def test_solicitud_profesor_libre_post_crea_solicitud(self):
        response = self.client.post('/solicitudes/profesor/', {
            'reserva_libre': '1',
            'nombre': 'Laura Gómez',
            'cedula': '555666777',
            'email': 'laura@udea.edu.co',
            'nombre_grupo': 'Semillero de Robótica',
            'cantidad_asistentes': '5',
            'descripcion_actividad': 'Taller abierto',
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'observaciones': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SolicitudReserva.objects.filter(cedula='555666777', reserva_libre=True).exists()
        )

    def test_solicitud_profesor_libre_con_error_no_crea_nada_y_muestra_error(self):
        response = self.client.post('/solicitudes/profesor/', {
            'reserva_libre': '1',
            'nombre': '',
            'cedula': '555666777',
            'email': 'laura@udea.edu.co',
            'nombre_grupo': 'Semillero de Robótica',
            'cantidad_asistentes': '5',
            'descripcion_actividad': 'Taller abierto',
            'laboratorio': self.laboratorio.id,
            'fecha_reserva': self.fecha.isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('El nombre del profesor es requerido.', response.context['errores_libres'])
        self.assertFalse(SolicitudReserva.objects.filter(cedula='555666777').exists())

    def test_registro_profesor_publico_post_crea_solicitud(self):
        response = self.client.post('/solicitudes/registro-profesor/', {
            'nombre': 'Pedro',
            'apellido': 'Suárez',
            'cedula': '321321321',
            'correo': 'pedro@example.com',
            'programa': 'Ingeniería',
            'curso_nombre': ['Cálculo I'],
            'curso_codigo': ['CAL-HTTP'],
            'curso_cantidad': ['30'],
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SolicitudRegistroProfesor.objects.filter(cedula='321321321').exists())

    def test_detalle_solicitud_profesor_aprobar_profesor(self):
        solicitud = SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='321321321', correo='pedro@example.com',
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            f'/solicitudes/solicitudes-profesores/{solicitud.id}/', {'accion': 'aprobar_profesor'},
        )

        self.assertEqual(response.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'aprobada')
        self.assertIsNotNone(solicitud.usuario_creado)

    def test_detalle_solicitud_profesor_accion_invalida_no_rompe_y_muestra_mensaje(self):
        solicitud = SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='321321321', correo='pedro@example.com',
        )
        self.client.force_login(self.admin)

        # aprobar_curso sin que la solicitud del profesor esté aprobada: antes
        # era un no-op silencioso; ahora responde igual (redirect, no 500) y
        # además informa el error via messages.
        response = self.client.post(
            f'/solicitudes/solicitudes-profesores/{solicitud.id}/',
            {'accion': 'aprobar_curso', 'curso_id': '999999'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        mensajes = [str(m) for m in response.context['messages']]
        self.assertTrue(any('todavía no está aprobada' in m for m in mensajes))


class ModelosCleanValidationTests(TestCase):
    """clean() de Curso, SolicitudRegistroCurso y SolicitudInsumo."""

    def setUp(self):
        crear_catalogos()
        self.laboratorio = Laboratorio.objects.create(nombre='Lab Clean Test', ubicacion='X')
        self.docente = Usuario.objects.create_user(
            username='docente_clean_test', password='x', codigo='DOCCLEAN1',
            rol=Rol.objects.get(nombre='Docente'),
        )
        self.no_docente = Usuario.objects.create_user(
            username='admin_clean_test', password='x', codigo='ADMCLEAN1',
            rol=Rol.objects.get(nombre='Administrador'),
        )

    # -- Curso ------------------------------------------------------------

    def test_curso_valido(self):
        curso = Curso(
            nombre='Física General', codigo='FIS-CLEAN-1',
            profesor=self.docente, cantidad_estudiantes=20,
        )
        curso.full_clean()

    def test_curso_cantidad_estudiantes_cero_es_invalida(self):
        curso = Curso(
            nombre='Física General', codigo='FIS-CLEAN-2',
            profesor=self.docente, cantidad_estudiantes=0,
        )
        with self.assertRaises(ValidationError):
            curso.full_clean()

    def test_curso_profesor_sin_rol_docente_es_invalido(self):
        curso = Curso(
            nombre='Física General', codigo='FIS-CLEAN-3',
            profesor=self.no_docente, cantidad_estudiantes=20,
        )
        with self.assertRaises(ValidationError):
            curso.full_clean()

    # -- SolicitudRegistroCurso ----------------------------------------------

    def test_solicitud_registro_curso_cantidad_valida(self):
        solicitud_profesor = SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='9998887771',
        )
        curso = SolicitudRegistroCurso(
            solicitud_profesor=solicitud_profesor, nombre='Cálculo I',
            codigo='CAL-CLEAN-1', cantidad_estudiantes=30,
        )
        curso.full_clean()

    def test_solicitud_registro_curso_cantidad_cero_es_invalida(self):
        solicitud_profesor = SolicitudRegistroProfesor.objects.create(
            nombre='Pedro', apellido='Suárez', cedula='9998887772',
        )
        curso = SolicitudRegistroCurso(
            solicitud_profesor=solicitud_profesor, nombre='Cálculo I',
            codigo='CAL-CLEAN-2', cantidad_estudiantes=0,
        )
        with self.assertRaises(ValidationError):
            curso.full_clean()

    # -- SolicitudInsumo ----------------------------------------------------

    def test_solicitud_insumo_cantidad_valida(self):
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', nombre='Ana', cedula='1',
            laboratorio=self.laboratorio, fecha_reserva=datetime.now(),
        )
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        solicitud_insumo = SolicitudInsumo(solicitud=solicitud, insumo=insumo, cantidad=1)
        solicitud_insumo.full_clean()

    def test_solicitud_insumo_cantidad_cero_es_invalida(self):
        solicitud = SolicitudReserva.objects.create(
            tipo_solicitante='estudiante', nombre='Ana', cedula='1',
            laboratorio=self.laboratorio, fecha_reserva=datetime.now(),
        )
        insumo = Insumo.objects.create(nombre='Multímetro', descripcion='Para tests')
        solicitud_insumo = SolicitudInsumo(solicitud=solicitud, insumo=insumo, cantidad=0)
        with self.assertRaises(ValidationError):
            solicitud_insumo.full_clean()
