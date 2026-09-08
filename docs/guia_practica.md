# Guía para presentar la práctica

## Introducción

“Seleccionamos Robocopy de Windows para demostrar un respaldo básico con una herramienta existente. Después desarrollamos un programa Python que crea versiones y permite recuperación total, de carpeta e individual. Lo automatizamos mediante el Programador de tareas.”

Alcance: archivos de una carpeta de prueba. Recuperación total significa recuperar esa carpeta completa, no reinstalar Windows. El texto del profesor permite seleccionar una herramienta; si exige específicamente la aplicación Windows Backup, esa demostración debe realizarse aparte.

## Parte 1: sistema existente

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/demo_windows.ps1
```

El script deja en `demo_runs/windows_<fecha>_<id>/` los originales fuera de servicio, una copia con Robocopy, tres destinos recuperados, logs y hashes. Usa exclusivamente datos que crea en esa ejecución.

| Evidencia | Qué mostrar |
|---|---|
| Antes | Cuatro archivos ficticios y una carpeta vacía |
| Respaldo | `respaldo_robocopy/` y `01-respaldo.log` |
| Incidente | `datos` se modifica y renombra como `datos_fuera_de_servicio` |
| Total | `recuperacion_total/`: 4 archivos y carpeta vacía |
| Parcial | `recuperacion_parcial/documentos/`: 2 archivos |
| Individual | `recuperacion_individual/documentos/tarea.txt`: 1 archivo |
| Comprobación | `evidencia.json`: hashes esperados y obtenidos coincidentes |

Los comandos esenciales equivalen a los siguientes; usa rutas de tu práctica:

```powershell
robocopy "C:\Proyecto\Datos" "D:\Backups\Proyecto\Version1" /E /COPY:DAT /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Fallo de respaldo" }

robocopy "D:\Backups\Proyecto\Version1" "C:\Proyecto\RecuperadoTotal" /E /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Fallo de recuperacion total" }

robocopy "D:\Backups\Proyecto\Version1\documentos" "C:\Proyecto\RecuperadoParcial\documentos" /E /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Fallo de recuperacion parcial" }

robocopy "D:\Backups\Proyecto\Version1\documentos" "C:\Proyecto\RecuperadoIndividual\documentos" tarea.txt /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) { throw "Fallo de recuperacion individual" }
```

`/E` incluye subcarpetas vacías, `/R:1 /W:1` limita reintentos y `/XJ` excluye junctions. Los códigos menores que 8 no representan un fallo de copia; además comprobamos hashes. No se usa `/MIR` ni `/PURGE`, que pueden borrar contenido del destino. [Referencia de Robocopy, Microsoft](https://learn.microsoft.com/es-es/windows-server/administration/windows-commands/robocopy).

Sin unidad D:, la demostración automática funciona con carpetas separadas en la unidad actual. Explica que esto demuestra recuperación lógica, pero no tolera una avería de esa unidad.

### Alternativa gráfica

**Historial de archivos** permite seleccionar un disco externo o ubicación de red, incluir la carpeta de prueba en una biblioteca y recuperar versiones anteriores. La aplicación **Windows Backup** utiliza una cuenta Microsoft y OneDrive para determinadas carpetas y ajustes. Consulta [Microsoft Support](https://support.microsoft.com/en-us/windows/experience/backup-recovery/backup-restore-and-recovery-in-windows) para sus requisitos y procedimientos.

La evidencia de este proyecto corresponde a Robocopy; no se afirma haber ejecutado Historial de archivos o Windows Backup.

## Parte 2: programa desarrollado

```powershell
python scripts/demo.py
```

Muestra `demo_runs/python_<fecha>_<id>/`:

1. Dos versiones independientes en `backups/`; `tarea.txt` cambió entre ellas.
2. El origen dejó de estar disponible y quedó renombrado.
3. La recuperación total reconstruye `datos/` desde la primera versión: 6 archivos y una carpeta vacía.
4. La parcial recupera únicamente `documentos/`: 3 archivos.
5. La individual recupera `documentos/tarea.txt`: 1 archivo con su contenido original.
6. `evidencia.json` compara hashes y `operaciones.jsonl` registra lo ejecutado.

Después abre `python src/backup.py` para enseñar el menú. Crea un respaldo, elige una versión y recupera a una carpeta nueva. Muestra `manifest.json` para explicar fecha, ruta, tamaño y SHA-256.

Para demostrar corrupción, crea un respaldo adicional de prueba, modifica un archivo **dentro de esa copia descartable** y ejecuta `verificar --backup <ruta>`. El programa debe devolver error. Conserva una versión sana para el resto de la exposición.

## Parte 3: automatización

Sigue la instalación del README usando `config.json` y tu ejecutable real de Python. Muestra:

- Desencadenador diario a las 20:00 o a la hora elegida.
- Acción `src/backup.py --config <ruta> respaldo`.
- Usuario actual con sesión iniciada; sin entradas del menú.
- Ejecución manual de la tarea para no esperar a la hora programada.
- Nueva versión, registro `status: ok` y resultado `0` en la información de la tarea.

La definición se puede exportar sin instalarla. Una tarea permanente para tus datos se registra con `-Instalar`; no uses rutas de la computadora de otro integrante.

## Cierre

“El respaldo crea una copia en un momento determinado. La recuperación selecciona cuánto restaurar. Comprobamos que los bytes recuperados coinciden con los originales mediante SHA-256. La automatización invoca nuestro programa sin intervención, y la bitácora permite revisar el resultado. Para uso real necesitamos copias en otro dispositivo y medidas adicionales según los datos.”

## Entrega

- Código y versión de Python utilizada.
- Evidencias ejecutadas de las tres variantes para Robocopy y Python.
- Capturas propias del menú, carpetas y tarea programada durante la exposición.
- Explicación del diseño, integridad y límites.
- Resultado de `python -m unittest discover -s tests -v`.

Los JSON del proyecto son registros de comprobación. Las capturas del escritorio se toman al hacer la demostración; no se presentan capturas simuladas como ejecuciones reales.
