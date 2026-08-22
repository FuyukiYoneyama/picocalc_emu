import hashlib
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from uf2_image import (  # noqa: E402
    MAGIC_END,
    MAGIC_START0,
    MAGIC_START1,
    RP2040_FAMILY_ID,
    UF2_BLOCK_SIZE,
    UF2_FLAG_FAMILY_ID_PRESENT,
    UF2_FLAG_NOT_MAIN_FLASH,
    Uf2ImageError,
    assemble_flash,
    inspect_uf2,
)


ROOT = Path(__file__).resolve().parents[1]
PICOCALC = ROOT / "tools/picocalc.py"


def write_uf2(path: Path, blocks, *, family_id=RP2040_FAMILY_ID, family_flag=True):
    count = len(blocks)
    encoded = bytearray()
    for block_number, target, payload, flags in blocks:
        flags = flags | (UF2_FLAG_FAMILY_ID_PRESENT if family_flag else 0)
        chunk = bytearray(UF2_BLOCK_SIZE)
        struct.pack_into(
            "<IIIIIIII",
            chunk,
            0,
            MAGIC_START0,
            MAGIC_START1,
            flags,
            target,
            len(payload),
            block_number,
            count,
            family_id if family_flag else 0,
        )
        chunk[32 : 32 + len(payload)] = payload
        struct.pack_into("<I", chunk, 508, MAGIC_END)
        encoded.extend(chunk)
    path.write_bytes(encoded)


class Uf2ImageTests(unittest.TestCase):
    def test_assemble_is_deterministic_and_fills_blank_flash_with_ff(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-uf2-test-") as temporary:
            root = Path(temporary)
            source = root / "bootloader.uf2"
            output = root / "initial.bin"
            blocks = [
                (1, 0x1000_0100, bytes(range(64)), 0),
                (0, 0x1000_0000, b"boot2" + bytes(59), 0),
            ]
            write_uf2(source, blocks)
            report = assemble_flash(source, output, flash_size=4096)
            image = output.read_bytes()
            self.assertEqual(len(image), 4096)
            self.assertEqual(image[:64], b"boot2" + bytes(59))
            self.assertEqual(image[0x100:0x140], bytes(range(64)))
            self.assertEqual(image[0x40:0x100], b"\xff" * 0xC0)
            self.assertEqual(image[0x140:], b"\xff" * (4096 - 0x140))
            self.assertEqual(report["operation"], "assemble")
            self.assertEqual(report["block_count"], 2)
            self.assertEqual(report["input"]["name"], source.name)
            self.assertNotIn("path", report["input"])
            self.assertEqual(report["flash"]["output_name"], output.name)
            self.assertEqual(report["flash"]["output_sha256"], hashlib.sha256(image).hexdigest())

            second = root / "second.bin"
            second_report = assemble_flash(source, second, flash_size=4096)
            self.assertEqual(second.read_bytes(), image)
            self.assertEqual(second_report["flash"]["output_sha256"], report["flash"]["output_sha256"])

    def test_inspect_accepts_unordered_blocks_but_reports_source_index(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-uf2-test-") as temporary:
            path = Path(temporary) / "app.uf2"
            write_uf2(
                path,
                [
                    (1, 0x1000_0200, b"B" * 16, 0),
                    (0, 0x1000_0000, b"A" * 16, 0),
                ],
            )
            report = inspect_uf2(path)
            self.assertEqual([block["block_number"] for block in report["blocks"]], [0, 1])
            self.assertEqual(report["blocks"][0]["source_index"], 1)
            self.assertEqual(report["blocks"][1]["source_index"], 0)

    def test_rejects_wrong_family_duplicates_overlap_and_nonflash(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-uf2-test-") as temporary:
            root = Path(temporary)

            wrong = root / "wrong.uf2"
            write_uf2(wrong, [(0, 0x1000_0000, b"A" * 4, 0)], family_id=0x1234)
            with self.assertRaises(Uf2ImageError):
                inspect_uf2(wrong)

            duplicate = root / "duplicate.uf2"
            write_uf2(
                duplicate,
                [(0, 0x1000_0000, b"A" * 4, 0), (0, 0x1000_0100, b"B" * 4, 0)],
            )
            with self.assertRaises(Uf2ImageError):
                inspect_uf2(duplicate)

            overlap = root / "overlap.uf2"
            write_uf2(
                overlap,
                [(0, 0x1000_0000, b"A" * 8, 0), (1, 0x1000_0004, b"B" * 8, 0)],
            )
            with self.assertRaises(Uf2ImageError):
                assemble_flash(overlap, root / "overlap.bin", flash_size=4096)

            nonflash = root / "nonflash.uf2"
            write_uf2(nonflash, [(0, 0x1000_0000, b"A" * 4, UF2_FLAG_NOT_MAIN_FLASH)])
            with self.assertRaises(Uf2ImageError):
                assemble_flash(nonflash, root / "nonflash.bin", flash_size=4096)

    def test_family_flag_can_be_explicitly_relaxed_but_range_stays_strict(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-uf2-test-") as temporary:
            root = Path(temporary)
            no_family = root / "no-family.uf2"
            write_uf2(no_family, [(0, 0x1000_0000, b"A" * 4, 0)], family_flag=False)
            with self.assertRaises(Uf2ImageError):
                inspect_uf2(no_family)
            report = inspect_uf2(no_family, expected_family_id=None, require_family_id=False)
            self.assertEqual(report["family_ids"], [])

            out_of_range = root / "out-of-range.uf2"
            write_uf2(out_of_range, [(0, 0x1000_1000, b"A" * 4, 0)])
            with self.assertRaises(Uf2ImageError):
                assemble_flash(out_of_range, root / "out.bin", flash_size=4096)

    def test_cli_assemble_and_inspect(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-uf2-test-") as temporary:
            root = Path(temporary)
            source = root / "app.uf2"
            output = root / "app.bin"
            write_uf2(source, [(0, 0x1000_0000, b"A" * 16, 0)])
            assembled = subprocess.run(
                [
                    sys.executable,
                    str(PICOCALC),
                    "uf2",
                    "assemble",
                    str(source),
                    str(output),
                    "--flash-size-mib",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(assembled.returncode, 0, assembled.stderr)
            assemble_report = json.loads(assembled.stdout)
            self.assertEqual(assemble_report["operation"], "assemble")
            self.assertEqual(output.stat().st_size, 1024 * 1024)

            inspected = subprocess.run(
                [sys.executable, str(PICOCALC), "uf2", "inspect", str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["block_count"], 1)


if __name__ == "__main__":
    unittest.main()
