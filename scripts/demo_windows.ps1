# Compatible con Windows PowerShell 5.1 y PowerShell 7. Datos ficticios independientes.
[CmdletBinding()]
param([string]$Workspace)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if (-not $Workspace) { $Workspace = Join-Path $PSScriptRoot '..\demo_runs' }

function Assert-Child([string]$Path, [string]$Root) {
    $full = [IO.Path]::GetFullPath($Path)
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "La ruta no esta dentro de la demostracion: $full"
    }
}

function Get-Hashes([string]$Root) {
    $map = @{}
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($prefix.Length).Replace('\', '/')
        $map[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $map
}

function Invoke-Robocopy([string]$Source, [string]$Target, [string]$Log, [string]$File = '') {
    $arguments = @($Source, $Target)
    if ($File) { $arguments += $File } else { $arguments += '/E' }
    $arguments += @('/COPY:DAT', '/DCOPY:T', '/R:1', '/W:1', '/XJ', '/NP', "/LOG:$Log")
    & robocopy.exe @arguments | Out-Host
    $code = $LASTEXITCODE
    if ($code -ge 8) { throw "Robocopy fallo (codigo $code). Revisa $Log" }
    return $code
}

Get-Command robocopy.exe -ErrorAction Stop | Out-Null
$runId = 'windows_' + (Get-Date -Format 'yyyyMMdd_HHmmss_') + [guid]::NewGuid().ToString('N').Substring(0, 8)
$run = [IO.Path]::GetFullPath((Join-Path $Workspace $runId))
New-Item -ItemType Directory -Path $run | Out-Null
$source = Join-Path $run 'datos'
$backup = Join-Path $run 'respaldo_robocopy'
foreach ($folder in @('documentos', 'fotos', 'proyectos', 'vacia')) {
    New-Item -ItemType Directory -Path (Join-Path $source $folder) -Force | Out-Null
}
Set-Content -LiteralPath (Join-Path $source 'documentos\tarea.txt') -Value 'Version original de la tarea.' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $source 'documentos\notas.txt') -Value 'Notas para recuperacion parcial.' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $source 'proyectos\hola.py') -Value 'print("Recuperado")' -Encoding UTF8
[IO.File]::WriteAllBytes((Join-Path $source 'fotos\muestra.bin'), [byte[]](0..255))
$expected = Get-Hashes $source
$backupCode = Invoke-Robocopy $source $backup (Join-Path $run '01-respaldo.log')
$saved = Get-Hashes $backup
if ($saved.Count -ne $expected.Count) { throw 'Cantidad incorrecta en el respaldo.' }
foreach ($key in $expected.Keys) {
    if ($saved[$key] -ne $expected[$key]) { throw "Hash incorrecto en respaldo: $key" }
}
Set-Content -LiteralPath (Join-Path $source 'documentos\tarea.txt') -Value 'Version modificada despues del respaldo.' -Encoding UTF8
$unavailable = Join-Path $run 'datos_fuera_de_servicio'
# Verificacion absoluta antes del unico movimiento: ambas rutas pertenecen a esta ejecucion.
Assert-Child $source $run
Assert-Child $unavailable $run
Move-Item -LiteralPath $source -Destination $unavailable

$results = @()
foreach ($mode in @('total', 'parcial', 'individual')) {
    $destination = Join-Path $run "recuperacion_$mode"
    $log = Join-Path $run "02-recuperacion-$mode.log"
    $selected = @{}
    if ($mode -eq 'total') {
        $code = Invoke-Robocopy $backup $destination $log
        $selected = $expected
        if (-not (Test-Path -LiteralPath (Join-Path $destination 'vacia') -PathType Container)) {
            throw 'No se recupero la carpeta vacia.'
        }
    } elseif ($mode -eq 'parcial') {
        $code = Invoke-Robocopy (Join-Path $backup 'documentos') (Join-Path $destination 'documentos') $log
        foreach ($key in $expected.Keys) { if ($key.StartsWith('documentos/')) { $selected[$key] = $expected[$key] } }
    } else {
        $code = Invoke-Robocopy (Join-Path $backup 'documentos') (Join-Path $destination 'documentos') $log 'tarea.txt'
        $selected['documentos/tarea.txt'] = $expected['documentos/tarea.txt']
    }
    $actual = Get-Hashes $destination
    if ($actual.Count -ne $selected.Count) { throw "Cantidad incorrecta en recuperacion $mode" }
    foreach ($key in $selected.Keys) {
        if ($actual[$key] -ne $selected[$key]) { throw "Hash incorrecto en $mode : $key" }
    }
    $results += [pscustomobject]@{ mode = $mode; files = $actual.Count; sha256_match = $true;
        robocopy_exit_code = $code; expected = $selected; actual = $actual }
}
$report = [ordered]@{ tool = 'Robocopy de Windows'; created_at = (Get-Date).ToUniversalTime().ToString('o');
    powershell = $PSVersionTable.PSVersion.ToString(); backup_exit_code = $backupCode;
    empty_directory_restored = $true; results = $results }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $run 'evidencia.json') -Encoding UTF8
$lines = @('# Evidencia ejecutada: Robocopy', '', '| Recuperacion | Archivos | SHA-256 | Codigo Robocopy |', '|---|---:|---|---:|')
foreach ($row in $results) { $lines += "| $($row.mode) | $($row.files) | Coincide | $($row.robocopy_exit_code) |" }
$lines += @('', 'Origen renombrado despues del respaldo. Carpeta vacia recuperada.', 'Hashes completos en evidencia.json; comandos y resultados en los archivos .log.')
$lines | Set-Content -LiteralPath (Join-Path $run 'evidencia.md') -Encoding UTF8
Write-Host "Demostracion aprobada. Evidencias: $run"
exit 0
