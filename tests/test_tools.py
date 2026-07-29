import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PICOCALC = ROOT / "tools/picocalc.py"
VERIFY = ROOT / "tools/verify_environment.py"


def run(*arguments, env=None):
    return subprocess.run(
        [sys.executable, *map(str, arguments)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )


class ToolTests(unittest.TestCase):
    def test_portable_verification_and_json_schema(self):
        completed = run(VERIFY, "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["mode"], "portable")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["failed"], 0)
        self.assertTrue(report["checks"])

    def test_reference_verification_reports_missing_repositories(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = run(
                VERIFY,
                "--references",
                "--strict-commit",
                "--reference-root",
                temporary,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        missing = [
            check
            for check in report["checks"]
            if check["name"].startswith("reference-commit:")
        ]
        self.assertEqual(len(missing), 3)
        self.assertTrue(all(check["actual"] == "missing" for check in missing))

    def test_strict_commit_requires_reference_mode(self):
        completed = run(VERIFY, "--strict-commit")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("require --references", completed.stderr)

    def test_source_fingerprint_detects_removed_lcd_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            shutil.copytree(
                ROOT,
                project,
                ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", "third_party", "build"
                ),
            )
            display = project / "bsp/src/display.cpp"
            display.write_text(
                display.read_text(encoding="utf-8").replace(
                    "write_command1(0x3a, 0x65)",
                    "write_command1(0x3a, 0x66)",
                ),
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        lcd = next(
            check
            for check in report["checks"]
            if check["name"] == "source-fingerprint:lcd-known-good-sequence"
        )
        self.assertEqual(lcd["status"], "fail")

    def test_project_generator_pins_bsp_and_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "Demo_App-1"
            completed = run(
                PICOCALC,
                "new",
                "Demo_App-1",
                "--output",
                destination,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((destination / "app/main.cpp").is_file())
            self.assertTrue((destination / "bsp/src/display.cpp").is_file())
            metadata = json.loads(
                (destination / ".picocalc-project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["project_name"], "Demo_App-1")
            self.assertEqual(metadata["bsp_version"], "0.1.0")

    def test_project_generator_rejects_invalid_name(self):
        completed = run(PICOCALC, "new", "../bad")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("name must start with a letter", completed.stderr)

    def test_project_generator_does_not_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = run(
                PICOCALC,
                "new",
                "Existing",
                "--output",
                temporary,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("destination already exists", completed.stderr)

    def test_build_rejects_missing_sdk(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.13)\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.pop("PICO_SDK_PATH", None)
            completed = run(
                PICOCALC,
                "build",
                "--project",
                project,
                "--sdk",
                project / "missing-sdk",
                env=environment,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Pico SDK not found", completed.stderr)

    def test_build_rejects_invalid_picotool_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            project = temporary_path / "project"
            sdk = temporary_path / "sdk"
            project.mkdir()
            (project / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.13)\n",
                encoding="utf-8",
            )
            (sdk / "external").mkdir(parents=True)
            (sdk / "external/pico_sdk_import.cmake").write_text("", encoding="utf-8")
            completed = run(
                PICOCALC,
                "build",
                "--project",
                project,
                "--sdk",
                sdk,
                "--picotool-dir",
                temporary_path / "missing-picotool",
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid picotool", completed.stderr)

    def test_reference_fetch_dry_run_uses_catalog_urls_and_commits(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "references"
            completed = run(
                PICOCALC,
                "fetch-references",
                "--output",
                output,
                "--dry-run",
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.count("fetch https://github.com/"), 3)
        self.assertIn("0d677d07cb0a037ee9cf331106400052622603ee", completed.stdout)

    def test_reference_fetch_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "picocalc-life").mkdir()
            completed = run(
                PICOCALC,
                "fetch-references",
                "--output",
                output,
                "--dry-run",
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("destination already exists", completed.stderr)


if __name__ == "__main__":
    unittest.main()
