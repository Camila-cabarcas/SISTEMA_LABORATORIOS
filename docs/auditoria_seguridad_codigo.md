# Auditoría de código — Sistema de Laboratorios

Fecha: 2026-09-01
Alcance: todo el código de producción (modelos, services, vistas, templates de email, configuración, migraciones). No incluye una revisión de dependencias de terceros (`requirements.txt`) más allá de lo que aparece abajo.

Metodología: lectura dirigida por área de riesgo (control de acceso, integridad de datos, configuración de despliegue), más verificación ejecutable donde fue posible: `manage.py check --deploy`, `manage.py makemigrations --check`, reproducción en vivo (sin escritura) de la colisión de `Usuario.codigo`, búsqueda de SQL crudo/`csrf_exempt`, y un mapeo completo de decoradores de acceso en las 6 apps (`reservas`, `solicitudes`, `prestamos`, `laboratorio`, `inventario`, `users`).

---

## CRÍTICO (Debe arreglarse ya)

### 1. `SECRET_KEY` hardcodeado y commiteado a git — ✅ RESUELTO (2026-09-01)
- **Dónde estaba:** `config/settings.py:18` — `SECRET_KEY = 'django-insecure-clave-temporal-para-desarrollo-123456789'`.
- **Por qué era grave:** `SECRET_KEY` firma las cookies de sesión, los tokens CSRF y cualquier dato firmado por Django (p. ej. tokens de reseteo de contraseña). Al estar hardcodeado en un archivo que el propio código documentaba como "sí se commitea a git", cualquiera con acceso al repositorio — incluido su historial, aunque se cambie después — podía forjar sesiones y tokens CSRF válidos. Era además una contradicción directa con la política que el mismo archivo enunciaba dos líneas antes ("Secretos como SENDGRID_API_KEY NUNCA van hardcodeados acá").
- **Qué se hizo:** `SECRET_KEY` ahora se lee de `.env` (`SECRET_KEY = os.getenv('SECRET_KEY')`), con `raise ImproperlyConfigured(...)` si falta — no hay fallback inseguro silencioso. Se generó una clave nueva y aleatoria (`get_random_secret_key()`) y se agregó a `.env` (gitignorado, no versionado) y `.env.example` quedó documentado con instrucciones para generar la propia. Confirmado con `git ls-files`/`git check-ignore` que `.env` no está ni puede quedar trackeado, y con `manage.py check` + la suite completa que la app arranca igual con la clave nueva.
- **Pendiente para quien despliegue:** la clave vieja (la que estaba hardcodeada) sigue expuesta para siempre en el historial de git — si el repositorio tiene o llega a tener remoto/colaboradores externos, considerar además reescribir el historial (`git filter-repo` o similar) o, más simple, no depender de que esa clave vieja sea secreta nunca más (ya se rotó, que es lo que realmente importa).

### 2. Un `Laboratorio`/`Laboratorio`-role solo está aislado a su lab en una vista; el resto del flujo de reservas/préstamos es global
- **Dónde:** `reservas/views.py` — `lista_reservas`, `detalle_reserva`, `aprobar_reserva`, `cancelar_reserva_admin`, `eliminar_insumo_reserva`; `prestamos/views.py` — `lista_prestamos`, `detalle_prestamo`, `crear_prestamo`, `cambiar_estado_prestamo`, `iniciar_inspeccion`, `inspeccionar_prestamo`, `marcar_devuelto`. Todas están decoradas solo con `@rol_requerido('Administrador', 'Laboratorio')`, sin ningún chequeo adicional de laboratorio.
- **Por qué es grave:** la pregunta explícita de esta auditoría — "¿Laboratorista solo ve su lab?" — tiene respuesta **no** para la gran mayoría del flujo real (aprobar/cancelar reservas, crear préstamos, marcar devoluciones). Un usuario con rol `Laboratorio` asignado a un solo laboratorio (vía `Laboratorio.encargados`) puede, por URL directa o simplemente navegando `/reservas/` y `/prestamos/` sin aplicar el filtro `?lab=`, ver y **actuar** sobre reservas y préstamos de *cualquier* laboratorio del sistema — aprobar/cancelar reservas ajenas, crear préstamos ajenos, marcar devoluciones ajenas. El único punto que sí aplica el aislamiento correctamente es `editar_insumos_reserva` (vía `EditarInsumosReservaService.verificar_acceso` → `es_laboratorista_del_laboratorio`), y las vistas de "gestión de laboratorio" en `laboratorio/views.py` (`detalle_laboratorio`, `reservas_laboratorio`, `prestamos_laboratorio`, etc., vía `_check_lab_access`) — pero esas último son una vista *alternativa*, no la que un laboratorista usaría normalmente desde el menú "Actividad" (que apunta a `/reservas/` y `/prestamos/`, sin scoping).
- **Cómo arreglarlo:** aplicar el mismo patrón que ya existe (`es_laboratorista_del_laboratorio` en `laboratorio/models.py`, o `_check_lab_access`) en cada una de las vistas listadas arriba: para un usuario `Laboratorio`, filtrar el queryset de listado a `solicitud__laboratorio__in=<labs asignados>` y, en las vistas de detalle/acción, verificar contra `reserva.solicitud.first().laboratorio` (o `prestamo.reserva.solicitud.first().laboratorio`) antes de permitir la operación — devolviendo 403 igual que ya hace `editar_insumos_reserva`. `Administrador` sigue viendo/actuando sobre todo, sin cambios.
- **Nota:** no hay ningún test que cubra esto (confirmado con `grep` sobre `tests/`) — el único test de aislamiento por laboratorio que existe es el de `editar_insumos_reserva`, precisamente porque ahí sí se implementó el control.

