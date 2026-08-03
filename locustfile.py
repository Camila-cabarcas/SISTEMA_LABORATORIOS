"""
locustfile.py — pruebas de carga v3 del Sistema de Laboratorios (14 flujos de negocio).

REQUISITO PREVIO: python manage.py seed_locust
Crea/asegura: Laboratorio E2E (horario lun-vie 06:00-18:00) con 6 Módulos,
Insumo E2E con ítems Disponibles, e2e_admin / e2e_laboratorista, y (desde
v3) un profesor YA REGISTRADO con contraseña conocida — e2e_profesor — más
un Curso a su nombre (ver seed_e2e.py y seed_locust.py).

Variables de entorno relevantes (con sus defaults):

    LOCUST_LAB_ID               id del laboratorio a usar (default 1)
    LOCUST_ADMIN_USER/PASS      credenciales del admin        (default e2e_admin / E2eAdmin!2026)
    LOCUST_LAB_USER/PASS        credenciales del laboratorista (default e2e_laboratorista / E2eLab!2026)
    LOCUST_PROF_USER/PASS       credenciales del profesor YA REGISTRADO (default e2e_profesor / E2eProfesor!2026)
    LOCUST_PROF_NOMBRE          nombre completo del profesor, debe calzar con SolicitudReserva.clean() (default "Profesor E2E")
    LOCUST_PROGRAMA             programa académico activo a usar (default "Ingeniería de Sistemas")
    LOCUST_SPEED_FACTOR         ver "TIMING" abajo (default 60)
    LOCUST_MAX_SLEEP_SEG        tope de las esperas comprimidas admin/laboratorista, en segundos reales (default 300)
    LOCUST_MAX_ESPERA_ENTREGA_SEG  tope de la espera REAL (sin comprimir) hacia fecha_devolucion, en segundos (default 300 = 5 min; ver TIMING)

USO:
    locust -f locustfile.py --host=http://localhost:8000 --headless \
        --users 30 --spawn-rate 3 --run-time 10m --html reporte.html --csv resultados

Este archivo NO define un LoadTestShape — --users/--spawn-rate/--run-time
de la CLI funcionan de forma normal (una versión anterior traía un
LoadTestShape embebido que los ignoraba silenciosamente; se quitó).

────────────────────────────────────────────────────────────────────────────
QUÉ HAY EN v3 (novedades sobre v2)
────────────────────────────────────────────────────────────────────────────
v2 cubría el flujo feliz solicitud→aprobación→préstamo→entrega con 4 clases
(estudiante anónimo, admin, laboratorista×2). v3 agrega 10 clases más para
cubrir otros orígenes de solicitud y varios flujos de excepción:

  1. ProfesorRegistradoConReserva   — login real, solicitud directa con curso propio
  2. ProfesorInvitadoConReserva      — solicitud "reserva libre", sin cuenta
  3. LaboratoristaConPrestamoDirecto — reserva + préstamo sin solicitud previa
  4. InspeccionConItemsDanados       — fuerza 'danado' y verifica la BD
  5. InspeccionConItemsNoEntregados  — fuerza 'no_entregado' (pérdida)
  6. CancelacionDeSolicitud          — un estudiante anónimo intenta cancelar
  7. CancelacionDeReservaAprobada    — cancela una reserva ya aprobada
  8. DevolucionAnticipada            — entrega inmediata tras el préstamo
  9. ProrrogaDeDevolucion            — sondea una prórroga (no existe)
  10. MultiplosModulosEnMismaReserva — solicitud con 2-3 módulos a la vez

Todas reutilizan las MISMAS tres colas (`cola_aprobacion`, `cola_prestamo`,
`cola_entrega`) que ya usaban las 4 clases de v2 — ver "PIPELINE" en la
sección siguiente. Cada fila del CSV ahora lleva `tipo_flujo`: cuando una
solicitud avanza normalmente por el pipeline compartido, `tipo_flujo`
conserva el ORIGEN que la creó (estudiante / profesor_registrado /
profesor_invitado / prestamo_directo); si un flujo especializado (4, 5, 6,
7, 8, 9) intercepta el préstamo antes de que LaboratoristaConEntrega lo
tome, esa clase sobrescribe `tipo_flujo` con su propia etiqueta, porque para
esas filas la dimensión interesante es "qué variante ocurrió", no quién
originó la reserva.

HALLAZGOS DE LA APP QUE ESTOS FLUJOS EXPONEN (documentados, no "arreglados")
────────────────────────────────────────────────────────
Varios de los 10 flujos nuevos existen justamente para ejercitar reglas de
negocio reales del sistema, incluyendo huecos genuinos en la app — no se
simuló ningún comportamiento que el código no tenga:
  - No existe un endpoint público de autocancelación: /reservas/<id>/cancelar/
    exige rol Administrador/Laboratorio. CancelacionDeSolicitud confirma
    esto (302 a /login/) en vez de asumir que "cancelar mi propia solicitud"
    es posible.
  - No existe ninguna función de prórroga (ni formulario, ni endpoint) —
    CambiarEstadoPrestamoForm solo edita el campo `estado`. ProrrogaDeDevolucion
    sondea la ruta más plausible y confirma el 404 en vez de fabricar una.
  - FinalizarInspeccionService, al marcar un ítem 'no_entregado', NO cambia
    su EstadoItem (el comentario en el código dice explícitamente "sin
    cambio de estado") y el catálogo sembrado ni siquiera tiene un estado
    "Perdido". InspeccionConItemsNoEntregados verifica y registra esto.
  - solicitud_estudiante() recorta `modulos_ids` a `ids[:1]` — un estudiante
    JAMÁS puede pedir más de un módulo por ese camino, sin importar cuántos
    envíe. Solo el camino de profesor registrado (ProfesorSolicitudForm)
    asigna la lista completa — por eso MultiplosModulosEnMismaReserva usa
    ese camino, no el de estudiante.
  - El profesor invitado (reserva_libre) guarda la SolicitudReserva llamando
    a .save() directo, sin pasar por ProfesorSolicitudForm — por lo tanto
    SolicitudReserva.clean() (duración 2-8h, horario del laboratorio,
    coincidencia de nombre de profesor) NUNCA se ejecuta para ese camino;
    solo corren las validaciones manuales, más simples, del propio view.

────────────────────────────────────────────────────────────────────────────
PIPELINE (colas compartidas) — igual que v2
────────────────────────────────────────────────────────────────────────────
Un flujo real de este sistema tiene una dependencia estricta entre pasos que
Locust no modela de forma nativa (cada HttpUser normalmente actúa solo, sin
saber qué hicieron otros usuarios). Este archivo usa TRES colas en memoria
(`queue.Queue`) compartidas entre TODAS las clases de usuario: cada etapa
deja su resultado en la cola de la siguiente etapa, que lo recoge en su
propio ciclo de tareas — igual a como trabajarían roles distintos en la
vida real.

LIMITACIÓN IMPORTANTE: las colas viven en el proceso Python de Locust. Esto
funciona perfecto en una corrida normal de un solo proceso. Si se usa Locust
distribuido con múltiples PROCESOS (`--processes N`), cada proceso tendría
su propia cola separada y el pipeline se fragmentaría entre procesos — no
soportado por este diseño.

TIMING — por qué no hay sleep() real de minutos/horas (y su límite real)
────────────────────────────────────────────────────────
La consigna original (5-15 min de revisión, 10-30 min de alistamiento) se
comprime con SPEED_FACTOR antes de convertirse en un sleep real:

    segundos_reales = (minutos_simulados * 60) / SPEED_FACTOR

Con SPEED_FACTOR=60 (default), 1 minuto simulado = 1 segundo real, topado
además por LOCUST_MAX_SLEEP_SEG. Esto es válido para esperas que el script
elige agregar ANTES de actuar (p.ej. "el admin se demora un rato en
revisar") — el servidor solo ve el resultado de esa demora cuando por fin
llega la siguiente petición, sin importar cuánto haya durado "de verdad".

Pero esta compresión NO puede usarse para "adelantar el reloj" hasta un
instante futuro ya fijado — dormir menos tiempo real nunca hace que el reloj
de pared avance más rápido. Y las reglas de negocio de la app comparan
siempre contra su reloj REAL: hora_limite_retiro = fecha_reserva + 30 min
reales (fijo, sin excepción) y fecha_devolucion = hora_fin elegida, que por
validación de SolicitudReserva.clean() debe ser 2-4h reales después de
hora_inicio (mínimo de negocio, no configurable). Es decir: el propio
sistema exige que toda reserva viva al menos 2 horas reales entre el
retiro y la devolución — no hay forma de comprimir eso sin mentirle al
servidor.

Por eso este archivo separa dos tipos de espera:
  - dormir_simulado(minutos): comprimida por SPEED_FACTOR — para las
    demoras de revisión/alistamiento (admin y laboratorista), que se suman
    sobre un punto de referencia ya alcanzado y caben cómodas dentro de la
    ventana real de 30 min de hora_limite_retiro.
  - esperar_real_acotado(momento_objetivo): espera REAL (sin comprimir,
    solo topada por LOCUST_MAX_ESPERA_ENTREGA_SEG) hacia fecha_devolucion,
    porque esa sí es una meta futura ya fijada en el servidor. Con el tope
    por defecto (5 min), la entrega llegará casi siempre bastante ANTES de
    fecha_devolucion (variante real "temprana", honesta) en una corrida
    corta. Para observar de verdad las variantes "a_tiempo" y "retrasada"
    hay que subir LOCUST_MAX_ESPERA_ENTREGA_SEG a varias horas y correr la
    prueba por ese mismo tiempo — no hay atajo posible. La variante que
    efectivamente se reporta (`variante_entrega_real` en el CSV) siempre se
    calcula a partir del timestamp real de entrega, nunca de la intención.

PESOS (relativos, no necesitan sumar 100)
────────────────────────────────────────────────────────
Núcleo (igual que v2): EstudianteConReservaEnHora=40, AdminAprobador=30,
LaboratoristaConPrestamo=20, LaboratoristaConEntrega=10.
Nuevos (v3), como fracción menor del total — son flujos alternativos o de
excepción, no el camino principal: ProfesorRegistradoConReserva=6,
ProfesorInvitadoConReserva=5, LaboratoristaConPrestamoDirecto=4,
InspeccionConItemsDanados=4, DevolucionAnticipada=4, CancelacionDeSolicitud=3,
CancelacionDeReservaAprobada=3, InspeccionConItemsNoEntregados=3,
MultiplosModulosEnMismaReserva=3, ProrrogaDeDevolucion=2.
Nota sobre `e2e_profesor` compartido: los flujos 1 y 10 reutilizan la MISMA
cuenta de profesor sembrada; SolicitudReserva.clean() limita a 8h de
solicitudes por profesor por día, así que bajo carga sostenida es normal
ver 'rechazada_validacion' crecer en esos dos flujos según avanza la
corrida — es la regla de negocio real, no un bug del script.

REPORTES
────────────────────────────────────────────────────────
- CSV `locust_flujos_v3.csv`: una fila por flujo terminado (completado,
  cancelado, sondeado o rechazado por una regla de negocio), con columna
  `tipo_flujo` para poder agrupar por cada uno de los 14 flujos.
- Métricas de tiempo y contadores de resultado se reportan también como
  "requests" custom de Locust (vía events.request.fire), para aprovechar
  directamente sus tablas/gráficos de --html y --csv sin reinventar
  gráficos aparte.
- Al terminar la corrida (evento `quitting`) se imprime en consola un
  resumen de variantes de entrega y un resumen por tipo de flujo.
"""
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from queue import Queue, Empty

