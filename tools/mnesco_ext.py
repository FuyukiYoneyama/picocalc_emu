#!/usr/bin/env python3
"""Run the M-NESCO SD/flash/XIP acceptance matrix locally.

The caller supplies read-only ``NAME=ROM`` inputs.  The generated evidence
stores only the basename, iNES metadata, SHA-256 and sanitized run results;
the source pathname is deliberately never written to the manifest.

This is an acceptance tool, not a ROM collection tool.  ROM binaries and the
temporary FAT image stay outside the repository and are removed after each
case.  CI is intentionally not involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from sd_image import pack_tree  # noqa: E402


RAM_THRESHOLD = 16 + 512 + 0x8000 + 0x2000


class GateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class RomCase:
    name: str
    basename: str
    data: bytes
    sha256: str
    mapper: int
    submapper: int
    trainer: bool
    prg_bytes: int
    chr_bytes: int
    prg_offset: int
    chr_offset: int
    source_region: str

    @classmethod
    def load(cls, name: str, path: Path) -> "RomCase":
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
            raise GateError(f"invalid case name: {name!r}")
        data = path.read_bytes()
        if len(data) < 16 or data[:4] != b"NES\x1a":
            raise GateError(f"{path.name}: missing iNES magic")
        h = data[:16]
        nes2 = (h[7] & 0x0C) == 0x08
        mapper = (h[6] >> 4) | (h[7] & 0xF0)
        submapper = 0
        if nes2:
            mapper |= (h[8] & 0x0F) << 8
            submapper = h[8] >> 4
            prg_units = h[4] | ((h[9] & 0x0F) << 8)
            chr_units = h[5] | ((h[9] >> 4) << 8)
        else:
            prg_units = h[4]
            chr_units = h[5]
        trainer = bool(h[6] & 0x04)
        prg_bytes = prg_units * 0x4000
        chr_bytes = chr_units * 0x2000
        prg_offset = 16 + (512 if trainer else 0)
        chr_offset = prg_offset + prg_bytes
        expected = chr_offset + chr_bytes
        if expected > len(data):
            raise GateError(f"{path.name}: truncated iNES payload ({len(data)} < {expected})")
        if expected != len(data):
            raise GateError(f"{path.name}: trailing bytes are not accepted ({len(data)} != {expected})")
        if prg_bytes == 0:
            raise GateError(f"{path.name}: empty PRG payload")
        return cls(
            name=name,
            basename=path.name,
            data=data,
            sha256=sha256_bytes(data),
            mapper=mapper,
            submapper=submapper,
            trainer=trainer,
            prg_bytes=prg_bytes,
            chr_bytes=chr_bytes,
            prg_offset=prg_offset,
            chr_offset=chr_offset,
            source_region="ram" if len(data) < RAM_THRESHOLD else "xip",
        )

    def samples(self, offset: int, size: int) -> dict[str, int]:
        middle = (size - 1) // 2
        return {
            "first": self.data[offset],
            "middle": self.data[offset + middle],
            "last": self.data[offset + size - 1],
        }

    def sample_digest(self, offset: int, size: int) -> str:
        middle = (size - 1) // 2
        return sha256_bytes(bytes((self.data[offset], self.data[offset + middle], self.data[offset + size - 1])))

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "basename": self.basename,
            "source_class": "caller-supplied read-only ROM",
            "sha256": self.sha256,
            "bytes": len(self.data),
            "mapper": self.mapper,
            "submapper": self.submapper,
            "trainer": self.trainer,
            "prg_bytes": self.prg_bytes,
            "chr_bytes": self.chr_bytes,
            "source_region_expected": self.source_region,
            "prg_samples": self.samples(self.prg_offset, self.prg_bytes),
            "chr_samples": self.samples(self.chr_offset, self.chr_bytes) if self.chr_bytes else None,
            "prg_sample_sha256": self.sample_digest(self.prg_offset, self.prg_bytes),
            "chr_sample_sha256": self.sample_digest(self.chr_offset, self.chr_bytes) if self.chr_bytes else None,
        }


ROM_MARKER = re.compile(
    r"rom path=(?P<path>[^ ]+) bytes=(?P<bytes>\d+) mapper=(?P<mapper>\d+) "
    r"submapper=(?P<submapper>\d+) prg=(?P<prg>\d+) chr=(?P<chr>\d+) "
    r"trainer=(?P<trainer>[01]) sha256=(?P<sha>[0-9a-f]{64})"
)
SAMPLE_MARKER = re.compile(
    r"sample=(?P<region>prg|chr) point=(?P<point>first|middle|last) "
    r"offset=(?P<offset>\d+) value=(?P<value>[0-9A-Fa-f]{2})"
)
DIGEST_MARKER = re.compile(
    r"sample=(?P<region>prg|chr) digest=(?P<digest>[0-9a-f]{64}) bytes=(?P<bytes>\d+)"
)
COUNT_MARKER = re.compile(
    r"cpu_fetches=(?P<fetch>\d+) cpu_rom_reads=(?P<rom>\d+) cpu_digest=(?P<cpu>[0-9a-f]+) "
    r"ppu_bus_reads=(?P<ppu>\d+) ppu_digest=(?P<ppud>[0-9a-f]+)"
)
XIP_MARKER = re.compile(
    r"core1_xip=(?P<core1>\w+) digest=(?P<core1_digest>[0-9a-f]+) "
    r"dma_xip=(?P<dma>\w+) digest=(?P<dma_digest>[0-9a-f]+)"
)
DONE_MARKER = re.compile(r"\[NESCO_MNESCO_DONE\] result=(?P<result>\w+)")


def parse_uart(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8", errors="replace")
    rom_match = ROM_MARKER.search(text)
    counts = COUNT_MARKER.search(text)
    xip = XIP_MARKER.search(text)
    done = DONE_MARKER.search(text)
    if not rom_match or not counts or not xip or not done:
        missing = [
            label for label, match in (("rom", rom_match), ("counts", counts), ("xip", xip), ("done", done)) if not match
        ]
        raise GateError(f"M-NESCO UART markers missing: {', '.join(missing)}")
    samples: dict[str, dict[str, int]] = {"prg": {}, "chr": {}}
    for match in SAMPLE_MARKER.finditer(text):
        samples[match["region"]][match["point"]] = int(match["value"], 16)
    digests: dict[str, dict[str, Any]] = {}
    for match in DIGEST_MARKER.finditer(text):
        digests[match["region"]] = {"sha256": match["digest"], "bytes": int(match["bytes"])}
    return {
        "rom": {
            "path": rom_match["path"],
            "bytes": int(rom_match["bytes"]),
            "mapper": int(rom_match["mapper"]),
            "submapper": int(rom_match["submapper"]),
            "prg_bytes": int(rom_match["prg"]),
            "chr_bytes": int(rom_match["chr"]),
            "trainer": rom_match["trainer"] == "1",
            "sha256": rom_match["sha"],
        },
        "samples": samples,
        "sample_digests": digests,
        "counts": {
            "cpu_fetches": int(counts["fetch"]),
            "cpu_rom_reads": int(counts["rom"]),
            "cpu_digest": counts["cpu"],
            "ppu_bus_reads": int(counts["ppu"]),
            "ppu_digest": counts["ppud"],
        },
        "xip": {
            "core1": xip["core1"],
            "core1_digest": xip["core1_digest"],
            "dma": xip["dma"],
            "dma_digest": xip["dma_digest"],
        },
        "done": done["result"],
    }


def validate_report(case: RomCase, report: dict[str, Any], uart: dict[str, Any], phase: str) -> None:
    if report.get("verdict", {}).get("status") != "pass":
        raise GateError(f"{case.name} {phase}: report verdict is not pass: {report.get('verdict')}")
    if report.get("stop_reason") != "scenario_done":
        raise GateError(f"{case.name} {phase}: unexpected stop reason {report.get('stop_reason')!r}")
    scenario = report.get("scenario") or {}
    if scenario.get("status") != "pass":
        raise GateError(f"{case.name} {phase}: scenario is not pass")
    if report.get("exception") or report.get("error"):
        raise GateError(f"{case.name} {phase}: runner error/exception present")
    if report.get("unsupported_mmio"):
        raise GateError(f"{case.name} {phase}: unsupported MMIO present")
    sd = report.get("sd") or {}
    if sd.get("unknown_commands"):
        raise GateError(f"{case.name} {phase}: unknown SD commands present")
    flash = report.get("flash") or {}
    if flash.get("unknown_commands") or flash.get("errors"):
        raise GateError(f"{case.name} {phase}: flash mutation/unknown command present")
    keyboard = report.get("keyboard") or {}
    if keyboard.get("key_events_dropped", 0) or keyboard.get("key_events_overwritten", 0):
        raise GateError(f"{case.name} {phase}: keyboard events were lost")

    expected = case.manifest()
    rom = uart["rom"]
    for key in ("bytes", "mapper", "submapper", "prg_bytes", "chr_bytes", "trainer", "sha256"):
        expected_key = {"bytes": "bytes", "mapper": "mapper", "submapper": "submapper", "prg_bytes": "prg_bytes", "chr_bytes": "chr_bytes", "trainer": "trainer", "sha256": "sha256"}[key]
        if rom[key] != expected[expected_key]:
            raise GateError(f"{case.name} {phase}: ROM {key} mismatch ({rom[key]!r} != {expected[expected_key]!r})")
    for region, offset, size in (("prg", case.prg_offset, case.prg_bytes), ("chr", case.chr_offset, case.chr_bytes)):
        if size == 0:
            continue
        if uart["samples"].get(region) != expected[f"{region}_samples"]:
            raise GateError(f"{case.name} {phase}: {region} first/middle/last sample mismatch")
        digest = uart["sample_digests"].get(region)
        if not digest or digest["sha256"] != expected[f"{region}_sample_sha256"] or digest["bytes"] != size:
            raise GateError(f"{case.name} {phase}: {region} sample digest mismatch")
    if uart["counts"]["cpu_fetches"] == 0 or uart["counts"]["cpu_rom_reads"] == 0 or uart["counts"]["ppu_bus_reads"] == 0:
        raise GateError(f"{case.name} {phase}: CPU/PPU observation count is zero")
    if uart["done"] != "PASS":
        raise GateError(f"{case.name} {phase}: diagnostic result is {uart['done']}")
    expected_xip = "pass" if (phase == "B" or case.source_region == "xip") else "not_applicable"
    if uart["xip"]["core1"] != expected_xip or uart["xip"]["dma"] != expected_xip:
        raise GateError(f"{case.name} {phase}: XIP probe result is inconsistent with {expected_xip}")


def run_one(
    *,
    case: RomCase,
    phase: str,
    repeat: int,
    runner: Path,
    firmware: Path,
    backend_commit: str,
    scenario: Path,
    sd_image: Path,
    initial_flash: Path,
    cycles: int,
    quantum: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"mnesco-{case.name}-{phase.lower()}-{repeat}-") as temp:
        work = Path(temp)
        report_path = work / "report.json"
        uart_path = work / "uart.bin"
        trace_path = work / "sd-trace.json"
        sd_out = work / "sd-output.img"
        flash_out = work / "flash-output.bin"
        command = [
            str(runner), "--bin", str(initial_flash), "--board", "picocalc", "--keyboard",
            "--quantum", str(quantum), "--sd-image", str(sd_image), "--sd-image-out", str(sd_out),
            "--sd-trace", str(trace_path), "--flash-image-out", str(flash_out), "--scenario", str(scenario),
            "--uart", str(uart_path), "--json", str(report_path), "--cycles", str(cycles),
            "--expect-stop", "scenario_done", "--backend-commit", backend_commit,
        ]
        # The runner resolves its default bootrom and other relative assets from
        # the backend repository root, not from target/ (the binary's parent).
        # Keep this explicit so a release build invoked from another workspace
        # has the same asset resolution as the documented backend commands.
        backend_root = runner.parent.parent.parent
        completed = subprocess.run(command, cwd=backend_root, capture_output=True, text=True)
        if not report_path.exists() or not uart_path.exists():
            detail = completed.stderr[-1000:].strip() or completed.stdout[-1000:].strip()
            raise GateError(
                f"{case.name} {phase}{repeat}: runner produced no report "
                f"(rc={completed.returncode}): {detail}"
            )
        report = json.loads(report_path.read_text())
        uart_bytes = uart_path.read_bytes()
        if completed.returncode != 0:
            raise GateError(f"{case.name} {phase}{repeat}: runner failed rc={completed.returncode}: {completed.stderr[-1000:]}")
        uart = parse_uart(uart_bytes)
        validate_report(case, report, uart, phase)
        if sha256_bytes(uart_bytes) != report.get("uart", {}).get("sha256"):
            raise GateError(f"{case.name} {phase}{repeat}: UART SHA mismatch")
        if not sd_out.exists() or sha256_file(sd_out) != sha256_file(sd_image):
            raise GateError(f"{case.name} {phase}{repeat}: SD backing changed")
        trace = json.loads(trace_path.read_text())
        if trace.get("unknown_commands"):
            raise GateError(f"{case.name} {phase}{repeat}: SD trace contains unknown commands")
        if not flash_out.exists():
            raise GateError(f"{case.name} {phase}{repeat}: no flash export")
        return {
            "phase": phase,
            "repeat": repeat,
            "report": report,
            "uart": uart,
            "uart_sha256": sha256_bytes(uart_bytes),
            "sd_trace_sha256": trace.get("digest_sha256"),
            "sd_image_sha256": sha256_file(sd_out),
            "flash_sha256": sha256_file(flash_out),
            "flash_path": str(flash_out),
            "fingerprint_sha256": sha256_bytes(canonical(report).encode()),
        }, flash_out.read_bytes()


def compare_repeats(case: RomCase, phase: str, runs: list[dict[str, Any]]) -> None:
    if len(runs) < 3:
        raise GateError(f"{case.name} {phase}: three deterministic runs are required")
    keys = ("fingerprint_sha256", "uart_sha256", "sd_trace_sha256", "flash_sha256")
    baseline = runs[0]
    for run in runs[1:]:
        for key in keys:
            if run[key] != baseline[key]:
                raise GateError(f"{case.name} {phase}: repeat mismatch in {key}")


def validate_cross_phase(case: RomCase, runs_a: list[dict[str, Any]], runs_b: list[dict[str, Any]]) -> None:
    """Require the flash image exported by A to remain byte-identical in B."""
    if not runs_a or not runs_b:
        raise GateError(f"{case.name}: cross-phase comparison requires A and B runs")
    expected_flash = runs_a[0]["flash_sha256"]
    for run in runs_b:
        if run["flash_sha256"] != expected_flash:
            raise GateError(
                f"{case.name} B: flash SHA changed after A export "
                f"({run['flash_sha256']} != {expected_flash})"
            )
    # The source path is expected to change from SD to flash, but every ROM
    # identity, boundary sample, and observation digest must remain identical.
    a_uart = runs_a[0].get("uart") or {}
    a_rom = dict(a_uart.get("rom") or {})
    if a_rom.get("path") != "sd:/TEST.NES":
        raise GateError(f"{case.name} A: unexpected source path {a_rom.get('path')!r}")
    a_rom.pop("path", None)
    for run in runs_b:
        b_uart = run.get("uart") or {}
        b_rom = dict(b_uart.get("rom") or {})
        if b_rom.get("path") != "flash:/TEST.NES":
            raise GateError(f"{case.name} B: unexpected reattach path {b_rom.get('path')!r}")
        b_rom.pop("path", None)
        if b_rom != a_rom:
            raise GateError(f"{case.name} B: ROM identity changed across SD/flash reattach")
        for key in ("samples", "sample_digests", "counts", "xip", "done"):
            if b_uart.get(key) != a_uart.get(key):
                raise GateError(f"{case.name} B: {key} changed across SD/flash reattach")


def parse_case_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("case must be NAME=ROM_PATH")
    name, raw_path = value.split("=", 1)
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"ROM does not exist: {path.name}")
    return name, path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--backend-commit", required=True)
    parser.add_argument("--scenario-sd", type=Path, required=True)
    parser.add_argument("--scenario-flash", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", type=parse_case_arg, required=True,
                        help="NAME=ROM_PATH; repeat for each read-only input")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cycles", type=int, default=2_000_000_000)
    parser.add_argument("--quantum", type=int, default=16)
    args = parser.parse_args(list(argv) if argv is not None else None)
    # The runner is launched with the backend repository as cwd so its
    # bootrom/default assets resolve correctly.  Make all caller paths
    # absolute before constructing the command line; otherwise a relative
    # scenario path would accidentally be looked up in the backend checkout.
    args.runner = args.runner.expanduser().resolve()
    args.firmware = args.firmware.expanduser().resolve()
    args.scenario_sd = args.scenario_sd.expanduser().resolve()
    args.scenario_flash = args.scenario_flash.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    if args.repeats != 3:
        raise SystemExit("M-NESCO acceptance requires exactly --repeats 3")
    if args.quantum < 1:
        raise SystemExit("--quantum must be positive")
    for path in (args.runner, args.firmware, args.scenario_sd, args.scenario_flash):
        if not path.is_file():
            raise SystemExit(f"missing input: {path.name}")
    cases = [RomCase.load(name, path.expanduser().resolve()) for name, path in args.case]
    if len({case.name for case in cases}) != len(cases):
        raise SystemExit("case names must be unique")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema": 1,
        "acceptance": "M-NESCO extension 1-15",
        "ci": "not used; local runner only",
        "runner_backend_commit": args.backend_commit,
        "firmware": {"basename": args.firmware.name, "sha256": sha256_file(args.firmware)},
        "runner": {"basename": args.runner.name, "sha256": sha256_file(args.runner)},
        "repeats": args.repeats,
        "cycles": args.cycles,
        "quantum": args.quantum,
        "cases": [],
    }
    try:
        for case in cases:
            case_dir = args.output / case.name
            case_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=f"mnesco-sd-{case.name}-") as temp:
                temp_root = Path(temp)
                tree = temp_root / "tree"
                tree.mkdir()
                (tree / "TEST.NES").write_bytes(case.data)
                sd_image = temp_root / "input.img"
                pack = pack_tree(tree, sd_image, fat_type="fat32", size_mib=64, volume_label="PICOCALC")
                sd_manifest = {
                    "format": "fat32",
                    "bytes": sd_image.stat().st_size,
                    "image_sha256": sha256_file(sd_image),
                    "tree_sha256": pack.get("tree_sha256"),
                    "file": {"basename": "TEST.NES", "sha256": case.sha256, "bytes": len(case.data)},
                }
                runs_a: list[dict[str, Any]] = []
                flash_a: bytes | None = None
                for repeat in range(1, args.repeats + 1):
                    print(f"RUN {case.name} A{repeat}", flush=True)
                    result, flash = run_one(
                        case=case, phase="A", repeat=repeat, runner=args.runner, firmware=args.firmware,
                        backend_commit=args.backend_commit, scenario=args.scenario_sd, sd_image=sd_image,
                        initial_flash=args.firmware, cycles=args.cycles, quantum=args.quantum,
                    )
                    runs_a.append(result)
                    if flash_a is None:
                        flash_a = flash
                    print(f"PASS {case.name} A{repeat}", flush=True)
                compare_repeats(case, "A", runs_a)
                runs_b: list[dict[str, Any]] = []
                if case.source_region == "xip":
                    flash_path = temp_root / "flash-a.bin"
                    flash_path.write_bytes(flash_a or b"")
                    for repeat in range(1, args.repeats + 1):
                        print(f"RUN {case.name} B{repeat}", flush=True)
                        result, _ = run_one(
                            case=case, phase="B", repeat=repeat, runner=args.runner, firmware=args.firmware,
                            backend_commit=args.backend_commit, scenario=args.scenario_flash, sd_image=sd_image,
                            initial_flash=flash_path, cycles=args.cycles, quantum=args.quantum,
                        )
                        runs_b.append(result)
                        print(f"PASS {case.name} B{repeat}", flush=True)
                    compare_repeats(case, "B", runs_b)
                    # Reattaching the exported image must not mutate it merely
                    # by starting from flash rather than SD.  This is a
                    # separate cross-phase gate from repeat determinism.
                    validate_cross_phase(case, runs_a, runs_b)
                case_record = {
                    "input": case.manifest(),
                    "sd": sd_manifest,
                    "run_a": [{k: v for k, v in run.items() if k != "report" and k != "flash_path"} for run in runs_a],
                    "run_b": [{k: v for k, v in run.items() if k != "report" and k != "flash_path"} for run in runs_b],
                    "flash_reattach": bool(runs_b),
                    "status": "pass",
                }
                (case_dir / "case.json").write_text(json.dumps(case_record, indent=2, sort_keys=True) + "\n")
                manifest["cases"].append(case_record)
                print(f"PASS {case.name}: A=3 deterministic, B={'3 deterministic' if runs_b else 'not_applicable (RAM source)'}")
    except (GateError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    manifest["status"] = "pass"
    (args.output / "mnesco-ext-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"M-NESCO extension acceptance PASS: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
