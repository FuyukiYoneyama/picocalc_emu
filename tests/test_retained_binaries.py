"""Evidence retention must not disable the release asset guard."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_environment import verify_release_conditions


class RetainedBinaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "firmware-validation/evidence/example/uart.bin"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"original\r\n")
        self.entry = {"path": self.path.relative_to(self.root).as_posix(),
                      "kind": "uart-capture",
                      "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()}

    def manifest(self, entries=None):
        (self.root / "firmware-validation/retained-binaries.json").write_text(
            json.dumps({"schema_version": 1, "files": entries if entries is not None else [self.entry]}))

    def status(self):
        checks = []
        verify_release_conditions(checks, self.root)
        return next(c["status"] for c in checks if c["name"] == "release:no-conformance-target")

    def test_registered_original_passes(self):
        self.manifest()
        self.assertEqual(self.status(), "pass")

    def test_unregistered_uart_is_not_ignored(self):
        self.assertEqual(self.status(), "fail")

    def test_changed_or_missing_original_fails(self):
        self.manifest()
        self.path.write_bytes(b"changed")
        self.assertEqual(self.status(), "fail")
        self.path.unlink()
        self.assertEqual(self.status(), "fail")

    def test_extra_firmware_fails(self):
        self.manifest()
        self.path.with_name("extra.uf2").write_bytes(b"firmware")
        self.assertEqual(self.status(), "fail")

    def test_official_sample_remains_forbidden_even_if_registered(self):
        sample = self.path.with_name("picocalc_helloworld.bin")
        self.path.rename(sample)
        self.entry["path"] = sample.relative_to(self.root).as_posix()
        self.manifest()
        self.assertEqual(self.status(), "fail")

    def test_bad_manifest_entries_fail_closed(self):
        for field, value in [("path", "../outside.bin"), ("path", "docs/uart.bin"),
                             ("sha256", "bad"), ("kind", "anything")]:
            with self.subTest(field=field, value=value):
                self.manifest([{**self.entry, field: value}])
                self.assertEqual(self.status(), "fail")
        self.manifest([self.entry, self.entry])
        self.assertEqual(self.status(), "fail")

    def test_malformed_manifest_fails(self):
        self.manifest()
        (self.root / "firmware-validation/retained-binaries.json").write_text("{")
        self.assertEqual(self.status(), "fail")

    def test_symlink_escape_fails(self):
        outside = self.root / "outside.bin"
        self.path.rename(outside)
        self.path.symlink_to(outside)
        self.manifest()
        self.assertEqual(self.status(), "fail")
