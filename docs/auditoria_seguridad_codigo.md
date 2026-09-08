# Auditoría de código — Sistema de Laboratorios

Fecha: 2026-09-01 (actualizada 2026-09-02 con la auditoría de cuentas por laboratorio y contraseña admin)
Alcance: todo el código de producción (modelos, services, vistas, templates de email, configuración, migraciones). No incluye una revisión de dependencias de terceros (`requirements.txt`) más allá de lo que aparece abajo.

Metodología: lectura dirigida por área de riesgo (control de acceso, integridad de datos, configuración de despliegue), más verificación ejecutable donde fue posible: `manage.py check --deploy`, `manage.py makemigrations --check`, reproducción en vivo (sin escritura) de la colisión de `Usuario.codigo` y del estado real de `Laboratorio.encargados`/contraseña admin contra la base de datos de desarrollo, búsqueda de SQL crudo/`csrf_exempt`, y un mapeo completo de decoradores de acceso en las 6 apps (`reservas`, `solicitudes`, `prestamos`, `laboratorio`, `inventario`, `users`).

---

## CRÍTICO (Debe arreglarse ya)

### 1. `SECRET_KEY` hardcodeado y commiteado a git — ✅ RESUELTO (2026-09-01)
- **Dónde estaba:** `config/settings.py:18` — `SECRET_KEY = 'django-insecure-clave-temporal-para-desarrollo-123456789'`.
- **Por qué era grave:** `SECRET_KEY` firma las cookies de sesión, los tokens CSRF y cualquier dato firmado por Django (p. ej. tokens de reseteo de contraseña). Al estar hardcodeado en un archivo que el propio código documentaba como "sí se commitea a git", cualquiera con acceso al repositorio — incluido su historial, aunque se cambie después — podía forjar sesiones y tokens CSRF válidos. Era además una contradicción directa con la política que el mismo archivo enunciaba dos líneas antes ("Secretos como SENDGRID_API_KEY NUNCA van hardcodeados acá").
- **Qué se hizo:** `SECRET_KEY` ahora se lee de `.env` (`SECRET_KEY = os.getenv('SECRET_KEY')`), con `raise ImproperlyConfigured(...)` si falta — no hay fallback inseguro silencioso. Se generó una clave nueva y aleatoria (`get_random_secret_key()`) y se agregó a `.env` (gitignorado, no versionado) y `.env.example` quedó documentado con instrucciones para generar la propia. Confirmado con `git ls-files`/`git check-ignore` que `.env` no está ni puede quedar trackeado, y con `manage.py check` + la suite completa que la app arranca igual con la clave nueva.
- **Pendiente para quien despliegue:** la clave vieja (la que estaba hardcodeada) sigue expuesta para siempre en el historial de git — si el repositorio tiene o llega a tener remoto/colaboradores externos, considerar además reescribir el historial (`git filter-repo` o similar) o, más simple, no depender de que esa clave vieja sea secreta nunca más (ya se rotó, que es lo que realmente importa).

### 2. Un `Laboratorio`/`Laboratorio`-role solo está aislado a su lab en una vista; el resto del flujo de reservas/préstamos es global — ✅ RESUELTO (2026-09-03)
- **Dónde estaba:** `reservas/views.py` — `lista_reservas`, `detalle_reserva`, `aprobar_reserva`, `cancelar_reserva_admin`, `eliminar_insumo_reserva`; `prestamos/views.py` — `lista_prestamos`, `detalle_prestamo`, `crear_prestamo`, `cambiar_estado_prestamo`, `iniciar_inspeccion`, `inspeccionar_prestamo`, `marcar_devuelto`. Todas estaban decoradas solo con `@rol_requerido('Administrador', 'Laboratorio')`, sin ningún chequeo adicional de laboratorio.
- **Por qué era grave:** la pregunta explícita de esta auditoría — "¿Laboratorista solo ve su lab?" — tenía respuesta **no** para la gran mayoría del flujo real (aprobar/cancelar reservas, crear préstamos, marcar devoluciones). Un usuario con rol `Laboratorio` asignado a un solo laboratorio (vía `Laboratorio.encargados`) podía, por URL directa o simplemente navegando `/reservas/` y `/prestamos/` sin aplicar el filtro `?lab=`, ver y **actuar** sobre reservas y préstamos de *cualquier* laboratorio del sistema.
- **Qué se hizo:** se agregó `users/helpers.py` (`es_administrador`, `laboratorios_visibles`, `verificar_acceso_laboratorio`, `laboratorio_de_reserva`, `laboratorio_de_prestamo`) — reutiliza `es_laboratorista_del_laboratorio` (`laboratorio/models.py`), la misma función que ya usaban `editar_insumos_reserva` y `_check_lab_access`, en vez de reimplementar el criterio de acceso por tercera vez con el riesgo de que las tres versiones divergieran. Se aplicó en las 12 vistas listadas arriba (las 10 originalmente identificadas más `eliminar_insumo_reserva` e `inspeccionar_prestamo`, que quedaron fuera de la lista pero son de la misma categoría): las vistas de listado (`lista_reservas`, `lista_prestamos`) filtran el queryset a los laboratorios del usuario; las de detalle/acción verifican el laboratorio del objeto puntual antes de proceder, devolviendo 403 (`templates/error_sin_acceso.html` para "no es tu laboratorio", `templates/error_sin_laboratorio.html` para "no tienes ninguno asignado"). `Administrador` sigue viendo/actuando sobre todo, sin cambios. `crear_reserva`, `reservas_para_prestamo`, `horarios_disponibles` y los 3 `exportar_*_excel` quedaron deliberadamente fuera de este alcance (no estaban en la lista original de la auditoría ni en la del pedido que lo implementó) — quedan como una brecha menor conocida, no crítica, para una vuelta futura.
- **Tests:** 30 nuevos — 14 unitarios sobre `users/helpers.py` (`tests/test_services/test_users_helpers.py`) y 16 HTTP sobre las vistas reales (`tests/test_views/test_reservas_views.py`, `tests/test_views/test_prestamos_views.py`), cubriendo: laboratorista ve/no ve reservas y préstamos ajenos en las listas, 403 al intentar detalle/aprobar/cancelar/crear-préstamo/cambiar-estado/marcar-devuelto de otro laboratorio, Administrador sin restricción, y el caso de un usuario `Laboratorio` sin ningún laboratorio asignado (403 con mensaje propio en vez de una lista vacía silenciosa).

