"""Respaldos completos versionados y recuperación selectiva, sin dependencias."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from uuid import uuid4


class BackupError(Exception):
    """Error que puede mostrarse directamente al usuario."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def checked_path(value: str | Path) -> Path:
    """Comprueba enlaces ANTES de resolverlos, incluidos junctions de Windows."""
    path = Path(os.path.abspath(Path(value).expanduser()))
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BackupError(f"No se admiten enlaces ni puntos de reanálisis: {part}")
    return path.resolve()


def overlaps(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def relative_name(value: str) -> str:
    """Acepta únicamente rutas relativas portables; nunca rutas del manifiesto sin validar."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise BackupError(f"Ruta relativa inválida: {value!r}")
    parts = value.split("/")
    for part in parts:
        if (part in ("", ".", "..") or part.endswith((".", " "))
                or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", part.split(".")[0])):
            raise BackupError(f"Ruta relativa inválida: {value!r}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path) -> list[dict]:
    result = []
    seen = set()

    def walk(folder: Path) -> None:
        for path in sorted(folder.iterdir()):
            checked_path(path)
            name = relative_name(path.relative_to(root).as_posix())
            if name.casefold() in seen:
                raise BackupError(f"Nombres duplicados sin distinguir mayúsculas: {name}")
            seen.add(name.casefold())
            info = path.stat()
            if stat.S_ISDIR(info.st_mode):
                result.append({"path": name, "type": "directory"})
                walk(path)
            elif stat.S_ISREG(info.st_mode):
                result.append({"path": name, "type": "file", "size": info.st_size,
                               "mtime_ns": info.st_mtime_ns})
            else:
                raise BackupError(f"No es un archivo o carpeta regular: {path}")

    walk(root)
    return result


def copy_verified(source: Path, target: Path, expected: str | None = None) -> str:
    checked_path(source)
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise BackupError(f"No es un archivo regular: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as src, target.open("xb") as dst:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
            dst.write(block)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise BackupError(f"El archivo cambió durante la copia: {source}")
    checksum = digest.hexdigest()
    if sha256(target) != checksum or (expected is not None and checksum != expected):
        raise BackupError(f"Integridad SHA-256 incorrecta: {source}")
    shutil.copystat(source, target)
    return checksum


def create_backup(source: str | Path, repository: str | Path) -> dict:
    source, repository = checked_path(source), checked_path(repository)
    if not source.is_dir():
        raise BackupError(f"La carpeta de origen no existe: {source}")
    if overlaps(source, repository):
        raise BackupError("Origen y almacén de respaldos deben estar separados, sin anidarse.")
    entries = inventory(source)
    total_bytes = sum(e.get("size", 0) for e in entries)
    repository.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(repository).free < total_bytes:
        raise BackupError("Espacio insuficiente para el respaldo.")
    backup_id = "Backup_" + datetime.now().strftime("%Y-%m-%d_%H%M%S_%f_") + uuid4().hex[:8]
    staging = Path(tempfile.mkdtemp(prefix=".incomplete-", dir=repository))
    try:
        data = staging / "datos"
        data.mkdir()
        stored = []
        for entry in entries:
            item = dict(entry)
            target = data / entry["path"]
            if entry["type"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
            else:
                item["sha256"] = copy_verified(source / entry["path"], target)
            stored.append(item)
        if inventory(source) != entries:
            raise BackupError("El origen cambió durante el respaldo; vuelve a intentarlo con los archivos cerrados.")
        manifest = {"format_version": 1, "id": backup_id, "created_at": now(),
                    "source": str(source), "files": sum(e["type"] == "file" for e in stored),
                    "bytes": total_bytes, "entries": stored}
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verify_backup(staging)
        final = repository / backup_id
        staging.rename(final)
        return {"backup": str(final), "id": backup_id, "files": manifest["files"], "bytes": total_bytes}
    finally:
        # Únicamente el temporal que esta función acaba de crear dentro del almacén.
        if staging.exists() and staging.parent == repository and staging.name.startswith(".incomplete-"):
            shutil.rmtree(staging)


def read_manifest(backup: str | Path) -> tuple[Path, dict]:
    backup = checked_path(backup)
    try:
        manifest_path = checked_path(backup / "manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError(f"No se puede leer el manifiesto de {backup}: {exc}") from exc
    if (not isinstance(manifest, dict) or manifest.get("format_version") != 1
            or not isinstance(manifest.get("entries"), list)
            or not isinstance(manifest.get("id"), str)
            or not isinstance(manifest.get("created_at"), str)):
        raise BackupError("Formato de manifiesto inválido o no compatible.")
    entries = {}
    seen = set()
    for entry in manifest["entries"]:
        if not isinstance(entry, dict):
            raise BackupError("Entrada de manifiesto inválida.")
        name = relative_name(entry.get("path"))
        if name.casefold() in seen or entry.get("type") not in ("file", "directory"):
            raise BackupError(f"Entrada duplicada o tipo inválido: {name}")
        seen.add(name.casefold())
        if entry["type"] == "file" and (
                type(entry.get("size")) is not int or entry["size"] < 0
                or not isinstance(entry.get("sha256"), str)
                or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])):
            raise BackupError(f"Tamaño o hash inválido: {name}")
        entries[name] = entry
    for name in entries:
        for parent in PurePosixPath(name).parents:
            if str(parent) != "." and entries.get(str(parent), {}).get("type") != "directory":
                raise BackupError(f"Carpeta padre ausente o inválida: {parent}")
    if (manifest.get("files") != sum(e["type"] == "file" for e in entries.values())
            or manifest.get("bytes") != sum(e.get("size", 0) for e in entries.values() if e["type"] == "file")):
        raise BackupError("Los totales del manifiesto no coinciden.")
    if not checked_path(backup / "datos").is_dir():
        raise BackupError("El respaldo no contiene la carpeta datos.")
    return backup, manifest


def select_entries(manifest: dict, mode: str, selection: str | None) -> list[dict]:
    if mode == "total":
        if selection:
            raise BackupError("La recuperación total no usa una ruta de selección.")
        return manifest["entries"]
    if mode not in ("parcial", "individual") or not selection:
        raise BackupError("Selecciona una ruta para recuperación parcial o individual.")
    selection = relative_name(selection.replace("\\", "/"))
    entry = next((e for e in manifest["entries"] if e["path"] == selection), None)
    expected = "directory" if mode == "parcial" else "file"
    if entry is None or entry["type"] != expected:
        raise BackupError(f"La selección no corresponde a una {expected}: {selection}")
    return [e for e in manifest["entries"] if e["path"] == selection
            or (mode == "parcial" and e["path"].startswith(selection + "/"))]


def verify_entries(backup: Path, entries: list[dict]) -> None:
    for entry in entries:
        path = checked_path(backup / "datos" / entry["path"])
        if entry["type"] == "directory":
            if not path.is_dir():
                raise BackupError(f"Falta la carpeta: {entry['path']}")
        elif (not path.is_file() or path.stat().st_size != entry["size"]
              or sha256(path) != entry["sha256"]):
            raise BackupError(f"Integridad incorrecta o archivo ausente: {entry['path']}")


def verify_backup(backup: str | Path) -> dict:
    backup, manifest = read_manifest(backup)
    verify_entries(backup, manifest["entries"])
    actual = {(e["path"], e["type"]) for e in inventory(backup / "datos")}
    expected = {(e["path"], e["type"]) for e in manifest["entries"]}
    if actual != expected:
        raise BackupError("Hay contenido no registrado en el manifiesto.")
    return {"backup": str(backup), "files": manifest["files"], "bytes": manifest["bytes"], "integrity": "ok"}


def restore_backup(backup: str | Path, destination: str | Path, mode: str = "total",
                   selection: str | None = None, overwrite: bool = False) -> dict:
    backup, manifest = read_manifest(backup)
    destination = checked_path(destination)
    if overlaps(backup.parent, destination):
        raise BackupError("El destino de recuperación debe estar fuera del almacén de respaldos y no contenerlo.")
    entries = select_entries(manifest, mode, selection)
    if mode == "total":
        verify_backup(backup)
    else:
        verify_entries(backup, entries)

    def preflight() -> None:
        for path in [destination, *destination.parents]:
            checked_path(path)
            if path.exists() and not path.is_dir():
                raise BackupError(f"Una carpeta de destino es un archivo: {path}")
        for entry in entries:
            target = checked_path(destination / entry["path"])
            for parent in target.parents:
                if parent.exists() and not parent.is_dir():
                    raise BackupError(f"Una carpeta de destino es un archivo: {parent}")
                if parent == destination:
                    break
            if target.exists():
                is_dir = entry["type"] == "directory"
                if target.is_dir() != is_dir or (not is_dir and not target.is_file()):
                    raise BackupError(f"Conflicto de tipo en el destino: {target}")
                if not is_dir and not overwrite:
                    raise BackupError(f"Ya existe {target}. Usa otro destino o --sobrescribir.")

    preflight()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Se preparan y validan TODOS los archivos seleccionados antes de tocar el destino.
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        for entry in entries:
            if entry["type"] == "file":
                copy_verified(backup / "datos" / entry["path"], staging / entry["path"], entry["sha256"])
        preflight()
        destination.mkdir(parents=True, exist_ok=True)
        for entry in sorted(entries, key=lambda e: (e["path"].count("/"), e["path"])):
            target = checked_path(destination / entry["path"])
            if entry["type"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if overwrite:
                os.replace(staging / entry["path"], target)
            else:
                # Creación exclusiva: incluso si aparece un archivo tras preflight, no se pisa.
                with target.open("xb") as dst:
                    try:
                        with (staging / entry["path"]).open("rb") as src:
                            shutil.copyfileobj(src, dst)
                    except BaseException:
                        dst.close()
                        target.unlink()
                        raise
                shutil.copystat(staging / entry["path"], target)
            if sha256(target) != entry["sha256"]:
                raise BackupError(f"La verificación final falló: {target}")
    return {"destination": str(destination), "mode": mode, "selection": selection,
            "files": sum(e["type"] == "file" for e in entries), "integrity": "ok"}


def list_backups(repository: str | Path) -> list[dict]:
    repository = checked_path(repository)
    if not repository.exists():
        return []
    result = []
    for candidate in sorted(repository.glob("Backup_*"), reverse=True):
        try:
            _, manifest = read_manifest(candidate)
            result.append({"backup": str(candidate), "id": candidate.name,
                           "created_at": manifest["created_at"], "files": manifest["files"],
                           "bytes": manifest["bytes"], "status": "sin verificar"})
        except (BackupError, OSError) as exc:
            result.append({"backup": str(candidate), "id": candidate.name, "status": "inválido", "error": str(exc)})
    return result
