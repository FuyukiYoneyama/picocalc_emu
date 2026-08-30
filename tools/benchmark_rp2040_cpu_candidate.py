#!/usr/bin/env python3
"""Measure and validate RP2040 CPU backend candidates on registered applications.

This runner deliberately has a different contract from
``benchmark_firmware_realtime.py``.  It treats the backend commit as an
experiment input, keeps baseline/candidate runs paired, and hashes the guest
observation projection without backend provenance fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import resource
except ImportError:  # pragma: no cover - resource is Unix-only
    resource = None  # type: ignore[assignment]

import picocalc


ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCHEMA_ID = "picocalc.rp2040-cpu-profile"
AB_SCHEMA_ID = "picocalc.rp2040-cpu-ab"
DECISION_SCHEMA_ID = "picocalc.rp2040-cpu-decision"
RECORD_TYPE = "picocalc.rp2040-cpu-record"
SCHEMA_VERSION = 1
REQUIRED_WORKLOAD_IDS = frozenset(("picotetris-opt1b-vrp5", "picoedit-r1-vrp2f"))
# Cargo features accepted by the measurement contract.  The allow-list also
# includes planned CPU-candidate features so the runner can be prepared before
# the corresponding backend implementation lands.
KNOWN_FEATURES = frozenset(
    {
        "behavior-trace",
        "compact-dispatch-key-prototype",
        "cpu-application-profiler",
        "decode-invalidation-tag-guard",
        "decoded-op-8byte-prototype",
        "diagnostic-pc-compile-out-prototype",
        "event-horizon-profiler",
        "executable-sram-invalidation-filter",
        "idle-profiler",
        "nvic-bitmap-scan-prototype",
        "pending-exception-fast-reject",
        "sd-gen1-multiblock",
        "test-hooks",
        "threading",
        "testing",
        "unconditional-cache-lookup-prototype",
    }
)
# ``picocalc-harness`` enables this feature by default.  Every build
# provenance record therefore carries the effective Cargo set, not merely the
# candidate-specific additions supplied on the CLI.
DEFAULT_EFFECTIVE_FEATURES = ("sd-gen1-multiblock",)
BUILD_PROVENANCE_SCHEMA_ID = "picocalc.rp2040-build-provenance"
BUILD_PROVENANCE_VERSION = 1
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262157,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Return the projection encoding fixed by the measurement contract."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_json_sha256(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def normalize_feature_set(features: Sequence[str]) -> List[str]:
    """Validate and canonicalize the declared Cargo feature set."""
    if not isinstance(features, (list, tuple)):
        raise ValueError("feature_set must be a list of Cargo feature names")
    values = list(features)
    if any(not isinstance(feature, str) or not feature for feature in values):
        raise ValueError("feature_set contains an empty or non-string feature")
    unknown = sorted(set(values) - KNOWN_FEATURES)
    if unknown:
        raise ValueError(
            "feature_set contains unknown Cargo feature(s): {}".format(
                ", ".join(unknown)
            )
        )
    if len(set(values)) != len(values):
        raise ValueError("feature_set contains duplicate Cargo features")
    return sorted(values)


def effective_feature_set(features: Sequence[str]) -> List[str]:
    """Return the sorted Cargo feature set actually expected in a build."""
    requested = normalize_feature_set(features)
    return sorted(set(DEFAULT_EFFECTIVE_FEATURES).union(requested))


def runner_provenance_path(runner: Path) -> Path:
    return runner.with_name(runner.name + ".build.json")


def _is_sha256_text(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def validate_runner_provenance(
    runner: Path,
    expected_backend_commit: str,
    expected_features: Sequence[str],
    *,
    expected_role: Optional[str] = None,
    allow_production_role: bool = False,
) -> Dict[str, Any]:
    """Require a build sidecar that binds Cargo provenance to the binary.

    The sidecar is generated after Cargo completes from the effective feature
    graph (`cargo tree -e features`), lockfile, toolchain, and exact argv.  Its
    runner SHA-256 binds those claims to the executable; unlike a CLI label,
    changing the binary after the build makes the next preflight fail.
    """
    if not runner.is_file():
        raise ValueError("runner is missing: {}".format(runner))
    path = runner_provenance_path(runner)
    if not path.is_file():
        raise ValueError("runner build provenance is missing: {}".format(path))
    try:
        provenance = _read_json(path)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("runner build provenance is unreadable: {}".format(path)) from error
    if not isinstance(provenance, Mapping):
        raise ValueError("runner build provenance is not an object: {}".format(path))
    if provenance.get("schema_id") != BUILD_PROVENANCE_SCHEMA_ID:
        raise ValueError("runner build provenance schema_id is invalid: {}".format(path))
    if provenance.get("schema_version") != BUILD_PROVENANCE_VERSION:
        raise ValueError("runner build provenance schema_version is invalid: {}".format(path))
    if provenance.get("backend_commit") != expected_backend_commit:
        raise ValueError("runner build provenance backend commit differs from backend HEAD")
    if provenance.get("backend_dirty") is not False:
        raise ValueError("runner build provenance backend is dirty")
    runner_digest = provenance.get("runner_sha256")
    actual_runner_digest = sha256_file(runner)
    if runner_digest != actual_runner_digest:
        raise ValueError("runner build provenance SHA-256 does not match runner")
    expected_effective = effective_feature_set(expected_features)
    declared_effective = provenance.get("feature_set")
    cargo_features = provenance.get("cargo_features")
    try:
        normalized_declared = normalize_feature_set(declared_effective)
        normalized_cargo = normalize_feature_set(cargo_features)
    except ValueError as error:
        raise ValueError("runner build provenance feature set is invalid: {}".format(path)) from error
    if normalized_declared != expected_effective or normalized_cargo != expected_effective:
        raise ValueError("runner build provenance feature set differs from expected effective Cargo features")
    if provenance.get("effective_features_sha256") != canonical_json_sha256(expected_effective):
        raise ValueError("runner build provenance effective feature digest is invalid")
    for field in ("lockfile_sha256", "cargo_tree_sha256"):
        if not _is_sha256_text(provenance.get(field)):
            raise ValueError("runner build provenance {} is invalid".format(field))
    cargo_argv = provenance.get("cargo_argv")
    if not isinstance(cargo_argv, list) or not cargo_argv or not all(
        isinstance(argument, str) and argument for argument in cargo_argv
    ):
        raise ValueError("runner build provenance cargo_argv is invalid")
    for field in ("rustc_version", "cargo_version"):
        if not isinstance(provenance.get(field), str) or not provenance[field]:
            raise ValueError("runner build provenance {} is missing".format(field))
    if expected_role is not None:
        accepted_roles = {expected_role}
        if allow_production_role:
            accepted_roles.add("production")
        if provenance.get("role") not in accepted_roles:
            raise ValueError("runner build provenance role differs from expected {}".format(expected_role))
    cargo_tree_features = provenance.get("cargo_tree_features")
    try:
        normalized_tree_features = normalize_feature_set(cargo_tree_features)
    except ValueError as error:
        raise ValueError("runner build provenance cargo tree feature set is invalid: {}".format(path)) from error
    if normalized_tree_features != expected_effective:
        raise ValueError("runner build provenance cargo tree feature set differs from expected effective Cargo features")
    return {
        "path": path,
        "sha256": sha256_file(path),
        "feature_set": expected_effective,
        "role": provenance.get("role"),
    }


def cargo_tree_root_features(path: Path) -> List[str]:
    """Read the harness feature set from ``cargo tree --format '{p} {f}'``.

    The root line is the only part of the tree that describes the features
    activated on ``picocalc-harness`` itself.  Dependency feature names are
    deliberately ignored; accepting the caller's CLI declaration without
    checking this line would make the sidecar a self-attested label.
    """
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError) as error:
        raise ValueError("cargo tree evidence is unreadable: {}".format(path)) from error
    if not lines:
        raise ValueError("cargo tree evidence is empty: {}".format(path))
    root = lines[0]
    match = re.fullmatch(
        r"picocalc-harness\s+v[^\s]+(?:\s+\([^)]*\))?\s*(.*)", root
    )
    if match is None:
        raise ValueError(
            "cargo tree evidence does not start with the formatted picocalc-harness root: {}".format(
                path
            )
        )
    feature_text = match.group(1).strip()
    raw_features = [feature.strip() for feature in feature_text.split(",") if feature.strip()]
    # Cargo reports the implicit feature named ``default`` as well as the
    # features it enables.  The measurement contract records the effective
    # named features, so remove only that implicit label before normalization.
    raw_features = [feature for feature in raw_features if feature != "default"]
    if not raw_features:
        raise ValueError("cargo tree root has no effective harness features: {}".format(path))
    return effective_feature_set(raw_features)


def write_runner_provenance(args: argparse.Namespace) -> int:
    """Create the build sidecar immediately after a verified Cargo build."""
    backend = Path(args.backend).resolve()
    runner = Path(args.runner).resolve()
    identity = clean_backend_identity(backend)
    validate_runner_embedded_commit(runner, identity["commit"])
    effective = effective_feature_set(getattr(args, "feature_set", []))
    lockfile = Path(args.lockfile).resolve()
    cargo_tree = Path(args.cargo_tree).resolve()
    if not lockfile.is_file() or not cargo_tree.is_file():
        raise ValueError("lockfile and cargo tree evidence must be regular files")
    cargo_tree_features = cargo_tree_root_features(cargo_tree)
    if cargo_tree_features != effective:
        raise ValueError(
            "cargo tree root feature set differs from --feature-set: {} != {}".format(
                cargo_tree_features, effective
            )
        )
    cargo_argv = list(getattr(args, "cargo_argv", []))
    if not cargo_argv:
        raise ValueError("provenance requires --cargo-argv at least once")
    provenance = {
        "schema_id": BUILD_PROVENANCE_SCHEMA_ID,
        "schema_version": BUILD_PROVENANCE_VERSION,
        "role": args.role,
        "backend_commit": identity["commit"],
        "backend_dirty": False,
        "runner_sha256": sha256_file(runner),
        "feature_set": effective,
        "cargo_features": effective,
        "cargo_tree_features": cargo_tree_features,
        "effective_features_sha256": canonical_json_sha256(effective),
        "lockfile_sha256": sha256_file(lockfile),
        "cargo_tree_sha256": sha256_file(cargo_tree),
        "cargo_argv": cargo_argv,
        "rustc_version": args.rustc_version,
        "cargo_version": args.cargo_version,
    }
    output = Path(args.output).resolve() if args.output is not None else runner_provenance_path(runner)
    if output != runner_provenance_path(runner):
        raise ValueError("provenance output must be adjacent to runner: {}".format(runner_provenance_path(runner)))
    _write_json_once(output, provenance)
    return 0


def guest_observation_projection(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove backend identity and harness-only audio oracle metadata."""
    if not isinstance(report, Mapping):
        raise ValueError("schema-8 report must be an object")
    projection = {
        str(key): value
        for key, value in report.items()
        if key not in ("backend_build", "backend_commit")
    }
    audio_sink = projection.get("audio_sink")
    if isinstance(audio_sink, Mapping):
        projection["audio_sink"] = {
            key: value
            for key, value in audio_sink.items()
            if key not in ("expected_count", "expected_sha256")
        }
    return projection


def guest_observation_sha256(report: Mapping[str, Any]) -> str:
    return canonical_json_sha256(guest_observation_projection(report))


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            "git {} failed in {}: {}".format(
                " ".join(arguments), repository, result.stderr.strip()
            )
        )
    return result.stdout.strip()


