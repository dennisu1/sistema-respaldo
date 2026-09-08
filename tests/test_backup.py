"""Pruebas de las funciones principales con archivos temporales."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src import backup


class PruebasRespaldo(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)
        self.origen = self.base / "datos"
        self.backups = self.base / "backups"
        self.recuperados = self.base / "recuperados"
        (self.origen / "documentos/vacia").mkdir(parents=True)
        (self.origen / "documentos/tarea.txt").write_text("Información original", encoding="utf-8")
        (self.origen / "imagen.bin").write_bytes(bytes(range(256)))

    def crear(self):
        return backup.crear_respaldo(self.origen, self.backups)

    def test_versiones_independientes(self):
        primera = self.crear()
        (self.origen / "documentos/tarea.txt").write_text("Versión nueva", encoding="utf-8")
        segunda = self.crear()
        self.assertNotEqual(primera, segunda)
        self.assertEqual(len(backup.obtener_respaldos(self.backups)), 2)
        self.assertEqual((primera / "datos/documentos/tarea.txt").read_text(encoding="utf-8"), "Información original")
        self.assertEqual((segunda / "datos/documentos/tarea.txt").read_text(encoding="utf-8"), "Versión nueva")

    def test_recuperacion_total_sin_origen(self):
        version = self.crear()
        self.origen.rename(self.base / "datos_no_disponibles")
        destino = backup.recuperar(version, self.recuperados)
        self.assertEqual((destino / "imagen.bin").read_bytes(), bytes(range(256)))
        self.assertEqual((destino / "documentos/tarea.txt").read_text(encoding="utf-8"), "Información original")
        self.assertTrue((destino / "documentos/vacia").is_dir())

    def test_recuperacion_parcial(self):
        destino = backup.recuperar(self.crear(), self.recuperados, "parcial", "documentos")
        self.assertTrue((destino / "documentos/tarea.txt").is_file())
        self.assertTrue((destino / "documentos/vacia").is_dir())
        self.assertFalse((destino / "imagen.bin").exists())

    def test_recuperacion_individual(self):
        destino = backup.recuperar(self.crear(), self.recuperados, "individual", "documentos/tarea.txt")
        archivos = [ruta.relative_to(destino).as_posix() for ruta in destino.rglob("*") if ruta.is_file()]
        self.assertEqual(archivos, ["documentos/tarea.txt"])

    def test_cada_recuperacion_conserva_las_anteriores(self):
        version = self.crear()
        primera = backup.recuperar(version, self.recuperados)
        (primera / "imagen.bin").write_bytes(b"Conservar este cambio")
        segunda = backup.recuperar(version, self.recuperados)
        self.assertNotEqual(primera, segunda)
        self.assertEqual((primera / "imagen.bin").read_bytes(), b"Conservar este cambio")
        self.assertEqual((segunda / "imagen.bin").read_bytes(), bytes(range(256)))

    def test_rechaza_rutas_y_selecciones_incorrectas(self):
        for almacen in (self.origen, self.origen / "backups", self.base):
            with self.subTest(almacen=almacen), self.assertRaises(ValueError):
                backup.crear_respaldo(self.origen, almacen)
        version = self.crear()
        for modo, seleccion in (("individual", "../imagen.bin"), ("individual", str(self.origen)),
                                ("parcial", "imagen.bin"), ("individual", "documentos"),
                                ("parcial", None), ("individual", "inexistente")):
            with self.subTest(seleccion=seleccion), self.assertRaises(ValueError):
                backup.recuperar(version, self.recuperados, modo, seleccion)
        with self.assertRaises(ValueError):
            backup.recuperar(version, self.backups)

    def test_un_error_no_deja_un_respaldo_incompleto(self):
        with patch("src.backup.shutil.copytree", side_effect=OSError("Error de copia")):
            with self.assertRaises(OSError):
                self.crear()
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_origen_inexistente(self):
        with self.assertRaises(ValueError):
            backup.crear_respaldo(self.base / "no_existe", self.backups)
        self.assertFalse(self.backups.exists())

    def test_no_sigue_enlaces(self):
        try:
            (self.origen / "enlace").symlink_to(self.base, target_is_directory=True)
        except OSError:
            self.skipTest("Este equipo no permite crear enlaces simbólicos de prueba")
        with self.assertRaises(ValueError):
            self.crear()

    def test_automatico_no_necesita_interaccion(self):
        programa = Path(backup.__file__).resolve()
        comando = [sys.executable, str(programa), "--automatico", "--origen", str(self.origen),
                   "--backups", str(self.backups)]
        resultado = subprocess.run(comando, cwd=self.base, stdin=subprocess.DEVNULL,
                                   capture_output=True, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(len(backup.obtener_respaldos(self.backups)), 1)
        fallido = subprocess.run([sys.executable, str(programa), "--automatico", "--origen", "no_existe"],
                                 cwd=self.base, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
        self.assertEqual(fallido.returncode, 1)


if __name__ == "__main__":
    unittest.main()
