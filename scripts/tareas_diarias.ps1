# tareas_diarias.ps1 - SISTEMA_LABORATORIOS
#
# Ejecuta, con el Python del venv del proyecto, los comandos de gestion
# periodicos de prestamos:
#   1. marcar_retrasados                -> Activo => Retrasado si ya paso la devolucion
#   2. enviar_recordatorios_devolucion  -> email de atraso (una sola vez por prestamo)
#
# Pensado para el Programador de tareas de Windows. Escribe la salida en
# logs\tareas_programadas.log y termina con codigo 1 si algun comando falla.
# No contiene credenciales: todo se lee del .env del proyecto.

$ErrorActionPreference = 'Stop'

$Proyecto = Split-Path -Parent $PSScriptRoot
$Python   = Join-Path $Proyecto 'venv\Scripts\python.exe'
$Manage   = Join-Path $Proyecto 'manage.py'
$LogDir   = Join-Path $Proyecto 'logs'
$Log      = Join-Path $LogDir 'tareas_programadas.log'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Log([string]$Mensaje) {
    $linea = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Mensaje
    Add-Content -Path $Log -Value $linea -Encoding UTF8
}

if (-not (Test-Path $Python)) {
    Write-Log "ERROR: no existe $Python (crear el venv primero)."
    exit 1
}

$env:PYTHONIOENCODING = 'utf-8'
Set-Location $Proyecto

$Comandos = @('marcar_retrasados', 'enviar_recordatorios_devolucion')
$Fallos = 0

foreach ($Comando in $Comandos) {
    Write-Log "Inicio: $Comando"
    $ErrorActionPreference = 'Continue'
    $salida = & $Python $Manage $Comando 2>&1 | ForEach-Object { "$_" }
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    foreach ($l in $salida) { Write-Log "  $l" }
    if ($codigo -ne 0) {
        Write-Log "FALLO: $Comando (codigo $codigo)"
        $Fallos++
    } else {
        Write-Log "OK: $Comando"
    }
}

exit ([int]($Fallos -gt 0))