def clean_backend_identity(backend: Path) -> Dict[str, Any]:
    """Return the exact commit used by a clean backend worktree."""
    if not backend.is_dir():
        raise ValueError("backend directory is missing: {}".format(backend))
    commit = git_output(backend, "rev-parse", "HEAD")
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("backend HEAD is not a full commit: {}".format(commit))
    dirty = git_output(backend, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise ValueError("backend working tree is dirty: {}".format(backend))
    return {"commit": commit, "dirty": False}


def validate_runner_embedded_commit(runner: Path, backend_commit: str) -> None:
    """Fail before a guest run if the executable was built from another HEAD.

    ``picocalc-harness`` embeds ``PICOEM_BUILT_COMMIT`` in the release binary.
    Looking for the exact 40-byte value is intentionally conservative: an
    absent marker is an identity failure, never a reason to guess.
    """
    if not runner.is_file():
        raise ValueError("runner is missing: {}".format(runner))
    try:
        payload = runner.read_bytes()
    except OSError as error:
        raise ValueError("runner is unreadable: {}".format(runner)) from error
    if backend_commit.encode("ascii") not in payload:
        raise ValueError(
            "runner does not embed backend HEAD {}; rebuild the runner".format(backend_commit)
        )


def host_cpu() -> Dict[str, Any]:
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
        "platform": platform.platform(),
        "kernel": platform.release(),
    }


def load_workloads(target_ids: Sequence[str], firmware_paths: Sequence[Path]) -> List[Dict[str, Any]]:
    """Resolve repeated CLI options before any runner subprocess is started."""
    if len(target_ids) != len(firmware_paths):
        raise ValueError(
            "--target and --firmware must have the same number of values; "
            "each target is paired with the firmware at the same position"
        )
    if not target_ids:
        raise ValueError("--target and --firmware must each be specified at least once")
    if set(target_ids) != REQUIRED_WORKLOAD_IDS:
        raise ValueError(
            "CPU application measurement requires exactly the registered PicoTetris r10 and PicoEdit r4 workloads"
        )
    workloads: List[Dict[str, Any]] = []
    seen = set()
    for index, (target_id, firmware_arg) in enumerate(zip(target_ids, firmware_paths), 1):
        if target_id in seen:
            raise ValueError("duplicate --target at position {}: {}".format(index, target_id))
        seen.add(target_id)
        target = picocalc.load_firmware_target(target_id)
        if target is None or target.get("status") != "active":
            raise ValueError("target must exist and be active: {}".format(target_id))
        firmware = Path(firmware_arg).expanduser().resolve()
        if not firmware.is_file():
            raise ValueError("firmware is missing for {}: {}".format(target_id, firmware))
        firmware_sha256 = sha256_file(firmware)
        expected_firmware_sha256 = target["artifacts"]["bin_sha256"]
        if firmware_sha256 != expected_firmware_sha256:
            raise ValueError(
                "firmware does not match target {} ({} != {})".format(
                    target_id, firmware_sha256, expected_firmware_sha256
                )
            )
        scenario = target.get("scenario")
        scenario_path = ROOT / scenario["path"] if scenario else None
        if scenario_path is not None:
            if not scenario_path.is_file():
                raise ValueError("scenario is missing for {}: {}".format(target_id, scenario_path))
            scenario_sha256 = sha256_file(scenario_path)
            if scenario_sha256 != scenario["sha256"]:
                raise ValueError("scenario does not match target {}".format(target_id))
        workloads.append(
            {
                "id": target_id,
                "revision": target["revision"],
                "target": target,
                "firmware": firmware,
                "firmware_sha256": firmware_sha256,
                "scenario_sha256": scenario["sha256"] if scenario else None,
                "contract_sha256": picocalc.firmware_target_contract_sha256(target),
            }
        )
    return workloads


def validate_target_firmware_pairs(
    target_ids: Sequence[str], firmware_paths: Sequence[Path]
) -> List[Dict[str, Any]]:
    """Public alias used by tests and callers that want preflight-only validation."""
    return load_workloads(target_ids, firmware_paths)


def target_command(
    target: Mapping[str, Any],
    firmware: Path,
    runner: Path,
    report: Path,
    uart: Path,
    snapshots: Path,
    *,
    backend_commit: Optional[str],
    behavior_trace: Optional[Path] = None,
    cpu_application_profile: Optional[Path] = None,
) -> List[str]:
    """Build a target command and require an explicit backend identity override."""
    if not backend_commit:
        raise ValueError(
            "backend_commit override is required; never use the registry accepted pin"
        )
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
        "--backend-commit", backend_commit,
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
    bootrom = contract.get("bootrom") or target.get("bootrom")
    if bootrom:
        bootrom_path = bootrom.get("path") if isinstance(bootrom, Mapping) else bootrom
        if bootrom_path:
            command.extend(["--bootrom", str(ROOT / bootrom_path)])
    sd = contract["sd"]
    if sd["attached"]:
        command.extend(["--sd", "--sd-format", sd["format"]])
    scenario = target.get("scenario")
    if scenario is not None:
        command.extend(["--scenario", str(ROOT / scenario["path"])])
        command.extend(["--snapshot-dir", str(snapshots)])
    audio_count, audio_sha256, audio_report_required = _audio_contract(target)
    if audio_count is not None or audio_sha256 is not None:
        if audio_count is None or audio_sha256 is None:
            raise ValueError(
                "target audio sink contract must specify both expected count and SHA-256"
            )
        command.extend(["--expect-audio-sink-count", str(audio_count)])
        command.extend(["--expect-audio-sink-sha256", audio_sha256])
    elif audio_report_required:
        # The PicoEdit contract intentionally expects an inactive audio sink.
        # Requesting the analysis sidecar makes the harness emit that report
        # without inventing a zero-count oracle (the harness rejects count 0).
        command.extend(["--audio-analysis", str(report.parent / "audio-analysis.json")])
    if behavior_trace is not None:
        command.extend(["--behavior-trace", str(behavior_trace)])
    if cpu_application_profile is not None:
        command.extend(["--cpu-application-profile", str(cpu_application_profile)])
    return command


def _audio_contract(target: Mapping[str, Any]) -> Tuple[Optional[int], Optional[str], bool]:
    """Extract audio report requirements from the registered report checks."""
    count: Optional[int] = None
    digest: Optional[str] = None
    report_required = False
    for check in target.get("acceptance", {}).get("report_checks", []):
        path = check.get("path")
        if not isinstance(path, str) or not path.startswith("audio_sink."):
            continue
        report_required = True
        if path == "audio_sink.dma_write_count":
            value = check.get("value")
            if type(value) is not int or value <= 0:
                raise ValueError("audio sink expected count must be a positive integer")
            count = value
        elif path == "audio_sink.pcm_sha256":
            value = check.get("value")
            if not isinstance(value, str) or len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError("audio sink expected SHA-256 is invalid")
            digest = value
    return count, digest, report_required


def report_value(report: Mapping[str, Any], path: str) -> Any:
    current: Any = report
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise KeyError(path)
        current = current[component]
    return current


