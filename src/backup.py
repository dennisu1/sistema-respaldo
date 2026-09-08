"""Proyecto académico: respaldar una carpeta y recuperar sus archivos."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
import tempfile


# Rutas predeterminadas. También se pueden cambiar al ejecutar el programa.
PROYECTO = Path(__file__).resolve().parents[1]
CARPETA_ORIGEN = PROYECTO / "test_data"
CARPETA_BACKUPS = PROYECTO / "backups"
CARPETA_RECUPERADOS = PROYECTO / "recuperados"


def validar_ruta(ruta):
    """Evita seguir enlaces o accesos a otras carpetas mediante junctions."""
    ruta = Path(os.path.abspath(Path(ruta).expanduser()))
    for parte in [*reversed(ruta.parents), ruta]:
        if parte.is_symlink():
            raise ValueError(f"No se admiten enlaces: {parte}")
        if parte.exists() and getattr(parte.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError(f"No se admiten puntos de reanálisis: {parte}")
    return ruta


def comprobar_separacion(primera, segunda):
    if primera == segunda or primera in segunda.parents or segunda in primera.parents:
        raise ValueError("Las carpetas deben estar separadas, sin estar una dentro de otra.")


def obtener_contenido(carpeta):
    """Lista archivos y subcarpetas, incluyendo las que están vacías."""
    elementos = []
    for elemento in sorted(carpeta.iterdir()):
        validar_ruta(elemento)
        elementos.append(elemento)
        if elemento.is_dir():
            elementos.extend(obtener_contenido(elemento))
        elif not elemento.is_file():
            raise ValueError(f"No es un archivo regular: {elemento}")
    return elementos


def copiar_a_carpeta_nueva(origen, destino, ruta_relativa=Path(".")):
    """La carpeta final aparece solo cuando termina la copia."""
    if destino.exists():
        raise ValueError(f"El destino ya existe: {destino}")
    if origen.is_dir():
        obtener_contenido(origen)  # Comprobar enlaces antes de copiar.
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".temporal-", dir=destino.parent) as temporal:
        copia = Path(temporal) / "copia"
        objetivo = copia / ruta_relativa
        if origen.is_dir():
            shutil.copytree(origen, objetivo)
        else:
            objetivo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, objetivo)
        copia.rename(destino)
    return destino


def crear_respaldo(origen, carpeta_backups):
    origen = validar_ruta(origen)
    carpeta_backups = validar_ruta(carpeta_backups)
    if not origen.is_dir():
        raise ValueError(f"La carpeta de origen no existe: {origen}")
    comprobar_separacion(origen, carpeta_backups)
    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    destino = carpeta_backups / f"Backup_{fecha}"
    return copiar_a_carpeta_nueva(origen, destino, Path("datos"))


def obtener_respaldos(carpeta_backups):
    carpeta_backups = validar_ruta(carpeta_backups)
    if not carpeta_backups.exists():
        return []
    return sorted([carpeta.name for carpeta in carpeta_backups.iterdir()
                   if carpeta.name.startswith("Backup_") and (carpeta / "datos").is_dir()],
                  reverse=True)


def recuperar(respaldo, carpeta_recuperados, modo="total", seleccion=None):
    respaldo = validar_ruta(respaldo)
    datos = validar_ruta(respaldo / "datos")
    carpeta_recuperados = validar_ruta(carpeta_recuperados)
    if not datos.is_dir():
        raise ValueError("El respaldo no contiene una carpeta de datos.")
    comprobar_separacion(respaldo.parent, carpeta_recuperados)
    if modo not in ("total", "parcial", "individual"):
        raise ValueError("Tipo de recuperación inválido.")

    relativa = Path(".")
    origen = datos
    if modo != "total":
        if not seleccion:
            raise ValueError("Selecciona una carpeta o un archivo.")
        relativa = Path(seleccion)
        if relativa.is_absolute() or relativa.drive or ".." in relativa.parts or relativa == Path("."):
            raise ValueError("La selección debe estar dentro del respaldo.")
        origen = validar_ruta(datos / relativa)
        if datos not in origen.parents:
            raise ValueError("La selección debe estar dentro del respaldo.")
        if modo == "parcial" and not origen.is_dir():
            raise ValueError("La selección no es una carpeta.")
        if modo == "individual" and not origen.is_file():
            raise ValueError("La selección no es un archivo.")
    elif seleccion is not None:
        raise ValueError("La recuperación total no necesita una selección.")

    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    destino = carpeta_recuperados / f"Recuperacion_{modo}_{fecha}"
    return copiar_a_carpeta_nueva(origen, destino, relativa)


def seleccionar(opciones, titulo):
    if not opciones:
        print("No hay elementos disponibles.")
        return None
    print(f"\n{titulo}")
    for numero, opcion in enumerate(opciones, 1):
        print(f"{numero}. {opcion}")
    while True:
        respuesta = input("Número (0 para volver): ").strip()
        if respuesta == "0":
            return None
        if respuesta.isdecimal() and 1 <= int(respuesta) <= len(opciones):
            return opciones[int(respuesta) - 1]
        print("Escribe un número de la lista.")


def menu(origen, backups, recuperados):
    while True:
        print("\n=== SISTEMA DE RESPALDO Y RECUPERACIÓN ===")
        print(f"Origen: {origen}\nRespaldos: {backups}\nRecuperaciones: {recuperados}")
        print("\n1. Crear respaldo\n2. Recuperación total\n3. Recuperar una carpeta")
        print("4. Recuperar un archivo\n5. Ver respaldos\n6. Salir")
        opcion = input("Opción: ").strip()
        try:
            if opcion == "6":
                return
            if opcion == "1":
                print("Respaldo creado en:", crear_respaldo(origen, backups))
            elif opcion == "5":
                versiones = obtener_respaldos(backups)
                print("\n".join(versiones) if versiones else "No hay respaldos disponibles.")
            elif opcion in ("2", "3", "4"):
                nombre = seleccionar(obtener_respaldos(backups), "Respaldos disponibles")
                if nombre is None:
                    continue
                respaldo = backups / nombre
                modo = {"2": "total", "3": "parcial", "4": "individual"}[opcion]
                elegida = None
                if modo != "total":
                    datos = validar_ruta(respaldo / "datos")
                    contenido = obtener_contenido(datos)
                    opciones = [ruta.relative_to(datos) for ruta in contenido
                                if (ruta.is_dir() if modo == "parcial" else ruta.is_file())]
                    elegida = seleccionar(opciones, "Contenido del respaldo")
                    if elegida is None:
                        continue
                print("Recuperación guardada en:", recuperar(respaldo, recuperados, modo, elegida))
            else:
                print("Elige una opción entre 1 y 6.")
        except (OSError, ValueError) as error:
            print(f"No se pudo completar la operación: {error}")


def main():
    argumentos = argparse.ArgumentParser(description="Respaldo básico de una carpeta")
    argumentos.add_argument("--origen", type=Path, default=CARPETA_ORIGEN)
    argumentos.add_argument("--backups", type=Path, default=CARPETA_BACKUPS)
    argumentos.add_argument("--recuperados", type=Path, default=CARPETA_RECUPERADOS)
    argumentos.add_argument("--automatico", action="store_true", help="Crear un respaldo sin abrir el menú")
    opciones = argumentos.parse_args()
    try:
        origen = validar_ruta(opciones.origen)
        backups = validar_ruta(opciones.backups)
        recuperados = validar_ruta(opciones.recuperados)
        if opciones.automatico:
            print("Respaldo creado en:", crear_respaldo(origen, backups))
        else:
            menu(origen, backups, recuperados)
        return 0
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nPrograma finalizado.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
