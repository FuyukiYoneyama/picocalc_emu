#!/usr/bin/env python3
"""Bounded allocation experiment; reuse the existing target argv builder.

This does not promote a target or weaken the historical recovery gate.
All report fields except backend provenance must match, including quantum,
PSRAM tick count, audio expectations, scenario steps and guest cycles.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def projection(report):
    return {key: value for key, value in report.items()
            if key not in ("backend_build", "backend_commit")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pairs", type=int, choices=(1, 3), default=3)
    args = parser.parse_args()
    validation = args.validation.resolve()
    sys.path.insert(0, str(validation / "tools"))
    import benchmark_rp2040_cpu_candidate as existing

    registry_path = validation / "reference-projects/firmware-targets.json"
    registry = json.loads(registry_path.read_bytes())
    target = next(t for t in registry["targets"] if t["id"] == args.target)
    firmware = args.firmware.resolve()
    assert digest(firmware) == target["artifacts"]["bin_sha256"], "fixed BIN mismatch"
    scenario = validation / target["scenario"]["path"]
    assert digest(scenario) == target["scenario"]["sha256"], "fixed scenario mismatch"
    assert 11 in os.sched_getaffinity(0), "recorded affinity unavailable"
    repos = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    identities = {}
    for role, repo in repos.items():
        assert not git(repo, "status", "--porcelain"), f"dirty {role}"
        runner = repo / "target/release/picocalc-run"
        identities[role] = {
            "commit": git(repo, "rev-parse", "HEAD"),
            "runner_sha256": digest(runner),
            "cargo_lock_sha256": digest(repo / "Cargo.lock"),
            "audio_source_sha256": digest(repo / "crates/rp2040-emu/src/audio_sink.rs"),
        }
    bootrom = repos["baseline"] / "roms/rp2040/bootrom-rp2040-b2.bin"
    assert digest(bootrom) == "9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81"
    # The recovery checkpoint uses 1e9 rather than the registry's larger budget.
    if args.target == "picotetris-opt1b":
        target["runner"]["cycles"] = 1_000_000_000
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "kind": "bounded-dma-audio-allocation-comparison",
        "target": args.target,
        "firmware_sha256": digest(firmware),
        "scenario_sha256": digest(scenario),
        "registry_sha256": digest(registry_path),
        "argv_builder_sha256": digest(validation / "tools/benchmark_rp2040_cpu_candidate.py"),
        "identities": identities,
        "platform": platform.platform(),
        "affinity_cpu": 11,
        "timeout_seconds": 300,
        "order": [(["baseline", "candidate"] if pair % 2 == 0 else ["candidate", "baseline"])
                  for pair in range(args.pairs)],
        "projection_exclusions": ["backend_build", "backend_commit"],
        "runs": [],
    }
    write_json(output / "manifest.json", manifest)
    canonical = None
    results = {}
    os.sched_setaffinity(0, {11})
    for pair, order in enumerate(manifest["order"], 1):
        for role in order:
            directory = output / f"pair-{pair}-{role}"
            directory.mkdir()
            runner = repos[role] / "target/release/picocalc-run"
            argv = existing.target_command(
                target, firmware, runner, Path("report.json"), Path("uart.raw"), Path("snapshots"),
                backend_commit=identities[role]["commit"], host_timing=Path("host-timing.json"),
            )
            argv += ["--bootrom", str(bootrom), "--fb-png", "framebuffer.png"]
            entry = {"pair": pair, "role": role, "argv": argv, "started_unix": time.time()}
            print(f"START {args.target} pair={pair} {role}", flush=True)
            with (directory / "stdout.log").open("w") as stdout, (directory / "stderr.log").open("w") as stderr:
                try:
                    completed = subprocess.run(argv, cwd=directory, stdout=stdout, stderr=stderr, timeout=300)
                    entry["returncode"] = completed.returncode
                except subprocess.TimeoutExpired:
                    entry["returncode"] = "timeout"
            entry["finished_unix"] = time.time()
            manifest["runs"].append(entry)
            write_json(output / "manifest.json", manifest)
            assert entry["returncode"] == 0, f"runner failed; inspect {directory}"
            report = json.loads((directory / "report.json").read_bytes())
            timing = json.loads((directory / "host-timing.json").read_bytes())
            assert report["backend_build"]["dirty"] is False, "dirty built runner"
            assert report["backend_commit"] == identities[role]["commit"]
            assert report["verdict"]["status"] == "pass"
            assert report["scenario"]["status"] == "pass"
            assert timing["timing_scope"] == "picocalc-harness::run_loop"
            assert timing["cycles"] == report["cycles"]
            assert timing["stop_reason"] == report["stop_reason"] == "scenario_done"
            projected = projection(report)
            write_json(directory / "projection.json", projected)
            observed = {
                "report": projected,
                "uart": digest(directory / "uart.raw"),
                "framebuffer": digest(directory / "framebuffer.png"),
                "snapshots": {str(p.relative_to(directory)): digest(p)
                              for p in sorted((directory / "snapshots").rglob("*.png"))},
            }
            if canonical is None:
                canonical = observed
            assert canonical == observed, f"observation mismatch; inspect {directory}"
            cpu = timing["emulation_cpu_ns"] / 1e9
            wall = timing["emulation_wall_ns"] / 1e9
            assert cpu > 0 and wall > 0
            results[(pair, role)] = {
                "cpu_seconds": cpu, "wall_seconds": wall,
                "real_time_percent": report["elapsed_us"] / 1e6 / wall * 100,
                "cycles": report["cycles"], "elapsed_us": report["elapsed_us"],
            }
            entry["metrics"] = results[(pair, role)]
            entry["observations_equal"] = True
            write_json(output / "manifest.json", manifest)
            print(f"DONE pair={pair} {role} CPU={cpu:.6f}s wall={wall:.6f}s equal=true", flush=True)
    reductions = [1 - results[(pair, "candidate")]["cpu_seconds"] / results[(pair, "baseline")]["cpu_seconds"]
                  for pair in range(1, args.pairs + 1)]
    summary = {
        "observations_equal": True,
        "cpu_reduction_fractions": reductions,
        "median_paired_cpu_reduction": statistics.median(reductions),
        "continue_to_regressions": args.pairs == 3 and min(reductions) > 0 and statistics.median(reductions) >= .20,
        "medians": {role: {metric: statistics.median(results[(pair, role)][metric] for pair in range(1, args.pairs + 1))
                           for metric in ("cpu_seconds", "wall_seconds", "real_time_percent")}
                    for role in repos},
        "recovery_14_percent_reached": min(results[(pair, "candidate")]["real_time_percent"]
                                            for pair in range(1, args.pairs + 1)) >= 14,
        "main_integration_authorized_by_this_record": False,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