from locust import HttpUser, between, events, task

# ── Configuración ────────────────────────────────────────────────────────────

LAB_ID = int(os.environ.get('LOCUST_LAB_ID', '1'))

ADMIN_USER = os.environ.get('LOCUST_ADMIN_USER', 'e2e_admin')
ADMIN_PASS = os.environ.get('LOCUST_ADMIN_PASS', 'E2eAdmin!2026')
LAB_USER = os.environ.get('LOCUST_LAB_USER', 'e2e_laboratorista')
LAB_PASS = os.environ.get('LOCUST_LAB_PASS', 'E2eLab!2026')
PROF_USER = os.environ.get('LOCUST_PROF_USER', 'e2e_profesor')
PROF_PASS = os.environ.get('LOCUST_PROF_PASS', 'E2eProfesor!2026')
PROF_NOMBRE = os.environ.get('LOCUST_PROF_NOMBRE', 'Profesor E2E')
PROGRAMA = os.environ.get('LOCUST_PROGRAMA', 'Ingeniería de Sistemas')

SPEED_FACTOR = float(os.environ.get('LOCUST_SPEED_FACTOR', '60'))
MAX_SLEEP_SEG = float(os.environ.get('LOCUST_MAX_SLEEP_SEG', '300'))
MAX_ESPERA_ENTREGA_SEG = float(os.environ.get('LOCUST_MAX_ESPERA_ENTREGA_SEG', '300'))

# Desfases (minutos reales) del "turno" pedido respecto al momento de la
# solicitud: negativos = turno que ya inició hace poco (llegada un poco
# tarde); 0 = turno es ahora mismo; positivos = turno próximo, por el que
# el estudiante SÍ espera de verdad (son pocos minutos, no horas — ver
# TIMING en el docstring del módulo).
OFFSETS_SOLICITUD_MIN = [-25, -15, -5, 0, 0, 3, 8]

NOMBRES = ['Ana', 'Luis', 'Camila', 'Andrés', 'Valentina', 'Santiago', 'Laura', 'Julián', 'Mariana', 'Diego']
APELLIDOS = ['Gómez', 'Rodríguez', 'Pérez', 'Martínez', 'López', 'García', 'Hernández', 'Torres']

CSV_PATH = 'locust_flujos_v3.csv'
CSV_COLUMNAS = [
    'tipo_flujo', 'cedula', 'hora_objetivo_slot',
    'hora_solicitud', 'resultado_solicitud',
    'hora_aprobacion', 'tiempo_solicitud_aprobacion_seg',
    'hora_prestamo', 'tiempo_aprobacion_prestamo_seg', 'resultado_prestamo',
    'variante_entrega_intencion', 'hora_entrega', 'fecha_devolucion_esperada',
    'tiempo_prestamo_entrega_seg', 'desviacion_entrega_seg', 'variante_entrega_real',
    'items_bien', 'items_danado', 'items_no_entregado', 'item_estado_confirmado_bd',
    'fue_cancelada', 'momento_cancelacion', 'motivo_cancelacion',
    'prorroga_solicitada', 'prorroga_resultado',
    'cantidad_modulos_solicitados', 'cantidad_modulos_confirmados',
    'resultado_final',
]

ITEM_OPTION_RE = re.compile(r'<option value="(\d+)">')
ESTADO_ITEM_RE = re.compile(r'name="estado_(\d+)"')
RESERVA_ID_RE = re.compile(r'/reservas/(\d+)/')
PRESTAMO_ID_RE = re.compile(r'/prestamos/(\d+)/')

# ── Colas del pipeline (compartidas entre clases de usuario) ─────────────────

cola_aprobacion = Queue()
cola_prestamo = Queue()
cola_entrega = Queue()

_csv_lock = threading.Lock()
_resumen_lock = threading.Lock()
_resumen_conteos = {}       # variante_real ('temprana'/'a_tiempo'/'retrasada') -> cantidad
_resumen_por_flujo = {}     # tipo_flujo -> {resultado_final: cantidad}

_ids_conocidos_lock = threading.Lock()
_ids_reserva_conocidos = []  # ids de reservas ya vistas por cualquier flujo (para CancelacionDeSolicitud)

_curso_lock = threading.Lock()
_curso_id_cache = {'id': None, 'intentado': False}

_insumo_lock = threading.Lock()
_insumo_id_cache = {'id': None, 'intentado': False}


def _iso(dt):
    return dt.isoformat() if dt else ''


def _registrar_fila_csv(fila):
    existe = os.path.exists(CSV_PATH)
    with _csv_lock:
        with open(CSV_PATH, 'a', encoding='utf-8', newline='') as f:
            if not existe:
                f.write(','.join(CSV_COLUMNAS) + '\n')
            valores = [str(fila.get(col, '')) for col in CSV_COLUMNAS]
            f.write(','.join(v.replace(',', ';') for v in valores) + '\n')

    tipo_flujo = fila.get('tipo_flujo') or 'desconocido'
    resultado = fila.get('resultado_final') or 'desconocido'
    with _resumen_lock:
        bucket = _resumen_por_flujo.setdefault(tipo_flujo, {})
        bucket[resultado] = bucket.get(resultado, 0) + 1


def _sumar_resumen(clave):
    with _resumen_lock:
        _resumen_conteos[clave] = _resumen_conteos.get(clave, 0) + 1


def _reserva_conocida_agregar(reserva_id):
    with _ids_conocidos_lock:
        _ids_reserva_conocidos.append(reserva_id)
        if len(_ids_reserva_conocidos) > 200:
            del _ids_reserva_conocidos[:100]


def _reserva_conocida_muestra():
    with _ids_conocidos_lock:
        return random.choice(_ids_reserva_conocidos) if _ids_reserva_conocidos else None


def dormir_simulado(minutos_simulados):
    """Duerme el tiempo real equivalente a `minutos_simulados` de tiempo de
    negocio, comprimido por SPEED_FACTOR (ver docstring del módulo)."""
    segundos = max(0.0, (minutos_simulados * 60.0) / SPEED_FACTOR)
    segundos = min(segundos, MAX_SLEEP_SEG)
    time.sleep(segundos)


def esperar_real_acotado(momento_objetivo, tope_seg):
    """Duerme tiempo REAL (sin comprimir) hacia `momento_objetivo`, topado en
    `tope_seg`. Si el tope no alcanza a cubrir la distancia real, la espera
    se queda corta a propósito — ver TIMING en el docstring del módulo."""
    delta_seg = (momento_objetivo - datetime.now()).total_seconds()
    if delta_seg <= 0:
        return
    time.sleep(min(delta_seg, tope_seg))


