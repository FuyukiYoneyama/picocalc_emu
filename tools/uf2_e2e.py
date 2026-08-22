#!/usr/bin/env python3
"""Run and judge the local UF2Loader end-to-end gate.

This is deliberately a host-side gate, not another UF2 loader.  The external
``uf2loader`` firmware remains the authority for selecting and programming an
application; this module supplies deterministic inputs, runs the real runner
three times, and checks the complete flash/SD/report boundary.

The gate is intentionally explicit about the two UF2 roles:

* ``bootloader.uf2`` is assembled into the initial XIP flash image;
* ``loader.uf2`` is the SRAM ``BOOT2040.UF2`` file read by stage3; and
* ``app.uf2`` is the selected application written by the loader.

It never treats a final screen alone as success.  A passing result requires
strict UF2 metadata, a watchdog reset, a second boot epoch, exact report and
trace determinism, NOR readback (including the loader's documented proginfo
mutation), and invariant boot/loader regions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sd_image import SdImageError, pack_tree
from uf2_image import (
    DEFAULT_FLASH_BASE,
    DEFAULT_FLASH_SIZE,
    Uf2Block,
    Uf2ImageError,
    assemble_flash,
    parse_uf2,
)


UF2_PAGE_SIZE = 256
FLASH_SECTOR_SIZE = 4096
RP2040_SRAM_BASE = 0x2000_0000
RP2040_SRAM_END = 0x2004_2000
PROGINFO_OFFSET = 0x110
PROGINFO_SIZE = 28  # magic + flash_end + RP2040's 20-byte filename
PROGINFO_MAGIC = 0xE98C_C638
DEFAULT_LOADER_REGION_SIZE = 16 * 1024
DEFAULT_SELECTED_PATH = "/pico1-apps/test.uf2"


class Uf2E2eError(Exception):
    """A setup or judged-gate failure with a user-actionable message."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n")


def _require_file(path: Path, description: str) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise Uf2E2eError(f"{description} is not a regular file: {path}")
    return path


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise Uf2E2eError(f"cannot run git for {repo}: {error}") from error
    if result.returncode != 0:
        raise Uf2E2eError(f"git {' '.join(args)} failed for {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def _assert_clean_repo(repo: Path, expected_commit: str, description: str) -> None:
    actual = _git(repo, "rev-parse", "HEAD")
    if actual != expected_commit:
        raise Uf2E2eError(f"{description} HEAD {actual} does not match expected {expected_commit}")
    status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise Uf2E2eError(f"{description} checkout is not clean; U6 evidence cannot use a dirty build")


def _validate_payload_blocks(blocks: Sequence[Uf2Block], role: str) -> None:
    if not blocks:
        raise Uf2E2eError(f"{role} UF2 contains no blocks")
    if any(len(block.payload) != UF2_PAGE_SIZE for block in blocks):
        raise Uf2E2eError(f"{role} UF2 must use 256-byte payload blocks")
    if any(block.target_address % UF2_PAGE_SIZE for block in blocks):
        raise Uf2E2eError(f"{role} UF2 contains an unaligned target address")
    ranges = sorted(
        (block.target_address, block.end_address, block.block_number) for block in blocks
    )
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] < previous[1]:
            raise Uf2E2eError(
                f"{role} UF2 payload ranges overlap: blocks {previous[2]} and {current[2]}"
            )


def _validate_loader_uf2(path: Path) -> Dict[str, Any]:
    blocks = parse_uf2(path)
    _validate_payload_blocks(blocks, "BOOT2040")
    if any(not block.is_main_flash for block in blocks):
        raise Uf2E2eError("BOOT2040.UF2 contains a NOT_MAIN_FLASH block")
    if blocks[0].target_address != RP2040_SRAM_BASE:
        raise Uf2E2eError("BOOT2040.UF2 must start at RP2040 SRAM base")
    if any(
        block.target_address < RP2040_SRAM_BASE
        or block.end_address > RP2040_SRAM_END
        for block in blocks
    ):
        raise Uf2E2eError("BOOT2040.UF2 contains a target outside RP2040 SRAM")
    return {
        "name": path.name,
        "sha256": _sha256_file(path),
        "block_count": len(blocks),
        "first_address": f"0x{blocks[0].target_address:08x}",
        "last_address_exclusive": f"0x{max(block.end_address for block in blocks):08x}",
    }


