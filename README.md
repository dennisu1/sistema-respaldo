# Sistema de Respaldo y Recuperación

Proyecto académico de **Seguridad de la Información**. Incluye una práctica con una herramienta existente de Windows y un programa propio en Python con recuperación y automatización.

| Requisito | Entrega |
|---|---|
| Usar un sistema existente | Robocopy de Windows, con demostración independiente |
| Recuperación total, parcial e individual | Ambas demostraciones recuperan las tres variantes y comparan SHA-256 |
| Desarrollar respaldo y recuperación | Programa Python con menú y comandos |
| Automatizar | Script para una tarea diaria de Windows, sin interacción del programa |

**Total, parcial e individual describen qué se recupera.** Cada versión es un respaldo completo de la carpeta seleccionada. No se implementan respaldos incrementales/diferenciales ni una imagen del sistema operativo.

## Empezar

Necesitas **Python 3.10 o posterior**. El programa usa exclusivamente la biblioteca estándar: no requiere `pip install`. Para la práctica nativa y el programador necesitas Windows y PowerShell 5.1 o posterior.

Desde la raíz del repositorio:

```powershell
python --version
python src/backup.py
```

Si tu instalación usa el lanzador de Windows, sustituye `python` por `py -3`. También puedes invocar un ejecutable concreto: `& "C:\ruta\python.exe" src/backup.py`.

```text
================================
   SISTEMA DE RESPALDO
================================
1. Crear respaldo
2. Recuperar respaldo completo
3. Recuperar una carpeta
4. Recuperar un archivo
5. Ver respaldos disponibles
6. Verificar respaldo
7. Salir
```

La opción 1 propone `test_data` y `backups`. Las recuperaciones proponen `recuperados`. El menú muestra las versiones y rutas disponibles. Para reemplazar archivos existentes se debe escribir `SI`; de manera predeterminada un conflicto detiene la recuperación antes de copiar.

## Demostrar las dos partes

```powershell
# Parte 1: herramienta existente de Windows; no llama al programa Python.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/demo_windows.ps1

# Parte 2: programa propio; crea dos versiones y recupera la primera.
python scripts/demo.py

# Pruebas automatizadas
python -m unittest discover -s tests -v
```

Cada demostración crea una carpeta nueva dentro de `demo_runs/`, genera datos ficticios, respalda, modifica el origen y lo renombra para simular su indisponibilidad. Luego ejecuta las tres recuperaciones y genera `evidencia.md`, `evidencia.json` y bitácoras. **No borra originales del usuario ni modifica `test_data`.** El `Bypass` del ejemplo solo afecta ese proceso de PowerShell; no cambia la política del equipo.

Consulta la [guía de exposición](docs/guia_practica.md), el [diseño del programa](docs/diseno.md) y los [resultados ejecutados](docs/evidencias/README.md).

## Comandos

```powershell
python src/backup.py respaldo --origen "test_data" --destino "backups"
python src/backup.py listar --destino "backups"

# Obtener una versión existente en PowerShell.
$version = (Get-ChildItem -LiteralPath "backups" -Directory -Filter "Backup_*" |
    Sort-Object Name -Descending | Select-Object -First 1).FullName

python src/backup.py contenido --backup "$version"
python src/backup.py verificar --backup "$version"

# Total: todos los archivos y carpetas.
python src/backup.py recuperar --backup "$version" --destino "recuperados/total"

# Parcial: documentos y su contenido; conserva el prefijo documentos/.
python src/backup.py recuperar --backup "$version" --destino "recuperados/parcial" --modo parcial --ruta "documentos"

# Individual: únicamente documentos/tarea.txt.
python src/backup.py recuperar --backup "$version" --destino "recuperados/individual" --modo individual --ruta "documentos/tarea.txt"
```

`--destino` siempre es la **raíz de recuperación**, incluso en modo individual. Para restaurar sobre el origen, usa esa carpeta como destino y añade `--sobrescribir` solo si quieres reemplazar los archivos coincidentes. Los archivos adicionales se conservan: recuperación total no significa sincronización con borrado.

Las opciones globales `--config` y `--json` van **antes** del comando:

```powershell
Copy-Item -LiteralPath config.example.json -Destination config.json
python src/backup.py --config config.json --json respaldo
```

Edita `config.json` para tus carpetas. Las rutas relativas de configuración parten de la carpeta del JSON; las rutas de los comandos parten del directorio actual. Sin configuración, los valores predeterminados parten de la raíz del proyecto. La bitácora debe estar fuera del origen, los respaldos y la recuperación.

```json
{
  "source": "C:/Proyecto/Datos",
  "backup_root": "D:/Backups/Proyecto",
  "log_file": "C:/Proyecto/Logs/operaciones.jsonl"
}
```