### 3. Las tablas de estado (`EstadoReserva`, `EstadoPrestamo`, `EstadoItem`, `EstadoInsumo`, `TipoMovimiento`) no tienen `unique=True` en `nombre`
- **Dónde:** `reservas/models.py:12`, `prestamos/models.py:13`, `inventario/models.py:10,16,22`.
- **Por qué es grave:** todo el sistema depende de `EstadoReserva.objects.get(nombre='Aprobada')` (y equivalentes) en decenas de puntos — vistas, services, comandos, tests. Si alguna vez existen dos filas con el mismo `nombre` (vía Django admin, una migración de datos mal ejecutada, o una edición manual de la BD), **todas** esas llamadas `.get()` lanzan `MultipleObjectsReturned` y rompen crear reservas, aprobar, cancelar, crear préstamos, devolver ítems — el sistema completo. Verifiqué en vivo (solo lectura) que hoy no hay duplicados en la base de datos de desarrollo, pero nada a nivel de esquema lo impide.
- **Cómo arreglarlo:** agregar `unique=True` a `nombre` en las 5 clases, con una migración (trivial dado que hoy no hay duplicados que resolver primero).

---

## ADVERTENCIA (Revisar antes de producción)

### 4. `Usuario.codigo`: `unique=True` + `blank=True` sin `null=True` — reproducido en vivo
- **Dónde:** `users/models.py:31`.
- Django solo excluye de la validación de unicidad los valores `None`, no las cadenas vacías `''`. Con `blank=True` (permite dejarlo vacío en un formulario) pero sin `null=True`, **solo un usuario en todo el sistema puede quedar sin código** — reproduje esto contra la base de datos de desarrollo actual: crear un segundo `Usuario` sin código vía `UsuarioForm` falla con "Ya existe un/a Usuario con este/a Codigo" (ya hay al menos un usuario real con código vacío). Django sí bloquea esto correctamente a nivel de formulario (no es un 500), pero es un bug de modelado que va a confundir a cualquier administrador que intente crear una segunda cuenta sin código (p. ej. dos cuentas de laboratorio, o un docente al que todavía no se le asigna código).
- **Cómo arreglarlo:** agregar `null=True` además de `blank=True` (con la migración correspondiente convirtiendo los `''` existentes a `NULL`), que es como Django maneja unicidad-opcional de forma estándar.

### 5. `eliminar_laboratorio` no tiene las protecciones que sí tienen otros `.delete()` destructivos del mismo proyecto
- **Dónde:** `laboratorio/views.py:135-143`.
- A diferencia de `eliminar_usuario`, `eliminar_curso`, `eliminar_item_inventario` (protegidos con `@requiere_contrasena_admin`) y de `eliminar_programa` (que verifica referencias activas antes de permitir el borrado — `users/views.py:286-291`), `eliminar_laboratorio` solo exige `@rol_requerido('Administrador')` y borra directo. `SolicitudReserva.laboratorio` es `on_delete=CASCADE`, así que borrar un laboratorio borra **todo su historial de solicitudes** (auditoría perdida) y deja `Reserva`/`Prestamo`/`ReservaInsumo`/`PrestamoItem` huérfanos — sin forma de rastrear a qué laboratorio pertenecían, porque `Reserva` no tiene FK directa a `Laboratorio` (solo vía `solicitud.laboratorio`, que ya no existe). Esto coincide con lo que ya señala la memoria del proyecto ("nunca hacer `.delete()`/bulk ops contra `db.sqlite3` sin respaldo — Laboratorio cascadea hasta SolicitudReserva"), pero el código no tiene ninguna barrera técnica que lo refleje.
- **Cómo arreglarlo:** agregar `@requiere_contrasena_admin` (mínimo) y/o el mismo chequeo de referencias que usa `eliminar_programa` antes de permitir el borrado; considerar además si `Laboratorio` debería desactivarse (ya existe el campo `activo`) en vez de borrarse físicamente.