def _validate_app_uf2(path: Path, flash_base: int, flash_size: int) -> List[Uf2Block]:
    blocks = parse_uf2(path)
    _validate_payload_blocks(blocks, "application")
    if any(not block.is_main_flash for block in blocks):
        raise Uf2E2eError("application UF2 contains a NOT_MAIN_FLASH block")
    if blocks[0].target_address != flash_base:
        raise Uf2E2eError("application UF2 must contain block 0 at XIP flash base")
    flash_end = flash_base + flash_size
    if any(
        block.target_address < flash_base or block.end_address > flash_end for block in blocks
    ):
        raise Uf2E2eError("application UF2 contains a target outside the attached flash")
    return list(blocks)


def _assemble_initial(bootloader_uf2: Path, output: Path, flash_size: int) -> Dict[str, Any]:
    try:
        return assemble_flash(bootloader_uf2, output, flash_size=flash_size)
    except (Uf2ImageError, OSError, UnicodeError) as error:
        raise Uf2E2eError(f"cannot assemble initial flash from bootloader UF2: {error}") from error


def _expected_loader_flash(
    initial: bytes,
    app_blocks: Sequence[Uf2Block],
    *,
    flash_base: int,
    loader_region_size: int,
    selected_path: str,
    flash_end: Optional[int],
) -> bytes:
    """Model only the deterministic RP2040 operations made by ``ui/uf2.c``.

    The first application block is special: uf2loader erases sector 0, restores
    the existing boot2 and deliberately does not program the application's
    block-0 payload.  Later blocks erase each sector once and program with NOR
    ``old & new`` semantics.  The final page receives the loader's documented
    28-byte proginfo mutation.
    """

    image = bytearray(initial)
    erased: set[int] = set()
    boot2 = bytes(initial[:UF2_PAGE_SIZE])
    for block in app_blocks:
        offset = block.target_address - flash_base
        sector = offset // FLASH_SECTOR_SIZE
        if offset == 0:
            if sector not in erased:
                base = sector * FLASH_SECTOR_SIZE
                image[base : base + FLASH_SECTOR_SIZE] = b"\xff" * FLASH_SECTOR_SIZE
                image[:UF2_PAGE_SIZE] = boot2
                erased.add(sector)
            continue
        if sector not in erased:
            base = sector * FLASH_SECTOR_SIZE
            image[base : base + FLASH_SECTOR_SIZE] = b"\xff" * FLASH_SECTOR_SIZE
            erased.add(sector)
        payload = bytearray(block.payload)
        overlap_start = max(offset, PROGINFO_OFFSET)
        overlap_end = min(offset + len(payload), PROGINFO_OFFSET + PROGINFO_SIZE)
        if overlap_start < overlap_end:
            payload[overlap_start - offset : overlap_end - offset] = b"\xff" * (
                overlap_end - overlap_start
            )
        for index, value in enumerate(payload):
            image[offset + index] &= value

    if flash_end is None:
        flash_end = flash_base + len(image) - loader_region_size
    if not flash_base < flash_end <= flash_base + len(image):
        raise Uf2E2eError("--flash-end must fall inside the attached flash")
    filename = selected_path.encode("ascii")
    if len(filename) > 20:
        raise Uf2E2eError("selected path must fit uf2loader's 20-byte RP2040 proginfo field")
    proginfo = bytearray(image[PROGINFO_OFFSET : PROGINFO_OFFSET + PROGINFO_SIZE])
    proginfo[0:4] = PROGINFO_MAGIC.to_bytes(4, "little")
    proginfo[4:8] = flash_end.to_bytes(4, "little")
    proginfo[8:28] = filename.ljust(20, b"\0")
    for index, value in enumerate(proginfo):
        image[PROGINFO_OFFSET + index] &= value
    return bytes(image)


def _changed_ranges(left: bytes, right: bytes) -> List[Tuple[int, int]]:
    changed = [index for index, (a, b) in enumerate(zip(left, right)) if a != b]
    if not changed:
        return []
    ranges: List[Tuple[int, int]] = []
    start = previous = changed[0]
    for index in changed[1:]:
        if index != previous + 1:
            ranges.append((start, previous))
            start = index
        previous = index
    ranges.append((start, previous))
    return ranges


