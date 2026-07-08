# Diagrama Entidad-Relación — Sistema de Laboratorios

Este diagrama refleja el estado actual del modelo de datos del proyecto `sistema_laboratorios`, generado a partir de la lectura directa de los archivos `models.py` de las apps `users`, `laboratorio`, `inventario`, `reservas`, `solicitudes` y `prestamos`.

**Fecha de generación:** 2026-07-02

> Nota: `SolicitudReserva.reserva` es una FK simple (no `unique=True`) hacia `Reserva`, por lo que estructuralmente permite varias solicitudes por reserva; en la práctica del negocio cada solicitud genera y referencia una única reserva propia (relación 1:1 de uso). Por fidelidad al código se representa como uno-a-muchos (`Reserva ||--o{ SolicitudReserva`). Lo mismo aplica para `Prestamo.reserva`, que tampoco tiene restricción `unique`. La relación `Laboratorio ↔ Usuario` (encargados) es un M2M real gestionado por Django; se representa con `}o--o{`.

```mermaid
erDiagram

    %% ── users ───────────────────────────────────────────────────
    Rol {
        int id PK
        string nombre
    }

    ProgramaAcademico {
        int id PK
        string nombre
        boolean activo
    }

    Usuario {
        int id PK
        string username
        string first_name
        string last_name
        string email
        string codigo
        string programa
        boolean is_active
        int rol_id FK
    }

    %% ── laboratorio ─────────────────────────────────────────────
    Laboratorio {
        int id PK
        string nombre
        string ubicacion
        string programa
    }

    HorarioLaboratorio {
        int id PK
        string dia
        time hora_inicio
        time hora_fin
        boolean bloqueado
        string motivo_bloqueo
        int laboratorio_id FK
    }

    EventoLaboratorio {
        int id PK
        string titulo
        datetime inicio
        datetime fin
        boolean bloqueado
        int laboratorio_id FK
        int creado_por_id FK
    }

    Modulo {
        int id PK
        string nombre
        int capacidad
        boolean disponible
        string motivo_no_disponible
        int laboratorio_id FK
    }

    Laboratorista {
        int id PK
        string nombre
        string apellido
        string cedula
        string correo
        string programa
        json responsabilidades
        boolean activo
    }

    LaboratoristaLab {
        int id PK
        int laboratorista_id FK
        int laboratorio_id FK
        string tipo
    }

    %% ── inventario ──────────────────────────────────────────────
    TipoMovimiento {
        int id PK
        string nombre
    }

    EstadoItem {
        int id PK
        string nombre
    }

    EstadoInsumo {
        int id PK
        string nombre
    }

    Insumo {
        int id PK
        string nombre
        string descripcion
        string marca
        int stock_minimo
        int estado_id FK
    }

    ItemInventario {
        int id PK
        string codigo
        int insumo_id FK
        int estado_id FK
        int laboratorio_id FK
        datetime fecha_registro
        int updated_by_id FK
    }

    MovimientoInventario {
        int id PK
        int item_inventario_id FK
        int usuario_id FK
        int tipo_movimiento_id FK
        datetime fecha
        string observacion
    }

    %% ── reservas ────────────────────────────────────────────────
    EstadoReserva {
        int id PK
        string nombre
    }

    Reserva {
        int id PK
        int usuario_id FK
        datetime fecha_reserva
        datetime hora_limite_retiro
        datetime fecha_devolucion
        int estado_id FK
        datetime fecha_creacion
    }

    ReservaInsumo {
        int id PK
        int reserva_id FK
        int insumo_id FK
        int cantidad
    }

    %% ── prestamos ───────────────────────────────────────────────
    EstadoPrestamo {
        int id PK
        string nombre
    }

    Prestamo {
        int id PK
        int reserva_id FK
        int responsable_id FK
        int estado_id FK
        datetime fecha_entrega
        datetime fecha_devolucion
    }

    PrestamoItem {
        int id PK
        int prestamo_id FK
        int item_inventario_id FK
    }

    %% ── solicitudes ─────────────────────────────────────────────
    Curso {
        int id PK
        string nombre
        string codigo
        int profesor_id FK
        int cantidad_estudiantes
    }

    SolicitudReserva {
        int id PK
        string tipo_solicitante
        int usuario_id FK
        string nombre
        string cedula
        string programa
        int curso_id FK
        int laboratorio_id FK
        datetime fecha_reserva
        time hora_inicio
        time hora_fin
        boolean necesita_modulo
        string observaciones
        boolean reserva_libre
        string descripcion_actividad
        int cantidad_asistentes_libre
        int reserva_id FK
        datetime fecha_creacion
    }

    SolicitudInsumo {
        int id PK
        int solicitud_id FK
        int insumo_id FK
        int cantidad
    }

    SolicitudRegistroProfesor {
        int id PK
        string nombre
        string apellido
        string cedula
        string correo
        string programa
        string estado
        datetime fecha_creacion
        int usuario_creado_id FK
    }

    SolicitudRegistroCurso {
        int id PK
        int solicitud_profesor_id FK
        string nombre
        string codigo
        int cantidad_estudiantes
        string estado
        int curso_creado_id FK
    }

    %% ── Relaciones ──────────────────────────────────────────────

    %% users
    Rol ||--o{ Usuario : tiene
    Usuario }o--o{ Laboratorio : encargados

    %% laboratorio
    Laboratorio ||--o{ HorarioLaboratorio : define
    Laboratorio ||--o{ EventoLaboratorio : tiene
    Usuario ||--o{ EventoLaboratorio : crea
    Laboratorio ||--o{ Modulo : tiene
    Laboratorio ||--o{ LaboratoristaLab : asignaciones
    Laboratorista ||--o{ LaboratoristaLab : asignaciones

    %% inventario
    EstadoInsumo ||--o{ Insumo : clasifica
    Insumo ||--o{ ItemInventario : tiene
    EstadoItem ||--o{ ItemInventario : clasifica
    Laboratorio ||--o{ ItemInventario : ubica
    Usuario ||--o{ ItemInventario : actualiza
    ItemInventario ||--o{ MovimientoInventario : registra
    Usuario ||--o{ MovimientoInventario : realiza
    TipoMovimiento ||--o{ MovimientoInventario : clasifica

    %% reservas
    EstadoReserva ||--o{ Reserva : tiene
    Usuario ||--o{ Reserva : hace
    Reserva ||--o{ ReservaInsumo : incluye
    Insumo ||--o{ ReservaInsumo : "solicitado en"

    %% prestamos
    EstadoPrestamo ||--o{ Prestamo : tiene
    Reserva ||--o{ Prestamo : genera
    Usuario ||--o{ Prestamo : "es responsable de"
    Prestamo ||--o{ PrestamoItem : incluye
    ItemInventario ||--o{ PrestamoItem : "prestado en"

    %% solicitudes
    Usuario ||--o{ Curso : dicta
    Usuario ||--o{ SolicitudReserva : hace
    Laboratorio ||--o{ SolicitudReserva : recibe
    Curso ||--o{ SolicitudReserva : "asociada a"
    Reserva ||--o{ SolicitudReserva : origina
    SolicitudReserva }o--o{ Modulo : asigna
    SolicitudReserva ||--o{ SolicitudInsumo : incluye
    Insumo ||--o{ SolicitudInsumo : "solicitado en"
    SolicitudRegistroProfesor ||--o{ SolicitudRegistroCurso : tiene
    Usuario ||--o{ SolicitudRegistroProfesor : crea
    Curso ||--o{ SolicitudRegistroCurso : genera
```