### 6. `reservas_laboratorio` (la vista que sí pretende estar scoped) usa una lógica de scoping potencialmente incorrecta
- **Dónde:** `laboratorio/views.py:146-161`.
- Determina "reservas de este laboratorio" vía `ReservaInsumo.objects.filter(insumo__items__laboratorio=laboratorio)` — es decir, reservas que pidieron un insumo que *tiene al menos un ítem físico* en ese laboratorio — en vez de `solicitud__laboratorio=laboratorio` (el laboratorio para el que efectivamente se hizo la reserva). Como un mismo `Insumo` puede tener `ItemInventario` en varios laboratorios, esta vista puede: (a) mostrar reservas hechas para OTRO laboratorio si pidieron un insumo que también tiene stock acá, y (b) esconder reservas legítimas de este laboratorio si el insumo pedido todavía no tiene ítems físicos cargados. No es una falla de seguridad (sigue exigiendo `_check_lab_access`), pero sí un bug de corrección que socava la confiabilidad justo de la vista que se supone es la "correcta" para un laboratorista.
- **Cómo arreglarlo:** filtrar por `Reserva.objects.filter(solicitud__laboratorio=laboratorio)` directamente.

### 7. `cursos_profesor` (pública, sin login) permite enumerar cursos de un docente conociendo solo su nombre
- **Dónde:** `solicitudes/views.py:117-170`.
- El parámetro `cedula` es opcional: si no se envía, la vista toma automáticamente el primer docente que matchee por nombre (`usuarios[0]`) y devuelve sus cursos (código, nombre, cantidad de estudiantes) — sin ninguna verificación real de identidad. Si se envía una cédula que no coincide, el mensaje de error lista los nombres de otros docentes que sí matchearon el nombre buscado ("Docentes encontrados: X, Y, Z"), lo cual ayuda a enumerar cuentas por tanteo. No es información ultra-sensible, pero contradice el modelo de "cédula como verificación" que sí se aplicó consistentemente en el autoservicio nuevo (`MisReservasService`), y el hecho de que `cedula` sea opcional aquí lo vuelve, en la práctica, no-verificación.
- **Cómo arreglarlo:** exigir `cedula` siempre (no como fallback opcional) y no listar nombres de otros docentes en el mensaje de error.

### 8. Sin protección contra fuerza bruta en ningún endpoint
- **Dónde:** todo el proyecto — no hay `django-ratelimit`, `django-axes` ni throttling manual en ningún lado (`grep` sin resultados). Aplica tanto a `/login/` (vista de Django por defecto, sin límite de intentos) como al autoservicio nuevo por cédula+email (`/solicitudes/`, `/reservas/<id>/detalles/`, `/reservas/<id>/cancelar/`).
- Dado que las reservas se identifican por ID secuencial y la "autenticación" del autoservicio es cédula (9 dígitos predecibles) + email institucional (patrón `nombre.apellido@udea.edu.co` fácil de adivinar o obtener), un atacante automatizado podría iterar para encontrar y cancelar reservas ajenas, o simplemente para leer sus datos. Es un modelo de identidad deliberadamente débil (decisión tomada explícitamente al construir la función, documentada en el código) — pero sin throttling, esa debilidad es explotable a escala.
- **Cómo arreglarlo:** agregar throttling básico (por IP, por ejemplo con `django-ratelimit`) al menos sobre `/solicitudes/` (la búsqueda), `/reservas/<id>/detalles/` y `/reservas/<id>/cancelar/`, y considerar lo mismo para `/login/`.

