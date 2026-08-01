import json
import importlib.util
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
GENERATE_BOARD = ROOT / "tools/generate_board_header.py"


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
    def test_build_versions_selects_non_coexistence_variant(self):
        specification = importlib.util.spec_from_file_location("picocalc", PICOCALC)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        project = ROOT / "templates/rp2040-basic"
        _, standard = module.build_versions(project, "pio-rgb565", False)
        _, coexistence = module.build_versions(project, "pio-rgb565", True)
        self.assertEqual(standard, "0.8.3-b-pio-rgb565-default")
        self.assertEqual(coexistence, "0.8.3-b-pio-rgb565-psram-lcd-coexist")

    def copy_project(self, temporary):
        project = Path(temporary) / "project"
        shutil.copytree(
            ROOT,
            project,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "third_party", "build", "build-ci"
            ),
        )
        return project

    def test_lcd_protocol_emits_exact_transactions_and_cs_chunks(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "a C++17 host compiler is required")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "lcd_protocol_test"
            compiled = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "bsp/include"),
                    str(ROOT / "tests/lcd_protocol_test.cpp"),
                    "-o",
                    str(executable),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run(
                [str(executable)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn("transaction test passed", executed.stdout)

    def test_generated_board_header_is_current(self):
        completed = run(GENERATE_BOARD, "--check")
        self.assertEqual(completed.returncode, 0, completed.stderr)

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
        self.assertEqual(len(missing), 4)
        self.assertTrue(all(check["actual"] == "missing" for check in missing))

    def test_strict_commit_requires_reference_mode(self):
        completed = run(VERIFY, "--strict-commit")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("require --references", completed.stdout)

    def test_lcd_transaction_test_detects_changed_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            protocol = project / "bsp/include/picocalc/detail/lcd_protocol.h"
            protocol.write_text(
                protocol.read_text(encoding="utf-8").replace(
                    "{0x3a, {board::kLcdColmod}, 1}",
                    "{0x3a, {0x65}, 1}",
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
            if check["name"] == "host-test:lcd-transactions"
        )
        self.assertEqual(lcd["status"], "fail")
        self.assertEqual(lcd["stage"], "execute")

    def test_generated_header_check_detects_profile_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            profile_path = project / "profiles/picocalc-rp2040.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["display"]["visible_width"] = 321
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        generated = next(
            check
            for check in report["checks"]
            if check["name"] == "structured-profile:generated-board-header"
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(generated["status"], "fail")
        self.assertTrue(generated["stale"])

    def test_json_mode_normalizes_malformed_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            (project / "profiles/picocalc-rp2040.json").write_text(
                "{broken",
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
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("Traceback", completed.stderr)
        generated = next(
            check
            for check in report["checks"]
            if check["name"] == "structured-profile:generated-board-header"
        )
        self.assertEqual(generated["error_type"], "JSONDecodeError")

    def test_json_mode_normalizes_malformed_reference_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            (project / "reference-projects/catalog.json").write_text(
                "[] not-json",
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--references",
                "--reference-root",
                temporary,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(
            any(check["name"] == "reference-catalog" for check in report["checks"])
        )
        self.assertNotIn("Traceback", completed.stderr)

    def test_json_mode_normalizes_invalid_arguments(self):
        completed = run(VERIFY, "--strict-commit", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(report["mode"], "invalid")
        self.assertEqual(report["checks"][0]["name"], "invocation:arguments")
        self.assertEqual(completed.stderr, "")

    def test_hardware_record_rejects_unsubstantiated_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            template_path = project / "hardware-validation/template.json"
            record = json.loads(template_path.read_text(encoding="utf-8"))
            record["overall_status"] = "pass"
            record_path = project / "hardware-validation/records/unsubstantiated.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        ledger = next(
            check
            for check in report["checks"]
            if check["name"] == "hardware-validation:records"
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(ledger["status"], "fail")
        self.assertGreaterEqual(len(ledger["invalid"][0]["errors"]), 7)

    def test_hardware_record_accepts_complete_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            template_path = project / "hardware-validation/template.json"
            record = json.loads(template_path.read_text(encoding="utf-8"))
            evidence_dir = project / "hardware-validation/records/session"
            evidence_dir.mkdir()
            relative_files = {
                "lcd": "hardware-validation/records/session/lcd.png",
                "sd": "hardware-validation/records/session/uart.log",
                "keyboard": "hardware-validation/records/session/keys.log",
            }
            for relative in relative_files.values():
                (project / relative).write_text("evidence", encoding="utf-8")
            build_log = "hardware-validation/records/session/build.log"
            (project / build_log).write_text("build passed", encoding="utf-8")

            record.update(
                {
                    "validation_id": "bsp-0.1.0-20260729-01",
                    "repository_commit": "a" * 40,
                    "validation_date": "2026-07-29",
                    "operator": "test",
                    "overall_status": "pass",
                }
            )
            record["firmware"]["uf2_sha256"] = "b" * 64
            record["firmware"]["build_log"] = build_log
            record["hardware"]["board_revision"] = "1.0"
            record["software"]["compiler"] = "arm-none-eabi-g++ 9.2.1"
            record["software"]["cmake"] = "3.16.3"
            record["sd_card"].update(
                {
                    "manufacturer": "test-vendor",
                    "model": "test-model",
                    "capacity": "8 GB",
                }
            )
            for name, relative in relative_files.items():
                record["tests"][name] = {
                    "status": "pass",
                    "observed": "verified",
                    "evidence_files": [relative],
                }
            record_path = project / "hardware-validation/records/complete.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        ledger = next(
            check
            for check in report["checks"]
            if check["name"] == "hardware-validation:records"
        )
        self.assertEqual(completed.returncode, 0, report)
        self.assertEqual(ledger["passing_records"], 1)

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
            self.assertTrue(
                (
                    destination
                    / "bsp/include/picocalc/detail/lcd_protocol.h"
                ).is_file()
            )
            self.assertTrue(
                (
                    destination
                    / "bsp/include/picocalc/board_generated.h"
                ).is_file()
            )
            self.assertFalse((destination / "build").exists())
            self.assertFalse((destination / ".picocalc-build-history.json").exists())
            metadata = json.loads(
                (destination / ".picocalc-project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["project_name"], "Demo_App-1")
            self.assertEqual(metadata["bsp_version"], "0.5.0")

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
        self.assertEqual(completed.stdout.count("fetch https://github.com/"), 4)
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
