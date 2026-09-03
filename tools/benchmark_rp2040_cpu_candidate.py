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
HOST_STABILITY_SCHEMA_ID = "picocalc.rp2040-cpu-host-stability"
SHORT_BLOCK_SCHEMA_ID = "picocalc.rp2040-cpu-short-block"
RECORD_TYPE = "picocalc.rp2040-cpu-record"
SCHEMA_VERSION = 1
HOST_STABILITY_WARMUP_RUNS = 2
HOST_STABILITY_MEASURED_RUNS = 10
HOST_STABILITY_ADJACENT_LOG_LIMIT = 0.02
HOST_STABILITY_MAD_LIMIT = 0.02
HOST_STABILITY_V2_MEASURED_RUNS = 12
HOST_STABILITY_V2_GROUP_SIZE = 3
HOST_STABILITY_V2_GROUP_COUNT = HOST_STABILITY_V2_MEASURED_RUNS // HOST_STABILITY_V2_GROUP_SIZE
HOST_STABILITY_V2_GROUP_ADJACENT_LOG_LIMIT = 0.02
CPU_TIME_DIAGNOSTIC_WARMUP_RUNS = 1
CPU_TIME_DIAGNOSTIC_MEASURED_RUNS = 4
P1B_FILTERABLE_COMBINED_MIN_RATIO = 0.01
LOAD_SHAPE_INSTANCE_COUNTS = (1, 2, 4, 8)
LOAD_SHAPE_DEFAULT_CYCLES = 10_000_000
AFFINITY_PILOT_MODES = ("pinned-vcpu", "inherited-set")
AFFINITY_PILOT_REPLICATES = 3
COOLDOWN_PILOT_VALUES = (0.0, 5.0, 15.0, 60.0)
COOLDOWN_PILOT_REPLICATES = 3
COOLDOWN_PILOT_CPU_RELATIVE_MAD_LIMIT = 0.02
COOLDOWN_PILOT_CPU_WALL_RATIO_LIMIT = 0.02
SHORT_BLOCK_COUNT = 5
SHORT_BLOCK_PAIRS = 2
SHORT_BLOCK_ANCHOR_REPLICATES = 3
SHORT_BLOCK_DEFAULT_CYCLES = 10_000_000
SHORT_BLOCK_COOLDOWN_SECONDS = 0.0
SHORT_BLOCK_ANCHOR_MAD_LIMIT = 0.02
SHORT_BLOCK_ANCHOR_DRIFT_LIMIT = 0.02
AB_PRIMARY_METRICS = ("cpu-time", "wall-time")
REQUIRED_WORKLOAD_IDS = frozenset(("picotetris-opt1b-vrp5", "picoedit-r1-vrp2f"))
# The first null batch exposed a long-session host throughput drift.  Keep the
# recovery interval fixed and part of the record identity so it cannot be
# tuned after looking at a result.
AB_INTER_RUN_COOLDOWN_SECONDS = 60.0
CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1 = "interleaved-anchor-v1"
CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2 = "interleaved-anchor-v2"
CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3 = "interleaved-anchor-v3"
CALIBRATION_ANCHOR_RESIDUAL_LIMIT = 0.02
INTERLEAVED_ANCHOR_AFTER_RUNS = (10, 20, 30)
INTERLEAVED_ANCHOR_V2_REPLICATES = 3
INTERLEAVED_ANCHOR_V3_AFTER_RUNS = (5, 10, 15, 20, 25, 30, 35)
INTERLEAVED_ANCHOR_V3_REPLICATES = 3
CALIBRATION_ANCHOR_GROUP_MAD_LIMIT = 0.02
CALIBRATION_ANCHOR_LOCAL_RESIDUAL_LIMIT = 0.02
CALIBRATION_PAIR_SENSITIVITY_LIMIT = 0.02
# P0-A2 uses the same production executable for A and B.  These thresholds
# are fixed before looking at a batch: the raw pair effect is primary, while
# the host-corrected effect is retained as a sensitivity check.
NULL_CONTROL_COMBINED_MAX_ABS_EFFECT = 0.01
NULL_CONTROL_WORKLOAD_MAX_ABS_EFFECT = 0.02
# Cargo features accepted by the measurement contract.  The allow-list also
# includes planned CPU-candidate features so the runner can be prepared before
# the corresponding backend implementation lands.
KNOWN_FEATURES = frozenset(
    {
        "behavior-trace",
        "compact-dispatch-key-prototype",
        "cpu-application-profiler",
        "decode-invalidation-tag-guard",
        "dynamic-quantum-prototype",
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
# ``picocalc-harness`` enables both features by default on the current clean
# baseline. Every build provenance record therefore carries this effective
# Cargo set, not merely the candidate-specific additions supplied on the CLI.
# Historical records retain their original identities and are not rewritten.
DEFAULT_EFFECTIVE_FEATURES = (
    "decode-invalidation-tag-guard",
    "sd-gen1-multiblock",
)
DYNAMIC_QUANTUM_FEATURE = "dynamic-quantum-prototype"
DYNAMIC_QUANTUM_MAX = 16
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
    if {
        "threading",
        "executable-sram-invalidation-filter",
    }.issubset(values):
        raise ValueError(
            "executable-sram-invalidation-filter is Serial-only and cannot be combined with threading"
        )
    return sorted(values)


def effective_feature_set(features: Sequence[str]) -> List[str]:
    """Return the sorted Cargo feature set actually expected in a build."""
    requested = normalize_feature_set(features)
    return sorted(set(DEFAULT_EFFECTIVE_FEATURES).union(requested))


def runner_step_quantum(target: Mapping[str, Any], feature_set: Sequence[str] = ()) -> int:
    """Resolve the configured runner quantum for a normal or Q1 candidate.

    Registered targets retain their historical q1 contract. The experimental
    dynamic-quantum candidate is the one explicit exception: it uses the
    registered PSRAM target with a q16 maximum and falls back to q1 whenever
    the backend policy says that the device is engaged or a transition is
    possible.
    """
    contract = target["runner"]
    registered_quantum = int(contract["quantum"])
    requested = normalize_feature_set(feature_set)
    if DYNAMIC_QUANTUM_FEATURE not in requested:
        return registered_quantum
    if contract.get("psram") is not True:
        raise ValueError(
            "dynamic-quantum-prototype is restricted to a PSRAM workload"
        )
    if registered_quantum != 1:
        raise ValueError(
            "dynamic-quantum-prototype requires the registered q1 PSRAM contract"
        )
    return DYNAMIC_QUANTUM_MAX


def validate_profile_feature_set(candidate_id: str, features: Sequence[str]) -> List[str]:
    """Validate profile instrumentation required by the candidate phase."""
    declared = normalize_feature_set(features)
    required = ["cpu-application-profiler"]
    if candidate_id == "P1-B":
        required.append("executable-sram-invalidation-filter")
    if candidate_id == "P2-A":
        required.append("pending-exception-fast-reject")
    missing = [feature for feature in required if feature not in declared]
    if missing:
        raise ValueError(
            "profile candidate {} requires --feature-set {}".format(
                candidate_id, ",".join(missing)
            )
        )
    return declared


def validate_pending_exception_profile(profile: Mapping[str, Any]) -> None:
    """Validate P2-A aggregate/core exception counter conservation."""
    counters = profile.get("counters")
    scopes: List[Tuple[str, Any]] = [("aggregate", counters)]
    cores = profile.get("cores")
    if not isinstance(cores, list):
        raise ValueError("P2-A profile cores are invalid")
    scopes.extend(("core-{}".format(index), core) for index, core in enumerate(cores))
    for scope, source in scopes:
        exception = source.get("exception") if isinstance(source, Mapping) else None
        if not isinstance(exception, Mapping):
            raise ValueError("P2-A profile {} exception counters are missing".format(scope))
        values: Dict[str, int] = {}
        for field in ("polls", "reject_no_candidate", "reject_primask", "reject_active_handler", "entries"):
            value = exception.get(field)
            if type(value) is not int or value < 0:
                raise ValueError("P2-A profile {} exception {} is invalid".format(scope, field))
            values[field] = value
        exception_source = exception.get("source")
        if not isinstance(exception_source, Mapping):
            raise ValueError("P2-A profile {} exception source is missing".format(scope))
        source_values: Dict[str, int] = {}
        for field in ("pendsv", "systick", "nvic"):
            value = exception_source.get(field)
            if type(value) is not int or value < 0:
                raise ValueError("P2-A profile {} exception source {} is invalid".format(scope, field))
            source_values[field] = value
        if values["polls"] != sum(
            values[field]
            for field in ("reject_no_candidate", "reject_primask", "reject_active_handler", "entries")
        ):
            raise ValueError("P2-A profile {} exception poll conservation is invalid".format(scope))
        if values["entries"] != sum(source_values.values()):
            raise ValueError("P2-A profile {} exception source conservation is invalid".format(scope))
    invariants = profile.get("invariants")
    if (
        not isinstance(invariants, Mapping)
        or invariants.get("exception_poll_conservation") is not True
        or invariants.get("exception_source_conservation") is not True
    ):
        raise ValueError("P2-A profile exception invariants are invalid")


def validate_executable_sram_filter_profile(profile: Mapping[str, Any]) -> None:
    """Validate P1-B SRAM-write denominator and skipped-write counters.

    ``invalidation.requests`` retains its historical meaning (requests that
    actually entered the decode-invalidation queue), so it is intentionally
    not used as the denominator here.  Both aggregate and per-core records
    must expose the explicit P1-B counters and satisfy the conservation
    inequality before a production A/B can start.
    """
    counters = profile.get("counters")
    scopes: List[Tuple[str, Any]] = [("aggregate", counters)]
    cores = profile.get("cores")
    if not isinstance(cores, list):
        raise ValueError("P1-B profile cores are invalid")
    scopes.extend(("core-{}".format(index), core) for index, core in enumerate(cores))
    for scope, source in scopes:
        invalidation = source.get("invalidation") if isinstance(source, Mapping) else None
        if not isinstance(invalidation, Mapping):
            raise ValueError("P1-B profile {} invalidation counters are missing".format(scope))
        values: Dict[str, int] = {}
        for field in ("sram_write_requests", "non_executable_sram_write_requests"):
            value = invalidation.get(field)
            if type(value) is not int or value < 0:
                raise ValueError("P1-B profile {} {} is invalid".format(scope, field))
            values[field] = value
        if values["non_executable_sram_write_requests"] > values["sram_write_requests"]:
            raise ValueError("P1-B profile {} skipped writes exceed SRAM writes".format(scope))
    invariants = profile.get("invariants")
    if not isinstance(invariants, Mapping) or invariants.get("valid") is not True:
        raise ValueError("P1-B profile invariants are invalid")


def summarize_executable_sram_filter_profiles(
    profiles: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Compute the fixed P1-B workload and equal-weight filterability gate."""
    workload_rows: List[Dict[str, Any]] = []
    for profile in profiles:
        workload = profile.get("workload")
        workload_id = workload.get("id") if isinstance(workload, Mapping) else None
        counters = profile.get("counters")
        invalidation = counters.get("invalidation") if isinstance(counters, Mapping) else None
        total = invalidation.get("sram_write_requests") if isinstance(invalidation, Mapping) else None
        skipped = (
            invalidation.get("non_executable_sram_write_requests")
            if isinstance(invalidation, Mapping)
            else None
        )
        if (
            not isinstance(workload_id, str)
            or type(total) is not int
            or total <= 0
            or type(skipped) is not int
            or skipped < 0
            or skipped > total
        ):
            raise ValueError("P1-B profile filterability counters are invalid")
        workload_rows.append(
            {
                "workload": workload_id,
                "sram_write_requests": total,
                "non_executable_sram_write_requests": skipped,
                "filterable_request_rate": skipped / total,
            }
        )
    if not workload_rows:
        raise ValueError("P1-B profile has no workload counter rows")
    workload_rows.sort(key=lambda row: row["workload"])
    combined_ratio = statistics.mean(
        float(row["filterable_request_rate"]) for row in workload_rows
    )
    return {
        "method": "p1b-filterable-sram-write-rate-v1",
        "threshold": P1B_FILTERABLE_COMBINED_MIN_RATIO,
        "workloads": workload_rows,
        "combined_ratio": combined_ratio,
        "pass": len(workload_rows) == 2 and combined_ratio >= P1B_FILTERABLE_COMBINED_MIN_RATIO,
    }


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
    """Remove backend and host-scheduler metadata from guest observations.

    ``step_quantum`` is a runner configuration scalar, while
    ``psram.tick_count`` counts host calls to the PSRAM model. Neither is a
    guest-visible result, and the dynamic candidate is expected to change
    both. The exclusions are fixed by PERF-Q2 before candidate measurements;
    all other report fields remain part of the comparison.
    """
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
    projection.pop("step_quantum", None)
    psram = projection.get("psram")
    if isinstance(psram, Mapping):
        normalized_psram = dict(psram)
        normalized_psram.pop("tick_count", None)
        projection["psram"] = normalized_psram
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


def _read_cpu_pressure() -> Optional[Dict[str, Dict[str, float]]]:
    try:
        lines = Path("/proc/pressure/cpu").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    pressure: Dict[str, Dict[str, float]] = {}
    try:
        for line in lines:
            label, values = line.split(" ", 1)
            parsed: Dict[str, float] = {}
            for item in values.split():
                key, value = item.split("=", 1)
                parsed[key] = float(value)
            pressure[label] = parsed
    except (ValueError, TypeError):
        return None
    return pressure or None


def _read_proc_cpu_stat() -> Optional[Dict[str, int]]:
    try:
        lines = Path("/proc/stat").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    names = (
        "user", "nice", "system", "idle", "iowait", "irq", "softirq",
        "steal", "guest", "guest_nice",
    )
    try:
        line = next(line for line in lines if line.startswith("cpu "))
        values = [int(value) for value in line.split()[1 : 1 + len(names)]]
    except (StopIteration, ValueError):
        return None
    if len(values) != len(names) or any(value < 0 for value in values):
        return None
    return dict(zip(names, values))


def _read_cgroup_cpu_stat() -> Optional[Dict[str, int]]:
    try:
        lines = Path("/sys/fs/cgroup/cpu.stat").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    try:
        values = {}
        for line in lines:
            key, value = line.split()
            values[key] = int(value)
    except (ValueError, TypeError):
        return None
    return values or None


def _read_scheduler_state() -> Optional[Dict[str, int]]:
    try:
        return {
            "policy": int(os.sched_getscheduler(0)),
            "priority": int(os.sched_getparam(0).sched_priority),
            "nice": int(os.getpriority(os.PRIO_PROCESS, 0)),
        }
    except (AttributeError, OSError, PermissionError, ValueError):
        return None


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
    try:
        loadavg: Optional[List[float]] = list(os.getloadavg())
    except (AttributeError, OSError):
        loadavg = None
    try:
        allowed_cpus: Optional[List[int]] = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        allowed_cpus = None
    return {
        "model": model,
        "logical_cpus": os.cpu_count(),
        "reported_mhz": statistics.median(frequencies) if frequencies else None,
        "loadavg": loadavg,
        "allowed_cpus": allowed_cpus,
        "platform": platform.platform(),
        "kernel": platform.release(),
        "cpu_pressure": _read_cpu_pressure(),
        "proc_cpu_stat": _read_proc_cpu_stat(),
        "cgroup_cpu_stat": _read_cgroup_cpu_stat(),
        "scheduler": _read_scheduler_state(),
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
    feature_set: Sequence[str] = (),
    behavior_trace: Optional[Path] = None,
    cpu_application_profile: Optional[Path] = None,
    host_timing: Optional[Path] = None,
) -> List[str]:
    """Build a target command and require an explicit backend identity override."""
    if not backend_commit:
        raise ValueError(
            "backend_commit override is required; never use the registry accepted pin"
        )
    contract = target["runner"]
    quantum = runner_step_quantum(target, feature_set)
    command = [
        str(runner),
        "--bin", str(firmware),
        "--board", contract["board"],
        "--lcd-variant", contract["lcd_variant"],
        "--quantum", str(quantum),
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
    if host_timing is not None:
        command.extend(["--host-timing", str(host_timing)])
    return command


def load_shape_command(
    target: Mapping[str, Any],
    firmware: Path,
    runner: Path,
    report: Path,
    uart: Path,
    host_timing: Path,
    cycles: int,
    *,
    backend_commit: Optional[str],
) -> List[str]:
    """Build a short cycle-limit command for independent guest scaling.

    This deliberately omits the registered scenario and acceptance markers:
    the load-shape probe measures host occupancy, not a workload verdict. The
    same registered firmware/device contract is retained, while the cycle
    limit is shortened and made the explicit successful stop.
    """
    if not backend_commit:
        raise ValueError("backend_commit override is required; never use the registry accepted pin")
    if type(cycles) is not int or cycles <= 0:
        raise ValueError("load-shape cycles must be a positive integer")
    contract = target["runner"]
    command = [
        str(runner),
        "--bin", str(firmware),
        "--board", contract["board"],
        "--lcd-variant", contract["lcd_variant"],
        "--quantum", str(contract["quantum"]),
        "--cycles", str(cycles),
        "--json", str(report),
        "--uart", str(uart),
        "--host-timing", str(host_timing),
        "--backend-commit", backend_commit,
        "--expect-stop", "cycle_limit",
    ]
    if contract.get("psram", False):
        command.append("--psram")
    if contract.get("keyboard", False):
        command.append("--keyboard")
    sd = contract["sd"]
    if sd["attached"]:
        command.extend(["--sd", "--sd-format", sd["format"]])
    bootrom = contract.get("bootrom") or target.get("bootrom")
    if bootrom:
        bootrom_path = bootrom.get("path") if isinstance(bootrom, Mapping) else bootrom
        if bootrom_path:
            command.extend(["--bootrom", str(ROOT / bootrom_path)])
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
    workload: Mapping[str, Any], report: Mapping[str, Any], backend_commit: str,
    feature_set: Sequence[str] = (),
) -> None:
    """Validate report acceptance while allowing backend identity to differ."""
    target = workload["target"]
    required = [
        {"path": "schema_version", "op": "eq", "value": 8},
        {"path": "verdict.status", "op": "eq", "value": "pass"},
        {"path": "backend_build.commit", "op": "eq", "value": backend_commit},
        {"path": "backend_build.dirty", "op": "eq", "value": False},
        {"path": "firmware.sha256", "op": "eq", "value": workload["firmware_sha256"]},
        {"path": "step_quantum", "op": "eq", "value": runner_step_quantum(target, feature_set)},
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
        "comparison_projection": guest_observation_projection(projection),
        "domain_summary": domain_summary,
    }


def validate_behavior_pair(
    baseline_artifact: Mapping[str, Any], candidate_artifact: Mapping[str, Any],
    baseline_backend_commit: Optional[str] = None,
    candidate_backend_commit: Optional[str] = None,
) -> None:
    left = behavior_summary(baseline_artifact, baseline_backend_commit)
    right = behavior_summary(candidate_artifact, candidate_backend_commit)
    if left["comparison_projection"] != right["comparison_projection"]:
        raise ValueError("behavior projection mismatch")
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


def make_short_block_schedule(
    workload_ids: Sequence[str],
    pairs: int = SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS,
) -> List[Dict[str, Any]]:
    """Partition the fixed A/B schedule into five independently observable blocks."""
    if pairs != SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS:
        raise ValueError(
            "short block schedule fixes pairs at {}".format(
                SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS
            )
        )
    schedule = make_ab_schedule(workload_ids, pairs)
    blocks: List[Dict[str, Any]] = []
    for block_index in range(SHORT_BLOCK_COUNT):
        first_pair = block_index * SHORT_BLOCK_PAIRS + 1
        last_pair = first_pair + SHORT_BLOCK_PAIRS - 1
        items = [
            dict(item, block_index=block_index + 1)
            for item in schedule
            if first_pair <= item["pair"] <= last_pair
        ]
        blocks.append(
            {
                "block_index": block_index + 1,
                "block_id": "block-{:02d}".format(block_index + 1),
                "pair_indices": list(range(first_pair, last_pair + 1)),
                "pre_anchor_ids": [
                    "block-{:02d}-anchor-pre-{:03d}".format(
                        block_index + 1, replicate
                    )
                    for replicate in range(1, SHORT_BLOCK_ANCHOR_REPLICATES + 1)
                ],
                "post_anchor_ids": [
                    "block-{:02d}-anchor-post-{:03d}".format(
                        block_index + 1, replicate
                    )
                    for replicate in range(1, SHORT_BLOCK_ANCHOR_REPLICATES + 1)
                ],
                "runs": items,
            }
        )
    if sum(len(block["runs"]) for block in blocks) != len(schedule):
        raise ValueError("short block schedule does not cover the A/B schedule")
    return blocks


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


def interleaved_anchor_measurement_policy() -> Dict[str, Any]:
    """Return the immutable policy fields for the revised null-control."""
    return {
        "inter_run_cooldown_seconds": AB_INTER_RUN_COOLDOWN_SECONDS,
        "calibration_method": CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1,
        "anchor_layout": {
            "pre_count": 3,
            "after_measured_runs": list(INTERLEAVED_ANCHOR_AFTER_RUNS),
            "post_count": 3,
        },
        "anchor_run_ids": [
            "anchor-pre-{:03d}".format(index) for index in range(1, 4)
        ] + [
            "anchor-after-{:03d}".format(index) for index in INTERLEAVED_ANCHOR_AFTER_RUNS
        ] + [
            "anchor-post-{:03d}".format(index) for index in range(1, 4)
        ],
        "correction_method": "piecewise-linear-interpolation-of-log-baseline-anchor-throughput-v1",
        "anchor_residual_threshold": CALIBRATION_ANCHOR_RESIDUAL_LIMIT,
        "pair_level_sensitivity_method": "raw-vs-host-corrected-log-ratio-v1",
    }


def interleaved_anchor_measurement_policy_v2() -> Dict[str, Any]:
    """Return the fixed replicated-anchor policy for long-session stability.

    Each of the five calibration boundaries is measured three times.  The
    median log-throughput at each boundary is used for interpolation; the
    fixed scaled-MAD dispersion gate is recorded alongside the model gate.
    """
    anchor_run_ids = []
    for prefix in ("pre", "after-010", "after-020", "after-030", "post"):
        anchor_run_ids.extend(
            "anchor-{}-{:03d}".format(prefix, index)
            for index in range(1, INTERLEAVED_ANCHOR_V2_REPLICATES + 1)
        )
    return {
        "inter_run_cooldown_seconds": AB_INTER_RUN_COOLDOWN_SECONDS,
        "calibration_method": CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2,
        "anchor_layout": {
            "pre_count": INTERLEAVED_ANCHOR_V2_REPLICATES,
            "after_measured_runs": list(INTERLEAVED_ANCHOR_AFTER_RUNS),
            "post_count": INTERLEAVED_ANCHOR_V2_REPLICATES,
            "replicates_per_group": INTERLEAVED_ANCHOR_V2_REPLICATES,
        },
        "anchor_group_ids": ["pre", "after-010", "after-020", "after-030", "post"],
        "anchor_run_ids": anchor_run_ids,
        "correction_method": "piecewise-linear-interpolation-of-log-baseline-anchor-group-median-throughput-v2",
        "anchor_aggregation_method": "median-of-replicate-log-throughput-v1",
        "anchor_residual_threshold": CALIBRATION_ANCHOR_RESIDUAL_LIMIT,
        "anchor_group_dispersion_gate_used": True,
        "anchor_group_dispersion_threshold": CALIBRATION_ANCHOR_GROUP_MAD_LIMIT,
        "pair_level_sensitivity_method": "raw-vs-host-corrected-log-ratio-v1",
    }


def interleaved_anchor_measurement_policy_v3() -> Dict[str, Any]:
    """Return the fixed high-resolution replicated-anchor policy.

    v2 exposed a non-linear host trajectory between five boundaries.  v3
    keeps every threshold unchanged, but samples the same 40-run protocol at
    nine boundaries so the correction knots follow the observed trajectory.
    The leave-one-group-out residual is deterministic and is an explicit
    anti-overfit gate rather than a post-hoc model choice.
    """
    group_ids = ["pre"] + [
        "after-{:03d}".format(after_run)
        for after_run in INTERLEAVED_ANCHOR_V3_AFTER_RUNS
    ] + ["post"]
    anchor_run_ids = []
    for group_id in group_ids:
        anchor_run_ids.extend(
            "anchor-{}-{:03d}".format(group_id, index)
            for index in range(1, INTERLEAVED_ANCHOR_V3_REPLICATES + 1)
        )
    return {
        "inter_run_cooldown_seconds": AB_INTER_RUN_COOLDOWN_SECONDS,
        "calibration_method": CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3,
        "anchor_layout": {
            "pre_count": INTERLEAVED_ANCHOR_V3_REPLICATES,
            "after_measured_runs": list(INTERLEAVED_ANCHOR_V3_AFTER_RUNS),
            "post_count": INTERLEAVED_ANCHOR_V3_REPLICATES,
            "replicates_per_group": INTERLEAVED_ANCHOR_V3_REPLICATES,
        },
        "anchor_group_ids": group_ids,
        "anchor_run_ids": anchor_run_ids,
        "correction_method": "piecewise-linear-interpolation-of-log-baseline-anchor-group-median-throughput-v3",
        "anchor_aggregation_method": "median-of-replicate-log-throughput-v1",
        "anchor_residual_threshold": CALIBRATION_ANCHOR_RESIDUAL_LIMIT,
        "anchor_local_residual_method": "leave-one-group-out-log-linear-v1",
        "anchor_local_residual_threshold": CALIBRATION_ANCHOR_LOCAL_RESIDUAL_LIMIT,
        "anchor_group_dispersion_gate_used": True,
        "anchor_group_dispersion_threshold": CALIBRATION_ANCHOR_GROUP_MAD_LIMIT,
        "pair_level_sensitivity_method": "raw-vs-host-corrected-log-ratio-v1",
        "pair_level_sensitivity_gate_used": True,
        "pair_level_sensitivity_threshold": CALIBRATION_PAIR_SENSITIVITY_LIMIT,
        "global_residual_diagnostic_only": True,
    }


def validate_calibration_method(value: str) -> str:
    if value not in (
        CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1,
        CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2,
        CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3,
    ):
        raise ValueError(
            "--calibration-method must be one of {}, {}, or {}".format(
                CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1,
                CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2,
                CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3,
            )
        )
    return value


def _anchor_elapsed_seconds(start_ns: int, end_ns: int, protocol_start_ns: int) -> float:
    if end_ns <= start_ns or protocol_start_ns > start_ns:
        raise ValueError("anchor timing coordinates are invalid")
    midpoint_ns = start_ns + (end_ns - start_ns) // 2
    elapsed = (midpoint_ns - protocol_start_ns) / 1_000_000_000.0
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("anchor elapsed coordinate is invalid")
    return elapsed


def _anchor_log_linear_model(
    anchors: Sequence[Mapping[str, Any]],
    model_name: str = "global-log-linear-v1",
) -> Dict[str, Any]:
    """Fit a global line for residual diagnostics in log-throughput space."""
    if len(anchors) < 2:
        raise ValueError("at least two calibration anchors are required")
    points: List[Tuple[float, float]] = []
    for anchor in anchors:
        elapsed = anchor.get("elapsed_seconds")
        throughput = anchor.get("throughput")
        if (
            not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not math.isfinite(float(elapsed))
            or not isinstance(throughput, (int, float))
            or isinstance(throughput, bool)
            or not math.isfinite(float(throughput))
            or float(throughput) <= 0
        ):
            raise ValueError("calibration anchor timing/throughput is invalid")
        points.append((float(elapsed), math.log(float(throughput))))
    if any(left[0] >= right[0] for left, right in zip(points, points[1:])):
        raise ValueError("calibration anchors are not strictly time ordered")
    mean_x = statistics.mean(point[0] for point in points)
    mean_y = statistics.mean(point[1] for point in points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator <= 0:
        raise ValueError("calibration anchor times are degenerate")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
    intercept = mean_y - slope * mean_x
    residuals = []
    for anchor, (x, y) in zip(anchors, points):
        predicted_log = intercept + slope * x
        residual = math.exp(abs(y - predicted_log)) - 1.0
        residuals.append(
            {
                "anchor_id": anchor.get("anchor_id"),
                "observed_log_throughput": y,
                "predicted_log_throughput": predicted_log,
                "relative_residual": residual,
            }
        )
    max_residual = max(item["relative_residual"] for item in residuals)
    rms_residual = math.sqrt(
        statistics.mean(item["relative_residual"] ** 2 for item in residuals)
    )
    return {
        "model": model_name,
        "slope": slope,
        "intercept": intercept,
        "reference_throughput": geometric_mean([math.exp(point[1]) for point in points]),
        "residuals": residuals,
        "max_relative_residual": max_residual,
        "rms_relative_residual": rms_residual,
        "valid": max_residual <= CALIBRATION_ANCHOR_RESIDUAL_LIMIT,
    }


def _aggregate_anchor_groups(
    anchors: Sequence[Mapping[str, Any]],
    group_specs: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Aggregate replicated anchors by boundary using median log throughput."""
    by_group: Dict[str, List[Mapping[str, Any]]] = {}
    for anchor in anchors:
        group_id = anchor.get("group_id")
        if not isinstance(group_id, str):
            raise ValueError("replicated calibration anchor has no group_id")
        by_group.setdefault(group_id, []).append(anchor)
    groups: List[Dict[str, Any]] = []
    for spec in group_specs:
        group_id = str(spec["group_id"])
        replicates = by_group.get(group_id, [])
        expected_count = int(spec["replicate_count"])
        if len(replicates) != expected_count:
            raise ValueError(
                "calibration anchor group {} has {} replicates, expected {}".format(
                    group_id, len(replicates), expected_count
                )
            )
        elapsed_values = [float(anchor["elapsed_seconds"]) for anchor in replicates]
        throughput_values = [float(anchor["throughput"]) for anchor in replicates]
        if any(value <= 0 or not math.isfinite(value) for value in throughput_values):
            raise ValueError("calibration anchor group throughput is invalid")
        log_values = [math.log(value) for value in throughput_values]
        median_log = _median(log_values)
        median_throughput = math.exp(median_log)
        deviations = [math.exp(abs(value - median_log)) - 1.0 for value in log_values]
        mad_log = _median([abs(value - median_log) for value in log_values])
        scaled_mad_log = 1.4826 * mad_log
        relative_mad = math.exp(scaled_mad_log) - 1.0
        groups.append(
            {
                "anchor_id": group_id,
                "group_id": group_id,
                "position": spec["position"],
                "after_measured_run": int(spec["after_measured_run"]),
                "anchor_count": expected_count,
                "anchor_ids": [anchor.get("anchor_id") for anchor in replicates],
                "elapsed_seconds": _median(elapsed_values),
                "throughput": median_throughput,
                "replicate_throughputs": throughput_values,
                "relative_deviations": deviations,
                "mad_log_throughput": mad_log,
                "scaled_mad_log_throughput": scaled_mad_log,
                "relative_mad": relative_mad,
                "dispersion_valid": relative_mad <= CALIBRATION_ANCHOR_GROUP_MAD_LIMIT,
            }
        )
    return groups


def _interleaved_anchor_v2_group_specs() -> List[Dict[str, Any]]:
    return [
        {
            "group_id": "pre",
            "position": "pre",
            "after_measured_run": 0,
            "replicate_count": INTERLEAVED_ANCHOR_V2_REPLICATES,
        },
        *[
            {
                "group_id": "after-{:03d}".format(after_run),
                "position": "after-measured-run",
                "after_measured_run": after_run,
                "replicate_count": INTERLEAVED_ANCHOR_V2_REPLICATES,
            }
            for after_run in INTERLEAVED_ANCHOR_AFTER_RUNS
        ],
        {
            "group_id": "post",
            "position": "post",
            "after_measured_run": 40,
            "replicate_count": INTERLEAVED_ANCHOR_V2_REPLICATES,
        },
    ]


def _interleaved_anchor_v3_group_specs() -> List[Dict[str, Any]]:
    return [
        {
            "group_id": "pre",
            "position": "pre",
            "after_measured_run": 0,
            "replicate_count": INTERLEAVED_ANCHOR_V3_REPLICATES,
        },
        *[
            {
                "group_id": "after-{:03d}".format(after_run),
                "position": "after-measured-run",
                "after_measured_run": after_run,
                "replicate_count": INTERLEAVED_ANCHOR_V3_REPLICATES,
            }
            for after_run in INTERLEAVED_ANCHOR_V3_AFTER_RUNS
        ],
        {
            "group_id": "post",
            "position": "post",
            "after_measured_run": 40,
            "replicate_count": INTERLEAVED_ANCHOR_V3_REPLICATES,
        },
    ]


def _anchor_piecewise_local_residual_model(
    groups: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Validate piecewise knots with a fixed leave-one-group-out check.

    Interior groups are predicted from their immediate retained neighbours in
    log-throughput space.  The first and last groups use one-sided linear
    extrapolation from the first/last two retained knots.  This is fixed by
    protocol and cannot be selected after seeing a batch result.
    """
    if len(groups) < 3:
        raise ValueError("at least three anchor groups are required")
    points: List[Tuple[str, float, float]] = []
    for group in groups:
        group_id = group.get("group_id")
        elapsed = group.get("elapsed_seconds")
        throughput = group.get("throughput")
        if (
            not isinstance(group_id, str)
            or not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not math.isfinite(float(elapsed))
            or not isinstance(throughput, (int, float))
            or isinstance(throughput, bool)
            or not math.isfinite(float(throughput))
            or float(throughput) <= 0
        ):
            raise ValueError("piecewise anchor knot is invalid")
        points.append((group_id, float(elapsed), math.log(float(throughput))))
    if any(left[1] >= right[1] for left, right in zip(points, points[1:])):
        raise ValueError("piecewise anchor knots are not strictly time ordered")
    residuals: List[Dict[str, Any]] = []
    for index, (group_id, x, observed_log) in enumerate(points):
        if index == 0:
            left = points[1]
            right = points[2]
        elif index == len(points) - 1:
            left = points[-3]
            right = points[-2]
        else:
            left = points[index - 1]
            right = points[index + 1]
        if right[1] <= left[1]:
            raise ValueError("piecewise leave-one-out knots are degenerate")
        fraction = (x - left[1]) / (right[1] - left[1])
        predicted_log = left[2] + fraction * (right[2] - left[2])
        residuals.append(
            {
                "anchor_id": group_id,
                "observed_log_throughput": observed_log,
                "predicted_log_throughput": predicted_log,
                "relative_residual": math.exp(abs(observed_log - predicted_log)) - 1.0,
                "left_knot_id": left[0],
                "right_knot_id": right[0],
            }
        )
    max_residual = max(item["relative_residual"] for item in residuals)
    rms_residual = math.sqrt(
        statistics.mean(item["relative_residual"] ** 2 for item in residuals)
    )
    global_diagnostic = _anchor_log_linear_model(
        groups, model_name="global-log-linear-v3-diagnostic"
    )
    return {
        "model": "piecewise-log-linear-v3",
        "knot_ids": [point[0] for point in points],
        "reference_throughput": geometric_mean(
            [math.exp(point[2]) for point in points]
        ),
        "local_residual_method": "leave-one-group-out-log-linear-v1",
        "local_residual_threshold": CALIBRATION_ANCHOR_LOCAL_RESIDUAL_LIMIT,
        "residuals": residuals,
        "max_relative_residual": max_residual,
        "rms_relative_residual": rms_residual,
        "valid": max_residual <= CALIBRATION_ANCHOR_LOCAL_RESIDUAL_LIMIT,
        "global_diagnostic": global_diagnostic,
    }


def interpolate_anchor_throughput(
    anchors: Sequence[Mapping[str, Any]], elapsed_seconds: float
) -> float:
    """Interpolate adjacent anchor log-throughputs at a measured-run midpoint."""
    if not math.isfinite(elapsed_seconds) or len(anchors) < 2:
        raise ValueError("invalid interpolation coordinate or anchor set")
    points = []
    for anchor in anchors:
        elapsed = anchor.get("elapsed_seconds")
        throughput = anchor.get("throughput")
        if (
            not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not isinstance(throughput, (int, float))
            or isinstance(throughput, bool)
            or float(throughput) <= 0
        ):
            raise ValueError("invalid interpolation anchor")
        points.append((float(elapsed), math.log(float(throughput))))
    if elapsed_seconds < points[0][0] or elapsed_seconds > points[-1][0]:
        raise ValueError("measured run lies outside calibration anchor range")
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if elapsed_seconds <= right_x:
            fraction = (elapsed_seconds - left_x) / (right_x - left_x)
            return math.exp(left_y + fraction * (right_y - left_y))
    return math.exp(points[-1][1])


def _pair_level_sensitivity(
    pair_results: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    deltas = [float(item["corrected_pair_log_ratio"]) - float(item["pair_log_ratio"]) for item in pair_results]
    if not deltas:
        raise ValueError("pair-level sensitivity requires pair results")
    return {
        "method": "raw-vs-host-corrected-log-ratio-v1",
        "n": len(deltas),
        "mean_delta_log_ratio": statistics.mean(deltas),
        "max_abs_delta_log_ratio": max(abs(delta) for delta in deltas),
        "raw_combined_mean_log_ratio": statistics.mean(float(item["pair_log_ratio"]) for item in pair_results),
        "corrected_combined_mean_log_ratio": statistics.mean(float(item["corrected_pair_log_ratio"]) for item in pair_results),
    }


def _ci_contains_zero(summary: Mapping[str, Any]) -> bool:
    interval = summary.get("ci95_effect")
    return (
        isinstance(interval, list)
        and len(interval) == 2
        and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in interval)
        and float(interval[0]) <= 0.0 <= float(interval[1])
    )


def evaluate_null_control(
    pair_results: Sequence[Mapping[str, Any]],
    workload_ids: Sequence[str],
) -> Dict[str, Any]:
    """Apply the pre-registered same-executable P0-A2 null-control gate."""
    if not pair_results or len(pair_results) != len(workload_ids) * 10:
        raise ValueError("null-control requires ten pairs for each workload")
    workload_effects: Dict[str, Dict[str, Dict[str, Any]]] = {}
    by_pair: Dict[int, List[Mapping[str, Any]]] = {}
    for workload_id in workload_ids:
        entries = [item for item in pair_results if item.get("workload") == workload_id]
        if len(entries) != 10:
            raise ValueError("null-control workload does not contain ten pairs: {}".format(workload_id))
        workload_effects[workload_id] = {
            "raw": summarize_log_effect([float(item["pair_log_ratio"]) for item in entries]),
            "host_corrected": summarize_log_effect(
                [float(item["corrected_pair_log_ratio"]) for item in entries]
            ),
        }
        for item in entries:
            pair_index = item.get("pair_index")
            if type(pair_index) is not int:
                raise ValueError("null-control pair index is invalid")
            by_pair.setdefault(pair_index, []).append(item)
    if set(by_pair) != set(range(1, 11)) or any(len(items) != len(workload_ids) for items in by_pair.values()):
        raise ValueError("null-control pair indexes do not cover both workloads")
    combined_raw = [
        statistics.mean(float(item["pair_log_ratio"]) for item in by_pair[pair])
        for pair in range(1, 11)
    ]
    combined_corrected = [
        statistics.mean(float(item["corrected_pair_log_ratio"]) for item in by_pair[pair])
        for pair in range(1, 11)
    ]
    combined = {
        "raw": summarize_log_effect(combined_raw),
        "host_corrected": summarize_log_effect(combined_corrected),
    }
    checks: List[Dict[str, Any]] = []
    for workload_id in workload_ids:
        for mode in ("raw", "host_corrected"):
            effect = workload_effects[workload_id][mode]
            checks.append(
                {
                    "scope": workload_id,
                    "mode": mode,
                    "max_abs_effect": NULL_CONTROL_WORKLOAD_MAX_ABS_EFFECT,
                    "absolute_effect_pass": abs(float(effect["geometric_mean_effect"]))
                    <= NULL_CONTROL_WORKLOAD_MAX_ABS_EFFECT,
                    "ci95_contains_zero": _ci_contains_zero(effect),
                }
            )
    for mode in ("raw", "host_corrected"):
        effect = combined[mode]
        checks.append(
            {
                "scope": "combined",
                "mode": mode,
                "max_abs_effect": NULL_CONTROL_COMBINED_MAX_ABS_EFFECT,
                "absolute_effect_pass": abs(float(effect["geometric_mean_effect"]))
                <= NULL_CONTROL_COMBINED_MAX_ABS_EFFECT,
                "ci95_contains_zero": _ci_contains_zero(effect),
            }
        )
    failed = [
        "{} {} effect/CI".format(item["scope"], item["mode"])
        for item in checks
        if not item["absolute_effect_pass"] or not item["ci95_contains_zero"]
    ]
    return {
        "method": "same-executable-null-v1",
        "primary_mode": "raw",
        "workload_max_abs_effect": NULL_CONTROL_WORKLOAD_MAX_ABS_EFFECT,
        "combined_max_abs_effect": NULL_CONTROL_COMBINED_MAX_ABS_EFFECT,
        "workloads": workload_effects,
        "combined": combined,
        "checks": checks,
        "pass": not failed,
        "reasons": failed,
    }


def validate_inter_run_cooldown(value: float) -> float:
    """Validate the fixed host-recovery interval used by performance A/B."""
    if not math.isfinite(value) or value != AB_INTER_RUN_COOLDOWN_SECONDS:
        raise ValueError(
            "--inter-run-cooldown-seconds is fixed at {:.0f}".format(
                AB_INTER_RUN_COOLDOWN_SECONDS
            )
        )
    return value


def primary_metric_fields(primary_metric: str) -> Dict[str, str]:
    """Return the immutable throughput fields for a production A/B metric."""
    if primary_metric == "cpu-time":
        return {
            "raw": "cycles_per_emulation_cpu_second",
            "corrected": "corrected_emulated_cycles_per_cpu_second",
            "predicted": "predicted_anchor_cpu_throughput",
        }
    if primary_metric == "wall-time":
        return {
            "raw": "emulated_cycles_per_wall_second",
            "corrected": "corrected_emulated_cycles_per_wall_second",
            "predicted": "predicted_anchor_throughput",
        }
    raise ValueError("unknown primary metric: {}".format(primary_metric))


def _sleep_between_runs(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _with_host_stability_primary_metric(
    policy: Dict[str, Any], primary_metric: Optional[str]
) -> Dict[str, Any]:
    """Annotate a newly generated sentinel with its throughput clock.

    Historical v1/v2/v3 records omitted this field and therefore mean
    wall-time.  Keeping the field optional preserves those immutable records;
    new CPU-time sentinels must declare the clock explicitly so a CPU-primary
    A/B cannot accidentally use a wall-only preflight.
    """
    if primary_metric is not None:
        primary_metric_fields(primary_metric)
        policy["primary_metric"] = primary_metric
    return policy


def host_stability_measurement_policy(
    primary_metric: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the fixed sentinel protocol used before a v3 production batch."""
    return _with_host_stability_primary_metric(
        {
            "method": "host-stability-sentinel-v1",
            "warmup_runs": HOST_STABILITY_WARMUP_RUNS,
            "measured_runs": HOST_STABILITY_MEASURED_RUNS,
            "inter_run_cooldown_seconds": AB_INTER_RUN_COOLDOWN_SECONDS,
            "adjacent_log_throughput_threshold": HOST_STABILITY_ADJACENT_LOG_LIMIT,
            "relative_mad_threshold": HOST_STABILITY_MAD_LIMIT,
        },
        primary_metric,
    )


def host_stability_measurement_policy_v2(
    primary_metric: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the fixed grouped sentinel protocol used after v1 rejection."""
    return _with_host_stability_primary_metric(
        {
            "method": "host-stability-sentinel-v2",
            "warmup_runs": HOST_STABILITY_WARMUP_RUNS,
            "measured_runs": HOST_STABILITY_V2_MEASURED_RUNS,
            "replicates_per_group": HOST_STABILITY_V2_GROUP_SIZE,
            "group_count": HOST_STABILITY_V2_GROUP_COUNT,
            "inter_run_cooldown_seconds": AB_INTER_RUN_COOLDOWN_SECONDS,
            "group_adjacent_log_throughput_threshold": HOST_STABILITY_V2_GROUP_ADJACENT_LOG_LIMIT,
            "relative_mad_threshold": HOST_STABILITY_MAD_LIMIT,
        },
        primary_metric,
    )


def host_stability_measurement_policy_v3(
    primary_metric: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the grouped sentinel protocol with host attribution counters."""
    policy = host_stability_measurement_policy_v2(primary_metric=primary_metric)
    policy["method"] = "host-stability-sentinel-v3"
    policy["diagnostics"] = [
        "cpu_pressure",
        "proc_cpu_stat_steal",
        "cgroup_cpu_stat",
        "scheduler",
    ]
    return policy


def host_stability_measurement_policy_for_version(
    version: int, primary_metric: Optional[str] = None
) -> Dict[str, Any]:
    if version == 1:
        return host_stability_measurement_policy(primary_metric=primary_metric)
    if version == 2:
        return host_stability_measurement_policy_v2(primary_metric=primary_metric)
    if version == 3:
        return host_stability_measurement_policy_v3(primary_metric=primary_metric)
    raise ValueError("unsupported host stability protocol version: {}".format(version))


def cpu_time_diagnostic_measurement_policy() -> Dict[str, Any]:
    return {
        "method": "cpu-time-attribution-v1",
        "warmup_runs": CPU_TIME_DIAGNOSTIC_WARMUP_RUNS,
        "measured_runs": CPU_TIME_DIAGNOSTIC_MEASURED_RUNS,
        "inter_run_cooldown_seconds": AB_INTER_RUN_COOLDOWN_SECONDS,
        "primary_metric": "cycles_per_cpu_second",
        "secondary_metric": "cycles_per_wall_second",
    }


def _host_snapshot_is_complete(snapshot: object, expected_cpu: Optional[int]) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    required = ("model", "logical_cpus", "reported_mhz", "loadavg", "allowed_cpus", "platform", "kernel")
    if any(key not in snapshot for key in required):
        return False
    if not isinstance(snapshot.get("model"), str) or not snapshot["model"]:
        return False
    if type(snapshot.get("logical_cpus")) is not int or snapshot["logical_cpus"] <= 0:
        return False
    if not isinstance(snapshot.get("reported_mhz"), (int, float)) or isinstance(snapshot["reported_mhz"], bool):
        return False
    if not math.isfinite(float(snapshot["reported_mhz"])) or float(snapshot["reported_mhz"]) <= 0:
        return False
    loadavg = snapshot.get("loadavg")
    if (
        not isinstance(loadavg, list)
        or len(loadavg) != 3
        or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in loadavg)
    ):
        return False
    allowed_cpus = snapshot.get("allowed_cpus")
    if not isinstance(allowed_cpus, list) or any(type(value) is not int for value in allowed_cpus):
        return False
    if expected_cpu is not None and allowed_cpus != [expected_cpu]:
        return False
    return isinstance(snapshot.get("platform"), str) and isinstance(snapshot.get("kernel"), str)


def _host_snapshot_diagnostics_complete(snapshot: object) -> bool:
    """Validate the additional host counters used for drift attribution."""
    if not isinstance(snapshot, Mapping):
        return False
    pressure = snapshot.get("cpu_pressure")
    if not isinstance(pressure, Mapping) or set(pressure) != {"some", "full"}:
        return False
    for values in pressure.values():
        if not isinstance(values, Mapping) or not {"avg10", "avg60", "avg300", "total"}.issubset(values):
            return False
        if any(
            not isinstance(values[key], (int, float))
            or isinstance(values[key], bool)
            or not math.isfinite(float(values[key]))
            or float(values[key]) < 0
            for key in ("avg10", "avg60", "avg300", "total")
        ):
            return False
    proc_cpu = snapshot.get("proc_cpu_stat")
    proc_keys = {
        "user", "nice", "system", "idle", "iowait", "irq", "softirq",
        "steal", "guest", "guest_nice",
    }
    if not isinstance(proc_cpu, Mapping) or set(proc_cpu) != proc_keys:
        return False
    if any(type(proc_cpu[key]) is not int or proc_cpu[key] < 0 for key in proc_keys):
        return False
    cgroup_cpu = snapshot.get("cgroup_cpu_stat")
    cgroup_keys = {"usage_usec", "user_usec", "system_usec", "nice_usec", "nr_periods", "nr_throttled", "throttled_usec"}
    if not isinstance(cgroup_cpu, Mapping) or not cgroup_keys.issubset(cgroup_cpu):
        return False
    if any(
        type(cgroup_cpu[key]) is not int or cgroup_cpu[key] < 0
        for key in cgroup_keys
    ):
        return False
    scheduler = snapshot.get("scheduler")
    if not isinstance(scheduler, Mapping) or set(scheduler) != {"policy", "priority", "nice"}:
        return False
    return all(type(scheduler[key]) is int for key in ("policy", "priority", "nice"))


def summarize_host_stability(
    samples: Sequence[Mapping[str, Any]],
    *,
    expected_cpu: Optional[int] = None,
    expected_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Recompute the preflight gates from immutable sentinel samples."""
    if len(samples) != HOST_STABILITY_MEASURED_RUNS:
        raise ValueError(
            "host stability preflight requires exactly {} measured samples".format(
                HOST_STABILITY_MEASURED_RUNS
            )
        )
    throughputs: List[float] = []
    snapshot_valid = True
    identity_values = []
    affinity_valid = True
    for sample in samples:
        throughput = sample.get("throughput")
        if not isinstance(throughput, (int, float)) or isinstance(throughput, bool) or not math.isfinite(float(throughput)) or float(throughput) <= 0:
            raise ValueError("host stability sample throughput is invalid")
        throughputs.append(float(throughput))
        snapshot_valid = snapshot_valid and _host_snapshot_is_complete(
            sample.get("host_snapshot_start"), expected_cpu
        ) and _host_snapshot_is_complete(sample.get("host_snapshot_end"), expected_cpu)
        start_affinity = sample.get("host_snapshot_start", {}).get("allowed_cpus") if isinstance(sample.get("host_snapshot_start"), Mapping) else None
        end_affinity = sample.get("host_snapshot_end", {}).get("allowed_cpus") if isinstance(sample.get("host_snapshot_end"), Mapping) else None
        affinity_valid = affinity_valid and start_affinity == end_affinity and (
            expected_cpu is None or start_affinity == [expected_cpu]
        )
        identity_values.append(
            (
                sample.get("backend_commit"),
                sample.get("runner_sha256"),
                sample.get("build_provenance_sha256"),
            )
        )
    if expected_identity is None:
        identity_valid = len(set(identity_values)) == 1 and all(
            isinstance(value, str) and value for identity in identity_values for value in identity
        )
    else:
        expected_tuple = (
            expected_identity.get("commit"),
            expected_identity.get("runner_sha256"),
            expected_identity.get("build_provenance_sha256"),
        )
        identity_valid = all(identity == expected_tuple for identity in identity_values)
    log_values = [math.log(value) for value in throughputs]
    median_log = _median(log_values)
    mad = _median([abs(value - median_log) for value in log_values])
    scaled_mad = 1.4826 * mad
    relative_mad = math.exp(scaled_mad) - 1.0
    adjacent_deltas = [
        abs(log_values[index] - log_values[index - 1])
        for index in range(1, len(log_values))
    ]
    max_adjacent_delta = max(adjacent_deltas, default=0.0)
    gates = {
        "sample_count_valid": len(samples) == HOST_STABILITY_MEASURED_RUNS,
        "relative_mad_valid": relative_mad <= HOST_STABILITY_MAD_LIMIT,
        "adjacent_log_throughput_valid": max_adjacent_delta <= HOST_STABILITY_ADJACENT_LOG_LIMIT,
        "host_snapshot_valid": snapshot_valid,
        "identity_valid": identity_valid,
        "cpu_affinity_valid": affinity_valid,
    }
    return {
        "sample_count": len(samples),
        "throughput_median": math.exp(median_log),
        "median_log_throughput": median_log,
        "mad_log_throughput": mad,
        "scaled_mad": scaled_mad,
        "relative_mad": relative_mad,
        "adjacent_abs_log_deltas": adjacent_deltas,
        "max_adjacent_abs_log_delta": max_adjacent_delta,
        "gates": gates,
        "valid": all(gates.values()),
    }


def summarize_host_stability_v2(
    samples: Sequence[Mapping[str, Any]],
    *,
    expected_cpu: Optional[int] = None,
    expected_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Recompute the grouped v2 sentinel gates from immutable samples.

    The raw adjacent deltas remain diagnostic.  The fixed acceptance gates use
    three-sample log medians and require both each group's relative MAD and
    each adjacent group-median delta to be at most 2%.
    """
    if len(samples) != HOST_STABILITY_V2_MEASURED_RUNS:
        raise ValueError(
            "host stability v2 preflight requires exactly {} measured samples".format(
                HOST_STABILITY_V2_MEASURED_RUNS
            )
        )
    throughputs: List[float] = []
    snapshot_valid = True
    identity_values = []
    affinity_valid = True
    for sample in samples:
        throughput = sample.get("throughput")
        if (
            not isinstance(throughput, (int, float))
            or isinstance(throughput, bool)
            or not math.isfinite(float(throughput))
            or float(throughput) <= 0
        ):
            raise ValueError("host stability v2 sample throughput is invalid")
        throughputs.append(float(throughput))
        snapshot_valid = snapshot_valid and _host_snapshot_is_complete(
            sample.get("host_snapshot_start"), expected_cpu
        ) and _host_snapshot_is_complete(sample.get("host_snapshot_end"), expected_cpu)
        start_affinity = (
            sample.get("host_snapshot_start", {}).get("allowed_cpus")
            if isinstance(sample.get("host_snapshot_start"), Mapping)
            else None
        )
        end_affinity = (
            sample.get("host_snapshot_end", {}).get("allowed_cpus")
            if isinstance(sample.get("host_snapshot_end"), Mapping)
            else None
        )
        affinity_valid = affinity_valid and start_affinity == end_affinity and (
            expected_cpu is None or start_affinity == [expected_cpu]
        )
        identity_values.append(
            (
                sample.get("backend_commit"),
                sample.get("runner_sha256"),
                sample.get("build_provenance_sha256"),
            )
        )
    if expected_identity is None:
        identity_valid = len(set(identity_values)) == 1 and all(
            isinstance(value, str) and value
            for identity in identity_values
            for value in identity
        )
    else:
        expected_tuple = (
            expected_identity.get("commit"),
            expected_identity.get("runner_sha256"),
            expected_identity.get("build_provenance_sha256"),
        )
        identity_valid = all(identity == expected_tuple for identity in identity_values)
    log_values = [math.log(value) for value in throughputs]
    median_log = _median(log_values)
    mad = _median([abs(value - median_log) for value in log_values])
    scaled_mad = 1.4826 * mad
    relative_mad = math.exp(scaled_mad) - 1.0
    adjacent_deltas = [
        abs(log_values[index] - log_values[index - 1])
        for index in range(1, len(log_values))
    ]
    group_median_logs = []
    group_relative_mads = []
    for start in range(0, len(log_values), HOST_STABILITY_V2_GROUP_SIZE):
        group_logs = log_values[start : start + HOST_STABILITY_V2_GROUP_SIZE]
        group_median = _median(group_logs)
        group_mad = _median([abs(value - group_median) for value in group_logs])
        group_median_logs.append(group_median)
        group_relative_mads.append(math.exp(1.4826 * group_mad) - 1.0)
    group_median_deltas = [
        abs(group_median_logs[index] - group_median_logs[index - 1])
        for index in range(1, len(group_median_logs))
    ]
    max_adjacent_delta = max(adjacent_deltas, default=0.0)
    max_group_median_delta = max(group_median_deltas, default=0.0)
    gates = {
        "sample_count_valid": len(samples) == HOST_STABILITY_V2_MEASURED_RUNS,
        "relative_mad_valid": relative_mad <= HOST_STABILITY_MAD_LIMIT,
        "group_relative_mad_valid": all(
            value <= HOST_STABILITY_MAD_LIMIT for value in group_relative_mads
        ),
        "group_adjacent_log_throughput_valid": max_group_median_delta
        <= HOST_STABILITY_V2_GROUP_ADJACENT_LOG_LIMIT,
        "host_snapshot_valid": snapshot_valid,
        "identity_valid": identity_valid,
        "cpu_affinity_valid": affinity_valid,
    }
    return {
        "sample_count": len(samples),
        "throughput_median": math.exp(median_log),
        "median_log_throughput": median_log,
        "mad_log_throughput": mad,
        "scaled_mad": scaled_mad,
        "relative_mad": relative_mad,
        "adjacent_abs_log_deltas": adjacent_deltas,
        "max_adjacent_abs_log_delta": max_adjacent_delta,
        "group_medians": [math.exp(value) for value in group_median_logs],
        "group_relative_mads": group_relative_mads,
        "group_median_abs_log_deltas": group_median_deltas,
        "max_group_median_abs_log_delta": max_group_median_delta,
        "gates": gates,
        "valid": all(gates.values()),
    }


def summarize_host_stability_v3(
    samples: Sequence[Mapping[str, Any]],
    *,
    expected_cpu: Optional[int] = None,
    expected_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply the v2 grouped gates and require attribution snapshots."""
    summary = summarize_host_stability_v2(
        samples,
        expected_cpu=expected_cpu,
        expected_identity=expected_identity,
    )
    diagnostics_valid = all(
        _host_snapshot_diagnostics_complete(sample.get("host_snapshot_start"))
        and _host_snapshot_diagnostics_complete(sample.get("host_snapshot_end"))
        for sample in samples
    )
    gates = dict(summary["gates"])
    gates["diagnostics_valid"] = diagnostics_valid
    summary["gates"] = gates
    summary["valid"] = all(gates.values())
    return summary


def summarize_cpu_time_attribution(
    samples: Sequence[Mapping[str, Any]],
    *,
    expected_cpu: Optional[int] = None,
    expected_identity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Summarize CPU-time versus wall-time without making a speed claim."""
    if len(samples) != CPU_TIME_DIAGNOSTIC_MEASURED_RUNS:
        raise ValueError(
            "CPU-time diagnostic requires exactly {} measured samples".format(
                CPU_TIME_DIAGNOSTIC_MEASURED_RUNS
            )
        )
    wall_values: List[float] = []
    cpu_values: List[float] = []
    cpu_time_sources: List[str] = []
    snapshot_valid = True
    affinity_valid = True
    identity_values = []
    for sample in samples:
        cycles = sample.get("cycles")
        wall_seconds = sample.get("wall_seconds")
        emulation_wall_seconds = sample.get("emulation_wall_seconds")
        emulation_cpu_seconds = sample.get("emulation_cpu_seconds")
        user_seconds = sample.get("user_seconds")
        system_seconds = sample.get("system_seconds")
        if (
            type(cycles) is not int
            or cycles <= 0
            or not isinstance(wall_seconds, (int, float))
            or isinstance(wall_seconds, bool)
            or not math.isfinite(float(wall_seconds))
            or float(wall_seconds) <= 0
            or not isinstance(user_seconds, (int, float))
            or isinstance(user_seconds, bool)
            or not math.isfinite(float(user_seconds))
            or float(user_seconds) < 0
            or not isinstance(system_seconds, (int, float))
            or isinstance(system_seconds, bool)
            or not math.isfinite(float(system_seconds))
            or float(system_seconds) < 0
            or float(user_seconds) + float(system_seconds) <= 0
        ):
            raise ValueError("CPU-time diagnostic sample timing is invalid")
        wall_values.append(float(cycles) / float(wall_seconds))
        if (
            isinstance(emulation_cpu_seconds, (int, float))
            and not isinstance(emulation_cpu_seconds, bool)
            and math.isfinite(float(emulation_cpu_seconds))
            and float(emulation_cpu_seconds) > 0
            and isinstance(emulation_wall_seconds, (int, float))
            and not isinstance(emulation_wall_seconds, bool)
            and math.isfinite(float(emulation_wall_seconds))
            and float(emulation_wall_seconds) > 0
        ):
            cpu_values.append(float(cycles) / float(emulation_cpu_seconds))
            cpu_time_sources.append("in_process_run_loop")
        else:
            # Keep the historical diagnostic record readable, but never let
            # this child-level fallback masquerade as the new primary metric.
            cpu_values.append(float(cycles) / (float(user_seconds) + float(system_seconds)))
            cpu_time_sources.append("child_rusage")
        snapshot_valid = snapshot_valid and _host_snapshot_is_complete(
            sample.get("host_snapshot_start"), expected_cpu
        ) and _host_snapshot_is_complete(sample.get("host_snapshot_end"), expected_cpu)
        start_affinity = (
            sample.get("host_snapshot_start", {}).get("allowed_cpus")
            if isinstance(sample.get("host_snapshot_start"), Mapping)
            else None
        )
        end_affinity = (
            sample.get("host_snapshot_end", {}).get("allowed_cpus")
            if isinstance(sample.get("host_snapshot_end"), Mapping)
            else None
        )
        affinity_valid = affinity_valid and start_affinity == end_affinity and (
            expected_cpu is None or start_affinity == [expected_cpu]
        )
        identity_values.append(
            (
                sample.get("backend_commit"),
                sample.get("runner_sha256"),
                sample.get("build_provenance_sha256"),
            )
        )
    if expected_identity is None:
        identity_valid = len(set(identity_values)) == 1 and all(
            isinstance(value, str) and value
            for identity in identity_values
            for value in identity
        )
    else:
        expected_tuple = (
            expected_identity.get("commit"),
            expected_identity.get("runner_sha256"),
            expected_identity.get("build_provenance_sha256"),
        )
        identity_valid = all(identity == expected_tuple for identity in identity_values)

    def stats(values: Sequence[float]) -> Dict[str, Any]:
        logs = [math.log(value) for value in values]
        median_log = _median(logs)
        mad = _median([abs(value - median_log) for value in logs])
        scaled = 1.4826 * mad
        return {
            "median": math.exp(median_log),
            "mad_log": mad,
            "relative_mad": math.exp(scaled) - 1.0,
        }

    wall_stats = stats(wall_values)
    cpu_stats = stats(cpu_values)
    ratio_values = [cpu / wall for cpu, wall in zip(cpu_values, wall_values)]
    ratio_stats = stats(ratio_values)
    gates = {
        "sample_count_valid": len(samples) == CPU_TIME_DIAGNOSTIC_MEASURED_RUNS,
        "cpu_time_valid": all(value > 0 for value in cpu_values),
        "wall_time_valid": all(value > 0 for value in wall_values),
        "host_snapshot_valid": snapshot_valid,
        "identity_valid": identity_valid,
        "cpu_affinity_valid": affinity_valid,
    }
    return {
        "sample_count": len(samples),
        "wall_throughput": wall_stats,
        "cpu_throughput": cpu_stats,
        "cpu_to_wall_ratio": ratio_stats,
        "wall_throughputs": wall_values,
        "cpu_throughputs": cpu_values,
        "cpu_time_sources": sorted(set(cpu_time_sources)),
        "primary_cpu_time_scope": (
            "in_process_run_loop"
            if set(cpu_time_sources) == {"in_process_run_loop"}
            else "child_rusage"
            if set(cpu_time_sources) == {"child_rusage"}
            else "mixed"
        ),
        "gates": gates,
        "valid": all(gates.values()),
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
            "measurement_cpu", "diagnostic_profile_record", "host_stability_record",
            "host_stability_record_sha256",
        ):
            # A profile is produced after correctness for P1-B/P2-A.  The
            # correctness phase therefore cannot know its record name yet;
            # allow optional phase metadata to transition from absent to its
            # fixed pointer exactly once.  Any later change remains an
            # identity mismatch and is rejected.
            if (
                field in {
                    "diagnostic_profile_record",
                    "host_stability_record",
                    "host_stability_record_sha256",
                }
                and existing.get(field) is None
                and manifest.get(field) is not None
            ):
                continue
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
        if (
            merged.get("diagnostic_profile_record") is None
            and manifest.get("diagnostic_profile_record") is not None
        ):
            merged["diagnostic_profile_record"] = manifest["diagnostic_profile_record"]
        for field in ("host_stability_record", "host_stability_record_sha256"):
            if merged.get(field) is None and manifest.get(field) is not None:
                merged[field] = manifest[field]
        existing_policy = existing.get("measurement_policy")
        new_policy = manifest.get("measurement_policy")
        if new_policy is not None:
            if existing_policy is not None and existing_policy != new_policy:
                raise ValueError("record manifest measurement policy mismatch: {}".format(manifest_path))
            merged["measurement_policy"] = dict(new_policy)
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
    expected_feature_set: Sequence[str] = ()
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
        host_timing_path = directory / "host-timing.json"
        trace_path = behavior_trace or (directory / "behavior-trace.json")
        profile_path = cpu_application_profile
        if behavior_trace is not None:
            behavior_trace.parent.mkdir(parents=True, exist_ok=True)
        if cpu_application_profile is not None:
            cpu_application_profile.parent.mkdir(parents=True, exist_ok=True)
        command = target_command(
            workload["target"], workload["firmware"], runner, report_path, uart_path, snapshots,
            backend_commit=backend_identity["commit"],
            feature_set=expected_feature_set,
            behavior_trace=trace_path if behavior_trace is not None else None,
            cpu_application_profile=profile_path,
            host_timing=host_timing_path,
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
        validate_report(
            workload, report, backend_identity["commit"], expected_feature_set
        )
        if behavior_trace is not None and not behavior_trace.is_file():
            raise ValueError("runner did not write behavior trace: {}".format(behavior_trace))
        if cpu_application_profile is not None and not cpu_application_profile.is_file():
            raise ValueError("runner did not write CPU profile: {}".format(cpu_application_profile))
        if not host_timing_path.is_file():
            raise ValueError("runner did not write in-process host timing: {}".format(host_timing_path))
        host_timing = json.loads(host_timing_path.read_bytes())
        if not isinstance(host_timing, Mapping):
            raise ValueError("runner host timing is not an object")
        if host_timing.get("schema_version") != 1:
            raise ValueError("runner host timing schema_version is not 1")
        if host_timing.get("artifact_type") != "in-process-host-timing":
            raise ValueError("runner host timing artifact_type is invalid")
        if host_timing.get("timing_scope") != "picocalc-harness::run_loop":
            raise ValueError("runner host timing scope is invalid")
        timing_cycles = host_timing.get("cycles")
        if timing_cycles != report.get("cycles"):
            raise ValueError("runner host timing cycles differ from report")
        if host_timing.get("stop_reason") != report.get("stop_reason"):
            raise ValueError("runner host timing stop_reason differs from report")
        emulation_wall_ns = host_timing.get("emulation_wall_ns")
        emulation_cpu_ns = host_timing.get("emulation_cpu_ns")
        if type(emulation_wall_ns) is not int or emulation_wall_ns <= 0:
            raise ValueError("runner host timing has invalid emulation_wall_ns")
        if type(emulation_cpu_ns) is not int or emulation_cpu_ns <= 0:
            raise ValueError("runner host timing has invalid emulation_cpu_ns")
        wall_seconds = wall_ns / 1_000_000_000
        cycles = report["cycles"]
        if type(cycles) is not int or cycles <= 0 or wall_ns <= 0:
            raise ValueError("runner report has invalid positive timing/cycle values")
        measurement: Dict[str, Any] = {
            "wall_ns": wall_ns,
            "wall_seconds": wall_seconds,
            "cycles": cycles,
            # This interval is measured inside the runner, around only the
            # authoritative run_loop. It excludes subprocess startup/wait,
            # report serialization, and the benchmark cooldown.
            "emulation_wall_ns": emulation_wall_ns,
            "emulation_wall_seconds": emulation_wall_ns / 1_000_000_000,
            "emulation_cpu_ns": emulation_cpu_ns,
            "emulation_cpu_seconds": emulation_cpu_ns / 1_000_000_000,
            "cycles_per_emulation_cpu_second": cycles / (emulation_cpu_ns / 1_000_000_000),
            "cycles_per_emulation_wall_second": cycles / (emulation_wall_ns / 1_000_000_000),
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
    effective = sorted(os.sched_getaffinity(0))
    if effective != [cpu]:
        os.sched_setaffinity(0, set(before))
        raise ValueError(
            "--cpu affinity request was not applied: requested {}, got {}".format(
                cpu, effective
            )
        )
    return before


def _restore_cpu_affinity(before: Optional[List[int]]) -> None:
    if before is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, set(before))


def _host_stability_identity(
    backend: Path, runner: Path, feature_set: Sequence[str]
) -> Dict[str, Any]:
    identity = clean_backend_identity(backend)
    if not runner.is_file():
        raise ValueError("runner is missing: {}".format(runner))
    validate_runner_embedded_commit(runner, identity["commit"])
    normalized_features = effective_feature_set(feature_set)
    provenance = validate_runner_provenance(
        runner,
        identity["commit"],
        normalized_features,
        expected_role="baseline_production",
    )
    identity.update(
        {
            "runner_sha256": sha256_file(runner),
            "feature_set": normalized_features,
            "build_provenance_sha256": provenance["sha256"],
            "role": "baseline_production",
            "provenance_role": provenance["role"],
        }
    )
    return identity


def _require_host_stability_gate(
    record_path: Optional[Path],
    workloads: Sequence[Mapping[str, Any]],
    baseline_identity: Mapping[str, Any],
    measurement_cpu: int,
    inter_run_cooldown_seconds: float,
    primary_metric: str = "wall-time",
) -> Dict[str, Any]:
    """Reject v3 A/B before subprocess launch unless the sentinel passed.

    A sentinel without ``primary_metric`` is a historical wall-time record.
    CPU-primary A/B therefore requires a newly generated sentinel that
    explicitly measures the in-process CPU-time throughput; a wall-only
    preflight must never silently authorize a CPU-time comparison.
    """
    primary_metric_fields(primary_metric)
    if record_path is None:
        raise ValueError("v3 A/B requires --host-stability-record")
    path = record_path.resolve()
    if not path.is_file():
        raise ValueError("host stability record is missing: {}".format(path))
    record = _read_json(path)
    if not isinstance(record, Mapping):
        raise ValueError("host stability record is not an object: {}".format(path))
    if (
        record.get("schema_id") != HOST_STABILITY_SCHEMA_ID
        or record.get("schema_version") != SCHEMA_VERSION
        or record.get("artifact_type") != "host-stability"
        or record.get("status") != "pass"
    ):
        raise ValueError("host stability record is not passing: {}".format(path))
    measurement_policy = record.get("measurement_policy")
    if not isinstance(measurement_policy, Mapping):
        raise ValueError("host stability measurement policy is invalid")
    record_primary_metric = measurement_policy.get("primary_metric", "wall-time")
    if record_primary_metric != primary_metric:
        raise ValueError(
            "host stability record primary metric differs from A/B: {} != {}".format(
                record_primary_metric, primary_metric
            )
        )
    method = measurement_policy.get("method")
    if method == "host-stability-sentinel-v1":
        summarize = summarize_host_stability
        expected_policy = host_stability_measurement_policy(
            primary_metric=record_primary_metric
            if "primary_metric" in measurement_policy
            else None
        )
    elif method == "host-stability-sentinel-v2":
        summarize = summarize_host_stability_v2
        expected_policy = host_stability_measurement_policy_v2(
            primary_metric=record_primary_metric
            if "primary_metric" in measurement_policy
            else None
        )
    elif method == "host-stability-sentinel-v3":
        summarize = summarize_host_stability_v3
        expected_policy = host_stability_measurement_policy_v3(
            primary_metric=record_primary_metric
            if "primary_metric" in measurement_policy
            else None
        )
    else:
        raise ValueError("host stability measurement policy differs from the fixed protocol")
    if dict(measurement_policy) != expected_policy:
        raise ValueError("host stability measurement policy differs from the fixed protocol")
    if record.get("measurement_cpu") != measurement_cpu:
        raise ValueError("host stability record CPU differs from A/B")
    expected_workload = next(
        (workload for workload in workloads if workload["id"].startswith("picotetris-")),
        None,
    )
    recorded_workload = record.get("workload")
    if expected_workload is None or not isinstance(recorded_workload, Mapping):
        raise ValueError("host stability record workload is invalid")
    expected_workload_identity = {
        key: expected_workload[key]
        for key in ("id", "revision", "firmware_sha256", "scenario_sha256", "contract_sha256")
    }
    if dict(recorded_workload) != expected_workload_identity:
        raise ValueError("host stability record workload differs from A/B")
    if record.get("backend_identity") != dict(baseline_identity):
        raise ValueError("host stability record backend identity differs from A/B")
    if record.get("cpu_affinity") != {"requested": measurement_cpu, "effective": [measurement_cpu]}:
        raise ValueError("host stability record affinity differs from A/B")
    if record.get("inter_run_cooldown_seconds") != inter_run_cooldown_seconds:
        raise ValueError("host stability record cooldown differs from A/B")
    samples = record.get("samples")
    if not isinstance(samples, list) or any(not isinstance(sample, Mapping) for sample in samples):
        raise ValueError("host stability record samples are invalid")
    expected_summary = summarize(
        samples,
        expected_cpu=measurement_cpu,
        expected_identity=baseline_identity,
    )
    if record.get("summary") != expected_summary:
        raise ValueError("host stability record summary is not derived from samples")
    return dict(record)


def run_cpu_time_diagnostic(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if args.cpu is None:
        raise ValueError("cpu-time-diagnostic requires --cpu for affinity pinning")
    warmup = CPU_TIME_DIAGNOSTIC_WARMUP_RUNS if args.warmup is None else args.warmup
    runs = CPU_TIME_DIAGNOSTIC_MEASURED_RUNS if args.runs is None else args.runs
    if warmup != CPU_TIME_DIAGNOSTIC_WARMUP_RUNS:
        raise ValueError("cpu-time-diagnostic fixes --warmup at {}".format(CPU_TIME_DIAGNOSTIC_WARMUP_RUNS))
    if runs != CPU_TIME_DIAGNOSTIC_MEASURED_RUNS:
        raise ValueError("cpu-time-diagnostic fixes --runs at {}".format(CPU_TIME_DIAGNOSTIC_MEASURED_RUNS))
    cooldown = validate_inter_run_cooldown(args.inter_run_cooldown_seconds)
    calibration_workload = next(
        (workload for workload in workloads if workload["id"].startswith("picotetris-")),
        None,
    )
    if calibration_workload is None:
        raise ValueError("cpu-time-diagnostic requires the registered PicoTetris workload")
    identity = _host_stability_identity(args.backend, args.runner, getattr(args, "feature_set", []))
    _require_admission_gate(args.admission_record, workloads, identity)
    output = args.output.resolve()
    _refuse_existing(output)
    before = _set_cpu_affinity(args.cpu)
    samples: List[Dict[str, Any]] = []
    error_text: Optional[str] = None
    try:
        for _ in range(warmup):
            run_guest(
                calibration_workload,
                args.backend,
                args.runner,
                expected_backend_identity=identity,
            )
            _sleep_between_runs(cooldown)
        for index in range(1, runs + 1):
            host_start = host_cpu()
            result = run_guest(
                calibration_workload,
                args.backend,
                args.runner,
                expected_backend_identity=identity,
            )
            host_end = host_cpu()
            measurement = result["measurement"]
            usage = measurement.get("host_usage_delta", {})
            samples.append(
                {
                    "sample_id": "cpu-time-{:03d}".format(index),
                    "cycles": measurement["cycles"],
                    "wall_seconds": measurement["wall_seconds"],
                    "emulation_wall_seconds": measurement["emulation_wall_seconds"],
                    "emulation_cpu_seconds": measurement["emulation_cpu_seconds"],
                    "cycles_per_emulation_cpu_second": measurement[
                        "cycles_per_emulation_cpu_second"
                    ],
                    "cycles_per_emulation_wall_second": measurement[
                        "cycles_per_emulation_wall_second"
                    ],
                    "user_seconds": usage.get("user_seconds"),
                    "system_seconds": usage.get("system_seconds"),
                    "backend_commit": measurement["backend_commit"],
                    "runner_sha256": measurement["runner_sha256"],
                    "build_provenance_sha256": measurement["build_provenance_sha256"],
                    "host_snapshot_start": host_start,
                    "host_snapshot_end": host_end,
                }
            )
            _sleep_between_runs(cooldown)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        error_text = str(error)
    finally:
        _restore_cpu_affinity(before)
    if len(samples) == runs:
        summary = summarize_cpu_time_attribution(
            samples,
            expected_cpu=args.cpu,
            expected_identity=identity,
        )
    else:
        summary = {
            "sample_count": len(samples),
            "gates": {"sample_count_valid": False},
            "valid": False,
        }
    record = {
        "schema_id": "picocalc.rp2040-cpu-time-attribution",
        "schema_version": 1,
        "artifact_type": "cpu-time-attribution",
        "record_id": args.batch_id or output.stem,
        "status": "pass" if error_text is None and summary.get("valid") is True else "invalid",
        "measurement_policy": cpu_time_diagnostic_measurement_policy(),
        "measurement_cpu": args.cpu,
        "cpu_affinity": {"requested": args.cpu, "effective": [args.cpu]},
        "inter_run_cooldown_seconds": cooldown,
        "workload": {
            key: calibration_workload[key]
            for key in ("id", "revision", "firmware_sha256", "scenario_sha256", "contract_sha256")
        },
        "backend_identity": identity,
        "samples": samples,
        "summary": summary,
        "reasons": (
            [
                "gate:{}".format(name)
                for name, passed in summary.get("gates", {}).items()
                if passed is not True
            ]
            if error_text is None
            else [error_text]
        ),
    }
    _write_json_once(output, record)
    if record["status"] != "pass":
        raise ValueError("CPU-time diagnostic is invalid; see {}".format(output))
    print("CPU-time diagnostic: PASS ({})".format(output))
    return 0


def _child_affinity_setter(cpu: int):
    """Return a POSIX pre-exec hook that pins one independent guest."""
    if not hasattr(os, "sched_setaffinity"):
        raise ValueError("load-shape needs Linux sched_setaffinity")

    def apply() -> None:
        os.sched_setaffinity(0, {cpu})
        if sorted(os.sched_getaffinity(0)) != [cpu]:
            raise OSError("child affinity was not applied for CPU {}".format(cpu))

    return apply


def _load_shape_run_record(
    process: subprocess.Popen[bytes],
    report_path: Path,
    host_timing_path: Path,
    assigned_cpu: int,
    cycles: int,
) -> Dict[str, Any]:
    returncode = process.returncode
    if returncode != 0:
        raise ValueError("load-shape guest exited {}".format(returncode))
    if not report_path.is_file() or not host_timing_path.is_file():
        raise ValueError("load-shape guest did not produce report and host timing")
    report = _read_json(report_path)
    timing = _read_json(host_timing_path)
    if not isinstance(report, Mapping) or not isinstance(timing, Mapping):
        raise ValueError("load-shape report or host timing is not an object")
    if report.get("verdict", {}).get("status") != "pass":
        raise ValueError("load-shape guest verdict is not pass")
    if report.get("cycles") != cycles or timing.get("cycles") != cycles:
        raise ValueError("load-shape guest cycles differ from requested limit")
    if report.get("stop_reason") != "cycle_limit" or timing.get("stop_reason") != "cycle_limit":
        raise ValueError("load-shape guest did not stop at cycle_limit")
    if timing.get("artifact_type") != "in-process-host-timing":
        raise ValueError("load-shape host timing artifact type is invalid")
    cpu_ns = timing.get("emulation_cpu_ns")
    wall_ns = timing.get("emulation_wall_ns")
    if type(cpu_ns) is not int or cpu_ns <= 0 or type(wall_ns) is not int or wall_ns <= 0:
        raise ValueError("load-shape host timing values are invalid")
    cpu_seconds = cpu_ns / 1_000_000_000
    wall_seconds = wall_ns / 1_000_000_000
    return {
        "assigned_cpu": assigned_cpu,
        "cycles": cycles,
        "emulation_cpu_ns": cpu_ns,
        "emulation_cpu_seconds": cpu_seconds,
        "emulation_wall_ns": wall_ns,
        "emulation_wall_seconds": wall_seconds,
        "cycles_per_emulation_cpu_second": cycles / cpu_seconds,
        "cycles_per_emulation_wall_second": cycles / wall_seconds,
        "guest_observation_sha256": guest_observation_sha256(report),
        "report_sha256": sha256_file(report_path),
    }


def _pilot_dispersion(values: Sequence[float]) -> Dict[str, Any]:
    """Summarize a fixed-size pilot group without choosing a winner post hoc."""
    if not values or any(value <= 0 or not math.isfinite(value) for value in values):
        raise ValueError("pilot metric values must be finite and positive")
    median = statistics.median(values)
    mad = statistics.median([abs(value - median) for value in values])
    scaled_mad = 1.4826 * mad
    return {
        "median": median,
        "mad": mad,
        "scaled_mad": scaled_mad,
        "relative_mad": math.exp(scaled_mad / median) - 1.0,
    }


def _run_short_pilot_guest(
    workload: Mapping[str, Any],
    backend: Path,
    runner: Path,
    identity: Mapping[str, Any],
    cycles: int,
    *,
    affinity_mode: str,
    cpu: int,
) -> Dict[str, Any]:
    """Run one short, cycle-limited registered application for a pilot.

    The parent process owns the mode transition.  ``pinned-vcpu`` also applies
    a child pre-exec pin as a fail-closed check, while ``inherited-set``
    intentionally leaves the child affinity untouched so it inherits the
    parent's full allowed set.
    """
    if affinity_mode not in AFFINITY_PILOT_MODES:
        raise ValueError("unknown affinity pilot mode: {}".format(affinity_mode))
    with tempfile.TemporaryDirectory(prefix="picocalc-rp2040-pilot-") as temporary:
        root = Path(temporary)
        report_path = root / "report.json"
        uart_path = root / "uart.bin"
        timing_path = root / "host-timing.json"
        command = load_shape_command(
            workload["target"], workload["firmware"], runner,
            report_path, uart_path, timing_path, cycles,
            backend_commit=identity["commit"],
        )
        host_start = host_cpu()
        started_ns = time.perf_counter_ns()
        result = subprocess.run(
            command,
            cwd=str(backend),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            preexec_fn=(
                _child_affinity_setter(cpu)
                if affinity_mode == "pinned-vcpu"
                else None
            ),
        )
        process_wall_seconds = (time.perf_counter_ns() - started_ns) / 1_000_000_000
        host_end = host_cpu()
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise ValueError(
                "pilot guest exited {} for {}{}".format(
                    result.returncode,
                    workload["id"],
                    ": " + stderr[-500:] if stderr else "",
                )
            )
        short = _load_shape_run_record(
            result, report_path, timing_path, cpu, cycles
        )
        short.update(
            {
                "workload": workload["id"],
                "workload_revision": workload["revision"],
                "affinity_mode": affinity_mode,
                "expected_cpu": cpu,
                "parent_allowed_cpus": host_start.get("allowed_cpus"),
                "process_wall_seconds": process_wall_seconds,
                "host_snapshot_start": host_start,
                "host_snapshot_end": host_end,
            }
        )
        return short


def run_affinity_pilot(args: argparse.Namespace) -> int:
    """Compare pinned-vCPU and inherited-set execution on both workloads."""
    workloads = load_workloads(args.target, args.firmware)
    if args.cpu is None:
        raise ValueError("affinity-pilot requires --cpu")
    if args.replicates != AFFINITY_PILOT_REPLICATES:
        raise ValueError(
            "affinity-pilot fixes --replicates at {}".format(
                AFFINITY_PILOT_REPLICATES
            )
        )
    if type(args.cycles) is not int or args.cycles <= 0:
        raise ValueError("affinity-pilot requires positive --cycles")
    identity = clean_backend_identity(args.backend)
    validate_runner_embedded_commit(args.runner, identity["commit"])
    output = args.output.resolve()
    _refuse_existing(output)
    if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
        raise ValueError("affinity-pilot needs Linux sched_getaffinity/sched_setaffinity")
    original = sorted(os.sched_getaffinity(0))
    if args.cpu not in original:
        raise ValueError("affinity-pilot CPU is outside the allowed affinity set")
    rows: List[Dict[str, Any]] = []
    error_text: Optional[str] = None
    try:
        for mode in AFFINITY_PILOT_MODES:
            if mode == "pinned-vcpu":
                _set_cpu_affinity(args.cpu)
            else:
                os.sched_setaffinity(0, set(original))
            for workload in workloads:
                for replicate in range(1, args.replicates + 1):
                    row = _run_short_pilot_guest(
                        workload, args.backend, args.runner, identity, args.cycles,
                        affinity_mode=mode, cpu=args.cpu,
                    )
                    row["replicate"] = replicate
                    rows.append(row)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        error_text = str(error)
    finally:
        os.sched_setaffinity(0, set(original))
    expected_rows = len(AFFINITY_PILOT_MODES) * len(workloads) * args.replicates
    summaries: Dict[str, Any] = {}
    all_projection_equal = True
    for workload in workloads:
        by_mode = {}
        observations = set()
        for mode in AFFINITY_PILOT_MODES:
            group = [
                row for row in rows
                if row.get("workload") == workload["id"]
                and row.get("affinity_mode") == mode
            ]
            observations.update(row.get("guest_observation_sha256") for row in group)
            if len(group) != args.replicates:
                by_mode[mode] = {"replicates": len(group), "valid": False}
                continue
            by_mode[mode] = {
                "replicates": len(group),
                "cpu_throughput": _pilot_dispersion(
                    [row["cycles_per_emulation_cpu_second"] for row in group]
                ),
                "wall_throughput": _pilot_dispersion(
                    [row["cycles_per_emulation_wall_second"] for row in group]
                ),
                "cpu_wall_ratio": _pilot_dispersion(
                    [
                        row["emulation_cpu_seconds"]
                        / row["emulation_wall_seconds"]
                        for row in group
                    ]
                ),
                "observations": sorted(
                    {row["guest_observation_sha256"] for row in group}
                ),
            }
            by_mode[mode]["valid"] = (
                len(by_mode[mode]["observations"]) == 1
            )
        all_projection_equal = all_projection_equal and len(observations) == 1
        effect: Optional[float] = None
        if all(
            by_mode.get(mode, {}).get("valid") is True
            for mode in AFFINITY_PILOT_MODES
        ):
            effect = log_ratio(
                by_mode["inherited-set"]["cpu_throughput"]["median"],
                by_mode["pinned-vcpu"]["cpu_throughput"]["median"],
            )
        summaries[workload["id"]] = {
            "modes": by_mode,
            "guest_observation_equal_across_modes": len(observations) == 1,
            "inherited_over_pinned_cpu_log_ratio": effect,
        }
    valid = (
        error_text is None
        and len(rows) == expected_rows
        and all_projection_equal
        and all(
            summary["guest_observation_equal_across_modes"]
            and all(mode.get("valid") is True for mode in summary["modes"].values())
            for summary in summaries.values()
        )
    )
    record = {
        "schema_id": "picocalc.rp2040-cpu-affinity-pilot",
        "schema_version": 1,
        "artifact_type": "affinity-pilot",
        "record_id": args.batch_id or output.stem,
        "status": "pass" if valid else "invalid",
        "measurement_policy": {
            "method": "short-fixed-cycle-affinity-pilot-v1",
            "cycles_per_run": args.cycles,
            "modes": list(AFFINITY_PILOT_MODES),
            "replicates_per_mode_workload": args.replicates,
            "cpu_time_metric": "cycles_per_emulation_cpu_second",
            "diagnostic_only": True,
        },
        "measurement_cpu": args.cpu,
        "original_allowed_cpus": original,
        "backend_identity": identity,
        "runner_sha256": sha256_file(args.runner),
        "workloads": [
            {
                key: workload[key]
                for key in (
                    "id", "revision", "firmware_sha256", "scenario_sha256",
                    "contract_sha256",
                )
            }
            for workload in workloads
        ],
        "rows": rows,
        "summary": summaries,
        "reasons": [] if error_text is None else [error_text],
    }
    if len(rows) != expected_rows:
        record["reasons"].append(
            "expected {} rows, got {}".format(expected_rows, len(rows))
        )
    if not all_projection_equal:
        record["reasons"].append("guest observation differs across affinity modes")
    _write_json_once(output, record)
    if not valid:
        raise ValueError("affinity pilot is invalid; see {}".format(output))
    print("affinity pilot: PASS ({})".format(output))
    return 0


def run_cooldown_pilot(args: argparse.Namespace) -> int:
    """Select the smallest cooldown using a predeclared short-run gate."""
    workloads = load_workloads(args.target, args.firmware)
    if args.cpu is None:
        raise ValueError("cooldown-pilot requires --cpu")
    if args.replicates != COOLDOWN_PILOT_REPLICATES:
        raise ValueError(
            "cooldown-pilot fixes --replicates at {}".format(
                COOLDOWN_PILOT_REPLICATES
            )
        )
    if type(args.cycles) is not int or args.cycles <= 0:
        raise ValueError("cooldown-pilot requires positive --cycles")
    calibration_workload = next(
        (workload for workload in workloads if workload["id"].startswith("picotetris-")),
        None,
    )
    if calibration_workload is None:
        raise ValueError("cooldown-pilot requires the registered PicoTetris workload")
    identity = clean_backend_identity(args.backend)
    validate_runner_embedded_commit(args.runner, identity["commit"])
    output = args.output.resolve()
    _refuse_existing(output)
    original = _set_cpu_affinity(args.cpu)
    rows: List[Dict[str, Any]] = []
    error_text: Optional[str] = None
    try:
        for cooldown in COOLDOWN_PILOT_VALUES:
            for replicate in range(1, args.replicates + 1):
                row = _run_short_pilot_guest(
                    calibration_workload, args.backend, args.runner, identity,
                    args.cycles, affinity_mode="pinned-vcpu", cpu=args.cpu,
                )
                row["cooldown_seconds"] = cooldown
                row["replicate"] = replicate
                rows.append(row)
                if cooldown > 0.0 and replicate < args.replicates:
                    _sleep_between_runs(cooldown)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        error_text = str(error)
    finally:
        _restore_cpu_affinity(original)
    groups: Dict[str, Any] = {}
    for cooldown in COOLDOWN_PILOT_VALUES:
        group = [
            row for row in rows
            if row.get("cooldown_seconds") == cooldown
        ]
        cpu_values = [row["cycles_per_emulation_cpu_second"] for row in group]
        ratio_values = [
            row["emulation_cpu_seconds"] / row["emulation_wall_seconds"]
            for row in group
        ]
        groups[str(int(cooldown))] = {
            "replicates": len(group),
            "cpu_throughput": (
                _pilot_dispersion(cpu_values) if cpu_values else None
            ),
            "cpu_wall_ratio": (
                _pilot_dispersion(ratio_values) if ratio_values else None
            ),
            "observations": sorted(
                {row.get("guest_observation_sha256") for row in group}
            ),
        }
    zero = groups["0"].get("cpu_wall_ratio")
    zero_median = zero.get("median") if isinstance(zero, Mapping) else None
    for key, summary in groups.items():
        ratio = summary.get("cpu_wall_ratio")
        throughput = summary.get("cpu_throughput")
        gates = {
            "replicate_count": summary["replicates"] == args.replicates,
            "cpu_relative_mad_le_2pct": (
                isinstance(throughput, Mapping)
                and throughput.get("relative_mad") is not None
                and throughput["relative_mad"] <= COOLDOWN_PILOT_CPU_RELATIVE_MAD_LIMIT
            ),
            "cpu_wall_ratio_vs_zero_le_2pct": (
                isinstance(ratio, Mapping)
                and zero_median is not None
                and abs(ratio["median"] / zero_median - 1.0)
                <= COOLDOWN_PILOT_CPU_WALL_RATIO_LIMIT
            ),
            "projection_equal": len(summary["observations"]) == 1,
        }
        summary["gates"] = gates
        summary["valid"] = all(gates.values())
    selected_key = next(
        (key for key in ("0", "5", "15", "60") if groups[key]["valid"]),
        None,
    )
    valid = error_text is None and selected_key is not None
    record = {
        "schema_id": "picocalc.rp2040-cpu-cooldown-pilot",
        "schema_version": 1,
        "artifact_type": "cooldown-pilot",
        "record_id": args.batch_id or output.stem,
        "status": "pass" if valid else "invalid",
        "measurement_policy": {
            "method": "short-fixed-cycle-cooldown-pilot-v1",
            "cycles_per_run": args.cycles,
            "cooldowns_seconds": list(COOLDOWN_PILOT_VALUES),
            "replicates_per_cooldown": args.replicates,
            "affinity": "pinned-vcpu",
            "measurement_cpu": args.cpu,
            "selection_rule": (
                "smallest cooldown satisfying replicate count, CPU relative MAD "
                "<=2%, CPU/wall ratio within 2% of zero-cooldown, and projection "
                "equality; fixed before observation"
            ),
            "cpu_relative_mad_limit": COOLDOWN_PILOT_CPU_RELATIVE_MAD_LIMIT,
            "cpu_wall_ratio_limit": COOLDOWN_PILOT_CPU_WALL_RATIO_LIMIT,
        },
        "backend_identity": identity,
        "runner_sha256": sha256_file(args.runner),
        "workload": {
            key: calibration_workload[key]
            for key in (
                "id", "revision", "firmware_sha256", "scenario_sha256",
                "contract_sha256",
            )
        },
        "rows": rows,
        "summary": groups,
        "selected_cooldown_seconds": (
            float(selected_key) if selected_key is not None else None
        ),
        "reasons": [] if error_text is None else [error_text],
    }
    _write_json_once(output, record)
    if not valid:
        raise ValueError("cooldown pilot is invalid; see {}".format(output))
    print(
        "cooldown pilot: PASS (selected {}s; {})".format(
            record["selected_cooldown_seconds"], output
        )
    )
    return 0


def _short_block_pair_results(
    rows: Sequence[Mapping[str, Any]],
    pair_indices: Sequence[int],
    workloads: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Derive CPU-primary and wall-secondary ratios for one fixed block."""
    result: List[Dict[str, Any]] = []
    for pair in pair_indices:
        for workload in workloads:
            selected = [
                row for row in rows
                if row.get("kind") == "run"
                and row.get("pair") == pair
                and row.get("workload") == workload["id"]
            ]
            by_role = {row.get("role"): row for row in selected}
            if set(by_role) != {"baseline", "candidate"}:
                raise ValueError(
                    "short block pair is missing baseline/candidate for {} pair {}".format(
                        workload["id"], pair
                    )
                )
            baseline = by_role["baseline"]
            candidate = by_role["candidate"]
            baseline_cpu = baseline.get("cycles_per_emulation_cpu_second")
            candidate_cpu = candidate.get("cycles_per_emulation_cpu_second")
            baseline_wall = baseline.get("cycles_per_emulation_wall_second")
            candidate_wall = candidate.get("cycles_per_emulation_wall_second")
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) <= 0
                for value in (baseline_cpu, candidate_cpu, baseline_wall, candidate_wall)
            ):
                raise ValueError("short block throughput is invalid")
            result.append(
                {
                    "workload": workload["id"],
                    "pair_index": pair,
                    "order": baseline.get("order"),
                    "run_ids": [baseline.get("run_id"), candidate.get("run_id")],
                    "cpu_primary_log_ratio": log_ratio(float(candidate_cpu), float(baseline_cpu)),
                    "wall_secondary_log_ratio": log_ratio(float(candidate_wall), float(baseline_wall)),
                    "pair_log_ratio": log_ratio(float(candidate_cpu), float(baseline_cpu)),
                    "baseline_guest_observation_sha256": baseline.get("guest_observation_sha256"),
                    "candidate_guest_observation_sha256": candidate.get("guest_observation_sha256"),
                    "guest_observation_equal": (
                        baseline.get("guest_observation_sha256")
                        == candidate.get("guest_observation_sha256")
                    ),
                }
            )
    return result


def run_short_block(args: argparse.Namespace) -> int:
    """Run the fixed five-block short CPU-time A/B screening protocol.

    Each run is a real registered application firmware execution with a short
    cycle limit.  It is intentionally a screening/diagnostic record: the
    CPU-time effect is measured and retained, while promotion still requires
    the full registered production A/B protocol.
    """
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("short-block requires exactly the two registered workloads")
    if args.cpu is None:
        raise ValueError("short-block requires --cpu")
    if args.replicates != SHORT_BLOCK_ANCHOR_REPLICATES:
        raise ValueError(
            "short-block fixes --replicates at {}".format(SHORT_BLOCK_ANCHOR_REPLICATES)
        )
    if type(args.cycles) is not int or args.cycles <= 0:
        raise ValueError("short-block requires positive --cycles")
    cooldown = float(args.inter_run_cooldown_seconds)
    if not math.isfinite(cooldown) or cooldown != SHORT_BLOCK_COOLDOWN_SECONDS:
        raise ValueError(
            "short-block fixes --inter-run-cooldown-seconds at {}".format(
                SHORT_BLOCK_COOLDOWN_SECONDS
            )
        )
    if args.final_report_only and args.candidate_id != "P0-A2":
        raise ValueError("--final-report-only is reserved for candidate_id P0-A2")

    identities = preflight_backends(
        [args.baseline_backend, args.candidate_backend],
        [args.baseline_runner, args.candidate_runner],
        labels=("baseline_production", "candidate_production"),
        feature_sets=((), getattr(args, "feature_set", [])),
        allow_production_role=(
            args.candidate_id == "P0-A2"
            and args.baseline_runner.resolve() == args.candidate_runner.resolve()
        ),
    )
    _require_admission_gate(args.admission_record, workloads, identities["baseline_production"])
    correctness_record = getattr(args, "correctness_record", None)
    if correctness_record is not None:
        _require_correctness_gate(
            correctness_record,
            workloads,
            identities,
            required_trace=not args.final_report_only,
        )

    record_root = args.output.resolve()
    _validate_record_root(record_root)
    batch_id = args.batch_id or record_root.name
    _validate_batch_id(record_root, batch_id)
    short_dir = record_root / "short-block"
    _refuse_existing_files(short_dir)
    for aggregate in (record_root / "summary.json", record_root / "decision.md", record_root / "short-block" / "record.json"):
        _refuse_existing(aggregate)
    policy = {
        "method": "short-fixed-cycle-five-block-cpu-time-v1",
        "cycles_per_run": args.cycles,
        "block_count": SHORT_BLOCK_COUNT,
        "pairs_per_block": SHORT_BLOCK_PAIRS,
        "pairs": SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS,
        "anchor_replicates_per_boundary": SHORT_BLOCK_ANCHOR_REPLICATES,
        "anchor_boundaries_per_block": ["pre", "post"],
        "inter_run_cooldown_seconds": SHORT_BLOCK_COOLDOWN_SECONDS,
        "primary_metric": "cycles_per_emulation_cpu_second",
        "secondary_metric": "cycles_per_emulation_wall_second",
        "anchor_relative_mad_limit": SHORT_BLOCK_ANCHOR_MAD_LIMIT,
        "anchor_pre_post_drift_limit": SHORT_BLOCK_ANCHOR_DRIFT_LIMIT,
        "diagnostic_only": True,
        "promotion_requires_full_production_ab": True,
    }
    manifest_identity = _base_manifest(
        batch_id,
        workloads,
        identities,
        candidate_id=args.candidate_id,
        cpu=args.cpu,
        feature_set=getattr(args, "feature_set", []),
    )
    manifest_identity["short_block_policy"] = policy
    if correctness_record is not None:
        manifest_identity["correctness_record"] = correctness_record.resolve().name
    _record_manifest(record_root, manifest_identity)
    decision_context = _manifest_decision_context(
        record_root, workloads, identities,
        feature_set=getattr(args, "feature_set", []),
    )
    blocks = make_short_block_schedule([workload["id"] for workload in workloads])
    calibration_workload = next(
        workload for workload in workloads if workload["id"].startswith("picotetris-")
    )
    by_id = {workload["id"]: workload for workload in workloads}
    rows: List[Dict[str, Any]] = []
    error_text: Optional[str] = None
    before = _set_cpu_affinity(args.cpu)
    try:
        for block in blocks:
            for anchor_id in block["pre_anchor_ids"]:
                row = _run_short_pilot_guest(
                    calibration_workload,
                    args.baseline_backend,
                    args.baseline_runner,
                    identities["baseline_production"],
                    args.cycles,
                    affinity_mode="pinned-vcpu",
                    cpu=args.cpu,
                )
                row.update(
                    {
                        "kind": "anchor",
                        "anchor_id": anchor_id,
                        "anchor_position": "pre",
                        "block_index": block["block_index"],
                        "workload": calibration_workload["id"],
                        "role": "baseline",
                    }
                )
                rows.append(row)
                _sleep_between_runs(cooldown)
            for item in block["runs"]:
                role = item["role"]
                identity = identities["{}_production".format(role)]
                row = _run_short_pilot_guest(
                    by_id[item["workload"]],
                    args.baseline_backend if role == "baseline" else args.candidate_backend,
                    args.baseline_runner if role == "baseline" else args.candidate_runner,
                    identity,
                    args.cycles,
                    affinity_mode="pinned-vcpu",
                    cpu=args.cpu,
                )
                row.update({"kind": "run", **item})
                rows.append(row)
                _sleep_between_runs(cooldown)
            for anchor_id in block["post_anchor_ids"]:
                row = _run_short_pilot_guest(
                    calibration_workload,
                    args.baseline_backend,
                    args.baseline_runner,
                    identities["baseline_production"],
                    args.cycles,
                    affinity_mode="pinned-vcpu",
                    cpu=args.cpu,
                )
                row.update(
                    {
                        "kind": "anchor",
                        "anchor_id": anchor_id,
                        "anchor_position": "post",
                        "block_index": block["block_index"],
                        "workload": calibration_workload["id"],
                        "role": "baseline",
                    }
                )
                rows.append(row)
                _sleep_between_runs(cooldown)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        error_text = str(error)
    finally:
        _restore_cpu_affinity(before)

    run_rows = [row for row in rows if row.get("kind") == "run"]
    anchor_rows = [row for row in rows if row.get("kind") == "anchor"]
    block_summaries: List[Dict[str, Any]] = []
    pair_results: List[Dict[str, Any]] = []
    for block in blocks:
        block_rows = [row for row in rows if row.get("block_index") == block["block_index"]]
        pre = [row for row in block_rows if row.get("anchor_position") == "pre"]
        post = [row for row in block_rows if row.get("anchor_position") == "post"]
        try:
            pre_cpu = _pilot_dispersion([row["cycles_per_emulation_cpu_second"] for row in pre])
            post_cpu = _pilot_dispersion([row["cycles_per_emulation_cpu_second"] for row in post])
            pre_wall = _pilot_dispersion([row["cycles_per_emulation_wall_second"] for row in pre])
            post_wall = _pilot_dispersion([row["cycles_per_emulation_wall_second"] for row in post])
            block_pairs = _short_block_pair_results(block_rows, block["pair_indices"], workloads)
            pair_results.extend(block_pairs)
            drift = abs(post_cpu["median"] / pre_cpu["median"] - 1.0)
            observations = {row.get("guest_observation_sha256") for row in block_rows}
            block_valid = (
                len(pre) == args.replicates
                and len(post) == args.replicates
                and pre_cpu["relative_mad"] <= SHORT_BLOCK_ANCHOR_MAD_LIMIT
                and post_cpu["relative_mad"] <= SHORT_BLOCK_ANCHOR_MAD_LIMIT
                and drift <= SHORT_BLOCK_ANCHOR_DRIFT_LIMIT
                and all(item["guest_observation_equal"] is True for item in block_pairs)
            )
            block_summaries.append(
                {
                    "block_id": block["block_id"],
                    "block_index": block["block_index"],
                    "pair_indices": block["pair_indices"],
                    "pre_anchor_cpu": pre_cpu,
                    "post_anchor_cpu": post_cpu,
                    "pre_anchor_wall": pre_wall,
                    "post_anchor_wall": post_wall,
                    "pre_post_cpu_relative_drift": drift,
                    "guest_observation_count": len(observations),
                    "pair_results": block_pairs,
                    "valid": block_valid,
                }
            )
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
            block_summaries.append(
                {
                    "block_id": block["block_id"],
                    "block_index": block["block_index"],
                    "pair_indices": block["pair_indices"],
                    "valid": False,
                    "error": str(error),
                }
            )
    workload_effects: Dict[str, Any] = {}
    for workload in workloads:
        values = [
            float(item["cpu_primary_log_ratio"])
            for item in pair_results
            if item.get("workload") == workload["id"]
        ]
        workload_effects[workload["id"]] = (
            summarize_log_effect(values) if len(values) == SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS else {"n": len(values)}
        )
    by_pair: Dict[int, List[float]] = {}
    for item in pair_results:
        by_pair.setdefault(int(item["pair_index"]), []).append(float(item["cpu_primary_log_ratio"]))
    combined_values = [statistics.mean(by_pair[pair]) for pair in sorted(by_pair) if len(by_pair[pair]) == len(workloads)]
    combined = (
        summarize_log_effect(combined_values)
        if len(combined_values) == SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS
        else {"n": len(combined_values)}
    )
    expected_rows = SHORT_BLOCK_COUNT * SHORT_BLOCK_PAIRS * len(workloads) * 2
    expected_anchors = SHORT_BLOCK_COUNT * 2 * SHORT_BLOCK_ANCHOR_REPLICATES
    protocol_valid = (
        error_text is None
        and len(run_rows) == expected_rows
        and len(anchor_rows) == expected_anchors
        and len(block_summaries) == SHORT_BLOCK_COUNT
        and all(block.get("valid") is True for block in block_summaries)
        and all(item.get("guest_observation_equal") is True for item in pair_results)
    )
    reasons = [] if error_text is None else [error_text]
    if len(run_rows) != expected_rows:
        reasons.append("expected {} measured rows, got {}".format(expected_rows, len(run_rows)))
    if len(anchor_rows) != expected_anchors:
        reasons.append("expected {} anchor rows, got {}".format(expected_anchors, len(anchor_rows)))
    if any(block.get("valid") is not True for block in block_summaries):
        reasons.append("one or more block anchor/projection gates failed")
    result_record = {
        "schema_id": SHORT_BLOCK_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "short-block-ab",
        "record_id": batch_id,
        "candidate_id": args.candidate_id,
        "status": "pass" if protocol_valid else "invalid",
        "measurement_policy": policy,
        "measurement_cpu": args.cpu,
        "backend_identities": identities,
        "workloads": _workload_manifest_entries(workloads),
        "correctness_record": correctness_record.resolve().name if correctness_record is not None else None,
        "rows": rows,
        "blocks": block_summaries,
        "summary": {"workloads": workload_effects, "combined": combined},
        "pair_results": pair_results,
        "reasons": reasons,
    }
    short_dir.mkdir(parents=True, exist_ok=True)
    _write_json_once(short_dir / "record.json", result_record)
    _write_json_once(
        record_root / "summary.json",
        {
            "schema_id": SHORT_BLOCK_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "short-block-summary",
            "record_id": batch_id,
            "candidate_id": args.candidate_id,
            "status": result_record["status"],
            "measurement_policy": policy,
            "blocks": block_summaries,
            "workloads": workload_effects,
            "combined": combined,
            "pair_results": pair_results,
            "reasons": reasons,
        },
    )
    _write_json_replace(
        record_root / "decision.json",
        {
            "schema_id": DECISION_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "record_id": batch_id,
            "candidate_id": args.candidate_id,
            "decision_kind": "performance" if protocol_valid else "invalid",
            "status": "pending" if protocol_valid else "invalid",
            "correctness": (
                {"status": "pass", "source": correctness_record.resolve().name}
                if correctness_record is not None
                else {"status": "not_run"}
            ),
            "statistics": result_record["summary"],
            "reasons": reasons,
            **decision_context,
        },
    )
    _write_text_once(
        record_root / "decision.md",
        "# RP2040 CPU short-block decision\n\n"
        + ("Protocol gates passed; full production A/B remains required for promotion.\n"
           if protocol_valid else "Short-block protocol was invalid; see summary.json.\n"),
    )
    _write_sha256sums_once(record_root)
    if not protocol_valid:
        raise ValueError("short-block protocol is invalid; see {}".format(record_root))
    print("short-block CPU-time diagnostic: PASS ({})".format(record_root))
    return 0


def run_load_shape(args: argparse.Namespace) -> int:
    """Measure independent guest scaling without making an A/B decision."""
    workloads = load_workloads(args.target, args.firmware)
    calibration_workload = next(
        (workload for workload in workloads if workload["id"].startswith("picotetris-")),
        None,
    )
    if calibration_workload is None:
        raise ValueError("load-shape requires the registered PicoTetris workload")
    if type(args.cycles) is not int or args.cycles <= 0:
        raise ValueError("load-shape requires positive --cycles")
    identity = clean_backend_identity(args.backend)
    validate_runner_embedded_commit(args.runner, identity["commit"])
    output = args.output.resolve()
    _refuse_existing(output)
    if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
        raise ValueError("load-shape needs Linux sched_getaffinity/sched_setaffinity")
    available_cpus = sorted(os.sched_getaffinity(0))
    counts = tuple(count for count in LOAD_SHAPE_INSTANCE_COUNTS if count <= len(available_cpus))
    if not counts:
        raise ValueError("load-shape has no usable instance count for the allowed CPU set")
    host_start = host_cpu()
    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="picocalc-rp2040-load-shape-") as temporary:
        root = Path(temporary)
        for count in counts:
            processes: List[Tuple[subprocess.Popen[bytes], Path, Path, int]] = []
            batch_started_ns = time.perf_counter_ns()
            try:
                for index, cpu in enumerate(available_cpus[:count], 1):
                    report_path = root / "k{}-{:02d}-report.json".format(count, index)
                    uart_path = root / "k{}-{:02d}-uart.bin".format(count, index)
                    timing_path = root / "k{}-{:02d}-host-timing.json".format(count, index)
                    command = load_shape_command(
                        calibration_workload["target"],
                        calibration_workload["firmware"],
                        args.runner,
                        report_path,
                        uart_path,
                        timing_path,
                        args.cycles,
                        backend_commit=identity["commit"],
                    )
                    process = subprocess.Popen(
                        command,
                        cwd=str(args.backend),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        preexec_fn=_child_affinity_setter(cpu),
                    )
                    processes.append((process, report_path, timing_path, cpu))
                instance_records = []
                for process, report_path, timing_path, cpu in processes:
                    process.wait()
                    instance_records.append(
                        _load_shape_run_record(
                            process, report_path, timing_path, cpu, args.cycles
                        )
                    )
            except BaseException:
                for process, _, _, _ in processes:
                    if process.poll() is None:
                        process.kill()
                for process, _, _, _ in processes:
                    process.wait()
                raise
            batch_wall_ns = time.perf_counter_ns() - batch_started_ns
            total_cpu_seconds = sum(item["emulation_cpu_seconds"] for item in instance_records)
            total_cycles = sum(item["cycles"] for item in instance_records)
            batch_wall_seconds = batch_wall_ns / 1_000_000_000
            observations = {item["guest_observation_sha256"] for item in instance_records}
            if len(observations) != 1:
                raise ValueError("load-shape guest observations differ at K={}".format(count))
            results.append(
                {
                    "instance_count": count,
                    "assigned_cpus": available_cpus[:count],
                    "instances": instance_records,
                    "batch_wall_ns": batch_wall_ns,
                    "batch_wall_seconds": batch_wall_seconds,
                    "aggregate_cycles": total_cycles,
                    "aggregate_emulation_cpu_seconds": total_cpu_seconds,
                    "aggregate_cycles_per_cpu_second": total_cycles / total_cpu_seconds,
                    "aggregate_cycles_per_batch_wall_second": total_cycles / batch_wall_seconds,
                    "normalized_host_cpu_fraction": (
                        total_cpu_seconds / batch_wall_seconds / len(available_cpus)
                    ),
                    "guest_observation_sha256": next(iter(observations)),
                }
            )
    host_end = host_cpu()
    record = {
        "schema_id": "picocalc.rp2040-cpu-load-shape",
        "schema_version": 1,
        "artifact_type": "load-shape",
        "record_id": args.batch_id or output.stem,
        "status": "pass",
        "measurement_policy": {
            "method": "independent-guest-load-shape-v1",
            "instance_counts": list(LOAD_SHAPE_INSTANCE_COUNTS),
            "cycles_per_instance": args.cycles,
            "single_guest_promotion_metric": "cycles_per_emulation_cpu_second",
            "scaling_is_diagnostic_only": True,
        },
        "measurement_cpus": available_cpus,
        "workload": {
            key: calibration_workload[key]
            for key in ("id", "revision", "firmware_sha256", "scenario_sha256", "contract_sha256")
        },
        "backend_identity": identity,
        "runner_sha256": sha256_file(args.runner),
        "host_snapshot_start": host_start,
        "host_snapshot_end": host_end,
        "results": results,
    }
    _write_json_once(output, record)
    print("load-shape diagnostic: PASS ({})".format(output))
    return 0


def run_host_stability_preflight(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("stability-preflight requires exactly the two registered workloads")
    if args.cpu is None:
        raise ValueError("stability-preflight requires --cpu for affinity pinning")
    protocol_version = getattr(args, "protocol_version", 2)
    requested_primary_metric = getattr(args, "primary_metric", None)
    primary_metric = requested_primary_metric or "wall-time"
    metric_fields = primary_metric_fields(primary_metric)
    policy = host_stability_measurement_policy_for_version(
        protocol_version,
        primary_metric=requested_primary_metric,
    )
    warmup = HOST_STABILITY_WARMUP_RUNS if args.warmup is None else args.warmup
    runs = int(policy["measured_runs"]) if args.runs is None else args.runs
    if warmup != int(policy["warmup_runs"]):
        raise ValueError("stability-preflight fixes --warmup at {}".format(policy["warmup_runs"]))
    if runs != int(policy["measured_runs"]):
        raise ValueError("stability-preflight fixes --runs at {}".format(policy["measured_runs"]))
    cooldown = validate_inter_run_cooldown(args.inter_run_cooldown_seconds)
    calibration_workload = next(
        (workload for workload in workloads if workload["id"].startswith("picotetris-")),
        None,
    )
    if calibration_workload is None:
        raise ValueError("stability-preflight requires the registered PicoTetris workload")
    identity = _host_stability_identity(args.backend, args.runner, getattr(args, "feature_set", []))
    _require_admission_gate(args.admission_record, workloads, identity)
    output = args.output.resolve()
    _refuse_existing(output)
    before = _set_cpu_affinity(args.cpu)
    samples: List[Dict[str, Any]] = []
    error_text: Optional[str] = None
    try:
        for _ in range(warmup):
            run_guest(
                calibration_workload,
                args.backend,
                args.runner,
                expected_backend_identity=identity,
            )
            _sleep_between_runs(cooldown)
        for index in range(1, runs + 1):
            host_start = host_cpu()
            started_ns = time.perf_counter_ns()
            result = run_guest(
                calibration_workload,
                args.backend,
                args.runner,
                expected_backend_identity=identity,
            )
            ended_ns = time.perf_counter_ns()
            host_end = host_cpu()
            measurement = result["measurement"]
            sample = {
                "sample_id": "sentinel-{:03d}".format(index),
                "protocol_elapsed_seconds": (ended_ns - started_ns) / 1_000_000_000,
                "throughput": measurement[metric_fields["raw"]],
                "cycles": measurement["cycles"],
                "wall_seconds": measurement["wall_seconds"],
                "backend_commit": measurement["backend_commit"],
                "runner_sha256": measurement["runner_sha256"],
                "build_provenance_sha256": measurement["build_provenance_sha256"],
                "host_snapshot_start": host_start,
                "host_snapshot_end": host_end,
            }
            optional_measurements = {
                "emulation_wall_seconds": measurement.get("emulation_wall_seconds"),
                "emulation_cpu_seconds": measurement.get("emulation_cpu_seconds"),
                "cycles_per_emulation_wall_second": measurement.get(
                    "emulated_cycles_per_wall_second"
                ),
                "cycles_per_emulation_cpu_second": measurement.get(
                    "cycles_per_emulation_cpu_second"
                ),
            }
            sample.update(
                {
                    key: value
                    for key, value in optional_measurements.items()
                    if value is not None
                }
            )
            samples.append(sample)
            _sleep_between_runs(cooldown)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        error_text = str(error)
    finally:
        _restore_cpu_affinity(before)
    if len(samples) == runs:
        summarize = (
            summarize_host_stability
            if protocol_version == 1
            else summarize_host_stability_v2
            if protocol_version == 2
            else summarize_host_stability_v3
        )
        summary = summarize(
            samples,
            expected_cpu=args.cpu,
            expected_identity=identity,
        )
    else:
        summary = {
            "sample_count": len(samples),
            "gates": {"sample_count_valid": False},
            "valid": False,
        }
    record = {
        "schema_id": HOST_STABILITY_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "host-stability",
        "record_id": args.batch_id or output.stem,
        "status": "pass" if error_text is None and summary.get("valid") is True else "invalid",
        "measurement_policy": policy,
        "measurement_cpu": args.cpu,
        "cpu_affinity": {"requested": args.cpu, "effective": [args.cpu]},
        "inter_run_cooldown_seconds": cooldown,
        "workload": {
            key: calibration_workload[key]
            for key in ("id", "revision", "firmware_sha256", "scenario_sha256", "contract_sha256")
        },
        "backend_identity": identity,
        "samples": samples,
        "summary": summary,
        "reasons": (
            [
                "gate:{}".format(name)
                for name, passed in summary.get("gates", {}).items()
                if passed is not True
            ]
            if error_text is None
            else [error_text]
        ),
    }
    _write_json_once(output, record)
    if record["status"] != "pass":
        raise ValueError("host stability preflight is invalid; see {}".format(output))
    print("host-stability preflight: PASS ({})".format(output))
    return 0


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
    *, candidate_id: str, cpu: Optional[int], feature_set: Sequence[str] = (),
    measurement_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    all_features = set(effective_feature_set(feature_set))
    for identity in identities.values():
        if isinstance(identity, Mapping) and isinstance(identity.get("feature_set"), list):
            all_features.update(normalize_feature_set(identity["feature_set"]))
    manifest = {
        "record_id": batch_id,
        "candidate_id": candidate_id,
        "workloads": _workload_manifest_entries(workloads),
        "backend_identities": dict(identities),
        "feature_set": sorted(all_features),
        "host": host_cpu(),
        "measurement_cpu": cpu,
    }
    if measurement_policy is not None:
        manifest["measurement_policy"] = dict(measurement_policy)
    return manifest


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
    context = _decision_context(
        workloads, merged_identities, feature_set=merged_features,
    )
    if "measurement_policy" in manifest:
        context["measurement_policy"] = manifest["measurement_policy"]
    return context


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
    inter_run_cooldown_seconds: float = 0.0,
) -> List[float]:
    values = []
    for _ in range(count):
        measurement = run_guest(
            workload, backend, runner,
            expected_backend_identity=expected_backend_identity,
        )["measurement"]["emulated_cycles_per_wall_second"]
        values.append(measurement)
        _sleep_between_runs(inter_run_cooldown_seconds)
    return values


def _run_interleaved_anchor_ab(
    args: argparse.Namespace,
    workloads: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    record_root: Path,
    decision_context: Mapping[str, Any],
    measurement_policy: Mapping[str, Any],
) -> int:
    """Run the fixed 10-pair A/B with interleaved host-speed anchors."""
    calibration_method = measurement_policy.get("calibration_method")
    primary_metric = measurement_policy.get("primary_metric", "wall-time")
    metric_fields = primary_metric_fields(primary_metric)
    use_replicated_anchors = calibration_method in (
        CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2,
        CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3,
    )
    is_v3 = calibration_method == CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3
    anchor_after_runs = (
        INTERLEAVED_ANCHOR_V3_AFTER_RUNS
        if is_v3
        else INTERLEAVED_ANCHOR_AFTER_RUNS
    )
    group_specs = (
        _interleaved_anchor_v3_group_specs()
        if is_v3
        else _interleaved_anchor_v2_group_specs()
    )
    calibration_workload = next(
        (workload for workload in workloads if workload["id"].startswith("picotetris-")),
        None,
    )
    if calibration_workload is None:
        raise ValueError("ab requires a registered PicoTetris workload for calibration")
    by_id = {workload["id"]: workload for workload in workloads}
    schedule = make_ab_schedule([workload["id"] for workload in workloads], args.pairs)
    anchors: List[Dict[str, Any]] = []
    measured: List[Dict[str, Any]] = []
    summary_written = False
    before = _set_cpu_affinity(args.cpu)
    try:
        for _ in range(args.warmup):
            for workload in workloads:
                warmup_backend = args.baseline_backend
                warmup_runner = args.baseline_runner
                warmup_identity = identities["baseline_production"]
                run_guest(
                    workload,
                    warmup_backend,
                    warmup_runner,
                    expected_backend_identity=warmup_identity,
                )
                _sleep_between_runs(args.inter_run_cooldown_seconds)
                run_guest(
                    workload,
                    args.candidate_backend,
                    args.candidate_runner,
                    expected_backend_identity=identities["candidate_production"],
                )
                _sleep_between_runs(args.inter_run_cooldown_seconds)
        host_snapshot_start = host_cpu()
        protocol_start_ns = time.perf_counter_ns()
        if host_snapshot_start.get("allowed_cpus") != [args.cpu]:
            raise ValueError("interleaved-anchor protocol did not retain requested CPU affinity")

        def run_anchor(
            anchor_id: str,
            position: str,
            after_measured_run: int,
            group_id: Optional[str] = None,
            replicate_index: Optional[int] = None,
        ) -> None:
            started_ns = time.perf_counter_ns()
            result = run_guest(
                calibration_workload,
                args.baseline_backend,
                args.baseline_runner,
                expected_backend_identity=identities["baseline_production"],
            )
            ended_ns = time.perf_counter_ns()
            measurement = result["measurement"]
            anchor = {
                "anchor_id": anchor_id,
                "position": position,
                "after_measured_run": after_measured_run,
                "workload": calibration_workload["id"],
                "role": "baseline",
                "elapsed_seconds": _anchor_elapsed_seconds(
                    started_ns, ended_ns, protocol_start_ns
                ),
                # ``throughput`` is the metric used by the fixed calibration
                # model.  Keep both clocks in every anchor so a CPU-primary
                # result remains auditable against wall-time diagnostics.
                "throughput": measurement[metric_fields["raw"]],
                "cpu_throughput": measurement["cycles_per_emulation_cpu_second"],
                "wall_throughput": measurement["emulated_cycles_per_wall_second"],
                "cycles": measurement["cycles"],
                "wall_seconds": measurement["wall_seconds"],
                "guest_observation_sha256": measurement["guest_observation_sha256"],
                "backend_commit": measurement["backend_commit"],
                "runner_sha256": measurement["runner_sha256"],
                "build_provenance_sha256": measurement["build_provenance_sha256"],
            }
            if group_id is not None:
                anchor["group_id"] = group_id
            if replicate_index is not None:
                anchor["replicate_index"] = replicate_index
            anchors.append(anchor)
            _sleep_between_runs(args.inter_run_cooldown_seconds)

        def run_measured(item: Mapping[str, Any]) -> None:
            workload = by_id[item["workload"]]
            backend = args.baseline_backend if item["role"] == "baseline" else args.candidate_backend
            runner = args.baseline_runner if item["role"] == "baseline" else args.candidate_runner
            started_ns = time.perf_counter_ns()
            result = run_guest(
                workload,
                backend,
                runner,
                expected_backend_identity=identities["{}_production".format(item["role"])],
            )
            ended_ns = time.perf_counter_ns()
            measured.append(
                {
                    "item": dict(item),
                    "measurement": result["measurement"],
                    "elapsed_seconds": _anchor_elapsed_seconds(
                        started_ns, ended_ns, protocol_start_ns
                    ),
                }
            )
            _sleep_between_runs(args.inter_run_cooldown_seconds)

        if use_replicated_anchors:
            for index in range(1, args.calibration_runs + 1):
                run_anchor(
                    "anchor-pre-{:03d}".format(index),
                    "pre",
                    0,
                    group_id="pre",
                    replicate_index=index,
                )
        else:
            for index in range(1, args.calibration_runs + 1):
                run_anchor(
                    "anchor-pre-{:03d}".format(index),
                    "pre",
                    0,
                )
        for measured_index, item in enumerate(schedule, 1):
            run_measured(item)
            if measured_index in anchor_after_runs:
                if use_replicated_anchors:
                    group_id = "after-{:03d}".format(measured_index)
                    for index in range(1, args.calibration_runs + 1):
                        run_anchor(
                            "anchor-{}-{:03d}".format(group_id, index),
                            "after-measured-run",
                            measured_index,
                            group_id=group_id,
                            replicate_index=index,
                        )
                else:
                    run_anchor(
                        "anchor-after-{:03d}".format(measured_index),
                        "after-measured-run",
                        measured_index,
                    )
        if use_replicated_anchors:
            for index in range(1, args.calibration_runs + 1):
                run_anchor(
                    "anchor-post-{:03d}".format(index),
                    "post",
                    len(schedule),
                    group_id="post",
                    replicate_index=index,
                )
        else:
            for index in range(1, args.calibration_runs + 1):
                run_anchor(
                    "anchor-post-{:03d}".format(index),
                    "post",
                    len(schedule),
                )
        host_snapshot_end = host_cpu()

        expected_anchor_ids = measurement_policy["anchor_run_ids"]
        actual_anchor_ids = [anchor["anchor_id"] for anchor in anchors]
        if actual_anchor_ids != expected_anchor_ids:
            raise ValueError(
                "interleaved-anchor protocol produced unexpected anchor IDs: {} != {}".format(
                    actual_anchor_ids, expected_anchor_ids
                )
            )
        if use_replicated_anchors and len({anchor["guest_observation_sha256"] for anchor in anchors}) != 1:
            raise ValueError("replicated calibration anchors disagree on guest observation")
        if len(measured) != len(schedule):
            raise ValueError("interleaved-anchor protocol did not collect all measured runs")
        model_anchors = anchors
        anchor_groups: List[Dict[str, Any]] = []
        if use_replicated_anchors:
            anchor_groups = _aggregate_anchor_groups(anchors, group_specs)
            model_anchors = anchor_groups
        if is_v3:
            model = _anchor_piecewise_local_residual_model(model_anchors)
        else:
            model = _anchor_log_linear_model(
                model_anchors,
                model_name=(
                    "global-log-linear-v2"
                    if use_replicated_anchors
                    else "global-log-linear-v1"
                ),
            )
        reference_throughput = model["reference_throughput"]
        leaves: List[Dict[str, Any]] = []
        for item in measured:
            measurement = dict(item["measurement"])
            predicted = interpolate_anchor_throughput(model_anchors, item["elapsed_seconds"])
            correction = reference_throughput / predicted
            raw_throughput = measurement[metric_fields["raw"]]
            corrected_throughput = raw_throughput * correction
            leaf = {
                "schema_id": AB_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": args.batch_id,
                "candidate_id": args.candidate_id,
                "artifact_type": "run",
                **item["item"],
                **measurement,
                "protocol_elapsed_seconds": item["elapsed_seconds"],
                metric_fields["predicted"]: predicted,
                "host_speed_correction": correction,
                "corrected_emulated_cycles_per_wall_second": (
                    measurement["emulated_cycles_per_wall_second"] * correction
                ),
                "corrected_emulated_cycles_per_cpu_second": (
                    measurement["cycles_per_emulation_cpu_second"] * correction
                ),
                "primary_metric": primary_metric,
                "primary_throughput": raw_throughput,
                "corrected_primary_throughput": corrected_throughput,
            }
            leaves.append(leaf)
        for leaf in leaves:
            _write_json_once(record_root / "ab" / "{}.json".format(leaf["run_id"]), leaf)

        grouped: Dict[str, Dict[int, Dict[str, Mapping[str, Any]]]] = {}
        for leaf in leaves:
            grouped.setdefault(leaf["workload"], {}).setdefault(leaf["pair"], {})[leaf["role"]] = leaf
        summaries: Dict[str, Any] = {}
        combined_raw: List[float] = []
        pair_results: List[Dict[str, Any]] = []
        for workload in workloads:
            workload_id = workload["id"]
            ratios: List[float] = []
            for pair in range(1, args.pairs + 1):
                values = grouped[workload_id][pair]
                raw_ratio = log_ratio(
                    values["candidate"]["primary_throughput"],
                    values["baseline"]["primary_throughput"],
                )
                corrected_ratio = log_ratio(
                    values["candidate"]["corrected_primary_throughput"],
                    values["baseline"]["corrected_primary_throughput"],
                )
                wall_raw_ratio = log_ratio(
                    values["candidate"]["emulated_cycles_per_wall_second"],
                    values["baseline"]["emulated_cycles_per_wall_second"],
                )
                cpu_raw_ratio = log_ratio(
                    values["candidate"]["cycles_per_emulation_cpu_second"],
                    values["baseline"]["cycles_per_emulation_cpu_second"],
                )
                wall_corrected_ratio = log_ratio(
                    values["candidate"]["corrected_emulated_cycles_per_wall_second"],
                    values["baseline"]["corrected_emulated_cycles_per_wall_second"],
                )
                cpu_corrected_ratio = log_ratio(
                    values["candidate"]["corrected_emulated_cycles_per_cpu_second"],
                    values["baseline"]["corrected_emulated_cycles_per_cpu_second"],
                )
                ratios.append(raw_ratio)
                pair_results.append(
                    {
                        "workload": workload_id,
                        "pair_index": pair,
                        "order": values["baseline"]["order"],
                        "run_ids": [values["baseline"]["run_id"], values["candidate"]["run_id"]],
                        "pair_log_ratio": raw_ratio,
                        "corrected_pair_log_ratio": corrected_ratio,
                        "primary_metric": primary_metric,
                        "wall_pair_log_ratio": wall_raw_ratio,
                        "cpu_pair_log_ratio": cpu_raw_ratio,
                        "wall_corrected_pair_log_ratio": wall_corrected_ratio,
                        "cpu_corrected_pair_log_ratio": cpu_corrected_ratio,
                        "baseline_guest_observation_sha256": values["baseline"]["guest_observation_sha256"],
                        "candidate_guest_observation_sha256": values["candidate"]["guest_observation_sha256"],
                        "guest_observation_equal": (
                            values["baseline"]["guest_observation_sha256"]
                            == values["candidate"]["guest_observation_sha256"]
                        ),
                    }
                )
            summaries[workload_id] = summarize_log_effect(ratios)
        pair_sensitivity = _pair_level_sensitivity(pair_results)
        pair_sensitivity_valid = (
            pair_sensitivity["max_abs_delta_log_ratio"]
            <= CALIBRATION_PAIR_SENSITIVITY_LIMIT
        )
        # Combined effect is the equal-weight mean of the two workloads at
        # each pair index (10 values), not the 20 workload-specific ratios.
        combined_raw = [
            statistics.mean(
                float(item["pair_log_ratio"])
                for item in pair_results
                if item["pair_index"] == pair
            )
            for pair in range(1, args.pairs + 1)
        ]
        if use_replicated_anchors:
            anchor_drift = calibration_drift(
                [anchor_groups[0]["throughput"]],
                [anchor_groups[-1]["throughput"]],
            )
        else:
            anchor_drift = calibration_drift(
                [anchor["throughput"] for anchor in anchors[: args.calibration_runs]],
                [anchor["throughput"] for anchor in anchors[-args.calibration_runs :]],
            )
        null_control: Optional[Dict[str, Any]] = None
        if args.candidate_id == "P0-A2":
            null_control = evaluate_null_control(
                pair_results, [workload["id"] for workload in workloads]
            )
        calibration = {
            "method": calibration_method,
            "anchor_count": len(anchors),
            "anchor_run_ids": actual_anchor_ids,
            "anchors": anchors,
            "anchor_model": model,
            "pre_post_relative_drift": anchor_drift["relative_drift"],
            "pre_post_drift_gate_used": False,
            "global_residual_diagnostic_only": True,
            "host_snapshot_start": host_snapshot_start,
            "host_snapshot_end": host_snapshot_end,
            "cpu_affinity": {
                "requested": args.cpu,
                "effective_start": host_snapshot_start.get("allowed_cpus"),
                "effective_end": host_snapshot_end.get("allowed_cpus"),
            },
            "correctness_gate": "pass",
            "pair_level_sensitivity": pair_sensitivity,
            "valid": model["valid"],
        }
        if use_replicated_anchors:
            calibration["anchor_group_count"] = len(anchor_groups)
            calibration["anchor_group_ids"] = [group["group_id"] for group in anchor_groups]
            calibration["anchor_groups"] = anchor_groups
            calibration["anchor_group_dispersion_gate_used"] = True
            calibration["anchor_group_dispersion_threshold"] = CALIBRATION_ANCHOR_GROUP_MAD_LIMIT
            calibration["anchor_group_dispersion_valid"] = all(
                group["dispersion_valid"] for group in anchor_groups
            )
            calibration["valid"] = bool(
                model["valid"] and calibration["anchor_group_dispersion_valid"]
            )
        if is_v3:
            calibration["anchor_local_residual_gate_used"] = True
            calibration["anchor_local_residual_threshold"] = CALIBRATION_ANCHOR_LOCAL_RESIDUAL_LIMIT
            calibration["anchor_local_residual_valid"] = model["valid"]
            calibration["pair_level_sensitivity_gate_used"] = True
            calibration["pair_level_sensitivity_threshold"] = CALIBRATION_PAIR_SENSITIVITY_LIMIT
            calibration["pair_level_sensitivity_valid"] = pair_sensitivity_valid
            calibration["valid"] = bool(
                calibration["valid"] and pair_sensitivity_valid
            )
        mismatches = [
            result for result in pair_results if result["guest_observation_equal"] is not True
        ]
        summary_status = "pending"
        if not calibration["valid"] or mismatches or (
            null_control is not None and not null_control["pass"]
        ):
            summary_status = "invalid"
        elif null_control is not None and null_control["pass"]:
            summary_status = "pass"
        summary = {
            "schema_id": AB_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "record_id": args.batch_id,
            "candidate_id": args.candidate_id,
            "artifact_type": "summary",
            "status": summary_status,
            "pairs": args.pairs,
            "measured_runs": len(schedule),
            "schedule": {"ab": args.pairs // 2, "ba": args.pairs // 2},
            "calibration": calibration,
            "workloads": summaries,
            "pair_results": pair_results,
            "combined": summarize_log_effect(combined_raw),
            "host": host_snapshot_end,
            "measurement_policy": dict(measurement_policy),
        }
        if null_control is not None:
            summary["null_control"] = null_control
        _write_json_once(record_root / "summary.json", summary)
        summary_written = True
        if summary_status == "invalid":
            reasons = []
            if not model["valid"]:
                reasons.append(
                    "interleaved anchor local residual exceeded 2%"
                    if is_v3
                    else "interleaved anchor residual exceeded 2%"
                )
            if use_replicated_anchors and not calibration["anchor_group_dispersion_valid"]:
                reasons.append("replicated anchor dispersion exceeded 2%")
            if is_v3 and not calibration["pair_level_sensitivity_valid"]:
                reasons.append("pair-level raw-vs-host-corrected sensitivity exceeded 2%")
            if mismatches:
                reasons.append("guest observation projection mismatch during A/B")
            if null_control is not None and not null_control["pass"]:
                reasons.extend("null-control: {}".format(reason) for reason in null_control["reasons"])
            decision = {
                "schema_id": DECISION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": args.batch_id,
                "candidate_id": args.candidate_id,
                "decision_kind": "invalid",
                "status": "invalid",
                "reasons": reasons,
                "statistics": summary,
                **dict(decision_context),
            }
            decision_text = "# RP2040 CPU candidate decision\n\nBatch invalid: {}.\n".format(
                "; ".join(reasons)
            )
        elif args.candidate_id == "P0-A2":
            decision = {
                "schema_id": DECISION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": args.batch_id,
                "candidate_id": args.candidate_id,
                "decision_kind": "null-control",
                "status": "pass",
                "statistics": summary,
                "correctness": {"status": "pass", "source": "correctness/comparison.json"},
                **dict(decision_context),
            }
            decision_text = "# RP2040 CPU candidate decision\n\nP0-A2 null-control passed; candidate A/B admission is open.\n"
        else:
            decision = {
                "schema_id": DECISION_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": args.batch_id,
                "candidate_id": args.candidate_id,
                "decision_kind": "performance",
                "status": "pending",
                "statistics": summary,
                "correctness": {"status": "pass", "source": "correctness/comparison.json"},
                **dict(decision_context),
            }
            decision_text = "# RP2040 CPU candidate decision\n\nPerformance A/B is pending review and null-control sensitivity.\n"
        _write_json_replace(record_root / "decision.json", decision)
        _write_text_once(record_root / "decision.md", decision_text)
        _write_text_once(
            record_root / "hotpath-disassembly.txt",
            "P0-B profile provides CPU hot-path evidence; candidate A/B disassembly is recorded separately.\n",
        )
        _write_sha256sums_once(record_root)
        if summary_status == "invalid":
            raise ValueError("interleaved-anchor A/B batch is invalid; see decision.json")
    except Exception as error:
        if not summary_written:
            failure_summary = {
                "schema_id": AB_SCHEMA_ID,
                "schema_version": SCHEMA_VERSION,
                "record_id": args.batch_id,
                "candidate_id": args.candidate_id,
                "artifact_type": "summary",
                "status": "invalid",
                "pairs": args.pairs,
                "measured_runs": len(measured),
                "schedule": {"ab": args.pairs // 2, "ba": args.pairs // 2},
                "calibration": {
                    "method": calibration_method,
                    "anchor_count": len(anchors),
                    "anchor_run_ids": [anchor.get("anchor_id") for anchor in anchors],
                    "valid": False,
                    "error": str(error),
                },
                "workloads": {},
                "pair_results": [],
                "combined": {},
                "host": host_cpu(),
                "measurement_policy": dict(measurement_policy),
            }
            _write_json_once(record_root / "summary.json", failure_summary)
            _write_json_replace(
                record_root / "decision.json",
                {
                    "schema_id": DECISION_SCHEMA_ID,
                    "schema_version": SCHEMA_VERSION,
                    "record_id": args.batch_id,
                    "candidate_id": args.candidate_id,
                    "decision_kind": "invalid",
                    "status": "invalid",
                    "reasons": ["interleaved-anchor protocol failed", str(error)],
                    "statistics": failure_summary,
                    **dict(decision_context),
                },
            )
            _write_text_once(
                record_root / "decision.md",
                "# RP2040 CPU candidate decision\n\nBatch invalid: interleaved-anchor protocol failed.\n",
            )
            _write_text_once(
                record_root / "hotpath-disassembly.txt",
                "P0-B profile provides CPU hot-path evidence; candidate A/B disassembly is recorded separately.\n",
            )
            _write_sha256sums_once(record_root)
        raise
    finally:
        _restore_cpu_affinity(before)
    return 0


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
                    identity_features = (
                        identity.get("feature_set", [])
                        if isinstance(identity, Mapping)
                        else ()
                    )
                    validate_report(workload, report, commit, identity_features)
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


def _require_profile_gate(
    profile_record: Optional[Path],
    workloads: Sequence[Mapping[str, Any]],
    candidate_identity: Mapping[str, Any],
    measurement_cpu: Optional[int],
    candidate_id: str = "P2-A",
) -> None:
    """Require the candidate-specific diagnostic profile before production A/B."""
    if profile_record is None:
        raise ValueError("{} A/B requires --profile-record diagnostic profile".format(candidate_id))
    record = profile_record.resolve()
    _validate_record_root(record)
    if not (record / "SHA256SUMS").is_file():
        raise ValueError("{} profile record is missing SHA256SUMS".format(candidate_id))
    _verify_existing_sha256sums(record)
    manifest = _read_json(record / "manifest.json")
    decision = _read_json(record / "decision.json")
    if not isinstance(manifest, Mapping) or not isinstance(decision, Mapping):
        raise ValueError("{} profile record manifest/decision must be objects".format(candidate_id))
    expected_workloads = _workload_manifest_entries(workloads)
    if (
        manifest.get("record_type") != RECORD_TYPE
        or manifest.get("record_version") != SCHEMA_VERSION
        or manifest.get("record_id") != record.name
        or manifest.get("candidate_id") != candidate_id
        or manifest.get("workloads") != expected_workloads
    ):
        raise ValueError("{} profile record identity/workloads do not match A/B".format(candidate_id))
    if manifest.get("measurement_cpu") != measurement_cpu:
        raise ValueError("{} profile record CPU differs from A/B".format(candidate_id))
    identities = manifest.get("backend_identities")
    profile_identity = identities.get("candidate_profile") if isinstance(identities, Mapping) else None
    if not isinstance(profile_identity, Mapping):
        raise ValueError("{} profile record candidate_profile identity is missing".format(candidate_id))
    if profile_identity.get("commit") != candidate_identity.get("commit"):
        raise ValueError("{} profile backend commit differs from A/B candidate".format(candidate_id))
    profile_features = profile_identity.get("feature_set")
    profile_required_features = {"cpu-application-profiler", "sd-gen1-multiblock"}
    # The profile binary intentionally includes the profiler, while the
    # production candidate is a compile-out build.  Keep these requirements
    # separate so a production A/B cannot be blocked for correctly omitting
    # diagnostic code.
    candidate_required_features = {"sd-gen1-multiblock"}
    if candidate_id == "P1-B":
        profile_required_features.add("executable-sram-invalidation-filter")
        candidate_required_features.add("executable-sram-invalidation-filter")
    elif candidate_id == "P2-A":
        profile_required_features.add("pending-exception-fast-reject")
        candidate_required_features.add("pending-exception-fast-reject")
    if not isinstance(profile_features, list) or not profile_required_features.issubset(profile_features):
        raise ValueError("{} profile record lacks required profiler features".format(candidate_id))
    candidate_features = candidate_identity.get("feature_set")
    if not isinstance(candidate_features, list) or not candidate_required_features.issubset(candidate_features):
        raise ValueError("{} A/B candidate lacks required production features".format(candidate_id))
    if manifest.get("feature_set") != profile_features:
        raise ValueError("{} profile record feature_set differs from candidate_profile identity".format(candidate_id))
    if decision.get("decision_kind") != "profile" or decision.get("status") != "pass":
        raise ValueError("{} profile record decision is not passing".format(candidate_id))
    profile_dir = record / "profile"
    if not profile_dir.is_dir():
        raise ValueError("{} profile record directory is missing".format(candidate_id))
    expected_paths = {
        profile_dir / "{}-r{}.json".format(workload["id"], workload["revision"])
        for workload in workloads
    }
    actual_paths = {
        path
        for path in profile_dir.glob("*.json")
        if not path.name.endswith("-measurement.json")
    }
    if actual_paths != expected_paths:
        raise ValueError("{} profile record does not cover exactly both workloads".format(candidate_id))
    profile_values: List[Mapping[str, Any]] = []
    for workload in workloads:
        profile_path = profile_dir / "{}-r{}.json".format(workload["id"], workload["revision"])
        profile = _read_json(profile_path)
        if not isinstance(profile, Mapping):
            raise ValueError("{} profile is not an object: {}".format(candidate_id, profile_path))
        expected_profile_workload = {
            key: workload[key]
            for key in ("id", "revision", "firmware_sha256", "scenario_sha256")
        }
        if (
            profile.get("candidate_id") != candidate_id
            or profile.get("workload") != expected_profile_workload
            or profile.get("feature_set") != profile_features
        ):
            raise ValueError("{} profile identity/workload/features are invalid: {}".format(candidate_id, profile_path))
        if candidate_id == "P1-B":
            validate_executable_sram_filter_profile(profile)
        elif candidate_id == "P2-A":
            validate_pending_exception_profile(profile)
        profile_values.append(profile)
    if candidate_id == "P1-B":
        filterability = summarize_executable_sram_filter_profiles(profile_values)
        if decision.get("filterability") != filterability:
            raise ValueError("P1-B profile filterability summary does not match counters")
        if filterability.get("pass") is not True:
            raise ValueError("P1-B profile filterability gate is not passing")


def run_ab(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("ab requires exactly the two registered workloads")
    if args.pairs != 10:
        raise ValueError("ab fixes --pairs at 10 (5 AB + 5 BA)")
    if args.warmup != 1:
        raise ValueError("ab fixes --warmup at 1")
    calibration_method = getattr(
        args, "calibration_method", CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1
    )
    validate_calibration_method(calibration_method)
    expected_calibration_runs = (
        INTERLEAVED_ANCHOR_V2_REPLICATES
        if calibration_method in (
            CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2,
            CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3,
        )
        else 3
    )
    if args.calibration_runs != expected_calibration_runs:
        raise ValueError(
            "ab fixes --calibration-runs at {} for {}".format(
                expected_calibration_runs, calibration_method
            )
        )
    inter_run_cooldown_seconds = validate_inter_run_cooldown(
        args.inter_run_cooldown_seconds
    )
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
    if args.candidate_id in ("P1-B", "P2-A"):
        _require_profile_gate(
            getattr(args, "profile_record", None),
            workloads,
            identities["candidate_production"],
            args.cpu,
            candidate_id=args.candidate_id,
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
    host_stability_record = getattr(args, "host_stability_record", None)
    if calibration_method == CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3:
        _require_host_stability_gate(
            host_stability_record,
            workloads,
            identities["baseline_production"],
            args.cpu,
            inter_run_cooldown_seconds,
            primary_metric=getattr(args, "primary_metric", "cpu-time"),
        )
    _refuse_existing_files(record_root / "ab")
    for aggregate in (record_root / "summary.json", record_root / "decision.md", record_root / "hotpath-disassembly.txt"):
        _refuse_existing(aggregate)
    measurement_policy = (
        interleaved_anchor_measurement_policy_v3()
        if calibration_method == CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3
        else (
            interleaved_anchor_measurement_policy_v2()
            if calibration_method == CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2
            else interleaved_anchor_measurement_policy()
        )
    )
    primary_metric = getattr(args, "primary_metric", "cpu-time")
    primary_metric_fields(primary_metric)
    measurement_policy = dict(measurement_policy)
    measurement_policy["primary_metric"] = primary_metric
    manifest_identity = _base_manifest(
        batch_id, workloads, identities, candidate_id=args.candidate_id, cpu=args.cpu,
        feature_set=getattr(args, "feature_set", []),
        measurement_policy=measurement_policy,
    )
    if calibration_method == CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3:
        manifest_identity["host_stability_record"] = str(host_stability_record.resolve())
        manifest_identity["host_stability_record_sha256"] = sha256_file(host_stability_record.resolve())
    if args.candidate_id in ("P1-B", "P2-A"):
        profile_record = getattr(args, "profile_record", None)
        if profile_record is None:
            raise ValueError("{} A/B requires --profile-record diagnostic profile".format(args.candidate_id))
        manifest_identity["diagnostic_profile_record"] = profile_record.resolve().name
    _record_manifest(record_root, manifest_identity)
    decision_context = _manifest_decision_context(
        record_root, workloads, identities, feature_set=getattr(args, "feature_set", []),
    )
    return _run_interleaved_anchor_ab(
        args,
        workloads,
        identities,
        record_root,
        decision_context,
        measurement_policy,
    )


def run_profile(args: argparse.Namespace) -> int:
    workloads = load_workloads(args.target, args.firmware)
    if len(workloads) != 2:
        raise ValueError("profile requires exactly the two registered workloads")
    identity = clean_backend_identity(args.backend)
    if not args.runner.is_file():
        raise ValueError("runner is missing: {}".format(args.runner))
    validate_runner_embedded_commit(args.runner, identity["commit"])
    declared_features = validate_profile_feature_set(
        args.candidate_id, getattr(args, "feature_set", [])
    )
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
    normalized_profiles: List[Mapping[str, Any]] = []
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
            if args.candidate_id == "P1-B":
                validate_executable_sram_filter_profile(normalized_profile)
            elif args.candidate_id == "P2-A":
                validate_pending_exception_profile(normalized_profile)
            _write_json_once(profile_path, normalized_profile)
            _write_json_once(phase_dir / "{}-measurement.json".format(workload["id"]), result["measurement"])
            normalized_profiles.append(normalized_profile)
    finally:
        _restore_cpu_affinity(before)
    decision_payload: Dict[str, Any] = {
        "schema_id": DECISION_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "record_id": batch_id,
        "candidate_id": args.candidate_id,
        "decision_kind": "profile",
        "status": "pass",
        "correctness": {"status": "not_run", "profile": "written"},
        **decision_context,
    }
    if args.candidate_id == "P1-B":
        decision_payload["filterability"] = summarize_executable_sram_filter_profiles(
            normalized_profiles
        )
    _write_json_replace(record_root / "decision.json", decision_payload)
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

    stability = subparsers.add_parser(
        "stability-preflight",
        help="run the fixed baseline host-stability sentinel before v3 A/B",
    )
    _add_workloads(stability)
    stability.add_argument("--backend", type=Path, required=True)
    stability.add_argument("--runner", type=Path, required=True)
    stability.add_argument("--protocol-version", type=int, choices=(1, 2, 3), default=3)
    stability.add_argument(
        "--primary-metric", choices=AB_PRIMARY_METRICS,
        help="throughput clock used by the sentinel; CPU-primary A/B requires an explicit cpu-time sentinel",
    )
    stability.add_argument("--warmup", type=int)
    stability.add_argument("--runs", type=int)
    stability.add_argument(
        "--inter-run-cooldown-seconds", type=float,
        default=AB_INTER_RUN_COOLDOWN_SECONDS,
    )
    stability.add_argument("--admission-record", type=Path, required=True)
    stability.add_argument("--batch-id", required=True)
    stability.add_argument("--output", type=Path, required=True)
    stability.set_defaults(handler=run_host_stability_preflight)

    cpu_time = subparsers.add_parser(
        "cpu-time-diagnostic",
        help="compare runner CPU time with wall time without an A/B decision",
    )
    _add_workloads(cpu_time)
    cpu_time.add_argument("--backend", type=Path, required=True)
    cpu_time.add_argument("--runner", type=Path, required=True)
    cpu_time.add_argument("--warmup", type=int)
    cpu_time.add_argument("--runs", type=int)
    cpu_time.add_argument(
        "--inter-run-cooldown-seconds", type=float,
        default=AB_INTER_RUN_COOLDOWN_SECONDS,
    )
    cpu_time.add_argument("--admission-record", type=Path, required=True)
    cpu_time.add_argument("--batch-id", required=True)
    cpu_time.add_argument("--output", type=Path, required=True)
    cpu_time.set_defaults(handler=run_cpu_time_diagnostic)

    load_shape = subparsers.add_parser(
        "load-shape",
        help="measure independent guest host scaling without an A/B decision",
    )
    _add_workloads(load_shape)
    load_shape.add_argument("--backend", type=Path, required=True)
    load_shape.add_argument("--runner", type=Path, required=True)
    load_shape.add_argument("--cycles", type=int, default=LOAD_SHAPE_DEFAULT_CYCLES)
    load_shape.add_argument("--batch-id")
    load_shape.add_argument("--output", type=Path, required=True)
    load_shape.set_defaults(handler=run_load_shape)

    affinity_pilot = subparsers.add_parser(
        "affinity-pilot",
        help="compare pinned-vCPU and inherited-set short guest execution",
    )
    _add_workloads(affinity_pilot)
    affinity_pilot.add_argument("--backend", type=Path, required=True)
    affinity_pilot.add_argument("--runner", type=Path, required=True)
    affinity_pilot.add_argument("--cycles", type=int, default=LOAD_SHAPE_DEFAULT_CYCLES)
    affinity_pilot.add_argument("--replicates", type=int, default=AFFINITY_PILOT_REPLICATES)
    affinity_pilot.add_argument("--batch-id")
    affinity_pilot.add_argument("--output", type=Path, required=True)
    affinity_pilot.set_defaults(handler=run_affinity_pilot)

    cooldown_pilot = subparsers.add_parser(
        "cooldown-pilot",
        help="select the smallest fixed cooldown using short guest runs",
    )
    _add_workloads(cooldown_pilot)
    cooldown_pilot.add_argument("--backend", type=Path, required=True)
    cooldown_pilot.add_argument("--runner", type=Path, required=True)
    cooldown_pilot.add_argument("--cycles", type=int, default=LOAD_SHAPE_DEFAULT_CYCLES)
    cooldown_pilot.add_argument("--replicates", type=int, default=COOLDOWN_PILOT_REPLICATES)
    cooldown_pilot.add_argument("--batch-id")
    cooldown_pilot.add_argument("--output", type=Path, required=True)
    cooldown_pilot.set_defaults(handler=run_cooldown_pilot)

    short_block = subparsers.add_parser(
        "short-block",
        help="run the fixed five-block CPU-time A/B screening protocol",
    )
    _add_workloads(short_block)
    short_block.add_argument("--baseline-backend", type=Path, required=True)
    short_block.add_argument("--candidate-backend", type=Path, required=True)
    short_block.add_argument("--baseline-runner", type=Path, required=True)
    short_block.add_argument("--candidate-runner", type=Path, required=True)
    short_block.add_argument("--candidate-id", default="candidate")
    short_block.add_argument("--correctness-record", type=Path)
    short_block.add_argument("--admission-record", type=Path, required=True)
    short_block.add_argument("--cycles", type=int, default=SHORT_BLOCK_DEFAULT_CYCLES)
    short_block.add_argument(
        "--replicates", type=int, default=SHORT_BLOCK_ANCHOR_REPLICATES,
    )
    short_block.add_argument(
        "--inter-run-cooldown-seconds", type=float,
        default=SHORT_BLOCK_COOLDOWN_SECONDS,
    )
    short_block.add_argument("--batch-id")
    short_block.add_argument("--final-report-only", action="store_true")
    short_block.add_argument("--output", type=Path, required=True)
    short_block.set_defaults(handler=run_short_block)

    ab = subparsers.add_parser("ab")
    _add_workloads(ab)
    ab.add_argument("--baseline-backend", type=Path, required=True)
    ab.add_argument("--candidate-backend", type=Path, required=True)
    ab.add_argument("--baseline-runner", type=Path, required=True)
    ab.add_argument("--candidate-runner", type=Path, required=True)
    ab.add_argument(
        "--profile-record", type=Path,
        help="P1-B/P2-A feature-on diagnostic profile record required before production A/B",
    )
    ab.add_argument(
        "--host-stability-record", type=Path,
        help="v3 host-stability sentinel record required before production A/B",
    )
    ab.add_argument("--pairs", type=int, default=10)
    ab.add_argument("--warmup", type=int, default=1)
    ab.add_argument("--calibration-runs", type=int, default=3)
    ab.add_argument(
        "--calibration-method",
        default=CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1,
        choices=(
            CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V1,
            CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V2,
            CALIBRATION_METHOD_INTERLEAVED_ANCHOR_V3,
        ),
        help="fixed host-stability protocol; v2 uses five groups and v3 uses nine groups of three anchors",
    )
    ab.add_argument(
        "--primary-metric", choices=AB_PRIMARY_METRICS, default="cpu-time",
        help="production A/B primary throughput clock; CPU time is the default",
    )
    ab.add_argument(
        "--inter-run-cooldown-seconds", type=float,
        default=AB_INTER_RUN_COOLDOWN_SECONDS,
        help="fixed host-recovery interval between guest runs",
    )
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
        try:
            validate_calibration_method(args.calibration_method)
        except ValueError as error:
            parser.error(str(error))
        try:
            validate_inter_run_cooldown(args.inter_run_cooldown_seconds)
        except ValueError as error:
            parser.error(str(error))
        if args.cpu is None:
            parser.error("ab requires --cpu for affinity pinning")
        if args.final_report_only and args.candidate_id != "P0-A2":
            parser.error("--final-report-only is reserved for candidate_id P0-A2")
    if args.command == "stability-preflight":
        policy = host_stability_measurement_policy_for_version(args.protocol_version)
        if args.warmup is not None and args.warmup != policy["warmup_runs"]:
            parser.error("--warmup is fixed at {}".format(policy["warmup_runs"]))
        if args.runs is not None and args.runs != policy["measured_runs"]:
            parser.error("--runs is fixed at {}".format(policy["measured_runs"]))
        try:
            validate_inter_run_cooldown(args.inter_run_cooldown_seconds)
        except ValueError as error:
            parser.error(str(error))
        if args.cpu is None:
            parser.error("stability-preflight requires --cpu for affinity pinning")
    if args.command == "cpu-time-diagnostic":
        if args.warmup is not None and args.warmup != CPU_TIME_DIAGNOSTIC_WARMUP_RUNS:
            parser.error("--warmup is fixed at {}".format(CPU_TIME_DIAGNOSTIC_WARMUP_RUNS))
        if args.runs is not None and args.runs != CPU_TIME_DIAGNOSTIC_MEASURED_RUNS:
            parser.error("--runs is fixed at {}".format(CPU_TIME_DIAGNOSTIC_MEASURED_RUNS))
        try:
            validate_inter_run_cooldown(args.inter_run_cooldown_seconds)
        except ValueError as error:
            parser.error(str(error))
        if args.cpu is None:
            parser.error("cpu-time-diagnostic requires --cpu for affinity pinning")
    if args.command == "load-shape" and args.cycles <= 0:
        parser.error("load-shape requires positive --cycles")
    if args.command == "affinity-pilot":
        if args.cycles <= 0:
            parser.error("affinity-pilot requires positive --cycles")
        if args.replicates != AFFINITY_PILOT_REPLICATES:
            parser.error(
                "affinity-pilot fixes --replicates at {}".format(
                    AFFINITY_PILOT_REPLICATES
                )
            )
        if args.cpu is None:
            parser.error("affinity-pilot requires --cpu")
    if args.command == "cooldown-pilot":
        if args.cycles <= 0:
            parser.error("cooldown-pilot requires positive --cycles")
        if args.replicates != COOLDOWN_PILOT_REPLICATES:
            parser.error(
                "cooldown-pilot fixes --replicates at {}".format(
                    COOLDOWN_PILOT_REPLICATES
                )
            )
        if args.cpu is None:
            parser.error("cooldown-pilot requires --cpu")
    if args.command == "short-block":
        if args.cycles <= 0:
            parser.error("short-block requires positive --cycles")
        if args.replicates != SHORT_BLOCK_ANCHOR_REPLICATES:
            parser.error(
                "short-block fixes --replicates at {}".format(
                    SHORT_BLOCK_ANCHOR_REPLICATES
                )
            )
        if args.inter_run_cooldown_seconds != SHORT_BLOCK_COOLDOWN_SECONDS:
            parser.error(
                "short-block fixes --inter-run-cooldown-seconds at {}".format(
                    SHORT_BLOCK_COOLDOWN_SECONDS
                )
            )
        if args.cpu is None:
            parser.error("short-block requires --cpu")
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
