"""Demostración repetible con datos ficticios; nunca borra datos del usuario."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backup import main  # noqa: E402


def hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def run() -> Path:
    workspace = ROOT / "demo_runs" / ("python_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:8])
    workspace.mkdir(parents=True)
    source = workspace / "datos"
    shutil.copytree(ROOT / "test_data", source)
    (source / "vacia").mkdir()
    (source / "documentos" / "niñez y educación.txt").write_text("Información de prueba: áéíóú ñ\n", encoding="utf-8")
    (source / "fotos" / "binario.bin").write_bytes(bytes(range(256)) * 16)
    expected = hashes(source)
    settings = workspace / "config.json"
    settings.write_text(json.dumps({"source": "datos", "backup_root": "backups",
                                    "log_file": "operaciones.jsonl"}), encoding="utf-8")

    def invoke(*args: str) -> None:
        print("\n> python src/backup.py " + " ".join(args))
        code = main(["--config", str(settings), *args])
        if code != 0:
            raise RuntimeError(f"La demostración falló con código {code}")

    invoke("respaldo")
    first = next((workspace / "backups").glob("Backup_*"))
    (source / "documentos" / "tarea.txt").write_text("Segunda versión del documento.\n", encoding="utf-8")
    invoke("respaldo")
    invoke("listar")
    # Simular indisponibilidad sin borrar: solo se renombra la carpeta creada arriba.
    source.rename(workspace / "datos_fuera_de_servicio")
    rows = []
    for mode, selection, output in (("total", None, "datos"),
                                    ("parcial", "documentos", "recuperacion_parcial"),
                                    ("individual", "documentos/tarea.txt", "recuperacion_individual")):
        destination = workspace / output
        args = ["recuperar", "--backup", str(first), "--destino", str(destination), "--modo", mode]
        if selection:
            args.extend(["--ruta", selection])
        invoke(*args)
        selected = {name: digest for name, digest in expected.items() if mode == "total"
                    or name == selection or (mode == "parcial" and name.startswith(selection + "/"))}
        actual = hashes(destination)
        if actual != selected or (mode == "total" and not (destination / "vacia").is_dir()):
            raise RuntimeError(f"La recuperación {mode} no coincide con el original.")
        rows.append({"mode": mode, "files": len(actual), "sha256_match": actual == selected,
                     "expected": selected, "actual": actual})
    invoke("verificar", "--backup", str(first))
    report = {"tool": "Programa propio Python", "python": platform.python_version(),
              "platform": platform.system(), "created_at": datetime.now().astimezone().isoformat(),
              "backup": first.name, "versions": 2, "empty_directory_restored": True, "results": rows}
    (workspace / "evidencia.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Evidencia ejecutada: programa propio", "", f"Python: {platform.python_version()}", "",
             "Se crearon dos versiones, se renombró el origen y se recuperó la primera versión.", "",
             "| Recuperación | Archivos | SHA-256 |", "|---|---:|---|"]
    lines.extend(f"| {row['mode']} | {row['files']} | Coincide |" for row in rows)
    lines.extend(["", "Carpeta vacía recuperada. Los hashes completos están en `evidencia.json`.", ""])
    (workspace / "evidencia.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDemostración aprobada. Evidencias: {workspace}")
    return workspace


if __name__ == "__main__":
    run()