def login_django(client, username, password):
    """Login estándar de Django: token CSRF de /login/ + credenciales."""
    resp = client.get('/login/', name='/login/ [GET]')
    token = resp.cookies.get('csrftoken')
    if not token:
        return False
    resp = client.post(
        '/login/',
        data={'username': username, 'password': password, 'csrfmiddlewaretoken': token},
        headers={'Referer': f'{client.base_url}/login/'},
        name='/login/ [POST]',
    )
    return 'sessionid' in client.cookies


def nueva_cedula():
    return str(random.randint(1_000_000_000, 9_999_999_999))


def nuevo_nombre():
    return f'{random.choice(NOMBRES)} {random.choice(APELLIDOS)}'


def fire_metric(user, name, seconds, exception=None):
    """Reporta una métrica custom como si fuera un 'request' de Locust —
    así aparece en las tablas/gráficos de --html y --csv sin código aparte."""
    user.environment.events.request.fire(
        request_type='FLUJO',
        name=name,
        response_time=max(0.0, seconds) * 1000.0,
        response_length=0,
        exception=exception,
        context={},
    )


def obtener_insumo_id(client):
    """Resuelve (una sola vez por proceso, con caché) el id de un Insumo con
    stock real vía la API pública /solicitudes/api/insumos/. Sin esto, las
    solicitudes se crean sin ReservaInsumo — la reserva llega a préstamo
    pero sin ningún ItemInventario enlazado, así que inspeccionar/verificar
    ítems (flujos 4 y 5) no tendría nada real que revisar. Prefiere
    'Insumo E2E' (el que seed_locust garantiza con stock); si no está,
    cae al primero de la lista con cantidad_disponible > 0 — tomar
    ciegamente el primero de la API (sin filtrar stock) fue el bug real de
    la primera versión de este helper: la API no ordena por disponibilidad,
    así que data[0] bien puede ser un insumo con 0 unidades."""
    with _insumo_lock:
        if _insumo_id_cache['intentado']:
            return _insumo_id_cache['id']
        _insumo_id_cache['intentado'] = True

        with client.get(
            '/solicitudes/api/insumos/',
            name='/solicitudes/api/insumos/',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return None
            try:
                data = resp.json()
            except ValueError:
                return None

        candidato = next((i for i in data if i.get('nombre') == 'Insumo E2E'), None)
        if not candidato:
            candidato = next((i for i in data if i.get('cantidad_disponible', 0) > 0), None)
        if candidato:
            _insumo_id_cache['id'] = candidato['id']
        return _insumo_id_cache['id']


def obtener_curso_id(client):
    """Resuelve (una sola vez por proceso, con caché) el id del Curso de
    PROF_NOMBRE vía la API pública /solicitudes/cursos-profesor/ — evita
    depender de un id de Curso hardcodeado que solo existiría en una BD
    concreta."""
    with _curso_lock:
        if _curso_id_cache['intentado']:
            return _curso_id_cache['id']
        _curso_id_cache['intentado'] = True

        with client.get(
            '/solicitudes/cursos-profesor/',
            params={'nombre': PROF_NOMBRE},
            name='/solicitudes/cursos-profesor/',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return None
            try:
                data = resp.json()
            except ValueError:
                return None

        cursos = data.get('cursos') or []
        if cursos:
            _curso_id_cache['id'] = cursos[0]['id']
        return _curso_id_cache['id']


def _consultar_modulos(client):
    hoy = datetime.now().date().isoformat()
    with client.get(
        f'/laboratorio/{LAB_ID}/modulos/disponibles-publica/',
        params={'fecha': hoy},
        name='/laboratorio/[id]/modulos/disponibles-publica/',
        catch_response=True,
    ) as resp:
        if resp.status_code == 200:
            resp.success()
        else:
            resp.failure(f'Status inesperado: {resp.status_code}')
            return []
        try:
            return resp.json().get('modulos', [])
        except ValueError:
            return []


def obtener_modulos_disponibles(client, cantidad):
    disponibles = [m['id'] for m in _consultar_modulos(client) if m.get('seleccionable')]
    random.shuffle(disponibles)
    return disponibles[:cantidad]


def obtener_modulos_estado(client):
    return {m['id']: m.get('estado') for m in _consultar_modulos(client)}


def verificar_estado_item_bd(client, item_inventario_id):
    """Confirma en /inventario/items/ (BD real, no el código fuente) el
    estado actual de un ItemInventario por su id — la tabla lista
    <td>id</td><td>codigo</td><td>insumo</td><td>estado</td> por fila."""
    if not item_inventario_id:
        return None
    with client.get(
        '/inventario/items/',
        name='/inventario/items/ [verificación]',
        catch_response=True,
    ) as resp:
        if resp.status_code == 200:
            resp.success()
        else:
            resp.failure(f'Status inesperado: {resp.status_code}')
            return None
        texto = resp.text
    patron = re.compile(
        r'<td>' + re.escape(str(item_inventario_id)) + r'</td>\s*<td>[^<]*</td>\s*<td>[^<]*</td>\s*<td>([^<]*)</td>'
    )
    m = patron.search(texto)
    return m.group(1).strip() if m else None


def realizar_entrega(user, item, objetivo_dt, estado_forzado=None):
    """Ejecuta iniciar-inspección + inspeccionar + marcar-devuelto sobre un
    préstamo activo (`item` sacado de cola_entrega), esperando en tiempo
    real (topado por MAX_ESPERA_ENTREGA_SEG) hasta `objetivo_dt`. Si
    `estado_forzado` se da ('bien'/'danado'/'no_entregado'), TODOS los
    ítems se marcan así; si no, se sortea aleatoriamente 85/10/5 como en el
    flujo normal. Devuelve un dict con los datos resultantes, o None si
    algún paso HTTP falló (ya reportado a Locust como fallo)."""
    esperar_real_acotado(objetivo_dt, MAX_ESPERA_ENTREGA_SEG)

    prestamo_id = item['prestamo_id']
    client = user.client
    token = client.cookies.get('csrftoken')
    if not token:
        return None

    with client.post(
        f'/prestamos/{prestamo_id}/iniciar-inspeccion/',
        data={'csrfmiddlewaretoken': token},
        headers={'Referer': f'{client.base_url}/prestamos/{prestamo_id}/'},
        name='/prestamos/[id]/iniciar-inspeccion/',
        catch_response=True,
    ) as resp:
        if resp.status_code == 200:
            resp.success()
        else:
            resp.failure(f'Status inesperado: {resp.status_code}')
            return None
        texto = resp.text

    item_ids = ESTADO_ITEM_RE.findall(texto)
    conteo = {'bien': 0, 'danado': 0, 'no_entregado': 0}

    data = {'csrfmiddlewaretoken': token, 'accion': 'marcar_devuelto'}
    for iid in item_ids:
        estado = estado_forzado or random.choices(['bien', 'danado', 'no_entregado'], weights=[85, 10, 5])[0]
        data[f'estado_{iid}'] = estado
        data[f'observaciones_{iid}'] = 'Inspección generada por Locust (v3)'
        conteo[estado] += 1

    token = client.cookies.get('csrftoken') or token
    data['csrfmiddlewaretoken'] = token
    with client.post(
        f'/prestamos/{prestamo_id}/inspeccionar/',
        data=data,
        headers={'Referer': f'{client.base_url}/prestamos/{prestamo_id}/inspeccionar/'},
        name='/prestamos/[id]/inspeccionar/',
        catch_response=True,
    ) as resp:
        if resp.status_code == 200:
            resp.success()
        else:
            resp.failure(f'Status inesperado: {resp.status_code}')
            return None

    token = client.cookies.get('csrftoken') or token
    with client.post(
        f'/prestamos/{prestamo_id}/marcar-devuelto/',
        data={'csrfmiddlewaretoken': token},
        headers={'Referer': f'{client.base_url}/prestamos/{prestamo_id}/marcar-devuelto/'},
        name='/prestamos/[id]/marcar-devuelto/',
        catch_response=True,
    ) as resp:
        if resp.status_code in (200, 302):
            resp.success()
        else:
            resp.failure(f'Status inesperado: {resp.status_code}')
            return None

    hora_entrega = datetime.now()
    return {
        'conteo': conteo,
        'hora_entrega': hora_entrega,
        'tiempo_entrega_seg': (hora_entrega - item['hora_prestamo']).total_seconds(),
        'desviacion_seg': (hora_entrega - item['fecha_devolucion_esperada']).total_seconds(),
        'prestamo_id': prestamo_id,
        'item_ids_prestamo': item_ids,
    }


# ── a) Estudiante: solicita una reserva a una hora específica ───────────────

class EstudianteConReservaEnHora(HttpUser):
    """Solicita una reserva pública (sin login) para un horario específico:
    un turno que ya inició hace poco, que es ahora mismo, o uno próximo (en
    cuyo caso SÍ espera de verdad, en tiempo real, a que llegue — son pocos
    minutos, no horas)."""

    weight = 40
    wait_time = between(1, 3)

    @task
    def solicitar_reserva(self):
        offset_min = random.choice(OFFSETS_SOLICITUD_MIN)
        momento_slot = datetime.now() + timedelta(minutes=offset_min)
        if offset_min > 0:
            time.sleep(offset_min * 60)
        hora_inicio = momento_slot.time().replace(second=0, microsecond=0)
        hora_str = hora_inicio.strftime('%H:%M')
        hoy = momento_slot.date()

        margen_horas = max(2.0, min(4.0, (18 * 60 - hora_inicio.hour * 60 - hora_inicio.minute) / 60.0))
        duracion_horas = random.choice([h for h in [2, 2.5, 3, 3.5, 4] if h <= margen_horas]) if margen_horas >= 2 else 2
        hora_fin = (momento_slot + timedelta(hours=duracion_horas)).time()

        cedula = nueva_cedula()
        nombre = nuevo_nombre()
        insumo_id = obtener_insumo_id(self.client)

        resp = self.client.get('/solicitudes/estudiante/', name='/solicitudes/estudiante/ [GET]')
        token = resp.cookies.get('csrftoken')
        if not token:
            return

        hora_solicitud = datetime.now()

        data = {
            'csrfmiddlewaretoken': token,
            'nombre': nombre,
            'cedula': cedula,
            'programa': PROGRAMA,
            'laboratorio': str(LAB_ID),
            'fecha_reserva': hoy.isoformat(),
            'hora_inicio': hora_inicio.strftime('%H:%M'),
            'hora_fin': hora_fin.strftime('%H:%M'),
            'observaciones': 'Generado por Locust (flujo v3)',
            'insumos_ids': str(insumo_id) if insumo_id else '',
            'insumos_cantidades': '1' if insumo_id else '',
        }

        with self.client.post(
            '/solicitudes/estudiante/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/solicitudes/estudiante/'},
            name='/solicitudes/estudiante/ [POST]',
            catch_response=True,
        ) as resp:
            # La vista siempre re-renderiza el form (200) si hay errores de
            # validación (horario fuera de rango, día no disponible, etc.) o
            # redirige a /exitosa/ (200 tras seguir el redirect) si se creó.
            exito = '/solicitudes/exitosa/' in resp.url
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

        if exito:
            fecha_devolucion_esperada = datetime.combine(hoy, hora_fin)
            cola_aprobacion.put({
                'tipo_flujo': 'estudiante',
                'cedula': cedula,
                'hora_objetivo_slot': hora_str,
                'hora_solicitud': hora_solicitud,
                'fecha_devolucion_esperada': fecha_devolucion_esperada,
            })
        else:
            _registrar_fila_csv({
                'tipo_flujo': 'estudiante',
                'cedula': cedula,
                'hora_objetivo_slot': hora_str,
                'hora_solicitud': hora_solicitud.isoformat(),
                'resultado_solicitud': 'rechazada_validacion' if resp.status_code == 200 else f'error_http_{resp.status_code}',
                'resultado_final': 'incompleto',
            })
            fire_metric(self, 'ERROR: solicitud rechazada por validación', 0, exception=Exception('validación de negocio'))


# ── b) Admin: aprueba solicitudes pendientes ────────────────────────────────

class AdminAprobador(HttpUser):
    """Espera 5-15 minutos simulados tras la solicitud, busca la reserva por
    cédula (como lo haría un admin real en la lista) y la aprueba. Sirve por
    igual a cualquier origen (estudiante, profesor registrado, profesor
    invitado) porque busca por cédula, no por tipo de solicitante."""

    weight = 30
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, ADMIN_USER, ADMIN_PASS)

    @task
    def aprobar_siguiente(self):
        if not self.autenticado:
            return
        try:
            item = cola_aprobacion.get(block=False)
        except Empty:
            return

        dormir_simulado(random.uniform(5, 15))

        with self.client.get(
            f'/reservas/?buscar={item["cedula"]}',
            name='/reservas/?buscar=[cedula]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
            texto = resp.text if resp.status_code == 200 else ''

        ids = RESERVA_ID_RE.findall(texto)
        if not ids:
            _registrar_fila_csv({
                'tipo_flujo': item.get('tipo_flujo', 'estudiante'),
                'cedula': item['cedula'],
                'hora_objetivo_slot': item['hora_objetivo_slot'],
                'hora_solicitud': item['hora_solicitud'].isoformat(),
                'resultado_solicitud': 'creada',
                'resultado_prestamo': 'reserva_no_encontrada',
                'resultado_final': 'incompleto',
            })
            return
        reserva_id = ids[0]
        _reserva_conocida_agregar(reserva_id)

        token = self.client.cookies.get('csrftoken')
        if not token:
            return

        with self.client.post(
            f'/reservas/{reserva_id}/aprobar/',
            data={'accion': 'aprobar', 'csrfmiddlewaretoken': token},
            headers={'Referer': f'{self.client.base_url}/reservas/{reserva_id}/'},
            name='/reservas/[id]/aprobar/',
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 302):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return

        hora_aprobacion = datetime.now()
        tiempo_aprobacion = (hora_aprobacion - item['hora_solicitud']).total_seconds()
        fire_metric(self, 'TIEMPO: solicitud -> aprobación', tiempo_aprobacion)

        cola_prestamo.put({
            **item,
            'reserva_id': reserva_id,
            'hora_aprobacion': hora_aprobacion,
            'tiempo_solicitud_aprobacion_seg': tiempo_aprobacion,
        })


# ── c) Laboratorista: crea el préstamo dentro de la ventana de retiro ───────

class LaboratoristaConPrestamo(HttpUser):
    """Espera 10-30 minutos simulados tras la aprobación y crea el préstamo.
    Si para entonces ya pasó hora_limite_retiro (fecha_reserva + 30 min
    reales) la app responde 'expirada' — se registra como error de negocio,
    no como fallo del script."""

    weight = 20
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def crear_prestamo_siguiente(self):
        if not self.autenticado:
            return
        try:
            item = cola_prestamo.get(block=False)
        except Empty:
            return

        dormir_simulado(random.uniform(10, 30))

        reserva_id = item['reserva_id']
        with self.client.get(
            f'/prestamos/crear/{reserva_id}/',
            name='/prestamos/crear/[reserva_id]/ [GET]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return
            texto = resp.text

        if 'Límite de retiro expirado' in texto:
            fire_metric(self, 'ERROR: préstamo fuera de horario (expirada)', 0,
                        exception=Exception('hora_limite_retiro superada'))
            _registrar_fila_csv({
                'tipo_flujo': item.get('tipo_flujo', 'estudiante'),
                'cedula': item['cedula'], 'hora_objetivo_slot': item['hora_objetivo_slot'],
                'hora_solicitud': item['hora_solicitud'].isoformat(), 'resultado_solicitud': 'creada',
                'hora_aprobacion': item['hora_aprobacion'].isoformat(),
                'tiempo_solicitud_aprobacion_seg': item['tiempo_solicitud_aprobacion_seg'],
                'resultado_prestamo': 'expirada', 'resultado_final': 'incompleto',
            })
            return
        if 'no disponible aún' in texto:
            fire_metric(self, 'ERROR: préstamo fuera de horario (antes de hora)', 0,
                         exception=Exception('reserva aún no disponible'))
            _registrar_fila_csv({
                'tipo_flujo': item.get('tipo_flujo', 'estudiante'),
                'cedula': item['cedula'], 'hora_objetivo_slot': item['hora_objetivo_slot'],
                'hora_solicitud': item['hora_solicitud'].isoformat(), 'resultado_solicitud': 'creada',
                'hora_aprobacion': item['hora_aprobacion'].isoformat(),
                'tiempo_solicitud_aprobacion_seg': item['tiempo_solicitud_aprobacion_seg'],
                'resultado_prestamo': 'antes_de_hora', 'resultado_final': 'incompleto',
            })
            return

        item_ids = ITEM_OPTION_RE.findall(texto)
        token = self.client.cookies.get('csrftoken')
        if not token:
            return

        data = {'csrfmiddlewaretoken': token}
        if item_ids:
            data['items'] = item_ids[0]

        with self.client.post(
            f'/prestamos/crear/{reserva_id}/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/prestamos/crear/{reserva_id}/'},
            name='/prestamos/crear/[reserva_id]/ [POST]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return
            url_final = resp.url

        ids = PRESTAMO_ID_RE.findall(url_final)
        if not ids:
            return
        prestamo_id = ids[0]

        hora_prestamo = datetime.now()
        tiempo_prestamo = (hora_prestamo - item['hora_aprobacion']).total_seconds()
        fire_metric(self, 'TIEMPO: aprobación -> préstamo', tiempo_prestamo)

        cola_entrega.put({
            **item,
            'prestamo_id': prestamo_id,
            'hora_prestamo': hora_prestamo,
            'tiempo_aprobacion_prestamo_seg': tiempo_prestamo,
            'item_inventario_id': item_ids[0] if item_ids else None,
        })


# ── d) Laboratorista: inspecciona y entrega (temprana / a tiempo / retrasada) ─

class LaboratoristaConEntrega(HttpUser):
    """Recoge préstamos activos y los devuelve en 3 variantes de timing
    respecto a fecha_devolucion_esperada (= hora_fin elegida en la solicitud):
    temprana (antes), a_tiempo (cerca) o retrasada (después, estrés)."""

    weight = 10
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    def _entregar(self, item, variante_intencion, offset_min_lo, offset_min_hi):
        offset_min = random.uniform(offset_min_lo, offset_min_hi)
        objetivo = item['fecha_devolucion_esperada'] + timedelta(minutes=offset_min)

        resultado = realizar_entrega(self, item, objetivo)
        if resultado is None:
            return

        desviacion = resultado['desviacion_seg']
        if desviacion < -300:
            variante_real = 'temprana'
        elif desviacion > 300:
            variante_real = 'retrasada'
        else:
            variante_real = 'a_tiempo'

        fire_metric(self, 'TIEMPO: préstamo -> entrega', resultado['tiempo_entrega_seg'])
        fire_metric(self, f'TIEMPO: desviación entrega ({variante_real})', abs(desviacion))
        fire_metric(self, f'RESULTADO: entrega {variante_real}', 0)
        _sumar_resumen(variante_real)

        conteo = resultado['conteo']
        _registrar_fila_csv({
            'tipo_flujo': item.get('tipo_flujo', 'estudiante'),
            'cedula': item['cedula'], 'hora_objetivo_slot': item['hora_objetivo_slot'],
            'hora_solicitud': item['hora_solicitud'].isoformat(), 'resultado_solicitud': 'creada',
            'hora_aprobacion': item['hora_aprobacion'].isoformat(),
            'tiempo_solicitud_aprobacion_seg': item['tiempo_solicitud_aprobacion_seg'],
            'hora_prestamo': item['hora_prestamo'].isoformat(),
            'tiempo_aprobacion_prestamo_seg': item['tiempo_aprobacion_prestamo_seg'],
            'resultado_prestamo': 'creado',
            'variante_entrega_intencion': variante_intencion,
            'hora_entrega': resultado['hora_entrega'].isoformat(),
            'fecha_devolucion_esperada': item['fecha_devolucion_esperada'].isoformat(),
            'tiempo_prestamo_entrega_seg': resultado['tiempo_entrega_seg'],
            'desviacion_entrega_seg': desviacion,
            'variante_entrega_real': variante_real,
            'items_bien': conteo['bien'], 'items_danado': conteo['danado'],
            'items_no_entregado': conteo['no_entregado'],
            'resultado_final': 'completo',
        })

    @task(7)
    def entrega_a_tiempo(self):
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return
        self._entregar(item, 'a_tiempo', -10, 10)

    @task(2)
    def entrega_temprana(self):
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return
        self._entregar(item, 'temprana', -60, -30)

    @task(2)
    def entrega_retrasada(self):
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return
        self._entregar(item, 'retrasada', 30, 90)


# ── 1) Profesor YA REGISTRADO: solicitud directa con curso propio ───────────

class ProfesorRegistradoConReserva(HttpUser):
    """(v3) Profesor YA REGISTRADO (login real con e2e_profesor): crea su
    solicitud directamente contra /solicitudes/profesor/ (requiere un Curso
    propio, resuelto vía la API pública cursos-profesor). La app sigue
    exigiendo aprobación de un Admin/Laboratorio igual que para un
    estudiante — no existe, en el código real, un camino de 'no requiere
    admin' para profesores registrados —, así que este flujo entrega su
    resultado a la MISMA cola_aprobacion que EstudianteConReservaEnHora,
    reutilizando AdminAprobador/LaboratoristaConPrestamo/LaboratoristaConEntrega
    sin cambios."""

    weight = 6
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, PROF_USER, PROF_PASS)

    @task
    def solicitar_reserva(self):
        if not self.autenticado:
            return

        curso_id = obtener_curso_id(self.client)
        if not curso_id:
            return

        offset_min = random.choice(OFFSETS_SOLICITUD_MIN)
        momento_slot = datetime.now() + timedelta(minutes=offset_min)
        if offset_min > 0:
            time.sleep(offset_min * 60)
        hora_inicio = momento_slot.time().replace(second=0, microsecond=0)
        hora_str = hora_inicio.strftime('%H:%M')
        hoy = momento_slot.date()

        margen_horas = max(2.0, min(4.0, (18 * 60 - hora_inicio.hour * 60 - hora_inicio.minute) / 60.0))
        duracion_horas = random.choice([h for h in [2, 2.5, 3, 3.5, 4] if h <= margen_horas]) if margen_horas >= 2 else 2
        hora_fin = (momento_slot + timedelta(hours=duracion_horas)).time()

        cedula = nueva_cedula()
        insumo_id = obtener_insumo_id(self.client)

        resp = self.client.get('/solicitudes/profesor/', name='/solicitudes/profesor/ [GET]')
        token = resp.cookies.get('csrftoken')
        if not token:
            return

        hora_solicitud = datetime.now()
        data = {
            'csrfmiddlewaretoken': token,
            'nombre': PROF_NOMBRE,
            'cedula': cedula,
            'curso': str(curso_id),
            'laboratorio': str(LAB_ID),
            'fecha_reserva': hoy.isoformat(),
            'hora_inicio': hora_inicio.strftime('%H:%M'),
            'hora_fin': hora_fin.strftime('%H:%M'),
            'observaciones': 'Generado por Locust (v3 - profesor registrado)',
            'insumos_ids': str(insumo_id) if insumo_id else '',
            'insumos_cantidades': '1' if insumo_id else '',
            'modulos_ids': '',
        }
        with self.client.post(
            '/solicitudes/profesor/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/solicitudes/profesor/'},
            name='/solicitudes/profesor/ [POST]',
            catch_response=True,
        ) as resp:
            exito = '/solicitudes/exitosa/' in resp.url
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

        if exito:
            cola_aprobacion.put({
                'tipo_flujo': 'profesor_registrado',
                'cedula': cedula,
                'hora_objetivo_slot': hora_str,
                'hora_solicitud': hora_solicitud,
                'fecha_devolucion_esperada': datetime.combine(hoy, hora_fin),
            })
        else:
            _registrar_fila_csv({
                'tipo_flujo': 'profesor_registrado',
                'cedula': cedula, 'hora_objetivo_slot': hora_str,
                'hora_solicitud': hora_solicitud.isoformat(),
                'resultado_solicitud': 'rechazada_validacion' if resp.status_code == 200 else f'error_http_{resp.status_code}',
                'resultado_final': 'incompleto',
            })


