# Sistema de Laboratorios

[![pytest](https://img.shields.io/badge/pytest-22%2F22-brightgreen)]()
[![Django tests](https://img.shields.io/badge/django--test-14%2F14-brightgreen)]()
[![Cypress E2E](https://img.shields.io/badge/cypress-5%20pasos%20E2E-brightgreen)]()
[![Locust](https://img.shields.io/badge/locust-14%20flujos%2C%200%25%20failures-brightgreen)]()
[![Django](https://img.shields.io/badge/Django-6.0.5-092E20)]()
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB)]()

## 📚 Documentación completa

La documentación detallada del proyecto está disponible en Notion:
[Ver documentación en Notion](https://cautious-boater-fbc.notion.site/Sistema-de-Laboratorios-Documentaci-n-752210c966904c4f9f4b9595f34fee84?pvs=143)

Sistema web desarrollado en Django para la gestión integral de laboratorios universitarios: control de inventario, reservas de espacios y módulos, préstamos de insumos y solicitudes públicas de estudiantes y profesores.

## 1. Descripción general

El sistema centraliza el ciclo de vida completo del uso de un laboratorio: desde que un estudiante o profesor solicita usarlo (sin necesidad de iniciar sesión), pasando por la revisión y aprobación de esa solicitud por parte del personal del laboratorio, hasta la entrega física de los insumos en préstamo y su devolución. Todo movimiento de inventario queda registrado para garantizar trazabilidad completa.

El sistema también ofrece un mapa visual en tiempo real de los módulos (puestos físicos) de cada laboratorio, permitiendo al personal administrativo conocer en todo momento qué módulos están disponibles, ocupados, reservados o inactivos.

## 2. Stack tecnológico

- **Backend:** Django 6.0.5 (Python)
- **Base de datos:** SQLite (`db.sqlite3`)
- **Frontend:** Templates de Django + Bootstrap
- **Zona horaria:** `America/Bogota` (`USE_TZ = False`, fechas en hora local sin soporte de `tzdata` para conversión)
- **Idioma:** Español (`es-co`)
- **Modelo de usuario:** personalizado (`users.Usuario`, extiende `AbstractUser`)
- **Herramientas de desarrollo:** `mypy` + `django-stubs` para chequeo de tipos
- **Testing:** `pytest` + `pytest-django` (servicios y vistas), `manage.py test` (Django `TestCase`), Cypress (E2E), Locust (carga) — ver [sección 9](#9-testing-y-aseguramiento-de-calidad).

## 3. Estructura de apps

| App | Descripción |
| --- | --- |
| `users` | Modelo de usuario personalizado (`Usuario`) y modelo de roles (`Rol`). Gestiona alta, edición y desactivación de usuarios, y expone los decoradores `rol_requerido` (control de acceso por rol) y `requiere_contrasena_admin` (control de acceso reforzado para acciones irreversibles) usados para proteger vistas. También modela los programas académicos (`ProgramaAcademico`) usados en los formularios del sistema. |
| `laboratorio` | Modela los laboratorios físicos, sus horarios de operación (`HorarioLaboratorio`), eventos/bloqueos (`EventoLaboratorio`) y los módulos o puestos (`Modulo`). Incluye el mapa visual de disponibilidad de módulos. Gestiona el personal de laboratorio: `Laboratorista` (personas registradas sin login propio) y `LaboratoristaLab` (tabla intermedia que asocia un laboratorista a un laboratorio con un tipo de rol: encargado o laboratorista). |
| `inventario` | Catálogo de insumos (`Insumo`), ítems físicos individuales (`ItemInventario`, con soporte de soft-delete vía `deleted_at`) y el registro de movimientos (`MovimientoInventario`) que da trazabilidad a cada cambio de estado de un ítem. |
| `reservas` | Gestiona las reservas (`Reserva`) del laboratorio: creación, aprobación, cancelación y expiración automática. Asocia los insumos solicitados en cada reserva (`ReservaInsumo`). |
| `prestamos` | Gestiona la entrega física de los ítems de inventario asociados a una reserva aprobada (`Prestamo`, `PrestamoItem`), su inspección de devolución (`InspeccionItem`) y el marcado de préstamos retrasados. |
| `solicitudes` | Expone los formularios públicos (sin autenticación) para estudiantes y profesores. Genera automáticamente una `SolicitudReserva` y, a partir de ella, una `Reserva` en estado "Pendiente". También modela los cursos (`Curso`) usados para la asignación automática de módulos a profesores. Incluye el flujo de autoregistro: `SolicitudRegistroProfesor` (solicitud pública de un profesor para registrarse en el sistema) y `SolicitudRegistroCurso` (cursos que el profesor registra junto con su solicitud, aprobados individualmente por el Administrador). |

## 4. Roles y permisos

El sistema define cuatro roles (modelo `Rol`), con los siguientes niveles de acceso:

- **Administrador:** acceso total al sistema (usuarios, laboratorios, inventario, reservas, préstamos).
- **Laboratorio:** cuenta de login compartida por laboratorio. Gestiona reservas, préstamos, movimientos de inventario y el mapa del laboratorio asignado. No tiene acceso a la gestión de usuarios ni a laboratorios distintos del suyo.
- **Docente:** no tiene acceso de inicio de sesión al sistema administrativo. Su interacción se limita al formulario público de solicitud en `/solicitudes/profesor/`.
- **Estudiante:** no tiene acceso de inicio de sesión al sistema administrativo. Su interacción se limita al formulario público de solicitud en `/solicitudes/estudiante/`.

El control de acceso a las vistas administrativas se implementa mediante el decorador `rol_requerido` (`users/decorators.py`), que redirige a `/usuarios/sin-permiso/` a cualquier usuario autenticado sin el rol adecuado, y a `/login/` a cualquier usuario no autenticado. Las acciones irreversibles (eliminar, desactivar) suman además el decorador `requiere_contrasena_admin` — ver [6.11](#611-control-de-acceso-con-contraseña-admin).

## 5. Flujo principal del sistema

1. El estudiante o el profesor llena el formulario público correspondiente (`/solicitudes/estudiante/` o `/solicitudes/profesor/`), sin necesidad de autenticarse.
2. Al enviarse el formulario se crea una `SolicitudReserva`, la cual genera automáticamente una `Reserva` asociada en estado **"Pendiente"**.
3. La cuenta de Laboratorio o el Administrador revisa la reserva desde `/reservas/` y la **aprueba** o **cancela**.
4. Cuando llega el momento de uso, el Encargado crea el préstamo asociado a la reserva aprobada (`/prestamos/crear/<reserva_id>/`) y asigna los ítems físicos disponibles del inventario correspondientes a los insumos solicitados.
5. Al devolver los insumos, el préstamo se marca como **"Devuelto"** y, mediante signals, los ítems regresan automáticamente a estado **"Disponible"** (o al estado que corresponda según la inspección — ver [6.13](#613-estados-de-un-ítem-trazabilidad)).
6. Cada cambio relevante en el inventario (préstamo, devolución, daño, mantenimiento, baja) queda registrado en `MovimientoInventario`, garantizando trazabilidad completa de cada ítem.

## 6. Reglas de negocio

### 6.1 Horario y duración de reservas

- **Estudiante:** cada reserva debe durar mínimo 2 horas y máximo 4 horas.
- **Profesor:** cada reserva debe durar mínimo 2 horas y máximo 8 horas.
- **Estudiante:** máximo 4 horas acumuladas por día, sumando todas sus reservas de ese día (se identifica al estudiante por su cédula).
- **Profesor:** máximo 8 horas acumuladas por día, sumando todas sus reservas de ese día (se identifica al profesor por su usuario).
- El laboratorio opera de lunes a viernes, según los horarios configurados por laboratorio (`HorarioLaboratorio`).
- El estudiante puede reservar para el mismo día/momento en que hace la solicitud.
- El profesor debe reservar con un mínimo de 1 día de anticipación.
- Ver también [6.10](#610-horario-especial-después-de-las-1600) para el caso de solicitudes cercanas al cierre.

### 6.2 Módulos (puestos físicos del laboratorio)

Cada módulo (`Modulo`) puede encontrarse en uno de cuatro estados:

- **Disponible:** sin reservas activas ni bloqueos.
- **Ocupado:** en uso en este momento, según la hora actual y una reserva aprobada vigente.
- **Reservado:** tiene una reserva futura para esa fecha, aún no aprobada/en curso.
- **Inactivo:** deshabilitado manualmente, con un motivo registrado (`motivo_no_disponible`).

Reglas de asignación y administración:

- El estudiante puede seleccionar como máximo 1 módulo por reserva.
- El profesor puede seleccionar hasta tantos módulos como estudiantes tenga su curso (campo `cantidad_estudiantes` del modelo `Curso`).
- El Administrador y el Encargado pueden marcar cualquier módulo como no disponible, indicando un motivo (por ejemplo, mantenimiento o daño), y volver a habilitarlo posteriormente.
- El mapa visual de módulos (`/laboratorio/<id>/mapa/`) se actualiza en tiempo real mediante *polling* cada 30 segundos.
- Para consultar la disponibilidad de módulos en el mapa, el Administrador/Encargado debe seleccionar obligatoriamente fecha, hora de inicio y hora de fin, y la hora de fin debe ser posterior a la hora de inicio.

### 6.3 Expiración y automatización

- Las reservas en estado **"Pendiente"** que superan su `hora_limite_retiro` sin haber sido utilizadas se marcan automáticamente como **"Expiradas"**.
- Esta expiración ocurre tanto mediante el management command `expirar_reservas` (ejecutado cada 5 minutos vía el Programador de Tareas de Windows) como al cargar la lista de reservas en `/reservas/` (auto-expiración en línea).
- **Legacy:** esta regla es de cuando una reserva nacía "Pendiente" y esperaba aprobación manual. Con la aprobación automática (ver `SolicitudReserva.crear_reserva()`), toda reserva nueva nace directamente "Aprobada" — el flujo normal ya no genera reservas "Pendiente", así que en la práctica esta expiración hoy no tiene nada que hacer. El estado "Expirada" y el chequeo se mantienen (sin tocar "Aprobada") para no perder la protección si algo vuelve a dejar una reserva en "Pendiente" por otra vía.
- Los préstamos que superan su fecha de devolución se marcan como **"Retrasados"** mediante el management command `marcar_retrasados`.
- Si se elimina el último insumo asociado a una reserva, esa reserva se cancela automáticamente.

### 6.4 Fechas de una reserva

| Campo | Significado |
| --- | --- |
| `fecha_creacion` | Cuándo se creó la solicitud/reserva (timestamp de registro). |
| `fecha_reserva` | Cuándo se va a usar el laboratorio (fecha de uso programada). |
| `hora_limite_retiro` | Hasta cuándo se puede retirar el préstamo antes de que la reserva expire. |
| `fecha_devolucion` | Cuándo debe devolverse el préstamo. |

### 6.5 Restricciones de edición

- No se pueden agregar insumos a una reserva en estado **"Expirada"** o **"Cancelada"**.

### 6.6 Reservas libres

- Los profesores pueden reservar sin un curso registrado en el sistema (semillero, práctica externa, grupo sin curso oficial).
- Requieren: nombre del grupo, cantidad de asistentes y descripción de la actividad.
- Solo el Administrador puede aprobarlas; la cuenta de Laboratorio no tiene acceso a este tipo de reservas.
- Se identifican con el badge "Reserva libre" en la lista de reservas.

### 6.7 Registro de profesores y cursos

- Los profesores pueden autoregistrarse desde `/solicitudes/registro-profesor/` sin necesidad de login.
- En el mismo formulario pueden registrar sus datos personales y uno o varios cursos.
- El Administrador revisa las solicitudes desde `/solicitudes/solicitudes-profesores/`.
- El flujo de aprobación es en dos pasos: primero se aprueba al profesor (lo que crea automáticamente su `Usuario` con rol Docente), y luego se aprueba cada curso por separado (lo que crea el `Curso` vinculado al profesor).
- Las solicitudes de cursos cuyo profesor aún no ha sido aprobado no aparecen como aprobables.

### 6.8 Personal de laboratorio

- Cada laboratorio tiene una cuenta de login compartida con rol **Laboratorio**, creada automáticamente al crear el laboratorio.
- Los laboratoristas son personas registradas en el sistema sin login propio (`Laboratorista`).
- La relación entre un laboratorista y un laboratorio se gestiona mediante `LaboratoristaLab`, que almacena también el tipo de rol por laboratorio: `encargado` o `laboratorista`.
- Máximo 1 encargado por laboratorio; intentar asignar un segundo muestra un aviso y degrada el tipo a laboratorista.
- Un mismo laboratorista puede ser encargado en varios laboratorios simultáneamente.
- Los laboratoristas tienen un conjunto de responsabilidades predefinidas (préstamos, inventario, apertura, etc.) que se registran en cada perfil.

### 6.9 Programas académicos

- Los programas académicos se gestionan desde `/usuarios/programas/` (solo Administrador).
- Todos los formularios del sistema (solicitudes públicas, registro de laboratoristas, registro de profesores) usan el selector de programas desde base de datos.
- Los programas pueden activarse o desactivarse; solo los activos aparecen en los selectores.

### 6.10 Horario especial (después de las 16:00)

Una reserva que empieza a las 16:00 o después ya no tiene margen para cumplir la duración mínima de 2 horas sin pasarse del cierre del laboratorio (18:00). En vez de rechazar toda solicitud tardía, `SolicitudReserva.clean()` la ajusta automáticamente:

- Si `hora_inicio >= 16:00`, `hora_fin` se fija siempre a **18:00**, sin importar qué duración haya pedido el solicitante.
- La duración mínima de 2 horas **no** se exige en este caso — puede quedar en minutos.
- `hora_fin` nunca puede superar las 18:00 (cierre del laboratorio).

Ejemplos:

| Solicitud | Resultado |
| --- | --- |
| 16:30 → 16:45 | Se ajusta a 16:30 → 18:00 ✅ |
| 17:00 → 17:15 | Se ajusta a 17:00 → 18:00 ✅ |
| 17:59 → 18:00 | Se ajusta a 17:59 → 18:00 ✅ |
| 18:00 en adelante | Rechazada — el laboratorio ya está cerrado ❌ |

### 6.11 Control de acceso con contraseña admin

Para acciones irreversibles, el sistema exige una **contraseña admin** independiente de la contraseña de login:

- Solo **Administrador** y **Laboratorio** pueden configurarla y usarla; cualquier otro rol autenticado recibe **403 Forbidden** de inmediato, sin llegar a ver el formulario.
- Se pide **en cada acción**, sin sesión temporal: confirmarla una vez no evita que se vuelva a pedir en la siguiente acción sensible.
- El formulario de confirmación muestra el contexto específico de la acción (qué se va a afectar) antes de pedir la contraseña, por ejemplo: *"Estás a punto de: Eliminar — Objeto: Curso - Física 101"*.

Vistas protegidas actualmente:

- Eliminar curso (`/solicitudes/cursos/<id>/eliminar/`)
- Eliminar insumo (`/inventario/eliminar/<id>/`)
- Eliminar programa académico (`/usuarios/programas/<id>/eliminar/`)
- Desactivar usuario (`/usuarios/<id>/desactivar/`)
- Eliminar ítem de inventario (`/inventario/items/<id>/eliminar/`) — ver [6.12](#612-soft-delete-e-historial-auditable)

La contraseña admin se configura/cambia desde `/usuarios/cambiar-contrasena-admin/` (requiere volver a ingresar la contraseña de login vigente para confirmarla). Toda la actividad — accesos denegados, contraseñas incorrectas, acciones autorizadas — queda registrada en `logs/acceso_admin.log`, con usuario, acción, objeto afectado y timestamp.

### 6.12 Soft-delete e historial auditable

`ItemInventario` no se borra físicamente al eliminarlo: se marca con `deleted_at`. Esto existe porque `PrestamoItem`, `InspeccionItem` y `MovimientoInventario` apuntan al ítem con `on_delete=CASCADE` — un `delete()` real se llevaría por delante el historial de préstamos e inspecciones de ese ítem, no solo el ítem.

- Un ítem eliminado desaparece de las listas y deja de poder seleccionarse para préstamos nuevos (incluso si su `estado` interno sigue en "Disponible").
- Su historial de préstamos, inspecciones y movimientos sigue siendo consultable en `/inventario/items/<id>/historial/`, con un aviso indicando cuándo se eliminó.
- `ItemInventario.objects` trae todos los ítems (incluidos los eliminados, para auditoría); `ItemInventario.activos` trae solo los no eliminados (usado en listas y formularios de selección).

Métodos relevantes del modelo:

- `soft_delete()`: marca `deleted_at = timezone.now()`.
- `is_deleted()`: `True` si el ítem fue eliminado.

### 6.13 Estados de un ítem (trazabilidad)

Catálogo real de `EstadoItem`:

- **Disponible:** listo para prestarse.
- **Prestado:** en un préstamo activo (se asigna automáticamente al crear el `PrestamoItem`).
- **Dañado:** la inspección de devolución lo marcó como dañado.
- **Perdido:** la inspección de devolución lo marcó como `no_entregado` — antes esto no cambiaba el estado del ítem (se detectó con las pruebas de carga de Locust); ahora `FinalizarInspeccionService` lo marca "Perdido" automáticamente.
- **Mantenimiento** / **Baja:** estados administrativos manuales, sin transición automática asociada.

## 7. Instalación y puesta en marcha

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd sistema_laboratorios

# 2. Crear y activar entorno virtual (Windows)
python -m venv venv
venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Aplicar migraciones
python manage.py migrate

# 5. Crear superusuario (Administrador)
python manage.py createsuperuser

# 6. Levantar el servidor de desarrollo
python manage.py runserver
```

La aplicación quedará disponible en `http://127.0.0.1:8000/`.

> **Nota:** el proyecto usa `DEBUG = True` y una `SECRET_KEY` de desarrollo en `config/settings.py`. Antes de cualquier despliegue en producción, estos valores deben reemplazarse y `ALLOWED_HOSTS` debe restringirse.

### Usuarios de prueba (`seed_e2e`)

Para tener datos realistas sin crearlos a mano (usuarios, laboratorio, insumo, módulos, curso), corré:

```bash
python manage.py seed_e2e
```

Usuarios creados (contraseña admin ya configurada, lista para probar el flujo de [6.11](#611-control-de-acceso-con-contraseña-admin)):

| Usuario | Contraseña | Rol | Contraseña admin |
| --- | --- | --- | --- |
| `e2e_admin` | `E2eAdmin!2026` | Administrador | *(configurar desde `/usuarios/cambiar-contrasena-admin/`)* |
| `e2e_laboratorista` | `E2eLab!2026` | Laboratorio | *(configurar desde `/usuarios/cambiar-contrasena-admin/`)* |
| `e2e_profesor` | `E2eProfesor!2026` | Docente | — (Docente no tiene acceso a contraseña admin) |

> `seed_e2e` no asigna una contraseña admin de fábrica — hay que configurarla una vez desde la UI (`set_admin_password`), como lo haría un Administrador real la primera vez.

Datos de prueba creados:

- 1 laboratorio: "Laboratorio E2E" (horario lunes a viernes, 06:00–18:00)
- 6 módulos, uno por zona (izquierda, centro-top, centro-mid, centro-bot, derecha, inferior)
- 1 insumo: "Insumo E2E" con ítems en estado Disponible (`seed_locust` amplía este pool a 25+ ítems para pruebas de carga)
- 1 curso: "Curso E2E", vinculado a `e2e_profesor`

## 8. Automatizaciones

El sistema depende de dos *management commands* de Django que deben ejecutarse periódicamente. En el entorno de desarrollo/producción actual, esto se hace mediante el **Programador de Tareas de Windows**:

| Comando | App | Frecuencia configurada | Qué hace |
| --- | --- | --- | --- |
| `expirar_reservas` | `reservas` | Cada 5 minutos | Marca como "Expiradas" las reservas **Pendiente** cuya `hora_limite_retiro` ya pasó. Legacy: con auto-aprobación (ver 6.3) ya no se crean reservas Pendiente, así que en el flujo normal de hoy este comando es un no-op. |
| `marcar_retrasados` | `prestamos` | No configurada actualmente | Marca como "Retrasados" los préstamos activos cuya fecha de devolución de la reserva ya pasó (con 5 minutos de gracia). |

> ⚠️ La tarea programada de `marcar_retrasados` fue eliminada del Programador de Tareas de Windows y está pendiente de volver a configurarse. Mientras tanto, debe ejecutarse manualmente cuando sea necesario.

Ejecución manual:

```bash
python manage.py expirar_reservas
python manage.py marcar_retrasados
```

## 9. Testing y aseguramiento de calidad

### Tests unitarios y de integración

```bash
# pytest — servicios y vistas (tests/), con fixtures compartidas en tests/conftest.py
pytest tests/
# 22/22 ✅

# Django TestCase — por app (prestamos/tests.py, inventario/tests.py)
python manage.py test
# 14/14 ✅
```

Cubren, entre otras cosas: el flujo completo de inspección y devolución (incluyendo que un ítem `no_entregado` quede "Perdido" — 6.13), el control de acceso con contraseña admin en sus 4 combinaciones (rol no autorizado, sin contraseña configurada, contraseña incorrecta, contraseña correcta) para ambos roles habilitados, y que el soft-delete de un ítem no borre su historial de préstamos ni lo deje seleccionable para uno nuevo.

### Tests E2E (Cypress)

```bash
npm run test:e2e:headless
```

`cypress/e2e/flujo_completo.cy.js` cubre, en 5 pasos secuenciales sobre el mismo préstamo, el recorrido completo de una reserva real:

1. Estudiante crea una solicitud de reserva.
2. Administrador aprueba la solicitud.
3. Laboratorista crea el préstamo.
4. Laboratorista inspecciona los ítems del préstamo.
5. El sistema marca el préstamo como devuelto.

### Pruebas de carga (Locust v3)

`locustfile.py` simula 14 flujos de negocio distintos corriendo en simultáneo, coordinados mediante colas en memoria (una etapa dispara la siguiente: solicitud → aprobación → préstamo → entrega):

```bash
python manage.py seed_locust
locust -f locustfile.py --host=http://localhost:8000
# Abre http://localhost:8089
```

| Flujo | Peso relativo |
| --- | --- |
| `EstudianteConReservaEnHora` | 40 |
| `AdminAprobador` | 30 |
| `LaboratoristaConPrestamo` | 20 |
| `LaboratoristaConEntrega` | 10 |
| `ProfesorRegistradoConReserva` | 6 |
| `ProfesorInvitadoConReserva` | 5 |
| `LaboratoristaConPrestamoDirecto`, `InspeccionConItemsDanados`, `DevolucionAnticipada` | 4 c/u |
| `InspeccionConItemsNoEntregados`, `CancelacionDeSolicitud`, `CancelacionDeReservaAprobada`, `MultiplosModulosEnMismaReserva` | 3 c/u |
| `ProrrogaDeDevolucion` | 2 |

Los primeros 4 son el flujo principal (mismo peso relativo que en la sección 5); los 10 restantes cubren orígenes alternativos de solicitud (profesor registrado/invitado) y casos de excepción (cancelaciones, devolución anticipada, ítems dañados/perdidos, sondeo de una prórroga que **no existe** en el sistema — hallazgo real documentado en el propio `locustfile.py`, no una funcionalidad pendiente de una fase anterior).

Resultado de la corrida más reciente verificada: **0% de fallas** con 40 usuarios concurrentes y ~1000 requests. El detalle fila por fila (hora de solicitud, tiempos de cada etapa, resultado) queda en `locust_flujos_v3.csv`; la auditoría de accesos con contraseña admin generada durante la corrida, en `logs/acceso_admin.log`.

## 10. Referencia de URLs principales

| Ruta | Descripción |
| --- | --- |
| `/` | Dashboard según el rol del usuario autenticado. |
| `/login/` → `/logout/` | Autenticación de Administrador/Laboratorio. |
| `/admin/` | Panel de administración de Django. |
| `/solicitudes/estudiante/` | Formulario público de solicitud para estudiantes (sin login). |
| `/solicitudes/profesor/` | Formulario público de solicitud para profesores (sin login). |
| `/solicitudes/exitosa/` | Página de confirmación tras enviar una solicitud. |
| `/solicitudes/registro-profesor/` | Formulario público de autoregistro de profesor con sus cursos (sin login). |
| `/solicitudes/solicitudes-profesores/` | Lista de solicitudes de registro de profesores pendientes (solo Administrador). |
| `/solicitudes/solicitudes-profesores/<id>/` | Detalle y aprobación de una solicitud de registro de profesor. |
| `/solicitudes/cursos/` | Gestión de cursos (Administrador/Laboratorio). |
| `/solicitudes/cursos/crear/` | Crear nuevo curso. |
| `/solicitudes/cursos/<id>/eliminar/` | Eliminar curso (requiere contraseña admin). |
| `/reservas/` | Listado y gestión de reservas (Administrador/Laboratorio). |
| `/reservas/<id>/aprobar/` | Aprobar o cancelar una reserva pendiente. |
| `/reservas/<id>/cancelar/` | Cancelar una reserva. |
| `/reservas/crear/` | Creación manual de reserva por Administrador/Laboratorio: selector de tipo de solicitante (estudiante/profesor), selector visual de rango de horario y selección visual de módulos (límite de 1 módulo para estudiante; hasta `cantidad_estudiantes` del curso para profesor). |
| `/reservas/para-prestamo/` | Reservas aprobadas listas para generar un préstamo. |
| `/prestamos/` | Listado de préstamos. |
| `/prestamos/crear/<reserva_id>/` | Crear un préstamo a partir de una reserva aprobada. |
| `/prestamos/<id>/devolver/` | Marcar un préstamo como devuelto. |
| `/inventario/` | Gestión de insumos. |
| `/inventario/eliminar/<id>/` | Eliminar insumo (requiere contraseña admin). |
| `/inventario/items/` | Gestión de ítems físicos de inventario (solo ítems activos, no soft-deleted). |
| `/inventario/items/<id>/eliminar/` | Eliminar (soft-delete) un ítem de inventario — requiere contraseña admin. |
| `/inventario/items/<id>/historial/` | Historial de préstamos, inspecciones y movimientos de un ítem — accesible aunque el ítem esté eliminado. |
| `/inventario/movimientos/` | Historial de movimientos de inventario. |
| `/laboratorio/` | Listado de laboratorios (Administrador/Laboratorio). |
| `/laboratorio/<id>/mapa/` | Mapa visual en tiempo real de módulos del laboratorio. |
| `/laboratorio/<id>/modulo/<mod_id>/toggle/` | Habilitar/deshabilitar un módulo. |
| `/laboratorio/laboratoristas/` | Lista de laboratoristas (Administrador). |
| `/laboratorio/laboratoristas/crear/` | Crear nuevo laboratorista. |
| `/laboratorio/laboratoristas/<id>/` | Detalle del laboratorista con sus asignaciones por laboratorio. |
| `/laboratorio/<id>/laboratoristas/` | Asignar y gestionar laboratoristas en un laboratorio. |
| `/usuarios/` | Gestión de usuarios (Administrador). |
| `/usuarios/<id>/desactivar/` | Desactivar usuario (requiere contraseña admin). |
| `/usuarios/cambiar-contrasena-admin/` | Configurar o cambiar la contraseña admin (Administrador/Laboratorio). |
| `/usuarios/profesores/` | Lista de profesores registrados (Docentes). |
| `/usuarios/profesores/crear/` | Crear nuevo profesor manualmente. |
| `/usuarios/profesores/<id>/` | Detalle del profesor con sus cursos. |
| `/usuarios/programas/` | Gestión de programas académicos (solo Administrador). |
| `/usuarios/programas/<id>/eliminar/` | Eliminar programa académico (requiere contraseña admin). |

## 11. Estado del proyecto / pendientes

**Completado recientemente:**

- Sistema de control de acceso con contraseña admin, independiente del login, para acciones irreversibles (6.11).
- Auditoría completa de esas acciones en `logs/acceso_admin.log`.
- Soft-delete de ítems de inventario para preservar historial de préstamos e inspecciones (6.12).
- Corrección del estado "Perdido": un ítem `no_entregado` ahora sí cambia de estado (6.13) — encontrado con las pruebas de carga de Locust.
- Ajuste automático de horario para solicitudes después de las 16:00, en vez de rechazarlas (6.10).
- Suite de pruebas de carga con Locust ampliada a 14 flujos de negocio (principal + 10 casos alternativos/excepción).
- Cobertura de tests ampliada: 22 (pytest) + 14 (Django) tests unitarios/integración.

**Pendiente:**

- Sistema de vetos para usuarios que devuelven tarde o dañan insumos.
- Prórroga de devolución de un préstamo — no existe todavía ningún endpoint ni formulario para esto (confirmado al construir las pruebas de carga: la ruta más plausible responde 404).
- Notificaciones por correo al aprobar/rechazar solicitudes.
- Integración futura con TIP/tarjeta universitaria.
- API REST.
- Migración opcional a PostgreSQL.
- Containerización (Docker).
- CI/CD (por ejemplo, GitHub Actions) para correr la suite de tests automáticamente.
