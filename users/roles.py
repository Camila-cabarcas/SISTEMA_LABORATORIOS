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
"""

ADMINISTRADOR = 'Administrador'
LABORATORISTA = 'Laboratorista'
MONITOR = 'Monitor'

# Personal con gestión del laboratorio (sin el Monitor).
ROLES_GESTION = (ADMINISTRADOR, LABORATORISTA)

# Personal que opera préstamos y reservas (con el Monitor).
ROLES_OPERACION = (ADMINISTRADOR, LABORATORISTA, MONITOR)