def _without_backend_commit_checks(checks: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [
        check
        for check in checks
        if check.get("path") != "backend_build.commit"
    ]


def validate_report(
    workload: Mapping[str, Any], report: Mapping[str, Any], backend_commit: str
) -> None:
    """Validate report acceptance while allowing backend identity to differ."""
    target = workload["target"]
    required = [
        {"path": "schema_version", "op": "eq", "value": 8},
        {"path": "verdict.status", "op": "eq", "value": "pass"},
        {"path": "backend_build.commit", "op": "eq", "value": backend_commit},
        {"path": "backend_build.dirty", "op": "eq", "value": False},
        {"path": "firmware.sha256", "op": "eq", "value": workload["firmware_sha256"]},
        {"path": "step_quantum", "op": "eq", "value": target["runner"]["quantum"]},
        {"path": "cycle_limit", "op": "eq", "value": target["runner"]["cycles"]},
        {"path": "exception", "op": "eq", "value": None},
        {"path": "error", "op": "eq", "value": None},
        {"path": "unsupported_mmio", "op": "length_eq", "value": 0},
    ]
    failures = picocalc.check_report(
        dict(report),
        required + list(_without_backend_commit_checks(target["acceptance"]["report_checks"])),
    )
    if "backend_commit" in report and report.get("backend_commit") != backend_commit:
        failures.append("backend_commit does not match backend HEAD")
    expected_timeline = target["acceptance"].get("timeline_sha256")
    timeline = report.get("scenario", {}).get("steps") if isinstance(report.get("scenario"), Mapping) else None
    if expected_timeline and (
        timeline is None or picocalc.normalized_json_sha256(timeline) != expected_timeline
    ):
        failures.append("scenario timeline SHA-256 mismatch")
    if failures:
        raise ValueError("target report failed: {}".format("; ".join(failures)))


def validate_guest_projection_pair(
    baseline_report: Mapping[str, Any], candidate_report: Mapping[str, Any]
) -> None:
    if guest_observation_projection(baseline_report) != guest_observation_projection(candidate_report):
        raise ValueError("guest observation projection mismatch")


def behavior_summary(
    artifact: Mapping[str, Any], expected_backend_commit: Optional[str] = None
) -> Dict[str, Any]:
    if not isinstance(artifact, Mapping):
        raise ValueError("behavior artifact must be an object")
    if artifact.get("schema_version") != 1:
        raise ValueError("behavior artifact schema version is invalid")
    if artifact.get("normal_report_schema_version") != 8:
        raise ValueError("behavior artifact report schema version is invalid")
    if artifact.get("mode") != "correctness_trace_on":
        raise ValueError("behavior artifact mode is not correctness_trace_on")
    if artifact.get("valid_for_wall_time") is not False:
        raise ValueError("behavior artifact cannot be used for wall-time measurement")
    if artifact.get("behavior_projection_encoding") != "sorted-json-v1":
        raise ValueError("behavior artifact encoding is invalid")
    projection = artifact.get("behavior_projection")
    digest = artifact.get("behavior_sha256")
    if not isinstance(projection, Mapping) or not isinstance(digest, str):
        raise ValueError("behavior artifact is missing projection or digest")
    backend_build = artifact.get("backend_build")
    if not isinstance(backend_build, Mapping) or backend_build.get("dirty") is not False:
        raise ValueError("behavior artifact backend build is missing or dirty")
    if expected_backend_commit is not None and backend_build.get("commit") != expected_backend_commit:
        raise ValueError("behavior artifact backend commit does not match runner identity")
    if canonical_json_sha256(projection) != digest:
        raise ValueError("behavior artifact SHA-256 does not match projection")
    event_trace = projection.get("event_trace")
    if not isinstance(event_trace, Mapping):
        raise ValueError("behavior event trace is missing")
    if event_trace.get("schema_version") != 2:
        raise ValueError("behavior event trace schema version is invalid")
    if event_trace.get("canonical_encoding") != "PICOEM-EVENT-v1":
        raise ValueError("behavior event trace encoding is invalid")
    if event_trace.get("streaming") is not True or event_trace.get("retains_event_array") is not False:
        raise ValueError("behavior event trace is not the streaming form")
    total_events = event_trace.get("total_events")
    trace_sha256 = event_trace.get("sha256")
    if type(total_events) is not int or total_events < 0:
        raise ValueError("behavior event total is invalid")
    if not isinstance(trace_sha256, str) or len(trace_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in trace_sha256
    ):
        raise ValueError("behavior event stream SHA-256 is invalid")
    domains = event_trace.get("domains") if isinstance(event_trace, Mapping) else None
    if not isinstance(domains, list):
        raise ValueError("behavior event domains are missing")
    domain_summary = []
    names = set()
    domain_total = 0
    for domain in domains:
        if not isinstance(domain, Mapping) or not isinstance(domain.get("name"), str):
            raise ValueError("behavior domain is malformed")
        if domain["name"] in names:
            raise ValueError("behavior domain names are duplicated")
        names.add(domain["name"])
        domain_summary.append(
            {
                "name": domain["name"],
                "events": domain.get("events"),
                "sha256": domain.get("sha256"),
            }
        )
        if type(domain.get("events")) is not int or domain["events"] < 0:
            raise ValueError("behavior domain event count is invalid")
        domain_total += domain["events"]
        if not isinstance(domain.get("sha256"), str) or len(domain["sha256"]) != 64 or any(
            character not in "0123456789abcdef" for character in domain["sha256"]
        ):
            raise ValueError("behavior domain SHA-256 is invalid")
    if domain_total != total_events:
        raise ValueError("behavior event total does not match domain totals")
    return {
        "behavior_sha256": digest,
        "projection": projection,
        "domain_summary": domain_summary,
    }


def validate_behavior_pair(
    baseline_artifact: Mapping[str, Any], candidate_artifact: Mapping[str, Any],
    baseline_backend_commit: Optional[str] = None,
    candidate_backend_commit: Optional[str] = None,
) -> None:
    left = behavior_summary(baseline_artifact, baseline_backend_commit)
    right = behavior_summary(candidate_artifact, candidate_backend_commit)
    if left["projection"] != right["projection"]:
        raise ValueError("behavior projection mismatch")
    if left["behavior_sha256"] != right["behavior_sha256"]:
        raise ValueError("behavior SHA-256 mismatch")
    if left["domain_summary"] != right["domain_summary"]:
        raise ValueError("behavior domain summary mismatch")


def make_ab_schedule(workload_ids: Sequence[str], pairs: int = 10) -> List[Dict[str, Any]]:
    """Create the fixed 5 AB + 5 BA, alternating-workload schedule."""
    if not workload_ids:
        raise ValueError("at least one workload is required")
    if pairs < 1 or pairs % 2:
        raise ValueError("--pairs must be a positive even number for equal AB and BA")
    if len(set(workload_ids)) != len(workload_ids):
        raise ValueError("workload IDs must be unique")
    schedule: List[Dict[str, Any]] = []
    run_number = 1
    for pair in range(1, pairs + 1):
        order = "AB" if pair % 2 else "BA"
        selected = list(workload_ids) if pair % 2 else list(reversed(workload_ids))
        for workload_id in selected:
            roles = ("baseline", "candidate") if order == "AB" else ("candidate", "baseline")
            for role in roles:
                schedule.append(
                    {
                        "run_id": "run-{:03d}".format(run_number),
                        "pair": pair,
                        "order": order,
                        "workload": workload_id,
                        "role": role,
                    }
                )
                run_number += 1
    return schedule


def log_ratio(candidate_throughput: float, baseline_throughput: float) -> float:
    if candidate_throughput <= 0 or baseline_throughput <= 0:
        raise ValueError("throughput must be positive")
    return math.log(candidate_throughput / baseline_throughput)


def _median(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("at least one value is required")
    return statistics.median(values)


def median_iqr(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        raise ValueError("at least one value is required")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    lower = ordered[:midpoint]
    upper = ordered[-midpoint:] if midpoint else ordered
    q1 = statistics.median(lower) if lower else ordered[0]
    q3 = statistics.median(upper) if upper else ordered[-1]
    return {
        "median": statistics.median(ordered),
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
    }


def summarize_log_effect(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        raise ValueError("at least one log ratio is required")
    mean = statistics.mean(values)
    effects = [math.exp(value) - 1.0 for value in values]
    summary: Dict[str, Any] = {
        "n": len(values),
        "mean_log_ratio": mean,
        "geometric_mean_effect": math.exp(mean) - 1.0,
        "sample_sd_log_ratio": None,
        "ci95_log_ratio": None,
        "ci95_effect": None,
        "percent_effect": median_iqr(effects),
    }
    if len(values) > 1:
        deviation = statistics.stdev(values)
        critical = T_CRITICAL_95.get(len(values) - 1, 1.96)
        half_width = critical * deviation / math.sqrt(len(values))
        low, high = mean - half_width, mean + half_width
        summary.update(
            {
                "sample_sd_log_ratio": deviation,
                "ci95_log_ratio": [low, high],
                "ci95_effect": [math.exp(low) - 1.0, math.exp(high) - 1.0],
            }
        )
    return summary


def geometric_mean(values: Sequence[float]) -> float:
    if not values or any(value <= 0 for value in values):
        raise ValueError("geometric mean requires positive values")
    return math.exp(statistics.mean(math.log(value) for value in values))


def calibration_drift(pre: Sequence[float], post: Sequence[float]) -> Dict[str, Any]:
    if not pre or not post:
        raise ValueError("pre and post calibration require at least one value")
    pre_median = _median(pre)
    post_median = _median(post)
    if pre_median <= 0:
        raise ValueError("pre calibration median must be positive")
    relative = abs(post_median / pre_median - 1.0)
    return {
        "pre_values": list(pre),
        "post_values": list(post),
        "pre_median": pre_median,
        "post_median": post_median,
        "relative_drift": relative,
        "valid": relative <= 0.02,
    }


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _write_json_once(path: Path, value: object) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("refusing to overwrite existing artifact: {}".format(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def _refuse_existing(path: Path) -> None:
    if path.exists():
        raise ValueError("refusing to overwrite existing artifact: {}".format(path))


def _refuse_existing_files(directory: Path) -> None:
    """Refuse a phase directory that already contains any immutable leaf."""
    if not directory.exists():
        return
    if not directory.is_dir():
        raise ValueError("phase output is not a directory: {}".format(directory))
    for path in directory.rglob("*"):
        if path.is_file():
            raise ValueError("refusing to reuse phase output with existing artifact: {}".format(path))


def _record_root_and_phase(output: Path, phase: str) -> Tuple[Path, Path]:
    """Map the CLI phase directory to the canonical record root.

    The documented commands pass ``.../<record>/<phase>`` for admission,
    correctness, and profile, while ``ab`` passes the record root itself.
    Keeping this mapping here prevents a phase run from creating an orphaned
    record that the environment verifier cannot discover.
    """
    output = output.resolve()
    record_root = output.parent if output.name == phase else output
    _validate_record_root(record_root)
    if output.name == phase:
        return record_root, output
    return record_root, record_root / phase


def _validate_record_root(record_root: Path) -> None:
    records_root = (ROOT / "firmware-validation" / "records").resolve()
    if record_root.parent != records_root:
        raise ValueError(
            "record directory must be directly below firmware-validation/records: {}".format(
                record_root
            )
        )
    try:
        record_root.relative_to(records_root)
    except ValueError as error:
        raise ValueError(
            "record output must be below firmware-validation/records: {}".format(record_root)
        ) from error
    if not record_root.name.startswith("rp2040-cpu-"):
        raise ValueError("record directory must start with rp2040-cpu-: {}".format(record_root))


def _validate_batch_id(record_root: Path, batch_id: str) -> None:
    if batch_id != record_root.name:
        raise ValueError(
            "batch_id must equal the canonical record directory name: {} != {}".format(
                batch_id, record_root.name
            )
        )


def _write_sha256sums_once(record_root: Path) -> None:
    lines = []
    for path in sorted(record_root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        lines.append("{}  {}".format(sha256_file(path), path.relative_to(record_root).as_posix()))
    encoded = ("\n".join(lines) + "\n").encode("utf-8")
    path = record_root / "SHA256SUMS"
    # The checksum index is the one aggregate artifact that legitimately
    # changes when a later phase adds new immutable leaves to the same record.
    # Individual run/report/profile leaves are still protected by
    # ``_write_json_once``/``_refuse_existing``.
    path.write_bytes(encoded)


def _verify_existing_sha256sums(record_root: Path) -> None:
    """Reject a reused record whose immutable leaves were changed externally."""
    path = record_root / "SHA256SUMS"
    if not path.is_file():
        return
    listed = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError("record checksum index is unreadable: {}".format(path)) from error
    for line in lines:
        if not line.strip():
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as error:
            raise ValueError("record checksum index has an invalid line: {}".format(line)) from error
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("record checksum index has an invalid digest: {}".format(relative))
        artifact = (record_root / relative).resolve()
        try:
            artifact.relative_to(record_root.resolve())
        except ValueError as error:
            raise ValueError("record checksum entry escapes record root: {}".format(relative)) from error
        if artifact.name == "SHA256SUMS" or not artifact.is_file():
            raise ValueError("record checksum entry is not a regular artifact: {}".format(relative))
        if artifact in listed:
            raise ValueError("record checksum index contains a duplicate: {}".format(relative))
        if sha256_file(artifact) != digest:
            raise ValueError("record checksum mismatch: {}".format(relative))
        listed.add(artifact)
    for artifact in record_root.rglob("*"):
        resolved = artifact.resolve()
        if resolved.is_file() and resolved.name != "SHA256SUMS" and resolved not in listed:
            raise ValueError("record checksum index is missing: {}".format(artifact.relative_to(record_root)))


def _record_manifest(output: Path, identity: Mapping[str, Any]) -> None:
    manifest_path = output / "manifest.json"
    manifest = {
        "record_type": RECORD_TYPE,
        "record_version": SCHEMA_VERSION,
        **dict(identity),
    }
    if manifest_path.exists():
        if not (output / "SHA256SUMS").is_file():
            raise ValueError(
                "refusing to reuse a record without SHA256SUMS: {}".format(output)
            )
        _verify_existing_sha256sums(output)
        existing = _read_json(manifest_path)
        if not isinstance(existing, dict):
            raise ValueError("record manifest is not an object: {}".format(manifest_path))
        for field in (
            "record_type", "record_version", "record_id", "candidate_id", "workloads",
            "measurement_cpu",
        ):
            if existing.get(field) != manifest.get(field):
                raise ValueError("record manifest identity mismatch: {}".format(manifest_path))
        existing_features = set(normalize_feature_set(existing.get("feature_set", [])))
        new_features = set(normalize_feature_set(manifest.get("feature_set", [])))
        merged = dict(existing)
        merged["feature_set"] = sorted(existing_features | new_features)
        existing_identities = existing.get("backend_identities", {})
        new_identities = manifest.get("backend_identities", {})
        if not isinstance(existing_identities, dict) or not isinstance(new_identities, dict):
            raise ValueError("record manifest backend identities are malformed")
        merged_identities = dict(existing_identities)
        for label, value in new_identities.items():
            if label in merged_identities and merged_identities[label] != value:
                raise ValueError("record manifest backend identity mismatch: {}".format(label))
            merged_identities[label] = value
        merged["backend_identities"] = merged_identities
        if merged != existing:
            _write_json_replace(manifest_path, merged)
    else:
        if output.exists() and any(output.iterdir()):
            raise ValueError(
                "record root exists without a matching manifest: {}".format(output)
            )
        output.mkdir(parents=True, exist_ok=True)
        _write_json_once(manifest_path, manifest)


def _write_json_replace(path: Path, value: object) -> None:
    """Update aggregate metadata; immutable leaf artifacts use _write_json_once."""
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def _write_text_once(path: Path, text: str) -> None:
    encoded = text.encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("refusing to overwrite existing artifact: {}".format(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def _registered_report(workload: Mapping[str, Any]) -> Dict[str, Any]:
    target = workload["target"]
    validation = target.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("target validation attestation is missing")
    validation_ref = validation.get("record")
    if not isinstance(validation_ref, str) or not validation_ref:
        raise ValueError("target validation attestation has no record path")
    validation_path = ROOT / validation_ref
    validation_path = validation_path.resolve()
    try:
        validation_path.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("validation record path escapes repository: {}".format(validation_path)) from error
    validation_record = _read_json(validation_path)
    evidence = validation_record.get("evidence") if isinstance(validation_record, Mapping) else None
    if not isinstance(evidence, Mapping):
        raise ValueError("validation record has no evidence record path: {}".format(validation_path))
    record_ref = evidence.get("record")
    if not isinstance(record_ref, str) or not record_ref:
        raise ValueError("validation evidence has no record path: {}".format(validation_path))
    record_path = ROOT / record_ref
    record_path = record_path.resolve()
    try:
        record_path.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("validation evidence path escapes repository: {}".format(record_path)) from error
    expected_record_sha256 = evidence.get("sha256")
    if not isinstance(expected_record_sha256, str) or sha256_file(record_path) != expected_record_sha256:
        raise ValueError("validation evidence record SHA-256 mismatch: {}".format(record_path))
    record = _read_json(record_path)
    report_info = record.get("firmware_run", {}).get("report", {}) if isinstance(record, Mapping) else {}
    report_path = report_info.get("path")
    if not isinstance(report_path, str):
        raise ValueError("validation record has no firmware report path: {}".format(record_path))
    report_file = (ROOT / report_path).resolve()
    try:
        report_file.relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("firmware report path escapes repository: {}".format(report_file)) from error
    expected_report_sha256 = report_info.get("sha256")
    if not isinstance(expected_report_sha256, str) or sha256_file(report_file) != expected_report_sha256:
        raise ValueError("registered firmware report SHA-256 mismatch: {}".format(report_file))
    report = _read_json(report_file)
    if not isinstance(report, dict):
        raise ValueError("registered report is not an object: {}".format(report_path))
    return report


def _require_admission_gate(
    admission_record: Path,
    workloads: Sequence[Mapping[str, Any]],
    baseline_identity: Optional[Mapping[str, Any]] = None,
) -> None:
    """Require a passed common-baseline admission before later phases."""
    record = admission_record.resolve()
    _validate_record_root(record)
    if not (record / "SHA256SUMS").is_file():
        raise ValueError("admission record is missing SHA256SUMS")
    _verify_existing_sha256sums(record)
    manifest = _read_json(record / "manifest.json")
    decision = _read_json(record / "decision.json")
    if not isinstance(manifest, Mapping) or not isinstance(decision, Mapping):
        raise ValueError("admission record manifest/decision must be objects")
    expected_ids = [workload["id"] for workload in workloads]
    expected_workload_entries = _workload_manifest_entries(workloads)
    manifest_workloads = manifest.get("workloads")
    if (
        manifest.get("record_type") != RECORD_TYPE
        or manifest.get("record_version") != SCHEMA_VERSION
        or manifest.get("record_id") != record.name
        or manifest.get("candidate_id") != "P0-0"
        or not isinstance(manifest_workloads, list)
        or manifest_workloads != expected_workload_entries
    ):
        raise ValueError("admission record is not the fixed P0-0 workload gate")
    if decision.get("decision_kind") != "admission" or decision.get("status") != "pass":
        raise ValueError("admission record decision is not passing")
    manifest_identities = manifest.get("backend_identities")
    if not isinstance(manifest_identities, Mapping):
        raise ValueError("admission record manifest backend identities are missing")
    manifest_identity = manifest_identities.get("baseline_production")
    if not isinstance(manifest_identity, Mapping):
        raise ValueError("admission record baseline identity is missing")
    if (
        manifest_identity.get("role") != "baseline_production"
        or manifest_identity.get("provenance_role") != "baseline_production"
    ):
        raise ValueError("admission record baseline provenance role is invalid")
    if not isinstance(manifest.get("feature_set"), list) or manifest.get("feature_set") != manifest_identity.get("feature_set"):
        raise ValueError("admission record feature set differs from baseline identity")
    if (
        decision.get("record_id") != record.name
        or decision.get("candidate_id") != manifest.get("candidate_id")
        or decision.get("workloads") != manifest_workloads
        or decision.get("backend_identities") != manifest_identities
        or decision.get("feature_set") != manifest.get("feature_set")
    ):
        raise ValueError("admission record decision identity differs from manifest")
    if baseline_identity is not None and not _admission_baseline_identity_matches(
        manifest_identity, baseline_identity
    ):
        raise ValueError("admission record baseline identity differs from current baseline")
    correctness = decision.get("correctness")
    if not isinstance(correctness, Mapping) or correctness.get("status") != "pass":
        raise ValueError("admission record correctness gate is not passing")
    evidence = decision.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != len(expected_ids) or any(
        not isinstance(item, Mapping) for item in evidence
    ):
        raise ValueError("admission record evidence does not cover both workloads")
    evidence_by_workload = {}
    for item in evidence:
        workload_id = item.get("workload")
        if workload_id in evidence_by_workload or workload_id not in expected_ids:
            raise ValueError("admission record evidence has duplicate or unknown workload")
        evidence_by_workload[workload_id] = item
    admission_dir = record / "admission"
    expected_receipts = {
        "admission-{}.json".format(workload_id) for workload_id in expected_ids
    }
    if not admission_dir.is_dir() or {
        path.name for path in admission_dir.glob("*.json")
    } != expected_receipts:
        raise ValueError("admission record receipts do not cover exactly both workloads")
    for workload in workloads:
        workload_id = workload["id"]
        receipt_path = admission_dir / "admission-{}.json".format(workload_id)
        receipt = _read_json(receipt_path)
        evidence_item = evidence_by_workload.get(workload_id)
        if not isinstance(receipt, Mapping) or receipt != evidence_item:
            raise ValueError("admission receipt differs from decision evidence: {}".format(workload_id))
        if (
            receipt.get("schema_id") != DECISION_SCHEMA_ID
            or receipt.get("schema_version") != SCHEMA_VERSION
            or receipt.get("record_id") != record.name
            or receipt.get("candidate_id") != "P0-0"
            or receipt.get("decision_kind") != "admission"
            or receipt.get("status") != "pass"
            or receipt.get("workloads") != manifest_workloads
            or receipt.get("backend_identities") != manifest_identities
            or receipt.get("feature_set") != manifest.get("feature_set")
            or receipt.get("correctness") != {"status": "pass", "workload": workload_id}
        ):
            raise ValueError("admission receipt identity is invalid: {}".format(workload_id))
        if (
            receipt.get("backend_commit") != manifest_identity.get("commit")
            or receipt.get("runner_sha256") != manifest_identity.get("runner_sha256")
            or receipt.get("build_provenance_sha256") != manifest_identity.get("build_provenance_sha256")
            or receipt.get("registered_guest_observation_sha256")
            != guest_observation_sha256(_registered_report(workload))
        ):
            raise ValueError("admission receipt identity differs from registered baseline: {}".format(workload_id))
        runs = receipt.get("runs")
        if not isinstance(runs, list) or len(runs) != 2 or receipt.get("evidence") != runs:
            raise ValueError("admission receipt run evidence is invalid: {}".format(workload_id))
        registered_digest = receipt["registered_guest_observation_sha256"]
        for run in runs:
            if not isinstance(run, Mapping):
                raise ValueError("admission receipt run is not an object: {}".format(workload_id))
            if (
                run.get("backend_commit") != manifest_identity.get("commit")
                or run.get("runner_sha256") != manifest_identity.get("runner_sha256")
                or run.get("build_provenance_sha256") != manifest_identity.get("build_provenance_sha256")
                or run.get("guest_observation_sha256") != registered_digest
            ):
                raise ValueError("admission receipt run identity differs from baseline: {}".format(workload_id))


def _admission_baseline_identity_matches(
    admitted: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    """Compare the physical baseline execution identity across phase roles.

    P0-A2 intentionally reuses one production executable for both A and B and
    therefore gives that executable a sidecar role of ``production``.  The
    sidecar role (and its file digest) is metadata for the phase, not a change
    to the backend, executable, or effective feature set.  Keep the admission
    gate strict on those physical identities while allowing this documented
    role-only sidecar transition.
    """
    for key in ("commit", "dirty", "runner_sha256", "feature_set"):
        if admitted.get(key) != current.get(key):
            return False
    if admitted.get("build_provenance_sha256") == current.get("build_provenance_sha256"):
        return True
    return (
        admitted.get("role") == "baseline_production"
        and current.get("role") == "baseline_production"
        and admitted.get("provenance_role") == "baseline_production"
        and current.get("provenance_role") == "production"
    )


def _resource_usage() -> Dict[str, Optional[float]]:
    if resource is None:
        return {"user_seconds": None, "system_seconds": None, "max_rss": None}
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "user_seconds": usage.ru_utime,
        "system_seconds": usage.ru_stime,
        "max_rss": usage.ru_maxrss,
    }


def run_guest(
    workload: Mapping[str, Any], backend: Path, runner: Path, *,
    behavior_trace: Optional[Path] = None,
    cpu_application_profile: Optional[Path] = None,
    expected_backend_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Run one guest instance after all static identity checks have passed."""
    backend_identity = clean_backend_identity(backend)
    if not runner.is_file():
        raise ValueError("runner is missing: {}".format(runner))
    validate_runner_embedded_commit(runner, backend_identity["commit"])
    runner_sha256 = sha256_file(runner)
    provenance: Optional[Dict[str, Any]] = None
    if expected_backend_identity is not None:
        expected_feature_set = expected_backend_identity.get("feature_set", [])
        provenance = validate_runner_provenance(
            runner,
            backend_identity["commit"],
            expected_feature_set,
            expected_role=expected_backend_identity.get("role"),
            allow_production_role=expected_backend_identity.get("provenance_role") == "production",
        )
        if backend_identity != {
            "commit": expected_backend_identity.get("commit"),
            "dirty": expected_backend_identity.get("dirty"),
        }:
            raise ValueError("backend identity changed after preflight")
        if runner_sha256 != expected_backend_identity.get("runner_sha256"):
            raise ValueError("runner identity changed after preflight")
        if provenance["sha256"] != expected_backend_identity.get("build_provenance_sha256"):
            raise ValueError("runner build provenance changed after preflight")
    with tempfile.TemporaryDirectory(prefix="picocalc-rp2040-cpu-") as temporary:
        directory = Path(temporary)
        snapshots = directory / "snapshots"
        snapshots.mkdir()
        report_path = directory / "report.json"
        uart_path = directory / "uart.bin"
        trace_path = behavior_trace or (directory / "behavior-trace.json")
        profile_path = cpu_application_profile
        if behavior_trace is not None:
            behavior_trace.parent.mkdir(parents=True, exist_ok=True)
        if cpu_application_profile is not None:
            cpu_application_profile.parent.mkdir(parents=True, exist_ok=True)
        command = target_command(
            workload["target"], workload["firmware"], runner, report_path, uart_path, snapshots,
            backend_commit=backend_identity["commit"],
            behavior_trace=trace_path if behavior_trace is not None else None,
            cpu_application_profile=profile_path,
        )
        started = time.perf_counter_ns()
        before_usage = _resource_usage()
        result = subprocess.run(
            command,
            cwd=str(backend),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        wall_ns = time.perf_counter_ns() - started
        after_usage = _resource_usage()
        if result.returncode != 0:
            raise ValueError("runner exited {} for {}".format(result.returncode, workload["id"]))
        if not report_path.is_file():
            raise ValueError("runner did not write report: {}".format(report_path))
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes)
        validate_report(workload, report, backend_identity["commit"])
        if behavior_trace is not None and not behavior_trace.is_file():
            raise ValueError("runner did not write behavior trace: {}".format(behavior_trace))
        if cpu_application_profile is not None and not cpu_application_profile.is_file():
            raise ValueError("runner did not write CPU profile: {}".format(cpu_application_profile))
        wall_seconds = wall_ns / 1_000_000_000
        cycles = report["cycles"]
        if type(cycles) is not int or cycles <= 0 or wall_ns <= 0:
            raise ValueError("runner report has invalid positive timing/cycle values")
        measurement: Dict[str, Any] = {
            "wall_ns": wall_ns,
            "wall_seconds": wall_seconds,
            "cycles": cycles,
            "stop_reason": report.get("stop_reason"),
            "elapsed_us": report["elapsed_us"],
            "emulated_cycles_per_wall_second": cycles / wall_seconds,
            "report_sha256": sha256_bytes(report_bytes),
            "guest_observation_sha256": guest_observation_sha256(report),
            "uart_sha256": sha256_file(uart_path) if uart_path.is_file() else None,
            "snapshot_sha256": {
                path.name: sha256_file(path) for path in sorted(snapshots.glob("*.png"))
            },
            "host_usage_delta": {
                "user_seconds": (
                    after_usage["user_seconds"] - before_usage["user_seconds"]
                    if after_usage["user_seconds"] is not None and before_usage["user_seconds"] is not None
                    else None
                ),
                "system_seconds": (
                    after_usage["system_seconds"] - before_usage["system_seconds"]
                    if after_usage["system_seconds"] is not None and before_usage["system_seconds"] is not None
                    else None
                ),
                # Linux exposes max RSS through RUSAGE_CHILDREN as a
                # process-lifetime high-water mark, not a per-run delta.
                "max_rss_platform_units": after_usage["max_rss"],
                "max_rss_scope": "children_cumulative",
            },
            "backend_commit": backend_identity["commit"],
            "runner_sha256": runner_sha256,
            "build_provenance_sha256": provenance["sha256"] if provenance is not None else None,
        }
        return {"report": report, "measurement": measurement}


def _set_cpu_affinity(cpu: Optional[int]) -> Optional[List[int]]:
    if cpu is None:
        return None
    if not hasattr(os, "sched_setaffinity") or not hasattr(os, "sched_getaffinity"):
        raise ValueError("--cpu needs Linux sched_setaffinity")
    before = sorted(os.sched_getaffinity(0))
    if cpu not in before:
        raise ValueError("--cpu is outside the allowed affinity set")
    os.sched_setaffinity(0, {cpu})
    return before


def _restore_cpu_affinity(before: Optional[List[int]]) -> None:
    if before is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, set(before))


def preflight_backends(
    backends: Iterable[Path], runners: Iterable[Path],
    labels: Sequence[str] = ("baseline", "candidate"),
    feature_sets: Optional[Sequence[Sequence[str]]] = None,
    allow_production_role: bool = False,
) -> Dict[str, Dict[str, Any]]:
    backend_list = list(backends)
    runner_list = list(runners)
    if len(backend_list) != 2 or len(runner_list) != 2 or len(labels) != 2:
        raise ValueError("baseline and candidate backend/runner pairs are both required")
    if allow_production_role and (
        tuple(labels) != ("baseline_production", "candidate_production")
        or runner_list[0].resolve() != runner_list[1].resolve()
    ):
        raise ValueError(
            "shared production provenance is allowed only for P0-A2's identical production runner"
        )
    if feature_sets is None:
        feature_list: List[Sequence[str]] = [(), ()]
    else:
        feature_list = list(feature_sets)
        if len(feature_list) != 2:
            raise ValueError("two backend feature sets are required")
    identities: Dict[str, Dict[str, Any]] = {}
    for label, backend, runner, features in zip(labels, backend_list, runner_list, feature_list):
        identity = clean_backend_identity(backend)
        if not runner.is_file():
            raise ValueError("{} runner is missing: {}".format(label, runner))
        validate_runner_embedded_commit(runner, identity["commit"])
        normalized_features = effective_feature_set(features)
        provenance = validate_runner_provenance(
            runner,
            identity["commit"],
            normalized_features,
            expected_role=label,
            allow_production_role=allow_production_role,
        )
        identity["runner_sha256"] = sha256_file(runner)
        identity["feature_set"] = normalized_features
        identity["build_provenance_sha256"] = provenance["sha256"]
        identity["role"] = label
        identity["provenance_role"] = provenance["role"]
        identities[label] = identity
    return identities


def _workload_manifest_entries(workloads: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": workload["id"],
            "revision": workload["revision"],
            "firmware_sha256": workload["firmware_sha256"],
            "scenario_sha256": workload["scenario_sha256"],
            "contract_sha256": workload["contract_sha256"],
        }
        for workload in workloads
    ]


def _base_manifest(
    batch_id: str, workloads: Sequence[Mapping[str, Any]], identities: Mapping[str, Any],
    *, candidate_id: str, cpu: Optional[int], feature_set: Sequence[str] = ()
) -> Dict[str, Any]:
    all_features = set(effective_feature_set(feature_set))
    for identity in identities.values():
        if isinstance(identity, Mapping) and isinstance(identity.get("feature_set"), list):
            all_features.update(normalize_feature_set(identity["feature_set"]))
    return {
        "record_id": batch_id,
        "candidate_id": candidate_id,
        "workloads": _workload_manifest_entries(workloads),
        "backend_identities": dict(identities),
        "feature_set": sorted(all_features),
        "host": host_cpu(),
        "measurement_cpu": cpu,
    }


def _decision_context(
    workloads: Sequence[Mapping[str, Any]], identities: Mapping[str, Any],
    *, feature_set: Sequence[str] = ()
) -> Dict[str, Any]:
    """Return identity metadata shared by every phase decision artifact.

    The manifest remains the canonical record identity, but a standalone
    decision must still be auditable after it is copied out of the record
    directory.  Keep workload and executable/backend identities in the
    decision itself rather than relying on a reader to infer them from a
    phase-specific leaf.
    """
    return {
        "workloads": _workload_manifest_entries(workloads),
        "backend_identities": dict(identities),
        "feature_set": effective_feature_set(feature_set),
        "host": host_cpu(),
    }


def _manifest_decision_context(
    record_root: Path, workloads: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Any], *, feature_set: Sequence[str] = ()
) -> Dict[str, Any]:
    """Build decision metadata from the phase-merged manifest identity."""
    manifest = _read_json(record_root / "manifest.json")
    if not isinstance(manifest, Mapping):
        raise ValueError("record manifest is not an object: {}".format(record_root))
    merged_identities = manifest.get("backend_identities", identities)
    merged_features = manifest.get("feature_set", feature_set)
    if not isinstance(merged_identities, Mapping) or not isinstance(merged_features, list):
        raise ValueError("record manifest decision identity is malformed: {}".format(record_root))
    return _decision_context(
        workloads, merged_identities, feature_set=merged_features,
    )


def run_admission(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("admit requires exactly the two registered workloads")
    identity = clean_backend_identity(args.backend)
    if not args.runner.is_file():
        raise ValueError("runner is missing: {}".format(args.runner))
    validate_runner_embedded_commit(args.runner, identity["commit"])
    declared_features = normalize_feature_set(getattr(args, "feature_set", []))
    provenance = validate_runner_provenance(
        args.runner, identity["commit"], declared_features,
        expected_role="baseline_production",
    )
    identity["runner_sha256"] = sha256_file(args.runner)
    identity["feature_set"] = effective_feature_set(declared_features)
    identity["build_provenance_sha256"] = provenance["sha256"]
    identity["role"] = "baseline_production"
    identity["provenance_role"] = provenance["role"]
    record_root, phase_dir = _record_root_and_phase(args.output, "admission")
    batch_id = args.batch_id or record_root.name
    _validate_batch_id(record_root, batch_id)
    manifest_identity = _base_manifest(
        batch_id, workloads, {"baseline_production": identity}, candidate_id="P0-0",
        cpu=args.cpu, feature_set=getattr(args, "feature_set", []),
    )
    _refuse_existing_files(phase_dir)
    _record_manifest(record_root, manifest_identity)
    decision_context = _manifest_decision_context(
        record_root, workloads, {"baseline_production": identity},
        feature_set=getattr(args, "feature_set", []),
    )
    registered_reports = {}
    registered_digests = {}
    for workload in workloads:
        registered = _registered_report(workload)
        registered_reports[workload["id"]] = registered
        registered_digests[workload["id"]] = guest_observation_sha256(registered)
    before = _set_cpu_affinity(args.cpu)
    try:
        receipts = []
        for workload in workloads:
            registered = registered_reports[workload["id"]]
            registered_digest = registered_digests[workload["id"]]
            runs = []
            for index in range(2):
                result = run_guest(
                    workload, args.backend, args.runner,
                    expected_backend_identity=identity,
                )
                validate_guest_projection_pair(registered, result["report"])
                runs.append(result)
            if runs[0]["measurement"]["guest_observation_sha256"] != runs[1]["measurement"]["guest_observation_sha256"]:
                raise ValueError("admission determinism mismatch for {}".format(workload["id"]))
            receipt = {
                "schema_id": DECISION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": batch_id,
                "candidate_id": "P0-0",
                "decision_kind": "admission",
                "workload": workload["id"],
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "workloads": _workload_manifest_entries(workloads),
                "backend_identities": {"baseline_production": identity},
                "feature_set": identity["feature_set"],
                "registered_guest_observation_sha256": registered_digest,
                "runs": [run["measurement"] for run in runs],
                "correctness": {"status": "pass", "workload": workload["id"]},
                "evidence": [run["measurement"] for run in runs],
                "status": "pass",
            }
            _write_json_once(phase_dir / "admission-{}.json".format(workload["id"]), receipt)
            receipts.append(receipt)
        _write_json_replace(
            record_root / "decision.json",
            {
                "schema_id": DECISION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": batch_id,
                "candidate_id": "P0-0",
                "decision_kind": "admission",
                "status": "pass",
                "correctness": {"status": "pass", "workloads": [r["workload"] for r in receipts]},
                "evidence": receipts,
                **decision_context,
            },
        )
        _write_sha256sums_once(record_root)
    finally:
        _restore_cpu_affinity(before)
    return 0


def _correctness_one(
    workload: Mapping[str, Any], args: argparse.Namespace, output: Path,
    identities: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    baseline = run_guest(
        workload, args.baseline_backend, args.baseline_runner,
        expected_backend_identity=identities["baseline_production"],
    )
    candidate = run_guest(
        workload, args.candidate_backend, args.candidate_runner,
        expected_backend_identity=identities["candidate_production"],
    )
    validate_guest_projection_pair(baseline["report"], candidate["report"])
    record: Dict[str, Any] = {
        "schema_id": AB_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "correctness",
        "record_id": getattr(args, "_resolved_batch_id", args.batch_id or output.parent.parent.name),
        "candidate_id": args.candidate_id,
        "workload": workload["id"],
        "trace_required": not args.final_report_only,
        "baseline": baseline["measurement"],
        "candidate": candidate["measurement"],
        "baseline_guest_observation_sha256": baseline["measurement"]["guest_observation_sha256"],
        "candidate_guest_observation_sha256": candidate["measurement"]["guest_observation_sha256"],
        "guest_observation_equal": True,
        "guest_observation_sha256": baseline["measurement"]["guest_observation_sha256"],
        "behavior_equal": bool(args.final_report_only),
        "status": "pass",
    }
    if not args.final_report_only:
        if args.baseline_trace_runner is None or args.candidate_trace_runner is None:
            raise ValueError("correctness requires both trace runners unless --final-report-only")
        _refuse_existing(output / "baseline-behavior.json")
        _refuse_existing(output / "candidate-behavior.json")
        base_trace = run_guest(
            workload, args.baseline_backend, args.baseline_trace_runner,
            behavior_trace=output / "baseline-behavior.json",
            expected_backend_identity=identities["baseline_trace"],
        )
        cand_trace = run_guest(
            workload, args.candidate_backend, args.candidate_trace_runner,
            behavior_trace=output / "candidate-behavior.json",
            expected_backend_identity=identities["candidate_trace"],
        )
        validate_guest_projection_pair(baseline["report"], base_trace["report"])
        validate_guest_projection_pair(candidate["report"], cand_trace["report"])
        base_artifact = _read_json(output / "baseline-behavior.json")
        cand_artifact = _read_json(output / "candidate-behavior.json")
        baseline_trace_commit = base_trace["report"]["backend_build"]["commit"]
        candidate_trace_commit = cand_trace["report"]["backend_build"]["commit"]
        validate_behavior_pair(
            base_artifact,
            cand_artifact,
            baseline_backend_commit=baseline_trace_commit,
            candidate_backend_commit=candidate_trace_commit,
        )
        baseline_behavior = behavior_summary(base_artifact, baseline_trace_commit)
        candidate_behavior = behavior_summary(cand_artifact, candidate_trace_commit)
        record["behavior"] = {
            "baseline": baseline_behavior,
            "candidate": candidate_behavior,
            "status": "pass",
        }
        record["behavior_equal"] = True
    _write_json_once(output / "baseline-report.json", baseline["report"])
    _write_json_once(output / "candidate-report.json", candidate["report"])
    _write_json_once(output / "baseline-projection.json", guest_observation_projection(baseline["report"]))
    _write_json_once(output / "candidate-projection.json", guest_observation_projection(candidate["report"]))
    _write_json_once(output / "comparison.json", record)
    return record


def run_correctness(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("correctness requires exactly the two registered workloads")
    if args.final_report_only and args.candidate_id != "P0-A2":
        raise ValueError("--final-report-only is reserved for candidate_id P0-A2")
    identities = preflight_backends(
        [args.baseline_backend, args.candidate_backend],
        [args.baseline_runner, args.candidate_runner],
        labels=("baseline_production", "candidate_production"),
        feature_sets=((), getattr(args, "feature_set", [])),
        allow_production_role=(
            args.final_report_only
            and args.candidate_id == "P0-A2"
            and args.baseline_runner.resolve() == args.candidate_runner.resolve()
        ),
    )
    if not args.final_report_only and (args.baseline_trace_runner is None or args.candidate_trace_runner is None):
        raise ValueError("both trace runners are required unless --final-report-only")
    if not args.final_report_only:
        if args.baseline_trace_runner is None or args.candidate_trace_runner is None:
            raise ValueError("both trace runners are required unless --final-report-only")
        identities.update(
            preflight_backends(
                [args.baseline_backend, args.candidate_backend],
                [args.baseline_trace_runner, args.candidate_trace_runner],
                labels=("baseline_trace", "candidate_trace"),
                feature_sets=(
                    ("behavior-trace",),
                    tuple(
                        normalize_feature_set(
                            ["behavior-trace", *getattr(args, "feature_set", [])]
                        )
                    ),
                ),
            )
        )
    _require_admission_gate(args.admission_record, workloads, identities["baseline_production"])
    record_root, phase_dir = _record_root_and_phase(args.output, "correctness")
    batch_id = args.batch_id or record_root.name
    _validate_batch_id(record_root, batch_id)
    args._resolved_batch_id = batch_id
    _refuse_existing_files(phase_dir)
    _record_manifest(
        record_root,
        _base_manifest(
            batch_id, workloads, identities, candidate_id=args.candidate_id, cpu=args.cpu,
            feature_set=getattr(args, "feature_set", []),
        ),
    )
    decision_context = _manifest_decision_context(
        record_root, workloads, identities, feature_set=getattr(args, "feature_set", []),
    )
    before = _set_cpu_affinity(args.cpu)
    records = []
    try:
        for workload in workloads:
            records.append(
                _correctness_one(
                    workload, args, phase_dir / workload["id"], identities,
                )
            )
    finally:
        _restore_cpu_affinity(before)
    _write_json_replace(
        record_root / "decision.json",
        {
            "schema_id": DECISION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "record_id": batch_id,
            "candidate_id": args.candidate_id,
            "decision_kind": "correctness",
            "status": "pass",
            "correctness": {"status": "pass", "workloads": [r["workload"] for r in records]},
            **decision_context,
        },
    )
    _write_sha256sums_once(record_root)
    return 0


def _run_calibration(
    workload: Mapping[str, Any], backend: Path, runner: Path, count: int,
    expected_backend_identity: Optional[Mapping[str, Any]] = None,
) -> List[float]:
    values = []
    for _ in range(count):
        values.append(
            run_guest(
                workload, backend, runner,
                expected_backend_identity=expected_backend_identity,
            )["measurement"]["emulated_cycles_per_wall_second"]
        )
    return values


def _require_correctness_gate(
    record_root: Path,
    workloads: Sequence[Mapping[str, Any]],
    identities: Optional[Mapping[str, Mapping[str, Any]]] = None,
    required_trace: Optional[bool] = None,
) -> None:
    """Revalidate immutable correctness artifacts before any A/B run."""
    failures: List[str] = []
    identities = identities or {}
    try:
        manifest = _read_json(record_root / "manifest.json")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("correctness gate requires a readable manifest: {}".format(error)) from error
    if not isinstance(manifest, Mapping):
        raise ValueError("correctness gate requires an object manifest")
    manifest_identities = manifest.get("backend_identities", {})
    if not isinstance(manifest_identities, Mapping):
        raise ValueError("correctness gate manifest backend identities are malformed")
    for label, expected_identity in identities.items():
        recorded_identity = manifest_identities.get(label)
        if recorded_identity is not None and recorded_identity != expected_identity:
            failures.append("manifest backend identity differs for {}".format(label))
    for workload in workloads:
        workload_id = workload["id"]
        workload_dir = record_root / "correctness" / workload_id
        comparison_path = workload_dir / "comparison.json"
        if not comparison_path.is_file():
            failures.append("missing correctness comparison for {}".format(workload_id))
            continue
        try:
            comparison = _read_json(comparison_path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            failures.append("unreadable correctness comparison for {}: {}".format(workload_id, error))
            continue
        if not isinstance(comparison, Mapping):
            failures.append("correctness comparison for {} is not an object".format(workload_id))
            continue
        if comparison.get("schema_id") != AB_SCHEMA_ID or comparison.get("artifact_type") != "correctness":
            failures.append("correctness comparison schema mismatch for {}".format(workload_id))
        if comparison.get("record_id") != record_root.name:
            failures.append("correctness record_id mismatch for {}".format(workload_id))
        if comparison.get("workload") != workload_id:
            failures.append("correctness workload mismatch for {}".format(workload_id))
        if comparison.get("status") != "pass" or comparison.get("guest_observation_equal") is not True:
            failures.append("correctness gate failed for {}".format(workload_id))
        trace_required = comparison.get("trace_required")
        if not isinstance(trace_required, bool):
            failures.append("correctness trace_required is invalid for {}".format(workload_id))
        elif required_trace is not None and trace_required is not required_trace:
            failures.append(
                "correctness trace_required={} does not match A/B mode for {}".format(
                    trace_required, workload_id
                )
            )

        reports: Dict[str, Mapping[str, Any]] = {}
        projections: Dict[str, Mapping[str, Any]] = {}
        for role in ("baseline", "candidate"):
            report_path = workload_dir / "{}-report.json".format(role)
            projection_path = workload_dir / "{}-projection.json".format(role)
            try:
                report = _read_json(report_path)
                projection = _read_json(projection_path)
            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                failures.append("{} correctness artifacts are unreadable for {}: {}".format(role, workload_id, error))
                continue
            if not isinstance(report, Mapping) or not isinstance(projection, Mapping):
                failures.append("{} correctness artifacts are not objects for {}".format(role, workload_id))
                continue
            reports[role] = report
            projections[role] = projection
            identity = identities.get("{}_production".format(role), {})
            expected_commit = identity.get("commit") if isinstance(identity, Mapping) else None
            measurement = comparison.get(role)
            if not isinstance(measurement, Mapping):
                failures.append("{} correctness measurement is missing for {}".format(role, workload_id))
            elif isinstance(identity, Mapping):
                if measurement.get("backend_commit") != identity.get("commit"):
                    failures.append("{} correctness measurement backend commit differs for {}".format(role, workload_id))
                if measurement.get("runner_sha256") != identity.get("runner_sha256"):
                    failures.append("{} correctness measurement runner SHA-256 differs for {}".format(role, workload_id))
                if measurement.get("build_provenance_sha256") != identity.get("build_provenance_sha256"):
                    failures.append(
                        "{} correctness measurement build provenance SHA-256 differs for {}".format(
                            role, workload_id
                        )
                    )
            report_commit = (
                report.get("backend_build", {}).get("commit")
                if isinstance(report.get("backend_build"), Mapping)
                else None
            )
            commit = expected_commit or report_commit
            if not isinstance(commit, str):
                failures.append("{} correctness backend commit is missing for {}".format(role, workload_id))
            else:
                try:
                    validate_report(workload, report, commit)
                except (KeyError, OSError, UnicodeError, ValueError, TypeError, IndexError) as error:
                    failures.append(
                        "{} correctness report failed validation for {}: {}".format(
                            role, workload_id, error
                        )
                    )
            expected_projection = guest_observation_projection(report)
            if dict(projection) != expected_projection:
                failures.append("{} stored projection differs from report for {}".format(role, workload_id))
            digest = canonical_json_sha256(projection)
            comparison_digest = comparison.get("{}_guest_observation_sha256".format(role))
            if comparison_digest != digest:
                failures.append("{} correctness digest differs from stored projection for {}".format(role, workload_id))

        if set(reports) == {"baseline", "candidate"} and set(projections) == {"baseline", "candidate"}:
            if projections["baseline"] != projections["candidate"]:
                failures.append("correctness projections differ for {}".format(workload_id))
            if comparison.get("guest_observation_sha256") != canonical_json_sha256(projections["baseline"]):
                failures.append("correctness canonical digest mismatch for {}".format(workload_id))

        if trace_required is True:
            behavior_paths = {
                role: workload_dir / "{}-behavior.json".format(role)
                for role in ("baseline", "candidate")
            }
            if not all(path.is_file() for path in behavior_paths.values()):
                failures.append("behavior trace artifacts are missing for {}".format(workload_id))
            else:
                try:
                    behavior = {role: _read_json(path) for role, path in behavior_paths.items()}
                    baseline_backend = reports.get("baseline", {}).get("backend_build")
                    candidate_backend = reports.get("candidate", {}).get("backend_build")
                    baseline_commit = baseline_backend.get("commit") if isinstance(baseline_backend, Mapping) else None
                    candidate_commit = (
                        candidate_backend.get("commit")
                        if isinstance(candidate_backend, Mapping)
                        else None
                    )
                    baseline_trace_identity = identities.get("baseline_trace", {})
                    candidate_trace_identity = identities.get("candidate_trace", {})
                    expected_baseline_trace_commit = baseline_trace_identity.get("commit") or baseline_commit
                    expected_candidate_trace_commit = candidate_trace_identity.get("commit") or candidate_commit
                    validate_behavior_pair(
                        behavior["baseline"], behavior["candidate"],
                        baseline_backend_commit=expected_baseline_trace_commit,
                        candidate_backend_commit=expected_candidate_trace_commit,
                    )
                    recorded_behavior = comparison.get("behavior")
                    if not isinstance(recorded_behavior, Mapping):
                        failures.append("behavior summary is missing for {}".format(workload_id))
                    else:
                        for role, commit in (
                            ("baseline", expected_baseline_trace_commit),
                            ("candidate", expected_candidate_trace_commit),
                        ):
                            if recorded_behavior.get(role) != behavior_summary(behavior[role], commit):
                                failures.append(
                                    "behavior summary differs from artifact for {} {}".format(
                                        workload_id, role
                                    )
                                )
                except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                    failures.append("behavior trace validation failed for {}: {}".format(workload_id, error))
            if comparison.get("behavior_equal") is not True:
                failures.append("behavior trace gate failed for {}".format(workload_id))
        elif trace_required is False and comparison.get("behavior_equal") is not True:
            failures.append("final-report correctness gate failed for {}".format(workload_id))
    if failures:
        raise ValueError("correctness gate required before A/B run: {}".format("; ".join(failures)))


def run_ab(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("ab requires exactly the two registered workloads")
    if args.pairs != 10:
        raise ValueError("ab fixes --pairs at 10 (5 AB + 5 BA)")
    if args.warmup != 1:
        raise ValueError("ab fixes --warmup at 1")
    if args.calibration_runs != 3:
        raise ValueError("ab fixes --calibration-runs at 3")
    if args.cpu is None:
        raise ValueError("ab requires --cpu for affinity pinning")
    if getattr(args, "final_report_only", False) and args.candidate_id != "P0-A2":
        raise ValueError("--final-report-only is reserved for candidate_id P0-A2")
    identities = preflight_backends(
        [args.baseline_backend, args.candidate_backend],
        [args.baseline_runner, args.candidate_runner],
        labels=("baseline_production", "candidate_production"),
        feature_sets=((), getattr(args, "feature_set", [])),
        allow_production_role=(
            getattr(args, "final_report_only", False)
            and args.candidate_id == "P0-A2"
            and args.baseline_runner.resolve() == args.candidate_runner.resolve()
        ),
    )
    _require_admission_gate(args.admission_record, workloads, identities["baseline_production"])
    batch_id = args.batch_id
    if not batch_id:
        raise ValueError("--batch-id is required for ab")
    record_root = args.output.resolve()
    _validate_record_root(record_root)
    _validate_batch_id(record_root, batch_id)
    _require_correctness_gate(
        record_root, workloads, identities,
        required_trace=not getattr(args, "final_report_only", False),
    )
    _refuse_existing_files(record_root / "ab")
    for aggregate in (record_root / "summary.json", record_root / "decision.md", record_root / "hotpath-disassembly.txt"):
        _refuse_existing(aggregate)
    _record_manifest(
        record_root,
        _base_manifest(
            batch_id, workloads, identities, candidate_id=args.candidate_id, cpu=args.cpu,
            feature_set=getattr(args, "feature_set", []),
        ),
    )
    decision_context = _manifest_decision_context(
        record_root, workloads, identities, feature_set=getattr(args, "feature_set", []),
    )
    before = _set_cpu_affinity(args.cpu)
    try:
        calibration_workload = next(
            (workload for workload in workloads if workload["id"].startswith("picotetris-")),
            None,
        )
        if calibration_workload is None:
            raise ValueError("ab requires a registered PicoTetris workload for calibration")
        for _ in range(args.warmup):
            for workload in workloads:
                run_guest(
                    workload, args.baseline_backend, args.baseline_runner,
                    expected_backend_identity=identities["baseline_production"],
                )
                run_guest(
                    workload, args.candidate_backend, args.candidate_runner,
                    expected_backend_identity=identities["candidate_production"],
                )
        pre = _run_calibration(
            calibration_workload, args.baseline_backend, args.baseline_runner,
            args.calibration_runs, identities["baseline_production"],
        )
        schedule = make_ab_schedule([workload["id"] for workload in workloads], args.pairs)
        by_id = {workload["id"]: workload for workload in workloads}
        results: Dict[str, Dict[int, Dict[str, Any]]] = {workload["id"]: {} for workload in workloads}
        for item in schedule:
            workload = by_id[item["workload"]]
            backend = args.baseline_backend if item["role"] == "baseline" else args.candidate_backend
            runner = args.baseline_runner if item["role"] == "baseline" else args.candidate_runner
            result = run_guest(
                workload, backend, runner,
                expected_backend_identity=identities["{}_production".format(item["role"])],
            )
            leaf = {
                "schema_id": AB_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": batch_id,
                "candidate_id": args.candidate_id,
                "artifact_type": "run",
                **item,
                **result["measurement"],
            }
            _write_json_once(record_root / "ab" / "{}.json".format(item["run_id"]), leaf)
            results[item["workload"]].setdefault(item["pair"], {})[item["role"]] = leaf
        post = _run_calibration(
            calibration_workload,
            args.baseline_backend,
            args.baseline_runner,
            args.calibration_runs,
            identities["baseline_production"],
        )
        calibration = calibration_drift(pre, post)
        if not calibration["valid"]:
            invalid_summary = {
                "schema_id": AB_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": batch_id,
                "candidate_id": args.candidate_id,
                "artifact_type": "summary",
                "status": "invalid",
                "pairs": args.pairs,
                "measured_runs": len(schedule),
                "schedule": {"ab": args.pairs // 2, "ba": args.pairs // 2},
                "calibration": calibration,
                "workloads": {},
                "pair_results": [],
                "combined": {},
                "host": host_cpu(),
            }
            _write_json_once(record_root / "summary.json", invalid_summary)
            _write_json_replace(
                record_root / "decision.json",
                {
                    "schema_id": DECISION_SCHEMA_ID,
                    "schema_version": SCHEMA_VERSION,
                    "record_id": batch_id,
                    "candidate_id": args.candidate_id,
                    "decision_kind": "invalid",
                    "status": "invalid",
                    "reasons": ["calibration drift exceeded 2%", str(calibration)],
                    "statistics": invalid_summary,
                    **decision_context,
                },
            )
            _write_text_once(
                record_root / "decision.md",
                "# RP2040 CPU candidate decision\n\nBatch invalid: calibration drift exceeded 2%.\n",
            )
            _write_text_once(
                record_root / "hotpath-disassembly.txt",
                "P0-A1: hot-path disassembly is not collected until P0-B.\n",
            )
            _write_sha256sums_once(record_root)
            raise ValueError("calibration drift exceeded 2%: {}".format(calibration))
        summaries: Dict[str, Any] = {}
        combined_values: List[List[float]] = []
        pair_results: List[Dict[str, Any]] = []
        for workload in workloads:
            ratios = []
            for pair in range(1, args.pairs + 1):
                pair_result = results[workload["id"]][pair]
                ratio = log_ratio(
                    pair_result["candidate"]["emulated_cycles_per_wall_second"],
                    pair_result["baseline"]["emulated_cycles_per_wall_second"],
                )
                ratios.append(ratio)
                pair_results.append(
                    {
                        "workload": workload["id"],
                        "pair_index": pair,
                        "order": pair_result["baseline"]["order"],
                        "run_ids": [
                            pair_result["baseline"]["run_id"],
                            pair_result["candidate"]["run_id"],
                        ],
                        "pair_log_ratio": ratio,
                        "baseline_guest_observation_sha256": pair_result["baseline"]["guest_observation_sha256"],
                        "candidate_guest_observation_sha256": pair_result["candidate"]["guest_observation_sha256"],
                        "guest_observation_equal": (
                            pair_result["baseline"]["guest_observation_sha256"]
                            == pair_result["candidate"]["guest_observation_sha256"]
                        ),
                    }
                )
            summaries[workload["id"]] = summarize_log_effect(ratios)
            combined_values.append(ratios)
        combined = [statistics.mean(values) for values in zip(*combined_values)]
        summary = {
            "schema_id": AB_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "record_id": batch_id,
            "candidate_id": args.candidate_id,
            "artifact_type": "summary",
            "status": "pending",
            "pairs": args.pairs,
            "measured_runs": len(schedule),
            "schedule": {"ab": args.pairs // 2, "ba": args.pairs // 2},
            "calibration": calibration,
            "workloads": summaries,
            "pair_results": pair_results,
            "combined": summarize_log_effect(combined),
            "host": host_cpu(),
        }
        mismatches = [
            result for result in pair_results if result["guest_observation_equal"] is not True
        ]
        if mismatches:
            summary["status"] = "invalid"
            _write_json_once(record_root / "summary.json", summary)
            _write_json_replace(
                record_root / "decision.json",
                {
                    "schema_id": DECISION_SCHEMA_ID,
                    "schema_version": SCHEMA_VERSION,
                    "record_id": batch_id,
                    "candidate_id": args.candidate_id,
                    "decision_kind": "invalid",
                    "status": "invalid",
                    "reasons": ["guest observation projection mismatch during A/B"],
                    "statistics": summary,
                    **decision_context,
                },
            )
            _write_text_once(
                record_root / "decision.md",
                "# RP2040 CPU candidate decision\n\nBatch invalid: guest observation projection mismatch.\n",
            )
            _write_text_once(
                record_root / "hotpath-disassembly.txt",
                "P0-A1: hot-path disassembly is not collected until P0-B.\n",
            )
            _write_sha256sums_once(record_root)
            raise ValueError("guest observation projection mismatch during A/B")
        _write_json_once(record_root / "summary.json", summary)
        _write_json_replace(
            record_root / "decision.json",
            {
                "schema_id": DECISION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": batch_id,
                "candidate_id": args.candidate_id,
                "decision_kind": "performance",
                "status": "pending",
                "statistics": summary,
                "correctness": {"status": "pass", "source": "correctness/comparison.json"},
                **decision_context,
            },
        )
        _write_text_once(
            record_root / "decision.md",
            "# RP2040 CPU candidate decision\n\nPerformance A/B is pending correctness and review.\n",
        )
        _write_text_once(
            record_root / "hotpath-disassembly.txt",
            "P0-A1: hot-path disassembly is not collected until P0-B.\n",
        )
        _write_sha256sums_once(record_root)
    finally:
        _restore_cpu_affinity(before)
    return 0


def run_profile(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("profile requires exactly the two registered workloads")
    identity = clean_backend_identity(args.backend)
    if not args.runner.is_file():
        raise ValueError("runner is missing: {}".format(args.runner))
    validate_runner_embedded_commit(args.runner, identity["commit"])
    declared_features = normalize_feature_set(getattr(args, "feature_set", []))
    if "cpu-application-profiler" not in declared_features:
        raise ValueError("profile requires --feature-set cpu-application-profiler")
    provenance = validate_runner_provenance(
        args.runner, identity["commit"], declared_features,
        expected_role="candidate_profile",
    )
    identity["runner_sha256"] = sha256_file(args.runner)
    identity["feature_set"] = effective_feature_set(declared_features)
    identity["build_provenance_sha256"] = provenance["sha256"]
    identity["role"] = "candidate_profile"
    identity["provenance_role"] = provenance["role"]
    _require_admission_gate(args.admission_record, workloads)
    record_root, phase_dir = _record_root_and_phase(args.output, "profile")
    batch_id = args.batch_id or record_root.name
    _validate_batch_id(record_root, batch_id)
    _refuse_existing_files(phase_dir)
    _record_manifest(
        record_root,
        _base_manifest(
            batch_id, workloads, {"candidate_profile": identity}, candidate_id=args.candidate_id,
            cpu=args.cpu, feature_set=getattr(args, "feature_set", []),
        ),
    )
    decision_context = _manifest_decision_context(
        record_root, workloads, {"candidate_profile": identity},
        feature_set=getattr(args, "feature_set", []),
    )
    phase_dir.mkdir(parents=True, exist_ok=True)
    before = _set_cpu_affinity(args.cpu)
    try:
        for workload in workloads:
            profile_path = phase_dir / "{}-r{}.json".format(workload["id"], workload["revision"])
            _refuse_existing(profile_path)
            with tempfile.TemporaryDirectory(prefix="picocalc-rp2040-profile-") as temporary:
                raw_profile_path = Path(temporary) / "profile.json"
                result = run_guest(
                    workload, args.backend, args.runner,
                    cpu_application_profile=raw_profile_path,
                    expected_backend_identity=identity,
                )
                profile = _read_json(raw_profile_path)
            if not isinstance(profile, dict):
                raise ValueError("CPU profile is not an object: {}".format(profile_path))
            profile_features = profile.get("feature_set")
            expected_profile_features = effective_feature_set(declared_features)
            if not isinstance(profile_features, list) or normalize_feature_set(profile_features) != expected_profile_features:
                raise ValueError(
                    "CPU profile feature_set does not match the verified runner for {}".format(
                        workload["id"]
                    )
                )
            normalized_profile = {
                "schema_id": PROFILE_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": batch_id,
                "candidate_id": args.candidate_id,
                "workload": {
                    "id": workload["id"],
                    "revision": workload["revision"],
                    "firmware_sha256": workload["firmware_sha256"],
                    "scenario_sha256": workload["scenario_sha256"],
                },
                "backend": {"commit": identity["commit"], "dirty": False},
                "runner": {
                    "sha256": identity["runner_sha256"],
                    "build_provenance_sha256": identity["build_provenance_sha256"],
                },
                "cpu": host_cpu(),
                "interval": profile.get(
                    "interval",
                    {"start_emulated_cycle": 0, "end_emulated_cycle": result["measurement"]["cycles"]},
                ),
                "cores": profile.get("cores", []),
                "overflowed": bool(profile.get("overflowed", False)),
                "profile_valid": bool(profile.get("profile_valid", False)),
                "counters": profile.get("counters", {}),
                "invariants": profile.get("invariants", {"valid": False}),
                "feature_set": normalize_feature_set(profile_features),
                "raw_profile": profile,
            }
            if normalized_profile["overflowed"] is not False:
                raise ValueError("CPU profile counter overflowed for {}".format(workload["id"]))
            if normalized_profile["profile_valid"] is not True:
                raise ValueError("CPU profile is invalid for {}".format(workload["id"]))
            if (
                not isinstance(normalized_profile["invariants"], Mapping)
                or normalized_profile["invariants"].get("valid") is not True
            ):
                raise ValueError("CPU profile invariants are invalid for {}".format(workload["id"]))
            if not isinstance(normalized_profile["cores"], list) or not normalized_profile["cores"]:
                raise ValueError("CPU profile has no core records for {}".format(workload["id"]))
            if not isinstance(normalized_profile["counters"], Mapping):
                raise ValueError("CPU profile counters are invalid for {}".format(workload["id"]))
            _write_json_once(profile_path, normalized_profile)
            _write_json_once(phase_dir / "{}-measurement.json".format(workload["id"]), result["measurement"])
    finally:
        _restore_cpu_affinity(before)
    _write_json_replace(
        record_root / "decision.json",
        {
            "schema_id": DECISION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "record_id": batch_id,
            "candidate_id": args.candidate_id,
            "decision_kind": "profile",
            "status": "pass",
            "correctness": {"status": "not_run", "profile": "written"},
            **decision_context,
        },
    )
    _write_sha256sums_once(record_root)
    return 0


def run_summarize(args: argparse.Namespace) -> int:
    record = args.record.resolve()
    _validate_record_root(record)
    checksum_path = record / "SHA256SUMS"
    if not checksum_path.is_file():
        raise ValueError("summarize requires an existing SHA256SUMS: {}".format(record))
    _verify_existing_sha256sums(record)
    manifest_path = record / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("record manifest is missing: {}".format(manifest_path))
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("record_id") != record.name:
        raise ValueError("record manifest does not identify {}".format(record))
    manifest_workloads = manifest.get("workloads")
    if not isinstance(manifest_workloads, list) or len(manifest_workloads) != 2:
        raise ValueError("summarize requires exactly two manifest workloads")
    expected_workloads = [workload.get("id") for workload in manifest_workloads]
    if (
        any(not isinstance(workload_id, str) or not workload_id for workload_id in expected_workloads)
        or set(expected_workloads) != REQUIRED_WORKLOAD_IDS
    ):
        raise ValueError("record manifest workload IDs are not the fixed workload pair")
    existing_summary_path = record / "summary.json"
    existing_summary = _read_json(existing_summary_path) if existing_summary_path.is_file() else None
    if existing_summary is not None:
        summary_is_invalid = isinstance(existing_summary, dict) and existing_summary.get("status") == "invalid"
        if (
            not isinstance(existing_summary, dict)
            or existing_summary.get("schema_id") != AB_SCHEMA_ID
            or existing_summary.get("schema_version") != SCHEMA_VERSION
            or existing_summary.get("artifact_type") != "summary"
            or existing_summary.get("record_id") != record.name
            or existing_summary.get("pairs") != 10
            or existing_summary.get("measured_runs") != 40
            or not isinstance(existing_summary.get("workloads"), dict)
            or not isinstance(existing_summary.get("pair_results"), list)
            or (
                not summary_is_invalid
                and (
                    set(existing_summary.get("workloads", {})) != set(expected_workloads)
                    or len(existing_summary.get("pair_results", [])) != 20
                )
            )
            or (
                summary_is_invalid
                and (
                    len(existing_summary.get("pair_results", [])) not in {0, 20}
                    or (
                        len(existing_summary.get("pair_results", [])) == 0
                        and existing_summary.get("workloads") != {}
                    )
                )
            )
        ):
            raise ValueError("existing summary is not an RP2040 CPU A/B summary")
        summary = existing_summary
        if args.output is not None:
            _write_json_once(args.output, summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    runs = []
    seen_run_ids = set()
    for path in sorted((record / "ab").glob("run-*.json")):
        item = _read_json(path)
        if not isinstance(item, dict):
            raise ValueError("AB run is not an object: {}".format(path))
        if (
            item.get("schema_id") != AB_SCHEMA_ID
            or item.get("schema_version") != SCHEMA_VERSION
            or item.get("artifact_type") != "run"
            or item.get("record_id") != record.name
        ):
            raise ValueError("AB run identity is invalid: {}".format(path))
        run_id = item.get("run_id")
        if not isinstance(run_id, str) or run_id in seen_run_ids:
            raise ValueError("AB run ID is missing or duplicated: {}".format(path))
        seen_run_ids.add(run_id)
        runs.append(item)
    if len(runs) != 40:
        raise ValueError("summarize requires exactly 40 AB run artifacts, got {}".format(len(runs)))
    expected_schedule = {
        item["run_id"]: item
        for item in make_ab_schedule(expected_workloads, pairs=10)
    }
    if {item.get("run_id") for item in runs} != set(expected_schedule):
        raise ValueError("AB run IDs do not match the fixed 40-run schedule")
    grouped: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for item in runs:
        expected = expected_schedule.get(item.get("run_id"))
        if expected is None or any(
            item.get(field) != expected[field]
            for field in ("pair", "order", "workload", "role")
        ):
            raise ValueError("AB run does not match the fixed schedule: {}".format(item.get("run_id")))
        if item.get("workload") not in expected_workloads:
            raise ValueError("AB run workload is not in the manifest: {}".format(item.get("workload")))
        if item.get("role") not in {"baseline", "candidate"}:
            raise ValueError("AB run role is invalid: {}".format(item.get("run_id")))
        if item.get("order") not in {"AB", "BA"}:
            raise ValueError("AB run order is invalid: {}".format(item.get("run_id")))
        if type(item.get("pair")) is not int or not 1 <= item["pair"] <= 10:
            raise ValueError("AB run pair is invalid: {}".format(item.get("run_id")))
        pair_values = grouped.setdefault(item["workload"], {}).setdefault(int(item["pair"]), {})
        if item["role"] in pair_values:
            raise ValueError(
                "AB pair has duplicate {} role: {} pair {}".format(
                    item["role"], item["workload"], item["pair"]
                )
            )
        pair_values[item["role"]] = item
    if set(grouped) != set(expected_workloads):
        raise ValueError("AB runs do not cover both manifest workloads")
    summaries = {}
    all_ratios: Dict[int, List[float]] = {}
    pair_results: List[Dict[str, Any]] = []
    for workload, pairs in grouped.items():
        if set(pairs) != set(range(1, 11)):
            raise ValueError("AB runs do not cover all 10 pairs for {}".format(workload))
        ratios = []
        for pair, values in sorted(pairs.items()):
            if set(values) != {"baseline", "candidate"}:
                raise ValueError("AB pair lacks baseline/candidate for {} pair {}".format(workload, pair))
            ratio = log_ratio(
                values["candidate"]["emulated_cycles_per_wall_second"],
                values["baseline"]["emulated_cycles_per_wall_second"],
            )
            ratios.append(ratio)
            all_ratios.setdefault(pair, []).append(ratio)
            pair_results.append(
                {
                    "workload": workload,
                    "pair_index": pair,
                    "order": values["baseline"]["order"],
                    "run_ids": [values["baseline"]["run_id"], values["candidate"]["run_id"]],
                    "pair_log_ratio": ratio,
                    "baseline_guest_observation_sha256": values["baseline"].get("guest_observation_sha256"),
                    "candidate_guest_observation_sha256": values["candidate"].get("guest_observation_sha256"),
                    "guest_observation_equal": (
                        values["baseline"].get("guest_observation_sha256")
                        == values["candidate"].get("guest_observation_sha256")
                    ),
                }
            )
        summaries[workload] = summarize_log_effect(ratios)
    combined = [statistics.mean(all_ratios[pair]) for pair in sorted(all_ratios)]
    summary = {
        "schema_id": AB_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "record_id": record.name,
        "candidate_id": manifest.get("candidate_id", "unknown"),
        "artifact_type": "summary",
        "status": "pending",
        "pairs": 10,
        "measured_runs": len(runs),
        "schedule": {
            "ab": sum(1 for item in runs if item.get("order") == "AB") // 2,
            "ba": sum(1 for item in runs if item.get("order") == "BA") // 2,
        },
        "calibration": {"status": "not_available", "source": "summarize"},
        "workloads": summaries,
        "pair_results": pair_results,
        "combined": summarize_log_effect(combined),
    }
    _write_json_once(existing_summary_path, summary)
    _write_sha256sums_once(record)
    if args.output is not None:
        _write_json_once(args.output, summary)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _add_workloads(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", action="append", default=[], help="registered target ID (repeat in workload order)")
    parser.add_argument("--firmware", action="append", type=Path, default=[], help="firmware path paired with --target")
    parser.add_argument("--cpu", type=int)
    parser.add_argument(
        "--feature-set", action="append", default=[],
        help="compiled candidate feature (repeatable, recorded in manifest)",
    )


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    admit = subparsers.add_parser("admit")
    _add_workloads(admit)
    admit.add_argument("--backend", type=Path, required=True)
    admit.add_argument("--runner", type=Path, required=True)
    admit.add_argument("--batch-id")
    admit.add_argument("--output", type=Path, required=True)
    admit.set_defaults(handler=run_admission)

    correctness = subparsers.add_parser("correctness")
    _add_workloads(correctness)
    correctness.add_argument("--baseline-backend", type=Path, required=True)
    correctness.add_argument("--candidate-backend", type=Path, required=True)
    correctness.add_argument("--baseline-runner", type=Path, required=True)
    correctness.add_argument("--candidate-runner", type=Path, required=True)
    correctness.add_argument("--baseline-trace-runner", type=Path)
    correctness.add_argument("--candidate-trace-runner", type=Path)
    correctness.add_argument("--final-report-only", action="store_true")
    correctness.add_argument("--candidate-id", default="candidate")
    correctness.add_argument("--admission-record", type=Path, required=True)
    correctness.add_argument("--batch-id")
    correctness.add_argument("--output", type=Path, required=True)
    correctness.set_defaults(handler=run_correctness)

    profile = subparsers.add_parser("profile")
    _add_workloads(profile)
    profile.add_argument("--backend", type=Path, required=True)
    profile.add_argument("--runner", type=Path, required=True)
    profile.add_argument("--candidate-id", default="candidate")
    profile.add_argument("--admission-record", type=Path, required=True)
    profile.add_argument("--batch-id")
    profile.add_argument("--output", type=Path, required=True)
    profile.set_defaults(handler=run_profile)

    ab = subparsers.add_parser("ab")
    _add_workloads(ab)
    ab.add_argument("--baseline-backend", type=Path, required=True)
    ab.add_argument("--candidate-backend", type=Path, required=True)
    ab.add_argument("--baseline-runner", type=Path, required=True)
    ab.add_argument("--candidate-runner", type=Path, required=True)
    ab.add_argument("--pairs", type=int, default=10)
    ab.add_argument("--warmup", type=int, default=1)
    ab.add_argument("--calibration-runs", type=int, default=3)
    ab.add_argument("--candidate-id", default="candidate")
    ab.add_argument(
        "--final-report-only", action="store_true",
        help="P0-A2 only: use final report correctness without behavior traces",
    )
    ab.add_argument("--admission-record", type=Path, required=True)
    ab.add_argument("--batch-id", required=True)
    ab.add_argument("--output", type=Path, required=True)
    ab.set_defaults(handler=run_ab)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--record", type=Path, required=True)
    summarize.add_argument("--output", type=Path)
    summarize.set_defaults(handler=run_summarize)

    provenance = subparsers.add_parser(
        "provenance",
        help="write the runner-adjacent Cargo build provenance sidecar",
    )
    provenance.add_argument("--backend", type=Path, required=True)
    provenance.add_argument("--runner", type=Path, required=True)
    provenance.add_argument(
        "--role",
        choices=(
            "baseline_production", "candidate_production", "baseline_trace",
            "candidate_trace", "candidate_profile", "production",
        ),
        required=True,
    )
    provenance.add_argument("--feature-set", action="append", default=[])
    provenance.add_argument("--lockfile", type=Path, required=True)
    provenance.add_argument("--cargo-tree", type=Path, required=True)
    provenance.add_argument("--cargo-argv", action="append", default=[])
    provenance.add_argument("--rustc-version", required=True)
    provenance.add_argument("--cargo-version", required=True)
    provenance.add_argument("--output", type=Path)
    provenance.set_defaults(handler=write_runner_provenance)

    args = parser.parse_args(argv)
    if args.command == "ab":
        if args.pairs != 10:
            parser.error("--pairs is fixed at 10 (5 AB + 5 BA)")
        if args.warmup != 1:
            parser.error("--warmup is fixed at 1")
        if args.calibration_runs != 3:
            parser.error("--calibration-runs is fixed at 3")
        if args.cpu is None:
            parser.error("ab requires --cpu for affinity pinning")
        if args.final_report_only and args.candidate_id != "P0-A2":
            parser.error("--final-report-only is reserved for candidate_id P0-A2")
    if args.command == "correctness" and args.final_report_only and args.candidate_id != "P0-A2":
        parser.error("--final-report-only is reserved for candidate_id P0-A2")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    return args.handler(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as error:
        print("benchmark failed: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
