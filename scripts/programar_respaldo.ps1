[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PythonExe,
    [Parameter(Mandatory)][string]$Config,
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')][string]$Hora = '20:00',
    [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$Nombre = 'SistemaRespaldoAcademico',
    [switch]$Instalar
)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
$configPath = (Resolve-Path -LiteralPath $Config -ErrorAction Stop).Path
$script = Join-Path $project 'src\backup.py'
foreach ($path in @($python, $configPath, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or $path.Contains('"')) { throw "Ruta invalida: $path" }
}
# Comando no interactivo. Validar la configuracion sin crear un respaldo.
& $python -c 'import sys; sys.path.insert(0, sys.argv[1]); from src.backup import configuration; configuration(sys.argv[2])' $project $configPath
if ($LASTEXITCODE -ne 0) {
    throw 'No se pudo validar la configuracion con el ejecutable de Python indicado.'
}
$arguments = '"{0}" --config "{1}" respaldo' -f $script, $configPath
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.Add([timespan]::Parse($Hora)))
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Respaldo completo versionado del proyecto academico.'
$output = Join-Path $project 'logs'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$xmlPath = Join-Path $output ($Nombre + '.xml')
$task | Export-ScheduledTask | Set-Content -LiteralPath $xmlPath -Encoding Unicode
Write-Host "Definicion exportada: $xmlPath"
Write-Host "Ejecutable: $python"
Write-Host "Argumentos: $arguments"
Write-Host "Diariamente a las $Hora, con la sesion del usuario iniciada."
if ($Instalar -and $PSCmdlet.ShouldProcess($Nombre, 'Registrar tarea diaria')) {
    # Sin -Force: no reemplazar una tarea que ya exista.
    Register-ScheduledTask -TaskName $Nombre -InputObject $task -ErrorAction Stop | Out-Null
    Write-Host "Tarea instalada: $Nombre"
} elseif (-not $Instalar) {
    Write-Host 'Para registrar la tarea, ejecuta de nuevo con -Instalar.'
}
