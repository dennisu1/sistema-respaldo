import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src import core
from src.backup import main


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "datos con espacios"
        self.repository = self.root / "backups"
        self.destination = self.root / "recuperados"
        (self.source / "documentos" / "vacia").mkdir(parents=True)
        (self.source / "fotos").mkdir()
        (self.source / "documentos" / "niñez.txt").write_text("Información original\n", encoding="utf-8")
        (self.source / "documentos" / "otra.txt").write_text("otra versión", encoding="utf-8")
        (self.source / "fotos" / "datos.bin").write_bytes(bytes(range(256)) * 64)
        (self.source / "cero.txt").touch()

    def backup(self):
        return Path(core.create_backup(self.source, self.repository)["backup"])

    def edit_manifest(self, backup, callback):
        path = backup / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        callback(manifest)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_restore_all_after_source_unavailable(self):
        expected = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        backup = self.backup()
        self.source.rename(self.root / "fuera_de_servicio")
        report = core.restore_backup(backup, self.source)
        self.assertEqual(report["files"], 4)
        self.assertEqual({p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}, expected)
        self.assertTrue((self.source / "documentos/vacia").is_dir())

    def test_partial_restores_only_folder(self):
        core.restore_backup(self.backup(), self.destination, "parcial", "documentos")
        self.assertEqual({p.name for p in self.destination.iterdir()}, {"documentos"})
        self.assertTrue((self.destination / "documentos/vacia").is_dir())
        self.assertEqual(len(list(self.destination.rglob("*.txt"))), 2)

    def test_individual_preserves_parent_structure(self):
        core.restore_backup(self.backup(), self.destination, "individual", "documentos\\niñez.txt")
        files = [p.relative_to(self.destination).as_posix() for p in self.destination.rglob("*") if p.is_file()]
        self.assertEqual(files, ["documentos/niñez.txt"])

    def test_empty_source_and_empty_folder_restore(self):
        empty = self.root / "vacia"
        empty.mkdir()
        backup = Path(core.create_backup(empty, self.repository)["backup"])
        core.restore_backup(backup, self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])
        core.restore_backup(self.backup(), self.root / "solo_vacia", "parcial", "documentos/vacia")
        self.assertTrue((self.root / "solo_vacia/documentos/vacia").is_dir())

    def test_versions_remain_independent(self):
        first = self.backup()
        (self.source / "documentos/niñez.txt").write_text("nuevo", encoding="utf-8")
        second = self.backup()
        self.assertNotEqual(first, second)
        self.assertNotEqual((first / "datos/documentos/niñez.txt").read_bytes(),
                            (second / "datos/documentos/niñez.txt").read_bytes())
        self.assertEqual(len(core.list_backups(self.repository)), 2)

    def test_conflict_aborts_before_any_restore(self):
        backup = self.backup()
        self.destination.mkdir()
        existing = self.destination / "cero.txt"
        existing.write_text("No reemplazar", encoding="utf-8")
        with self.assertRaises(core.BackupError):
            core.restore_backup(backup, self.destination)
        self.assertEqual(existing.read_text(encoding="utf-8"), "No reemplazar")
        self.assertEqual(list(self.destination.iterdir()), [existing])

    def test_overwrite_explicit_keeps_unrelated_files(self):
        backup = self.backup()
        self.destination.mkdir()
        (self.destination / "cero.txt").write_text("modificado", encoding="utf-8")
        (self.destination / "extra.txt").write_text("conservar", encoding="utf-8")
        core.restore_backup(backup, self.destination, overwrite=True)
        self.assertEqual((self.destination / "cero.txt").read_bytes(), b"")
        self.assertEqual((self.destination / "extra.txt").read_text(encoding="utf-8"), "conservar")

    def test_corruption_detected_before_overwrite(self):
        backup = self.backup()
        (backup / "datos/documentos/niñez.txt").write_text("corrupto", encoding="utf-8")
        self.destination.mkdir()
        (self.destination / "cero.txt").write_text("conservar", encoding="utf-8")
        with self.assertRaises(core.BackupError):
            core.restore_backup(backup, self.destination, overwrite=True)
        self.assertEqual((self.destination / "cero.txt").read_text(encoding="utf-8"), "conservar")

    def test_same_size_corruption_detected(self):
        backup = self.backup()
        target = backup / "datos/fotos/datos.bin"
        data = bytearray(target.read_bytes())
        data[0] ^= 255
        target.write_bytes(data)
        with self.assertRaises(core.BackupError):
            core.verify_backup(backup)

    def test_partial_can_salvage_healthy_folder(self):
        backup = self.backup()
        (backup / "datos/fotos/datos.bin").unlink()
        core.restore_backup(backup, self.destination, "parcial", "documentos")
        self.assertTrue((self.destination / "documentos/niñez.txt").exists())
        with self.assertRaises(core.BackupError):
            core.verify_backup(backup)

    def test_untracked_backup_file_detected(self):
        backup = self.backup()
        (backup / "datos/intruso.txt").touch()
        with self.assertRaises(core.BackupError):
            core.verify_backup(backup)

    def test_nested_paths_refused(self):
        for repository in (self.source, self.source / "backups", self.root):
            with self.subTest(repository=repository), self.assertRaises(core.BackupError):
                core.create_backup(self.source, repository)
        backup = self.backup()
        for destination in (backup, self.repository / "otra", self.root):
            with self.subTest(destination=destination), self.assertRaises(core.BackupError):
                core.restore_backup(backup, destination)

    def test_missing_source_does_not_create_repository(self):
        with self.assertRaises(core.BackupError):
            core.create_backup(self.root / "no_existe", self.repository)
        self.assertFalse(self.repository.exists())

    def test_invalid_selection(self):
        backup = self.backup()
        for mode, selection in (("total", "cero.txt"), ("parcial", "cero.txt"),
                                ("individual", "documentos"), ("parcial", "ausente"),
                                ("individual", "../fuera"), ("parcial", None)):
            with self.subTest(mode=mode, selection=selection), self.assertRaises(core.BackupError):
                core.restore_backup(backup, self.destination, mode, selection)
        self.assertFalse(self.destination.exists())

    def test_untrusted_manifest_paths(self):
        backup = self.backup()
        for path in ("../fuera", "/absoluta", "C:/Windows/test", "a/../../escape", "a\\..\\escape",
                     "archivo:flujo", "a//b", "a/./b", "CON.txt", "aux", "a.", "a ", "", None):
            self.edit_manifest(backup, lambda m: m["entries"][0].update(path=path))
            with self.subTest(path=path), self.assertRaises(core.BackupError):
                core.restore_backup(backup, self.destination)
        self.assertFalse(self.destination.exists())

    def test_invalid_manifest_structures(self):
        backup = self.backup()
        original = (backup / "manifest.json").read_text(encoding="utf-8")
        changes = [lambda m: m.update(format_version=99), lambda m: m.update(entries="mal"),
                   lambda m: m["entries"].append(dict(m["entries"][0])),
                   lambda m: m.update(files=999), lambda m: m.update(bytes=999),
                   lambda m: m["entries"].append(None),
                   lambda m: m["entries"].append({"path": "padre/hijo", "type": "directory"})]
        for change in changes:
            (backup / "manifest.json").write_text(original, encoding="utf-8")
            self.edit_manifest(backup, change)
            with self.assertRaises(core.BackupError):
                core.verify_backup(backup)

    def test_file_in_destination_parent_is_refused(self):
        backup = self.backup()
        self.destination.mkdir()
        (self.destination / "documentos").touch()
        with self.assertRaises(core.BackupError):
            core.restore_backup(backup, self.destination, "individual", "documentos/niñez.txt", True)

    def test_copy_failure_never_publishes_version(self):
        with patch("src.core.copy_verified", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                self.backup()
        self.assertEqual(list(self.repository.iterdir()), [])

    def test_change_during_backup_never_publishes_version(self):
        original = core.copy_verified

        def changing(source, target, expected=None):
            result = original(source, target, expected)
            (self.source / "nuevo.txt").write_text("cambio", encoding="utf-8")
            return result

        with patch("src.core.copy_verified", side_effect=changing), self.assertRaises(core.BackupError):
            self.backup()
        self.assertEqual(list(self.repository.iterdir()), [])

    def test_corruption_during_restore_staging_does_not_touch_destination(self):
        backup = self.backup()
        with patch("src.core.copy_verified", side_effect=core.BackupError("cambió")):
            with self.assertRaises(core.BackupError):
                core.restore_backup(backup, self.destination)
        self.assertFalse(self.destination.exists())

    def test_low_space_prevents_version(self):
        with patch("src.core.shutil.disk_usage", return_value=shutil._ntuple_diskusage(1, 1, 0)):
            with self.assertRaises(core.BackupError):
                self.backup()
        self.assertEqual(list(self.repository.iterdir()), [])

    def test_incomplete_ignored_invalid_listed(self):
        self.repository.mkdir()
        (self.repository / ".incomplete-demo").mkdir()
        (self.repository / "Backup_roto").mkdir()
        rows = core.list_backups(self.repository)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "inválido")

    def test_symbolic_link_rejected(self):
        link = self.source / "enlace"
        try:
            link.symlink_to(self.source / "documentos", target_is_directory=True)
        except OSError:
            self.skipTest("Crear symlinks requiere permisos o modo desarrollador en Windows")
        with self.assertRaises(core.BackupError):
            self.backup()

    @unittest.skipUnless(os.name == "nt", "Junctions solo existen en Windows")
    def test_windows_junction_rejected(self):
        junction = self.source / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(self.root / "externo")],
                                capture_output=True)
        if result.returncode:
            self.skipTest("No fue posible crear el junction de prueba")
        self.addCleanup(lambda: os.rmdir(junction) if junction.exists() or junction.is_symlink() else None)
        with self.assertRaises(core.BackupError):
            self.backup()

    def test_case_collision_in_manifest_rejected(self):
        backup = self.backup()
        self.edit_manifest(backup, lambda m: m["entries"].append({"path": "DOCUMENTOS", "type": "directory"}))
        with self.assertRaises(core.BackupError):
            core.verify_backup(backup)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "datos").mkdir()
        (self.root / "datos/test.txt").write_text("contenido", encoding="utf-8")
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"source": "datos", "backup_root": "backups", "log_file": "logs/events.jsonl"}), encoding="utf-8")

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--config", str(self.config), "--json", *args])
        return code, out.getvalue(), err.getvalue()

    def test_full_cli_flow_and_audit(self):
        code, output, _ = self.invoke("respaldo")
        self.assertEqual(code, 0)
        backup = json.loads(output)["backup"]
        for args in (("listar",), ("contenido", "--backup", backup), ("verificar", "--backup", backup),
                     ("recuperar", "--backup", backup, "--destino", str(self.root / "restaurados"))):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args)[0], 0)
        events = [json.loads(line) for line in (self.root / "logs/events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(events), 5)
        self.assertTrue(all(event["status"] == "ok" for event in events))

    def test_failure_exit_status_and_audit(self):
        code, _, error = self.invoke("respaldo", "--origen", str(self.root / "missing"))
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(error))
        event = json.loads((self.root / "logs/events.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(event["status"], "error")

    def test_cli_from_other_working_directory(self):
        script = Path(__file__).resolve().parents[1] / "src/backup.py"
        result = subprocess.run([sys.executable, str(script), "--config", str(self.config), "--json", "respaldo"],
                                cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "backups").is_dir())

    def test_bad_config_is_readable_error(self):
        self.config.write_text('{"source": 4}', encoding="utf-8")
        code, _, error = self.invoke("respaldo")
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(error))

    def test_menu_exits(self):
        with patch("builtins.input", return_value="7"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--config", str(self.config)]), 0)

    def test_log_cannot_modify_source_data(self):
        self.config.write_text(json.dumps({"source": "datos", "backup_root": "backups", "log_file": "datos/test.txt"}), encoding="utf-8")
        self.assertEqual(self.invoke("respaldo")[0], 1)
        self.assertEqual((self.root / "datos/test.txt").read_text(encoding="utf-8"), "contenido")
        self.assertFalse((self.root / "backups").exists())

    def test_log_cannot_corrupt_a_manifest(self):
        _, output, _ = self.invoke("respaldo")
        backup = Path(json.loads(output)["backup"])
        manifest = backup / "manifest.json"
        original = manifest.read_bytes()
        self.config.write_text(json.dumps({"log_file": str(manifest)}), encoding="utf-8")
        self.assertEqual(self.invoke("verificar", "--backup", str(backup))[0], 1)
        self.assertEqual(manifest.read_bytes(), original)

    def test_log_cannot_follow_a_hard_link(self):
        log = self.root / "linked.log"
        os.link(self.root / "datos/test.txt", log)
        self.config.write_text(json.dumps({"source": "datos", "backup_root": "backups", "log_file": str(log)}), encoding="utf-8")
        self.assertEqual(self.invoke("respaldo")[0], 1)
        self.assertEqual((self.root / "datos/test.txt").read_text(encoding="utf-8"), "contenido")


if __name__ == "__main__":
    unittest.main()