Cada operación genera un registro JSON con fecha UTC, resultado y error si corresponde. Salidas del proceso: `0` éxito, `1` error operativo, `2` argumentos inválidos y `130` interrupción. Los errores de configuración o apertura de bitácora se muestran en pantalla sin poder registrarse en ella.

## Programar un respaldo diario

Primero ejecuta un respaldo manual con tu configuración. Después, desde PowerShell:

```powershell
$pythonExe = (python -c "import sys; print(sys.executable)")

# Exportar una definición revisable a logs/, sin instalarla.
.\scripts\programar_respaldo.ps1 -PythonExe "$pythonExe" -Config config.json -Hora "20:00"

# Instalar la tarea diaria.
.\scripts\programar_respaldo.ps1 -PythonExe "$pythonExe" -Config config.json -Hora "20:00" -Instalar

# Ejecutarla ahora y consultar su resultado.
Start-ScheduledTask -TaskName "SistemaRespaldoAcademico"
Get-ScheduledTaskInfo -TaskName "SistemaRespaldoAcademico"

# Quitar únicamente esta tarea al terminar la práctica.
Unregister-ScheduledTask -TaskName "SistemaRespaldoAcademico" -Confirm:$false
```

La tarea usa el usuario actual, con sesión iniciada y privilegios normales. Guarda rutas absolutas y no abre el menú. Evita ejecuciones superpuestas; Windows puede ejecutar una tarea omitida cuando vuelva a estar disponible. No despierta el equipo y conserva las restricciones predeterminadas de batería. Si mueves el proyecto o cambias Python, vuelve a crearla. El instalador no reemplaza tareas existentes. En equipos con políticas restrictivas puede necesitarse PowerShell con permisos permitidos por el administrador.

## Protección y límites

- Versiones independientes, nombres únicos, carpetas vacías y contenido binario.
- SHA-256 al respaldar, verificar y recuperar; detección de archivos ausentes o modificados.
- Una versión solo se publica después de completar y verificar la copia. Los temporales `.incomplete-*` no se listan como respaldos válidos.
- Rechazo de rutas que escapan del respaldo, nombres no portables, enlaces simbólicos y junctions. Se rechazan origen/almacén anidados y recuperación dentro del almacén.
- El manifiesto **no está firmado**: SHA-256 detecta alteraciones accidentales, pero no acredita autenticidad si alguien altera tanto datos como hashes.
- No hay cifrado, compresión, retención automática, VSS, copia de ACL, flujos NTFS alternativos ni recuperación de Windows instalado. Cierra los archivos antes de respaldar; las bases de datos activas necesitan métodos específicos.
- La recuperación prepara y valida todos los archivos seleccionados antes de escribir. Un fallo de disco o interrupción durante la escritura final puede dejar una recuperación parcial; el respaldo sigue disponible. Evita modificaciones concurrentes en las carpetas involucradas.

Para la práctica bastan carpetas distintas. Para protegerse de una avería física, usa otro dispositivo y conserva una copia desconectada o externa. Cada versión ocupa el tamaño completo de los datos; revisa el espacio y retira versiones antiguas solo cuando ya no las necesites.

## Estructura

```text
src/core.py                     Motor de respaldo, validación y recuperación
src/backup.py                   Menú, comandos y bitácora
scripts/demo.py                 Demostración del programa propio
scripts/demo_windows.ps1        Demostración independiente con Robocopy
scripts/programar_respaldo.ps1  Exportación e instalación de la tarea diaria
scripts/probar_automatizacion.ps1 Prueba real con una tarea temporal
test_data/                     Archivos ficticios versionados
tests/                         Pruebas funcionales, de errores y de seguridad
docs/                          Guía, diseño y evidencias verificadas
config.example.json            Configuración portable
```

`backups/`, `recuperados/`, `demo_runs/`, `logs/` y `config.json` están excluidos de Git para evitar publicar datos respaldados o rutas personales.

## Fuentes

- [Robocopy: opciones y códigos de salida — Microsoft Learn](https://learn.microsoft.com/es-es/windows-server/administration/windows-commands/robocopy).
- [Herramientas de respaldo y recuperación de Windows — Microsoft Support](https://support.microsoft.com/en-us/windows/experience/backup-recovery/backup-restore-and-recovery-in-windows).
- [New-ScheduledTask — Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtask).

La consigna menciona Windows Backup como ejemplo. Aquí se selecciona **Robocopy** como herramienta existente para respaldo básico de archivos; no se presenta como la aplicación Windows Backup, que integra la cuenta Microsoft y OneDrive.
