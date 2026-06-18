# Diagrama Entidad-Relación — Sistema de Laboratorios

Este diagrama refleja el estado actual del modelo de datos del proyecto `sistema_laboratorios`, generado a partir de la lectura directa de los archivos `models.py` de las apps `users`, `laboratorio`, `inventario`, `reservas`, `solicitudes` y `prestamos`.

**Fecha de generación:** 2026-06-18

> Nota: `SolicitudReserva.reserva` es una FK simple (no `unique=True`) hacia `Reserva`, por lo que estructuralmente permite varias solicitudes por reserva; en la práctica del negocio cada solicitud genera y referencia una única reserva propia (relación 1:1 de uso). Por fidelidad al código se representa como uno-a-muchos (`Reserva ||--o{ SolicitudReserva`). Lo mismo aplica para `Prestamo.reserva`, que tampoco tiene restricción `unique`.

```mermaid
erDiagram
    Rol {
        int id PK
        string nombre
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

    Laboratorio {
        int id PK
        string nombre
        string ubicacion
        string programa
        int encargado_id FK
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
        int reserva_id FK
        datetime fecha_creacion
    }

    SolicitudInsumo {
        int id PK
        int solicitud_id FK
        int insumo_id FK
        int cantidad
    }

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

    Rol ||--o{ Usuario : tiene
    Usuario ||--o{ Laboratorio : encarga
    Usuario ||--o{ EventoLaboratorio : crea
    Laboratorio ||--o{ HorarioLaboratorio : define
    Laboratorio ||--o{ EventoLaboratorio : tiene
    Laboratorio ||--o{ Modulo : tiene
    Laboratorio ||--o{ ItemInventario : ubica
    Laboratorio ||--o{ SolicitudReserva : recibe
    EstadoInsumo ||--o{ Insumo : clasifica
    Insumo ||--o{ ItemInventario : tiene
    EstadoItem ||--o{ ItemInventario : clasifica
    Usuario ||--o{ ItemInventario : actualiza
    ItemInventario ||--o{ MovimientoInventario : registra
    Usuario ||--o{ MovimientoInventario : realiza
    TipoMovimiento ||--o{ MovimientoInventario : clasifica
    EstadoReserva ||--o{ Reserva : tiene
    Usuario ||--o{ Reserva : hace
    Reserva ||--o{ ReservaInsumo : incluye
    Insumo ||--o{ ReservaInsumo : "solicitado en"
    Usuario ||--o{ Curso : dicta
    Usuario ||--o{ SolicitudReserva : hace
    Curso ||--o{ SolicitudReserva : "asociada a"
    Reserva ||--o{ SolicitudReserva : origina
    SolicitudReserva }o--o{ Modulo : asigna
    SolicitudReserva ||--o{ SolicitudInsumo : incluye
    Insumo ||--o{ SolicitudInsumo : "solicitado en"
    EstadoPrestamo ||--o{ Prestamo : tiene
    Reserva ||--o{ Prestamo : genera
    Usuario ||--o{ Prestamo : "es responsable de"
    Prestamo ||--o{ PrestamoItem : incluye
    ItemInventario ||--o{ PrestamoItem : "prestado en"
```
