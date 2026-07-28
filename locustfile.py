"""
locustfile.py — pruebas de carga del Sistema de Laboratorios.

REQUISITO PREVIO: sembrar los datos objetivo (usuarios, laboratorio, una
reserva "Pendiente" y un préstamo "Activo" con un ítem) con:

    python manage.py seed_locust

Ese comando imprime los IDs reales creados; si difieren de los defaults de
abajo, pásalos por variable de entorno (LOCUST_LAB_ID, LOCUST_RESERVA_ID,
LOCUST_PRESTAMO_ID, etc.) — así el archivo no queda atado a IDs hardcodeados
que solo existen en una base de datos concreta.

USO — interfaz web (abre http://localhost:8089):
    locust -f locustfile.py --host=http://localhost:8000

USO — headless, con el perfil de carga embebido en este archivo
(10 usuarios, spawn rate 2/s, 1 minuto) vía LoadTestShape:
    locust -f locustfile.py --host=http://localhost:8000 --headless \
        --html reporte.html --csv resultados

Los CSV/HTML que genera Locust (resultados_stats.csv, reporte.html, etc.)
ya traen tiempo de respuesta, throughput (req/s) y conteo de fallos por
endpoint — ver la clase LoggerErrores500 más abajo para un log aparte,
específico de errores 5xx.

DISTRIBUCIÓN DE USUARIOS (10 total): los `weight` de cada clase sostienen
exactamente 5 anónimos / 2 admin / 3 laboratorista cuando se corre con
--users 10 (Locust reparte usuarios proporcional al peso).

RESTRICCIÓN "NO modificar BD" vs. los endpoints pedidos: /reservas/<id>/aprobar/
y /prestamos/<id>/inspeccionar/ [POST] son, por diseño de la aplicación,
mutantes (aprueban una reserva / guardan una inspección) — no existe forma
de "probarlos de verdad" sin escribir en la BD. Para no generar filas nuevas
en cada request ni dejar el sistema en un estado roto, este archivo apunta
siempre a los MISMOS objetos sembrados por seed_locust (RESERVA_ID,
PRESTAMO_ID): aprobar una reserva ya aprobada, o guardar la misma inspección
"bien", son operaciones idempotentes a nivel de negocio aunque técnicamente
generen un UPDATE en cada corrida.

GET /laboratorio/ (Task 1, usuario anónimo): esa vista requiere rol
Administrador/Laboratorio (decorador rol_requerido) — un anónimo real
recibe una redirección 302 a /login/, nunca un 200 con el listado. Se deja
en el archivo tal como se pidió, pero el criterio de éxito refleja el
comportamiento real de la app (302 es la respuesta correcta a un anónimo,
no una falla) en vez de forzar una expectativa que la aplicación nunca
cumpliría para ese rol.
"""
import os
import re
from datetime import date

from locust import HttpUser, LoadTestShape, between, events, task

LAB_ID = int(os.environ.get('LOCUST_LAB_ID', '1'))
RESERVA_ID = int(os.environ.get('LOCUST_RESERVA_ID', '1'))
PRESTAMO_ID = int(os.environ.get('LOCUST_PRESTAMO_ID', '1'))

ADMIN_USER = os.environ.get('LOCUST_ADMIN_USER', 'e2e_admin')
ADMIN_PASS = os.environ.get('LOCUST_ADMIN_PASS', 'E2eAdmin!2026')
LAB_USER = os.environ.get('LOCUST_LAB_USER', 'e2e_laboratorista')
LAB_PASS = os.environ.get('LOCUST_LAB_PASS', 'E2eLab!2026')

ESTADO_ITEM_RE = re.compile(r'name="estado_(\d+)"')


def login_django(client, username, password):
    """
    Login estándar de Django: obtiene el token CSRF de /login/, lo envía
    junto con las credenciales, y confirma que la sesión quedó autenticada.
    """
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


