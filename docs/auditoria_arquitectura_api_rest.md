# Auditoría de Arquitectura — Preparación para API REST

**Proyecto:** sistema_laboratorios (Django 6.0 + SQLite)
**Alcance:** users, laboratorio, inventario, reservas, prestamos, solicitudes
**Fecha:** 2026-08-11

---

## 1. Resumen

**Puntos fuertes**

- Estructura modular por dominio (6 apps), consistente y sin mezclas raras entre apps.
- Dos apps (`reservas`, `prestamos`) ya tienen el patrón correcto: servicios de una responsabilidad, con logging estructurado, `ValidationError` y **tests dedicados** (`tests/test_services/`). Son la plantilla a replicar.
- Control de acceso por rol (`@rol_requerido`) aplicado de forma consistente en absolutamente todas las vistas protegidas revisadas.
- Soft-delete en `ItemInventario` vía manager custom (`objects` vs `activos`) — patrón limpio, bien documentado y usado correctamente en todas las vistas.
- `utils/excel_export.py` es un buen ejemplo de separar una responsabilidad transversal (generar Excel) de HTTP.

**Puntos débiles**

- Cobertura de service layer muy baja: solo 2 de 6 apps tienen servicios reales. `solicitudes` — el módulo con las reglas de negocio más complejas — tiene una carpeta `services/` **vacía**.
- Lógica de negocio pesada y duplicada directamente en vistas, sobre todo en `laboratorio/views.py` (981 líneas, el archivo más grande del proyecto).
- Validación a nivel de modelo (`clean()`) solo existe en 1 de ~15 modelos. El resto depende de `ModelForm`, que un serializer de DRF no usa automáticamente.
- Las señales (`signals.py`) esconden efectos secundarios de negocio (cambio de estado de inventario) fuera del ciclo request/response — riesgoso para una API que exponga escritura directa o bulk.
- Aplicación inconsistente de `requiere_contrasena_admin` en acciones igualmente destructivas.
- `djangorestframework` no está en `requirements.txt` — el proyecto no ha arrancado la capa de API todavía.

---

## 2. Hallazgos por categoría

### 2.1 Services / Use Cases

Inventario real de archivos de servicio:

| Archivo | Clases | Líneas |
|---|---|---|
| [reservas/services/crear_reserva_service.py](../reservas/services/crear_reserva_service.py) | `CrearReservaService` | 52 |
| [prestamos/services/inspeccionar_prestamo_service.py](../prestamos/services/inspeccionar_prestamo_service.py) | `InspeccionarPrestamoService`, `FinalizarInspeccionService` | 112 |
| `solicitudes/services/__init__.py` | *(vacío)* | 0 |

`users`, `inventario` y `laboratorio` no tienen carpeta `services/` en absoluto.

**Lo que está bien:** los dos servicios existentes siguen un patrón consistente y sólido — método `ejecutar`/verbo de negocio, logging con contexto (`usuario`, ids), `try/except` que loguea y re-lanza, y validaciones de negocio vía `ValidationError`. Ambos tienen tests unitarios propios. Es la plantilla correcta para todo lo que sigue.

**Lo que falta:**

