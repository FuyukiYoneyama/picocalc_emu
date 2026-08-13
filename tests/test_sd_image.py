import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import sd_image
from sd_image import SdImageError, extract_tree, pack_tree


ROOT = Path(__file__).resolve().parents[1]
PICOCALC = ROOT / "tools/picocalc.py"


def _write_fixture(root: Path, reverse: bool = False) -> None:
    files = [
        ("BOOT2040.UF2", b"boot\n"),
        ("pico1-apps/Long File Name.uf2", b"long-name\n"),
        ("pico1-apps/日本語データ.txt", "unicode\n".encode("utf-8")),
        ("pico1-apps/Empty Dir/.keep", b""),
        ("pico1-apps/zero.bin", b""),
    ]
    if reverse:
        files.reverse()
    for relative, content in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _tree_manifest(root: Path):
    result = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().casefold()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result.append((relative, "directory", None))
        else:
            result.append((relative, "file", path.read_bytes()))
    return result


class SdImageToolTests(unittest.TestCase):
    def test_fat32_and_fat16_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-sd-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            _write_fixture(source)
            expected = _tree_manifest(source)
            for fat_type in ("fat32", "fat16"):
                image = root / f"{fat_type}.img"
                extracted = root / f"{fat_type}-out"
                report = pack_tree(source, image, fat_type=fat_type, size_mib=64)
                self.assertEqual(report["format"], fat_type)
                self.assertEqual(report["image_bytes"], 64 * 1024 * 1024)
                restored = extract_tree(image, extracted)
                self.assertEqual(restored["format"], fat_type)
                self.assertEqual(_tree_manifest(extracted), expected)

    def test_pack_is_deterministic_independent_of_creation_order(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-sd-test-") as temporary:
            root = Path(temporary)
            left = root / "left"
            right = root / "right"
            _write_fixture(left, reverse=False)
            _write_fixture(right, reverse=True)
            left_image = root / "left.img"
            right_image = root / "right.img"
            left_report = pack_tree(left, left_image, size_mib=64)
            right_report = pack_tree(right, right_image, size_mib=64)
            self.assertEqual(left_image.read_bytes(), right_image.read_bytes())
            self.assertEqual(left_report["image_sha256"], right_report["image_sha256"])
            self.assertEqual(left_report["tree_sha256"], right_report["tree_sha256"])

    def test_cli_pack_extract_and_json_reports(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-sd-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            _write_fixture(source)
            image = root / "input.img"
            extracted = root / "output"
            packed = subprocess.run(
                [sys.executable, str(PICOCALC), "sd", "pack", str(source), str(image)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(packed.returncode, 0, packed.stderr)
            pack_report = json.loads(packed.stdout)
            self.assertEqual(pack_report["operation"], "pack")
            extracted_result = subprocess.run(
                [sys.executable, str(PICOCALC), "sd", "extract", str(image), str(extracted)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(extracted_result.returncode, 0, extracted_result.stderr)
            extract_report = json.loads(extracted_result.stdout)
            self.assertEqual(extract_report["operation"], "extract")
            self.assertEqual(_tree_manifest(extracted), _tree_manifest(source))

    def test_rejects_symlinks_case_collisions_and_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-sd-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "A").write_bytes(b"a")
            (source / "a").write_bytes(b"a")
            with self.assertRaises(SdImageError):
                pack_tree(source, root / "collision.img")

            valid = root / "valid"
            _write_fixture(valid)
            image = root / "valid.img"
            pack_tree(valid, image)
            with self.assertRaises(SdImageError):
                pack_tree(valid, image)

            symlink_source = root / "symlink-source"
            symlink_source.mkdir()
            target = root / "target.txt"
            target.write_text("target", encoding="utf-8")
            try:
                (symlink_source / "link.txt").symlink_to(target)
            except (NotImplementedError, OSError):
                symlink_source = None
            if symlink_source is not None:
                with self.assertRaises(SdImageError):
                    pack_tree(symlink_source, root / "symlink.img")

                root_link = root / "root-link"
                root_link.symlink_to(valid, target_is_directory=True)
                with self.assertRaises(SdImageError):
                    pack_tree(root_link, root / "root-link.img")

                output_parent = root / "output-parent"
                output_parent.symlink_to(root, target_is_directory=True)
                with self.assertRaises(SdImageError):
                    pack_tree(valid, output_parent / "unsafe.img")

    def test_extract_is_fail_closed_for_destination_and_malformed_image(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-sd-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            _write_fixture(source)
            image = root / "valid.img"
            pack_tree(source, image)
            try:
                image_link = root / "image-link.img"
                image_link.symlink_to(image)
                with self.assertRaises(SdImageError):
                    extract_tree(image_link, root / "link-out")
                output_link = root / "output-link"
                output_target = root / "output-target"
                output_target.mkdir()
                output_link.symlink_to(output_target, target_is_directory=True)
                with self.assertRaises(SdImageError):
                    extract_tree(image, output_link)
            except (NotImplementedError, OSError):
                pass

            # Corrupt the second FAT copy.  A valid image must never silently
            # choose one copy when the card contains two conflicting copies.
            corrupt = root / "fat-copy-corrupt.img"
            corrupt.write_bytes(image.read_bytes())
            with corrupt.open("r+b") as stream:
                stream.seek((32 + 1024) * 512 + 20)
                value = stream.read(1)
                stream.seek((32 + 1024) * 512 + 20)
                stream.write(bytes([value[0] ^ 0x01]))
            with self.assertRaises(SdImageError):
                extract_tree(corrupt, root / "fat-copy-out")

            existing = root / "existing"
            existing.mkdir()
            (existing / "keep").write_text("keep", encoding="utf-8")
            with self.assertRaises(SdImageError):
                extract_tree(image, existing)
            self.assertEqual((existing / "keep").read_text(encoding="utf-8"), "keep")

            malformed = root / "malformed.img"
            malformed.write_bytes(image.read_bytes()[:512])
            destination = root / "malformed-out"
            with self.assertRaises(SdImageError):
                extract_tree(malformed, destination)
            self.assertFalse(destination.exists())

    def test_changed_source_is_rejected_before_publish(self):
        with tempfile.TemporaryDirectory(prefix="picocalc-sd-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            _write_fixture(source)
            image = root / "input.img"

            original = source / "BOOT2040.UF2"
            real_open_regular_source = sd_image._open_regular_source
            calls = 0

            def mutate_after_scan(path: Path):
                nonlocal calls
                calls += 1
                if calls == 1:
                    original.write_bytes(b"changed while packing is prohibited")
                return real_open_regular_source(path)

            with mock.patch.object(sd_image, "_open_regular_source", side_effect=mutate_after_scan):
                with self.assertRaises(SdImageError):
                    pack_tree(source, image)
            self.assertFalse(image.exists())


if __name__ == "__main__":
    unittest.main()