### 3. `Laboratorio.encargados` está vacío en la base de datos real — el único control de acceso por lab que sí existe en el código hoy no tiene datos que lo alimenten — ✅ RESUELTO PARA 4/5 LABORATORIOS (2026-09-02)
- **Dónde:** tabla intermedia de `Laboratorio.encargados` (M2M). Verificado en vivo (solo lectura) contra la base de datos de desarrollo con `manage.py shell`, como parte de esta auditoría.
- **Qué encontré:**
  - Existen 5 laboratorios (`LAB-Mecanica`, `Lab Test`, `Laboratorio de ondas`, `Lab de Ingeniería de sistemas`, `Laboratorio E2E`) y 4 cuentas de usuario con el patrón `lab_*` (`lab_mecanica`, `lab_test`, `lab_ondas`, `lab_sistemas`), todas con `rol='Laboratorio'` — por el nombre, claramente pensadas una por laboratorio.
  - **Pero `laboratorio.encargados.all()` devuelve vacío para los 5 laboratorios, sin excepción.** Ningún usuario `lab_*` está vinculado a ningún laboratorio.
  - Como `es_laboratorista_del_laboratorio()` (`laboratorio/models.py`) y `_check_lab_access()` (`laboratorio/views.py`) dependen *exclusivamente* de esa relación (`laboratorio.encargados.filter(id=usuario.id).exists()`), el resultado práctico es que **hoy ningún usuario `lab_*` puede acceder a nada que esté scoped por laboratorio** — ni a `editar_insumos_reserva` (el único punto del sistema que implementa el aislamiento correctamente, ver punto CRÍTICO #2), ni a `detalle_laboratorio`/`reservas_laboratorio`/`prestamos_laboratorio`/`mapa_laboratorio` en `laboratorio/views.py`. Cualquiera de esas cuentas, intentando gestionar *su propio* laboratorio, recibe hoy un `PermissionDenied` (403).
  - Adicionalmente, `Laboratorio E2E` (el quinto laboratorio) no tiene ninguna cuenta `lab_*` asociada en absoluto — la cuenta relacionada con ese flujo (`e2e_laboratorista`, sembrada por `seed_e2e.py`) tiene el rol correcto pero tampoco está en `encargados` de ningún laboratorio.
- **Por qué probablemente pasó (hipótesis, no confirmada con certeza):** `crear_laboratorio` (`laboratorio/views.py:49-80`) sí ejecuta `laboratorio.encargados.add(usuario_lab)` correctamente cuando se crea un laboratorio nuevo por esa vía, y los usernames `lab_*` coinciden exactamente con el patrón que ese formulario genera. Que el vínculo no exista para las 5 filas reales sugiere que estos laboratorios y/o estas cuentas se crearon por otro camino (carga manual, fixture, corrección de datos, o antes de que existiera ese flujo de auto-provisión) y el paso de vincularlos quedó pendiente — existe una UI para hacerlo después (`gestionar_encargados` / `asignar_laboratorista`), pero aparentemente no se usó para estos 5.
- **Cómo arreglarlo:**
  1. Vincular cada laboratorio real con su cuenta correspondiente, ya sea desde la UI (`/laboratorio/<id>/`, sección de encargados) o una vez vía `manage.py shell`:
     ```python
     from users.models import Usuario
     from laboratorio.models import Laboratorio
     Laboratorio.objects.get(nombre='LAB-Mecanica').encargados.add(Usuario.objects.get(username='lab_mecanica'))
     Laboratorio.objects.get(nombre='Lab Test').encargados.add(Usuario.objects.get(username='lab_test'))
     Laboratorio.objects.get(nombre='Laboratorio de ondas').encargados.add(Usuario.objects.get(username='lab_ondas'))
     Laboratorio.objects.get(nombre='Lab de Ingenieria de sistemas').encargados.add(Usuario.objects.get(username='lab_sistemas'))
     # decidir qué hacer con "Laboratorio E2E": ¿necesita una cuenta real, o basta con e2e_laboratorista para pruebas?
     ```
  2. Agregar una comprobación de "salud de datos" (management command, o un chequeo en `manage.py check`) que alerte si algún `Laboratorio` activo no tiene `encargados`, para que este tipo de vínculo faltante no vuelva a pasar desapercibido — es exactamente el tipo de problema silencioso (no rompe nada visiblemente, solo deja una función inutilizable) que no se nota hasta que alguien intenta usarla.
- **Qué se hizo:** se vincularon las 4 cuentas reales con su laboratorio (`lab_mecanica`→`LAB-Mecanica`, `lab_test`→`Lab Test`, `lab_ondas`→`Laboratorio de ondas`, `lab_sistemas`→`Lab de Ingeniería de sistemas`) vía `Laboratorio.encargados.add(...)`. Verificado en vivo que `es_laboratorista_del_laboratorio()` ahora devuelve `True` para el laboratorio propio de cada cuenta y `False` para cualquier otro, y que la suite completa sigue en verde tras el cambio (era un cambio de datos, no de código). **`Laboratorio E2E` (ID 5) queda deliberadamente sin vincular** — no tiene una cuenta `lab_*` dedicada; queda pendiente decidir si necesita una, o si basta con `e2e_laboratorista` para ese flujo de pruebas. El punto 2 de "cómo arreglarlo" (chequeo de salud de datos) sigue pendiente, es una mejora de proceso, no de datos.

### 4. Las tablas de estado (`EstadoReserva`, `EstadoPrestamo`, `EstadoItem`, `EstadoInsumo`, `TipoMovimiento`) no tienen `unique=True` en `nombre` — ✅ RESUELTO (2026-09-03)
- **Dónde estaba:** `reservas/models.py:12`, `prestamos/models.py:13`, `inventario/models.py:10,16,22`.
- **Por qué era grave:** todo el sistema depende de `EstadoReserva.objects.get(nombre='Aprobada')` (y equivalentes) en decenas de puntos — vistas, services, comandos, tests. Si alguna vez existían dos filas con el mismo `nombre` (vía Django admin, una migración de datos mal ejecutada, o una edición manual de la BD), **todas** esas llamadas `.get()` lanzaban `MultipleObjectsReturned` y rompían crear reservas, aprobar, cancelar, crear préstamos, devolver ítems — el sistema completo.
- **Qué se hizo:** se agregó `unique=True` a `nombre` en las 5 clases (`EstadoReserva`, `EstadoPrestamo`, `EstadoItem`, `EstadoInsumo`, `TipoMovimiento`), con su migración (`reservas.0007`, `prestamos.0009`, `inventario.0007` — sin paso de deduplicación de datos porque, verificado antes de migrar, no había ningún duplicado). Se agregaron tests de regresión en `reservas/tests.py`, `prestamos/tests.py` e `inventario/tests.py` (`EstadoReservaUnicidadTests`, `EstadoPrestamoUnicidadTests`, `EstadosUnicidadTests`) que confirman: crear un segundo estado con el mismo nombre lanza `IntegrityError` (y no deja la fila creada), `full_clean()` lo rechaza con `ValidationError` (el camino que usaría un ModelForm), y `.get(nombre=...)` sigue funcionando normalmente para nombres únicos — el patrón que usa el resto del sistema no se rompió.

---

## ADVERTENCIA (Revisar antes de producción)

### 5. `Usuario.codigo`: `unique=True` + `blank=True` sin `null=True` — reproducido en vivo
- **Dónde:** `users/models.py:31`.
- Django solo excluye de la validación de unicidad los valores `None`, no las cadenas vacías `''`. Con `blank=True` (permite dejarlo vacío en un formulario) pero sin `null=True`, **solo un usuario en todo el sistema puede quedar sin código** — reproduje esto contra la base de datos de desarrollo actual: crear un segundo `Usuario` sin código vía `UsuarioForm` falla con "Ya existe un/a Usuario con este/a Codigo" (ya hay al menos un usuario real con código vacío — el superusuario `camila`). Django sí bloquea esto correctamente a nivel de formulario (no es un 500), pero es un bug de modelado que va a confundir a cualquier administrador que intente crear una segunda cuenta sin código.
- **Cómo arreglarlo:** agregar `null=True` además de `blank=True` (con la migración correspondiente convirtiendo los `''` existentes a `NULL`), que es como Django maneja unicidad-opcional de forma estándar.

### 6. `eliminar_laboratorio` no tiene las protecciones que sí tienen otros `.delete()` destructivos del mismo proyecto
- **Dónde:** `laboratorio/views.py:135-143`.
- A diferencia de `eliminar_usuario`, `eliminar_curso`, `eliminar_item_inventario` (protegidos con `@requiere_contrasena_admin`) y de `eliminar_programa` (que verifica referencias activas antes de permitir el borrado — `users/views.py:286-291`), `eliminar_laboratorio` solo exige `@rol_requerido('Administrador')` y borra directo. `SolicitudReserva.laboratorio` es `on_delete=CASCADE`, así que borrar un laboratorio borra **todo su historial de solicitudes** (auditoría perdida) y deja `Reserva`/`Prestamo`/`ReservaInsumo`/`PrestamoItem` huérfanos — sin forma de rastrear a qué laboratorio pertenecían, porque `Reserva` no tiene FK directa a `Laboratorio` (solo vía `solicitud.laboratorio`, que ya no existe). Esto coincide con lo que ya señala la memoria del proyecto ("nunca hacer `.delete()`/bulk ops contra `db.sqlite3` sin respaldo — Laboratorio cascadea hasta SolicitudReserva"), pero el código no tiene ninguna barrera técnica que lo refleje.
- **Cómo arreglarlo:** agregar `@requiere_contrasena_admin` (mínimo) y/o el mismo chequeo de referencias que usa `eliminar_programa` antes de permitir el borrado; considerar además si `Laboratorio` debería desactivarse (ya existe el campo `activo`) en vez de borrarse físicamente.

### 7. `reservas_laboratorio` (la vista que sí pretende estar scoped) usa una lógica de scoping potencialmente incorrecta
- **Dónde:** `laboratorio/views.py:146-161`.
- Determina "reservas de este laboratorio" vía `ReservaInsumo.objects.filter(insumo__items__laboratorio=laboratorio)` — es decir, reservas que pidieron un insumo que *tiene al menos un ítem físico* en ese laboratorio — en vez de `solicitud__laboratorio=laboratorio` (el laboratorio para el que efectivamente se hizo la reserva). Como un mismo `Insumo` puede tener `ItemInventario` en varios laboratorios, esta vista puede: (a) mostrar reservas hechas para OTRO laboratorio si pidieron un insumo que también tiene stock acá, y (b) esconder reservas legítimas de este laboratorio si el insumo pedido todavía no tiene ítems físicos cargados. No es una falla de seguridad (sigue exigiendo `_check_lab_access`), pero sí un bug de corrección que socava la confiabilidad justo de la vista que se supone es la "correcta" para un laboratorista.
- **Cómo arreglarlo:** filtrar por `Reserva.objects.filter(solicitud__laboratorio=laboratorio)` directamente.

### 8. `cursos_profesor` (pública, sin login) permite enumerar cursos de un docente conociendo solo su nombre
- **Dónde:** `solicitudes/views.py:117-170`.
- El parámetro `cedula` es opcional: si no se envía, la vista toma automáticamente el primer docente que matchee por nombre (`usuarios[0]`) y devuelve sus cursos (código, nombre, cantidad de estudiantes) — sin ninguna verificación real de identidad. Si se envía una cédula que no coincide, el mensaje de error lista los nombres de otros docentes que sí matchearon el nombre buscado ("Docentes encontrados: X, Y, Z"), lo cual ayuda a enumerar cuentas por tanteo. No es información ultra-sensible, pero contradice el modelo de "cédula como verificación" que sí se aplicó consistentemente en el autoservicio nuevo (`MisReservasService`), y el hecho de que `cedula` sea opcional aquí lo vuelve, en la práctica, no-verificación.
- **Cómo arreglarlo:** exigir `cedula` siempre (no como fallback opcional) y no listar nombres de otros docentes en el mensaje de error.

### 9. Sin protección contra fuerza bruta en ningún endpoint
- **Dónde:** todo el proyecto — no hay `django-ratelimit`, `django-axes` ni throttling manual en ningún lado (`grep` sin resultados). Aplica tanto a `/login/` (vista de Django por defecto, sin límite de intentos) como al autoservicio nuevo por cédula+email (`/solicitudes/`, `/reservas/<id>/detalles/`, `/reservas/<id>/cancelar/`).
- Dado que las reservas se identifican por ID secuencial y la "autenticación" del autoservicio es cédula (9 dígitos predecibles) + email institucional (patrón `nombre.apellido@udea.edu.co` fácil de adivinar o obtener), un atacante automatizado podría iterar para encontrar y cancelar reservas ajenas, o simplemente para leer sus datos. Es un modelo de identidad deliberadamente débil (decisión tomada explícitamente al construir la función, documentada en el código) — pero sin throttling, esa debilidad es explotable a escala.
- **Cómo arreglarlo:** agregar throttling básico (por IP, por ejemplo con `django-ratelimit`) al menos sobre `/solicitudes/` (la búsqueda), `/reservas/<id>/detalles/` y `/reservas/<id>/cancelar/`, y considerar lo mismo para `/login/`.

### 10. `SolicitudReserva.crear_reserva()` no es atómica
- **Dónde:** `solicitudes/models.py` — el método crea la `Reserva`, guarda (`full_clean()` + `save()`), luego copia los `ReservaInsumo` en un loop, y **solo al final** hace `self.reserva = reserva; self.save(...)`. Nada de esto está envuelto en `transaction.atomic()`. Lo mismo aplica a `CrearSolicitudReservaService.crear_desde_estudiante`/`crear_desde_profesor` (`crear_libre` sí es atómico, con `@transaction.atomic`).
- Si algo falla a mitad del loop de insumos (o el proceso muere), queda una `Reserva` ya guardada, con insumos parcialmente copiados, y sin ninguna `SolicitudReserva` que la referencie todavía (huérfana) — exactamente el tipo de "datos huérfanos" que pide revisar esta auditoría.
- **Cómo arreglarlo:** envolver el cuerpo de `crear_reserva()` (desde que se crea la `Reserva` hasta que se vincula) en `@transaction.atomic`.

### 11. Condiciones de carrera en las validaciones de solapamiento/límites
- **Dónde:** `Reserva.clean()`/`tiene_solapamiento()` (`reservas/models.py`), `SolicitudReserva.clean()`/`limite_pendientes_alcanzado()`/validación de horas por día (`solicitudes/models.py`). Todos son chequeos "leer, luego decidir, luego guardar" sin `select_for_update()` ni constraint de BD que los respalde.
- Dos solicitudes concurrentes para el mismo horario/laboratorio podrían ambas pasar la validación antes de que cualquiera termine de guardar, resultando en un doble-booking. Con SQLite y el volumen de tráfico esperado hoy el riesgo práctico es bajo, pero es una debilidad arquitectónica real para un sistema de reservas.
- **Cómo arreglarlo (si el volumen de uso crece):** `select_for_update()` sobre las reservas en conflicto potencial dentro de una transacción, o un `UniqueConstraint` a nivel de BD que lo haga imposible por diseño.

### 12. Configuración de despliegue pendiente
- `manage.py check --deploy` reporta: `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` sin configurar. Asumiendo que en producción el sitio se sirve por HTTPS (recomendado), estas cuatro deben activarse antes de salir a producción real.
- `ALLOWED_HOSTS = ['localhost', '127.0.0.1']` está hardcodeado — hay que actualizarlo al dominio/IP real de producción (y probablemente moverlo también a `.env`, siguiendo el mismo patrón que `SENDGRID_API_KEY`).

### 13. Emails a varios encargados exponen la lista de destinatarios entre sí
- **Dónde:** `utils/notificaciones_email.py::notificar_cancelacion` (rama `cancelada_por='estudiante'`) — arma la lista de emails de `Laboratorio.encargados` y los pasa todos como `destinatarios` (header `To:`) de un mismo mensaje.
- Cada encargado ve las direcciones de los demás encargados del mismo laboratorio. Severidad baja (todos son staff interno de la misma institución/laboratorio), pero es una práctica evitable. (Nota: hoy este email nunca se dispara en la práctica porque `encargados` está vacío — ver punto CRÍTICO #3 — pero el bug de diseño sigue ahí para cuando se corrija.)
- **Cómo arreglarlo:** usar `bcc` en vez de `to`, o enviar un mensaje individual por destinatario.

---

## RECOMENDACIÓN (Mejorar después)

1. **Tests de aislamiento por laboratorio.** Agregar el mismo patrón de test que ya existe para `editar_insumos_reserva` (`test_editar_insumos_laboratorista_de_otro_lab_es_rechazado`) a `lista_reservas`, `detalle_reserva`, `aprobar_reserva`, `crear_prestamo`, `detalle_prestamo`, etc., una vez corregido el punto CRÍTICO #2 — para que el hueco no pueda reintroducirse sin que un test lo detecte.
2. **Auditoría persistente, no solo logs.** Hoy "quién hizo qué y cuándo" (cancelaciones, aprobaciones, cambios de insumos) vive únicamente en `logger.info()` de texto plano (útil para depurar, no para consultar/reportar). Considerar una tabla de auditoría simple (modelo `RegistroAuditoria` genérico, o un campo `cancelado_por`/`motivo` directamente en `Reserva`) para poder responder "¿quién canceló esta reserva y por qué?" sin grepear archivos de log.
3. **CI.** No hay integración continua configurada (ya listado como pendiente en el README) — correr `pytest` y `manage.py check --deploy` automáticamente en cada cambio evitaría que regresiones como el hueco de scoping (#2) o un `SECRET_KEY` hardcodeado lleguen a `main` sin que nadie lo note.
4. **Uniformar `requiere_contrasena_admin`** en el resto de acciones destructivas irreversibles que hoy no lo tienen (`eliminar_laboratorio`, `eliminar_laboratorista`).
5. **Cobertura de tests general (medida con `pytest --cov`, no solo estimada):** 69% global, 282 tests, todos en verde. Por archivo, las vistas son el punto más débil y las apps más nuevas/tocadas recientemente están mejor cubiertas:
   - `laboratorio/views.py`: **14%** (469 líneas, 404 sin cubrir) — la app que contiene `_check_lab_access`, el patrón que el punto CRÍTICO #2 pide replicar en `reservas`/`prestamos`. Que sea el archivo peor cubierto de todo el proyecto no es casualidad: es exactamente el tipo de código (control de acceso por rol/laboratorio) donde huecos como el de #2 y #3 pasan desapercibidos más tiempo. No existe un `tests/test_views/test_laboratorio_views.py`; `laboratorio/tests.py` solo cubre `ModuloEstadoService`.
   - `users/views.py`: **25%** — gestión de usuarios/roles, también código sensible desde el punto de vista de seguridad.
   - `config/views.py`: 30%, `prestamos/views.py`: 43%, `inventario/views.py`: 46%, `solicitudes/views.py`: 55%, `reservas/views.py`: 58%.
   - Los `services/` en general están bien cubiertos (90%+), igual que `models.py` de `reservas`/`prestamos` (91-97%). El patrón "primero el service con tests, después la vista" que se usó en el trabajo más reciente (`cancelar_reserva_service.py` 93%, `editar_insumos_service.py` 94%) es el que falta aplicar hacia atrás en `laboratorio` y `users`.
   - Reporte HTML completo ya generado en `htmlcov/` (`pytest --cov=. --cov-report=html`).
6. **Datos de "salud" de laboratorios.** Más allá de arreglar el punto CRÍTICO #3 puntualmente, considerar una vista o comando de administración que liste laboratorios sin encargado asignado, para detectar a futuro este tipo de vínculo faltante sin tener que auditarlo a mano.

---

## Auditoría de cuentas por laboratorio y contraseña admin (2026-09-02)

Verificación puntual pedida explícitamente, ejecutada contra la base de datos de desarrollo real (`manage.py shell`, solo lectura) y contra el código.

### Cuentas por laboratorio
- **Laboratorios existentes (5):** `LAB-Mecanica` (1), `Lab Test` (2), `Laboratorio de ondas` (3), `Lab de Ingeniería de sistemas` (4), `Laboratorio E2E` (5).
- **Cuentas `lab_*` (4):** `lab_mecanica`, `lab_test`, `lab_ondas`, `lab_sistemas` — todas con `rol='Laboratorio'`, `is_staff=False`, y **sin `email` configurado** (campo vacío en las 4, ver la ADVERTENCIA correspondiente más abajo). `Laboratorio E2E` fue eliminado (ver "Seguimiento" al final de esta sección), así que ya no aplica que le falte cuenta.
- **No existe** ningún campo `Laboratorio.usuario_laboratorio` (relación 1-a-1) — el mecanismo real es `Laboratorio.encargados` (M2M a `Usuario`, ver `laboratorio/models.py`).
- **Hallazgo central (ver CRÍTICO #3 arriba) — ✅ resuelto para 4/5 durante esta misma auditoría:** esa relación `encargados` estaba **vacía para los 5 laboratorios** al momento de auditar. Se vincularon las 4 cuentas reales (`lab_mecanica`, `lab_test`, `lab_ondas`, `lab_sistemas`) a su laboratorio correspondiente; `Laboratorio E2E` queda pendiente por no tener una cuenta `lab_*` propia.
- **Usuario admin:** sí existe (`camila_admin`, `is_staff=True`, `is_superuser=True`, `rol='Administrador'`). También hay un superusuario personal (`camila`, sin `rol` asignado — `rol=None`) y cuentas de prueba E2E (`e2e_admin`, `e2e_laboratorista`, `e2e_profesor`).

### Contraseña admin
- El script de auditoría pedido busca una variable **global** `CONTRASENA_ADMIN` en `.env` — **no existe**, y así debe ser: no es como este proyecto implementa la funcionalidad.
- Lo que sí existe, y es un patrón más seguro que una contraseña compartida en `.env`: una contraseña admin **por usuario**, separada de la contraseña de login, hasheada en BD (`Usuario.admin_password_hash`, con `set_admin_password()`/`check_admin_password()` usando `make_password`/`check_password` de Django — PBKDF2). Cada Administrador o Laboratorio la configura desde `/usuarios/cambiar-contrasena-admin/` (`cambiar_contrasena_admin`, `users/views.py:119-144`), reautenticándose con su contraseña de login actual y con un mínimo de 8 caracteres.
- **Decorador `requiere_contrasena_admin`:** existe (`users/decorators.py`) y protege 5 vistas en 3 archivos:
  - `solicitudes/views.py`: `eliminar_curso`.
  - `inventario/views.py`: `eliminar_insumo`, `eliminar_item_inventario`.
  - `users/views.py`: `desactivar_usuario`, `eliminar_programa`.
  - **No** se usa en `reservas/views.py`, `prestamos/views.py` ni `laboratorio/views.py` — coincide con lo ya señalado en la ADVERTENCIA #6 (`eliminar_laboratorio` sin esta protección).
- **Estado real de las cuentas:** de los 11 usuarios en la base de datos, solo 3 tienen la contraseña admin configurada — `camila_admin`, `e2e_admin`, `e2e_laboratorista`. **Ninguna de las 4 cuentas `lab_*` reales la tiene configurada.** No es un bug (es autoservicio, cada quien la configura cuando la necesita) pero es información operativa relevante: hoy, si alguna de esas cuentas necesitara ejecutar una acción protegida (ninguna de las 5 protegidas actualmente permite rol `Laboratorio` salvo `eliminar_curso`), se encontraría con el mensaje "todavía no configuraste una contraseña admin" en vez de poder proceder.

### Conclusión de esta verificación puntual

Usando la taxonomía A–D pedida, la situación es una **variante de D (parcial), con un matiz importante**:

- ✅ Cuentas por laboratorio: **existen** (4 de 5, con rol correcto).
- ❌ Pero **no están vinculadas** a su laboratorio (`encargados` vacío) — por lo que, en la práctica, el aislamiento por lab no funciona para ninguna de ellas hoy, ni siquiera donde el código sí lo implementa (`editar_insumos_reserva`).
- ✅ Contraseña admin: **sí está implementada** — con un mecanismo más seguro que el que pedía verificar el script (por usuario y en BD, no una única clave compartida en `.env`).
- ❌ Aislamiento por laboratorio en las vistas centrales de reservas/préstamos: **falta** (ver CRÍTICO #2), y aunque se arreglara, seguiría sin funcionar hasta resolver el vínculo faltante (CRÍTICO #3).

**Acción ya ejecutada** (no requería cambio de código, solo de datos): se vincularon las 4 cuentas `lab_*` a su laboratorio correspondiente vía `Laboratorio.encargados`. Queda pendiente decidir qué hacer con `Laboratorio E2E` — ver el punto CRÍTICO #3.

### Seguimiento (2026-09-03): `Laboratorio E2E` eliminado y contraseñas de las 4 cuentas reales reseteadas
- **`Laboratorio E2E` (ID 5) fue eliminado** — decisión tomada, no pendiente. Antes de borrar verifiqué el radio de impacto: tenía **1892 `SolicitudReserva` vinculadas**, todas creadas en una ventana de ~4 días (2026-07-31 a 2026-08-03) y cada una con una cédula distinta generada al azar — consistente con datos sintéticos de pruebas de carga (Locust/`seed_locust.py`), no con actividad real. `SolicitudReserva.laboratorio` es `on_delete=CASCADE`, así que el borrado se llevó esas 1892 filas consigo (y dejó sin `laboratorio` rastreable, si alguna quedó, a las `Reserva`/`Prestamo` que referenciaban — el mismo mecanismo descrito en la ADVERTENCIA #6, aplicado acá deliberadamente sobre datos de prueba desechables, no sobre datos reales).
- **Contraseñas de las 4 cuentas reales (`lab_mecanica`, `lab_test`, `lab_ondas`, `lab_sistemas`) reseteadas** a una contraseña compartida simple, vía el nuevo comando `manage.py resetear_contrasenas_lab` (`users/management/commands/resetear_contrasenas_lab.py`) — genera `CREDENCIALES_LAB.txt` en la raíz del proyecto (agregado a `.gitignore` *antes* de generarlo, para que no haya ventana donde pudiera quedar comiteable por accidente).
- **Nota de seguridad, explícita y no bloqueante** (el usuario pidió esto expresamente, ya rotulado como "DESARROLLO" en su propio script): las 4 cuentas ahora comparten la misma contraseña, y es una de las más débiles posibles (aparece en cualquier lista de contraseñas comunes; `set_password()` en un management command no pasa por `AUTH_PASSWORD_VALIDATORS`, así que ni siquiera los validadores por defecto de Django la habrían bloqueado). Esto es aceptable para desarrollo local (`ALLOWED_HOSTS` sigue limitado a `localhost`/`127.0.0.1`, sin HTTPS todavía) pero **no debe replicarse así en producción** — cuando este sistema se despliegue de verdad, cada cuenta de laboratorio necesita su propia contraseña, generada aleatoriamente y entregada por un canal que no sea un `.txt` en el repo (aunque esté gitignoreado).
- `db.sqlite3` (que sí está trackeado en git pese a estar listado en `.gitignore` — ya lo estaba antes de esta sesión) quedó modificado por ambos cambios (borrado del laboratorio + contraseñas). No lo commiteé — queda a criterio del usuario cuándo hacerlo.

---

## Lo que SÍ está bien (para contexto, no todo son problemas)

- **Sin inyección SQL:** no hay `.raw()`, `cursor.execute()` ni `extra()` en ningún lugar del proyecto — 100% Django ORM.
- **CSRF:** el middleware está activo globalmente y no hay ningún `@csrf_exempt` en el proyecto.
- **Migraciones consistentes:** `manage.py makemigrations --check` no detecta cambios de modelo sin migrar.
- **`DEBUG = False`** ya está correctamente puesto (con un comentario que sugiere que esto ya se corrigió antes — buena señal de que el equipo presta atención a esto).
- **Secretos fuera del repo:** `SENDGRID_API_KEY` y, desde la corrección del punto #1, también `SECRET_KEY` viven en `.env` (gitignoreado, con `.env.example` de referencia) — ya no hay ninguna excepción a esa política dentro de `config/settings.py`.
- **Manejo de fallos de email:** cada notificación (`notificar_*`) está envuelta en `try/except Exception` con `logger.exception(...)` en el punto de llamada — un fallo de SendGrid nunca interrumpe el flujo de negocio (crear reserva, cancelar, etc.), solo queda registrado.
- **Contraseña admin separada** (`Usuario.admin_password_hash`, hasheada con `make_password`/`check_password` de Django — PBKDF2) para acciones críticas, con logging de intentos (`logger_acceso_admin`) — buen patrón de defensa en profundidad, más seguro que una clave compartida en `.env`, para las acciones más destructivas que sí lo usan.
- **`editar_insumos_reserva`** es el ejemplo a seguir para el resto del sistema: control de acceso por laboratorio, validación de stock, auditoría en log, notificación por email — todo presente y testeado (aunque hoy no funcione en la práctica hasta resolver el punto CRÍTICO #3).

---

## CONCLUSIÓN

❌ **NECESITA ARREGLOS antes de producción.**

Los cuatro puntos CRÍTICOS son concretos y accionables, no teóricos:

1. ~~El `SECRET_KEY` ya está expuesto (está en git) y debe rotarse independientemente de cuándo se despliegue.~~ **Resuelto** — ver detalle en el punto #1 de arriba.
2. ~~El aislamiento por laboratorio — explícitamente pedido en el objetivo de esta auditoría ("¿Laboratorista solo ve su lab?") — no se cumple en la mayoría del flujo real de reservas y préstamos, solo en la funcionalidad más reciente (`editar_insumos_reserva`).~~ **Resuelto** — ver detalle en el punto #2 de arriba.
3. ~~Verificado en esta misma sesión: aunque se arreglara el punto anterior, hoy ninguna cuenta de laboratorio está realmente vinculada a su laboratorio (`Laboratorio.encargados` vacío) — así que ni siquiera el único control que sí existe en código (`editar_insumos_reserva`) es utilizable en la práctica todavía.~~ **Resuelto** — ver detalle en el punto #3 de arriba (`Laboratorio E2E`, que no tenía cuenta propia, ya no existe: se eliminó por ser datos de prueba de carga, ver el "Seguimiento" en la sección de cuentas por laboratorio).
4. ~~La falta de `unique=True` en las tablas de estado es una bomba de tiempo de bajo costo de arreglar y alto costo si detona (rompe el sistema completo).~~ **Resuelto** — ver detalle en el punto #4 de arriba.

**Los cuatro puntos CRÍTICOS ya están resueltos** y ninguno requirió un rediseño (una línea de config, cuatro llamadas a `encargados.add()`, una migración de `unique=True` con tests de regresión, y un helper reutilizable aplicado a 12 vistas con 30 tests nuevos). Quedan pendientes, antes de un primer despliegue real, al menos las advertencias #5 (colisión de `codigo`) y #6 (`eliminar_laboratorio` sin protección) — el resto de advertencias y recomendaciones son mejoras de robustez que pueden abordarse de forma incremental sin bloquear el despliegue.