- `solicitudes` es la app con más reglas de negocio (`SolicitudReserva.clean()`, 90+ líneas) y **cero** servicios. Toda la orquestación vive repartida entre el modelo (`crear_reserva()`, `asignar_modulos_automaticamente()`) y las vistas.
- `laboratorio` no tiene servicios pese a tener la lógica más compleja del proyecto: el cálculo de "estado de módulo" (disponible/ocupado/reservado/inactivo) está implementado **de forma independiente 4 veces** dentro de `laboratorio/views.py` (ver [§2.7](#27-código-duplicado)). Esto es exactamente el tipo de lógica que una API necesita como función pura y testeable — hoy no existe en ningún lugar reutilizable.
- Flujos con reglas de negocio reales que hoy viven en vistas y deberían ser service:
  - Creación manual de reserva desde admin: [reservas/views.py:107-270](../reservas/views.py) (`crear_reserva`) — ~150 líneas parseando `request.POST` a mano.
  - Reserva libre de profesor: [solicitudes/views.py:52-183](../solicitudes/views.py) (`solicitud_profesor`, rama `es_libre`) — ~110 líneas de validación manual, en paralelo a `ProfesorSolicitudForm` que existe pero no se usa en esta rama.
  - Aprobación de profesor + generación de usuario: [solicitudes/views.py:361-432](../solicitudes/views.py) (`detalle_solicitud_profesor`).
  - Creación de laboratorio + cuenta de encargado asociada: [laboratorio/views.py:49-89](../laboratorio/views.py) (`crear_laboratorio`).

**¿Son reutilizables?** Sí — los dos servicios existentes no dependen de `request`, reciben ids/objetos y devuelven objetos de dominio o lanzan `ValidationError`. Son directamente invocables desde una vista DRF sin cambios. Ese es el estándar a exigir para todo lo nuevo.

### 2.2 Models

| Modelo | clean() | Métodos de negocio en el modelo | Nota |
|---|---|---|---|
| `Usuario` ([users/models.py](../users/models.py)) | No | `set_admin_password`, `check_admin_password`, `tiene_admin_password` | Buen encapsulamiento, sin `clean()` porque no lo necesita |
| `Reserva` ([reservas/models.py:62-73](../reservas/models.py)) | No | `save()` calcula `hora_limite_retiro`/`fecha_devolucion`; `generar_codigo()` | `generar_codigo()` navega `self.solicitud.first()` — acoplamiento inverso hacia `solicitudes` |
| `Prestamo` ([prestamos/models.py:43-71](../prestamos/models.py)) | No | `generar_codigo()` | Algoritmo de siglas duplicado con `Reserva.generar_codigo()` |
| `Insumo`/`ItemInventario` ([inventario/models.py](../inventario/models.py)) | No | `cantidad_disponible()`, `stock_minimo_alcanzado()`, `soft_delete()`, `is_deleted()` | Buen ejemplo: reglas de negocio correctamente en el modelo |
| `SolicitudReserva` ([solicitudes/models.py:93-248](../solicitudes/models.py)) | **Sí**, 90+ líneas | `crear_reserva()`, `asignar_modulos_automaticamente()`, `_calcular_duracion()`, `_validar_horario_laboratorio()` | Único `clean()` de todo el proyecto; ver nota abajo |

**Nota sobre `SolicitudReserva.clean()`:** correctamente ubicado en el modelo (es validación de negocio, no de presentación), pero tiene un efecto secundario atípico para un `clean()`: en la línea [solicitudes/models.py:116](../solicitudes/models.py) hace `self.usuario = usuarios.first()` — es decir, *muta* la instancia durante la validación en lugar de solo validar. Un `full_clean()` llamado desde un serializer de DRF (que sí lo invoca automáticamente) tendría este efecto secundario implícito, que hoy nadie documenta ni testea explícitamente.

**El hallazgo más relevante para la API:** de ~15 modelos en el proyecto, **solo uno** implementa `clean()`. Todos los demás (`Insumo`, `ItemInventario`, `Usuario`, `Laboratorio`, `Curso`, `Prestamo`, etc.) dependen enteramente de la validación de campo por defecto de Django (`required`, `unique`, FK) más lo que cada `ModelForm` agregue. Un `ModelSerializer` de DRF no hereda la validación de un `ModelForm` — si hoy `InsumoForm` no tiene `clean()` propio (y no lo tiene, ver [§2.5](#25-formularios)), tampoco hay nada que perder al migrar a un serializer, pero **tampoco hay nada que ganar automáticamente**: cualquier regla de negocio que dependa de una vista (p. ej. permisos de campo, cálculos) deberá reimplementarse explícitamente en el serializer si no se sube al modelo antes.

### 2.3 Vistas

La mayoría de las vistas CRUD son delgadas y siguen el patrón `ModelForm` estándar de Django — estas mapean directamente y sin fricción a un `ModelViewSet` + `ModelSerializer` de DRF.

El problema está concentrado en un subconjunto identificable de vistas con lógica de negocio sustancial escrita directamente ahí:

- **`laboratorio/views.py:mapa_laboratorio`** ([líneas 248-446](../laboratorio/views.py)) — ~200 líneas calculando disponibilidad de módulos, cruzando `SolicitudReserva`, `HistorialModulo` y `Prestamo`.
- **`laboratorio/views.py:estado_modulos_api` / `modulos_disponibles_api` / `modulos_disponibles_publica_api`** ([líneas 489-678](../laboratorio/views.py)) — reimplementan variantes de la misma lógica de estado de módulo.
- **`reservas/views.py:crear_reserva`** ([líneas 107-270](../reservas/views.py)) — parseo manual de ~15 campos de `request.POST`, sin usar el `ReservaForm` que existe en `reservas/forms.py` (que además no se usa en ningún otro lugar — código muerto).
- **`solicitudes/views.py:solicitud_profesor`**, rama `es_libre` ([líneas 56-183](../solicitudes/views.py)) — mismo patrón: validación manual campo por campo en vez de usar/extender un `Form`.
- **`laboratorio/views.py:crear_laboratorista` / `editar_laboratorista`** ([líneas 796-936](../laboratorio/views.py)) — parseo manual + validación manual con lista `errores`, sin `Form`.

**Manejo de errores — inconsistente:**

- `prestamos/views.py:marcar_devuelto` ([líneas 371-384](../prestamos/views.py)) hace `try/except` con logging estructurado y re-lanza — buen patrón, único lugar donde se ve completo.
- `solicitudes/views.py` usa `print()` para debug en vez del módulo `logging` que sí se usa consistentemente en `reservas`, `prestamos` y `users` (ver [líneas 41 y 44](../solicitudes/views.py): `print(f"Error creando reserva: {e}")`, `print(f"DEBUG: form inválido, errores={form.errors}")`).
- Vistas JSON no tienen un formato de error estandarizado: `estado_modulos_api` devuelve `{'error': '...'}` con status 400; `crear_evento`/`eliminar_evento` devuelven `{'status': 'error'}` sin mensaje ([laboratorio/views.py:230-244](../laboratorio/views.py)).
- Varios lookups usan `EstadoX.objects.get(nombre='Y')` (lanza `DoesNotExist` → 500 si falta el seed) mezclado con `.filter(nombre='Y').first()` (falla en silencio devolviendo `None`) para el mismo tipo de búsqueda en distintos puntos del código — comportamiento de fallo inconsistente ante el mismo problema (dato de seed faltante).

### 2.4 Decoradores (`users/decorators.py`)

Solo dos decoradores, ambos bien documentados con docstrings explicando el *porqué* (poco común en el resto del proyecto):

- **`rol_requerido(*roles)`** — aplicado consistentemente en las 6 apps; no se encontró ninguna vista que debiera estar protegida y no lo esté. Las vistas públicas (`solicitud_estudiante`, `solicitud_profesor`, `registro_profesor_publico`, `api_insumos`, `modulos_disponibles_publica_api`) están deliberadamente sin decorar, de forma consistente con su propósito (formularios públicos).
- **`requiere_contrasena_admin(...)`** — aplicado solo en algunas acciones irreversibles: `eliminar_insumo`, `eliminar_item_inventario`, `desactivar_usuario`, `eliminar_programa`, `eliminar_curso`. **No** está aplicado en `eliminar_laboratorio` ([laboratorio/views.py:135-142](../laboratorio/views.py)), `eliminar_laboratorista` ([laboratorio/views.py:940-949](../laboratorio/views.py)), `cancelar_reserva` ([reservas/views.py:322-331](../reservas/views.py)) ni `eliminar_insumo_reserva` ([reservas/views.py:452-467](../reservas/views.py)) — acciones igual de irreversibles. Esto parece un criterio aplicado caso por caso más que una política explícita.

**Para la API:** `rol_requerido` redirige a `login`/`sin_permiso` con HTML — no es reutilizable tal cual en un endpoint DRF, que necesita 401/403 JSON. Se debería extraer `ROLES_ACCION_CRITICA` y la lógica de comparación de rol a una `permission_class` de DRF que comparta la misma fuente de verdad (no reinventar la lista de roles en el serializer).

### 2.5 Formularios

- La mayoría de los forms son `ModelForm` de solo widgets, sin `clean()` propio — la validación real es la que Django aplica por defecto a nivel de campo.
- **Duplicación exacta:** `EstudianteSolicitudForm._guardar_insumos()` y `ProfesorSolicitudForm._guardar_insumos()` en [solicitudes/forms.py](../solicitudes/forms.py) (líneas 134-159 y 278-303) son el mismo método copiado literalmente. Debería vivir en un mixin, o mejor, en el service que aún no existe para `solicitudes`.
- **Código muerto:** `ReservaForm` ([reservas/forms.py:9-26](../reservas/forms.py)) no se importa ni se usa en ningún `views.py` — `crear_reserva` parsea `request.POST` directamente en su lugar.

### 2.6 Señales (Signals)

Dos archivos: [inventario/signals.py](../inventario/signals.py) y [prestamos/signals.py](../prestamos/signals.py).

- `prestamos/signals.py:registrar_movimiento_item` (post_save de `PrestamoItem`) y `registrar_movimiento_estado` (post_save de `Prestamo`) **mutan `ItemInventario.estado`** como efecto colateral implícito de guardar un préstamo — no es solo auditoría, es la transición de estado real del inventario.
- `inventario/signals.py:registrar_cambio_estado` coordina con lo anterior mediante un flag transitorio no persistido (`instance._desde_prestamo`) para no duplicar el registro — una comunicación señal-a-señal frágil, dependiente de que ambos módulos conozcan ese contrato implícito.

**Por qué esto importa para la API:** hoy "crear un `PrestamoItem`" cambia el inventario solo porque `.save()` dispara la señal. Esto es invisible salvo que se conozca el código de `signals.py`. Un `ModelViewSet` de DRF sobre `PrestamoItem` "funcionaría por accidente" (porque DRF también llama `.save()`), pero cualquier `bulk_create`/`update()` en el futuro — la clase exacta de operación que ya está señalada como riesgosa en este proyecto — **saltaría la señal en silencio** y dejaría el inventario desincronizado sin ningún error visible.

**Recomendación:** mover la transición de estado (`item.estado = ...`) a una llamada explícita de servicio (extender `InspeccionarPrestamoService` o crear un pequeño `PrestamoItemService.crear(...)`), dejando la señal — si se conserva — únicamente para el registro de auditoría (`MovimientoInventario`), que sí es razonable como efecto secundario transversal.

### 2.7 Código duplicado

| Duplicación | Ubicaciones |
|---|---|
| Cálculo de "estado de módulo" (disponible/ocupado/reservado/inactivo) — 4 implementaciones independientes con reglas ligeramente distintas | [laboratorio/views.py](../laboratorio/views.py): `mapa_laboratorio` (248-446), `estado_modulos_api` (489-573), `modulos_disponibles_api` (577-625), `modulos_disponibles_publica_api` (628-678) |
| `modulos_disponibles_api` y `modulos_disponibles_publica_api` — ~90% código idéntico | [laboratorio/views.py:577-678](../laboratorio/views.py) |
| `_guardar_insumos()` — método idéntico en dos forms | [solicitudes/forms.py:134-159](../solicitudes/forms.py) y [278-303](../solicitudes/forms.py) |
| Generación de username `doc_<cedula>` con loop de sufijo anticolisión | [users/views.py:177-184](../users/views.py) (`crear_profesor`) y [solicitudes/views.py:371-377](../solicitudes/views.py) (`detalle_solicitud_profesor`) |
| Chequeo "el laboratorio ya tiene encargado" | [laboratorio/views.py](../laboratorio/views.py): `asignar_laboratorista` (719-722, 750-754), `crear_laboratorista` (842-845), `editar_laboratorista` (916-919) |
| Algoritmo de siglas para `generar_codigo()` | [reservas/models.py:48-60](../reservas/models.py) y [prestamos/models.py:43-65](../prestamos/models.py) |
| Parseo de filtros `estado`/`fecha_inicio`/`fecha_fin` en exports Excel (menor prioridad) | `reservas/views.py:exportar_reservas_excel`, `prestamos/views.py:exportar_prestamos_excel`, `exportar_inspecciones_excel` |
| Nombres de estado como strings literales dispersos (`'Aprobada'`, `'Cancelada'`, `'Disponible'`, etc.) en ~15+ sitios en vez de constantes | Todas las apps |

---

## 3. Recomendaciones

### Antes de empezar la API (bloqueante)

1. **Extraer el cálculo de "estado de módulo" a una función/servicio único** (`laboratorio/services/estado_modulos_service.py`). Es el endpoint de lectura más usado del futuro API y hoy está escrito 4 veces con reglas que ya divergen ligeramente entre sí.
2. **Agregar `clean()`/validadores a nivel de modelo** para las reglas mínimas que hoy solo viven en `ModelForm` (unicidad, campos requeridos, invariantes de negocio) en `Insumo`, `ItemInventario`, `Usuario`, `Laboratorio`, `Curso`, `Prestamo`, `Reserva`. Un serializer de DRF no hereda validación de un `ModelForm`.
3. **Convertir la transición de estado de inventario en `prestamos/signals.py` en una llamada de servicio explícita**, dejando la señal solo (si acaso) para el registro de auditoría. Es el punto de mayor riesgo: una API que exponga escritura directa o bulk sobre `PrestamoItem`/`Prestamo` puede desincronizar el inventario en silencio.
4. **Crear servicios para los flujos sin servicio identificados:** reserva manual (`reservas/views.py:crear_reserva`), reserva libre de profesor (`solicitudes/views.py:solicitud_profesor`), aprobación de profesor (`solicitudes/views.py:detalle_solicitud_profesor`) — usando `CrearReservaService`/`InspeccionarPrestamoService` como plantilla.

### Después, no bloqueante para los primeros endpoints

5. Deduplicar: estado de módulo (4 sitios), `_guardar_insumos` (2 forms), chequeo de encargado (4 sitios), `generar_codigo` (2 modelos).
6. Centralizar nombres de estado como constantes en vez de strings literales repetidos.
7. Reemplazar `print()` por `logging` en `solicitudes/views.py`, igualando el estándar ya usado en `reservas`/`prestamos`/`users`.
8. Definir explícitamente (y documentar) qué acciones requieren `requiere_contrasena_admin` — hoy es un criterio implícito, caso por caso.

### En paralelo a construir la API

9. Agregar `djangorestframework` a `requirements.txt`; empezar los primeros `ViewSet`/serializers sobre `reservas` y `prestamos`, que son las apps con la lógica de negocio ya aislada en servicios y con tests existentes.
10. Eliminar o conectar `ReservaForm` (código muerto en `reservas/forms.py`).

---

## 4. Puntuación general

**Arquitectura: 6/10 — Funcional, con buenos cimientos, pero no lista para exponer una API directamente sobre las vistas actuales.**

La base es sólida donde existe (decoradores, soft-delete, los dos servicios existentes con sus tests), pero la cobertura es despareja: justo la app con las reglas de negocio más complejas (`solicitudes`) no tiene service layer, y el archivo de vistas más grande del proyecto (`laboratorio/views.py`) concentra lógica duplicada que una API necesitaría como función única y testeable. Las señales de `prestamos` esconden un efecto secundario de negocio crítico (cambio de estado de inventario) fuera del flujo explícito de request/response, lo cual es el mayor riesgo si se expone escritura vía API.

## 5. Próximos pasos

**No conviene saltar directo a construir la API.** Recomendación: sprint enfocado de refactor (los 4 puntos bloqueantes de la sección 3) usando `reservas`/`prestamos` como plantilla, y luego empezar la capa DRF por esas dos apps —ya están más cerca de listas—, mientras el refactor de `solicitudes` y `laboratorio` continúa en paralelo antes de exponer sus endpoints.
