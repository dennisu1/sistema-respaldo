# Sistema de Respaldo y Recuperación

Proyecto académico para la materia de Seguridad de la Información. El programa crea copias de una carpeta y permite recuperar todos sus archivos, una subcarpeta o un archivo individual.

## Uso

Necesitas **Python 3.10 o posterior**. No hay que instalar bibliotecas adicionales.

Desde la carpeta del proyecto:

```powershell
python src/backup.py
```

En Windows también puedes usar `py -3` en lugar de `python`, o indicar la ruta de tu ejecutable.

```text
1. Crear respaldo
2. Recuperación total
3. Recuperar una carpeta
4. Recuperar un archivo
5. Ver respaldos
6. Salir
```

El programa usa `test_data/` como origen, guarda las versiones en `backups/` y las recuperaciones en `recuperados/`. Para trabajar con otras carpetas:

```powershell
python src/backup.py --origen "C:/Proyecto/Datos" --backups "D:/Backups/Proyecto" --recuperados "C:/Proyecto/Recuperados"
```

Cada respaldo lleva la fecha y hora en su nombre. Al recuperar, eliges una versión y, si corresponde, una carpeta o archivo de la lista. **Cada recuperación crea una carpeta nueva**, conserva la estructura de los archivos y no reemplaza los originales.

```text
backups/Backup_<fecha>/datos/documentos/tarea.txt
                       ↓ recuperación individual
recuperados/Recuperacion_individual_<fecha>/documentos/tarea.txt
```

La copia se prepara en una carpeta temporal y se publica al terminar. Si falla, se informa el error. Origen, almacén y destino deben estar separados; el programa rechaza enlaces simbólicos y junctions.

## Demostración del programa

1. Ejecuta el menú y crea un respaldo de `test_data`.
2. Modifica `test_data/documentos/tarea.txt` y crea otro respaldo para mostrar dos versiones.
3. Renombra `test_data` como `test_data_no_disponible` para simular la pérdida del origen.
4. Selecciona el primer respaldo y prueba las tres recuperaciones.
5. Abre las carpetas creadas en `recuperados`: la total tendrá todo, la parcial solo la carpeta elegida y la individual solo el archivo elegido, con su contenido anterior.
6. Al terminar, vuelve a nombrar la carpeta de prueba como `test_data`.

Usa únicamente archivos de prueba. El script respalda contenido de archivos; no crea una imagen de Windows. Cierra los archivos antes de copiarlos. Para protección frente a una avería física, guarda el respaldo en otro dispositivo.

## Automatización con Windows

El siguiente comando crea un respaldo y termina, sin abrir el menú:

```powershell
python src/backup.py --automatico --origen "C:/Proyecto/Datos" --backups "D:/Backups/Proyecto"
```

En el **Programador de tareas**, selecciona **Crear tarea básica** y configura:

| Campo | Valor de ejemplo |
|---|---|
| Nombre | Respaldo del proyecto |
| Desencadenador | Diariamente a las 20:00 |
| Acción | Iniciar un programa |
| Programa | Ruta completa de `python.exe` |
| Argumentos | `"C:\ruta\sistema-respaldo\src\backup.py" --automatico --origen "C:\Proyecto\Datos" --backups "D:\Backups\Proyecto"` |

Sustituye las rutas por las de tu equipo. Puedes encontrar Python con `python -c "import sys; print(sys.executable)"`. Usa la opción de ejecutar con tu sesión iniciada. Después, pulsa **Ejecutar** sobre la tarea y comprueba que apareció un respaldo nuevo y que **Resultado de la última ejecución** sea `0`. Si el programa falla, devuelve `1`.

Si habías creado una tarea con la versión anterior del proyecto, actualiza su acción al comando con `--automatico` mostrado arriba.

## Parte de la tarea con una herramienta existente

La [práctica con Robocopy de Windows](docs/practica_windows.md) explica el respaldo y las tres recuperaciones usando una herramienta existente. Es una demostración separada del programa Python.

## Organización y pruebas

```text
src/backup.py              Programa completo, con funciones en español
test_data/                 Archivos de prueba
tests/test_backup.py      Pruebas de las funciones principales
docs/practica_windows.md  Parte de la práctica con Robocopy
```

Para comprobar el funcionamiento:

```powershell
python -m unittest discover -s tests -v
```

Las versiones son copias completas, sin compresión, cifrado ni verificación permanente de hashes. Los respaldos, las recuperaciones y los archivos temporales no se suben a Git.
