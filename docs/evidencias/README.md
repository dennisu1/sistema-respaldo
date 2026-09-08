# Resultados ejecutados

Validación realizada el **7 de septiembre de 2026** (hora de Ciudad de México; los JSON guardan UTC del 8 de septiembre) en Windows, con Python **3.12.14** y Windows PowerShell **5.1**.

| Sistema | Total | Parcial | Individual | Integridad |
|---|---:|---:|---:|---|
| Robocopy de Windows | 4 archivos | 2 archivos | 1 archivo | Todos los hashes coinciden |
| Programa Python | 6 archivos | 3 archivos | 1 archivo | Todos los hashes coinciden |

En ambos casos se creó un respaldo antes de modificar y renombrar el origen. La recuperación reconstruyó la versión respaldada. También se recuperaron carpetas vacías. Python creó dos versiones y recuperó la primera, incluyendo un nombre con acentos y un archivo binario.

- [Evidencia Robocopy](windows.json): SHA-256 esperado/obtenido por archivo y códigos de salida reales.
- [Evidencia Python](python.json): dos versiones, selección recuperada y SHA-256 por archivo.
- [Evidencia de automatización](automatizacion.json): una tarea temporal de Windows ejecutó el comando `respaldo`, produjo una versión íntegra y terminó con `LastTaskResult = 0`. La tarea temporal fue retirada.

Los JSON se copiaron de las demostraciones ejecutadas; contienen únicamente datos ficticios. No son capturas de pantalla ni evidencia de Windows Backup/Historial de archivos.

## Pruebas del programa

Resultado real: **33 pruebas, todas aprobadas, sin omisiones**, ejecutadas con:

```powershell
python -m unittest discover -s tests -v
```

Cubren recuperación total/parcial/individual, versiones independientes, carpetas vacías, binarios, Unicode, sobrescritura explícita, conservación de archivos adicionales, corrupción, rutas manipuladas, enlaces/junctions, fallos de copia y espacio, cambios del origen, configuración, bitácora y uso desde otro directorio.

El flujo de GitHub Actions define ejecuciones adicionales en Windows y Linux con Python 3.10 y 3.12. Este resultado local no sustituye los resultados que GitHub publique para cada ejecución remota.

## Reproducir

```powershell
python scripts/demo.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/demo_windows.ps1
$pythonExe = (python -c "import sys; print(sys.executable)")
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/probar_automatizacion.ps1 -PythonExe "$pythonExe"
```

La tercera prueba requiere acceso al Programador de tareas y sesión iniciada. Crea y retira una tarea temporal de nombre único; conserva sus datos de prueba en `demo_runs/`. La prueba dispara la tarea en el momento, por lo que acredita la acción programada sin esperar al siguiente horario diario.

Las siguientes ejecuciones generarán nuevas carpetas, fechas e identificadores. Los archivos bajo `demo_runs/` y los logs con rutas locales están excluidos de Git. Para la exposición, vuelve a ejecutar las demostraciones y toma tus propias capturas.