# ── 2) Profesor INVITADO: solicitud "reserva libre", sin cuenta ─────────────

class ProfesorInvitadoConReserva(HttpUser):
    """(v3) Profesor SIN cuenta (invitado): usa el camino 'reserva_libre' de
    /solicitudes/profesor/, que en el código guarda la SolicitudReserva de
    forma directa (sin pasar por ProfesorSolicitudForm) — por lo tanto NO
    corre SolicitudReserva.clean() (duración, horario, coincidencia de
    nombre de profesor), solo las validaciones manuales del propio view
    (campos presentes, fecha >= hoy). Solo un Administrador puede aprobar
    una reserva_libre (lo exige aprobar_reserva); como AdminAprobador ya usa
    credenciales de Administrador, no hace falta ningún cambio ahí."""

    weight = 5
    wait_time = between(1, 3)

    @task
    def solicitar_reserva_libre(self):
        offset_min = random.choice(OFFSETS_SOLICITUD_MIN)
        momento_slot = datetime.now() + timedelta(minutes=offset_min)
        if offset_min > 0:
            time.sleep(offset_min * 60)
        hora_inicio = momento_slot.time().replace(second=0, microsecond=0)
        hora_str = hora_inicio.strftime('%H:%M')
        hoy = momento_slot.date()
        hora_fin = (momento_slot + timedelta(hours=random.choice([2, 3, 4]))).time()

        cedula = nueva_cedula()
        nombre = nuevo_nombre()
        insumo_id = obtener_insumo_id(self.client)

        resp = self.client.get('/solicitudes/profesor/', name='/solicitudes/profesor/ [GET]')
        token = resp.cookies.get('csrftoken')
        if not token:
            return

        hora_solicitud = datetime.now()
        data = {
            'csrfmiddlewaretoken': token,
            'reserva_libre': '1',
            'nombre': nombre,
            'cedula': cedula,
            'nombre_grupo': 'Grupo invitado Locust',
            'cantidad_asistentes': str(random.randint(5, 20)),
            'descripcion_actividad': 'Actividad generada por Locust (v3 - profesor invitado)',
            'laboratorio': str(LAB_ID),
            'fecha_reserva': hoy.isoformat(),
            'hora_inicio': hora_inicio.strftime('%H:%M'),
            'hora_fin': hora_fin.strftime('%H:%M'),
            'observaciones': 'Generado por Locust (v3)',
            'insumos_ids': str(insumo_id) if insumo_id else '',
            'insumos_cantidades': '1' if insumo_id else '',
            'modulos_ids': '',
        }
        with self.client.post(
            '/solicitudes/profesor/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/solicitudes/profesor/'},
            name='/solicitudes/profesor/ [POST reserva_libre]',
            catch_response=True,
        ) as resp:
            exito = '/solicitudes/exitosa/' in resp.url
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

        if exito:
            cola_aprobacion.put({
                'tipo_flujo': 'profesor_invitado',
                'cedula': cedula,
                'hora_objetivo_slot': hora_str,
                'hora_solicitud': hora_solicitud,
                'fecha_devolucion_esperada': datetime.combine(hoy, hora_fin),
            })
        else:
            _registrar_fila_csv({
                'tipo_flujo': 'profesor_invitado',
                'cedula': cedula, 'hora_objetivo_slot': hora_str,
                'hora_solicitud': hora_solicitud.isoformat(),
                'resultado_solicitud': 'rechazada_validacion' if resp.status_code == 200 else f'error_http_{resp.status_code}',
                'resultado_final': 'incompleto',
            })


