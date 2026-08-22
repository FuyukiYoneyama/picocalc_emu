#!/usr/bin/env python3
"""Validate RP2040 UF2 files and assemble a deterministic raw flash image.

The firmware runner consumes a raw XIP flash image, not a UF2 container.  This
module is the small host-side boundary used by the U6 conformance flow.  It
does not execute or interpret firmware; it only validates UF2 block metadata
and places payloads at their declared XIP addresses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


UF2_BLOCK_SIZE = 512
UF2_HEADER_SIZE = 32
UF2_PAYLOAD_OFFSET = 32
UF2_PAYLOAD_MAX = 476
UF2_TRAILER_OFFSET = 508

MAGIC_START0 = 0x0A324655
MAGIC_START1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30

UF2_FLAG_NOT_MAIN_FLASH = 0x0000_0001
UF2_FLAG_FILE_CONTAINER = 0x0000_1000
UF2_FLAG_FAMILY_ID_PRESENT = 0x0000_2000

RP2040_FAMILY_ID = 0xE48B_FF56
DEFAULT_FLASH_BASE = 0x1000_0000
DEFAULT_FLASH_SIZE = 2 * 1024 * 1024
MAX_UF2_BLOCKS = 1_000_000


class Uf2ImageError(Exception):
    """An expected, user-correctable UF2 or output-image error."""


@dataclass(frozen=True)
class Uf2Block:
    index: int
    flags: int
    target_address: int
    payload: bytes
    block_number: int
    block_count: int
    file_size_or_family: int
    family_id: Optional[int]

    @property
    def end_address(self) -> int:
        return self.target_address + len(self.payload)

    @property
    def is_main_flash(self) -> bool:
        return not bool(self.flags & UF2_FLAG_NOT_MAIN_FLASH)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_path(path: Path, description: str) -> Path:
    """Reject symlink path components before opening a UF2/output file."""
    absolute = Path(os.path.abspath(path))
    components: List[Path] = []
    current = absolute
    while True:
        components.append(current)
        if current.parent == current:
            break
        current = current.parent
    for component in reversed(components):
        if component.is_symlink():
            raise Uf2ImageError(f"{description} must not pass through a symlink: {component}")
    return absolute


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def parse_uf2(
    input_path: Path,
    *,
    expected_family_id: Optional[int] = RP2040_FAMILY_ID,
    require_family_id: bool = True,
) -> List[Uf2Block]:
    """Parse and validate all UF2 blocks in ``input_path``.

    Validation is intentionally strict for firmware inputs: every block must
    have the same declared count, block numbers must be unique and contiguous,
    payloads must be word-sized, and family IDs must be present and consistent
    unless the caller explicitly opts out.
    """
    input_path = _canonical_path(Path(input_path), "UF2 input")
    if not input_path.is_file():
        raise Uf2ImageError(f"UF2 input is not a regular file: {input_path}")
    try:
        data = input_path.read_bytes()
    except OSError as error:
        raise Uf2ImageError(f"cannot read UF2 input {input_path}: {error}") from error
    if not data:
        raise Uf2ImageError("UF2 input is empty")
    if len(data) % UF2_BLOCK_SIZE:
        raise Uf2ImageError(
            f"UF2 size must be a multiple of {UF2_BLOCK_SIZE} bytes (got {len(data)})"
        )

    blocks: List[Uf2Block] = []
    declared_count: Optional[int] = None
    family_ids: set[int] = set()
    for index in range(len(data) // UF2_BLOCK_SIZE):
        chunk = data[index * UF2_BLOCK_SIZE : (index + 1) * UF2_BLOCK_SIZE]
        if _u32(chunk, 0) != MAGIC_START0 or _u32(chunk, 4) != MAGIC_START1:
            raise Uf2ImageError(f"block {index} has invalid UF2 start magic")
        if _u32(chunk, UF2_TRAILER_OFFSET) != MAGIC_END:
            raise Uf2ImageError(f"block {index} has invalid UF2 end magic")

        flags = _u32(chunk, 8)
        target_address = _u32(chunk, 12)
        payload_size = _u32(chunk, 16)
        block_number = _u32(chunk, 20)
        block_count = _u32(chunk, 24)
        file_size_or_family = _u32(chunk, 28)

        if payload_size == 0 or payload_size > UF2_PAYLOAD_MAX:
            raise Uf2ImageError(
                f"block {index} payload size {payload_size} is outside 1..{UF2_PAYLOAD_MAX}"
            )
        if payload_size % 4:
            raise Uf2ImageError(f"block {index} payload size is not 4-byte aligned")
        if block_count == 0 or block_count > MAX_UF2_BLOCKS:
            raise Uf2ImageError(f"block {index} has invalid block count {block_count}")
        if block_number >= block_count:
            raise Uf2ImageError(
                f"block {index} number {block_number} is outside block count {block_count}"
            )
        if declared_count is None:
            declared_count = block_count
        elif block_count != declared_count:
            raise Uf2ImageError(
                f"block {index} declares {block_count} blocks; expected {declared_count}"
            )

        family_id: Optional[int]
        if flags & UF2_FLAG_FAMILY_ID_PRESENT:
            family_id = file_size_or_family
            family_ids.add(family_id)
            if expected_family_id is not None and family_id != expected_family_id:
                raise Uf2ImageError(
                    f"block {index} family ID {family_id:#010x} does not match "
                    f"expected {expected_family_id:#010x}"
                )
        else:
            family_id = None
            if require_family_id:
                raise Uf2ImageError(f"block {index} has no RP2040 family ID")

        payload = bytes(chunk[UF2_PAYLOAD_OFFSET : UF2_PAYLOAD_OFFSET + payload_size])
        blocks.append(
            Uf2Block(
                index=index,
                flags=flags,
                target_address=target_address,
                payload=payload,
                block_number=block_number,
                block_count=block_count,
                file_size_or_family=file_size_or_family,
                family_id=family_id,
            )
        )

    assert declared_count is not None
    if len(blocks) != declared_count:
        raise Uf2ImageError(
            f"UF2 contains {len(blocks)} blocks but declares {declared_count}"
        )
    numbers = sorted(block.block_number for block in blocks)
    if numbers != list(range(declared_count)):
        raise Uf2ImageError("UF2 block numbers are not a unique contiguous sequence")
    if len(family_ids) > 1:
        raise Uf2ImageError("UF2 blocks contain inconsistent family IDs")
    return sorted(blocks, key=lambda block: block.block_number)


def _check_flash_ranges(
    blocks: Sequence[Uf2Block],
    *,
    flash_base: int,
    flash_size: int,
    allow_nonflash: bool,
) -> None:
    if flash_base < 0 or flash_base > 0xFFFF_FFFF:
        raise Uf2ImageError(f"flash base is outside the 32-bit address space: {flash_base:#x}")
    if flash_size <= 0:
        raise Uf2ImageError("flash size must be positive")
    flash_end = flash_base + flash_size
    if flash_end > 0x1_0000_0000:
        raise Uf2ImageError("flash base plus size overflows the 32-bit address space")

    ranges: List[tuple[int, int, int]] = []
    for block in blocks:
        if not block.is_main_flash:
            if not allow_nonflash:
                raise Uf2ImageError(
                    f"block {block.block_number} is marked NOT_MAIN_FLASH; it cannot be assembled"
                )
            continue
        if block.target_address < flash_base or block.end_address > flash_end:
            raise Uf2ImageError(
                f"block {block.block_number} target range "
                f"[{block.target_address:#010x}, {block.end_address:#010x}) "
                f"is outside flash [{flash_base:#010x}, {flash_end:#010x})"
            )
        if block.target_address % 4:
            raise Uf2ImageError(
                f"block {block.block_number} target address is not 4-byte aligned"
            )
        ranges.append((block.target_address, block.end_address, block.block_number))

    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] < previous[1]:
            raise Uf2ImageError(
                f"UF2 payload ranges overlap: blocks {previous[2]} and {current[2]}"
            )


def _block_report(block: Uf2Block) -> Dict[str, object]:
    return {
        "block_number": block.block_number,
        "source_index": block.index,
        "flags": block.flags,
        "target_address": f"0x{block.target_address:08x}",
        "payload_bytes": len(block.payload),
        "payload_sha256": _sha256_bytes(block.payload),
        "family_id": None if block.family_id is None else f"0x{block.family_id:08x}",
        "not_main_flash": not block.is_main_flash,
    }


def inspect_uf2(
    input_path: Path,
    *,
    expected_family_id: Optional[int] = RP2040_FAMILY_ID,
    require_family_id: bool = True,
) -> Dict[str, object]:
    input_path = _canonical_path(Path(input_path), "UF2 input")
    blocks = parse_uf2(
        input_path,
        expected_family_id=expected_family_id,
        require_family_id=require_family_id,
    )
    payload_bytes = sum(len(block.payload) for block in blocks if block.is_main_flash)
    ranges = [
        (block.target_address, block.end_address)
        for block in blocks
        if block.is_main_flash
    ]
    family_ids = sorted(
        {block.family_id for block in blocks if block.family_id is not None}
    )
    return {
        "schema_version": 1,
        "operation": "inspect",
        "input": {
            # Reports may be copied into public provenance records. Keep
            # machine-local directory names out of them; the SHA is the
            # identity of the input.
            "name": input_path.name,
            "bytes": input_path.stat().st_size,
            "sha256": _sha256_file(input_path),
        },
        "family_ids": [f"0x{family_id:08x}" for family_id in family_ids],
        "block_count": len(blocks),
        "main_flash_payload_bytes": payload_bytes,
        "main_flash_address_min": (
            None if not ranges else f"0x{min(start for start, _ in ranges):08x}"
        ),
        "main_flash_address_max_exclusive": (
            None if not ranges else f"0x{max(end for _, end in ranges):08x}"
        ),
        "blocks": [_block_report(block) for block in blocks],
    }


def assemble_flash(
    input_path: Path,
    output_path: Path,
    *,
    flash_base: int = DEFAULT_FLASH_BASE,
    flash_size: int = DEFAULT_FLASH_SIZE,
    fill_byte: int = 0xFF,
    expected_family_id: Optional[int] = RP2040_FAMILY_ID,
    require_family_id: bool = True,
    force: bool = False,
) -> Dict[str, object]:
    """Assemble a UF2 into a raw XIP flash image atomically."""
    input_path = _canonical_path(Path(input_path), "UF2 input")
    output_path = _canonical_path(Path(output_path), "raw flash output")
    if _same_path(input_path, output_path):
        raise Uf2ImageError("raw flash output must differ from UF2 input")
    if output_path.exists() and not force:
        raise Uf2ImageError(
            f"raw flash output already exists (use --force only when intentional): {output_path}"
        )
    if not 0 <= fill_byte <= 0xFF:
        raise Uf2ImageError("fill byte must be in 0..255")

    blocks = parse_uf2(
        input_path,
        expected_family_id=expected_family_id,
        require_family_id=require_family_id,
    )
    _check_flash_ranges(
        blocks,
        flash_base=flash_base,
        flash_size=flash_size,
        allow_nonflash=False,
    )

    image = bytearray([fill_byte]) * flash_size
    for block in blocks:
        offset = block.target_address - flash_base
        image[offset : offset + len(block.payload)] = block.payload

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=output_path.name + ".tmp-", dir=output_path.parent
    )
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as stream:
            stream.write(image)
            stream.flush()
            os.fsync(stream.fileno())
        if output_path.exists() and not force:
            raise Uf2ImageError(f"raw flash output appeared during assembly: {output_path}")
        os.replace(temporary, output_path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise

    report = inspect_uf2(
        input_path,
        expected_family_id=expected_family_id,
        require_family_id=require_family_id,
    )
    report.update(
        {
            "operation": "assemble",
            "flash": {
                "base": f"0x{flash_base:08x}",
                "size_bytes": flash_size,
                "fill_byte": f"0x{fill_byte:02x}",
                "output_name": output_path.name,
                "output_sha256": _sha256_bytes(bytes(image)),
            },
        }
    )
    return report


def _int_value(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from error


def _family_value(value: str) -> Optional[int]:
    if value.lower() in {"none", "off", "any"}:
        return None
    number = _int_value(value)
    if not 0 <= number <= 0xFFFF_FFFF:
        raise argparse.ArgumentTypeError("family ID must fit in 32 bits")
    return number


def _write_report(report: Dict[str, object], path: Optional[Path]) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(text, end="")
        return
    path = _canonical_path(Path(path), "JSON report")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".tmp-", dir=path.parent
    )
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def add_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "uf2", help="validate UF2 files and assemble raw XIP flash images"
    )
    commands = parser.add_subparsers(dest="uf2_command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--family-id",
        type=_family_value,
        default=RP2040_FAMILY_ID,
        help="expected UF2 family ID (default: RP2040 0xe48bff56; use none to disable)",
    )
    common.add_argument(
        "--allow-missing-family",
        action="store_true",
        help="allow UF2 blocks without the family-ID flag (not recommended for U6)",
    )
    inspect = commands.add_parser("inspect", parents=[common], help="validate and report UF2 metadata")
    inspect.add_argument("input_uf2", type=Path)
    inspect.add_argument("--json", dest="json_path", type=Path)

    assemble = commands.add_parser(
        "assemble", parents=[common], help="assemble UF2 payloads into a raw XIP flash image"
    )
    assemble.add_argument("input_uf2", type=Path)
    assemble.add_argument("output_flash", type=Path)
    assemble.add_argument("--flash-base", type=_int_value, default=DEFAULT_FLASH_BASE)
    assemble.add_argument("--flash-size-mib", type=int, default=2)
    assemble.add_argument("--fill-byte", type=_int_value, default=0xFF)
    assemble.add_argument("--force", action="store_true", help="replace an existing output explicitly")
    assemble.add_argument("--json", dest="json_path", type=Path)

    # Keep the strict U6 runner gate in its own module so this low-level UF2
    # parser remains usable without importing subprocess-heavy code.  The
    # subparser is registered here to make `picocalc.py uf2 e2e` the documented
    # entry point rather than leaving a second, easy-to-miss command beside it.
    from uf2_e2e import add_cli as add_e2e_cli

    add_e2e_cli(commands)


def run_cli(args: argparse.Namespace) -> int:
    if args.uf2_command == "e2e":
        from uf2_e2e import run_cli as run_e2e_cli

        return run_e2e_cli(args)
    try:
        require_family = not args.allow_missing_family and args.family_id is not None
        if args.uf2_command == "inspect":
            report = inspect_uf2(
                args.input_uf2,
                expected_family_id=args.family_id,
                require_family_id=require_family,
            )
        elif args.uf2_command == "assemble":
            if args.flash_size_mib <= 0:
                raise Uf2ImageError("--flash-size-mib must be positive")
            report = assemble_flash(
                args.input_uf2,
                args.output_flash,
                flash_base=args.flash_base,
                flash_size=args.flash_size_mib * 1024 * 1024,
                fill_byte=args.fill_byte,
                expected_family_id=args.family_id,
                require_family_id=require_family,
                force=args.force,
            )
        else:
            raise Uf2ImageError("a UF2 subcommand is required")
        _write_report(report, args.json_path)
        return 0
    except (Uf2ImageError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="picocalc-uf2")
    commands = parser.add_subparsers(dest="command", required=True)
    add_cli(commands)
    args = parser.parse_args()
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
