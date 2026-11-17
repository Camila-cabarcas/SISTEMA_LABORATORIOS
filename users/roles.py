"""
roles.py — users
Nombres de los roles del sistema (valor de users.Rol.nombre) y los grupos
de roles que comparten permisos. Sin imports de modelos a propósito: lo
importan decoradores, helpers y vistas sin riesgo de import circular.

- Administrador: todo.
- Laboratorista: lo del Monitor más importar inventario, aprobar/rechazar
  reservas y levantar vetos de daño/falta de insumo, solo en los
  laboratorios de Laboratorio.laboratoristas.
- Monitor: préstamos, reservas de estudiantes y consulta de inventario, solo
  en los laboratorios de Laboratorio.monitores.

Personal: el Administrador administra cuentas de laboratorista y de monitor
y todas las fichas; el Laboratorista ve Personal de su laboratorio y
administra sus fichas de monitor y su descripción; el Monitor no ve Personal.
"""

ADMINISTRADOR = 'Administrador'
LABORATORISTA = 'Laboratorista'
MONITOR = 'Monitor'

# Personal con gestión del laboratorio (sin el Monitor).
ROLES_GESTION = (ADMINISTRADOR, LABORATORISTA)

# Personal que opera préstamos y reservas (con el Monitor).
ROLES_OPERACION = (ADMINISTRADOR, LABORATORISTA, MONITOR)

# ── Personal (fijos, no configurables) ─────────────────────────────────────
# Crear, editar y dar de baja cuentas de laboratorista y de monitor.
ROLES_ADMIN_PERSONAL = (ADMINISTRADOR,)
# Fichas de monitor: el Administrador en cualquier laboratorio, el
# Laboratorista solo en el suyo. El Monitor no ve Personal.
ROLES_FICHAS_MONITOR = (ADMINISTRADOR, LABORATORISTA)
# Descripción del laboratorio: mismo criterio que las fichas.
ROLES_DESCRIPCION_LAB = (ADMINISTRADOR, LABORATORISTA)
# Aprobar o rechazar solicitudes de registro de profesor: el Administrador
# todas; el Laboratorista las de su laboratorio de interés o sin laboratorio.
ROLES_SOLICITUDES_PROFESOR = (ADMINISTRADOR, LABORATORISTA)
# Roles que solo se asignan desde Personal (no desde la pantalla genérica de
# usuarios ni desde el admin de Django).
ROLES_SOLO_DESDE_PERSONAL = (LABORATORISTA, MONITOR)