# ── 3) Laboratorista: préstamo directo, sin solicitud previa ────────────────

class LaboratoristaConPrestamoDirecto(HttpUser):
    """(v3) Caso de excepción: el laboratorista registra una reserva manual
    vía /reservas/crear/ (Admin/Laboratorio) en vez de esperar una solicitud
    pública. CrearReservaService, dentro de esa vista, aprueba la reserva
    automáticamente al crearla — así que este flujo pasa directo a crear el
    préstamo, sin pasar por cola_aprobacion."""

    weight = 4
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def crear_reserva_y_prestamo(self):
        if not self.autenticado:
            return

        ahora = datetime.now()
        hora_inicio = ahora.time().replace(second=0, microsecond=0)
        hora_fin = (ahora + timedelta(hours=2)).time()
        cedula = nueva_cedula()
        nombre = nuevo_nombre()
        insumo_id = obtener_insumo_id(self.client)

        resp = self.client.get('/reservas/crear/', name='/reservas/crear/ [GET]')
        token = resp.cookies.get('csrftoken')
        if not token:
            return

        hora_solicitud = datetime.now()
        data = {
            'csrfmiddlewaretoken': token,
            'tipo_solicitante': 'estudiante',
            'nombre': nombre, 'cedula': cedula, 'programa': PROGRAMA,
            'laboratorio': str(LAB_ID),
            'fecha': ahora.date().isoformat(),
            'hora_inicio': hora_inicio.strftime('%H:%M'),
            'hora_fin': hora_fin.strftime('%H:%M'),
            'observaciones': 'Reserva directa generada por Locust (v3)',
            'insumos_ids': str(insumo_id) if insumo_id else '',
            'insumos_cantidades': '1' if insumo_id else '',
        }
        with self.client.post(
            '/reservas/crear/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/reservas/crear/'},
            name='/reservas/crear/ [POST]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return
            url_final = resp.url

        ids = RESERVA_ID_RE.findall(url_final)
        if not ids:
            _registrar_fila_csv({
                'tipo_flujo': 'prestamo_directo', 'cedula': cedula,
                'hora_solicitud': hora_solicitud.isoformat(),
                'resultado_solicitud': 'rechazada_validacion',
                'resultado_final': 'incompleto',
            })
            return
        reserva_id = ids[0]
        _reserva_conocida_agregar(reserva_id)

        with self.client.get(
            f'/prestamos/crear/{reserva_id}/',
            name='/prestamos/crear/[reserva_id]/ [GET]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return
            texto = resp.text

        item_ids = ITEM_OPTION_RE.findall(texto)
        token = self.client.cookies.get('csrftoken')
        if not token:
            return
        post_data = {'csrfmiddlewaretoken': token}
        if item_ids:
            post_data['items'] = item_ids[0]

        with self.client.post(
            f'/prestamos/crear/{reserva_id}/',
            data=post_data,
            headers={'Referer': f'{self.client.base_url}/prestamos/crear/{reserva_id}/'},
            name='/prestamos/crear/[reserva_id]/ [POST]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return
            url_prestamo = resp.url

        ids_prestamo = PRESTAMO_ID_RE.findall(url_prestamo)
        if not ids_prestamo:
            return
        prestamo_id = ids_prestamo[0]
        hora_prestamo = datetime.now()

        fire_metric(self, 'RESULTADO: préstamo directo (sin solicitud previa)', 0)
        cola_entrega.put({
            'tipo_flujo': 'prestamo_directo',
            'cedula': cedula, 'hora_objetivo_slot': hora_inicio.strftime('%H:%M'),
            'hora_solicitud': hora_solicitud, 'resultado_solicitud': 'n/a_reserva_directa',
            'hora_aprobacion': hora_solicitud, 'tiempo_solicitud_aprobacion_seg': 0.0,
            'hora_prestamo': hora_prestamo,
            'tiempo_aprobacion_prestamo_seg': (hora_prestamo - hora_solicitud).total_seconds(),
            'fecha_devolucion_esperada': datetime.combine(ahora.date(), hora_fin),
            'prestamo_id': prestamo_id,
            'item_inventario_id': item_ids[0] if item_ids else None,
        })


# ── 4) Inspección forzando ítems DAÑADOS, con verificación en BD ────────────

class InspeccionConItemsDanados(HttpUser):
    """(v3) Fuerza estado_inspeccion='danado' en todos los ítems de un
    préstamo devuelto y verifica en /inventario/items/ que
    FinalizarInspeccionService de verdad actualizó el ItemInventario a
    'Dañado' — no se confía solo en el código fuente."""

    weight = 4
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def inspeccionar_danado(self):
        if not self.autenticado:
            return
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return

        resultado = realizar_entrega(self, item, datetime.now(), estado_forzado='danado')
        if resultado is None:
            return

        item_inventario_id = item.get('item_inventario_id')
        if not item_inventario_id:
            # El préstamo se creó sin ítems reales enlazados (pool de
            # ítems agotado bajo carga sostenida, o la reserva de origen no
            # traía insumos) — no hay nada que verificar, así que no se
            # reporta como si la verificación hubiera fallado.
            estado_bd = None
            fire_metric(self, 'RESULTADO: inspección dañado (sin ítem para verificar)', 0)
        else:
            estado_bd = verificar_estado_item_bd(self.client, item_inventario_id)
            confirmado = estado_bd == 'Dañado'
            fire_metric(
                self,
                'RESULTADO: inspección dañado (confirmado en BD)' if confirmado
                else 'ERROR: inspección dañado NO confirmada en BD',
                0,
                exception=None if confirmado else Exception(f'estado BD leído = {estado_bd!r}'),
            )

        conteo = resultado['conteo']
        _registrar_fila_csv({
            'tipo_flujo': 'inspeccion_danado',
            'cedula': item.get('cedula'), 'hora_objetivo_slot': item.get('hora_objetivo_slot'),
            'hora_solicitud': _iso(item.get('hora_solicitud')), 'resultado_solicitud': 'creada',
            'hora_aprobacion': _iso(item.get('hora_aprobacion')),
            'tiempo_solicitud_aprobacion_seg': item.get('tiempo_solicitud_aprobacion_seg'),
            'hora_prestamo': _iso(item.get('hora_prestamo')),
            'tiempo_aprobacion_prestamo_seg': item.get('tiempo_aprobacion_prestamo_seg'),
            'resultado_prestamo': 'creado',
            'hora_entrega': resultado['hora_entrega'].isoformat(),
            'fecha_devolucion_esperada': _iso(item.get('fecha_devolucion_esperada')),
            'tiempo_prestamo_entrega_seg': resultado['tiempo_entrega_seg'],
            'desviacion_entrega_seg': resultado['desviacion_seg'],
            'items_bien': conteo['bien'], 'items_danado': conteo['danado'],
            'items_no_entregado': conteo['no_entregado'],
            'item_estado_confirmado_bd': estado_bd or 'sin_item',
            'resultado_final': (
                'sin_item' if not item_inventario_id
                else 'completo' if estado_bd == 'Dañado' else 'completo_sin_confirmar'
            ),
        })


# ── 5) Inspección forzando ítems NO ENTREGADOS (pérdida) ────────────────────

class InspeccionConItemsNoEntregados(HttpUser):
    """(v3) Fuerza estado_inspeccion='no_entregado' (pérdida) en todos los
    ítems. OJO: en el código real, FinalizarInspeccionService NO cambia el
    estado del ItemInventario para 'no_entregado' ("sin cambio de estado",
    dice el comentario) y ni siquiera existe un EstadoItem "Perdido" en el
    catálogo sembrado. Este flujo verifica justamente eso — confirma que el
    ítem NO cambia de estado — y lo deja registrado como hallazgo, no como
    error del script."""

    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def inspeccionar_no_entregado(self):
        if not self.autenticado:
            return
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return

        estado_antes = verificar_estado_item_bd(self.client, item.get('item_inventario_id'))
        resultado = realizar_entrega(self, item, datetime.now(), estado_forzado='no_entregado')
        if resultado is None:
            return
        estado_despues = verificar_estado_item_bd(self.client, item.get('item_inventario_id'))

        fire_metric(self, 'RESULTADO: inspección no_entregado (sin marca de perdido — hallazgo de la app)', 0)

        conteo = resultado['conteo']
        _registrar_fila_csv({
            'tipo_flujo': 'inspeccion_no_entregado',
            'cedula': item.get('cedula'), 'hora_objetivo_slot': item.get('hora_objetivo_slot'),
            'hora_solicitud': _iso(item.get('hora_solicitud')), 'resultado_solicitud': 'creada',
            'hora_aprobacion': _iso(item.get('hora_aprobacion')),
            'tiempo_solicitud_aprobacion_seg': item.get('tiempo_solicitud_aprobacion_seg'),
            'hora_prestamo': _iso(item.get('hora_prestamo')),
            'tiempo_aprobacion_prestamo_seg': item.get('tiempo_aprobacion_prestamo_seg'),
            'resultado_prestamo': 'creado',
            'hora_entrega': resultado['hora_entrega'].isoformat(),
            'fecha_devolucion_esperada': _iso(item.get('fecha_devolucion_esperada')),
            'tiempo_prestamo_entrega_seg': resultado['tiempo_entrega_seg'],
            'desviacion_entrega_seg': resultado['desviacion_seg'],
            'items_bien': conteo['bien'], 'items_danado': conteo['danado'],
            'items_no_entregado': conteo['no_entregado'],
            'item_estado_confirmado_bd': f'{estado_antes} -> {estado_despues} (sin cambio esperado; no existe "Perdido")',
            'resultado_final': 'completo',
        })


# ── 6) Estudiante anónimo intenta cancelar su propia solicitud ──────────────

class CancelacionDeSolicitud(HttpUser):
    """(v3) Un estudiante anónimo crea su solicitud y luego intenta
    CANCELARLA él mismo. /reservas/<id>/cancelar/ exige rol
    Administrador/Laboratorio — no hay ningún endpoint público de
    autocancelación — así que, sin loguearse, se espera un 302 a /login/.
    Como una sesión anónima no puede conocer el id de SU propia reserva
    (ningún endpoint público lo expone), el intento apunta a una reserva
    real ya vista por cualquier otro flujo (o, a falta de una, al id 1) —
    lo que importa es que el decorador de rol bloquea el acceso ANTES de
    siquiera mirar el id, así que el resultado es representativo igual.
    'Funciona' aquí = queda correctamente bloqueado; no es un fallo del
    script."""

    weight = 3
    wait_time = between(1, 3)

    @task
    def crear_y_cancelar(self):
        offset_min = random.choice([o for o in OFFSETS_SOLICITUD_MIN if o <= 0])
        momento_slot = datetime.now() + timedelta(minutes=offset_min)
        hora_inicio = momento_slot.time().replace(second=0, microsecond=0)
        hoy = momento_slot.date()
        hora_fin = (momento_slot + timedelta(hours=2)).time()
        cedula = nueva_cedula()

        resp = self.client.get('/solicitudes/estudiante/', name='/solicitudes/estudiante/ [GET]')
        token = resp.cookies.get('csrftoken')
        if not token:
            return

        hora_solicitud = datetime.now()
        data = {
            'csrfmiddlewaretoken': token,
            'nombre': nuevo_nombre(), 'cedula': cedula, 'programa': PROGRAMA,
            'laboratorio': str(LAB_ID), 'fecha_reserva': hoy.isoformat(),
            'hora_inicio': hora_inicio.strftime('%H:%M'), 'hora_fin': hora_fin.strftime('%H:%M'),
            'observaciones': 'Generado por Locust (v3 - a cancelar)',
            'insumos_ids': '', 'insumos_cantidades': '',
        }
        with self.client.post(
            '/solicitudes/estudiante/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/solicitudes/estudiante/'},
            name='/solicitudes/estudiante/ [POST]',
            catch_response=True,
        ) as resp:
            exito = '/solicitudes/exitosa/' in resp.url
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

        if not exito:
            return

        reserva_id = _reserva_conocida_muestra() or '1'
        token = self.client.cookies.get('csrftoken')
        if not token:
            return

        with self.client.post(
            f'/reservas/{reserva_id}/cancelar/',
            data={'csrfmiddlewaretoken': token},
            headers={'Referer': f'{self.client.base_url}/reservas/{reserva_id}/cancelar/'},
            name='/reservas/[id]/cancelar/ [anónimo]',
            catch_response=True,
        ) as resp:
            bloqueada = '/login/' in resp.url
            if resp.status_code in (200, 302):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

        fue_cancelada = not bloqueada
        fire_metric(
            self,
            'RESULTADO: cancelación anónima bloqueada (esperado)' if bloqueada
            else 'ALERTA: cancelación anónima NO bloqueada',
            0,
            exception=None if bloqueada else Exception('una sesión anónima pudo cancelar una reserva'),
        )

        _registrar_fila_csv({
            'tipo_flujo': 'cancelacion_solicitud', 'cedula': cedula,
            'hora_solicitud': hora_solicitud.isoformat(), 'resultado_solicitud': 'creada',
            'fue_cancelada': fue_cancelada,
            'momento_cancelacion': datetime.now().isoformat(),
            'motivo_cancelacion': 'bloqueada_requiere_login' if bloqueada else 'permitida_sin_auth',
            'resultado_final': 'bloqueada_correctamente' if bloqueada else 'alerta_seguridad',
        })


# ── 7) Cancelación de una reserva ya aprobada ────────────────────────────────

class CancelacionDeReservaAprobada(HttpUser):
    """(v3) Toma reservas YA APROBADAS de cola_prestamo (compite con
    LaboratoristaConPrestamo por los mismos ítems: una fracción de las
    reservas aprobadas termina cancelada en vez de convertida en préstamo,
    algo realista) y las cancela como Administrador/Laboratorio —
    cancelar_reserva no tiene ninguna guarda de estado, así que siempre está
    'permitido' para un rol autorizado, sin importar que ya esté Aprobada."""

    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def cancelar_aprobada(self):
        if not self.autenticado:
            return
        try:
            item = cola_prestamo.get(block=False)
        except Empty:
            return

        reserva_id = item['reserva_id']
        token = self.client.cookies.get('csrftoken')
        if not token:
            return

        with self.client.post(
            f'/reservas/{reserva_id}/cancelar/',
            data={'csrfmiddlewaretoken': token},
            headers={'Referer': f'{self.client.base_url}/reservas/{reserva_id}/'},
            name='/reservas/[id]/cancelar/ [autorizado]',
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 302):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                return

        momento = datetime.now()
        fire_metric(self, 'RESULTADO: reserva aprobada cancelada', 0)

        _registrar_fila_csv({
            'tipo_flujo': 'cancelacion_reserva_aprobada',
            'cedula': item.get('cedula'), 'hora_objetivo_slot': item.get('hora_objetivo_slot'),
            'hora_solicitud': _iso(item.get('hora_solicitud')), 'resultado_solicitud': 'creada',
            'hora_aprobacion': _iso(item.get('hora_aprobacion')),
            'tiempo_solicitud_aprobacion_seg': item.get('tiempo_solicitud_aprobacion_seg'),
            'fue_cancelada': True, 'momento_cancelacion': momento.isoformat(),
            'motivo_cancelacion': 'cancelada_tras_aprobacion_por_laboratorista',
            'resultado_final': 'cancelada',
        })


# ── 8) Devolución anticipada (inmediata) ─────────────────────────────────────

class DevolucionAnticipada(HttpUser):
    """(v3) Devuelve el préstamo lo antes posible (sin esperar nada) — a
    diferencia de LaboratoristaConEntrega.entrega_temprana (que apunta 30-60
    min simulados antes del vencimiento), esta clase entrega de inmediato
    tras el préstamo, para medir el mejor caso posible de diferencia real
    contra fecha_devolucion_esperada."""

    weight = 4
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def devolver_de_inmediato(self):
        if not self.autenticado:
            return
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return

        resultado = realizar_entrega(self, item, datetime.now())
        if resultado is None:
            return

        diferencia = (item['fecha_devolucion_esperada'] - resultado['hora_entrega']).total_seconds()
        fire_metric(self, 'TIEMPO: devolución anticipada (adelanto real)', max(0.0, diferencia))
        _sumar_resumen('temprana')

        conteo = resultado['conteo']
        _registrar_fila_csv({
            'tipo_flujo': 'devolucion_anticipada',
            'cedula': item.get('cedula'), 'hora_objetivo_slot': item.get('hora_objetivo_slot'),
            'hora_solicitud': _iso(item.get('hora_solicitud')), 'resultado_solicitud': 'creada',
            'hora_aprobacion': _iso(item.get('hora_aprobacion')),
            'tiempo_solicitud_aprobacion_seg': item.get('tiempo_solicitud_aprobacion_seg'),
            'hora_prestamo': _iso(item.get('hora_prestamo')),
            'tiempo_aprobacion_prestamo_seg': item.get('tiempo_aprobacion_prestamo_seg'),
            'resultado_prestamo': 'creado', 'variante_entrega_intencion': 'anticipada_inmediata',
            'hora_entrega': resultado['hora_entrega'].isoformat(),
            'fecha_devolucion_esperada': _iso(item.get('fecha_devolucion_esperada')),
            'tiempo_prestamo_entrega_seg': resultado['tiempo_entrega_seg'],
            'desviacion_entrega_seg': resultado['desviacion_seg'], 'variante_entrega_real': 'temprana',
            'items_bien': conteo['bien'], 'items_danado': conteo['danado'],
            'items_no_entregado': conteo['no_entregado'],
            'resultado_final': 'completo',
        })


# ── 9) Prórroga de devolución (sondeo — la app no la implementa) ────────────

class ProrrogaDeDevolucion(HttpUser):
    """(v3) Antes de que el préstamo se devuelva, intenta pedir una
    prórroga. La app NO tiene ningún formulario ni endpoint para extender
    fecha_devolucion (CambiarEstadoPrestamoForm solo edita 'estado'; no hay
    ninguna ruta '.../prorroga/' registrada) — así que esto sondea la ruta
    más plausible y confirma el 404, documentándolo como hallazgo (función
    inexistente) en vez de simular una implementación ficticia. El préstamo
    NO se consume: se devuelve tal cual a cola_entrega para que otro flujo
    lo complete normalmente."""

    weight = 2
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task
    def solicitar_prorroga(self):
        if not self.autenticado:
            return
        try:
            item = cola_entrega.get(block=False)
        except Empty:
            return

        prestamo_id = item['prestamo_id']
        token = self.client.cookies.get('csrftoken')
        nueva_fecha = (item['fecha_devolucion_esperada'] + timedelta(hours=2)).isoformat()

        with self.client.post(
            f'/prestamos/{prestamo_id}/prorroga/',
            data={'csrfmiddlewaretoken': token, 'nueva_fecha_devolucion': nueva_fecha},
            headers={'Referer': f'{self.client.base_url}/prestamos/{prestamo_id}/'},
            name='/prestamos/[id]/prorroga/ [sondeo — no implementado]',
            catch_response=True,
        ) as resp:
            if resp.status_code == 404:
                resp.success()
                resultado = 'no_implementado_404'
            elif resp.status_code in (200, 302):
                resp.success()
                resultado = 'inesperado_endpoint_existe'
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')
                resultado = f'error_http_{resp.status_code}'

        fire_metric(self, f'RESULTADO: prórroga ({resultado})', 0)

        _registrar_fila_csv({
            'tipo_flujo': 'prorroga_devolucion',
            'cedula': item.get('cedula'), 'hora_objetivo_slot': item.get('hora_objetivo_slot'),
            'hora_prestamo': _iso(item.get('hora_prestamo')),
            'fecha_devolucion_esperada': _iso(item.get('fecha_devolucion_esperada')),
            'prorroga_solicitada': True, 'prorroga_resultado': resultado,
            'resultado_final': 'sondeo_completo',
        })

        cola_entrega.put(item)


# ── 10) Solicitud con múltiples módulos ──────────────────────────────────────

class MultiplosModulosEnMismaReserva(HttpUser):
    """(v3) Solicita varios módulos a la vez usando el camino de profesor
    registrado — ProfesorSolicitudForm._asignar_modulos() SÍ asigna TODOS
    los ids recibidos. OJO: el camino de estudiante (solicitud_estudiante())
    recorta a `ids[:1]`, solo permite 1 módulo, así que ese camino no sirve
    para este flujo. Se consultan los módulos realmente disponibles hoy vía
    la API pública y, tras enviar la solicitud, se vuelve a consultar esa
    misma API para confirmar cuántos quedaron en estado 'reservado' — el
    'inspeccionar todos' del pedido se traduce aquí como esa verificación
    (los módulos no pasan por el flujo de inspección de préstamos, que es
    solo para ítems de inventario prestables)."""

    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, PROF_USER, PROF_PASS)

    @task
    def solicitar_con_modulos(self):
        if not self.autenticado:
            return

        curso_id = obtener_curso_id(self.client)
        if not curso_id:
            return

        cantidad_deseada = random.choice([2, 3])
        modulos_ids = obtener_modulos_disponibles(self.client, cantidad_deseada)
        if len(modulos_ids) < 2:
            return

        offset_min = random.choice([o for o in OFFSETS_SOLICITUD_MIN if o <= 0])
        momento_slot = datetime.now() + timedelta(minutes=offset_min)
        hora_inicio = momento_slot.time().replace(second=0, microsecond=0)
        hoy = momento_slot.date()
        hora_fin = (momento_slot + timedelta(hours=3)).time()
        cedula = nueva_cedula()

        resp = self.client.get('/solicitudes/profesor/', name='/solicitudes/profesor/ [GET]')
        token = resp.cookies.get('csrftoken')
        if not token:
            return

        data = {
            'csrfmiddlewaretoken': token,
            'nombre': PROF_NOMBRE, 'cedula': cedula, 'curso': str(curso_id),
            'laboratorio': str(LAB_ID), 'fecha_reserva': hoy.isoformat(),
            'hora_inicio': hora_inicio.strftime('%H:%M'), 'hora_fin': hora_fin.strftime('%H:%M'),
            'necesita_modulo': 'on',
            'modulos_ids': ','.join(str(i) for i in modulos_ids),
            'observaciones': 'Generado por Locust (v3 - múltiples módulos)',
            'insumos_ids': '', 'insumos_cantidades': '',
        }
        with self.client.post(
            '/solicitudes/profesor/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/solicitudes/profesor/'},
            name='/solicitudes/profesor/ [POST con módulos]',
            catch_response=True,
        ) as resp:
            exito = '/solicitudes/exitosa/' in resp.url
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

        if not exito:
            _registrar_fila_csv({
                'tipo_flujo': 'modulos_multiples', 'cedula': cedula,
                'cantidad_modulos_solicitados': len(modulos_ids),
                'cantidad_modulos_confirmados': 0,
                'resultado_final': 'rechazada_validacion',
            })
            return

        time.sleep(1)  # margen real breve para que la asignación quede visible en la API
        modulos_tras = obtener_modulos_estado(self.client)
        confirmados = sum(1 for mid in modulos_ids if modulos_tras.get(mid) == 'reservado')

        fire_metric(self, 'RESULTADO: módulos asignados', confirmados)
        if confirmados < len(modulos_ids):
            fire_metric(self, 'ERROR: no todos los módulos quedaron reservados', 0,
                        exception=Exception(f'{confirmados}/{len(modulos_ids)} confirmados'))

        _registrar_fila_csv({
            'tipo_flujo': 'modulos_multiples', 'cedula': cedula,
            'cantidad_modulos_solicitados': len(modulos_ids),
            'cantidad_modulos_confirmados': confirmados,
            'resultado_final': 'completo' if confirmados == len(modulos_ids) else 'parcial',
        })


