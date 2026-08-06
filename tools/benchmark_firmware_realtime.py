#!/usr/bin/env python3
"""Measure emulated time against wall time for a registered firmware target."""

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import picocalc


ROOT = Path(__file__).resolve().parents[1]
T_CRITICAL_95 = (
    0.0,
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262157,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("cannot inspect Git repository {}".format(repository))
    return result.stdout.strip()


def host_cpu() -> Dict[str, object]:
    model = "unknown"
    frequencies: List[float] = []
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name") and model == "unknown":
                model = line.split(":", 1)[1].strip()
            elif line.startswith("cpu MHz"):
                frequencies.append(float(line.split(":", 1)[1].strip()))
    except (OSError, UnicodeError, ValueError, IndexError):
        pass
    return {
        "model": model,
        "logical_cpus": os.cpu_count(),
        "reported_mhz": statistics.median(frequencies) if frequencies else None,
    }


def summarize(values: List[float]) -> Dict[str, object]:
    mean = statistics.mean(values)
    median = statistics.median(values)
    minimum = min(values)
    maximum = max(values)
    if len(values) == 1:
        return {
            "mean": mean,
            "median": median,
            "sample_stddev": None,
            "minimum": minimum,
            "maximum": maximum,
            "mean_ci95": None,
        }
    deviation = statistics.stdev(values)
    degrees = len(values) - 1
    critical = T_CRITICAL_95[degrees] if degrees < len(T_CRITICAL_95) else 1.96
    half_width = critical * deviation / math.sqrt(len(values))
    return {
        "mean": mean,
        "median": median,
        "sample_stddev": deviation,
        "minimum": minimum,
        "maximum": maximum,
        "mean_ci95": [mean - half_width, mean + half_width],
    }


def target_command(
    target: dict,
    firmware: Path,
    runner: Path,
    report: Path,
    uart: Path,
    snapshots: Path,
) -> List[str]:
    contract = target["runner"]
    command = [
        str(runner),
        "--bin", str(firmware),
        "--board", contract["board"],
        "--lcd-variant", contract["lcd_variant"],
        "--quantum", str(contract["quantum"]),
        "--cycles", str(contract["cycles"]),
        "--json", str(report),
        "--uart", str(uart),
        "--backend-commit", target["backend"]["accepted"],
        "--expect-stop", target["acceptance"]["expected_stop_reason"],
    ]
    for marker in target["acceptance"]["required_uart_markers"]:
        command.extend(["--expect-uart", marker])
    if contract.get("stop_pc") is not None:
        command.extend(["--stop-pc", str(contract["stop_pc"])])
    if contract.get("psram", False):
        command.append("--psram")
    if contract.get("psram_verify_range"):
        command.extend(["--psram-verify-range", contract["psram_verify_range"]])
    if contract.get("keyboard", False):
        command.append("--keyboard")
    if contract.get("keys"):
        command.extend(["--keys", contract["keys"]])
    sd = contract["sd"]
    if sd["attached"]:
        command.extend(["--sd", "--sd-format", sd["format"]])
    scenario = target.get("scenario")
    if scenario is not None:
        command.extend(["--scenario", str(ROOT / scenario["path"])])
        command.extend(["--snapshot-dir", str(snapshots)])
    return command


def validate_report(target: dict, firmware_sha256: str, report: dict) -> None:
    contract = target["runner"]
    required = [
        {"path": "schema_version", "op": "eq", "value": 8},
        {"path": "verdict.status", "op": "eq", "value": "pass"},
        {"path": "backend_build.commit", "op": "eq", "value": target["backend"]["accepted"]},
        {"path": "backend_build.dirty", "op": "eq", "value": False},
        {"path": "firmware.sha256", "op": "eq", "value": firmware_sha256},
        {"path": "step_quantum", "op": "eq", "value": contract["quantum"]},
        {"path": "cycle_limit", "op": "eq", "value": contract["cycles"]},
        {"path": "exception", "op": "eq", "value": None},
        {"path": "error", "op": "eq", "value": None},
        {"path": "unsupported_mmio", "op": "length_eq", "value": 0},
    ]
    failures = picocalc.check_report(report, required + target["acceptance"]["report_checks"])
    expected_report = target["acceptance"].get("normalized_report_sha256")
    if expected_report and picocalc.normalized_json_sha256(report) != expected_report:
        failures.append("normalized report SHA-256 mismatch")
    expected_timeline = target["acceptance"].get("timeline_sha256")
    timeline = report.get("scenario", {}).get("steps")
    if expected_timeline and (
        timeline is None or picocalc.normalized_json_sha256(timeline) != expected_timeline
    ):
        failures.append("scenario timeline SHA-256 mismatch")
    if failures:
        raise ValueError("target report failed: {}".format("; ".join(failures)))


def run_once(target: dict, firmware: Path, backend: Path, runner: Path) -> Dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="picocalc-realtime-") as temporary:
        directory = Path(temporary)
        snapshots = directory / "snapshots"
        snapshots.mkdir()
        report_path = directory / "report.json"
        uart_path = directory / "uart.bin"
        command = target_command(
            target, firmware, runner, report_path, uart_path, snapshots
        )
        started = time.perf_counter_ns()
        result = subprocess.run(
            command,
            cwd=str(backend),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        wall_ns = time.perf_counter_ns() - started
        if result.returncode != 0:
            raise ValueError("runner exited {}".format(result.returncode))
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes)
        validate_report(target, sha256_file(firmware), report)
        snapshot_sha256 = {
            path.name: sha256_file(path) for path in sorted(snapshots.glob("*.png"))
        }
        emulated_us = report["elapsed_us"]
        cycles = report["cycles"]
        wall_seconds = wall_ns / 1_000_000_000
        return {
            "wall_ns": wall_ns,
            "wall_seconds": wall_seconds,
            "emulated_us": emulated_us,
            "cycles": cycles,
            "real_time_percent": (emulated_us / 1_000_000) / wall_seconds * 100,
            "emulated_cycles_per_wall_second": cycles / wall_seconds,
            "slowdown": wall_seconds / (emulated_us / 1_000_000),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "uart_sha256": sha256_file(uart_path),
            "snapshot_sha256": snapshot_sha256,
        }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="picotetris-r4")
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--backend-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--json", type=Path)
    arguments = parser.parse_args()
    if arguments.runs < 1 or arguments.warmup < 0:
        parser.error("--runs must be >= 1 and --warmup must be >= 0")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    target = picocalc.load_firmware_target(arguments.target)
    if target is None or target.get("status") != "active":
        raise ValueError("target must exist and be active")
    firmware = arguments.firmware.resolve()
    backend = arguments.backend_dir.resolve()
    runner = backend / "target/release/picocalc-run"
    firmware_sha256 = sha256_file(firmware)
    if firmware_sha256 != target["artifacts"]["bin_sha256"]:
        raise ValueError("firmware does not match the registered target")
    if git_output(backend, "rev-parse", "HEAD") != target["backend"]["accepted"]:
        raise ValueError("backend does not match the registered target")
    if git_output(backend, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("backend tracked working tree is dirty")
    if not runner.is_file():
        raise ValueError("release runner is missing")
    scenario = target.get("scenario")
    if scenario is not None and sha256_file(ROOT / scenario["path"]) != scenario["sha256"]:
        raise ValueError("scenario does not match the registered target")

    affinity_before: Optional[List[int]] = None
    if hasattr(os, "sched_getaffinity"):
        affinity_before = sorted(os.sched_getaffinity(0))
    if arguments.cpu is not None:
        if not hasattr(os, "sched_setaffinity"):
            raise ValueError("--cpu needs Linux sched_setaffinity")
        if affinity_before is not None and arguments.cpu not in affinity_before:
            raise ValueError("--cpu is outside the allowed affinity set")
        os.sched_setaffinity(0, {arguments.cpu})

    for index in range(arguments.warmup):
        print("warmup {}/{}".format(index + 1, arguments.warmup), file=sys.stderr)
        run_once(target, firmware, backend, runner)

    measurements = []
    for index in range(arguments.runs):
        print("run {}/{}".format(index + 1, arguments.runs), file=sys.stderr)
        measurement = run_once(target, firmware, backend, runner)
        measurement["run"] = index + 1
        measurements.append(measurement)

    report_hashes = {item["report_sha256"] for item in measurements}
    uart_hashes = {item["uart_sha256"] for item in measurements}
    snapshots = {
        json.dumps(item["snapshot_sha256"], sort_keys=True) for item in measurements
    }
    if len(report_hashes) != 1 or len(uart_hashes) != 1 or len(snapshots) != 1:
        raise ValueError("measured target outputs were not deterministic")

    cpu = host_cpu()
    walls = [item["wall_seconds"] for item in measurements]
    percentages = [item["real_time_percent"] for item in measurements]
    throughputs = [item["emulated_cycles_per_wall_second"] for item in measurements]
    slowdowns = [item["slowdown"] for item in measurements]
    emulated_seconds = measurements[0]["emulated_us"] / 1_000_000
    cycles = measurements[0]["cycles"]
    quantum = target["runner"]["quantum"]
    virtual_hz = cycles / emulated_seconds
    theory: Dict[str, object] = {
        "definition": "real_time_percent = emulated_seconds / wall_seconds * 100",
        "real_time_target_percent": 100.0,
        "ideal_wall_seconds": emulated_seconds,
        "required_emulated_cycles_per_wall_second": virtual_hz,
        "step_quantum": quantum,
    }
    if cpu["reported_mhz"] is not None:
        host_hz = float(cpu["reported_mhz"]) * 1_000_000
        dispatches_per_virtual_second = virtual_hz / quantum
        theory.update({
            "host_reported_hz": host_hz,
            "host_cycles_per_dispatch_budget_at_100_percent": (
                host_hz / dispatches_per_virtual_second
            ),
            "one_host_cycle_per_dispatch_ceiling_percent": (
                host_hz / dispatches_per_virtual_second * 100
            ),
            "ceiling_note": (
                "An unattainable instruction-count lower bound, not a performance prediction."
            ),
        })

    output = {
        "schema_version": 1,
        "metric": "emulated-time-to-wall-time",
        "target": {
            "id": target["id"],
            "revision": target["revision"],
            "firmware_sha256": firmware_sha256,
            "backend_commit": target["backend"]["accepted"],
            "runner_sha256": sha256_file(runner),
            "scenario_sha256": scenario["sha256"] if scenario else None,
            "cycles": cycles,
            "emulated_us": measurements[0]["emulated_us"],
            "step_quantum": quantum,
        },
        "environment": {
            "platform": platform.platform(),
            "kernel": platform.release(),
            "cpu": cpu,
            "cpu_affinity_before": affinity_before,
            "measurement_cpu": arguments.cpu,
        },
        "method": {
            "warmup_runs_excluded": arguments.warmup,
            "measured_runs": arguments.runs,
            "timer": "time.perf_counter_ns around the release runner process",
            "build_time_included": False,
            "target_validation_included": False,
            "runner_startup_and_artifact_writes_included": True,
        },
        "theory": theory,
        "measurements": measurements,
        "statistics": {
            "wall_seconds": summarize(walls),
            "real_time_percent": summarize(percentages),
            "emulated_cycles_per_wall_second": summarize(throughputs),
            "slowdown": summarize(slowdowns),
        },
        "determinism": {
            "all_reports_identical": len(report_hashes) == 1,
            "report_sha256": next(iter(report_hashes)),
            "all_uart_identical": len(uart_hashes) == 1,
            "uart_sha256": next(iter(uart_hashes)),
            "all_snapshots_identical": len(snapshots) == 1,
            "snapshot_sha256": measurements[0]["snapshot_sha256"],
        },
    }
    encoded = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.json is None:
        print(encoded, end="")
    else:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(encoded, encoding="utf-8")
        print("wrote {}".format(arguments.json))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        print("benchmark failed: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