### 9. `SolicitudReserva.crear_reserva()` no es atómica
- **Dónde:** `solicitudes/models.py` — el método crea la `Reserva`, guarda (`full_clean()` + `save()`), luego copia los `ReservaInsumo` en un loop, y **solo al final** hace `self.reserva = reserva; self.save(...)`. Nada de esto está envuelto en `transaction.atomic()`. Lo mismo aplica a `CrearSolicitudReservaService.crear_desde_estudiante`/`crear_desde_profesor` (`crear_libre` sí es atómico, con `@transaction.atomic`).
- Si algo falla a mitad del loop de insumos (o el proceso muere), queda una `Reserva` ya guardada, con insumos parcialmente copiados, y sin ninguna `SolicitudReserva` que la referencie todavía (huérfana) — exactamente el tipo de "datos huérfanos" que pide revisar esta auditoría.
- **Cómo arreglarlo:** envolver el cuerpo de `crear_reserva()` (desde que se crea la `Reserva` hasta que se vincula) en `@transaction.atomic`.

### 10. Condiciones de carrera en las validaciones de solapamiento/límites
- **Dónde:** `Reserva.clean()`/`tiene_solapamiento()` (`reservas/models.py`), `SolicitudReserva.clean()`/`limite_pendientes_alcanzado()`/validación de horas por día (`solicitudes/models.py`). Todos son chequeos "leer, luego decidir, luego guardar" sin `select_for_update()` ni constraint de BD que los respalde.
- Dos solicitudes concurrentes para el mismo horario/laboratorio podrían ambas pasar la validación antes de que cualquiera termine de guardar, resultando en un doble-booking. Con SQLite y el volumen de tráfico esperado hoy el riesgo práctico es bajo, pero es una debilidad arquitectónica real para un sistema de reservas.
- **Cómo arreglarlo (si el volumen de uso crece):** `select_for_update()` sobre las reservas en conflicto potencial dentro de una transacción, o un `UniqueConstraint` a nivel de BD que lo haga imposible por diseño.

### 11. Configuración de despliegue pendiente
- `manage.py check --deploy` reporta: `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` sin configurar. Asumiendo que en producción el sitio se sirve por HTTPS (recomendado), estas cuatro deben activarse antes de salir a producción real.
- `ALLOWED_HOSTS = ['localhost', '127.0.0.1']` está hardcodeado — hay que actualizarlo al dominio/IP real de producción (y probablemente moverlo también a `.env`, siguiendo el mismo patrón que `SENDGRID_API_KEY`).

### 12. Emails a varios encargados exponen la lista de destinatarios entre sí
- **Dónde:** `utils/notificaciones_email.py::notificar_cancelacion` (rama `cancelada_por='estudiante'`) — arma la lista de emails de `Laboratorio.encargados` y los pasa todos como `destinatarios` (header `To:`) de un mismo mensaje.
- Cada encargado ve las direcciones de los demás encargados del mismo laboratorio. Severidad baja (todos son staff interno de la misma institución/laboratorio), pero es una práctica evitable.
- **Cómo arreglarlo:** usar `bcc` en vez de `to`, o enviar un mensaje individual por destinatario.

---

## RECOMENDACIÓN (Mejorar después)