# ── Listeners globales ───────────────────────────────────────────────────────

@events.request.add_listener
def registrar_errores_500(request_type, name, response_time, response_length,
                           exception, context, **kwargs):
    """Log aparte de cualquier error 5xx real (no confundir con las métricas
    FLUJO custom, que usan `exception` para marcar reglas de negocio)."""
    response = kwargs.get('response')
    status_code = getattr(response, 'status_code', None)
    if status_code is not None and status_code >= 500:
        with open('locust_errores_500.log', 'a', encoding='utf-8') as f:
            f.write(f'{name} | status={status_code} | tiempo={response_time:.0f}ms\n')


@events.quitting.add_listener
def imprimir_resumen(environment, **kwargs):
    if _resumen_conteos:
        total = sum(_resumen_conteos.values())
        print('\n== Resumen de entregas por variante ==')
        for variante in ('temprana', 'a_tiempo', 'retrasada'):
            n = _resumen_conteos.get(variante, 0)
            pct = (n / total * 100) if total else 0
            barra = '#' * int(pct // 2)
            print(f'  {variante:>10}: {n:4d} ({pct:5.1f}%) {barra}')
        print(f'  {"total":>10}: {total:4d}')

    if _resumen_por_flujo:
        print('\n== Resumen por tipo de flujo (v3) ==')
        for tipo_flujo in sorted(_resumen_por_flujo):
            resultados = _resumen_por_flujo[tipo_flujo]
            total_flujo = sum(resultados.values())
            detalle = ', '.join(f'{k}={v}' for k, v in sorted(resultados.items()))
            print(f'  {tipo_flujo:<28}: {total_flujo:4d}  ({detalle})')

    if _resumen_conteos or _resumen_por_flujo:
        print(f'\n  Detalle por flujo en: {os.path.abspath(CSV_PATH)}')
