# Práctica con Robocopy de Windows

Esta es la parte de la tarea que usa una herramienta existente. Robocopy viene con Windows y permite copiar una carpeta completa o seleccionar archivos. No es la aplicación Windows Backup; se eligió como herramienta para respaldo básico.

## 1. Preparar los archivos

Desde la raíz del repositorio, abre PowerShell. Estos comandos crean una carpeta nueva para la práctica y copian los archivos ficticios del proyecto:

```powershell
$practica = Join-Path $PWD ("demo_runs/windows_" + (Get-Date -Format "yyyyMMdd_HHmmss_fffffff"))
New-Item -ItemType Directory -Path $practica | Out-Null
Copy-Item -LiteralPath "test_data" -Destination "$practica/Datos" -Recurse
```

## 2. Respaldar

```powershell
robocopy "$practica/Datos" "$practica/Respaldo" /E /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Falló el respaldo" }
$hashOriginal = (Get-FileHash -LiteralPath "$practica/Datos/documentos/tarea.txt").Hash
```

`/E` incluye subcarpetas vacías, `/R:1 /W:1` limita reintentos y `/XJ` excluye junctions. Un código de salida menor que 8 no representa un fallo de copia. [Documentación de Microsoft](https://learn.microsoft.com/es-es/windows-server/administration/windows-commands/robocopy).

## 3. Simular la pérdida del origen

Renombra únicamente la carpeta ficticia creada en esta ejecución:

```powershell
Rename-Item -LiteralPath "$practica/Datos" -NewName "Datos_no_disponibles"
```

## 4. Recuperar las tres variantes

```powershell
# Total: recuperar todo el respaldo.
robocopy "$practica/Respaldo" "$practica/Total" /E /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Falló la recuperación total" }

# Parcial: recuperar la carpeta documentos.
robocopy "$practica/Respaldo/documentos" "$practica/Parcial/documentos" /E /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Falló la recuperación parcial" }

# Individual: recuperar únicamente tarea.txt.
robocopy "$practica/Respaldo/documentos" "$practica/Individual/documentos" tarea.txt /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Falló la recuperación individual" }
```

## 5. Comprobar y presentar

Abre `$practica`: `Total` debe tener los cuatro archivos; `Parcial`, los dos de documentos; e `Individual`, solamente tarea.txt. También puedes comparar el hash del archivo recuperado:

```powershell
$hashRecuperado = (Get-FileHash -LiteralPath "$practica/Individual/documentos/tarea.txt").Hash
$hashOriginal -eq $hashRecuperado  # Debe mostrar True.
```

Toma capturas del respaldo, del origen renombrado, de las tres carpetas recuperadas y de la comparación. Aquí se usan carpetas del mismo disco para facilitar la práctica; una copia en otro dispositivo es necesaria para protegerse de una avería física.
