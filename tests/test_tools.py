import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ToolTests(unittest.TestCase):
    def test_contract_and_reference_evidence(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/verify_environment.py"),
                "--strict-commit",
                "--json",
            ],
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        self.assertEqual(report["status"], "pass")

    def test_project_generator_pins_bsp(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "Demo"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/picocalc.py"),
                    "new",
                    "Demo",
                    "--output",
                    str(destination),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((destination / "app/main.cpp").is_file())
            self.assertTrue((destination / "bsp/src/display.cpp").is_file())
            metadata = json.loads(
                (destination / ".picocalc-project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["project_name"], "Demo")
            self.assertEqual(metadata["bsp_version"], "0.1.0")


if __name__ == "__main__":
    unittest.main()