def _merge_ranges(ranges: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    merged: List[Tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _flash_checks(
    initial: bytes,
    final: bytes,
    app_blocks: Sequence[Uf2Block],
    *,
    flash_base: int,
    loader_region_size: int,
    selected_path: str,
    flash_end: Optional[int],
) -> Dict[str, Any]:
    if len(initial) != len(final):
        raise Uf2E2eError("final flash size differs from initial flash")
    expected = _expected_loader_flash(
        initial,
        app_blocks,
        flash_base=flash_base,
        loader_region_size=loader_region_size,
        selected_path=selected_path,
        flash_end=flash_end,
    )
    exact = final == expected
    boot2_unchanged = final[:UF2_PAGE_SIZE] == initial[:UF2_PAGE_SIZE]
    loader_start = len(initial) - loader_region_size
    loader_unchanged = final[loader_start:] == initial[loader_start:]
    app_ranges = _merge_ranges(
        (b.target_address - flash_base, b.end_address - flash_base) for b in app_blocks
    )
    expected_proginfo = (
        PROGINFO_OFFSET,
        PROGINFO_OFFSET + PROGINFO_SIZE,
    )
    diffs = _changed_ranges(expected, final)
    proginfo = final[PROGINFO_OFFSET : PROGINFO_OFFSET + PROGINFO_SIZE]
    filename = proginfo[8:28].split(b"\0", 1)[0].decode("ascii", errors="replace")
    return {
        "exact_loader_model": exact,
        "final_sha256": _sha256_bytes(final),
        "initial_sha256": _sha256_bytes(initial),
        "boot2_unchanged": boot2_unchanged,
        "loader_region_unchanged": loader_unchanged,
        "loader_region": {
            "start": f"0x{loader_start + flash_base:08x}",
            "bytes": loader_region_size,
        },
        "application_ranges": [
            {"start": f"0x{start + flash_base:08x}", "end_exclusive": f"0x{end + flash_base:08x}"}
            for start, end in app_ranges
        ],
        "proginfo_mutation_range": {
            "start": f"0x{PROGINFO_OFFSET + flash_base:08x}",
            "end_exclusive": f"0x{PROGINFO_OFFSET + PROGINFO_SIZE + flash_base:08x}",
        },
        "unexpected_diff_ranges": [
            {"start": f"0x{start + flash_base:08x}", "end": f"0x{end + flash_base:08x}"}
            for start, end in diffs
            if not (start >= expected_proginfo[0] and end < expected_proginfo[1])
        ],
        "proginfo": {
            "magic": f"0x{int.from_bytes(proginfo[0:4], 'little'):08x}",
            "flash_end": f"0x{int.from_bytes(proginfo[4:8], 'little'):08x}",
            "filename": filename,
            "filename_matches": filename == selected_path,
        },
        "expected_model_diff_count": sum(end - start + 1 for start, end in diffs),
    }


def _snapshot_app_pass(report: Dict[str, Any]) -> bool:
    steps = report.get("scenario", {}).get("steps", [])
    snapshots = [step for step in steps if step.get("op") == "snapshot"]
    return bool(snapshots) and snapshots[-1].get("status") == "pass" and snapshots[-1].get("detail", "").endswith("non-black pixels")


def _report_checks(report: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    equalities = {
        "schema_version": 8,
        "boot.mode": "boot2",
        "stop_reason": "scenario_done",
        "exception": None,
        "error": None,
        "verdict.status": "pass",
        "scenario.status": "pass",
        "flash.errors": [],
        "flash.unknown_commands": [],
        "sd.unknown_commands": [],
        "sd.blocks_written": 0,
        "keyboard.key_events_dropped": 0,
        "keyboard.key_events_overwritten": 0,
        "unsupported_mmio": [],
    }
    for path, expected in equalities.items():
        value: Any = report
        try:
            for component in path.split("."):
                value = value[component]
        except (KeyError, TypeError):
            failures.append(f"missing {path}")
            continue
        if value != expected:
            failures.append(f"{path} expected {expected!r}, got {value!r}")
    if len(report.get("watchdog_resets", [])) != 1:
        failures.append("watchdog_resets must contain exactly one warm reset")
    elif report["watchdog_resets"][0].get("epoch") != 1:
        failures.append("watchdog reset epoch must be 1")
    for path in ("flash.erase_count", "flash.program_count", "flash.program_bytes", "sd.commands_seen", "sd.blocks_read"):
        value: Any = report
        try:
            for component in path.split("."):
                value = value[component]
        except (KeyError, TypeError):
            failures.append(f"missing {path}")
            continue
        if not isinstance(value, int) or value <= 0:
            failures.append(f"{path} must be positive, got {value!r}")
    if report.get("sd", {}).get("raw_image", {}).get("dirty_blocks") != 0:
        failures.append("SD backing changed during loader run")
    if report.get("framebuffer", {}).get("non_black_pixels", 0) <= 0:
        failures.append("final framebuffer is empty")
    if not _snapshot_app_pass(report):
        failures.append("final application snapshot did not pass")
    return failures


def _run_one(
    index: int,
    *,
    output_root: Path,
    runner: Path,
    backend_dir: Path,
    initial_flash: Path,
    sd_image: Path,
    scenario: Path,
    bootrom: Optional[Path],
    backend_commit: str,
    cycles: int,
    quantum: int,
    lcd_variant: str,
) -> Dict[str, Any]:
    run_dir = output_root / f"run-{index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"
    final_flash_path = run_dir / "final.bin"
    final_sd_path = run_dir / "final.sd.img"
    trace_path = run_dir / "sd-trace.json"
    uart_path = run_dir / "uart.bin"
    snapshots = run_dir / "snapshots"
    command = [
        str(runner),
        "--bin",
        str(initial_flash),
        "--boot-mode",
        "boot2",
        "--board",
        "picocalc",
        "--lcd-variant",
        lcd_variant,
        "--quantum",
        str(quantum),
        "--cycles",
        str(cycles),
        "--backend-commit",
        backend_commit,
        "--sd-image",
        str(sd_image),
        "--sd-image-out",
        str(final_sd_path),
        "--sd-trace",
        str(trace_path),
        "--keyboard",
        "--scenario",
        str(scenario),
        "--snapshot-dir",
        str(snapshots),
        "--uart",
        str(uart_path),
        "--json",
        str(report_path),
        "--flash-image-out",
        str(final_flash_path),
        "--expect-stop",
        "scenario_done",
    ]
    if bootrom is not None:
        command.extend(["--bootrom", str(bootrom)])
    try:
        result = subprocess.run(command, cwd=backend_dir, capture_output=True, text=True)
    except OSError as error:
        raise Uf2E2eError(f"cannot execute picocalc-run: {error}") from error
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    if not report_path.is_file():
        raise Uf2E2eError(f"run {index} produced no JSON report (exit {result.returncode})")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Uf2E2eError(f"run {index} report is unreadable: {error}") from error
    failures = _report_checks(report)
    if result.returncode != 0:
        failures.append(f"picocalc-run exit code was {result.returncode}")
    for required in (final_flash_path, final_sd_path, trace_path, uart_path):
        if not required.is_file():
            failures.append(f"missing run artifact {required.name}")
    if failures:
        raise Uf2E2eError(f"U6 run {index} failed: " + "; ".join(failures))
    final_flash = final_flash_path.read_bytes()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    return {
        "index": index,
        "report": report,
        "report_sha256": _sha256_bytes(_canonical_json(report)),
        "uart_sha256": _sha256_file(uart_path),
        "framebuffer_sha256": report["framebuffer"]["rgb565_sha256"],
        "flash_sha256": _sha256_file(final_flash_path),
        "sd_sha256": _sha256_file(final_sd_path),
        "sd_trace_sha256": trace.get("digest_sha256"),
        "sd_trace_event_count": trace.get("event_count"),
        "flash_path": str(final_flash_path),
        "flash_bytes": final_flash,
        "trace": trace,
        # Keep the manifest relocatable and safe to copy into a public
        # evidence record; the output directory itself is not provenance.
        "report_path": str(report_path.relative_to(output_root)),
    }


def _run_reattach(
    *,
    output_root: Path,
    runner: Path,
    backend_dir: Path,
    final_flash: Path,
    sd_image: Path,
    scenario: Path,
    bootrom: Optional[Path],
    backend_commit: str,
    cycles: int,
    quantum: int,
    lcd_variant: str,
) -> Dict[str, Any]:
    """Boot the exported image again without the loader selection step."""

    run_dir = output_root / "reattach"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"
    exported_flash = run_dir / "flash.bin"
    exported_sd = run_dir / "sd.img"
    trace_path = run_dir / "sd-trace.json"
    uart_path = run_dir / "uart.bin"
    snapshots = run_dir / "snapshots"
    command = [
        str(runner),
        "--bin",
        str(final_flash),
        "--boot-mode",
        "boot2",
        "--board",
        "picocalc",
        "--lcd-variant",
        lcd_variant,
        "--quantum",
        str(quantum),
        "--cycles",
        str(cycles),
        "--backend-commit",
        backend_commit,
        "--sd-image",
        str(sd_image),
        "--sd-image-out",
        str(exported_sd),
        "--sd-trace",
        str(trace_path),
        "--scenario",
        str(scenario),
        "--snapshot-dir",
        str(snapshots),
        "--uart",
        str(uart_path),
        "--json",
        str(report_path),
        "--flash-image-out",
        str(exported_flash),
        "--expect-stop",
        "scenario_done",
    ]
    if bootrom is not None:
        command.extend(["--bootrom", str(bootrom)])
    try:
        result = subprocess.run(command, cwd=backend_dir, capture_output=True, text=True)
    except OSError as error:
        raise Uf2E2eError(f"cannot execute reattach run: {error}") from error
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    if not report_path.is_file():
        raise Uf2E2eError("reattach run produced no JSON report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Uf2E2eError(f"reattach report is unreadable: {error}") from error
    failures: List[str] = []
    for path, expected in {
        "schema_version": 8,
        "boot.mode": "boot2",
        "stop_reason": "scenario_done",
        "exception": None,
        "error": None,
        "verdict.status": "pass",
        "scenario.status": "pass",
        "flash.errors": [],
        "flash.unknown_commands": [],
        "sd.unknown_commands": [],
        "sd.blocks_written": 0,
        "unsupported_mmio": [],
    }.items():
        value: Any = report
        try:
            for component in path.split("."):
                value = value[component]
        except (KeyError, TypeError):
            failures.append(f"reattach missing {path}")
            continue
        if value != expected:
            failures.append(f"reattach {path} expected {expected!r}, got {value!r}")
    if report.get("watchdog_resets"):
        failures.append("reattach unexpectedly triggered a watchdog reset")
    if report.get("framebuffer", {}).get("non_black_pixels", 0) <= 0:
        failures.append("reattach framebuffer is empty")
    if not _snapshot_app_pass(report):
        failures.append("reattach application snapshot did not pass")
    for required in (exported_flash, exported_sd, trace_path, uart_path):
        if not required.is_file():
            failures.append(f"reattach missing {required.name}")
    if result.returncode != 0:
        failures.append(f"reattach exit code was {result.returncode}")
    if failures:
        raise Uf2E2eError("U6 reattach failed: " + "; ".join(failures))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    return {
        "report_sha256": _sha256_bytes(_canonical_json(report)),
        "uart_sha256": _sha256_file(uart_path),
        "framebuffer_sha256": report["framebuffer"]["rgb565_sha256"],
        "flash_sha256": _sha256_file(exported_flash),
        "sd_sha256": _sha256_file(exported_sd),
        "sd_trace_sha256": trace.get("digest_sha256"),
        "sd_trace_event_count": trace.get("event_count"),
        "report_path": str(report_path.relative_to(output_root)),
    }


def run_gate(args: argparse.Namespace) -> Dict[str, Any]:
    backend = _require_file(args.runner, "runner")
    backend_dir = Path(args.backend_dir).resolve()
    if not backend_dir.is_dir():
        raise Uf2E2eError(f"backend checkout is not a directory: {backend_dir}")
    _assert_clean_repo(backend_dir, args.backend_commit, "backend")
    loader_source_dir = Path(args.loader_source_dir).resolve()
    if not loader_source_dir.is_dir():
        raise Uf2E2eError(f"uf2loader source checkout is not a directory: {loader_source_dir}")
    _assert_clean_repo(loader_source_dir, args.loader_source_commit, "uf2loader source")
    bootloader = _require_file(args.bootloader_uf2, "bootloader UF2")
    loader = _require_file(args.loader_uf2, "BOOT2040.UF2")
    app = _require_file(args.app_uf2, "application UF2")
    scenario = _require_file(args.scenario, "U6 scenario")
    reattach_scenario = _require_file(args.reattach_scenario, "U6 reattach scenario")
    bootrom = _require_file(args.bootrom, "bootrom") if args.bootrom else None

    if args.flash_size_mib <= 0:
        raise Uf2E2eError("--flash-size-mib must be positive")
    flash_size = args.flash_size_mib * 1024 * 1024
    initial_dir = Path(args.output).resolve()
    initial_dir.mkdir(parents=True, exist_ok=True)
    initial_flash = initial_dir / "initial.bin"
    boot_report = _assemble_initial(bootloader, initial_flash, flash_size)
    loader_report = _validate_loader_uf2(loader)
    app_blocks = _validate_app_uf2(app, DEFAULT_FLASH_BASE, flash_size)

    if args.sd_image and args.sd_dir:
        raise Uf2E2eError("choose exactly one of --sd-image and --sd-dir")
    sd_image = initial_dir / "input.sd.img"
    sd_manifest: Optional[Dict[str, Any]] = None
    if args.sd_dir:
        try:
            sd_manifest = pack_tree(Path(args.sd_dir).resolve(), sd_image, fat_type="fat32", size_mib=64, volume_label="PICOCALC")
        except (SdImageError, OSError, UnicodeError) as error:
            raise Uf2E2eError(f"cannot pack SD directory: {error}") from error
    elif args.sd_image:
        source = _require_file(args.sd_image, "SD image")
        shutil.copyfile(source, sd_image)
    else:
        raise Uf2E2eError("one of --sd-image or --sd-dir is required")
    sd_sha = _sha256_file(sd_image)

    initial = initial_flash.read_bytes()
    expected_flash = _expected_loader_flash(
        initial,
        app_blocks,
        flash_base=DEFAULT_FLASH_BASE,
        loader_region_size=args.loader_region_size,
        selected_path=args.selected_path,
        flash_end=args.flash_end,
    )
    if args.repetitions != 3:
        raise Uf2E2eError("U6 acceptance requires exactly 3 repetitions")
    run_results: List[Dict[str, Any]] = []
    for index in range(1, args.repetitions + 1):
        result = _run_one(
            index,
            output_root=initial_dir,
            runner=backend,
            backend_dir=backend_dir,
            initial_flash=initial_flash,
            sd_image=sd_image,
            scenario=scenario,
            bootrom=bootrom,
            backend_commit=args.backend_commit,
            cycles=args.cycles,
            quantum=args.quantum,
            lcd_variant=args.lcd_variant,
        )
        flash_checks = _flash_checks(
            initial,
            result["flash_bytes"],
            app_blocks,
            flash_base=DEFAULT_FLASH_BASE,
            loader_region_size=args.loader_region_size,
            selected_path=args.selected_path,
            flash_end=args.flash_end,
        )
        if not flash_checks["exact_loader_model"]:
            raise Uf2E2eError(f"U6 run {index} final flash does not match loader model")
        if not flash_checks["boot2_unchanged"] or not flash_checks["loader_region_unchanged"]:
            raise Uf2E2eError(f"U6 run {index} modified a protected loader region")
        if not flash_checks["proginfo"]["filename_matches"]:
            raise Uf2E2eError(f"U6 run {index} proginfo filename mutation is unexpected")
        if result["sd_sha256"] != sd_sha:
            raise Uf2E2eError(f"U6 run {index} changed the SD backing image")
        result["flash_checks"] = flash_checks
        run_results.append(result)

    reattach = _run_reattach(
        output_root=initial_dir,
        runner=backend,
        backend_dir=backend_dir,
        final_flash=Path(run_results[0]["flash_path"]),
        sd_image=sd_image,
        scenario=reattach_scenario,
        bootrom=bootrom,
        backend_commit=args.backend_commit,
        cycles=args.cycles,
        quantum=args.quantum,
        lcd_variant=args.lcd_variant,
    )
    if reattach["flash_sha256"] != run_results[0]["flash_sha256"]:
        raise Uf2E2eError("flash SHA changed during final-image reattach")
    if reattach["sd_sha256"] != sd_sha:
        raise Uf2E2eError("SD backing changed during final-image reattach")

    comparable = [
        {
            key: result[key]
            for key in (
                "report_sha256",
                "uart_sha256",
                "framebuffer_sha256",
                "flash_sha256",
                "sd_sha256",
                "sd_trace_sha256",
                "sd_trace_event_count",
            )
        }
        for result in run_results
    ]
    deterministic = all(item == comparable[0] for item in comparable[1:])
    if not deterministic:
        raise Uf2E2eError("the three U6 runs are not deterministic")
    manifest = {
        "schema_version": 1,
        "gate": "U6",
        "status": "pass",
        "repetitions": args.repetitions,
        "provenance": {
            "backend_commit": args.backend_commit,
            "backend_dir": backend_dir.name,
            "uf2loader_source_commit": args.loader_source_commit,
            "uf2loader_source_dir": loader_source_dir.name,
            "runner": backend.name,
            "runner_sha256": _sha256_file(backend),
            "bootloader_uf2": {"name": bootloader.name, "sha256": _sha256_file(bootloader)},
            "bootloader_assembly": boot_report.get("flash", {}),
            "loader_uf2": loader_report,
            "app_uf2": {
                "name": app.name,
                "sha256": _sha256_file(app),
                "block_count": len(app_blocks),
                "payload_bytes": sum(len(block.payload) for block in app_blocks),
            },
            "scenario": {"name": scenario.name, "sha256": _sha256_file(scenario)},
            "sd_image": {"name": sd_image.name, "sha256": sd_sha, "manifest": sd_manifest},
        },
        "acceptance": {
            "uf2_blocks_strict": True,
            "flash_readback_exact_loader_model": True,
            "boot2_unchanged": True,
            "loader_region_unchanged": True,
            "sd_trace_deterministic": True,
            "unknown_sd_commands": False,
            "flash_mutation_errors": False,
            "three_run_deterministic": deterministic,
            "watchdog_resets_per_run": 1,
            "final_flash_reattach": True,
            "expected_proginfo_mutation": {
                "range": {
                    "start": f"0x{DEFAULT_FLASH_BASE + PROGINFO_OFFSET:08x}",
                    "end_exclusive": f"0x{DEFAULT_FLASH_BASE + PROGINFO_OFFSET + PROGINFO_SIZE:08x}",
                },
                "reason": "uf2loader writes magic, flash_end and selected filename",
            },
        },
        "runs": [
            {
                key: result[key]
                for key in (
                    "index",
                    "report_sha256",
                    "uart_sha256",
                    "framebuffer_sha256",
                    "flash_sha256",
                    "sd_sha256",
                    "sd_trace_sha256",
                    "sd_trace_event_count",
                    "flash_checks",
                    "report_path",
                )
            }
            for result in run_results
        ],
        "reattach": reattach,
    }
    _write_json(initial_dir / "u6-gate.json", manifest)
    return manifest


def add_cli(parser: argparse._SubParsersAction) -> None:
    gate = parser.add_parser("e2e", help="run the strict three-run UF2Loader U6 gate")
    gate.add_argument("--runner", type=Path, required=True, help="picocalc-run binary")
    gate.add_argument("--backend-dir", type=Path, required=True, help="clean backend checkout")
    gate.add_argument("--backend-commit", required=True, help="exact backend HEAD and compile identity")
    gate.add_argument("--loader-source-dir", type=Path, required=True, help="clean external uf2loader checkout")
    gate.add_argument("--loader-source-commit", required=True, help="exact external uf2loader source commit")
    gate.add_argument("--bootloader-uf2", type=Path, required=True)
    gate.add_argument("--loader-uf2", type=Path, required=True, help="SD BOOT2040.UF2")
    gate.add_argument("--app-uf2", type=Path, required=True, help="selected SD application UF2")
    source = gate.add_mutually_exclusive_group(required=True)
    source.add_argument("--sd-image", type=Path)
    source.add_argument("--sd-dir", type=Path)
    gate.add_argument("--scenario", type=Path, required=True)
    gate.add_argument("--reattach-scenario", type=Path, required=True)
    gate.add_argument("--bootrom", type=Path)
    gate.add_argument("--output", type=Path, required=True)
    gate.add_argument("--flash-size-mib", type=int, default=2)
    gate.add_argument("--loader-region-size", type=int, default=DEFAULT_LOADER_REGION_SIZE)
    gate.add_argument("--flash-end", type=lambda value: int(value, 0))
    gate.add_argument("--selected-path", default=DEFAULT_SELECTED_PATH)
    gate.add_argument("--cycles", type=int, default=1_500_000_000)
    gate.add_argument("--quantum", type=int, default=16)
    gate.add_argument("--lcd-variant", choices=("hwspi-rgb888", "pio-rgb565"), default="hwspi-rgb888")
    gate.add_argument("--repetitions", type=int, default=3)


def run_cli(args: argparse.Namespace) -> int:
    try:
        manifest = run_gate(args)
    except (Uf2E2eError, OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