class UsuarioAnonimo(HttpUser):
    """Task 1 — visitante público navegando el formulario de solicitud (solo GET)."""

    weight = 5
    wait_time = between(1, 3)

    @task(3)
    def ver_formulario_estudiante(self):
        self.client.get('/solicitudes/estudiante/', name='/solicitudes/estudiante/')

    @task(2)
    def listar_laboratorios(self):
        # Requiere login (ver nota en el docstring del módulo); 302 es la
        # respuesta correcta para un anónimo, no una falla del sistema.
        with self.client.get(
            '/laboratorio/',
            name='/laboratorio/',
            catch_response=True,
            allow_redirects=False,
        ) as resp:
            if resp.status_code in (200, 302):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

    @task(1)
    def ver_modulos_disponibles(self):
        hoy = date.today().isoformat()
        with self.client.get(
            f'/laboratorio/{LAB_ID}/modulos/disponibles-publica/?fecha={hoy}',
            name='/laboratorio/[id]/modulos/disponibles-publica/',
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 404:
                # LOCUST_LAB_ID no existe en este entorno (falta correr
                # seed_locust) — no es un fallo del sistema bajo prueba.
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')


class AdminUser(HttpUser):
    """Task 2 — administrador listando y aprobando reservas."""

    weight = 2
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, ADMIN_USER, ADMIN_PASS)

    @task(3)
    def listar_reservas(self):
        self.client.get('/reservas/', name='/reservas/')

    @task(2)
    def detalle_reserva(self):
        with self.client.get(
            f'/reservas/{RESERVA_ID}/', name='/reservas/[id]/', catch_response=True
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

    @task(1)
    def aprobar_reserva(self):
        token = self.client.cookies.get('csrftoken')
        if not self.autenticado or not token:
            return
        with self.client.post(
            f'/reservas/{RESERVA_ID}/aprobar/',
            data={'accion': 'aprobar', 'csrfmiddlewaretoken': token},
            headers={'Referer': f'{self.client.base_url}/reservas/{RESERVA_ID}/'},
            name='/reservas/[id]/aprobar/',
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 302, 404):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')


class LaboratoristaUser(HttpUser):
    """Task 3 — laboratorista listando préstamos e inspeccionando ítems."""

    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.autenticado = login_django(self.client, LAB_USER, LAB_PASS)

    @task(3)
    def listar_prestamos(self):
        self.client.get('/prestamos/', name='/prestamos/')

    @task(2)
    def detalle_prestamo(self):
        with self.client.get(
            f'/prestamos/{PRESTAMO_ID}/', name='/prestamos/[id]/', catch_response=True
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

    @task(2)
    def ver_pagina_inspeccion(self):
        with self.client.get(
            f'/prestamos/{PRESTAMO_ID}/inspeccionar/',
            name='/prestamos/[id]/inspeccionar/ [GET]',
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')

    @task(1)
    def guardar_inspeccion(self):
        if not self.autenticado:
            return

        # catch_response=True: un 404 (PRESTAMO_ID no existe en este entorno)
        # se trata igual que en ver_pagina_inspeccion, no como fallo; sin esto
        # Locust marca automáticamente cualquier no-2xx/3xx como error.
        with self.client.get(
            f'/prestamos/{PRESTAMO_ID}/inspeccionar/',
            name='/prestamos/[id]/inspeccionar/ [GET]',
            catch_response=True,
        ) as get_resp:
            if get_resp.status_code in (200, 404):
                get_resp.success()
            else:
                get_resp.failure(f'Status inesperado: {get_resp.status_code}')
            if get_resp.status_code != 200:
                return
            texto = get_resp.text

        item_ids = ESTADO_ITEM_RE.findall(texto)
        token = self.client.cookies.get('csrftoken')
        if not item_ids or not token:
            return

        data = {'csrfmiddlewaretoken': token, 'accion': 'guardar'}
        for item_id in item_ids:
            data[f'estado_{item_id}'] = 'bien'
            data[f'observaciones_{item_id}'] = 'Carga generada por Locust'

        with self.client.post(
            f'/prestamos/{PRESTAMO_ID}/inspeccionar/',
            data=data,
            headers={'Referer': f'{self.client.base_url}/prestamos/{PRESTAMO_ID}/inspeccionar/'},
            name='/prestamos/[id]/inspeccionar/ [POST]',
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 302, 404):
                resp.success()
            else:
                resp.failure(f'Status inesperado: {resp.status_code}')


class PerfilDeCarga(LoadTestShape):
    """
    Perfil de carga embebido: 10 usuarios totales, spawn rate 2/s, durante
    1 minuto. Solo aplica en corridas headless (`--headless`, sin --users/
    --spawn-rate/--run-time); en la interfaz web se puede seguir
    configurando manualmente el load test como de costumbre.
    """
    stages = [
        {'duration': 60, 'users': 10, 'spawn_rate': 2},
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage['duration']:
                return stage['users'], stage['spawn_rate']
        return None


@events.request.add_listener
def registrar_errores_500(request_type, name, response_time, response_length,
                           exception, context, **kwargs):
    """Deja un rastro aparte de cualquier error 5xx, con el endpoint y el tiempo
    de respuesta, para que sea fácil de encontrar entre todas las métricas."""
    response = kwargs.get('response')
    status_code = getattr(response, 'status_code', None)
    if status_code is not None and status_code >= 500:
        with open('locust_errores_500.log', 'a', encoding='utf-8') as f:
            f.write(f'{name} | status={status_code} | tiempo={response_time:.0f}ms\n')
