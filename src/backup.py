"""Interfaz en español: menú para clase y comandos para automatización."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .core import BackupError, checked_path, create_backup, list_backups, now, overlaps, read_manifest, restore_backup, verify_backup
else:
    from core import BackupError, checked_path, create_backup, list_backups, now, overlaps, read_manifest, restore_backup, verify_backup

PROJECT = Path(__file__).resolve().parents[1]


def configuration(filename: str | None) -> dict:
    settings = {"source": str(PROJECT / "test_data"), "backup_root": str(PROJECT / "backups"),
                "log_file": str(PROJECT / "logs" / "operaciones.jsonl")}
    if filename:
        path = Path(filename).expanduser().resolve()
        try:
            supplied = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise BackupError(f"No se puede leer la configuración: {exc}") from exc
        if not isinstance(supplied, dict) or set(supplied) - set(settings):
            raise BackupError("Configuración inválida. Claves: source, backup_root, log_file.")
        for key, value in supplied.items():
            if not isinstance(value, str) or not value.strip():
                raise BackupError(f"Ruta de configuración inválida: {key}")
            value_path = Path(value).expanduser()
            settings[key] = str(value_path if value_path.is_absolute() else path.parent / value_path)
    return settings


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Sistema de respaldo y recuperación de archivos")
    result.add_argument("--config", help="Archivo JSON; las rutas relativas parten de su carpeta")
    result.add_argument("--json", action="store_true", help="Salida JSON para scripts")
    sub = result.add_subparsers(dest="command")
    sub.add_parser("menu", help="Abrir menú interactivo (opción predeterminada)")
    backup = sub.add_parser("respaldo", help="Crear una versión completa de una carpeta")
    backup.add_argument("--origen", help="Carpeta de datos")
    backup.add_argument("--destino", help="Almacén de respaldos")
    listing = sub.add_parser("listar", help="Listar versiones y sus metadatos")
    listing.add_argument("--destino", help="Almacén de respaldos")
    for name, help_text in (("verificar", "Comprobar contenido y SHA-256"),
                            ("contenido", "Ver rutas que se pueden recuperar")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--backup", required=True, help="Carpeta de una versión Backup_...")
    restore = sub.add_parser("recuperar", help="Recuperar conservando la estructura relativa")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--destino", required=True, help="Carpeta raíz a la que recuperar")
    restore.add_argument("--modo", choices=["total", "parcial", "individual"], default="total")
    restore.add_argument("--ruta", help="Ruta dentro del respaldo; ej. documentos/tarea.txt")
    restore.add_argument("--sobrescribir", action="store_true", help="Reemplazar archivos existentes explícitamente")
    return result


def emit(value: dict | list, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, list):
        if not value:
            print("No hay respaldos disponibles.")
        for item in value:
            print(f"{item['id']} | {item.get('files', '?')} archivos | {item['status']}")
            if "error" in item:
                print(f"  {item['error']}")
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def execute(args: argparse.Namespace, settings: dict) -> dict | list:
    if args.command == "respaldo":
        return create_backup(args.origen or settings["source"], args.destino or settings["backup_root"])
    if args.command == "listar":
        return list_backups(args.destino or settings["backup_root"])
    if args.command == "verificar":
        return verify_backup(args.backup)
    if args.command == "contenido":
        _, manifest = read_manifest(args.backup)
        return {"backup": args.backup, "entries": manifest["entries"]}
    return restore_backup(args.backup, args.destino, args.modo, args.ruta, args.sobrescribir)


def audited(args: argparse.Namespace, settings: dict) -> dict | list:
    logfile = checked_path(settings["log_file"])
    if args.command == "respaldo":
        protected = [args.origen or settings["source"], args.destino or settings["backup_root"]]
    elif args.command == "listar":
        protected = [args.destino or settings["backup_root"]]
    else:
        protected = [args.backup]
        if args.command == "recuperar":
            protected.extend([str(checked_path(args.backup).parent), args.destino])
    if any(overlaps(logfile, checked_path(path)) for path in protected):
        raise BackupError("La bitácora debe estar fuera de los datos, respaldos y destino de recuperación.")
    if logfile.exists() and (not logfile.is_file() or logfile.stat().st_nlink > 1):
        raise BackupError("La bitácora debe ser un archivo regular sin enlaces físicos.")
    logfile.parent.mkdir(parents=True, exist_ok=True)
    # Abrir primero permite detectar una bitácora inaccesible antes de respaldar/recuperar.
    with logfile.open("a", encoding="utf-8") as log:
        try:
            result = execute(args, settings)
        except (BackupError, OSError) as exc:
            log.write(json.dumps({"time": now(), "operation": args.command,
                                  "status": "error", "message": str(exc)}, ensure_ascii=False) + "\n")
            raise
        log.write(json.dumps({"time": now(), "operation": args.command, "status": "ok",
                              "result": result}, ensure_ascii=False) + "\n")
        return result


def ask_path(label: str, default: str = "") -> str:
    value = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip().strip('"')
    if not value and not default:
        raise BackupError("La ruta no puede estar vacía.")
    return value or default


def menu(settings: dict) -> int:
    while True:
        print("\n================================\n   SISTEMA DE RESPALDO\n================================")
        print("1. Crear respaldo\n2. Recuperar respaldo completo\n3. Recuperar una carpeta"
              "\n4. Recuperar un archivo\n5. Ver respaldos disponibles\n6. Verificar respaldo\n7. Salir")
        try:
            choice = input("Opción: ").strip()
            if choice == "7":
                return 0
            if choice == "1":
                args = parser().parse_args(["respaldo", "--origen", ask_path("Origen", settings["source"]),
                                           "--destino", ask_path("Almacén", settings["backup_root"])])
            elif choice == "5":
                args = parser().parse_args(["listar", "--destino", ask_path("Almacén", settings["backup_root"])])
            elif choice in ("2", "3", "4", "6"):
                available = list_backups(ask_path("Almacén", settings["backup_root"]))
                if not available:
                    print("No hay respaldos disponibles.")
                    continue
                for index, item in enumerate(available, 1):
                    print(f"{index}. {item['id']} ({item['status']})")
                number = input("Número de versión: ").strip()
                if not number.isdigit() or not 1 <= int(number) <= len(available):
                    raise BackupError("Número de versión inválido.")
                selected = available[int(number) - 1]["backup"]
                if choice == "6":
                    args = parser().parse_args(["verificar", "--backup", selected])
                else:
                    mode = {"2": "total", "3": "parcial", "4": "individual"}[choice]
                    command = ["recuperar", "--backup", selected, "--modo", mode]
                    if mode != "total":
                        _, manifest = read_manifest(selected)
                        kind = "directory" if mode == "parcial" else "file"
                        for entry in manifest["entries"]:
                            if entry["type"] == kind:
                                print("  " + entry["path"])
                        command.extend(["--ruta", ask_path("Ruta de la lista")])
                    command.extend(["--destino", ask_path("Carpeta raíz de recuperación", str(PROJECT / "recuperados"))])
                    if input("¿Reemplazar archivos existentes? Escribe SI para autorizar: ").strip().upper() == "SI":
                        command.append("--sobrescribir")
                    args = parser().parse_args(command)
            else:
                print("Elige una opción entre 1 y 7.")
                continue
            emit(audited(args, settings))
            print("Operación completada.")
        except (BackupError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
        except (EOFError, KeyboardInterrupt):
            print("\nMenú cerrado.")
            return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        settings = configuration(args.config)
        if args.command in (None, "menu"):
            return menu(settings)
        emit(audited(args, settings), args.json)
        return 0
    except (BackupError, OSError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operación interrumpida; revisa el destino antes de reintentar.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