1. **Tests de aislamiento por laboratorio.** Agregar el mismo patrón de test que ya existe para `editar_insumos_reserva` (`test_editar_insumos_laboratorista_de_otro_lab_es_rechazado`) a `lista_reservas`, `detalle_reserva`, `aprobar_reserva`, `crear_prestamo`, `detalle_prestamo`, etc., una vez corregido el punto CRÍTICO #2 — para que el hueco no pueda reintroducirse sin que un test lo detecte.
2. **Auditoría persistente, no solo logs.** Hoy "quién hizo qué y cuándo" (cancelaciones, aprobaciones, cambios de insumos) vive únicamente en `logger.info()` de texto plano (útil para depurar, no para consultar/reportar). Considerar una tabla de auditoría simple (modelo `RegistroAuditoria` genérico, o un campo `cancelado_por`/`motivo` directamente en `Reserva`) para poder responder "¿quién canceló esta reserva y por qué?" sin grepear archivos de log.
3. **CI.** No hay integración continua configurada (ya listado como pendiente en el README) — correr `pytest` y `manage.py check --deploy` automáticamente en cada cambio evitaría que regresiones como el hueco de scoping (#2) o un `SECRET_KEY` hardcodeado lleguen a `main` sin que nadie lo note.
4. **Uniformar `requiere_contrasena_admin`** en el resto de acciones destructivas irreversibles que hoy no lo tienen (`eliminar_laboratorio`, `eliminar_laboratorista`).
5. **Cobertura de tests general (medida con `pytest --cov`, no solo estimada):** 69% global, 282 tests, todos en verde. Por archivo, las vistas son el punto más débil y las apps más nuevas/tocadas recientemente están mejor cubiertas:
   - `laboratorio/views.py`: **14%** (469 líneas, 404 sin cubrir) — la app que contiene `_check_lab_access`, el patrón que el punto CRÍTICO #2 pide replicar en `reservas`/`prestamos`. Que sea el archivo peor cubierto de todo el proyecto no es casualidad: es exactamente el tipo de código (control de acceso por rol/laboratorio) donde un hueco como el de #2 pasa desapercibido más tiempo. No existe un `tests/test_views/test_laboratorio_views.py`; `laboratorio/tests.py` solo cubre `ModuloEstadoService`.
   - `users/views.py`: **25%** — gestión de usuarios/roles, también código sensible desde el punto de vista de seguridad.
   - `config/views.py`: 30%, `prestamos/views.py`: 43%, `inventario/views.py`: 46%, `solicitudes/views.py`: 55%, `reservas/views.py`: 58%.
   - Los `services/` en general están bien cubiertos (90%+), igual que `models.py` de `reservas`/`prestamos` (91-97%). El patrón "primero el service con tests, después la vista" que se usó en el trabajo más reciente (`cancelar_reserva_service.py` 93%, `editar_insumos_service.py` 94%) es el que falta aplicar hacia atrás en `laboratorio` y `users`.
   - Reporte HTML completo ya generado en `htmlcov/` (`pytest --cov=. --cov-report=html`).

---

## Lo que SÍ está bien (para contexto, no todo son problemas)

- **Sin inyección SQL:** no hay `.raw()`, `cursor.execute()` ni `extra()` en ningún lugar del proyecto — 100% Django ORM.
- **CSRF:** el middleware está activo globalmente y no hay ningún `@csrf_exempt` en el proyecto.
- **Migraciones consistentes:** `manage.py makemigrations --check` no detecta cambios de modelo sin migrar.
- **`DEBUG = False`** ya está correctamente puesto (con un comentario que sugiere que esto ya se corrigió antes — buena señal de que el equipo presta atención a esto).
- **Secretos fuera del repo:** `SENDGRID_API_KEY` y, desde la corrección del punto #1, también `SECRET_KEY` viven en `.env` (gitignoreado, con `.env.example` de referencia) — ya no hay ninguna excepción a esa política dentro de `config/settings.py`.
- **Manejo de fallos de email:** cada notificación (`notificar_*`) está envuelta en `try/except Exception` con `logger.exception(...)` en el punto de llamada — un fallo de SendGrid nunca interrumpe el flujo de negocio (crear reserva, cancelar, etc.), solo queda registrado.
- **Contraseña admin separada** (`Usuario.admin_password_hash`, hasheada con `make_password`/`check_password` de Django — PBKDF2) para acciones críticas, con logging de intentos (`logger_acceso_admin`) — buen patrón de defensa en profundidad para las acciones más destructivas que sí lo usan.
- **`editar_insumos_reserva`** es el ejemplo a seguir para el resto del sistema: control de acceso por laboratorio, validación de stock, auditoría en log, notificación por email — todo presente y testeado.

---

## CONCLUSIÓN

❌ **NECESITA ARREGLOS antes de producción.**

Los tres puntos CRÍTICOS son concretos y accionables, no teóricos:

1. ~~El `SECRET_KEY` ya está expuesto (está en git) y debe rotarse independientemente de cuándo se despliegue.~~ **Resuelto** — ver detalle en el punto #1 de arriba.
2. El aislamiento por laboratorio — explícitamente pedido en el objetivo de esta auditoría ("¿Laboratorista solo ve su lab?") — **no se cumple** en la mayoría del flujo real de reservas y préstamos, solo en la funcionalidad más reciente (`editar_insumos_reserva`). Esto es una falla de control de acceso real, no una suposición: un laboratorista de un lab puede hoy aprobar, cancelar o crear préstamos sobre reservas de cualquier otro laboratorio.
3. La falta de `unique=True` en las tablas de estado es una bomba de tiempo de bajo costo de arreglar y alto costo si detona (rompe el sistema completo).

Ninguno de los tres requiere un rediseño — son cambios acotados (una línea de config, decoradores/filtros de queryset consistentes con un patrón que ya existe en el propio código, y una migración de `unique=True`). Una vez resueltos, junto con al menos las advertencias #4 (colisión de `codigo`) y #5 (`eliminar_laboratorio` sin protección), el sistema está en un punto razonable para producción — el resto de advertencias y recomendaciones son mejoras de robustez que pueden abordarse de forma incremental sin bloquear un primer despliegue.
