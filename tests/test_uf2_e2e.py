import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from uf2_e2e import (  # noqa: E402
    DEFAULT_FLASH_BASE,
    PROGINFO_MAGIC,
    Uf2E2eError,
    _expected_loader_flash,
    _flash_checks,
)
from uf2_image import Uf2Block  # noqa: E402


def block(number: int, address: int, payload: bytes) -> Uf2Block:
    return Uf2Block(
        index=number,
        flags=0,
        target_address=address,
        payload=payload,
        block_number=number,
        block_count=2,
        file_size_or_family=0,
        family_id=0xE48BFF56,
    )


class Uf2E2eModelTests(unittest.TestCase):
    def test_loader_model_preserves_boot2_skips_block_zero_and_mutates_proginfo(self):
        initial = bytearray(b"\xff" * 0x4000)
        initial[:256] = bytes(range(256))
        initial[0x200:0x300] = b"\xaa" * 256
        app_blocks = [
            block(0, DEFAULT_FLASH_BASE, b"\x00" * 256),
            block(1, DEFAULT_FLASH_BASE + 0x200, b"\xf0" * 256),
        ]

        final = _expected_loader_flash(
            bytes(initial),
            app_blocks,
            flash_base=DEFAULT_FLASH_BASE,
            loader_region_size=0x1000,
            selected_path="/pico1-apps/test.uf2",
            flash_end=DEFAULT_FLASH_BASE + 0x3000,
        )

        self.assertEqual(final[:256], bytes(range(256)))
        self.assertEqual(final[0x200:0x300], b"\xf0" * 256)
        self.assertEqual(final[0x110:0x114], PROGINFO_MAGIC.to_bytes(4, "little"))
        self.assertEqual(int.from_bytes(final[0x114:0x118], "little"), DEFAULT_FLASH_BASE + 0x3000)
        self.assertEqual(final[0x118:0x12c].rstrip(b"\0"), b"/pico1-apps/test.uf2")

    def test_flash_checks_rejects_any_unexpected_mutation(self):
        initial = b"\xff" * 0x4000
        app_blocks = [block(0, DEFAULT_FLASH_BASE, b"A" * 256)]
        expected = _expected_loader_flash(
            initial,
            app_blocks,
            flash_base=DEFAULT_FLASH_BASE,
            loader_region_size=0x1000,
            selected_path="/pico1-apps/test.uf2",
            flash_end=DEFAULT_FLASH_BASE + 0x3000,
        )
        checks = _flash_checks(
            initial,
            expected,
            app_blocks,
            flash_base=DEFAULT_FLASH_BASE,
            loader_region_size=0x1000,
            selected_path="/pico1-apps/test.uf2",
            flash_end=DEFAULT_FLASH_BASE + 0x3000,
        )
        self.assertTrue(checks["exact_loader_model"])
        self.assertTrue(checks["boot2_unchanged"])
        self.assertTrue(checks["loader_region_unchanged"])
        mutated = bytearray(expected)
        mutated[-0x1000] ^= 1
        bad = _flash_checks(
            initial,
            bytes(mutated),
            app_blocks,
            flash_base=DEFAULT_FLASH_BASE,
            loader_region_size=0x1000,
            selected_path="/pico1-apps/test.uf2",
            flash_end=DEFAULT_FLASH_BASE + 0x3000,
        )
        self.assertFalse(bad["exact_loader_model"])
        self.assertFalse(bad["loader_region_unchanged"])


if __name__ == "__main__":
    unittest.main()
