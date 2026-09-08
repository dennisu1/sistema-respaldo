# Prueba real del Programador de tareas. Retira solo la tarea temporal que crea.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$PythonExe)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$id = [guid]::NewGuid().ToString('N')
$taskName = 'SistemaRespaldoPrueba_' + $id
$run = Join-Path $project ('demo_runs\automatizacion_' + $id)
$data = Join-Path $run 'datos'
New-Item -ItemType Directory -Path $data -Force | Out-Null
Set-Content -LiteralPath (Join-Path $data 'prueba.txt') -Value 'Respaldo ejecutado por Windows Task Scheduler.' -Encoding UTF8
$config = Join-Path $run 'config.json'
@{ source = 'datos'; backup_root = 'backups'; log_file = 'operaciones.jsonl' } |
    ConvertTo-Json | Set-Content -LiteralPath $config -Encoding UTF8
$installed = $false
try {
    & (Join-Path $PSScriptRoot 'programar_respaldo.ps1') -PythonExe $PythonExe -Config $config -Nombre $taskName -Instalar
    $installed = $true
    $previousRun = (Get-ScheduledTaskInfo -TaskName $taskName).LastRunTime
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        $task = Get-ScheduledTask -TaskName $taskName
        $finished = ($info.LastRunTime -ne $previousRun) -and ($task.State -ne 'Running')
    } while (-not $finished -and (Get-Date) -lt $deadline)
    if (-not $finished -or $info.LastTaskResult -ne 0) {
        throw "La tarea no termino correctamente. Resultado: $($info.LastTaskResult)"
    }
    $versions = @(Get-ChildItem -LiteralPath (Join-Path $run 'backups') -Directory -Filter 'Backup_*')
    if ($versions.Count -ne 1) { throw 'Se esperaba exactamente una version creada por la tarea.' }
    & $PythonExe (Join-Path $project 'src\backup.py') --config $config verificar --backup $versions[0].FullName
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo verificar el respaldo programado.' }
    $original = (Get-FileHash -LiteralPath (Join-Path $data 'prueba.txt') -Algorithm SHA256).Hash
    $copied = (Get-FileHash -LiteralPath (Join-Path $versions[0].FullName 'datos\prueba.txt') -Algorithm SHA256).Hash
    if ($original -ne $copied) { throw 'Los hashes no coinciden.' }
    $report = [ordered]@{ tool = 'Programador de tareas de Windows'; created_at = (Get-Date).ToUniversalTime().ToString('o');
        last_task_result = $info.LastTaskResult; versions_created = $versions.Count;
        sha256_match = ($original -eq $copied); sha256 = $original.ToLowerInvariant(); temporary_task_removed = $false }
} finally {
    if ($installed) {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    }
}
$report.temporary_task_removed = $true
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'evidencia.json') -Encoding UTF8
Write-Host "Automatizacion comprobada; tarea temporal retirada. Evidencia: $run"
