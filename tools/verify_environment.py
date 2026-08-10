#!/usr/bin/env python3
"""Verify portable BSP contracts and optional hardware reference evidence."""

import argparse
import binascii
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import generate_board_header
import picocalc
from provenance import directory_sha256


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
Check = Dict[str, object]


def add_check(checks: List[Check], name: str, passed: bool, **details: object) -> None:
    check: Check = {"name": name, "status": "pass" if passed else "fail"}
    check.update(details)
    checks.append(check)


def error_details(error: BaseException) -> Dict[str, str]:
    return {
        "error_type": type(error).__name__,
        "error": str(error) or type(error).__name__,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bit_is_set(values: bytes, index: int) -> bool:
    return (values[index // 8] & (1 << (index % 8))) != 0


def git_head(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def git_has_commit(path: Path, commit: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "cat-file", "-e", commit + "^{commit}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def git_rev_parse(path: Path, revision: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", revision],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def parse_ci_workflow(ci_path: Path) -> Dict[str, object]:
    """Parse the tiny subset of GitHub Actions YAML needed for fail-closed checks."""
    text = ci_path.read_text(encoding="utf-8").splitlines()
    env: Dict[str, str] = {}
    jobs: Dict[str, Dict[str, str]] = {}
    in_env = False
    in_jobs = False
    current_job: Optional[str] = None
    current_block: List[str] = []

    def emit_job(job_id: Optional[str], block: List[str]) -> None:
        if job_id is None:
            return
        jobs[job_id] = {"body": "\n".join(block)}

    for raw_line in text:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if current_job is not None:
                current_block.append(raw_line)
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            emit_job(current_job, current_block)
            current_job = None
            current_block = []
            in_jobs = stripped == "jobs:"
            in_env = stripped == "env:"
            continue

        if in_env and indent == 2:
            match = re.match(r"^\s{2}([A-Z0-9_]+):\s*(.*)$", line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                if value and (
                    (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
                ):
                    value = value[1:-1]
                env[key] = value
            continue

        if in_jobs:
            job_match = re.match(r"^\s{2}([A-Za-z0-9_-]+):\s*$", line)
            if indent == 2 and job_match:
                emit_job(current_job, current_block)
                current_job = job_match.group(1)
                current_block = [raw_line]
            elif current_job is not None:
                current_block.append(raw_line)

    emit_job(current_job, current_block)

    for job_id, metadata in jobs.items():
        name = None
        for line in metadata["body"].splitlines():
            match = re.match(r"^\s{4}name:\s*(.+)$", line)
            if match:
                name = match.group(1).strip()
                break
        metadata["name"] = name or job_id
    return {"env": env, "jobs": jobs}


def require_text(
    checks: List[Check],
    root: Path,
    relative_path: str,
    label: str,
    required: List[str],
) -> None:
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        missing = [token for token in required if token not in text]
        add_check(
            checks,
            "source-fingerprint:" + label,
            not missing,
            path=relative_path,
            missing=missing,
        )
    except (OSError, UnicodeError) as error:
        add_check(
            checks,
            "source-fingerprint:" + label,
            False,
            path=relative_path,
            **error_details(error),
        )


def verify_audio_dma_restart(checks: List[Check], root: Path) -> None:
    """The EOF drain must leave the DMA channel reusable for the next track."""
    relative_path = "bsp/vendor/audio_picoment/platform/picocalc_audio_pwm.cpp"
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        start = text.index("void start_output()")
        end = text.index("void init_common(", start)
        start_output = text[start:end]
        required = (
            "dma_channel_set_irq0_enabled(static_cast<uint>(g_dma_channel), true);",
            "irq_set_enabled(DMA_IRQ_0, true);",
        )
        missing = [token for token in required if token not in start_output]
        drain_disable = (
            "dma_channel_set_irq0_enabled(static_cast<uint>(g_dma_channel), false);"
            in text
        )
        sdk_2_0_compatible = (
            "dma_channel_set_trans_count(static_cast<uint>(g_dma_channel), kHalfSamples, false);"
            in text
        )
        add_check(
            checks,
            "source-fingerprint:audio-dma-restart",
            not missing and drain_disable and sdk_2_0_compatible,
            path=relative_path,
            missing=missing,
            drain_disable=drain_disable,
            sdk_2_0_compatible=sdk_2_0_compatible,
        )
    except (OSError, UnicodeError, ValueError) as error:
        add_check(
            checks,
            "source-fingerprint:audio-dma-restart",
            False,
            path=relative_path,
            **error_details(error),
        )


def verify_generated_board(checks: List[Check], root: Path) -> None:
    profile_path = root / "profiles/picocalc-rp2040.json"
    generated_path = root / "bsp/include/picocalc/board_generated.h"
    try:
        profile = load_json(profile_path)
        expected = generate_board_header.render(profile, profile_path)
        actual = generated_path.read_text(encoding="utf-8")
        add_check(
            checks,
            "structured-profile:generated-board-header",
            actual == expected,
            profile=str(profile_path.relative_to(root)),
            generated=str(generated_path.relative_to(root)),
            stale=actual != expected,
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        add_check(
            checks,
            "structured-profile:generated-board-header",
            False,
            profile="profiles/picocalc-rp2040.json",
            generated="bsp/include/picocalc/board_generated.h",
            **error_details(error),
        )


def verify_lcd_transactions(checks: List[Check], root: Path) -> None:
    compiler = shutil.which("c++")
    if compiler is None:
        add_check(
            checks,
            "host-test:lcd-transactions",
            False,
            error="C++17 host compiler not found on PATH",
        )
        return

    source = root / "tests/lcd_protocol_test.cpp"
    audio_source = root / "tests/audio_ring_spsc_test.cpp"
    include = root / "bsp/include"
    try:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "lcd_protocol_test"
            compiled = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(include),
                    str(source),
                    "-o",
                    str(executable),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if compiled.returncode != 0:
                add_check(
                    checks,
                    "host-test:lcd-transactions",
                    False,
                    stage="compile",
                    returncode=compiled.returncode,
                    stderr=compiled.stderr[-4000:],
                )
                return
            executed = subprocess.run(
                [str(executable)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            audio_executable = Path(temporary) / "audio_ring_spsc_test"
            audio_compiled = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(include),
                    str(audio_source),
                    "-o",
                    str(audio_executable),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if audio_compiled.returncode == 0:
                audio_executed = subprocess.run(
                    [str(audio_executable)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                audio_returncode = audio_executed.returncode
                audio_stdout = audio_executed.stdout.strip()
                audio_stderr = audio_executed.stderr[-4000:]
            else:
                audio_returncode = audio_compiled.returncode
                audio_stdout = ""
                audio_stderr = audio_compiled.stderr[-4000:]
        add_check(
            checks,
            "host-test:lcd-transactions",
            executed.returncode == 0 and audio_returncode == 0,
            stage="execute",
            returncode=executed.returncode,
            audio_returncode=audio_returncode,
            stdout=(executed.stdout.strip() + "\n" + audio_stdout).strip(),
            stderr=(executed.stderr[-4000:] + "\n" + audio_stderr).strip(),
        )
    except OSError as error:
        add_check(
            checks,
            "host-test:lcd-transactions",
            False,
            stage="launch",
            **error_details(error),
        )


def validation_shape_errors(record: Any, completed: bool) -> List[str]:
    errors: List[str] = []
    if not isinstance(record, dict):
        return ["record must be a JSON object"]

    required = [
        "schema_version",
        "validation_id",
        "bsp_version",
        "repository_commit",
        "validation_date",
        "operator",
        "overall_status",
        "hardware",
        "software",
        "sd_card",
        "firmware",
        "tests",
        "notes",
    ]
    errors.extend("missing {}".format(key) for key in required if key not in record)
    if errors:
        return errors
    if record["schema_version"] != 1:
        errors.append("schema_version must be 1")
    if record["overall_status"] not in ("pending", "pass", "fail"):
        errors.append("invalid overall_status")

    section_keys = {
        "hardware": ("product", "board_revision", "mcu", "notes"),
        "software": ("pico_sdk", "compiler", "cmake"),
        "sd_card": ("manufacturer", "model", "capacity", "filesystem"),
        "firmware": ("path", "uf2_sha256", "build_log"),
    }
    for section, keys in section_keys.items():
        value = record.get(section)
        if not isinstance(value, dict):
            errors.append("{} must be an object".format(section))
            continue
        errors.extend(
            "missing {}.{}".format(section, key) for key in keys if key not in value
        )

    tests = record.get("tests")
    if not isinstance(tests, dict):
        errors.append("tests must be an object")
        return errors
    for name in ("lcd", "sd", "keyboard"):
        result = tests.get(name)
        if not isinstance(result, dict):
            errors.append("missing tests.{}".format(name))
            continue
        if result.get("status") not in ("pending", "pass", "fail"):
            errors.append("invalid tests.{}.status".format(name))
        if not isinstance(result.get("observed"), str):
            errors.append("tests.{}.observed must be a string".format(name))
        evidence = result.get("evidence_files")
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) and item for item in evidence
        ):
            errors.append("tests.{}.evidence_files must be string array".format(name))

    if completed and record["overall_status"] == "pass":
        if not re.fullmatch(r"[0-9a-f]{40}", record.get("repository_commit") or ""):
            errors.append("passing record requires full repository_commit")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record.get("validation_date") or ""):
            errors.append("passing record requires validation_date")
        if not record.get("operator"):
            errors.append("passing record requires operator")
        if not record.get("validation_id") or not record.get("bsp_version"):
            errors.append("passing record requires validation_id and bsp_version")
        for section, keys in {
            "hardware": ("product", "board_revision", "mcu"),
            "software": ("pico_sdk", "compiler", "cmake"),
            "sd_card": ("manufacturer", "model", "capacity", "filesystem"),
        }.items():
            value = record.get(section, {})
            for key in keys:
                if not isinstance(value, dict) or not value.get(key):
                    errors.append(
                        "passing record requires {}.{}".format(section, key)
                    )
        firmware = record.get("firmware")
        digest = firmware.get("uf2_sha256") if isinstance(firmware, dict) else None
        if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            errors.append("passing record requires UF2 SHA-256")
        for name in ("lcd", "sd", "keyboard"):
            result = tests.get(name, {})
            if result.get("status") != "pass":
                errors.append("passing record requires tests.{}=pass".format(name))
            if not result.get("evidence_files"):
                errors.append(
                    "passing record requires tests.{} evidence".format(name)
                )
    return errors


def verify_release_conditions(checks: List[Check], root: Path) -> None:
    """Check the automatable parts of docs/RELEASE_CHECKLIST.md.

    The conformance target is a thing to aim at, not an asset of this
    repository: only the result and the identity needed to reproduce it
    are recorded. And portable verification has to stay complete on a
    clone with no firmware backend, or a public release would require a
    private dependency.
    """
    # Firmware images belonging to the conformance track. Hardware
    # evidence for this project's own builds lives under
    # `hardware-validation/` and is out of scope here — what must never
    # appear is the official sample, or any firmware image inside the
    # emulator-side ledger and the target identity records.
    binary_suffixes = {".elf", ".bin", ".uf2", ".hex"}
    watched_dirs = ("firmware-validation", "reference-projects", "docs", "tools")
    strays: List[str] = []
    skip_dirs = {".git", "build", "build-ci", "artifacts", "__pycache__"}
    for directory in watched_dirs:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in binary_suffixes:
                continue
            relative = path.relative_to(root)
            if any(part in skip_dirs for part in relative.parts):
                continue
            strays.append(str(relative))
    # Anything named after the sample, anywhere.
    strays.extend(
        str(path.relative_to(root))
        for path in root.rglob("picocalc_helloworld*")
        if path.is_file() and ".git" not in path.parts
    )
    # Source files of the official sample would arrive under a directory
    # named after it; the identity records name it in text, which is fine.
    sample_dirs = [
        str(path.relative_to(root))
        for path in root.rglob("picocalc_helloworld")
        if path.is_dir() and ".git" not in path.parts
    ]
    add_check(
        checks,
        "release:no-conformance-target",
        not strays and not sample_dirs,
        firmware_images=strays,
        sample_directories=sample_dirs,
    )

    # The portable checks must not need the backend. They run from this
    # process, so reaching this point at all means they did not require
    # it; what we assert here is that the snapshot they read from exists.
    capability = root / "firmware-validation/capability.json"
    backend_dir_env = os.environ.get("PICOEM_PICOCALC_DIR")
    add_check(
        checks,
        "release:portable-without-backend",
        capability.is_file(),
        capability_snapshot=str(capability.relative_to(root)),
        backend_env_set=bool(backend_dir_env),
        note="portable verification reads the snapshot, never the backend checkout",
    )


def verify_host_backend(checks: List[Check], root: Path) -> None:
    """Check the host backend's shape without compiling it.

    Portable verification has no compiler guarantee, so this asserts the
    two properties that would silently rot: that the sources exist, and
    that the host build still shares the device's filesystem layer
    rather than quietly growing a copy of it. Whether it compiles and
    passes is `picocalc.py test --mode host`, which needs a toolchain.
    """
    host = root / "bsp" / "host"
    required = [
        host / "CMakeLists.txt",
        host / "CMakeLists.host.txt",
        host / "include" / "pico" / "stdlib.h",
        host / "include" / "picocalc" / "host.h",
        host / "tests" / "emu_smoke.cpp",
        host / "tests" / "sd_formats_test.cpp",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    add_check(checks, "host-backend:sources", not missing, missing=missing)

    try:
        text = (host / "CMakeLists.host.txt").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        add_check(checks, "host-backend:shares-device-filesystem", False,
                  **error_details(error))
        return

    # The value of the host filesystem test is that it runs the shipping
    # code. If these ever stop being pulled in from ../src, the host is
    # testing a copy and the result stops meaning anything.
    shared = ["src/filesystem.cpp", "src/fatfs_diskio.cpp"]
    absent = [name for name in shared if name not in text]
    # Writes are gated behind this macro in fatfs_diskio.cpp. Without it
    # the card is silently read-only and the smoke test fails at `write`.
    if "PICOCALC_BSP_ENABLE_SD_WRITE" not in text:
        absent.append("PICOCALC_BSP_ENABLE_SD_WRITE")
    add_check(checks, "host-backend:shares-device-filesystem", not absent,
              missing=absent)

    try:
        sd_source = (host / "src" / "sdcard.cpp").read_text(encoding="utf-8")
        sd_header = (host / "include" / "picocalc" / "host.h").read_text(
            encoding="utf-8"
        )
        sd_test = (host / "tests" / "sd_formats_test.cpp").read_text(encoding="utf-8")
        required_sd = {
            "fat32-default": "format_sd(SdFormat::Fat32)" in sd_source,
            "fat16-explicit": "SdFormat::Fat16" in sd_source,
            "public-format-api": "enum class SdFormat" in sd_header,
            "dual-format-smoke": (
                "check_fat32()" in sd_test
                and "check_fat16()" in sd_test
                and "smoke_test()" in sd_test
            ),
        }
        add_check(
            checks,
            "host-backend:sd-fat32-default-fat16-compatible",
            all(required_sd.values()),
            properties=required_sd,
        )
    except (OSError, UnicodeError) as error:
        add_check(
            checks,
            "host-backend:sd-fat32-default-fat16-compatible",
            False,
            **error_details(error),
        )


def verify_firmware_validation(checks: List[Check], root: Path) -> None:
    """Check the emulator-side ledger: capability snapshot and Gate records.

    The firmware backend lives in a separate repository, so a clone of
    this one cannot ask it what it supports. The snapshot in
    `firmware-validation/capability.json` is what keeps the portable
    verification complete without a backend checkout.
    """
    directory = root / "firmware-validation"
    if not directory.is_dir():
        # Nothing to check on a clone that predates the firmware track.
        return

    capability_path = directory / "capability.json"
    try:
        capability = load_json(capability_path)
        backend = capability.get("backend", {})
        scope = capability.get("scope", {})
        supported = capability.get("supported", [])
        unsupported = capability.get("unsupported", [])
        errors: List[str] = []

        if capability.get("schema_version") != 2:
            errors.append("schema_version must be 2")
        if not isinstance(backend, dict) or not backend.get("repo"):
            errors.append("backend.repo is required")
        if "commit" in backend:
            errors.append("backend.commit must be absent")
        if backend.get("execution_model") != "Serial":
            errors.append("backend.execution_model must be Serial while it is the reference")
        if not isinstance(scope, dict):
            errors.append("scope must be an object")
        else:
            if scope.get("authority") != "firmware-emulator-rp2040-binary-conformance":
                errors.append("scope.authority must be firmware-emulator-rp2040-binary-conformance")
            if scope.get("hardware_or_bsp_audio_evidence_implies_emulator_audio_output") is not False:
                errors.append(
                    "scope.hardware_or_bsp_audio_evidence_implies_emulator_audio_output must be false"
                )

        roles = backend.get("roles")
        if not isinstance(roles, dict):
            errors.append("backend.roles is required and must be an object")
            hardware = promoted = experimental = None
            r5_accepted = None
            opt1b_accepted = None
            opt1b_validation = None
        else:
            required_roles = {"hardware_correlated", "promoted", "experimental_main"}
            keys = set(roles.keys())
            if keys != required_roles:
                errors.append(
                    "backend.roles must contain exactly {}".format(
                        ", ".join(sorted(required_roles))
                    )
                )
            hardware = roles.get("hardware_correlated")
            promoted = roles.get("promoted")
            experimental = roles.get("experimental_main")

        try:
            registry = picocalc.load_firmware_registry(
                root / "reference-projects/firmware-targets.json"
            )
            targets_by_id = {item["id"]: item for item in registry.get("targets", [])}
            r5_target = targets_by_id.get("picotetris-r5")
            opt1b_target = targets_by_id.get("picotetris-opt1b")
            r5_accepted = r5_target["backend"]["accepted"] if r5_target else None
            opt1b_accepted = opt1b_target["backend"]["accepted"] if opt1b_target else None
            opt1b_validation = (
                opt1b_target.get("validation", {}).get("record")
                if opt1b_target
                else None
            )
            if (
                not r5_target
                or r5_target.get("status") != "active"
                or not opt1b_target
                or opt1b_target.get("status") != "active"
            ):
                errors.append(
                    "registry must contain active picotetris-r5 and picotetris-opt1b targets"
                )
        except (
            OSError,
            UnicodeError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            errors.append("registry load failed: {}".format(error))
            r5_accepted = None
            opt1b_accepted = None
            opt1b_validation = None

        def require_sha(value: Any) -> bool:
            return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None

        if not isinstance(hardware, dict):
            errors.append("hardware_correlated must be an object")
        if not isinstance(promoted, dict):
            errors.append("promoted must be an object")
        if not isinstance(experimental, dict):
            errors.append("experimental_main must be an object")

        if isinstance(hardware, dict):
            if not require_sha(hardware.get("commit")):
                errors.append("hardware_correlated.commit must be a git commit")
            elif r5_accepted is not None and hardware.get("commit") != r5_accepted:
                errors.append("hardware_correlated.commit must match picotetris-r5 backend.accepted")
            if hardware.get("target") != "picotetris-r5":
                errors.append("hardware_correlated.target must be picotetris-r5")
            if hardware.get("status") != "immutable_evidence":
                errors.append("hardware_correlated.status must be immutable_evidence")
            evidence = hardware.get("evidence")
            if not isinstance(evidence, str):
                errors.append("hardware_correlated.evidence must be a path")
            elif not (root / evidence).is_file():
                errors.append("hardware_correlated.evidence must exist")

        if isinstance(promoted, dict):
            if not require_sha(promoted.get("commit")):
                errors.append("promoted.commit must be a git commit")
            elif opt1b_accepted is not None and promoted.get("commit") != opt1b_accepted:
                errors.append("promoted.commit must match picotetris-opt1b backend.accepted")
            if promoted.get("target") != "picotetris-opt1b":
                errors.append("promoted.target must be picotetris-opt1b")
            if promoted.get("status") != "active":
                errors.append("promoted.status must be active")
            if promoted.get("validation") != opt1b_validation:
                errors.append("promoted.validation must match picotetris-opt1b validation.record")
            if not isinstance(opt1b_validation, str) or not (root / opt1b_validation).is_file():
                errors.append("picotetris-opt1b validation record must exist")

        if isinstance(experimental, dict):
            if experimental.get("promoted") is not False:
                errors.append("experimental_main.promoted must be false")
            if experimental.get("status") != "unpromoted":
                errors.append("experimental_main.status must be unpromoted")
            if not require_sha(experimental.get("commit")):
                errors.append("experimental_main.commit must be a git commit")
            source_equivalent = experimental.get("source_equivalent_to")
            if source_equivalent is not None and not require_sha(source_equivalent):
                errors.append(
                    "experimental_main.source_equivalent_to must be a git commit when present"
                )
            if not isinstance(experimental.get("ci_run_id"), int) or experimental.get("ci_run_id") <= 0:
                errors.append("experimental_main.ci_run_id must be a positive integer")

        if isinstance(hardware, dict) and isinstance(promoted, dict) and isinstance(
            experimental, dict
        ):
            if (
                isinstance(hardware.get("commit"), str)
                and isinstance(promoted.get("commit"), str)
                and isinstance(experimental.get("commit"), str)
                and (
                    experimental.get("commit") == hardware.get("commit")
                    or experimental.get("commit") == promoted.get("commit")
                )
            ):
                errors.append(
                    "experimental_main.commit must differ from hardware_correlated and promoted commits"
                )

        audio_supported = next(
            (
                item
                for item in supported
                if isinstance(item, dict) and item.get("id") == "audio-output"
            ),
            None,
        )
        if audio_supported is None:
            errors.append("supported must include the correlated audio-output capability")
        else:
            if audio_supported.get("status") != "same_artifact_hardware_correlated":
                errors.append(
                    "supported audio-output.status must be same_artifact_hardware_correlated"
                )
            if audio_supported.get("target") != "picocalc-audio-r1":
                errors.append("supported audio-output.target must be picocalc-audio-r1")
            for key in ("emulator_evidence", "evidence"):
                evidence_path = audio_supported.get(key)
                if not isinstance(evidence_path, str) or not (root / evidence_path).is_file():
                    errors.append("supported audio-output.{} must exist".format(key))
        if any(
            isinstance(item, dict) and item.get("id") == "audio-output"
            for item in unsupported
        ):
            errors.append("unsupported must not retain the correlated audio-output capability")

        for name, entries in (("supported", supported), ("unsupported", unsupported)):
            if not isinstance(entries, list) or not entries:
                errors.append("{} must be a non-empty list".format(name))
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not entry.get("id") or not entry.get("what"):
                    errors.append("{} entries need id and what".format(name))
                    break
        add_check(
            checks,
            "firmware-validation:capability",
            not errors,
            errors=errors,
            supported=len(supported) if isinstance(supported, list) else 0,
            unsupported=len(unsupported) if isinstance(unsupported, list) else 0,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        add_check(
            checks,
            "firmware-validation:capability",
            False,
            **error_details(error),
        )

    records_dir = directory / "records"
    try:
        reports = sorted(records_dir.glob("*/report.json"))
        invalid: List[Dict[str, object]] = []
        for path in reports:
            record = load_json(path)
            problems: List[str] = []
            if record.get("schema_version") != 1:
                problems.append("schema_version must be 1")
            # Every record says which unit of work it is evidence for.
            # Gates 0-7 were Milestone 1's internal steps. Later evidence
            # can identify either a numbered milestone or an R-series
            # roadmap package, but exactly one identity is required.
            has_gate = isinstance(record.get("gate"), int)
            has_milestone = isinstance(record.get("milestone"), int)
            roadmap_package = record.get("roadmap_package")
            has_roadmap_package = (
                isinstance(roadmap_package, str)
                and len(roadmap_package) >= 2
                and roadmap_package[0] == "R"
                and roadmap_package[1:].isdigit()
            )
            if sum((has_gate, has_milestone, has_roadmap_package)) != 1:
                problems.append(
                    "record must carry exactly one integer gate, integer milestone, "
                    "or R-series roadmap_package"
                )
            if record.get("record_id") != path.parent.name:
                problems.append("record_id must match the directory name")
            # Where the backend commit is recorded varies: the first
            # gates put it under the section it belonged to (the Serial
            # baseline, the runner), later ones use a top-level
            # `backend_commit`. Records are evidence and are not
            # rewritten after acceptance, so only the top-level form is
            # shape-checked; every record is separately required to
            # mention the backend commit somewhere.
            # `base` alone is enough when the work needed no fix on top
            # of the commit it started from; `accepted` records the
            # commit a gate was signed off at.
            backend_commit = record.get("backend_commit")
            if isinstance(backend_commit, dict) and not (
                backend_commit.get("accepted")
                or backend_commit.get("commit")
                or backend_commit.get("base")
            ):
                problems.append("backend_commit needs accepted, commit or base")
            if "backend_commit" not in json.dumps(record):
                problems.append("record does not name the backend commit")
            if problems:
                invalid.append({"path": path.name, "record": path.parent.name, "errors": problems})
        add_check(
            checks,
            "firmware-validation:records",
            not invalid,
            records=len(reports),
            invalid=invalid,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        add_check(
            checks,
            "firmware-validation:records",
            False,
            **error_details(error),
        )


def verify_r4_backend_role_ci(checks: List[Check], root: Path) -> None:
    """Verify CI wiring matches capability roles and target registry expectations."""
    errors: List[str] = []
    try:
        ci_path = root / ".github/workflows/ci.yml"
        workflow = parse_ci_workflow(ci_path)
        ci_env = workflow["env"]
        if not isinstance(ci_env, dict):
            raise TypeError("workflow env must be a mapping")
        jobs = workflow["jobs"]
        if not isinstance(jobs, dict):
            raise TypeError("workflow jobs must be a mapping")

        try:
            capability = load_json(root / "firmware-validation/capability.json")
            roles = capability["backend"]["roles"]
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
            raise ValueError("capability roles load failed: {}".format(error))

        try:
            registry = picocalc.load_firmware_registry(
                root / "reference-projects/firmware-targets.json"
            )
            registered = {target["id"]: target for target in registry.get("targets", [])}
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
            raise ValueError("registry load failed: {}".format(error))

        expected_jobs = [
            {
                "display_name": "hardware-correlated-firmware-regression",
                "target": "picotetris-r5",
                "backend_env": "PICOEM_HARDWARE_CORRELATED_COMMIT",
                "target_source_env": "PICOTETRIS_R5_SOURCE_COMMIT",
                "target_bin_env": "PICOTETRIS_R5_BIN_SHA256",
                "target_uf2_env": "PICOTETRIS_R5_UF2_SHA256",
                "target_bundle_env": "PICOTETRIS_R5_BUNDLE_SHA256",
                "target_bundle_path": "provenance/picotetris-r5.bundle",
                "backend_dir": "/tmp/picoem-picocalc",
            },
            {
                "display_name": "promoted-opt1b-firmware-regression",
                "target": "picotetris-opt1b",
                "backend_env": "PICOEM_PROMOTED_COMMIT",
                "target_source_env": "PICOTETRIS_OPT1B_SOURCE_COMMIT",
                "target_bin_env": "PICOTETRIS_OPT1B_BIN_SHA256",
                "target_uf2_env": "PICOTETRIS_OPT1B_UF2_SHA256",
                "target_bundle_env": "PICOTETRIS_OPT1B_BUNDLE_SHA256",
                "target_bundle_path": "provenance/picotetris-r3.bundle",
                "backend_dir": "/tmp/picoem-promoted",
            },
        ]
        name_to_job = {
            metadata.get("name"): job_id
            for job_id, metadata in jobs.items()
            if isinstance(metadata, dict) and metadata.get("name") is not None
        }

        def ci_value(field: str) -> Optional[str]:
            value = ci_env.get(field)
            return value if isinstance(value, str) and value else None

        for expected in expected_jobs:
            display_name = expected["display_name"]
            job_id = name_to_job.get(display_name)
            if job_id is None:
                errors.append("ci missing job named '{}'".format(display_name))
                continue
            job = jobs[job_id]
            body = job.get("body", "")
            if not isinstance(body, str):
                errors.append("ci job '{}' body is not captured".format(display_name))
                continue

            env_var = expected["backend_env"]
            expected_backend_commit = (
                roles.get("hardware_correlated", {}).get("commit")
                if expected["target"] == "picotetris-r5"
                else roles.get("promoted", {}).get("commit")
            )
            expected_backend = ci_value(env_var)
            if expected_backend is None:
                errors.append("ci job '{}' missing {}".format(display_name, env_var))
            elif expected_backend != expected_backend_commit:
                errors.append(
                    "{} mismatch: ci {}={}, capability commit={}".format(
                        display_name, env_var, expected_backend, expected_backend_commit
                    )
                )

            target = registered.get(expected["target"])
            if target is None:
                errors.append("registry target {} missing".format(expected["target"]))
                continue
            expected_backend_source = target.get("source", {}).get("commit")
            expected_backend_bin = target.get("artifacts", {}).get("bin_sha256")
            expected_backend_uf2 = target.get("artifacts", {}).get("uf2_sha256")

            source_env_value = ci_value(expected["target_source_env"])
            if source_env_value is None:
                errors.append("ci job '{}' missing {}".format(display_name, expected["target_source_env"]))
            elif source_env_value != expected_backend_source:
                errors.append(
                    "{} mismatch: {} != registry {}".format(
                        expected["target_source_env"], source_env_value, expected_backend_source
                    )
                )

            bin_env_value = ci_value(expected["target_bin_env"])
            if bin_env_value is None:
                errors.append("ci job '{}' missing {}".format(display_name, expected["target_bin_env"]))
            elif bin_env_value != expected_backend_bin:
                errors.append(
                    "{} mismatch: {} != registry {}".format(
                        expected["target_bin_env"], bin_env_value, expected_backend_bin
                    )
                )

            uf2_env_value = ci_value(expected["target_uf2_env"])
            if uf2_env_value is None:
                errors.append("ci job '{}' missing {}".format(display_name, expected["target_uf2_env"]))
            elif uf2_env_value != expected_backend_uf2:
                errors.append(
                    "{} mismatch: {} != registry {}".format(
                        expected["target_uf2_env"], uf2_env_value, expected_backend_uf2
                    )
                )

            bundle_env_value = ci_value(expected["target_bundle_env"])
            if bundle_env_value is None:
                errors.append("ci job '{}' missing {}".format(display_name, expected["target_bundle_env"]))
            else:
                bundle_path = root / expected["target_bundle_path"]
                if not bundle_path.is_file():
                    errors.append(
                        "ci bundle path {} not found for {}".format(
                            expected["target_bundle_path"], display_name
                        )
                    )
                else:
                    if bundle_env_value != sha256(bundle_path):
                        errors.append(
                            "{} mismatch for bundle {}".format(
                                expected["target_bundle_env"], expected["target_bundle_path"]
                            )
                        )
            target_token = expected["target"]
            if ("--target {}".format(target_token)) not in body:
                errors.append("{} must run --target {}".format(display_name, target_token))
            backend_dir = expected["backend_dir"]
            if 'test -z "$(git -C {} status --porcelain)"'.format(backend_dir) not in body:
                errors.append(
                    "{} must assert backend checkout is clean".format(display_name)
                )
            if expected["backend_env"] not in body:
                errors.append(
                    "{} must checkout backend using {}".format(
                        display_name, expected["backend_env"]
                    )
                )

        add_check(
            checks,
            "r4:backend-role-ci",
            not errors,
            errors=errors,
            job_count=len(expected_jobs),
            workflow=str(ci_path.relative_to(root)),
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        add_check(
            checks,
            "r4:backend-role-ci",
            False,
            **error_details(error),
        )


def verify_hardware_validation(checks: List[Check], root: Path) -> None:
    directory = root / "hardware-validation"
    try:
        schema = load_json(directory / "schema.json")
        template = load_json(directory / "template.json")
        schema_valid = (
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
            and schema.get("type") == "object"
            and isinstance(schema.get("required"), list)
            and isinstance(schema.get("$defs"), dict)
        )
        template_errors = validation_shape_errors(template, completed=False)
        add_check(
            checks,
            "hardware-validation:schema-and-template",
            schema_valid and not template_errors,
            schema_valid=schema_valid,
            template_errors=template_errors,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        add_check(
            checks,
            "hardware-validation:schema-and-template",
            False,
            **error_details(error),
        )
        return

    records_dir = directory / "records"
    try:
        record_paths = sorted(records_dir.glob("*.json"))
        invalid: List[Dict[str, object]] = []
        passing = 0
        for path in record_paths:
            try:
                record = load_json(path)
                errors = validation_shape_errors(record, completed=True)
                if isinstance(record, dict) and record.get("overall_status") == "pass":
                    evidence_paths: List[str] = []
                    tests = record.get("tests", {})
                    if isinstance(tests, dict):
                        for name in ("lcd", "sd", "keyboard"):
                            result = tests.get(name, {})
                            if isinstance(result, dict):
                                evidence = result.get("evidence_files", [])
                                if isinstance(evidence, list):
                                    evidence_paths.extend(
                                        item for item in evidence if isinstance(item, str)
                                    )
                    firmware = record.get("firmware", {})
                    if isinstance(firmware, dict):
                        build_log = firmware.get("build_log")
                        if isinstance(build_log, str) and build_log:
                            evidence_paths.append(build_log)
                        else:
                            errors.append("passing record requires firmware.build_log")
                    for relative in evidence_paths:
                        candidate = (root / relative).resolve()
                        try:
                            candidate.relative_to(root.resolve())
                        except ValueError:
                            errors.append(
                                "evidence path escapes repository: {}".format(relative)
                            )
                            continue
                        if not candidate.is_file():
                            errors.append(
                                "evidence file missing: {}".format(relative)
                            )
                if record.get("overall_status") == "pass" and not errors:
                    passing += 1
                if errors:
                    invalid.append({"path": str(path.relative_to(root)), "errors": errors})
            except (OSError, UnicodeError, ValueError, TypeError) as error:
                invalid.append(
                    {
                        "path": str(path.relative_to(root)),
                        **error_details(error),
                    }
                )
        add_check(
            checks,
            "hardware-validation:records",
            not invalid,
            records=len(record_paths),
            passing_records=passing,
            invalid=invalid,
        )
    except OSError as error:
        add_check(
            checks,
            "hardware-validation:records",
            False,
            **error_details(error),
        )


def verify_catalog(checks: List[Check], root: Path) -> None:
    try:
        catalog = load_json(root / "reference-projects/catalog.json")
        projects = catalog.get("projects", [])
        invalid = [
            project.get("name", "unnamed")
            for project in projects
            if not isinstance(project, dict)
            or not project.get("git_url")
            or not project.get("commit")
            or not project.get("evidence")
        ]
        valid = (
            catalog.get("schema_version") == 1
            and isinstance(projects, list)
            and bool(projects)
            and not invalid
        )
        add_check(checks, "catalog-schema", valid, invalid_projects=invalid)
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as error:
        add_check(checks, "catalog-schema", False, **error_details(error))


def verify_firmware_targets(checks: List[Check], root: Path) -> None:
    try:
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        schema = load_json(root / "reference-projects/firmware-targets.schema.json")
        targets = registry["targets"]
        active = [target for target in targets if target["status"] == "active"]
        problems: List[str] = []
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            problems.append("firmware target schema is not draft 2020-12")
        if schema.get("properties", {}).get("schema_version", {}).get("const") != 3:
            problems.append("firmware target schema does not pin version 3")
        if not active:
            problems.append("registry has no active target")
        for target in active:
            scenario = target.get("scenario")
            if scenario is not None:
                path = root / scenario["path"]
                actual = sha256(path) if path.is_file() else "missing"
                if actual != scenario["sha256"]:
                    problems.append("{} scenario fingerprint mismatch".format(target["id"]))
        add_check(
            checks,
            "firmware-targets:schema-and-contracts",
            not problems,
            targets=len(targets),
            active=len(active),
            errors=problems,
        )

        validation_schema = load_json(
            root / "firmware-validation/target-validation.schema.json"
        )
        validation_problems: List[str] = []
        if validation_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            validation_problems.append("target validation schema is not draft 2020-12")
        if validation_schema.get("properties", {}).get("schema_version", {}).get("const") != 1:
            validation_problems.append("target validation schema does not pin version 1")
        root_resolved = root.resolve()
        for target in targets:
            target_id = target["id"]
            validation_contract = target["validation"]
            validation_path = (root / validation_contract["record"]).resolve()
            try:
                validation_path.relative_to(root_resolved)
            except ValueError:
                validation_problems.append("{} validation path escapes repository".format(target_id))
                continue
            if not validation_path.is_file():
                validation_problems.append("{} validation record is missing".format(target_id))
                continue
            if sha256(validation_path) != validation_contract["sha256"]:
                validation_problems.append("{} validation record fingerprint mismatch".format(target_id))
                continue
            validation = load_json(validation_path)
            evidence = validation.get("evidence")
            if not isinstance(evidence, dict):
                validation_problems.append("{} validation evidence is invalid".format(target_id))
                continue
            expected_validation_keys = {
                "schema_version", "validation_id", "roadmap_package", "target_id",
                "target_revision", "target_contract_sha256", "evidence", "result",
            }
            expected_evidence_keys = {"record", "sha256", "record_id", "section"}
            if set(validation) != expected_validation_keys or set(evidence) != expected_evidence_keys:
                validation_problems.append("{} validation record has unexpected fields".format(target_id))
                continue
            expected_validation_id = "{}-r{}".format(target_id, target["revision"])
            if (
                validation.get("schema_version") != 1
                or validation.get("validation_id") != expected_validation_id
                or validation.get("roadmap_package") != "R4"
                or validation.get("target_id") != target_id
                or validation.get("target_revision") != target["revision"]
                or validation.get("target_contract_sha256")
                != picocalc.firmware_target_contract_sha256(target)
                or validation.get("result") != "accepted"
            ):
                validation_problems.append("{} validation does not match target contract".format(target_id))
                continue
            evidence_path = (root / evidence["record"]).resolve()
            try:
                evidence_path.relative_to(root_resolved)
            except ValueError:
                validation_problems.append("{} evidence path escapes repository".format(target_id))
                continue
            if not evidence_path.is_file() or sha256(evidence_path) != evidence.get("sha256"):
                validation_problems.append("{} evidence fingerprint mismatch".format(target_id))
                continue
            evidence_record = load_json(evidence_path)
            section = evidence.get("section")
            section_data = evidence_record.get(section) if isinstance(section, str) else None
            section_target = (
                section_data.get("target") if isinstance(section_data, dict) else None
            )
            if isinstance(section_target, dict):
                section_target = section_target.get("id")
            if section_target is None and isinstance(section_data, dict):
                command = section_data.get("command")
                if isinstance(command, str) and "--target {} ".format(target_id) in command:
                    section_target = target_id
            section_backend = (
                section_data.get("backend_commit")
                if isinstance(section_data, dict) else None
            )
            record_contract = evidence_record.get("target", {})
            record_contract_sha = (
                record_contract.get("contract_sha256")
                if isinstance(record_contract, dict) else None
            )
            if (
                evidence_record.get("record_id") != evidence.get("record_id")
                or evidence_record.get("result") != "pass"
                or not isinstance(section, str)
                or not isinstance(section_data, dict)
                or section_target != target_id
                or (
                    section_backend is not None
                    and section_backend != target["backend"]["accepted"]
                )
                or (
                    record_contract_sha is not None
                    and record_contract_sha
                    != picocalc.firmware_target_contract_sha256(target)
                )
            ):
                validation_problems.append("{} evidence record does not substantiate validation".format(target_id))
        add_check(
            checks,
            "firmware-targets:versioned-validations",
            not validation_problems,
            validations=len(targets),
            errors=validation_problems,
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as error:
        add_check(
            checks,
            "firmware-targets:schema-and-contracts",
            False,
            **error_details(error),
        )


def verify_template_smoke(checks: List[Check], root: Path) -> None:
    path = root / "templates/rp2040-basic/app/main.cpp"
    try:
        text = path.read_text(encoding="utf-8")
        backlight_only = "mode=backlight-only" in text
        lcd_only = "mode=lcd-only" in text
        required = (
            [
                "picocalc::init_backlight_only()",
                "mode=backlight-only",
            ]
            if backlight_only
            else (
                [
                "picocalc::init()",
                "display::clear(0xf800)",
                "display::verify_pixels(",
                "[PICOCALC][LCD][VERIFY]",
                "mode=lcd-only",
                ]
            )
            if lcd_only
            else [
                "picocalc::init()",
                "draw_test_pattern()",
                "display::clear(color)",
                "display::verify_pixels(",
            "[PICOCALC][LCD][VERIFY] app_status=",
            "audio::stop()",
            "reason=lcd_verify_complete",
            "[PICOCALC][VERIFY] psram=",
            "[PICOCALC][AUDIO][VERIFY] mode=%s status=%s",
            "filesystem::smoke_test()",
                "keyboard::read_event(",
                "[PICOCALC][SMOKE]",
            ]
        )
        missing = [token for token in required if token not in text]
        add_check(
            checks,
            "template-smoke",
            not missing,
            mode=("backlight-only" if backlight_only else
                  "lcd-only" if lcd_only else "full-smoke"),
            missing=missing,
        )
    except (OSError, UnicodeError) as error:
        add_check(checks, "template-smoke", False, **error_details(error))


def require_absent(
    checks: List[Check],
    root: Path,
    relative_path: str,
    label: str,
    forbidden: List[str],
) -> None:
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        present = [token for token in forbidden if token in text]
        add_check(
            checks,
            "source-fingerprint:" + label,
            not present,
            path=relative_path,
            present=present,
        )
    except (OSError, UnicodeError) as error:
        add_check(
            checks,
            "source-fingerprint:" + label,
            False,
            path=relative_path,
            **error_details(error),
        )


VENDORED_LCD_PIO_FILES = {
    "bsp/vendor/lcd_rgb565_pio.cpp":
        "d4013f26f7a49350a354d716e825ac516e952857e2f3578cd414ac50c1e88920",
    "bsp/vendor/lcd_rgb565_pio.h":
        "350aafa3ffb28ac8a31b6e1adcdef551e0177428ee67f9896978c1714e0978f9",
    "bsp/vendor/lcd_spi_min.pio":
        "618d4be87efb71a24422aa74d156d13db32e027cbfd5679cef21aa6d14b82fac",
}


def verify_vendored_lcd_pio(checks: List[Check], root: Path) -> None:
    """The PIO LCD transport must stay a byte-identical copy, not a rewrite."""
    modified: List[str] = []
    details: Dict[str, Any] = {}
    for relative_path, expected in VENDORED_LCD_PIO_FILES.items():
        path = root / relative_path
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            modified.append(relative_path)
            details[relative_path] = error_details(error)
            continue
        if digest != expected:
            modified.append(relative_path)
            details[relative_path] = {"expected": expected, "actual": digest}
    add_check(
        checks,
        "vendor-lcd-pio-unmodified",
        not modified,
        modified=modified,
        **details,
    )


def verify_portable(
    checks: List[Check], root: Path, include_target_schema: bool = True
) -> None:
    verify_generated_board(checks, root)
    require_text(
        checks,
        root,
        "bsp/include/picocalc/board.h",
        "board-static-asserts",
        [
            '#include "picocalc/board_generated.h"',
            "static_assert(kLcdSck == 10",
            "static_assert(kSdMiso == 16",
            "static_assert(kKeyboardSda == 6",
            "static_assert(kAudioLeft == 26",
            "static_assert(kLcdMaxPixelsPerCs == 160",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/display.cpp",
        "lcd-hwspi-rgb888-adapter",
        [
            '#include "vendor/lcd_hwspi_rgb888.h"',
            "vendor::lcd_hwspi_rgb888::init();",
            "vendor::lcd_hwspi_rgb888::begin_window(",
            "vendor::lcd_hwspi_rgb888::write_pixels_rgb565(",
            "vendor::lcd_hwspi_rgb888::write_solid_rgb565(",
            "vendor::lcd_hwspi_rgb888::readback_rgb888(",
            "rgb888_to_rgb565(",
            "PixelVerifyResult verify_pixels(",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/psram.cpp",
        "psram-safe-clock-policy",
        [
            "reference=pico_rescue",
            "candidates=",
            "2.00/0,3.00/0,1.50/1",
            "1.00/0,1.50/0,2.00/0,3.00/0,4.00/0",
            "psram_spi_init_clkdiv(pio1, -1, clkdiv, fudge)",
            "fudge=%u",
            "self_test()",
            "max_transfer_chunk_bytes",
            "write_us=%lu read_us=%lu",
            "reason=no_safe_configuration",
        ],
    )
    require_absent(
        checks,
        root,
        "bsp/src/psram.cpp",
        "psram-no-unsafe-250mhz-candidates",
        [
            "candidates[candidate_count++] = 1.0f",
            "candidates[candidate_count++] = 1.2f",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/audio.cpp",
        "audio-public-adapter",
        [
            '#include "picocalc/audio.h"',
            "picoment::audio_pwm::init_stream();",
            "picoment::audio_pwm::init_fixed_sine();",
            "picoment::audio_pwm::start_stream();",
            "picoment::audio_pwm::stop_stream();",
            "picoment::audio_pwm::write_sample(",
        ],
    )
    verify_audio_dma_restart(checks, root)
    require_text(
        checks,
        root,
        "bsp/include/picocalc/psram_buffer.h",
        "psram-bounds-buffer-api",
        [
            "class Buffer",
            "capacity_bytes",
            "return psram::read(",
            "return psram::write(",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/bsp.cpp",
        "audio-mode-selection",
        [
            "PICOCALC_AUDIO_REFERENCE_TONE",
            "audio::init_reference_tone()",
            "audio::init()",
            "mode=%s output=%s",
        ],
    )
    require_text(
        checks,
        root,
        "templates/rp2040-basic/CMakeLists.txt",
        "template-audio-mode-selection",
        [
            "PICOCALC_AUDIO_REFERENCE_TONE",
            'PICOCALC_LCD_VARIANT "pio-rgb565"',
            "PICOCALC_PSRAM_LCD_COEXIST_TEST",
            "0.8.4-a-hwspi-rgb888-rgb666-compat",
            "0.8.4-b-pio-rgb565-default",
            "0.8.4-b-pio-rgb565-psram-lcd-coexist",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/include/picocalc/psram.h",
        "psram-lcd-coexist-api",
        [
            "CoexistenceDisplayStep",
            "CoexistenceResult",
            "probe_lcd_coexistence",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/psram.cpp",
        "psram-lcd-coexist-probe",
        [
            "[PICOCALC][PSRAM][COEX]",
            "configure_candidate",
            "display_failures",
            "psram_failures",
            "bool restored = false",
            "reason=first_coexistence_pass",
        ],
    )
    require_text(
        checks,
        root,
        "templates/rp2040-basic/app/main.cpp",
        "template-psram-lcd-coexist-test",
        [
            "PICOCALC_PSRAM_LCD_COEXIST_TEST",
            "coexist_display_step",
            "probe_lcd_coexistence",
            "frames_per_candidate=120",
        ],
    )
    for example in ("lcd.cpp", "keyboard.cpp", "sd.cpp", "psram.cpp", "audio_stream.cpp"):
        require_text(
            checks,
            root,
            "templates/rp2040-basic/examples/" + example,
            "copyable-example-" + example[:-4],
            ["copy_"],
        )
    require_text(
        checks,
        root,
        "bsp/vendor/audio_picoment/platform/picocalc_audio_pwm.cpp",
        "audio-proven-reference",
        [
            "constexpr uint32_t kHalfSamples = 128",
            "constexpr uint32_t kRingSamples = 512",
            "kErrorDiffusionPercent = 100",
            "dma_timer_set_fraction(",
            "hardware/pwm.h",
            "hardware/dma.h",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/vendor/rp2040-psram/psram_spi.c",
        "psram-vendored-pio-driver",
        [
            "psram_spi_init_clkdiv",
            "0x66u",
            "0x99u",
            "pio_spi_write_read_dma_blocking",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/vendor/lcd_hwspi_rgb888.cpp",
        "lcd-hwspi-rgb888-vendored-transport",
        [
            "spi_init(spi1, board::kLcdSpiHz)",
            "sleep_ms(200)",
            "write_command(0x3a); write_data1(0x66)",
            "CASET, RASET",
            "g_window_open = true",
            "spi_set_baudrate(spi1, kReadbackSpiHz)",
            "spi_read_blocking(spi1, 0xff, result->raw",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/display_pio_rgb565.cpp",
        "lcd-pio-rgb565-wiring",
        [
            # B must stay an adapter over the vendored driver. These tokens fail
            # the moment transport logic is written back into this file.
            '#include "vendor/lcd_rgb565_pio.h"',
            "lcd_rgb565_pio_init(false)",
            "lcd_rgb565_pio_set_window(",
            "lcd_rgb565_pio_write_blocking(",
            "kTileSide = board::kLcdMaxPixelsPerCs",
            "kPixelsPerCall = static_cast<size_t>(board::kLcdMaxPixelsPerCs)",
            "tile_y += kTileSide",
            "driver=vendor/lcd_rgb565_pio.cpp",
            "set_bitbang_mode(true)",
            "pio_sm_set_enabled(pio0, kSm, false)",
            "bitbang_read_byte_falling()",
            "bitbang_set_read_window(",
            "format=rgb565",
            "PixelVerifyResult verify_pixels(",
        ],
    )
    require_absent(
        checks,
        root,
        "bsp/src/display_pio_rgb565.cpp",
        "lcd-pio-rgb565-no-local-transport",
        [
            "lcd_spi_min_program_init(",
            "pio_add_program(",
            "reset_panel(",
            "write_command1(",
        ],
    )
    verify_vendored_lcd_pio(checks, root)
    require_text(
        checks,
        root,
        "bsp/CMakeLists.txt",
        "lcd-variant-selection",
        [
            'PICOCALC_LCD_VARIANT "pio-rgb565"',
            "src/display.cpp",
            "src/display_pio_rgb565.cpp",
            "vendor/lcd_rgb565_pio.cpp",
            "pico_generate_pio_header(picocalc_bsp ${CMAKE_CURRENT_LIST_DIR}/vendor/lcd_spi_min.pio)",
            "hardware_pio",
            "hardware_dma",
        ],
    )
    require_text(
        checks,
        root,
        "tools/picocalc.py",
        "lcd-cli-default-pio-rgb565",
        [
            'marker = "psram-lcd-coexist" if coexistence_test',
            'default="pio-rgb565"',
            "default: pio-rgb565",
            "--psram-lcd-coexist-test",
        ],
    )
    verify_lcd_transactions(checks, root)
    require_text(
        checks,
        root,
        "bsp/src/sdcard.cpp",
        "sd-known-good-sequence",
        [
            "spi_init(kSpi, board::kSdInitHz)",
            "spi_set_baudrate(kSpi, board::kSdRunHz)",
            "command(0, 0, 0x95",
            "command(8, 0x000001aau, 0x87",
            "command(55,",
            "command(41, 0x40000000u",
            "command(58,",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/src/filesystem.cpp",
        "fatfs-read-write-smoke",
        [
            "f_mount(",
            "FA_CREATE_ALWAYS | FA_WRITE",
            "f_write(",
            "f_sync(",
            "FA_READ",
            "f_read(",
            "memcmp(",
            "f_unlink(",
        ],
    )
    require_text(
        checks,
        root,
        "bsp/include/picocalc/filesystem.h",
        "public-filesystem-mutation-api",
        [
            "Error open_write_truncate(",
            "WriteResult write(",
            "Error sync(",
            "Error stat(",
            "Error remove(",
            "Error rename(",
            "NotFound",
            "WriteFailed",
            "SyncFailed",
            "RemoveFailed",
            "RenameFailed",
        ],
    )
    verify_template_smoke(checks, root)
    verify_catalog(checks, root)
    verify_hardware_validation(checks, root)
    verify_host_backend(checks, root)
    verify_release_conditions(checks, root)
    verify_r0_contract(checks, root)
    if include_target_schema:
        verify_target_schema(checks, root)


def verify_target_schema(checks: List[Check], root: Path) -> None:
    """Verify the registry, schemas, attestations, and pinned R3 evidence."""
    verify_firmware_targets(checks, root)
    verify_firmware_validation(checks, root)
    verify_r4_backend_role_ci(checks, root)
    verify_r3_contract(checks, root)
    verify_r5_performance(checks, root)
    verify_r5_hardware_correlation(checks, root)
    verify_opt0_idle_profile(checks, root)
    verify_opt0_behavior_contract(checks, root)
    verify_opt1a_exact_idle_fast_forward(checks, root)
    verify_opt1b_serial_fast_path(checks, root)
    verify_opt2b_running_event_horizon(checks, root)
    verify_opt2c_exact_batching(checks, root)
    verify_opt2d_lever_comparison(checks, root)
    verify_opt2e_pio_pull_stall(checks, root)
    verify_opt2f_stationary_pin_bulk(checks, root)
    verify_opt2g_uart_deadline(checks, root)
    verify_next1_picoedit_blind_contract(checks, root)
    verify_next1_picoedit_hardware_correlation(checks, root)
    verify_next2_multicore_contract(checks, root)
    verify_next2_multicore_acceptance(checks, root)
    verify_next2_multicore_v2_evidence(checks, root)
    verify_next2_audio_contract(checks, root)
    verify_next3_negative_conformance(checks, root)
    verify_opt3a_xip_cursor_profile(checks, root)
    verify_opt3b_xip_decode_cursor(checks, root)
    verify_opt3c_compact_dispatch_key(checks, root)


def verify_next3_negative_conformance(checks: List[Check], root: Path) -> None:
    """Verify NEXT-3 definitions, audits, fault artifact, and hardware attempt."""
    name = "next3:negative-conformance-contract"
    base = root / "firmware-validation"
    paths = {
        "case_schema": base / "negative-conformance-case.schema.json",
        "kpi_schema": base / "negative-conformance-kpi.schema.json",
        "contract": base / "contracts/next3-negative-conformance-v1.json",
        "initial_kpi": base / "records/next3-0-20260810-01/kpi.json",
        "audit": base / "records/next3-lcd-031-audit-20260810-01/record.json",
        "post_audit_kpi": base / "records/next3-1-20260810-01/kpi.json",
        "fault": base / "records/next3-lcd-cs-fault-v1-20260810-01/record.json",
        "pre_hardware_kpi": base / "records/next3-fault-build-20260810-01/kpi.json",
        "fault_hardware": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/record.json",
        "current_kpi": base / "records/next3-hardware-attempt-20260810-01/kpi.json",
        "hardware_notes": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/notes.md",
        "hardware_uart": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/evidence/uf2loader-uart.log",
        "hardware_photo": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/evidence/uf2loader-final.jpg",
        "fault_bundle": root / "provenance/picocalc-next3-lcd-fault-v1.bundle",
        "document": root / "docs/NEXT3_NEGATIVE_CONFORMANCE.md",
    }
    expected_hashes = {
        "case_schema": "3153f4a902f8a99b938a01bafadffd019f9a9180fe3d4c79eaf890f84359c0ef",
        "kpi_schema": "bef7639eba4a60af8d2ceed9176655b31b6f26763f3d8777a344e00f873a82a5",
        "contract": "c2cc54339efcc5a3eb888a216d76ac0c067f53bd98397e0fad098afb6e77eb80",
        "initial_kpi": "afdf414550b7715531e5db3cdd2f355687853969e96eb0090374e86e6018ebdc",
        "audit": "a02130b8c0b6326b45218a26712d6f02ac0af9977ec462c076643caed90ead4c",
        "post_audit_kpi": "2c421fb178650955207b59975f39facba0aea0a58f5ba4d4f1d2bb1b7e752843",
        "fault": "056642382c11d553b137054b4e2385557fa67b179bfd47965012ae9217c3c4ab",
        "pre_hardware_kpi": "4f98fff5d79c6cc355a52c8a360a01021209dbca3f5be0d138c06a84ba844bb5",
        "fault_hardware": "60187ecb99c179ae7d234f02d99dbee18ca641f8793911265265b699d8287a14",
        "current_kpi": "0fbcc19e330032936048fb350a3ccc863b537d49e4d6353c05134676328f69db",
        "hardware_notes": "21611323ed4552e7718d06534efc4ce6e1205c4ac841f6217787632604c6986d",
        "hardware_uart": "e3187f9a2ce38eaae9361a0a2e1723ef561f7716d9d51f67cc03909fff755550",
        "hardware_photo": "84ba4e05ff16b8a5fa20a35a18f43bc5dfa6bd62cdd2e0533638a9cf58324f20",
        "fault_bundle": "8824baed4577441da7d58b3a52502c8a7392e029e2bfb53cbfddd4912b7b4ad6",
        "document": "35ca9e5e1bdc824b2820270c600df2c5dd0c2d815e5158dcfdf07dd252edbff0",
    }

    def evidence_records_valid(items: Any) -> bool:
        if not isinstance(items, list):
            return False
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                return False
            relative = item.get("path")
            expected = item.get("sha256")
            record_id = item.get("record_id")
            if not all(isinstance(value, str) and value for value in (relative, expected, record_id)):
                return False
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                return False
            if relative in seen:
                return False
            seen.add(relative)
            evidence_path = root / relative
            if not evidence_path.is_file() or sha256(evidence_path) != expected:
                return False
            try:
                evidence = load_json(evidence_path)
            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
                return False
            if evidence.get("record_id") != record_id:
                return False
        return True

    def snapshot_valid(
        snapshot: Any,
        *,
        candidates: int,
        audit_failures: int,
        inconclusive: int,
        records: int,
    ) -> bool:
        if not isinstance(snapshot, dict):
            return False
        positive = snapshot.get("positive_correlations", {})
        negative = snapshot.get("negative_conformance", {})
        rates = snapshot.get("rates", {})
        positive_records = positive.get("records")
        negative_records = negative.get("records")
        return all(
            (
                snapshot.get("schema_version") == 1,
                snapshot.get("roadmap_package") == "NEXT-3",
                snapshot.get("contract_id") == "next3-negative-conformance-v1-20260810",
                positive.get("completed_count") == 5,
                positive.get("completed_count") == len(positive_records),
                positive.get("emulator_pass_hardware_fail_count") == 0,
                evidence_records_valid(positive_records),
                negative.get("candidates_audited") == candidates,
                negative.get("hardware_confirmed_cases") == 0,
                negative.get("correct_detections") == 0,
                negative.get("false_accepts") == 0,
                negative.get("wrong_reason_failures") == 0,
                negative.get("artifact_audit_failures") == audit_failures,
                negative.get("inconclusive_cases") == inconclusive,
                len(negative_records) == records,
                evidence_records_valid(negative_records),
                rates.get("state") == "no_negative_denominator",
                rates.get("denominator") == negative.get("hardware_confirmed_cases") == 0,
                rates.get("detection_rate") is None,
                rates.get("false_accept_rate") is None,
            )
        )

    try:
        case_schema = load_json(paths["case_schema"])
        kpi_schema = load_json(paths["kpi_schema"])
        contract = load_json(paths["contract"])
        initial = load_json(paths["initial_kpi"])
        audit = load_json(paths["audit"])
        post_audit = load_json(paths["post_audit_kpi"])
        fault = load_json(paths["fault"])
        pre_hardware = load_json(paths["pre_hardware_kpi"])
        fault_hardware = load_json(paths["fault_hardware"])
        current = load_json(paths["current_kpi"])
        candidate = contract["first_candidate"]
        admission = contract["admission"]
        kpi_policy = contract["kpi_policy"]
        artifact = audit["artifact_audit"]
        fault_artifact = fault["artifact_audit"]
        aligned = all(
            (
                all(path.is_file() and sha256(path) == expected_hashes[key] for key, path in paths.items()),
                case_schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
                case_schema.get("properties", {}).get("schema_version", {}).get("const") == 1,
                "wrong_reason_failure"
                in case_schema.get("properties", {}).get("classification", {}).get("enum", []),
                kpi_schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
                kpi_schema.get("properties", {}).get("schema_version", {}).get("const") == 1,
                contract.get("schema_version") == 1,
                contract.get("contract_id") == "next3-negative-conformance-v1-20260810",
                contract.get("status") == "frozen_before_first_negative_emulator_run",
                admission.get("same_build_bin_and_uf2_required") is True,
                admission.get("pico_sdk_version_and_commit_required") is True,
                admission.get("clean_reproducible_build_required") is True,
                admission.get("defect_oracle_frozen_before_emulator_run") is True,
                admission.get("unrelated_emulator_failure_is_not_detection") is True,
                kpi_policy.get("negative_denominator") == "hardware_confirmed_negative_cases",
                kpi_policy.get("zero_denominator_representation")
                == {
                    "state": "no_negative_denominator",
                    "detection_rate": None,
                    "false_accept_rate": None,
                },
                kpi_policy.get("never_describe_zero_denominator_as_zero_percent") is True,
                kpi_policy.get("wrong_reason_failure_counts_as_correct_detection") is False,
                candidate.get("historical_source_commit_claim")
                == "51380fa836e58373d1747904d46b28307ac65fa2",
                candidate.get("historical_uf2_sha256_claim")
                == "ae182a6947e46ee9f927e5dfc1b539a448b45f846cd5935eb69c9782dd802c4f",
                snapshot_valid(
                    initial, candidates=0, audit_failures=0, inconclusive=0, records=0
                ),
                snapshot_valid(
                    post_audit, candidates=1, audit_failures=1, inconclusive=0, records=1
                ),
                snapshot_valid(
                    pre_hardware,
                    candidates=2,
                    audit_failures=1,
                    inconclusive=0,
                    records=2,
                ),
                snapshot_valid(
                    current, candidates=2, audit_failures=1, inconclusive=1, records=2
                ),
                audit.get("schema_version") == 1,
                audit.get("record_id") == "next3-lcd-031-audit-20260810-01",
                audit.get("status") == "artifact_audit_failed",
                audit.get("classification") == "artifact_not_reproducible",
                audit.get("candidate", {}).get("source_kind") == "historical_artifact",
                artifact.get("reproducibility") == "not_reproducible",
                artifact.get("source_commit")
                == "51380fa836e58373d1747904d46b28307ac65fa2",
                artifact.get("sdk_version") == "2.0.0",
                artifact.get("sdk_commit") is None,
                artifact.get("bin_sha256") is None,
                artifact.get("uf2_sha256")
                == "ae182a6947e46ee9f927e5dfc1b539a448b45f846cd5935eb69c9782dd802c4f",
                artifact.get("same_build_bin_and_uf2") is None,
                len(artifact.get("blocking_gaps", [])) == 7,
                audit.get("hardware_observation", {}).get("status") == "pending",
                audit.get("reason_match", {}).get("status") == "pending",
                audit.get("kpi_effect")
                == {
                    "negative_denominator_delta": 0,
                    "correct_detection_delta": 0,
                    "false_accept_delta": 0,
                },
                fault.get("schema_version") == 1,
                fault.get("record_id") == "next3-lcd-cs-fault-v1-20260810-01",
                fault.get("status") == "artifact_reproduced",
                fault.get("classification") == "pending",
                fault.get("candidate", {}).get("source_kind")
                == "explicit_fault_injection",
                fault_artifact.get("reproducibility") == "reproduced",
                fault_artifact.get("source_commit")
                == "d7f0668db17e74dfa94d10458487e627a880c4bc",
                fault_artifact.get("sdk_version") == "2.2.0",
                fault_artifact.get("sdk_commit")
                == "a1438dff1d38bd9c65dbd693f0e5db4b9ae91779",
                fault_artifact.get("bin_sha256")
                == "7ffc6335b3d65276f173954244c8eb481201c9805c6904f192b7b62ea87a5f0f",
                fault_artifact.get("uf2_sha256")
                == "74aa594d86666103f947b1905dafb25fd57cd6c49bf3397a9fb340d577c1d6c0",
                fault_artifact.get("same_build_bin_and_uf2") is True,
                fault_artifact.get("blocking_gaps") == [],
                fault.get("defect_oracle", {}).get("frozen_before_emulator_run") is True,
                fault.get("emulator_observation", {}).get("status") == "pending",
                fault.get("hardware_observation", {}).get("status") == "pending",
                fault.get("reason_match", {}).get("status") == "pending",
                fault.get("kpi_effect")
                == {
                    "negative_denominator_delta": 0,
                    "correct_detection_delta": 0,
                    "false_accept_delta": 0,
                },
                fault_hardware.get("schema_version") == 1,
                fault_hardware.get("record_id")
                == "next3-lcd-cs-fault-v1-hardware-attempt-20260810-01",
                fault_hardware.get("status") == "hardware_observed",
                fault_hardware.get("classification") == "inconclusive",
                fault_hardware.get("artifact_audit", {}).get("source_commit")
                == "d7f0668db17e74dfa94d10458487e627a880c4bc",
                fault_hardware.get("artifact_audit", {}).get("bin_sha256")
                == "7ffc6335b3d65276f173954244c8eb481201c9805c6904f192b7b62ea87a5f0f",
                fault_hardware.get("artifact_audit", {}).get("uf2_sha256")
                == "74aa594d86666103f947b1905dafb25fd57cd6c49bf3397a9fb340d577c1d6c0",
                fault_hardware.get("hardware_observation", {}).get("status") == "complete",
                fault_hardware.get("hardware_observation", {}).get("result") == "fail",
                len(fault_hardware.get("hardware_observation", {}).get("evidence", [])) == 6,
                fault_hardware.get("emulator_observation", {}).get("status") == "pending",
                fault_hardware.get("emulator_observation", {}).get("result") == "pending",
                fault_hardware.get("reason_match", {}).get("status") == "mismatch",
                fault_hardware.get("reason_match", {}).get("emulator_reason") is None,
                fault_hardware.get("kpi_effect")
                == {
                    "negative_denominator_delta": 0,
                    "correct_detection_delta": 0,
                    "false_accept_delta": 0,
                },
            )
        )
        add_check(
            checks,
            name,
            aligned,
            contract_id=contract.get("contract_id"),
            positive_correlations=current.get("positive_correlations", {}).get("completed_count"),
            negative_denominator=current.get("rates", {}).get("denominator"),
            rate_state=current.get("rates", {}).get("state"),
            candidates_audited=current.get("negative_conformance", {}).get("candidates_audited"),
            first_candidate_classification=audit.get("classification"),
            explicit_fault_status=fault_hardware.get("status"),
            explicit_fault_classification=fault_hardware.get("classification"),
            inconclusive_cases=current.get("negative_conformance", {}).get("inconclusive_cases"),
            emulator_first_run=fault_hardware.get("emulator_observation", {}).get("status"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt0_behavior_contract(checks: List[Check], root: Path) -> None:
    """Verify the immutable OPT0-B behavior projection and event digests."""
    try:
        record_root = root / "firmware-validation/records/opt0-b-20260808-01"
        artifact_path = record_root / "behavior-trace.json"
        report_path = record_root / "run-report.json"
        artifact = load_json(artifact_path)
        report = load_json(report_path)
        trace = artifact["behavior_projection"]["event_trace"]
        domains = {item["name"]: item for item in trace["domains"]}
        expected_counts = {
            "clock": 8,
            "irq_exception": 1_110,
            "pio_gpio": 1,
            "psram": 85_621_393,
            "lcd": 84_708_286,
            "dma_dreq": 82,
            "timer_pwm": 3_154_379,
            "serial_bus": 12_847,
            "scenario_input": 146,
        }
        canonical_projection = json.dumps(
            artifact["behavior_projection"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        aligned = all(
            (
                sha256(artifact_path)
                == "6a4e9c09afb3870eda6fd04ecef0016f740fd1138fbf417b6e3a8dfc4c2a1160",
                sha256(report_path)
                == "8e583d9526903bc9e4254a0818cd9dcca89fa2d289aff768273743fca12f054a",
                artifact.get("schema_version") == 1,
                artifact.get("mode") == "correctness_trace_on",
                artifact.get("valid_for_wall_time") is False,
                artifact.get("backend_build")
                == {
                    "commit": "763595fedefa08886b41298be79bff69324ac51f",
                    "dirty": False,
                },
                artifact.get("normal_report_schema_version") == 8,
                artifact.get("behavior_projection_encoding") == "sorted-json-v1",
                artifact.get("behavior_sha256")
                == hashlib.sha256(canonical_projection).hexdigest()
                == "3ee0dff39b10b5863aa28326189f70ba553e714c1e9ada403db1ad4622a1daf3",
                trace.get("schema_version") == 1,
                trace.get("canonical_encoding") == "PICOEM-EVENT-v1",
                trace.get("streaming") is True,
                trace.get("retains_event_array") is False,
                trace.get("sha256")
                == "448b0a00575b6748445906a5863c508f2fb86910fba73137605d66147bd191d9",
                set(domains) == set(expected_counts),
                all(
                    domains[name].get("events") == count
                    and re.fullmatch(r"[0-9a-f]{64}", domains[name].get("sha256", ""))
                    for name, count in expected_counts.items()
                ),
                trace.get("total_events") == sum(expected_counts.values()),
                report.get("schema_version") == 8,
                report.get("backend_build") == artifact.get("backend_build"),
                report.get("verdict", {}).get("status") == "pass",
                report.get("stop_reason") == "scenario_done",
                report.get("cycles") == 927_528_660,
                report.get("elapsed_us") == 3_715_000,
                report.get("uart", {}).get("sha256")
                == "bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c",
                report.get("framebuffer", {}).get("rgb565_sha256")
                == "f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2",
                len(report.get("scenario", {}).get("steps", [])) == 85,
            )
        )
        add_check(
            checks,
            "opt0-b:behavior-streaming-contract",
            aligned,
            backend_commit=artifact.get("backend_build", {}).get("commit"),
            behavior_sha256=artifact.get("behavior_sha256"),
            event_sha256=trace.get("sha256"),
            total_events=trace.get("total_events"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        add_check(
            checks,
            "opt0-b:behavior-streaming-contract",
            False,
            **error_details(error),
        )


def verify_opt1a_exact_idle_fast_forward(checks: List[Check], root: Path) -> None:
    """Verify the immutable OPT1-A candidate record and its cross-artifact digests."""
    name = "opt1-a:exact-idle-fast-forward"
    try:
        record_root = root / "firmware-validation/records/opt1-a-20260808-01"
        record = load_json(record_root / "record.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "realtime-performance.json")
        template_report = load_json(record_root / "template-b-report.json")
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1a"
        )
        exact = record["exactness"]
        contract = record["target"]
        behavior_contract = record["behavior_contract"]
        trace = behavior["behavior_projection"]["event_trace"]
        domains = trace["domains"]
        expected_domain_names = {
            "clock", "irq_exception", "pio_gpio", "psram", "lcd",
            "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
        }
        projection = json.dumps(
            behavior["behavior_projection"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        stats = performance["statistics"]
        template = record["additional_workloads"]["picocalc_template_b"]
        aligned = all((
            record.get("result") == "pass",
            target.get("id") == contract.get("id") == exact.get("target") == "picotetris-opt1a",
            target.get("revision") == contract.get("revision") == 3,
            contract.get("contract_sha256")
            == picocalc.firmware_target_contract_sha256(target)
            == "12151d51a47bac4164a4664dae4e354dbe18c4342298402efba6ff9898f7a9b1",
            target.get("backend", {}).get("accepted") == exact.get("backend_commit") == "c68c58f6c37fb31eb9313566c8b16883db9063b6",
            report.get("backend_build", {}).get("commit") == exact.get("backend_commit"),
            report.get("backend_build", {}).get("dirty") is False,
            report.get("verdict", {}).get("status") == "pass",
            report.get("cycles") == exact.get("cycles") == 927528660,
            report.get("elapsed_us") == exact.get("elapsed_us") == 3715000,
            report.get("uart", {}).get("sha256") == exact.get("uart_sha256"),
            report.get("framebuffer", {}).get("rgb565_sha256") == exact.get("framebuffer_rgb565_sha256"),
            report.get("scenario", {}).get("status") == "pass",
            report.get("scenario", {}).get("steps_total") == 85,
            len(report.get("scenario", {}).get("steps", [])) == exact.get("steps_total") == 85,
            picocalc.normalized_json_sha256(report) == exact.get("normalized_report_sha256") == target.get("acceptance", {}).get("normalized_report_sha256"),
            picocalc.normalized_json_sha256(report.get("scenario", {}).get("steps")) == exact.get("timeline_sha256") == target.get("acceptance", {}).get("timeline_sha256"),
            behavior.get("schema_version") == 1,
            trace.get("schema_version") == behavior_contract.get("schema_version") == 2,
            behavior_contract.get("behavior_sha256")
            == hashlib.sha256(projection).hexdigest()
            == behavior.get("behavior_sha256"),
            trace.get("sha256") == behavior_contract.get("event_stream_sha256"),
            trace.get("total_events") == behavior_contract.get("total_events") == 173498680,
            {item.get("name") for item in domains} == expected_domain_names,
            all(re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) and isinstance(item.get("events"), int) for item in domains),
            len(performance.get("measurements", []))
            == exact.get("runs")
            == record.get("performance", {}).get("measured_runs")
            == 10,
            performance.get("method", {}).get("warmup_runs_excluded")
            == record.get("performance", {}).get("warmup_runs_excluded")
            == 1,
            performance.get("determinism", {}).get("all_reports_identical") is True,
            performance.get("determinism", {}).get("all_uart_identical") is True,
            performance.get("determinism", {}).get("all_snapshots_identical") is True,
            stats.get("wall_seconds", {}).get("median") == 27.122874482999997,
            stats.get("real_time_percent", {}).get("median") == 13.696960105316276,
            record.get("hardware_correlation_completed") is False,
            record.get("optimization_status") == "candidate",
            template_report.get("backend_build", {}).get("commit")
            == exact.get("backend_commit"),
            template_report.get("backend_build", {}).get("dirty") is False,
            template_report.get("firmware", {}).get("sha256")
            == template.get("firmware_sha256")
            == "1e6abac252c28a349d172254c0bc08976786023597a1c44002bfcb1bfbd02a3d",
            template_report.get("verdict", {}).get("status")
            == template.get("candidate_result")
            == "pass",
            template_report.get("stop_reason") == "cycle_limit",
            template.get("behavior_report_without_backend_byte_identical") is True,
            template.get("uart_byte_identical") is True,
            template.get("screening_is_formal_benchmark") is False,
            all((record_root / path).is_file() for path in record.get("artifacts", {}).values()),
        ))
        add_check(checks, name, aligned, target=target.get("id"), backend_commit=exact.get("backend_commit"),
                  behavior_sha256=behavior.get("behavior_sha256"), event_sha256=trace.get("sha256"),
                  total_events=trace.get("total_events"), measured_runs=len(performance.get("measurements", [])))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, StopIteration, json.JSONDecodeError) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt1b_serial_fast_path(checks: List[Check], root: Path) -> None:
    """Verify the immutable promoted OPT1-B record and cross-artifact digests."""
    name = "opt1-b:serial-fast-path"
    try:
        record_root = root / "firmware-validation/records/opt1-b-20260808-01"
        record = load_json(record_root / "record.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "realtime-performance.json")
        template_report = load_json(record_root / "template-b-report.json")
        r5_equivalence = load_json(record_root / "r5-equivalence-report.json")
        hello_report = load_json(record_root / "hello-report.json")
        opt1a_root = root / "firmware-validation/records/opt1-a-20260808-01"
        opt1a_behavior = load_json(opt1a_root / "behavior-trace.json")
        opt1a_template_report = load_json(opt1a_root / "template-b-report.json")
        r5_preflight_report = load_json(
            root / "firmware-validation/records/r5-preflight-20260808-01/run-report.json"
        )
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )
        exact = record["exactness"]
        contract = record["target"]
        behavior_contract = record["behavior_contract"]
        template = record["additional_workloads"]["picocalc_template_b"]
        hello = record["additional_workloads"]["official_picocalc_hello"]
        trace = behavior["behavior_projection"]["event_trace"]

        projection = json.dumps(
            behavior["behavior_projection"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        wall_seconds = performance.get("statistics", {}).get("wall_seconds", {})
        wall_seconds_median = wall_seconds.get("median", performance.get("statistics", {}).get("median"))
        r5_equivalence_reference = record.get("r5_equivalence", {})
        without_backend = lambda value: {
            key: item for key, item in value.items()
            if key not in {"backend_commit", "backend_build"}
        }
        aligned = all((
            record.get("record_id") == "opt1-b-20260808-01",
            record.get("result") == "pass",
            record.get("optimization_status") == "promoted",
            record.get("hardware_correlation_completed") is True,
            target.get("id") == contract.get("id") == exact.get("target") == "picotetris-opt1b",
            target.get("revision") == contract.get("revision") == 5,
            contract.get("contract_sha256")
            == picocalc.firmware_target_contract_sha256(target)
            == "f3e8c251f6f9d9e6da0c8e2e43b474890db740474ac0b6a762927f316a1afc6f",
            target.get("backend", {}).get("accepted") == exact.get("backend_commit") == "e985a9d7ecb51ef760506a105edd34e31cf9b5f1",
            report.get("backend_build", {}).get("commit") == exact.get("backend_commit"),
            report.get("backend_build", {}).get("dirty") is False,
            report.get("verdict", {}).get("status") == "pass",
            report.get("cycles") == exact.get("cycles") == 927528660,
            report.get("elapsed_us") == exact.get("elapsed_us") == 3715000,
            report.get("uart", {}).get("sha256") == exact.get("uart_sha256"),
            report.get("framebuffer", {}).get("rgb565_sha256")
            == exact.get("framebuffer_rgb565_sha256"),
            report.get("scenario", {}).get("status") == "pass",
            report.get("scenario", {}).get("steps_total") == 85,
            len(report.get("scenario", {}).get("steps", [])) == exact.get("steps_total") == 85,
            picocalc.normalized_json_sha256(report) == exact.get("normalized_report_sha256"),
            picocalc.normalized_json_sha256(report.get("scenario", {}).get("steps"))
            == exact.get("timeline_sha256"),
            behavior.get("schema_version") == 1,
            trace.get("schema_version") == behavior_contract.get("schema_version") == 2,
            behavior_contract.get("behavior_sha256")
            == hashlib.sha256(projection).hexdigest()
            == behavior.get("behavior_sha256"),
            behavior.get("behavior_projection")
            == opt1a_behavior.get("behavior_projection"),
            trace.get("sha256") == behavior_contract.get("event_stream_sha256"),
            trace.get("total_events") == behavior_contract.get("total_events"),
            len(trace.get("domains", [])) == behavior_contract.get("domains") == 9,
            len(performance.get("measurements", []))
            == exact.get("runs")
            == record.get("performance", {}).get("measured_runs")
            == 10,
            performance.get("method", {}).get("warmup_runs_excluded")
            == record.get("performance", {}).get("warmup_runs_excluded")
            == 1,
            performance.get("determinism", {}).get("all_reports_identical") is True,
            performance.get("determinism", {}).get("all_uart_identical") is True,
            performance.get("determinism", {}).get("all_snapshots_identical") is True,
            wall_seconds_median
            == record.get("performance", {}).get("candidate_wall_seconds_median"),
            record.get("performance", {}).get("wall_time_reduction_percent")
            == 6.419972020632974,
            template.get("median_regression_percent")
            <= template.get("maximum_allowed_regression_percent", math.inf),
            template.get("maximum_allowed_regression_percent", math.inf)
            <= 3.0,
            template.get("behavior_report_without_backend_byte_identical") is True,
            record.get("r5_equivalence", {}).get("report_without_backend_byte_identical_to_r5_preflight")
            is True,
            without_backend(r5_equivalence) == without_backend(r5_preflight_report),
            hello.get("psram_matched") == 8388608,
            hello.get("psram_mismatched") == 0,
            hello_report.get("verdict", {}).get("status") == "pass",
            hello_report.get("backend_build", {}).get("commit") == exact.get("backend_commit"),
            hello_report.get("backend_build", {}).get("dirty") is False,
            hello_report.get("psram", {}).get("verify", {}).get("matched")
            == hello.get("psram_matched"),
            hello_report.get("psram", {}).get("verify", {}).get("mismatched")
            == hello.get("psram_mismatched"),
            hello_report.get("uart", {}).get("sha256") == hello.get("uart_sha256"),
            hello_report.get("framebuffer", {}).get("rgb565_sha256")
            == hello.get("framebuffer_rgb565_sha256"),
            all(
                (
                    (record_root / path).is_file()
                    for path in record.get("artifacts", {}).values()
                )
            ),
            r5_equivalence.get("verdict", {}).get("status") == "pass",
            r5_equivalence.get("backend_commit") == exact.get("backend_commit"),
            r5_equivalence.get("firmware", {}).get("sha256")
            == record.get("r5_equivalence", {}).get("firmware_sha256"),
            record.get("r5_equivalence", {}).get("target") == "picotetris-r5",
            r5_equivalence.get("cycles") == r5_equivalence_reference.get("cycles"),
            r5_equivalence.get("elapsed_us") == r5_equivalence_reference.get("elapsed_us"),
            r5_equivalence.get("uart", {}).get("sha256")
            == r5_equivalence_reference.get("uart_sha256"),
            r5_equivalence.get("framebuffer", {}).get("rgb565_sha256")
            == r5_equivalence_reference.get("framebuffer_rgb565_sha256"),
            r5_equivalence.get("scenario", {}).get("status") == "pass",
            r5_equivalence.get("scenario", {}).get("steps_total")
            == r5_equivalence_reference.get("steps_total"),
            r5_equivalence.get("backend_build", {}).get("dirty") is False,
            template_report.get("backend_build", {}).get("commit")
            == exact.get("backend_commit"),
            template_report.get("backend_build", {}).get("dirty") is False,
            template.get("firmware_sha256")
            == template_report.get("firmware", {}).get("sha256"),
            template.get("candidate_result") == "pass",
            template_report.get("schema_version") == 8,
            template_report.get("verdict", {}).get("status") == "pass",
            template_report.get("uart", {}).get("sha256") == template.get("uart_sha256"),
            template_report.get("framebuffer", {}).get("rgb565_sha256")
            == template.get("framebuffer_rgb565_sha256"),
            template_report.get("stop_reason") == "cycle_limit",
            without_backend(template_report) == without_backend(opt1a_template_report),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=target.get("id"),
            backend_commit=exact.get("backend_commit"),
            reduction_percent=record.get("performance", {}).get("wall_time_reduction_percent"),
            measured_runs=len(performance.get("measurements", [])),
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, StopIteration, json.JSONDecodeError) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt2b_running_event_horizon(checks: List[Check], root: Path) -> None:
    """Verify the immutable OPT2-B running-horizon profile evidence."""
    name = "opt2-b:running-event-horizon-profile"
    expected_backend = "ac0c3052e6c28fcf235a33f98f3a96470d2966f1"
    expected_profile_sha = "27d462fd6acc98bcfd42de8ace12b43bccff168b47a624285ab1d42213ac6a80"
    expected_report_sha = "75867be9188dc020941fcbe35fd8f9761191ac4e4b910346c78f564c9c1ab042"
    expected_behavior_sha = "a7fc839a4f9381525018b2d21b0b425cb8e9b721d29e80cf1bf3390370585835"
    try:
        record_root = root / "firmware-validation/records/opt2-b-running-horizon-20260808-01"
        record = load_json(record_root / "record.json")
        run_report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        profile = load_json(record_root / "running-event-horizon-profile.json")
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )

        exact = record["exactness"]
        contract = record["target"]
        profiler = record["profiler"]
        measurements = record["measurements"]
        behavior_projection = behavior["behavior_projection"]
        trace = behavior_projection["event_trace"]
        projection = json.dumps(
            behavior_projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        exact_domains = set(item.get("name") for item in trace["domains"])
        expected_domains = {
            "clock", "irq_exception", "pio_gpio", "psram", "lcd",
            "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
        }
        aligned = all((
            record.get("record_id") == "opt2-b-running-horizon-20260808-01",
            record.get("result") == "profiler_complete",
            record.get("optimization_status") == "measurement_complete_candidate_not_implemented",
            contract.get("id") == target.get("id") == "picotetris-opt1b",
            contract.get("revision") == target.get("revision") == 5,
            contract.get("firmware_sha256") == target.get("artifacts", {}).get("bin_sha256"),
            contract.get("firmware_sha256") == profile.get("firmware", {}).get("sha256"),
            contract.get("firmware_sha256") == run_report.get("firmware", {}).get("sha256"),
            profiler.get("backend_commit") == expected_backend,
            profiler.get("schema_version") == 1,
            profiler.get("feature") == "event-horizon-profiler",
            profiler.get("instrumented") is True,
            profiler.get("valid_for_wall_time") is False,
            profiler.get("observed_gaps_are_safe_windows") is False,
            profiler.get("conservative_horizon_complete_for_current_model") is True,
            profiler.get("backend_dirty") is False,
            run_report.get("backend_build", {}).get("commit") == profiler.get("backend_commit"),
            run_report.get("backend_build", {}).get("dirty") is False,
            run_report.get("verdict", {}).get("status") == exact.get("verdict"),
            run_report.get("cycles") == exact.get("cycles") == 927528660,
            run_report.get("elapsed_us") == exact.get("elapsed_us") == 3715000,
            run_report.get("scenario", {}).get("status") == "pass",
            run_report.get("stop_reason") == exact.get("stop_reason") == "scenario_done",
            run_report.get("scenario", {}).get("steps_total") == exact.get("scenario_steps_total") == 85,
            len(run_report.get("scenario", {}).get("steps", [])) == exact.get("scenario_steps_passed") == 85,
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("valid_for_wall_time") is False,
            trace.get("schema_version") == 2,
            hashlib.sha256(projection).hexdigest() == exact.get("behavior_sha256")
            == behavior.get("behavior_sha256"),
            trace.get("sha256") == exact.get("event_stream_sha256"),
            trace.get("total_events") == exact.get("event_stream_total_events"),
            len(trace.get("domains", [])) == len(expected_domains),
            exact_domains == expected_domains,
            exact.get("all_nine_event_domains_match_opt1b") is True,
            exact.get("matches_registered_target") is True,
            exact.get("uart_sha256") == run_report.get("uart", {}).get("sha256"),
            exact.get("framebuffer_rgb565_sha256")
            == run_report.get("framebuffer", {}).get("rgb565_sha256"),
            record.get("interpretation", {}).get("production_optimization_added") is False,
            profile.get("schema_version") == 1,
            profile.get("kind") == "rp2040_serial_running_event_horizon_profile",
            profile.get("execution_model") == "Serial",
            profile.get("instrumented") is True,
            profile.get("valid_for_wall_time") is False,
            profile.get("step_quantum") == 1,
            profile.get("stop_reason") == "scenario_done",
            profile.get("observed_gaps_are_safe_windows") is False,
            profile.get("conservative_horizon_complete_for_current_model") is True,
            profile.get("backend_build", {}).get("commit") == profiler.get("backend_commit"),
            profile.get("backend_build", {}).get("dirty") is False,
            profile.get("run_cycles") == exact.get("cycles") == run_report.get("cycles"),
            profile.get("counters", {}).get("running_steps") == measurements.get("running_steps"),
            profile.get("counters", {}).get("total_running_cycles") == measurements.get("running_cycles"),
            profile.get("counters", {}).get("boundary_steps") == measurements.get("boundary_steps"),
            profile.get("counters", {}).get("candidate_dispatches") == measurements.get("candidate_dispatches"),
            profile.get("counters", {}).get("candidate_cycles") == measurements.get("candidate_cycles"),
            record.get("artifacts", {}).get("running_event_horizon_profile_sha256")
            == expected_profile_sha,
            sha256(record_root / record.get("artifacts", {}).get("running_event_horizon_profile"))
            == expected_profile_sha,
            record.get("artifacts", {}).get("run_report_sha256") == expected_report_sha,
            sha256(record_root / record.get("artifacts", {}).get("run_report"))
            == expected_report_sha,
            record.get("artifacts", {}).get("behavior_trace_sha256") == expected_behavior_sha,
            sha256(record_root / record.get("artifacts", {}).get("behavior_trace"))
            == expected_behavior_sha,
            all(
                (
                    record_root / relpath
                ).is_file()
                for key, relpath in record.get("artifacts", {}).items()
                if not key.endswith("_sha256")
            ),
            measurements.get("running_steps") > 0,
            measurements.get("candidate_dispatches") > 0,
            measurements.get("candidate_cycles") > 0,
        ))
        add_check(
            checks,
            name,
            aligned,
            target=contract.get("id"),
            backend_commit=profiler.get("backend_commit"),
            running_steps=measurements.get("running_steps"),
            running_cycles=measurements.get("running_cycles"),
            candidate_dispatches=measurements.get("candidate_dispatches"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt2c_exact_batching(checks: List[Check], root: Path) -> None:
    """Verify the rejected OPT2-C prototype's exactness and screening evidence."""
    name = "opt2-c:bounded-exact-batching"
    expected_artifact_hashes = {
        "performance": "a55c1cc1c46882bbc4a59501d37119396a9845bd78656b053ff28eeca1e03c54",
        "run_report": "497edb7c625d6221b242bd2e34401370308ee1fc0e94c1a2ced1e0ac93b5cb1c",
        "behavior_trace": "afed2d16bb77f823b10f1d6d2cb63ad974cc582f6fa4909719d3333e2ba2a147",
    }
    expected_domains = {
        "clock", "irq_exception", "pio_gpio", "psram", "lcd",
        "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
    }
    try:
        record_root = root / "firmware-validation/records/opt2-c-exact-batching-20260808-01"
        record = load_json(record_root / "record.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "performance-screening.json")
        baseline_behavior = load_json(
            root
            / "firmware-validation/records/opt2-b-running-horizon-20260808-01/behavior-trace.json"
        )
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )

        baseline = record["baseline"]
        candidate = record["candidate"]
        exact = record["exactness"]
        screening = record["performance_screening"]
        decision = record["decision"]
        artifacts = record["artifacts"]
        projection = behavior["behavior_projection"]
        trace = projection["event_trace"]
        domains = {item.get("name") for item in trace["domains"]}
        baseline_samples = performance["baseline_wall_seconds"]
        candidate_samples = performance["candidate_wall_seconds"]
        median_regression = (
            statistics.median(candidate_samples) / statistics.median(baseline_samples) - 1
        ) * 100

        aligned = all((
            record.get("record_id") == "opt2-c-exact-batching-20260808-01",
            record.get("result") == "rejected",
            record.get("optimization_status") == "reverted",
            record.get("opt2_overall_status") == "incomplete",
            baseline.get("backend_commit") == "ac0c3052e6c28fcf235a33f98f3a96470d2966f1",
            baseline.get("target") == target.get("id") == "picotetris-opt1b",
            baseline.get("firmware_sha256") == target.get("artifacts", {}).get("bin_sha256"),
            candidate.get("backend_commit") == "815ef5daa5117c29a8a7505d5e5f1929d92d5b99",
            candidate.get("revert_commit") == "c44c87f1ed4235343c5fd18860fde47b64b54325",
            candidate.get("hardware_quantum") == 1,
            candidate.get("max_batch_cycles") == 64,
            candidate.get("batches") == 8420,
            candidate.get("batched_cycles") == 23176,
            candidate.get("dispatches_elided") == 14756,
            candidate.get("max_observed_batch_cycles") == 13,
            report.get("backend_build", {}).get("commit") == candidate.get("backend_commit"),
            report.get("backend_build", {}).get("dirty") is False,
            report.get("firmware", {}).get("sha256") == baseline.get("firmware_sha256"),
            report.get("verdict", {}).get("status") == "pass",
            report.get("stop_reason") == "scenario_done",
            report.get("cycles") == exact.get("cycles") == 927528660,
            report.get("elapsed_us") == exact.get("elapsed_us") == 3715000,
            report.get("scenario", {}).get("status") == "pass",
            len(report.get("scenario", {}).get("steps", [])) == exact.get("steps_passed") == 85,
            exact.get("steps_total") == 85,
            exact.get("projection_byte_identical") is True,
            projection == baseline_behavior.get("behavior_projection"),
            behavior.get("behavior_sha256") == exact.get("behavior_sha256"),
            trace.get("sha256") == exact.get("event_stream_sha256"),
            trace.get("total_events") == exact.get("total_events"),
            domains == expected_domains,
            exact.get("all_nine_domain_counts_and_hashes_identical") is True,
            report.get("uart", {}).get("sha256") == exact.get("uart_sha256"),
            report.get("framebuffer", {}).get("rgb565_sha256")
            == exact.get("framebuffer_rgb565_sha256"),
            report.get("psram", {}).get("tick_count") == exact.get("psram_tick_count"),
            performance.get("instrumented") is False,
            performance.get("trace_enabled") is False,
            performance.get("warmup_excluded") is True,
            len(baseline_samples) == len(candidate_samples) == screening.get("paired_runs") == 3,
            statistics.median(baseline_samples) == screening.get("baseline_median_wall_seconds"),
            statistics.median(candidate_samples) == screening.get("candidate_median_wall_seconds"),
            math.isclose(
                median_regression,
                screening.get("candidate_median_regression_percent"),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            screening.get("formal_ten_run_measurement_performed") is False,
            performance.get("formal_ten_run_measurement_performed") is False,
            performance.get("determinism", {}).get("all_runs_passed") is True,
            decision.get("accepted") is False,
            decision.get("active_target_changed") is False,
            decision.get("validation_attestation_added") is False,
            decision.get("hardware_correlation_required") is False,
            all(
                artifacts.get(key + "_sha256") == digest
                and sha256(record_root / artifacts[key]) == digest
                for key, digest in expected_artifact_hashes.items()
            ),
            (record_root / artifacts.get("notes", "")).is_file(),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=baseline.get("target"),
            candidate_commit=candidate.get("backend_commit"),
            result=record.get("result"),
            paired_runs=screening.get("paired_runs"),
            median_regression_percent=screening.get("candidate_median_regression_percent"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt2d_lever_comparison(checks: List[Check], root: Path) -> None:
    """Verify OPT2-D lever-ranking comparison and overlap/decode summary."""
    name = "opt2-d:lever-comparison"
    expected_backend = "e482172565fc3073ba0960eb5e2642968a65ae52"
    expected_artifact_hashes = {
        "comparison": "60ff25f44e855da4dbd171d0906e52a70a254570e8e0c11de088ddbec4014b13",
        "running_event_horizon_profile": (
            "436ae7288a6f01aca8aa0e5232452eb5456a19e86e91570bd2c02601d5723a0a"
        ),
        "run_report": "73b9aeedbc02baa712d91317b50783442bbc1a217518ee2a36d7f977332b4d0c",
        "behavior_trace": "97c3a7faeecd5b75012d068d5a6f86af4deaa4eab001abe45000797b32b2e264",
    }
    expected_decode = {
        "core0_cacheable_hits": 172_417_748,
        "core0_cacheable_misses": 297_282,
        "core0_noncacheable_fetches": 0,
        "core0_cache_hit_percent": 99.82787716853593,
        "core0_avg_sequential_hit_run_instructions": 4.562897526997386,
        "core0_hit_run_ge_4_mass": 86_811_548,
    }
    try:
        record_root = root / "firmware-validation/records/opt2-d-lever-comparison-20260809-01"
        record = load_json(record_root / "record.json")
        run_report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        comparison = load_json(record_root / "comparison.json")
        record_comparison = record["comparison"]
        profile = load_json(record_root / "running-event-horizon-profile.json")
        artifacts = record["artifacts"]
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )
        exact = record["exactness"]
        profiler = record["profiler"]
        decision = record["decision"]
        ranking = comparison["decision"]
        compare_peripheral = comparison["peripheral_horizon"]
        profile_decision_cpu = comparison["cpu_decode"]["core0"]
        running_profile_trace = behavior["behavior_projection"]["event_trace"]
        running_profile_domains = {item.get("name") for item in running_profile_trace["domains"]}
        expected_domains = {
            "clock", "irq_exception", "pio_gpio", "psram", "lcd",
            "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
        }

        decode_core0 = profile["decode_opportunity_by_core"][0]
        decode_core1 = profile["decode_opportunity_by_core"][1]
        signatures = profile["one_cycle_fallback_signatures"]
        signature_mass = signatures["cycle_mass"]
        signature_steps = signatures["steps"]

        union_signature_cycles = sum(signature_mass)
        profile_decode_hit_mass = decode_core0["sequential_cache_hit_runs"]["cycle_mass_ge"][0]
        record_decode_hit_percent = (
            decode_core0["cacheable_hits"]
            / (decode_core0["cacheable_hits"] + decode_core0["cacheable_misses"])
            * 100.0
        )

        aligned = all((
            record.get("record_id") == "opt2-d-lever-comparison-20260809-01",
            record.get("result") == "measurement_complete",
            record.get("opt2_overall_status") == "incomplete",
            record.get("target", {}).get("id") == target.get("id") == "picotetris-opt1b",
            record.get("target", {}).get("revision") == target.get("revision") == 5,
            record.get("target", {}).get("firmware_sha256")
            == target.get("artifacts", {}).get("bin_sha256"),
            record.get("target", {}).get("scenario_sha256")
            == target.get("scenario", {}).get("sha256"),
            record["target"].get("firmware_sha256") == run_report.get("firmware", {}).get("sha256"),
            profiler.get("backend_commit") == expected_backend,
            profiler.get("schema_version") == 2,
            profiler.get("feature") == "event-horizon-profiler",
            profiler.get("instrumented") is True,
            profiler.get("valid_for_wall_time") is False,
            profiler.get("fallback_occupancy_is_safe_window") is False,
            profiler.get("decode_hit_runs_are_speedup_prediction") is False,
            profiler.get("backend_dirty") is False,
            record.get("profiler", {}).get("fallback_occupancy_is_safe_window") is False,
            run_report.get("backend_build", {}).get("commit") == profiler.get("backend_commit"),
            run_report.get("backend_build", {}).get("dirty") is False,
            run_report.get("schema_version") == 8,
            run_report.get("verdict", {}).get("status") == exact.get("verdict"),
            run_report.get("stop_reason") == exact.get("stop_reason") == "scenario_done",
            run_report.get("cycles") == exact.get("cycles") == 927_528_660,
            run_report.get("elapsed_us") == exact.get("elapsed_us") == 3_715_000,
            run_report.get("scenario", {}).get("status") == "pass",
            len(run_report.get("scenario", {}).get("steps", [])) == exact.get("scenario_steps_passed") == 85,
            exact.get("scenario_steps_total") == 85,
            exact.get("all_nine_event_domains_match_opt1b") is True,
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("backend_build", {}).get("commit") == profiler.get("backend_commit"),
            behavior.get("behavior_sha256") == exact.get("behavior_sha256"),
            behavior.get("behavior_projection", {}).get("event_trace", {}).get("schema_version") == 2,
            running_profile_trace.get("sha256") == exact.get("event_stream_sha256"),
            running_profile_trace.get("total_events") == exact.get("event_stream_total_events"),
            set(running_profile_domains) == expected_domains,
            exact.get("uart_sha256") == run_report.get("uart", {}).get("sha256"),
            exact.get("framebuffer_rgb565_sha256")
            == run_report.get("framebuffer", {}).get("rgb565_sha256"),
            run_report.get("psram", {}).get("tick_count") == 305_747_113,
            profile.get("schema_version") == 2,
            profile.get("kind") == "rp2040_serial_running_event_horizon_profile",
            profile.get("execution_model") == "Serial",
            profile.get("instrumented") is True,
            profile.get("valid_for_wall_time") is False,
            profile.get("observed_gaps_are_safe_windows") is False,
            profile.get("fallback_occupancy_is_safe_window") is False,
            profile.get("decode_hit_runs_are_speedup_prediction") is False,
            profile.get("conservative_horizon_complete_for_current_model") is True,
            profile.get("run_cycles") == exact.get("cycles"),
            profile.get("firmware", {}).get("sha256")
            == record.get("target", {}).get("firmware_sha256"),
            profile.get("step_quantum") == 1,
            profile.get("backend_build", {}).get("dirty") is False,
            record.get("comparison", {}).get("peripheral_fallback_union_cycles") == union_signature_cycles,
            record_comparison.get("peripheral_fallback_union_cycles") == union_signature_cycles,
            record_comparison.get("peripheral_fallback_union_cycles") == 257_246_995,
            compare_peripheral.get("one_cycle_fallback_union_cycles") == 257_246_995,
            math.isclose(
                record_comparison.get("peripheral_fallback_percent_of_running"),
                83.26955948894727,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            record_comparison.get("pio_only_cycles") == 217_025_266,
            math.isclose(
                record_comparison.get("pio_only_percent_of_running"),
                70.24998794559914,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            math.isclose(
                record_comparison.get("decode_cache_hit_percent"),
                expected_decode["core0_cache_hit_percent"],
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            ranking.get("selected_next_prototype") == "PIO exact event horizon and bulk advance",
            comparison.get("input_profile_schema_version") == 2,
            comparison.get("semantics", {}).get("fallback_occupancy_is_safe_window") is False,
            comparison.get("semantics", {}).get("decode_hit_runs_are_speedup_prediction") is False,
            comparison.get("semantics", {}).get("cycle_masses_from_different_levers_are_not_additive") is True,
            decision.get("selected_next_prototype") == "PIO exact event horizon and bulk advance",
            decision.get("production_optimization_added") is False,
            decision.get("active_target_changed") is False,
            decision.get("cpu_decode_work_deferred_to") == "OPT3",
            decision.get("validation_attestation_added") is False,
            record.get("ci", {}).get("repository") == "FuyukiYoneyama/picoem-picocalc",
            record.get("ci", {}).get("run_id") == 31_280_667_153,
            record.get("ci", {}).get("head_sha") == expected_backend,
            record.get("ci", {}).get("conclusion") == "success",
            signatures.get("bit_order") == ["pio", "uart", "dma", "any_other"],
            signature_steps[1] == 121_389_006,
            signature_mass[1] == 217_025_266,
            signature_steps[2] == 17_462_905,
            signature_mass[2] == 34_901_586,
            signature_steps[4] == 12_098,
            signature_mass[4] == 22_000,
            signature_mass[5] == 2_128,
            signature_mass[6] == 5_296_015,
            decode_core0.get("cacheable_hits") == expected_decode["core0_cacheable_hits"],
            decode_core0.get("cacheable_misses") == expected_decode["core0_cacheable_misses"],
            decode_core0.get("noncacheable_fetches") == expected_decode["core0_noncacheable_fetches"],
            decode_core1.get("cacheable_hits") == 0,
            decode_core1.get("cacheable_misses") == 0,
            decode_core1.get("noncacheable_fetches") == 0,
            math.isclose(
                record_decode_hit_percent,
                expected_decode["core0_cache_hit_percent"],
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            decode_core0["sequential_cache_hit_runs"].get("episodes_ge")[4] == 1_029_459,
            decode_core0["sequential_cache_hit_runs"]["cycle_mass_ge"][4] == 23_317_771,
            profile_decision_cpu.get("cacheable_hits") == expected_decode["core0_cacheable_hits"],
            profile_decision_cpu.get("cacheable_misses") == expected_decode["core0_cacheable_misses"],
            profile_decision_cpu.get("noncacheable_fetches")
            == expected_decode["core0_noncacheable_fetches"],
            math.isclose(
                profile_decision_cpu.get("cache_hit_percent"),
                expected_decode["core0_cache_hit_percent"],
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            math.isclose(
                profile_decision_cpu.get("average_sequential_hit_run_instructions"),
                expected_decode["core0_avg_sequential_hit_run_instructions"],
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            math.isclose(
                profile_decision_cpu.get("hit_instruction_percent_ge_4"),
                (expected_decode["core0_hit_run_ge_4_mass"] / profile_decode_hit_mass) * 100.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            profile_decision_cpu.get("hit_instruction_mass_ge_4") == expected_decode["core0_hit_run_ge_4_mass"],
            compare_peripheral["exclusive_and_overlap_cycle_mass"].get("pio_only")
            == 217_025_266,
            compare_peripheral["exclusive_and_overlap_cycle_mass"].get("uart_only")
            == 34_901_586,
            compare_peripheral["exclusive_and_overlap_cycle_mass"].get("dma_only") == 22_000,
            compare_peripheral["exclusive_and_overlap_cycle_mass"].get("pio_dma") == 2_128,
            compare_peripheral["exclusive_and_overlap_cycle_mass"].get("uart_dma") == 5_296_015,
            all(
                artifacts.get(key + "_sha256") == digest
                and artifacts.get(key) is not None
                and (record_root / artifacts.get(key)).is_file()
                and sha256(record_root / artifacts.get(key)) == digest
                for key, digest in expected_artifact_hashes.items()
            ),
            all((record_root / value).is_file() for key, value in artifacts.items() if not key.endswith("_sha256")),
            record_comparison.get("pio_only_cycles")
            == compare_peripheral["exclusive_and_overlap_cycle_mass"]["pio_only"],
            profile_decode_hit_mass == decode_core0["cacheable_hits"],
            profile.get("counters", {}).get("candidate_cycles") > 0,
            profile.get("counters", {}).get("candidate_dispatches") > 0,
        ))
        add_check(
            checks,
            name,
            aligned,
            target=target.get("id"),
            backend_commit=profiler.get("backend_commit"),
            running_steps=profile.get("counters", {}).get("running_steps"),
            running_cycles=profile.get("counters", {}).get("total_running_cycles"),
            fallback_union_cycles=record_comparison.get("peripheral_fallback_union_cycles"),
            cache_hit_percent=expected_decode["core0_cache_hit_percent"],
            decision_selected_next_prototype=decision.get("selected_next_prototype"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt2e_pio_pull_stall(checks: List[Check], root: Path) -> None:
    """Verify the exact PIO pull-stall bulk-advance prototype metrics and decision."""
    name = "opt2-e:pio-pull-stall"
    expected_artifact_hashes = {
        "run_report": "20b0c5fec74e12d02bbe904d87b868a515392d10307dfa1c9fc9cfcaa05375b2",
        "behavior_trace": (
            "569c25aa3176c07287319e7adcec55bcf71ff40538c814ec7e1f911499773df3"
        ),
        "performance": (
            "7e2e17d6897768d524a4e9542e3299b1735ac2a714049d3dd0ef205f85ff6c73"
        ),
    }
    expected_domains = {
        "clock", "irq_exception", "pio_gpio", "psram", "lcd",
        "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
    }
    try:
        record_root = root / "firmware-validation/records/opt2-e-pio-pull-stall-20260809-01"
        record = load_json(record_root / "record.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "performance-screening.json")
        opt1b_behavior = load_json(
            root / "firmware-validation/records/opt1-b-20260808-01/behavior-trace.json"
        )
        artifacts = record["artifacts"]
        performance_record = record["performance_screening"]
        exact = record["exactness"]
        candidate = record["candidate"]
        decision = record["decision"]
        target_record = record["target"]
        target = next(
            item
            for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )
        profile_trace = behavior["behavior_projection"]["event_trace"]
        profile_domains = {item.get("name") for item in profile_trace["domains"]}
        baseline_samples = performance["baseline"]["wall_seconds"]
        candidate_samples = performance["candidate"]["wall_seconds"]
        baseline_median = statistics.median(baseline_samples)
        candidate_median = statistics.median(candidate_samples)
        improvement_percent = (baseline_median - candidate_median) / baseline_median * 100

        aligned = all((
            record.get("record_id") == "opt2-e-pio-pull-stall-20260809-01",
            record.get("result") == "rejected",
            record.get("optimization_status") == "reverted",
            record.get("opt2_overall_status") == "incomplete",
            record.get("roadmap_package") == "OPT2-E",
            target_record.get("id") == target.get("id") == "picotetris-opt1b",
            target_record.get("revision") == target.get("revision") == 5,
            target_record.get("firmware_sha256")
            == target.get("artifacts", {}).get("bin_sha256"),
            target_record.get("scenario_sha256") == target.get("scenario", {}).get("sha256"),
            report.get("firmware", {}).get("sha256") == target_record.get("firmware_sha256"),
            report.get("backend_build", {}).get("commit") == candidate.get("backend_commit"),
            report.get("backend_build", {}).get("dirty") is False,
            report.get("schema_version") == 8,
            report.get("verdict", {}).get("status") == "pass",
            report.get("stop_reason") == exact.get("stop_reason") == "scenario_done",
            report.get("cycles") == exact.get("cycles") == 927_528_660,
            report.get("elapsed_us") == exact.get("elapsed_us") == 3_715_000,
            report.get("scenario", {}).get("status") == "pass",
            len(report.get("scenario", {}).get("steps", [])) == 85,
            exact.get("scenario_steps_passed") == exact.get("scenario_steps_total") == 85,
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("backend_build", {}).get("commit") == candidate.get("backend_commit"),
            behavior.get("backend_build", {}).get("dirty") is False,
            behavior.get("mode") == "correctness_trace_on",
            behavior.get("valid_for_wall_time") is False,
            behavior.get("behavior_sha256") == exact.get("behavior_sha256"),
            behavior.get("behavior_projection") == opt1b_behavior.get("behavior_projection"),
            profile_trace.get("schema_version") == 2,
            profile_trace.get("sha256") == exact.get("event_stream_sha256"),
            profile_trace.get("total_events") == exact.get("event_stream_total_events"),
            set(profile_domains) == expected_domains,
            exact.get("all_nine_event_domains_match_opt1b") is True,
            exact.get("uart_sha256") == report.get("uart", {}).get("sha256"),
            exact.get("framebuffer_rgb565_sha256")
            == report.get("framebuffer", {}).get("rgb565_sha256"),
            exact.get("psram_tick_count") == report.get("psram", {}).get("tick_count"),
            performance.get("schema_version") == 1,
            performance.get("result") == "rejected_below_threshold",
            performance.get("valid_for_wall_time") is True,
            performance.get("measurement") == "OPT2-E PIO pull-stall bulk prototype screening",
            math.isclose(
                performance.get("median_improvement_percent"),
                improvement_percent,
                rel_tol=0.0,
                abs_tol=1e-9,
            ),
            performance.get("promotion_threshold_percent") == 5.0,
            performance.get("paired_improvement_percent") == [0.730769231, 0.661478599, 0.116867939],
            math.isclose(
                performance_record.get("candidate_median_improvement_percent"),
                improvement_percent,
                rel_tol=0.0,
                abs_tol=1e-9,
            ),
            performance_record.get("promotion_improvement_threshold_percent") == 5.0,
            performance_record.get("formal_ten_run_measurement_performed") is False,
            performance_record.get("all_six_measured_runs_exact") is True,
            performance_record.get("baseline_median_wall_seconds") == baseline_median == 25.70,
            performance_record.get("candidate_median_wall_seconds") == candidate_median == 25.64,
            len(baseline_samples)
            == len(candidate_samples)
            == performance_record.get("paired_runs") == 3,
            performance.get("baseline", {}).get("median_wall_seconds") == baseline_median,
            performance.get("candidate", {}).get("median_wall_seconds") == candidate_median,
            candidate.get("backend_commit") == "a7ac9020b9861c1c4803187b7092512b65f60835",
            candidate.get("revert_commit") == "a7939e550aee3f604e0e052159243bf0872fc285",
            candidate.get("feature") == "pio-exact-bulk-prototype",
            candidate.get("hardware_quantum") == 1,
            candidate.get("accepted_state") == "all enabled PIO state machines stalled on PULL with empty TX FIFO",
            candidate.get("fallback_state")
            == "active, mixed-stall, WAIT, RX-full or refilled-TX state machines",
            candidate.get("all_accepted_calls_single_cycle") is True,
            candidate.get("accepted_calls") == candidate.get("accepted_system_cycles"),
            candidate.get("accepted_system_cycles") == 371_982_564,
            candidate.get("accepted_pio_ticks") == 185_895_678,
            decision.get("accepted") is False,
            decision.get("active_target_changed") is False,
            decision.get("validation_attestation_added") is False,
            decision.get("hardware_correlation_required") is False,
            decision.get("next_investigation")
            == "design an exact stationary pin-device bulk observation contract before coalescing the outer PIO and update_gpio loop",
            record.get("ci", {}).get("repository") == "FuyukiYoneyama/picoem-picocalc",
            record.get("ci", {}).get("run_id") == 31_282_717_963,
            record.get("ci", {}).get("head_sha") == candidate.get("revert_commit"),
            record.get("ci", {}).get("conclusion") == "success",
            all(
                artifacts.get(key + "_sha256") == digest
                and artifacts.get(key) is not None
                and (record_root / artifacts.get(key)).is_file()
                and sha256(record_root / artifacts.get(key)) == digest
                for key, digest in expected_artifact_hashes.items()
            ),
            (record_root / artifacts.get("notes", "")).is_file(),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=record.get("target", {}).get("id"),
            backend_commit=candidate.get("backend_commit"),
            candidate_median_improvement_percent=performance.get("median_improvement_percent"),
            candidate_calls_single_cycle=candidate.get("all_accepted_calls_single_cycle"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt2f_stationary_pin_bulk(checks: List[Check], root: Path) -> None:
    """Verify the exact stationary pin-device bulk observation candidate and decision."""
    name = "opt2-f:stationary-pin-bulk"
    expected_artifact_hashes = {
        "performance": "90ae0f5f87ed71ed7ea59db65ed0933856af42862a2048f4f8b357bf0889c08e",
        "run_report": "02f20a7f15ec28535813fd832503a07907b68eee1ce13668d754f66423743d9c",
        "behavior_trace": "5175fc0c58951f798bfe34345ad033a8b4647a88f55eeb9edc256d826295dfae",
    }
    expected_domains = {
        "clock", "irq_exception", "pio_gpio", "psram", "lcd",
        "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
    }
    try:
        record_root = root / "firmware-validation/records/opt2-f-stationary-pin-bulk-20260809-01"
        record = load_json(record_root / "record.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "performance-screening.json")
        opt1b_behavior = load_json(
            root / "firmware-validation/records/opt1-b-20260808-01/behavior-trace.json"
        )
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )
        artifacts = record["artifacts"]
        exact = record["exactness"]
        candidate = record["candidate"]
        decision = record["decision"]
        screening = record["performance_screening"]
        target_record = record["target"]
        baseline_median = performance.get("baseline", {}).get("median_wall_seconds")
        candidate_median = performance.get("candidate", {}).get("median_wall_seconds")
        improvement_percent = (
            (baseline_median - candidate_median) / baseline_median * 100
            if isinstance(baseline_median, (int, float))
            and isinstance(candidate_median, (int, float))
            else None
        )
        profile = behavior["behavior_projection"]["event_trace"]
        profile_domains = {item.get("name") for item in profile.get("domains", [])}

        aligned = all((
            record.get("record_id") == "opt2-f-stationary-pin-bulk-20260809-01",
            record.get("result") == "rejected",
            record.get("optimization_status") == "reverted",
            record.get("opt2_overall_status") == "incomplete",
            record.get("roadmap_package") == "OPT2-F",
            target_record.get("id") == target.get("id") == "picotetris-opt1b",
            target_record.get("revision") == target.get("revision") == 5,
            target_record.get("firmware_sha256")
            == target.get("artifacts", {}).get("bin_sha256"),
            target_record.get("scenario_sha256") == target.get("scenario", {}).get("sha256"),
            candidate.get("backend_commit")
            == report.get("backend_build", {}).get("commit"),
            report.get("firmware", {}).get("sha256") == target_record.get("firmware_sha256"),
            candidate.get("backend_dirty") is False,
            candidate.get("feature") == "stationary-pin-bulk-prototype",
            candidate.get("prerequisite_commit") == "eea6eaaa188aed68fa6f86b5d6a629177348c528",
            candidate.get("candidate_revert_commit") == "cdb758408914883b0ac4a2ca7c8338cebd8b2da7",
            report.get("schema_version") == 8,
            report.get("backend_build", {}).get("dirty") is False,
            report.get("verdict", {}).get("status") == "pass",
            report.get("stop_reason") == exact.get("stop_reason") == "scenario_done",
            report.get("cycles") == exact.get("cycles") == 927_528_660,
            report.get("elapsed_us") == exact.get("elapsed_us") == 3_715_000,
            report.get("scenario", {}).get("status") == "pass",
            len(report.get("scenario", {}).get("steps", [])) == exact.get("scenario_steps_passed") == 85,
            exact.get("scenario_steps_total") == 85,
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("backend_build", {}).get("commit") == candidate.get("backend_commit"),
            behavior.get("backend_build", {}).get("dirty") is False,
            behavior.get("mode") == "correctness_trace_on",
            behavior.get("valid_for_wall_time") is False,
            behavior.get("behavior_sha256") == exact.get("behavior_sha256"),
            behavior.get("behavior_projection") == opt1b_behavior.get("behavior_projection"),
            profile.get("schema_version") == 2,
            profile.get("sha256") == exact.get("event_stream_sha256"),
            profile.get("total_events") == exact.get("event_stream_total_events"),
            set(profile_domains) == expected_domains,
            exact.get("all_nine_event_domains_match_opt1b") is True,
            exact.get("uart_sha256") == report.get("uart", {}).get("sha256"),
            exact.get("framebuffer_rgb565_sha256")
            == report.get("framebuffer", {}).get("rgb565_sha256"),
            exact.get("psram_tick_count") == report.get("psram", {}).get("tick_count"),
            performance.get("schema_version") == 1,
            performance.get("measurement") == "OPT2-F stationary pin-device bulk observation screening",
            performance.get("valid_for_wall_time") is True,
            performance.get("result") == "rejected_below_threshold",
            performance.get("host", {}).get("cpu_affinity") == 0,
            performance.get("host", {}).get("execution_order")
            == "alternating clean baseline/candidate pairs",
            performance.get("baseline", {}).get("backend_commit")
            == "a7939e550aee3f604e0e052159243bf0872fc285",
            performance.get("baseline", {}).get("backend_dirty") is False,
            performance.get("candidate", {}).get("backend_commit")
            == candidate.get("backend_commit"),
            performance.get("candidate", {}).get("backend_dirty") is False,
            performance.get("promotion_threshold_percent") == 5.0,
            performance.get("formal_ten_run_measurement_performed") is False,
            performance.get("exact_outputs_identical_across_all_six_measured_runs") is True,
            screening.get("paired_runs") == 3,
            len(performance.get("baseline", {}).get("wall_seconds", [])) == 3,
            len(performance.get("candidate", {}).get("wall_seconds", [])) == 3,
            baseline_median == statistics.median(
                performance.get("baseline", {}).get("wall_seconds", [])
            ) == screening.get("baseline_median_wall_seconds") == 26.18,
            candidate_median == statistics.median(
                performance.get("candidate", {}).get("wall_seconds", [])
            ) == screening.get("candidate_median_wall_seconds") == 26.00,
            math.isclose(
                screening.get("candidate_median_improvement_percent"),
                0.6875477463712747,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            math.isclose(
                performance.get("median_improvement_percent"),
                improvement_percent,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            screening.get("promotion_improvement_threshold_percent") == 5.0,
            screening.get("formal_ten_run_measurement_performed") is False,
            screening.get("all_six_measured_runs_exact") is True,
            candidate.get("final_revert_commit")
            == "2671d0476c1a4286de7e3666bf91e20e27613854",
            candidate.get("final_content_matches_commit")
            == "a7939e550aee3f604e0e052159243bf0872fc285",
            candidate.get("outer_calls") == 23_199_887,
            candidate.get("pio_system_cycles") == 371_982_564,
            candidate.get("update_gpio_calls_elided") == 37_012_745,
            candidate.get("pio_block_calls") == 302_454_671,
            candidate.get("pio_ticks") == 185_895_678,
            decision.get("accepted") is False,
            decision.get("active_target_changed") is False,
            decision.get("validation_attestation_added") is False,
            decision.get("hardware_correlation_required") is False,
            decision.get("next_investigation") == "UART deadline promotion",
            decision.get("cpu_block_work_deferred_to") == "OPT3",
            record.get("ci", {}).get("repository") == "FuyukiYoneyama/picoem-picocalc",
            record.get("ci", {}).get("run_id") == 31_285_484_757,
            record.get("ci", {}).get("head_sha")
            == candidate.get("final_revert_commit", candidate.get("revert_commit")),
            record.get("ci", {}).get("conclusion") == "success",
            all(
                artifacts.get(key + "_sha256") == digest
                and artifacts.get(key) is not None
                and (record_root / artifacts.get(key)).is_file()
                and sha256(record_root / artifacts.get(key)) == digest
                for key, digest in expected_artifact_hashes.items()
            ),
            (record_root / artifacts.get("notes", "")).is_file(),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=target_record.get("id"),
            backend_commit=candidate.get("backend_commit"),
            paired_runs=screening.get("paired_runs"),
            candidate_median_improvement_percent=screening.get("candidate_median_improvement_percent"),
            candidate_pio_system_cycles=candidate.get("pio_system_cycles"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt2g_uart_deadline(checks: List[Check], root: Path) -> None:
    """Verify the exact UART scheduler lane record and rejected decision."""
    name = "opt2-g:uart-deadline"
    expected_artifact_hashes = {
        "notes": "b9fa0c188096d661a29ac498ee5e522bd6a7f7295eabea2d8cc4b371096683b0",
        "performance": "11f5d0b571d919b464f58dca8173b238f68063eb84fe734f989c26ce794d84f7",
        "run_report": "aaaba8340342f24115faa860034397160c24eb9d181d5f5eb7dba9adde942388",
        "behavior_trace": "75a7c9c4ae07e23da7cc5554d4d8654a6bf8d74a331fa0ca305595620a77f8b1",
    }
    expected_domains = {
        "clock", "irq_exception", "pio_gpio", "psram", "lcd",
        "dma_dreq", "timer_pwm", "serial_bus", "scenario_input",
    }
    try:
        record_root = root / "firmware-validation/records/opt2-g-uart-deadline-20260809-01"
        record = load_json(record_root / "record.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "performance-screening.json")
        opt1b_behavior = load_json(
            root / "firmware-validation/records/opt1-b-20260808-01/behavior-trace.json"
        )
        target = next(
            item for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == "picotetris-opt1b"
        )
        candidate = record["candidate"]
        exact = record["exactness"]
        screening = record["performance_screening"]
        decision = record["decision"]
        target_record = record["target"]
        artifacts = record["artifacts"]
        profile = behavior["behavior_projection"]["event_trace"]
        profile_domains = {item.get("name") for item in profile.get("domains", [])}
        baseline_median = performance["baseline"]["median_wall_seconds"]
        candidate_median = performance["candidate"]["median_wall_seconds"]
        improvement = (baseline_median - candidate_median) / baseline_median * 100
        run_ids = [item.get("id") for item in performance.get("runs", [])]
        aligned = all((
            record.get("record_id") == "opt2-g-uart-deadline-20260809-01",
            record.get("result") == "rejected",
            record.get("optimization_status") == "reverted",
            record.get("opt2_overall_status") == "closed_without_additional_promotion",
            record.get("roadmap_package") == "OPT2-G",
            target_record.get("id") == target.get("id") == "picotetris-opt1b",
            target_record.get("revision") == target.get("revision") == 5,
            target_record.get("firmware_sha256") == target.get("artifacts", {}).get("bin_sha256"),
            target_record.get("scenario_sha256") == target.get("scenario", {}).get("sha256"),
            candidate.get("backend_commit") == "593e6d78541722920e1fa903e682d49912eae825",
            candidate.get("baseline_commit") == "2671d0476c1a4286de7e3666bf91e20e27613854",
            candidate.get("backend_dirty") is False,
            candidate.get("feature") == "uart-deadline-prototype",
            candidate.get("candidate_revert_commit") == "335ecdd7f01cbc5d4f63e18403033bd629efbe77",
            candidate.get("final_content_matches_commit") == "2671d0476c1a4286de7e3666bf91e20e27613854",
            candidate.get("actual_running_fast_forward") is False,
            candidate.get("fail_closed_lane") is True,
            candidate.get("lane_calls") == 3_137_790,
            candidate.get("lane_cycles") == 6_268_797,
            candidate.get("temporal_tx_calls") == 3_127_577,
            candidate.get("first_tx_deadline_cycles") == 1,
            candidate.get("static_calls") == 10_213,
            report.get("schema_version") == 8,
            report.get("backend_build", {}).get("commit") == candidate.get("backend_commit"),
            report.get("backend_build", {}).get("dirty") is False,
            report.get("verdict", {}).get("status") == "pass",
            report.get("stop_reason") == exact.get("stop_reason") == "scenario_done",
            report.get("cycles") == exact.get("cycles") == 927_528_660,
            report.get("elapsed_us") == exact.get("elapsed_us") == 3_715_000,
            report.get("scenario", {}).get("status") == "pass",
            len(report.get("scenario", {}).get("steps", [])) == exact.get("scenario_steps_passed") == 85,
            exact.get("scenario_steps_total") == 85,
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("backend_build", {}).get("commit") == candidate.get("backend_commit"),
            behavior.get("backend_build", {}).get("dirty") is False,
            behavior.get("mode") == "correctness_trace_on",
            behavior.get("valid_for_wall_time") is False,
            behavior.get("behavior_sha256") == exact.get("behavior_sha256"),
            behavior.get("behavior_projection") == opt1b_behavior.get("behavior_projection"),
            profile.get("schema_version") == 2,
            profile.get("sha256") == exact.get("event_stream_sha256"),
            profile.get("total_events") == exact.get("event_stream_total_events"),
            set(profile_domains) == expected_domains,
            exact.get("all_nine_event_domains_match_opt1b") is True,
            exact.get("uart_sha256") == report.get("uart", {}).get("sha256"),
            exact.get("framebuffer_rgb565_sha256") == report.get("framebuffer", {}).get("rgb565_sha256"),
            exact.get("psram_tick_count") == report.get("psram", {}).get("tick_count"),
            performance.get("schema_version") == 1,
            performance.get("measurement") == "OPT2-G UART exact scheduler lane screening",
            performance.get("valid_for_wall_time") is True,
            performance.get("result") == "rejected_below_threshold",
            performance.get("host", {}).get("cpu_affinity") == 0,
            performance.get("host", {}).get("affinity_command") == "taskset -c 0",
            performance.get("host", {}).get("execution_order")
            == "A/B/A/B/A/B alternating clean detached worktrees",
            performance.get("canonical", {}).get("cycles_limit") == 8_000_000_000,
            performance.get("canonical", {}).get("quantum") == 1,
            performance.get("canonical", {}).get("firmware_sha256") == target_record.get("firmware_sha256"),
            performance.get("baseline", {}).get("backend_commit") == candidate.get("baseline_commit"),
            performance.get("baseline", {}).get("backend_dirty") is False,
            performance.get("candidate", {}).get("backend_commit") == candidate.get("backend_commit"),
            performance.get("candidate", {}).get("backend_dirty") is False,
            performance.get("candidate", {}).get("feature") == candidate.get("feature"),
            performance.get("promotion_threshold_percent") == 5.0,
            performance.get("formal_ten_run_measurement_performed") is False,
            performance.get("exact_outputs_identical_across_all_six_measured_runs") is True,
            run_ids == ["a1", "b1", "a2", "b2", "a3", "b3"],
            all(item.get("cpu_affinity") == 0 and item.get("exit_code") == 0 for item in performance["runs"]),
            baseline_median == statistics.median(performance["baseline"]["wall_seconds"]) == screening["baseline_median_wall_seconds"] == 25.92,
            candidate_median == statistics.median(performance["candidate"]["wall_seconds"]) == screening["candidate_median_wall_seconds"] == 28.17,
            math.isclose(screening["candidate_median_improvement_percent"], -8.680555555555555, rel_tol=0.0, abs_tol=1e-12),
            math.isclose(performance["median_improvement_percent"], improvement, rel_tol=0.0, abs_tol=1e-12),
            screening.get("cpu_affinity") == 0,
            screening.get("all_six_measured_runs_exact") is True,
            decision.get("accepted") is False,
            decision.get("active_target_changed") is False,
            decision.get("validation_attestation_added") is False,
            decision.get("next_investigation") == "OPT3 CPU/decode/execute block cache",
            record.get("ci", {}).get("run_id") == 31_287_315_634,
            record.get("ci", {}).get("head_sha") == "335ecdd7f01cbc5d4f63e18403033bd629efbe77",
            record.get("ci", {}).get("conclusion") == "success",
            all(
                artifacts.get(key + "_sha256") == digest
                and (record_root / artifacts.get(key, "")).is_file()
                and sha256(record_root / artifacts.get(key)) == digest
                for key, digest in expected_artifact_hashes.items()
            ),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=target_record.get("id"),
            backend_commit=candidate.get("backend_commit"),
            paired_runs=screening.get("paired_runs"),
            candidate_median_improvement_percent=screening.get("candidate_median_improvement_percent"),
            lane_calls=candidate.get("lane_calls"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt3a_xip_cursor_profile(checks: List[Check], root: Path) -> None:
    """Verify the OPT3-A immutable XIP cursor profile and evidence."""
    name = "opt3-a:xip-cursor-profile"
    record_id = "opt3-a-xip-cursor-profile-20260809-01"
    target_id = "picotetris-opt1b"
    target_revision = 5
    backend_commit = "0b99b2eabe23205b3c6ac194dcdf016a53de554d"
    expected_domains = {
        "clock",
        "irq_exception",
        "pio_gpio",
        "psram",
        "lcd",
        "dma_dreq",
        "timer_pwm",
        "serial_bus",
        "scenario_input",
    }
    try:
        record_root = root / "firmware-validation/records" / record_id
        record = load_json(record_root / "record.json")
        profile = load_json(record_root / "running-event-horizon-profile.json")
        report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        analysis = load_json(record_root / "analysis.json")
        artifacts = record["artifacts"]
        target = next(
            item
            for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == target_id
        )

        target_record = record["target"]
        exactness = record["exactness"]
        opportunity = record["opportunity"]
        decision = record["decision"]
        semantics = analysis.get("semantics", {})
        core0 = analysis.get("core0", {})
        core1 = analysis.get("core1", {})
        analysis_decision = analysis.get("decision", {})
        profile_core0 = profile["decode_opportunity_by_core"][0]
        profile_core1 = profile["decode_opportunity_by_core"][1]
        profile_xip_hits = profile_core0["lookup_hits_by_region"]["immutable_xip_flash_aliases"]
        profile_xip_misses = profile_core0["lookup_misses_by_region"]["immutable_xip_flash_aliases"]
        profile_runs = profile_core0["immutable_xip_hit_runs"]
        profile_termination = profile_core0["immutable_xip_hit_run_termination_counters"]
        profile_invalidations = profile_core0["decode_cache_invalidation_observations"]
        event_trace = behavior.get("behavior_projection", {}).get("event_trace", {})
        termination = core0.get("termination", {})
        event_domains = {item.get("name") for item in event_trace.get("domains", [])}
        termination_sum = (
            termination.get("post_execute_next_pc_redirect", 0)
            + termination.get("xip_miss", 0)
            + termination.get("region_exit", 0)
            + termination.get("prefetch_exception", 0)
            + termination.get("fault", 0)
            + termination.get("open_at_snapshot", 0)
        )
        artifact_checks = [
            (artifact_name, record_root / artifact_path)
            for artifact_name, artifact_path in (
                ("analysis", artifacts["analysis"]),
                ("running_event_horizon_profile", artifacts["running_event_horizon_profile"]),
                ("run_report", artifacts["run_report"]),
                ("behavior_trace", artifacts["behavior_trace"]),
                ("notes", artifacts["notes"]),
            )
        ]

        def sha_and_exists(name: str, path: Path) -> bool:
            artifact_digest = artifacts.get("{}_sha256".format(name), "")
            return (
                path.is_file()
                and artifact_digest == sha256(path)
            )

        aligned = all((
            record.get("schema_version") == 1,
            record.get("record_id") == record_id,
            record.get("result") == "measurement_complete",
            record.get("opt3_overall_status") == "incomplete",
            record.get("roadmap_package") == "OPT3-A",
            analysis.get("schema_version") == 1,
            analysis.get("record_id") == record_id,
            analysis.get("input_profile_schema_version") == 3,
            target_record.get("id") == target_id,
            target_record.get("revision") == target_revision,
            target_record.get("firmware_sha256") == target.get("artifacts", {}).get("bin_sha256"),
            target_record.get("firmware_uf2_sha256")
            == target.get("artifacts", {}).get("uf2_sha256"),
            target_record.get("scenario_sha256") == target.get("scenario", {}).get("sha256"),
            record.get("profiler", {}).get("backend_commit") == backend_commit,
            record.get("profiler", {}).get("backend_dirty") is False,
            record.get("profiler", {}).get("schema_version") == 3,
            record.get("profiler", {}).get("feature") == "event-horizon-profiler",
            profile.get("schema_version") == 3,
            profile.get("backend_build", {}).get("commit") == backend_commit,
            profile.get("backend_build", {}).get("dirty") is False,
            profile.get("execution_model") == "Serial",
            profile.get("instrumented") is True,
            profile.get("valid_for_wall_time") is False,
            profile.get("decode_hit_runs_are_speedup_prediction") is False,
            profile.get("immutable_xip_hit_runs_are_speedup_prediction") is False,
            semantics.get("instrumented") is True,
            semantics.get("valid_for_wall_time") is False,
            semantics.get("run_mass_is_an_opportunity_bound") is True,
            semantics.get("immutable_xip_hit_runs_are_speedup_prediction") is False,
            report.get("schema_version") == 8,
            report.get("backend_build", {}).get("commit") == backend_commit,
            report.get("backend_build", {}).get("dirty") is False,
            report.get("firmware", {}).get("sha256") == target_record.get("firmware_sha256"),
            report.get("step_quantum") == 1,
            report.get("stop_reason") == exactness.get("stop_reason") == "scenario_done",
            report.get("cycles") == exactness.get("cycles") == 927_528_660,
            report.get("elapsed_us") == exactness.get("elapsed_us") == 3_715_000,
            report.get("scenario", {}).get("status") == "pass",
            report.get("verdict", {}).get("status") == "pass",
            len(report.get("scenario", {}).get("steps", [])) == 85,
            exactness.get("scenario_steps_passed") == 85,
            exactness.get("scenario_steps_total") == 85,
            exactness.get("all_nine_event_domains_match_opt1b") is True,
            report.get("uart", {}).get("sha256") == exactness.get("uart_sha256"),
            report.get("framebuffer", {}).get("rgb565_sha256")
            == exactness.get("framebuffer_rgb565_sha256"),
            report.get("psram", {}).get("tick_count") == exactness.get("psram_tick_count"),
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("mode") == "correctness_trace_on",
            behavior.get("backend_build", {}).get("commit") == backend_commit,
            behavior.get("backend_build", {}).get("dirty") is False,
            behavior.get("valid_for_wall_time") is False,
            behavior.get("behavior_sha256") == exactness.get("behavior_sha256"),
            event_trace.get("total_events") == 173_498_680,
            event_trace.get("schema_version") == 2,
            event_trace.get("sha256") == exactness.get("event_stream_sha256"),
            event_trace.get("total_events") == exactness.get("event_stream_total_events"),
            set(event_domains) == expected_domains,
            len(event_domains) == 9,
            profile_core0.get("cacheable_hits") == 172_417_748,
            profile_core0.get("cacheable_misses") == 297_282,
            profile_core0.get("noncacheable_fetches") == 0,
            profile_core0.get("cacheable_hits_narrow")
            + profile_core0.get("cacheable_hits_wide")
            == profile_core0.get("cacheable_hits"),
            sum(profile_core0.get("lookup_hits_by_region", {}).values())
            == profile_core0.get("cacheable_hits"),
            sum(profile_core0.get("lookup_misses_by_region", {}).values())
            == profile_core0.get("cacheable_misses")
            + profile_core0.get("noncacheable_fetches"),
            profile_xip_hits == 172_373_954,
            profile_xip_misses == 295_794,
            profile_runs.get("episodes_ge", [])[0] == 37_776_563,
            profile_runs.get("cycle_mass_ge", [])[0] == profile_xip_hits,
            profile_runs.get("cycle_mass_ge", [])[2] == 86_778_680,
            profile_runs.get("cycle_mass_ge", [])[4] == 23_313_232,
            profile_runs.get("cycle_mass_ge", [])[5] == 942_483,
            sum(profile_termination.values()) + 1 == profile_runs.get("episodes_ge", [])[0],
            profile_termination.get("post_execute_next_pc_redirect") == 37_756_069,
            profile_termination.get("xip_miss") == 20_218,
            profile_termination.get("prefetch_exception") == 275,
            profile_termination.get("region_exit") == 0,
            profile_termination.get("fault") == 0,
            profile_invalidations.get("entry_address_count") == 9_243_286,
            profile_invalidations.get("rom") == 0,
            profile_invalidations.get("xip") == 0,
            profile_invalidations.get("sram") == 9_243_286,
            profile_invalidations.get("bulk") == 0,
            profile_invalidations.get("all") == 0,
            all(
                profile_core1.get(key) == 0
                for key in (
                    "cacheable_hits",
                    "cacheable_misses",
                    "noncacheable_fetches",
                    "cacheable_hits_narrow",
                    "cacheable_hits_wide",
                )
            ),
            core0.get("cacheable_hits") == 172_417_748,
            core0.get("cacheable_misses") == 297_282,
            core0.get("immutable_xip_hits") == 172_373_954,
            core0.get("immutable_xip_misses") == 295_794,
            core0.get("immutable_xip_hit_runs") == 37_776_563,
            core0.get("immutable_xip_hit_instruction_mass") == 172_373_954,
            core0.get("immutable_xip_hits") == profile_xip_hits,
            core0.get("immutable_xip_misses") == profile_xip_misses,
            core0.get("immutable_xip_hit_runs") == profile_runs.get("episodes_ge", [])[0],
            core0.get("average_immutable_xip_hit_run_instructions") == 4.562986685686572,
            termination_sum == core0.get("immutable_xip_hit_runs", 0),
            core0.get("run_mass", {}).get("ge_4") == 86_778_680,
            core0.get("run_mass", {}).get("ge_32") == 942_483,
            core1.get("executed_instructions") == 0,
            core0.get("invalidation_observations", {}).get("xip") == 0,
            core0.get("invalidation_observations", {}).get("rom") == 0,
            core0.get("invalidation_observations", {}).get("bulk") == 0,
            core0.get("invalidation_observations", {}).get("all") == 0,
            opportunity.get("post_execute_redirect_terminations") == 37_756_069,
            opportunity.get("run_mass_ge_4") == 86_778_680,
            opportunity.get("run_mass_ge_32") == 942_483,
            opportunity.get("xip_invalidation_observations") == 0,
            decision.get("prototype_package") == "OPT3-B",
            decision.get("selected_next_prototype") == "short immutable-XIP decode cursor",
            decision.get("long_basic_block_batching_selected") is False,
            decision.get("production_optimization_added") is False,
            decision.get("active_target_changed") is False,
            decision.get("validation_attestation_added") is False,
            analysis_decision.get("prototype_package") == decision.get("prototype_package"),
            analysis_decision.get("selected_next_prototype")
            == decision.get("selected_next_prototype"),
            analysis_decision.get("long_basic_block_batching_selected") is False,
            analysis_decision.get("production_optimization_added") is False,
            record.get("ci", {}).get("run_id") == 31_291_223_952,
            record.get("ci", {}).get("conclusion") == "success",
            all(sha_and_exists(name, path) for name, path in artifact_checks),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=target_record.get("id"),
            result=record.get("result"),
            next_prototype=decision.get("selected_next_prototype"),
            run_episodes=core0.get("immutable_xip_hit_runs"),
            immutable_xip_hits=core0.get("immutable_xip_hits"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        StopIteration,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt3b_xip_decode_cursor(checks: List[Check], root: Path) -> None:
    """Verify the OPT3-B short immutable XIP decode-cursor prototype and rejection decision."""
    name = "opt3-b:xip-decode-cursor"
    record_id = "opt3-b-xip-decode-cursor-20260809-01"
    target_id = "picotetris-opt1b"
    target_revision = 5
    expected_artifact_hashes = {
        "run_report": "5de324816ad04a6799ea592be6d2c447860b0b693762c5e51f812c0463e65802",
        "behavior_trace": "5fcfbc6d6ca02fc3793b6cf57e73b6431b992fe09ef9b7587415fe1712bbc0de",
        "performance_screening": "309b7aee57ef2bf44eac88e90af331b673a824b8b89e4df30875694c62c7d713",
        "notes": "45ddabdd15a9e17543f30751ad61f4ade84109f5373d98fc1cd44425433f96b0",
    }
    try:
        record_root = root / "firmware-validation/records" / record_id
        record = load_json(record_root / "record.json")
        run_report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "performance-screening.json")
        opt1b_behavior = load_json(
            root / "firmware-validation/records/opt1-b-20260808-01/behavior-trace.json"
        )
        target_record = record["target"]
        registry_target = next(
            item
            for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == target_id
        )
        artifacts = record["artifacts"]

        exactness = record["exactness"]
        proof = record["proof"]
        core0_proof = proof["core0"]
        performance_summary = record["performance"]
        prototype = record["prototype"]
        decision = record["decision"]
        ci = record["ci"]
        event_trace = behavior.get("behavior_projection", {}).get("event_trace", {})
        event_domains = {item.get("name") for item in event_trace.get("domains", [])}

        artifact_checks = [
            (artifact_name, record_root / artifact_path)
            for artifact_name, artifact_path in (
                ("run_report", artifacts["run_report"]),
                ("behavior_trace", artifacts["behavior_trace"]),
                ("performance_screening", artifacts["performance_screening"]),
                ("notes", artifacts["notes"]),
            )
        ]
        report_proof = run_report.get("xip_decode_cursor_proof", {})
        report_core0_proof = report_proof.get("core0", {})
        report_core1_proof = report_proof.get("core1", {})
        baseline_samples = performance.get("baseline", {}).get("wall_seconds", [])
        candidate_samples = performance.get("candidate", {}).get("wall_seconds", [])
        pair_improvements = performance.get("pair_improvement_percent", [])

        aligned = all((
            record.get("schema_version") == 1,
            record.get("record_id") == record_id,
            record.get("result") == "rejected_performance_reverted",
            record.get("roadmap_package") == "OPT3-B",
            record.get("opt3_overall_status") == "incomplete",
            target_record.get("id") == target_id,
            target_record.get("revision") == target_revision,
            target_record.get("firmware_source_commit")
            == registry_target.get("source", {}).get("commit"),
            target_record.get("firmware_sha256")
            == registry_target.get("artifacts", {}).get("bin_sha256"),
            target_record.get("firmware_uf2_sha256")
            == registry_target.get("artifacts", {}).get("uf2_sha256"),
            target_record.get("scenario_sha256")
            == registry_target.get("scenario", {}).get("sha256"),
            prototype.get("baseline_backend_commit")
            == "0b99b2eabe23205b3c6ac194dcdf016a53de554d",
            prototype.get("candidate_backend_commit")
            == "0e22846186e68d2d726e49817a9f74c246f517ca",
            prototype.get("revert_backend_commit")
            == "e58e67f1be69357edec0bd47e879039f47a42648",
            prototype.get("candidate_backend_dirty") is False,
            prototype.get("feature") == "xip-decode-cursor-prototype",
            prototype.get("proof_feature") == "xip-decode-cursor-proof",
            prototype.get("candidate_runner_sha256")
            == performance.get("candidate", {}).get("runner_sha256")
            == "4d7a623280d527d0d70cf04808df44be399a1c55665bc41c90ff1de61f1ad43f",
            prototype.get("proof_runner_sha256")
            == "2076a26cb01b6ff635b93eed304ea4c44cd1c6bf4b61c31e178bf8b4867b0d46",
            prototype.get("serial_core0_only") is True,
            prototype.get("scheduler_instruction_quantum") == 1,
            prototype.get("immutable_xip_range") == "0x10000000..0x14000000",
            prototype.get("production_optimization_added") is False,
            exactness.get("verdict") == "pass",
            exactness.get("stop_reason") == "scenario_done",
            exactness.get("cycles") == 927_528_660,
            exactness.get("elapsed_us") == 3_715_000,
            exactness.get("scenario_steps_passed") == 85,
            exactness.get("scenario_steps_total") == 85,
            exactness.get("event_stream_total_events") == 173_498_680,
            exactness.get("all_nine_event_domains_match_opt1b") is True,
            exactness.get("uart_sha256")
            == "bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c",
            exactness.get("framebuffer_rgb565_sha256")
            == "f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2",
            exactness.get("psram_tick_count") == 305_747_113,
            exactness.get("behavior_sha256")
            == "79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8",
            exactness.get("event_stream_sha256")
            == "2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789",
            proof.get("core1_enabled") is False,
            proof.get("core1_all_counters_zero") is True,
            core0_proof.get("enabled") is True,
            core0_proof.get("buffered_entries_at_stop") == 1,
            core0_proof.get("take_hits") == 134_612_445,
            core0_proof.get("take_misses") == 38_102_585,
            core0_proof.get("installs") == 57_047_061,
            core0_proof.get("staged_entries") == 168_959_816,
            core0_proof.get("clears") == 32_017_974,
            core0_proof.get("enables") == 1,
            core0_proof.get("disables") == 0,
            report_core0_proof.get("enabled") is True,
            report_core0_proof.get("buffered_entries")
            == core0_proof.get("buffered_entries_at_stop"),
            report_core0_proof.get("take_hits") == core0_proof.get("take_hits"),
            report_core0_proof.get("take_misses") == core0_proof.get("take_misses"),
            report_core0_proof.get("installs") == core0_proof.get("installs"),
            report_core0_proof.get("staged_entries") == core0_proof.get("staged_entries"),
            report_core0_proof.get("clears") == core0_proof.get("clears"),
            report_core0_proof.get("enables") == core0_proof.get("enables"),
            report_core0_proof.get("disables") == core0_proof.get("disables"),
            report_core1_proof.get("enabled") is False,
            all(
                report_core1_proof.get(key) == 0
                for key in (
                    "buffered_entries",
                    "take_hits",
                    "take_misses",
                    "installs",
                    "staged_entries",
                    "clears",
                    "enables",
                    "disables",
                )
            ),
            performance_summary.get("method") == "trace/proof-OFF clean A/B/A/B/A/B screening",
            performance_summary.get("baseline_median_wall_seconds") == 25.98,
            performance_summary.get("candidate_median_wall_seconds") == 27.13,
            math.isclose(
                performance_summary.get("median_improvement_percent", 0.0),
                -4.4264819092,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            performance_summary.get("required_improvement_percent") == 5.0,
            performance_summary.get("all_six_runs_exact") is True,
            performance_summary.get("formal_ten_run_gate_executed") is False,
            performance_summary.get("decision") == "reject_and_revert",
            performance.get("schema_version") == 1,
            performance.get("record_id") == record_id,
            performance.get("method") == "trace/proof-OFF clean A/B/A/B/A/B screening",
            performance.get("cpu_affinity")
            == "same host and measurement session; alternating baseline/candidate",
            performance.get("formal_ten_run_gate_executed") is False,
            performance.get("formal_ten_run_gate_omission_reason")
            == "All three alternating pairs regressed and the three-run median failed the 5% adoption threshold; a ten-run promotion measurement could not change the rejection decision.",
            performance.get("all_six_runs_exact") is True,
            performance.get("decision") == "reject_and_revert",
            performance.get("baseline", {}).get("backend_commit")
            == prototype.get("baseline_backend_commit"),
            performance.get("baseline", {}).get("runner_sha256")
            == "e8483cc1ed40d0a7999c7546f02ffdeeb89848635686edd7bf0b95e93dea43ed",
            performance.get("baseline", {}).get("run_report_sha256")
            == "da42d93ef076b061b54d47f43b4bf3073ec3267c72a9550de36af40780f0329d",
            baseline_samples == [26.44, 25.66, 25.98],
            performance.get("baseline", {}).get("median_wall_seconds") == 25.98,
            performance.get("candidate", {}).get("backend_commit")
            == prototype.get("candidate_backend_commit"),
            performance.get("candidate", {}).get("run_report_sha256")
            == "2971235a5b5b18ee43e646f487f566b60738410d22cd15e42daff2d0c3f18f70",
            candidate_samples == [26.71, 27.13, 29.09],
            performance.get("candidate", {}).get("median_wall_seconds") == 27.13,
            pair_improvements == [-1.0211800303, -5.7287607171, -11.9707467283],
            math.isclose(
                performance.get("median_improvement_percent", 0.0),
                -4.4264819092,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            performance.get("required_improvement_percent") == 5.0,
            record.get("decision", {}).get("candidate_rejected") is True,
            record.get("decision", {}).get("candidate_reverted") is True,
            record.get("decision", {}).get("active_target_changed") is False,
            record.get("decision", {}).get("validation_attestation_added") is False,
            record.get("decision", {}).get("selected_next_investigation")
            == "OPT3-C compact predecoded dispatch key without eager successor copying",
            behavior.get("schema_version") == 1,
            behavior.get("normal_report_schema_version") == 8,
            behavior.get("mode") == "correctness_trace_on",
            behavior.get("backend_build", {}).get("commit")
            == "0e22846186e68d2d726e49817a9f74c246f517ca",
            behavior.get("backend_build", {}).get("dirty") is False,
            behavior.get("valid_for_wall_time") is False,
            behavior.get("behavior_sha256") == exactness.get("behavior_sha256"),
            behavior.get("behavior_projection") == opt1b_behavior.get("behavior_projection"),
            event_trace.get("total_events") == exactness.get("event_stream_total_events"),
            event_trace.get("schema_version") == 2,
            event_trace.get("sha256") == exactness.get("event_stream_sha256"),
            set(event_domains) == {
                "clock",
                "irq_exception",
                "pio_gpio",
                "psram",
                "lcd",
                "dma_dreq",
                "timer_pwm",
                "serial_bus",
                "scenario_input",
            },
            len(event_domains) == 9,
            run_report.get("schema_version") == 8,
            run_report.get("backend_build", {}).get("commit")
            == "0e22846186e68d2d726e49817a9f74c246f517ca",
            run_report.get("backend_build", {}).get("dirty") is False,
            run_report.get("firmware", {}).get("sha256") == target_record.get("firmware_sha256"),
            run_report.get("execution_model") == "Serial",
            run_report.get("step_quantum") == 1,
            run_report.get("stop_reason") == exactness.get("stop_reason"),
            run_report.get("cycles") == exactness.get("cycles"),
            run_report.get("elapsed_us") == exactness.get("elapsed_us"),
            len(run_report.get("scenario", {}).get("steps", [])) == 85,
            run_report.get("scenario", {}).get("status") == "pass",
            run_report.get("verdict", {}).get("status") == "pass",
            run_report.get("uart", {}).get("sha256")
            == exactness.get("uart_sha256"),
            run_report.get("framebuffer", {}).get("rgb565_sha256")
            == exactness.get("framebuffer_rgb565_sha256"),
            run_report.get("psram", {}).get("tick_count") == exactness.get("psram_tick_count"),
            ci.get("run_id") == 31_293_556_450,
            ci.get("head_sha")
            == "e58e67f1be69357edec0bd47e879039f47a42648",
            ci.get("conclusion") == "success",
            all(
                path.is_file()
                and artifacts.get(artifact_name + "_sha256")
                == expected_artifact_hashes[artifact_name]
                and sha256(path) == expected_artifact_hashes[artifact_name]
                for artifact_name, path in artifact_checks
            ),
        ))
        add_check(
            checks,
            name,
            aligned,
            target=target_record.get("id"),
            result=record.get("result"),
            baseline_backend=prototype.get("baseline_backend_commit"),
            candidate_backend=prototype.get("candidate_backend_commit"),
            revert_backend=prototype.get("revert_backend_commit"),
            candidate_median_wall_seconds=performance_summary.get("candidate_median_wall_seconds"),
            baseline_median_wall_seconds=performance_summary.get("baseline_median_wall_seconds"),
            decision=record.get("decision", {}).get("candidate_rejected"),
            domain_count=len(event_domains),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        IndexError,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt3c_compact_dispatch_key(checks: List[Check], root: Path) -> None:
    """Verify the OPT3-C compact decode-key prototype and rejection decision."""
    name = "opt3-c:compact-dispatch-key"
    record_id = "opt3-c-compact-dispatch-key-20260809-01"
    target_id = "picotetris-opt1b"
    target_revision = 5
    expected_domains = {
        "clock",
        "irq_exception",
        "pio_gpio",
        "psram",
        "lcd",
        "dma_dreq",
        "timer_pwm",
        "serial_bus",
        "scenario_input",
    }
    expected_artifact_hashes = {
        "run_report": "228659bd54ecf4fecb8fb819b1dbbd6ab08da0e80d9748812abd1ca087df0d72",
        "behavior_trace": "cb9d195d5c6d39a0bc3a9a3c007f2e27962fdd03319bd6da96a7a3979a6b1d9b",
        "performance_screening": (
            "ab22775ea0c47345bf0c306576c701e50dd97a0a2d5e3688bc1b695ee7f92794"
        ),
        "notes": "8f7b05ca0c17130d608eb4212748d8d59731ada969f40ad1cc3317daeb833793",
    }
    expected_omission_reason = (
        "The three-run median failed the 5% adoption threshold; "
        "a ten-run promotion measurement was not performed."
    )
    expected_next_investigation = (
        "pause performance optimization and prioritize blind app, multicore/audio, "
        "negative conformance, and headless interface work"
    )
    try:
        record_root = root / "firmware-validation/records" / record_id
        record = load_json(record_root / "record.json")
        run_report = load_json(record_root / "run-report.json")
        behavior = load_json(record_root / "behavior-trace.json")
        performance = load_json(record_root / "performance-screening.json")
        opt1b_behavior = load_json(
            root / "firmware-validation/records/opt1-b-20260808-01/behavior-trace.json"
        )
        target_record = record["target"]
        registry_target = next(
            item
            for item in load_json(root / "reference-projects/firmware-targets.json")["targets"]
            if item.get("id") == target_id
        )
        artifacts = record["artifacts"]
        exactness = record["exactness"]
        performance_summary = record["performance"]
        prototype = record["prototype"]
        decision = record["decision"]
        ci = record["ci"]
        event_trace = behavior.get("behavior_projection", {}).get("event_trace", {})
        event_domains = {item.get("name") for item in event_trace.get("domains", [])}
        baseline_samples = performance.get("baseline", {}).get("wall_seconds", [])
        candidate_samples = performance.get("candidate", {}).get("wall_seconds", [])
        pair_improvements = performance.get("pair_improvement_percent", [])

        artifact_checks = [
            (artifact_name, record_root / artifact_path)
            for artifact_name, artifact_path in (
                ("run_report", artifacts["run_report"]),
                ("behavior_trace", artifacts["behavior_trace"]),
                ("performance_screening", artifacts["performance_screening"]),
                ("notes", artifacts["notes"]),
            )
        ]

        aligned = all(
            (
                record.get("schema_version") == 1,
                record.get("record_id") == record_id,
                record.get("result") == "rejected_performance_reverted",
                record.get("roadmap_package") == "OPT3-C",
                record.get("opt3_overall_status") == "complete_no_additional_promotion",
                target_record.get("id") == target_id,
                target_record.get("revision") == target_revision,
                target_record.get("firmware_source_commit")
                == registry_target.get("source", {}).get("commit"),
                target_record.get("firmware_sha256")
                == registry_target.get("artifacts", {}).get("bin_sha256"),
                target_record.get("firmware_uf2_sha256")
                == registry_target.get("artifacts", {}).get("uf2_sha256"),
                target_record.get("scenario_sha256")
                == registry_target.get("scenario", {}).get("sha256"),
                prototype.get("baseline_backend_commit")
                == "e58e67f1be69357edec0bd47e879039f47a42648",
                prototype.get("candidate_backend_commit")
                == "3819a9d093b8ce980a61724ac8ab33ffe3003ec3",
                prototype.get("revert_backend_commit")
                == "04b2eb2fb26f126e848b5c041177324954a98290",
                prototype.get("candidate_backend_dirty") is False,
                prototype.get("feature") == "compact-dispatch-key-prototype",
                prototype.get("flags") == "bits1..6",
                prototype.get("decoded_op_size_bytes") == 12,
                prototype.get("successor_copy") is False,
                prototype.get("staging") is False,
                prototype.get("clear") is False,
                prototype.get("serial_core0_only") is True,
                prototype.get("scheduler_instruction_quantum") == 1,
                prototype.get("production_optimization_added") is False,
                exactness.get("verdict") == "pass",
                exactness.get("stop_reason") == "scenario_done",
                exactness.get("cycles") == 927_528_660,
                exactness.get("elapsed_us") == 3_715_000,
                exactness.get("scenario_steps_passed") == 85,
                exactness.get("scenario_steps_total") == 85,
                exactness.get("event_stream_total_events") == 173_498_680,
                exactness.get("all_nine_event_domains_match_opt1b") is True,
                exactness.get("uart_sha256")
                == "bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c",
                exactness.get("framebuffer_rgb565_sha256")
                == "f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2",
                exactness.get("psram_tick_count") == 305_747_113,
                exactness.get("behavior_sha256")
                == "79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8",
                exactness.get("event_stream_sha256")
                == "2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789",
                performance_summary.get("method")
                == "trace/proof-OFF clean A/B/A/B/A/B screening",
                performance_summary.get("baseline_median_wall_seconds") == 26.72,
                performance_summary.get("candidate_median_wall_seconds") == 25.61,
                math.isclose(
                    performance_summary.get("median_improvement_percent", 0.0),
                    4.1541916168,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ),
                performance_summary.get("required_improvement_percent") == 5.0,
                performance_summary.get("all_six_runs_exact") is True,
                performance_summary.get("formal_ten_run_gate_executed") is False,
                performance_summary.get("decision") == "reject_and_revert",
                performance.get("schema_version") == 1,
                performance.get("record_id") == record_id,
                performance.get("method")
                == "trace/proof-OFF clean A/B/A/B/A/B screening",
                performance.get("cpu_affinity")
                == "same host and measurement session; alternating baseline/candidate",
                performance.get("all_six_runs_exact") is True,
                performance.get("formal_ten_run_gate_executed") is False,
                performance.get("formal_ten_run_gate_omission_reason")
                == expected_omission_reason,
                performance.get("decision") == "reject_and_revert",
                baseline_samples == [27.18, 26.26, 26.72],
                candidate_samples == [25.31, 25.61, 25.77],
                pair_improvements == [6.8800588668, 2.4752475248, 3.5553892216],
                math.isclose(
                    performance.get("median_improvement_percent", 0.0),
                    4.1541916168,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ),
                performance.get("required_improvement_percent") == 5.0,
                performance.get("median_improvement_percent")
                < performance.get("required_improvement_percent"),
                performance.get("baseline", {}).get("backend_commit")
                == prototype.get("baseline_backend_commit"),
                performance.get("candidate", {}).get("backend_commit")
                == prototype.get("candidate_backend_commit"),
                performance.get("baseline", {}).get("runner_sha256")
                == "332a6ea5938472447b313397fdd261c4e2a6753715b3b16659bb8f1077071a1c",
                performance.get("candidate", {}).get("runner_sha256")
                == "604d0bc5f7f615c31791a283159e1aad4811cf1990366e700dbd45e579addbf0",
                performance.get("baseline", {}).get("median_wall_seconds") == 26.72,
                performance.get("candidate", {}).get("median_wall_seconds") == 25.61,
                record.get("decision", {}).get("candidate_rejected") is True,
                record.get("decision", {}).get("candidate_reverted") is True,
                record.get("decision", {}).get("active_target_changed") is False,
                record.get("decision", {}).get("validation_attestation_added") is False,
                record.get("decision", {}).get("selected_next_investigation")
                == expected_next_investigation,
                run_report.get("schema_version") == 8,
                run_report.get("backend_build", {}).get("commit")
                == prototype.get("candidate_backend_commit"),
                run_report.get("backend_build", {}).get("dirty") is False,
                run_report.get("firmware", {}).get("sha256")
                == target_record.get("firmware_sha256"),
                run_report.get("execution_model") == "Serial",
                run_report.get("step_quantum") == 1,
                run_report.get("stop_reason") == exactness.get("stop_reason"),
                run_report.get("cycles") == exactness.get("cycles"),
                run_report.get("elapsed_us") == exactness.get("elapsed_us"),
                len(run_report.get("scenario", {}).get("steps", [])) == 85,
                run_report.get("scenario", {}).get("status") == "pass",
                run_report.get("verdict", {}).get("status") == "pass",
                run_report.get("uart", {}).get("sha256") == exactness.get("uart_sha256"),
                run_report.get("framebuffer", {}).get("rgb565_sha256")
                == exactness.get("framebuffer_rgb565_sha256"),
                run_report.get("psram", {}).get("tick_count") == exactness.get("psram_tick_count"),
                behavior.get("schema_version") == 1,
                behavior.get("normal_report_schema_version") == 8,
                behavior.get("mode") == "correctness_trace_on",
                behavior.get("backend_build", {}).get("commit")
                == prototype.get("candidate_backend_commit"),
                behavior.get("backend_build", {}).get("dirty") is False,
                behavior.get("valid_for_wall_time") is False,
                behavior.get("behavior_sha256") == exactness.get("behavior_sha256"),
                behavior.get("behavior_projection")
                == opt1b_behavior.get("behavior_projection"),
                event_trace.get("total_events") == exactness.get("event_stream_total_events"),
                event_trace.get("schema_version") == 2,
                event_trace.get("sha256") == exactness.get("event_stream_sha256"),
                set(event_domains) == expected_domains,
                len(event_domains) == 9,
                ci.get("repository") == "FuyukiYoneyama/picoem-picocalc",
                ci.get("run_id") == 31_299_159_125,
                ci.get("head_sha")
                == "04b2eb2fb26f126e848b5c041177324954a98290",
                ci.get("conclusion") == "success",
                all(
                    path.is_file()
                    and artifacts.get(f"{artifact_name}_sha256")
                    == expected_artifact_hashes[artifact_name]
                    and sha256(path) == expected_artifact_hashes[artifact_name]
                    for artifact_name, path in artifact_checks
                ),
            )
        )
        add_check(
            checks,
            name,
            aligned,
            target=target_record.get("id"),
            result=record.get("result"),
            baseline_backend=prototype.get("baseline_backend_commit"),
            candidate_backend=prototype.get("candidate_backend_commit"),
            revert_backend=prototype.get("revert_backend_commit"),
            candidate_median_improvement_percent=performance.get("median_improvement_percent"),
            baseline_median_wall_seconds=performance_summary.get("baseline_median_wall_seconds"),
            candidate_median_wall_seconds=performance_summary.get("candidate_median_wall_seconds"),
            opt3_overall_status=record.get("opt3_overall_status"),
            domain_count=len(event_domains),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_next1_picoedit_blind_contract(checks: List[Check], root: Path) -> None:
    """Verify the fixed NEXT-1 blind-contract baseline and scenario constraints."""
    name = "next1:picoedit-blind-contract"
    contract_path = root / "blind-validation/picoedit-contract-v1.json"
    doc_path = root / "docs/NEXT1_PICOEDIT_BLIND_CONTRACT.md"
    expected_contract_sha256 = (
        "82ca4bc9666631dd040bd40894ece5a344416b75f318025e02c8ffad662ffc31"
    )
    expected_doc_sha256 = (
        "6189c4dbabf4f1a2204fdcacc89c355a3d66d7313524e0c9772dcc77816e5b13"
    )
    expected = {
        "schema_version": 1,
        "contract_id": "next1-picoedit-blind-v1-20260809",
        "status": "frozen_before_application_implementation",
        "application": {
            "name": "PicoEdit",
            "repository_directory": "picoedit-picocalc",
            "kind": "single-core FAT32 ASCII text editor",
            "max_document_bytes": 65_536,
            "authoritative_document_store": "PSRAM",
            "lcd_variant": "pio-rgb565",
            "sd_format": "fat32",
            "execution_model": "Serial",
            "scheduler_instruction_quantum": 1,
        },
        "frozen_baseline": {
            "picocalc_emu_commit": "08275fd0d5a58dc26d2ef8bf21d6f0125bbe355b",
            "promoted_backend_commit": "e985a9d7ecb51ef760506a105edd34e31cf9b5f1",
            "pico_sdk_version": "2.2.0",
            "pico_sdk_commit": "a1438dff1d38bd9c65dbd693f0e5db4b9ae91779",
            "arm_none_eabi_gcc": "13.2.1",
            "cmake": "3.28.3",
            "ninja": "1.11.1",
            "official_keyboard_source": "https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard",
            "official_keyboard_commit": "553da6f2408963b956779599d179d77fd611a4d7",
        },
        "prohibited_application_dependencies": [
            "ff.h",
            "picocalc/host.h",
            "emulator internal types",
            "structured report internals",
            "scenario runner internals",
            "PICOEM_* compile definitions",
            "emulator-only branches",
        ],
        "declared_prerequisite_gap": {
            "baseline_public_filesystem_is_read_only_except_fixed_smoke": True,
            "must_be_added_before_generation": [
                "create/truncate write open",
                "partial write result",
                "sync",
                "stat/existence query",
                "remove",
                "rename",
                "distinct not-found/write/sync/remove/rename errors",
            ],
            "implementation_boundary": (
                "shared Canonical BSP filesystem source used by device and host"
            ),
            "application_must_not_include_fatfs": True,
        },
        "fixed_ui_actions": [
            "open selected INPUT.TXT with Enter",
            "open search with Ctrl+F",
            "type draft and confirm with Enter",
            "move to line end with End",
            "insert space-o-k",
            "save with Ctrl+S",
        ],
        "seed_file": {
            "path": "0:/INPUT.TXT",
            "encoding": "ASCII",
            "newline": "LF",
            "bytes": 61,
            "content": "PicoEdit blind validation\nstatus: draft\nalpha beta gamma\nend\n",
            "sha256": "4e666f9e499a64cd564915d71233b02818e567c72183dc12e1ce34e4f8ec2ea7",
        },
        "expected_output": {
            "path": "0:/OUTPUT.TXT",
            "temporary_path": "0:/OUTPUT.TMP",
            "backup_path": "0:/OUTPUT.BAK",
            "encoding": "ASCII",
            "newline": "LF",
            "bytes": 64,
            "content": "PicoEdit blind validation\nstatus: draft ok\nalpha beta gamma\nend\n",
            "sha256": "5c704b1e8055cf77d3600eb4663c5b4ecf651c8b1085da2d0ada6e669ffc249e",
        },
        "host_acceptance": {
            "minimum_assertions": 100,
            "stdout_byte_identical": True,
            "hardware_free_core": True,
            "required_coverage": [
                "empty and boundary cursor",
                "insert delete backspace newline",
                "vertical horizontal home end movement",
                "forward search found and not found",
                "65536-byte capacity boundary",
                "chunked store behavior",
                "SHA-256 known vectors and canonical output",
            ],
        },
    }
    expected_first_run = {
        "backend_must_remain_frozen": True,
        "result_must_be_recorded_even_if_failure": True,
        "required_observations": [
            "fail-closed scenario completion",
            "PSRAM authoritative store used",
            "OUTPUT.TXT read-back is 64 bytes",
            "read-back SHA-256 matches expected",
            "keyboard dropped events is zero",
            "exception is absent",
            "unsupported MMIO count is zero",
            "final framebuffer evidence",
        ],
    }
    expected_hardware = {
        "same_build_bin_and_uf2": True,
        "timed_input_required": False,
        "continuous_successful_key_sequence_required": False,
        "intermediate_photograph_required": False,
        "required_evidence": [
            "final screen photograph",
            "UART log",
            "OUTPUT.TXT",
            "OUTPUT.TXT SHA-256",
        ],
        "emulator_pass_hardware_fail_classification": (
            "false_accept_and_NEXT-3_negative_conformance_seed"
        ),
    }

    def require_sha(value: Any) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None

    try:
        contract = load_json(contract_path)
        seed = contract["seed_file"]
        output = contract["expected_output"]
        seed_content = seed.get("content", "")
        output_content = output.get("content", "")
        seed_bytes = seed_content.encode("utf-8")
        output_bytes = output_content.encode("utf-8")
        aligned = all(
            (
                contract.get("schema_version") == expected["schema_version"],
                contract.get("contract_id") == expected["contract_id"],
                contract.get("status") == expected["status"],
                contract.get("application") == expected["application"],
                contract.get("frozen_baseline") == expected["frozen_baseline"],
                contract.get("prohibited_application_dependencies")
                == expected["prohibited_application_dependencies"],
                contract.get("declared_prerequisite_gap") == expected["declared_prerequisite_gap"],
                contract.get("fixed_ui_actions") == expected["fixed_ui_actions"],
                seed == expected["seed_file"],
                output == expected["expected_output"],
                contract.get("host_acceptance", {}).get("minimum_assertions")
                >= expected["host_acceptance"]["minimum_assertions"],
                contract.get("host_acceptance", {}).get("minimum_assertions") is not None,
                contract.get("host_acceptance", {}).get("stdout_byte_identical")
                is expected["host_acceptance"]["stdout_byte_identical"],
                contract.get("host_acceptance", {}).get("hardware_free_core")
                is expected["host_acceptance"]["hardware_free_core"],
                contract.get("host_acceptance", {}).get("required_coverage")
                == expected["host_acceptance"]["required_coverage"],
                contract.get("first_firmware_run", {}).get("backend_must_remain_frozen")
                is expected_first_run["backend_must_remain_frozen"],
                contract.get("first_firmware_run", {}).get("result_must_be_recorded_even_if_failure")
                is expected_first_run["result_must_be_recorded_even_if_failure"],
                contract.get("first_firmware_run", {}).get("required_observations")
                == expected_first_run["required_observations"],
                contract.get("hardware_correlation", {}).get("same_build_bin_and_uf2")
                is expected_hardware["same_build_bin_and_uf2"],
                contract.get("hardware_correlation", {}).get("timed_input_required")
                is expected_hardware["timed_input_required"],
                contract.get("hardware_correlation", {}).get("continuous_successful_key_sequence_required")
                is expected_hardware["continuous_successful_key_sequence_required"],
                contract.get("hardware_correlation", {}).get("intermediate_photograph_required")
                is expected_hardware["intermediate_photograph_required"],
                contract.get("hardware_correlation", {}).get("required_evidence")
                == expected_hardware["required_evidence"],
                contract.get("hardware_correlation", {}).get(
                    "emulator_pass_hardware_fail_classification"
                )
                == expected_hardware["emulator_pass_hardware_fail_classification"],
                doc_path.is_file(),
                sha256(contract_path) == expected_contract_sha256,
                sha256(doc_path) == expected_doc_sha256,
                seed.get("bytes") == len(seed_bytes) == expected["seed_file"]["bytes"],
                output.get("bytes") == len(output_bytes) == expected["expected_output"]["bytes"],
                seed.get("sha256")
                == hashlib.sha256(seed_bytes).hexdigest()
                == expected["seed_file"]["sha256"],
                output.get("sha256")
                == hashlib.sha256(output_bytes).hexdigest()
                == expected["expected_output"]["sha256"],
                require_sha(contract.get("frozen_baseline", {}).get("picocalc_emu_commit")),
                require_sha(contract.get("frozen_baseline", {}).get("promoted_backend_commit")),
                require_sha(contract.get("frozen_baseline", {}).get("pico_sdk_commit")),
                require_sha(contract.get("frozen_baseline", {}).get("official_keyboard_commit")),
            )
        )
        add_check(
            checks,
            name,
            aligned,
            contract_status=contract.get("status"),
            contract_id=contract.get("contract_id"),
            repo=contract.get("application", {}).get("repository_directory"),
            seed_sha=seed.get("sha256"),
            output_sha=output.get("sha256"),
            host_min_assertions=contract.get("host_acceptance", {}).get("minimum_assertions"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_next1_picoedit_hardware_correlation(
    checks: List[Check], root: Path
) -> None:
    """Verify the NEXT-1 PicoEdit same-artifact hardware evidence."""
    name = "next1:picoedit-hardware-correlation"
    try:
        record_root = (
            root
            / "firmware-validation/records/next1-picoedit-hardware-20260809-01"
        )
        record = load_json(record_root / "record.json")
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target_id = record.get("target", {}).get("id")
        target_revision = record.get("target", {}).get("revision")
        target = next(
            item
            for item in registry["targets"]
            if item.get("id") == target_id
            and item.get("revision") == target_revision
        )
        target_contract = picocalc.firmware_target_contract_sha256(target)

        input_contract_path = root / record["input_contract"]["path"]
        procedure_path = root / record["input_contract"]["procedure"]
        emulator_record_path = root / record["correlation"]["emulator_record"]
        emulator_record = load_json(emulator_record_path)

        artifact_paths = {
            artifact_name: record_root / artifact["path"]
            for artifact_name, artifact in record["artifacts"].items()
            if isinstance(artifact, dict) and "path" in artifact
        }
        required_artifacts = {
            "uart_log",
            "seed_input",
            "saved_output",
            "saved_backup",
            "final_photo",
        }
        if not required_artifacts.issubset(artifact_paths):
            raise ValueError("PicoEdit hardware evidence artifact set is incomplete")
        if not all(path.is_file() for path in artifact_paths.values()):
            raise ValueError("PicoEdit hardware evidence file is missing")

        artifact_hashes_ok = all(
            sha256(path) == record["artifacts"][artifact_name].get("sha256")
            for artifact_name, path in artifact_paths.items()
        )
        uart_bytes = artifact_paths["uart_log"].read_bytes()
        uart_text = uart_bytes.decode("utf-8", errors="strict")
        seed_bytes = artifact_paths["seed_input"].read_bytes()
        output_bytes = artifact_paths["saved_output"].read_bytes()
        backup_bytes = artifact_paths["saved_backup"].read_bytes()
        photo_bytes = artifact_paths["final_photo"].read_bytes()
        identity_line = record["artifact"]["identity_line"]
        save_marker = (
            "[PICOEDIT][SAVE] status=pass bytes=64 "
            "sha256=5c704b1e8055cf77d3600eb4663c5b4ecf651c8b1085da2d0ada6e669ffc249e "
            "expected=5c704b1e8055cf77d3600eb4663c5b4ecf651c8b1085da2d0ada6e669ffc249e "
            "readback=match psram=authoritative"
        )
        search_recovery = (
            "code=0x72 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x61 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x66 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x74 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x08 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x08 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x08 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=2 code=0x08 ctrl=up"
        )
        edit_recovery = (
            "[PICOEDIT][KEY] mode=1 code=0x20 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=1 code=0x6b ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=1 code=0x08 ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=1 code=0x6f ctrl=up\r\n"
            "[PICOEDIT][KEY] mode=1 code=0x6b ctrl=up"
        )

        expected_seed = (
            b"PicoEdit blind validation\nstatus: draft\nalpha beta gamma\nend\n"
        )
        expected_output = (
            b"PicoEdit blind validation\nstatus: draft ok\nalpha beta gamma\nend\n"
        )
        physical_run = record["physical_run"]
        correlation = record["correlation"]
        aligned = all(
            (
                record.get("schema_version") == 1,
                record.get("record_id")
                == "next1-picoedit-hardware-20260809-01",
                record.get("roadmap_package") == "NEXT-1",
                record.get("result") == "pass",
                record.get("classification")
                == "same_artifact_hardware_correlation",
                target_id == "picoedit-r1",
                target_revision == 1,
                record["target"].get("contract_sha256")
                == target_contract
                == "063f848a8583e565d55ba7991f7022f0c7e3dc009f762040b532a9d6395e35d1",
                record["source"].get("commit")
                == "82a6e4c76272e8f520d2f8cba42f1a7e549d4933",
                record["source"].get("bsp_source_commit")
                == "a0041b56516ed56ddff23e80d1900a7c0fc6ab15",
                record["artifact"].get("bin_sha256")
                == target["artifacts"]["bin_sha256"],
                record["artifact"].get("uf2_sha256")
                == target["artifacts"]["uf2_sha256"],
                sha256(input_contract_path)
                == record["input_contract"].get("sha256")
                == "6d9b98b6dfd6313c1b500843e2184191b06adf260e76ef5162d64c6fd1fd6e37",
                sha256(procedure_path)
                == record["input_contract"].get("procedure_sha256")
                == "5b50a871a7f952dddbe96032730e7fc5465a98c48c6e3121270d13a2a5c4c1ab",
                sha256(emulator_record_path)
                == correlation.get("emulator_record_sha256")
                == "bb5ac456e593cf45b7b76d281f3cbfc38be968a3d7c7408e5664d60b9c4c2652",
                emulator_record.get("result") == "pass",
                emulator_record.get("target", {}).get("id") == target_id,
                emulator_record.get("firmware_run", {}).get("firmware_bin_sha256")
                == record["artifact"].get("bin_sha256"),
                artifact_hashes_ok,
                seed_bytes == expected_seed,
                output_bytes == expected_output,
                backup_bytes == expected_output,
                len(uart_bytes) == record["artifacts"]["uart_log"].get("bytes") == 3620,
                identity_line in uart_text,
                "[PICOCALC][PSRAM] status=ok" in uart_text,
                "[PICOEDIT][SD] component=init status=ok detail=1" in uart_text,
                "[PICOEDIT][LOAD] status=pass path=0:/INPUT.TXT bytes=61" in uart_text,
                uart_text.count(save_marker) == 3,
                search_recovery in uart_text,
                edit_recovery in uart_text,
                physical_run["editing"].get("human_recovery_exercised") is True,
                physical_run["save"].get("successful_save_count") == 3,
                physical_run["sd_post_run"].get("temporary_file_absent") is True,
                physical_run["final_screen"].get("result") == "pass",
                physical_run["final_screen"].get("observed_status")
                == "SAVED - 64 bytes SHA PASS",
                photo_bytes[:2] == b"\xff\xd8",
                photo_bytes[-2:] == b"\xff\xd9",
                b"Exif\x00\x00" not in photo_bytes,
                b"http://ns.adobe.com/xap/1.0/" not in photo_bytes,
                correlation.get("same_registered_artifact") is True,
                correlation.get("hardware_correlation_completed") is True,
                correlation.get("emulator_result") == "pass",
                correlation.get("hardware_result") == "pass",
                correlation.get("emulator_pass_hardware_fail_count") == 0,
                correlation.get("false_accept") is False,
                correlation.get("verdict") == "pass",
            )
        )
        add_check(
            checks,
            name,
            aligned,
            record_id=record.get("record_id"),
            target=target_id,
            target_revision=target_revision,
            save_count=uart_text.count(save_marker),
            human_recovery_exercised=physical_run["editing"].get(
                "human_recovery_exercised"
            ),
            output_sha256=sha256(artifact_paths["saved_output"]),
            verdict=correlation.get("verdict"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_next2_multicore_contract(checks: List[Check], root: Path) -> None:
    """Verify the frozen NEXT-2A SDK multicore conformance contract."""
    name = "next2:multicore-contract"
    contract_path = root / "firmware-validation/contracts/next2-multicore-v1.json"
    doc_path = root / "docs/NEXT2_MULTICORE_CONFORMANCE.md"
    expected_markers = [
        "[NEXT2][MC][LAUNCH] status=pass ready=0xc0110001",
        "[NEXT2][MC][FIFO] status=pass vectors=4",
        "[NEXT2][MC][WFE_SEV] status=pass before=1 after=2",
        "[NEXT2][MC][IRQ_PROC1] status=pass count=1 word=0x13579bdf",
        "[NEXT2][MC][VERDICT] launch=pass fifo=pass wfe_sev=pass irq_proc1=pass overall=pass",
    ]
    expected_vectors = [
        {"input": "0x00000000", "output": "0x4b4ab4b5"},
        {"input": "0x12345678", "output": "0xde44308a"},
        {"input": "0xffffffff", "output": "0xd2d52d2a"},
        {"input": "0x0badcafe", "output": "0xe0890a4a"},
    ]
    try:
        contract = load_json(contract_path)
        phases = {phase.get("id"): phase for phase in contract["fixed_phases"]}
        baseline = contract["frozen_baseline"]
        first_run = contract["first_firmware_run"]
        formal = contract["formal_acceptance"]
        hardware = contract["hardware_correlation"]
        aligned = all(
            (
                contract.get("schema_version") == 1,
                contract.get("contract_id") == "next2-multicore-v1-20260809",
                contract.get("status") == "frozen_before_application_implementation",
                contract.get("roadmap_package") == "NEXT-2A",
                contract.get("application", {}).get("repository_directory")
                == "picocalc-multicore",
                contract.get("application", {}).get("kind")
                == "dual-core Pico SDK firmware conformance",
                contract.get("application", {}).get("execution_model") == "Serial",
                contract.get("application", {}).get("scheduler_instruction_quantum") == 1,
                contract.get("application", {}).get("human_input_required") is False,
                baseline.get("picocalc_emu_commit")
                == "76334780b2c5d7854c4707d7ce963f971b0a39c8",
                baseline.get("promoted_backend_commit")
                == "e985a9d7ecb51ef760506a105edd34e31cf9b5f1",
                baseline.get("pico_sdk_version") == "2.2.0",
                baseline.get("pico_sdk_commit")
                == "a1438dff1d38bd9c65dbd693f0e5db4b9ae91779",
                contract.get("required_sdk_paths")
                == [
                    "multicore_launch_core1",
                    "multicore_fifo_push_blocking",
                    "multicore_fifo_pop_blocking",
                    "__wfe",
                    "__sev",
                    "SIO_IRQ_PROC1",
                ],
                set(phases) == {"launch", "fifo", "wfe_sev", "irq_proc1"},
                phases["launch"].get("ready_word") == "0xc0110001",
                phases["fifo"].get("vectors") == expected_vectors,
                phases["wfe_sev"].get("armed_word") == "0xc0111001",
                phases["wfe_sev"].get("done_word") == "0xc0111002",
                phases["irq_proc1"].get("armed_word") == "0xc0112001",
                phases["irq_proc1"].get("input_word") == "0x13579bdf",
                phases["irq_proc1"].get("done_word") == "0xc0112002",
                phases["irq_proc1"].get("expected_irq_count") == 1,
                contract.get("required_uart_markers") == expected_markers,
                first_run.get("backend_must_remain_frozen") is True,
                first_run.get("result_must_be_recorded_even_if_failure") is True,
                first_run.get("expected_backend_commit")
                == baseline.get("promoted_backend_commit"),
                formal.get("same_artifact_bin_and_uf2") is True,
                formal.get("clean_clone_reproducible_builds") == 2,
                formal.get("firmware_runs") == 3,
                formal.get("core1_fatal_exception_must_fail") is True,
                formal.get("threaded_execution_model_in_scope") is False,
                hardware.get("human_key_input_required") is False,
                hardware.get("required_evidence")
                == ["complete UART log", "one final PASS photograph"],
                "DMA-paced PCM sample output" in contract.get("out_of_scope", []),
                sha256(contract_path)
                == "366c73583cdf94a788842a5891d546fbf29fbef016219485507e1d84be79dc03",
                doc_path.is_file(),
                "next2-multicore-v1-20260809" in doc_path.read_text(encoding="utf-8"),
                "picocalc-multicore-r1" in doc_path.read_text(encoding="utf-8"),
            )
        )
        add_check(
            checks,
            name,
            aligned,
            contract_id=contract.get("contract_id"),
            contract_status=contract.get("status"),
            backend=baseline.get("promoted_backend_commit"),
            phase_count=len(phases),
            marker_count=len(contract.get("required_uart_markers", [])),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_next2_audio_contract(checks: List[Check], root: Path) -> None:
    """Verify the versioned NEXT-2B producer and post-quantizer sink contract."""
    name = "next2:audio-contract"
    contract_path = root / "firmware-validation/contracts/next2-audio-v3.json"
    superseded_path = root / "firmware-validation/contracts/next2-audio-v2.json"
    legacy_path = root / "firmware-validation/contracts/next2-audio-v1.json"
    oracle_path = root / "tools/next2_audio_oracle_v3.py"
    doc_path = root / "docs/NEXT2_AUDIO_CONFORMANCE.md"
    record_path = (
        root / "firmware-validation/records/next2-audio-r1-20260809-01/record.json"
    )
    negative_path = (
        root
        / "firmware-validation/records/next2-audio-r1-20260809-01/negative-mutations.json"
    )
    hardware_record_path = (
        root
        / "firmware-validation/records/next2-audio-r1-hardware-20260809-01/record.json"
    )
    expected_producer_hash = (
        "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a"
    )
    expected_sink_hash = (
        "1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f"
    )
    try:
        contract = load_json(contract_path)
        producer_vector = contract["producer_vector"]
        expected_sink = contract["expected_dma_sink"]
        dma = contract["dma_and_timer_plan"]
        timer = dma["timer"]
        blocks = dma["blocks"]
        intra = dma["intra_block_due_cycle_gaps"]
        boundary = dma["block_boundary_due_cycle_gaps"]
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(item for item in registry["targets"] if item["id"] == "picocalc-audio-r1")
        record = load_json(record_path)
        negative = load_json(negative_path)
        hardware_record = load_json(hardware_record_path)
        producer_digest = hashlib.sha256()
        sink_digest = hashlib.sha256()
        frame_count = producer_vector["frame_count"]
        left_error = 0
        right_error = 0
        for index in range(frame_count):
            left = (index * 17 + 3) & 0xFF
            right = 255 - ((index * 29 + 7) & 0xFF)
            left_pcm = left * 257 - 32768
            right_pcm = right * 257 - 32768
            producer_digest.update(struct.pack("<I", left | (right << 16)))

            left_shaped = min(65535, max(0, left_pcm + 32768 + left_error))
            right_shaped = min(65535, max(0, right_pcm + 32768 + right_error))
            left_output = min(255, max(0, (left_shaped + 128) >> 8))
            right_output = min(255, max(0, (right_shaped + 128) >> 8))
            left_error = left_shaped - left_output * 257
            right_error = right_shaped - right_output * 257
            sink_digest.update(struct.pack("<I", left_output | (right_output << 16)))

        producer_hash = producer_digest.hexdigest()
        sink_hash = sink_digest.hexdigest()
        doc = doc_path.read_text(encoding="utf-8")
        hardware_root = hardware_record_path.parent
        hardware_uart = hardware_record["physical_run"]["uart_capture"]
        hardware_final = hardware_record["physical_run"]["final_screen"]
        hardware_audio = hardware_record["physical_run"]["acoustic_capture"]
        hardware_uart_path = (
            hardware_root / hardware_record["artifacts"]["uart_log"]["path"]
        )
        hardware_photo_path = (
            hardware_root / hardware_record["artifacts"]["final_photo"]["path"]
        )
        hardware_audio_path = (
            hardware_root / hardware_record["artifacts"]["audio_capture"]["path"]
        )
        hardware_correlation = hardware_record["correlation"]
        aligned = all(
            (
                sha256(contract_path)
                == "d9624c236dfee27405c692e6ae844e0b722e2a30ffd064a89b54d714cccf71af",
                sha256(superseded_path)
                == "8c2ca770a853dbb4077b05dce6293fce433c51d0f3b271e6a06ab07953ba64b5",
                sha256(legacy_path)
                == "040dd9ae78380d0a56461c5263dddb72ae3936172418173de51243c500535c30",
                contract.get("schema_version") == 1,
                contract.get("contract_id") == "next2-audio-v3-20260809",
                contract.get("status")
                == "versioned_after_fail_closed_first_run_before_formal_acceptance",
                contract.get("roadmap_package") == "NEXT-2B",
                contract.get("supersedes", {}).get("contract_id")
                == "next2-audio-v2-20260809",
                contract.get("supersedes", {}).get("sha256")
                == sha256(superseded_path),
                contract.get("application", {}).get("repository_directory")
                == "picocalc-audio",
                contract.get("application", {}).get("execution_model") == "Serial",
                contract.get("application", {}).get("scheduler_instruction_quantum")
                == 1,
                contract.get("application", {}).get("commit")
                == "724b3ac74f1401a19d6310af387c65ad1e5476a4",
                contract.get("frozen_baseline", {}).get("backend_commit")
                == "d92db1b391a6bab078ca73ee4eb1b2ca88e394a3",
                frame_count == 49_152,
                producer_vector.get("pattern_period_frames") == 256,
                producer_vector.get("packed_seed_sha256") == expected_producer_hash,
                producer_hash == expected_producer_hash,
                expected_sink.get("sha256") == expected_sink_hash,
                sink_hash == expected_sink_hash,
                timer == {"index": 0, "x": 3, "y": 15625, "treq": 59},
                dma.get("destination", {}).get("address") == "0x40050070",
                dma.get("destination", {}).get("transfer_width_bits") == 32,
                blocks == {
                    "frames_per_block": 128,
                    "block_count": 384,
                    "software_retriggered_boundary_count": 383,
                    "malformed_block_count": 0,
                },
                intra.get("allowed") == [5208, 5209],
                intra.get("gap_5208_count") == 32640,
                intra.get("gap_5209_count") == 16128,
                intra.get("unexpected_gap_count") == 0,
                boundary.get("count") == 383,
                boundary.get("sha256")
                == "bb5372879a362de7eff7283322d1eb30b5879660cd87a90b379904253301bc06",
                len(contract.get("required_uart_markers", [])) == 5,
                contract.get("formal_acceptance", {}).get(
                    "first_backend_run_recorded_even_if_failure"
                )
                is True,
                contract.get("formal_acceptance", {}).get("firmware_runs")
                == 3,
                contract.get("formal_acceptance", {}).get(
                    "clean_clone_reproducible_builds"
                )
                == 2,
                "firmware_self_observation" in contract.get("authority_split", {}),
                "backend_authoritative_observation"
                in contract.get("authority_split", {}),
                "audio_sink" == contract.get("backend_required_report", {}).get("section"),
                contract.get("first_run_findings", {}).get("first_firmware_verdict")
                == "fail",
                contract.get("first_run_findings", {}).get("observed_dma_writes")
                == 24895,
                target.get("source", {}).get("commit")
                == "724b3ac74f1401a19d6310af387c65ad1e5476a4",
                target.get("artifacts", {}).get("bin_sha256")
                == "acaaf220fa9912a4cbd09de923f002ffe1fc0748d7c295ea997c1d28319b0cb6",
                target.get("artifacts", {}).get("uf2_sha256")
                == "d6986103e74e153fd23ea7ce25111bba0a5752331959367b0aa63f6eb1c28677",
                target.get("backend", {}).get("accepted")
                == "d92db1b391a6bab078ca73ee4eb1b2ca88e394a3",
                target.get("runner", {}).get("audio_sink", {}).get("expected_count")
                == 49152,
                target.get("runner", {}).get("audio_sink", {}).get("expected_sha256")
                == expected_sink_hash,
                record.get("result") == "pass",
                record.get("target", {}).get("id") == "picocalc-audio-r1",
                record.get("firmware_run", {}).get("runs") == 3,
                record.get("firmware_run", {}).get("all_pass") is True,
                record.get("firmware_run", {}).get("reports_byte_identical") is True,
                record.get("firmware_run", {}).get("uart_byte_identical") is True,
                record.get("firmware_run", {}).get("timelines_byte_identical") is True,
                record.get("firmware_run", {}).get("snapshots_byte_identical") is True,
                record.get("reproducible_build", {}).get("builds_compared") == 2,
                record.get("reproducible_build", {}).get("bin_reproducible") is True,
                record.get("reproducible_build", {}).get("uf2_reproducible") is True,
                record.get("audio_sink", {}).get("dma_write_count") == 49152,
                record.get("audio_sink", {}).get("pcm_sha256") == expected_sink_hash,
                record.get("negative_conformance", {}).get("result") == "pass",
                record.get("hardware_correlation", {}).get("status") == "pending",
                hardware_record.get("schema_version") == 1,
                hardware_record.get("result") == "pass",
                hardware_record.get("contract", {}).get("id")
                == "next2-audio-v3-20260809",
                hardware_record.get("target", {}).get("id") == "picocalc-audio-r1",
                hardware_record.get("target", {}).get("revision") == 1,
                len(hardware_uart.get("marker_count_each", {})) == 5,
                hardware_uart.get("complete_marker_blocks") == 18,
                all(value == 18 for value in hardware_uart["marker_count_each"].values()),
                hardware_uart.get("fail_marker_count") == 0,
                hardware_final.get("result") == "pass",
                all(
                    hardware_final.get(field) == "pass"
                    for field in ("init", "dma_cfg", "stream", "stats", "firmware")
                ),
                hardware_audio.get("result") == "pass",
                hardware_correlation.get("same_registered_artifact") is True,
                hardware_correlation.get("hardware_correlation_completed") is True,
                hardware_correlation.get("false_accept") is False,
                sha256(hardware_uart_path)
                == hardware_record["artifacts"]["uart_log"]["sha256"]
                == "75e822775cda4d4ce81d14c7b2aafbe3abfb5d413d4a8ae5587d178aee136965",
                sha256(hardware_photo_path)
                == hardware_record["artifacts"]["final_photo"]["sha256"]
                == "302f92c6b40c5b2f727e1347fc6d9d7c6c69b4e473fb9692e64cb987197dea03",
                sha256(hardware_audio_path)
                == hardware_record["artifacts"]["audio_capture"]["sha256"]
                == "ccb53ebf7c599581a90dc56c88bc2796b5dbe800c97fc7c99f1f09548eeba495",
                negative.get("result") == "pass",
                len(negative.get("mutations", [])) == 10,
                all(item.get("rejected") is True for item in negative.get("mutations", [])),
                oracle_path.is_file(),
                doc_path.is_file(),
                "next2-audio-v3-20260809" in doc,
                expected_producer_hash in doc,
                expected_sink_hash in doc,
                "formal emulator acceptance" in doc,
                "hardware correlation" in doc,
                "R5" in doc,
            )
        )
        add_check(
            checks,
            name,
            aligned,
            contract_id=contract.get("contract_id"),
            contract_status=contract.get("status"),
            frame_count=frame_count,
            producer_sha256=producer_hash,
            sample_sha256=sink_hash,
            implementation="same_artifact_hardware_correlated",
            hardware_correlation=hardware_correlation.get("verdict"),
            hardware_uart_blocks=hardware_uart.get("complete_marker_blocks"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_next2_multicore_acceptance(checks: List[Check], root: Path) -> None:
    """Verify the accepted NEXT-2A target and its three deterministic runs."""
    name = "next2:multicore-acceptance"
    try:
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(
            item for item in registry["targets"]
            if item["id"] == "picocalc-multicore-r1"
        )
        record_root = (
            root
            / "firmware-validation/records/next2-multicore-r1-20260809-01"
        )
        record = load_json(record_root / "record.json")
        run_reports = []
        report_hashes = []
        uart_hashes = []
        snapshot_hashes = []
        normalized_hashes = []
        timeline_hashes = []
        for number in (1, 2, 3):
            run_root = record_root / "runs" / "run-{}".format(number)
            report_path = run_root / "run-report.json"
            uart_path = run_root / "uart.log"
            snapshot_path = run_root / "snapshots/next2-multicore-final.png"
            report = load_json(report_path)
            run_reports.append(report)
            report_hashes.append(sha256(report_path))
            uart_hashes.append(sha256(uart_path))
            snapshot_hashes.append(sha256(snapshot_path))
            normalized_hashes.append(picocalc.normalized_json_sha256(report))
            timeline_hashes.append(
                picocalc.normalized_json_sha256(report["scenario"]["steps"])
            )

        expected_markers = target["acceptance"]["required_uart_markers"]
        reports_valid = all(
            report.get("backend_build")
            == {"commit": target["backend"]["accepted"], "dirty": False}
            and report.get("firmware", {}).get("sha256")
            == target["artifacts"]["bin_sha256"]
            and report.get("execution_model") == "Serial"
            and report.get("stop_reason") == "scenario_done"
            and report.get("cycles") == 152_548_085
            and report.get("elapsed_us") == 615_000
            and report.get("exception") is None
            and report.get("unsupported_mmio") == []
            and report.get("unsupported_mmio_truncated") is False
            and report.get("verdict", {}).get("status") == "pass"
            and report.get("verdict", {}).get("required_uart_markers")
            == expected_markers
            and report.get("scenario", {}).get("status") == "pass"
            and report.get("scenario", {}).get("steps_total") == 2
            for report in run_reports
        )
        firmware_run = record["firmware_run"]
        reproducible = record["reproducible_build"]
        aligned = all(
            (
                target.get("revision") == 1,
                target.get("status") == "active",
                target.get("source", {}).get("commit")
                == "9dfb04e1ed6bb4600b4ce4ade6a3a6b72c321837",
                target.get("backend", {}).get("accepted")
                == "38683d65800ef36026f674dd47228024d69eb5e7",
                target.get("artifacts", {}).get("bin_sha256")
                == "4d99a40413f31d3b83586083a036325bbe651bcba73297b101bd88a78b451675",
                target.get("artifacts", {}).get("uf2_sha256")
                == "d9fe9beda7a1ba63c98cc811c0009cd8982d84e40f6e1e8066bf46fcc0337de8",
                target.get("scenario", {}).get("sha256")
                == sha256(root / target["scenario"]["path"]),
                record.get("record_id") == "next2-multicore-r1-20260809-01",
                record.get("roadmap_package") == "NEXT-2A",
                record.get("result") == "pass",
                record.get("target", {}).get("contract_sha256")
                == picocalc.firmware_target_contract_sha256(target),
                record.get("backend", {}).get("core1_fatal_exception_result")
                == "pass",
                firmware_run.get("runs") == 3,
                firmware_run.get("all_pass") is True,
                firmware_run.get("reports_byte_identical") is True,
                firmware_run.get("uart_byte_identical") is True,
                firmware_run.get("timelines_byte_identical") is True,
                firmware_run.get("snapshots_byte_identical") is True,
                reproducible.get("clean_clone") is True,
                reproducible.get("builds_compared") == 2,
                reproducible.get("bin_reproducible") is True,
                reproducible.get("uf2_reproducible") is True,
                reports_valid,
                len(set(report_hashes)) == 1,
                len(set(uart_hashes)) == 1,
                len(set(snapshot_hashes)) == 1,
                len(set(normalized_hashes)) == 1,
                len(set(timeline_hashes)) == 1,
                normalized_hashes[0]
                == target["acceptance"]["normalized_report_sha256"]
                == firmware_run.get("normalized_report_sha256"),
                timeline_hashes[0]
                == target["acceptance"]["timeline_sha256"]
                == firmware_run.get("timeline_sha256"),
                report_hashes[0] == record["evidence"]["run_report_sha256"],
                uart_hashes[0] == record["evidence"]["uart_sha256"],
                snapshot_hashes[0] == record["evidence"]["snapshot_png_sha256"],
            )
        )
        add_check(
            checks,
            name,
            aligned,
            target=target.get("id"),
            backend=target.get("backend", {}).get("accepted"),
            runs=len(run_reports),
            cycles=run_reports[0].get("cycles"),
            core1_fatal_fail_closed=(
                record.get("backend", {}).get("core1_fatal_exception_result")
                == "pass"
            ),
            hardware_correlation=record.get("hardware_correlation"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_next2_multicore_v2_evidence(checks: List[Check], root: Path) -> None:
    """Verify v1 history, the v2 target, and completed v2 hardware evidence."""
    name = "next2:multicore-v2-evidence"
    try:
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(
            item for item in registry["targets"]
            if item["id"] == "picocalc-multicore-r2"
        )
        contract_path = (
            root
            / "firmware-validation/contracts/next2-multicore-hardware-evidence-v2.json"
        )
        contract = load_json(contract_path)
        attempt_root = (
            root
            / "firmware-validation/records/next2-multicore-hardware-attempt-20260809-01"
        )
        attempt = load_json(attempt_root / "record.json")
        record_root = (
            root / "firmware-validation/records/next2-multicore-r2-20260809-01"
        )
        record = load_json(record_root / "record.json")
        hardware_root = (
            root
            / "firmware-validation/records/next2-multicore-r2-hardware-20260809-01"
        )
        hardware_record_path = hardware_root / "record.json"
        hardware_record = load_json(hardware_record_path)

        report_hashes = []
        uart_hashes = []
        snapshot_hashes = []
        normalized_hashes = []
        timeline_hashes = []
        reports = []
        for number in (1, 2, 3):
            run_root = record_root / "runs" / "run-{}".format(number)
            report_path = run_root / "run-report.json"
            uart_path = run_root / "uart.log"
            snapshot_path = run_root / "snapshots/next2-multicore-final.png"
            report = load_json(report_path)
            reports.append(report)
            report_hashes.append(sha256(report_path))
            uart_hashes.append(sha256(uart_path))
            snapshot_hashes.append(sha256(snapshot_path))
            normalized_hashes.append(picocalc.normalized_json_sha256(report))
            timeline_hashes.append(
                picocalc.normalized_json_sha256(report["scenario"]["steps"])
            )

        markers = target["acceptance"]["required_uart_markers"]
        reports_valid = all(
            report.get("backend_build")
            == {"commit": target["backend"]["accepted"], "dirty": False}
            and report.get("firmware", {}).get("sha256")
            == target["artifacts"]["bin_sha256"]
            and report.get("stop_reason") == "scenario_done"
            and report.get("cycles") == 152_548_092
            and report.get("elapsed_us") == 615_000
            and report.get("exception") is None
            and report.get("unsupported_mmio") == []
            and report.get("unsupported_mmio_truncated") is False
            and report.get("verdict", {}).get("status") == "pass"
            and report.get("verdict", {}).get("required_uart_markers") == markers
            and report.get("scenario", {}).get("status") == "pass"
            and report.get("scenario", {}).get("steps_total") == 2
            for report in reports
        )

        repeat_report_path = record_root / record["late_attach_evidence_probe"]["report"]
        repeat_uart_path = record_root / record["late_attach_evidence_probe"]["uart"]
        repeat_report = load_json(repeat_report_path)
        repeat_uart = repeat_uart_path.read_text(encoding="utf-8")

        photo_path = attempt_root / attempt["artifacts"]["final_photo"]["path"]
        attempt_uart_paths = [
            attempt_root / attempt["artifacts"]["uart_attempt_1"]["path"],
            attempt_root / attempt["artifacts"]["uart_attempt_2"]["path"],
        ]
        final_screen = attempt["physical_run"]["final_screen"]
        firmware_run = record["firmware_run"]
        reproducible = record["reproducible_build"]
        probe = record["late_attach_evidence_probe"]
        hardware_uart_path = (
            hardware_root / hardware_record["artifacts"]["uart_log"]["path"]
        )
        hardware_photo_path = (
            hardware_root / hardware_record["artifacts"]["final_photo"]["path"]
        )
        hardware_uart_bytes = hardware_uart_path.read_bytes()
        hardware_uart_lines = hardware_uart_bytes.decode("utf-8").splitlines()
        hardware_run = hardware_record["physical_run"]
        hardware_uart = hardware_run["uart_capture"]
        hardware_screen = hardware_run["final_screen"]
        hardware_correlation = hardware_record["correlation"]

        aligned = all(
            (
                sha256(contract_path)
                == "5eb2a9090e255e2a59b85e9dd9b9f70d1e5e0f74eb8401108491d2c3a5d7c44b",
                contract.get("contract_id")
                == "next2-multicore-hardware-evidence-v2-20260809",
                contract.get("status") == "frozen_before_v2_application_implementation",
                contract.get("new_requirement", {}).get("period_ms") == 1000,
                contract.get("required_uart_markers") == markers,
                target.get("revision") == 2,
                target.get("supersedes") == "picocalc-multicore-r1",
                target.get("source", {}).get("commit")
                == "e9e99f0bfde7b2706fbe7f5a2a92331eed141c98",
                target.get("artifacts", {}).get("bin_sha256")
                == "a8816759038df060da3ead7a9e80b02f91e667822132b30c0c1b2436e81c0649",
                target.get("artifacts", {}).get("uf2_sha256")
                == "2e19d56560add74267dfc7e1f3876c0034e51d07a5e499ce23e868e7fc7d573f",
                target.get("scenario", {}).get("sha256")
                == sha256(root / target["scenario"]["path"]),
                record.get("target", {}).get("contract_sha256")
                == picocalc.firmware_target_contract_sha256(target),
                record.get("result") == "pass",
                firmware_run.get("runs") == 3,
                firmware_run.get("all_pass") is True,
                firmware_run.get("reports_byte_identical") is True,
                firmware_run.get("uart_byte_identical") is True,
                firmware_run.get("timelines_byte_identical") is True,
                firmware_run.get("snapshots_byte_identical") is True,
                reproducible.get("clean_clone") is True,
                reproducible.get("builds_compared") == 2,
                reproducible.get("bin_reproducible") is True,
                reproducible.get("uf2_reproducible") is True,
                reports_valid,
                len(set(report_hashes)) == 1,
                len(set(uart_hashes)) == 1,
                len(set(snapshot_hashes)) == 1,
                len(set(normalized_hashes)) == 1,
                len(set(timeline_hashes)) == 1,
                normalized_hashes[0]
                == target["acceptance"]["normalized_report_sha256"]
                == firmware_run.get("normalized_report_sha256"),
                timeline_hashes[0]
                == target["acceptance"]["timeline_sha256"]
                == firmware_run.get("timeline_sha256"),
                report_hashes[0] == record["evidence"]["run_report_sha256"],
                uart_hashes[0] == record["evidence"]["uart_sha256"],
                snapshot_hashes[0] == record["evidence"]["snapshot_png_sha256"],
                sha256(repeat_report_path) == probe.get("report_sha256"),
                sha256(repeat_uart_path) == probe.get("uart_sha256"),
                repeat_report.get("stop_reason") == "cycle_limit",
                repeat_report.get("cycles") == 500_000_000,
                repeat_report.get("exception") is None,
                repeat_report.get("unsupported_mmio") == [],
                probe.get("complete_marker_blocks") == 2,
                all(repeat_uart.count(marker) == 2 for marker in markers),
                attempt.get("result") == "evidence_incomplete",
                attempt.get("physical_run", {}).get("uart_capture", {}).get("bytes_each")
                == [0, 0],
                all(path.read_bytes() == b"" for path in attempt_uart_paths),
                sha256(photo_path)
                == attempt["artifacts"]["final_photo"]["sha256"],
                final_screen.get("result") == "pass",
                all(
                    final_screen.get(field) == "pass"
                    for field in ("launch", "fifo", "wfe_sev", "irq1", "overall")
                ),
                attempt.get("correlation", {}).get("hardware_correlation_completed")
                is False,
                record.get("hardware_correlation", {}).get("status")
                == "pending_complete_uart_evidence",
                hardware_record.get("record_id")
                == "next2-multicore-r2-hardware-20260809-01",
                hardware_record.get("result") == "pass",
                hardware_record.get("classification")
                == "same_artifact_hardware_correlation",
                hardware_record.get("contract", {}).get("id")
                == contract.get("contract_id"),
                hardware_record.get("contract", {}).get("sha256")
                == sha256(contract_path),
                hardware_record.get("contract", {}).get(
                    "required_evidence_satisfied"
                )
                is True,
                hardware_record.get("target", {}).get("id") == target.get("id"),
                hardware_record.get("target", {}).get("revision")
                == target.get("revision"),
                hardware_record.get("target", {}).get("contract_sha256")
                == picocalc.firmware_target_contract_sha256(target),
                hardware_record.get("source", {}).get("commit")
                == target.get("source", {}).get("commit"),
                hardware_record.get("source", {}).get("backend_commit")
                == target.get("backend", {}).get("accepted"),
                hardware_record.get("artifact", {}).get("bin_sha256")
                == target.get("artifacts", {}).get("bin_sha256"),
                hardware_record.get("artifact", {}).get("uf2_sha256")
                == target.get("artifacts", {}).get("uf2_sha256"),
                hardware_record.get("artifact", {}).get(
                    "operator_reported_using_specified_uf2"
                )
                is True,
                sha256(hardware_uart_path)
                == hardware_record["artifacts"]["uart_log"]["sha256"]
                == "a5a367b8a2d614bf217a6ce96dddb9684df0f1a1bf1e09906ab406d537cf8ad2",
                len(hardware_uart_bytes) == 20_664,
                hardware_uart_bytes.count(b"\r\n") == 360,
                hardware_uart_lines == markers * 72,
                hardware_uart.get("result") == "pass",
                hardware_uart.get("complete_marker_blocks") == 72,
                hardware_uart.get("all_blocks_byte_identical") is True,
                hardware_uart.get("all_fixed_values_match_contract") is True,
                hardware_uart.get("overall_verdict") == "pass",
                all(
                    count == 72
                    for count in hardware_uart["marker_count_each"].values()
                ),
                sha256(hardware_photo_path)
                == hardware_record["artifacts"]["final_photo"]["sha256"]
                == "b86b826c7c26cd0883fd0ef5494ef40dc0e0fccbf56ff394f09517d8350ef343",
                hardware_record["artifacts"]["final_photo"][
                    "source_original_sha256"
                ]
                == "5cda6cb05b7b34ed8083b82741942751d3dd19a670623a7cd49ddf6b0d5ebac6",
                hardware_record["artifacts"]["final_photo"][
                    "decoded_rgb_sha256"
                ]
                == "e2e4729c364f40299bdeb1e8737251d9de7128fc1670c952d0b7f1d8fd989ecd",
                hardware_record["artifacts"]["final_photo"].get("width")
                == 3024,
                hardware_record["artifacts"]["final_photo"].get("height")
                == 3024,
                hardware_screen.get("result") == "pass",
                all(
                    hardware_screen.get(field) == "pass"
                    for field in ("launch", "fifo", "wfe_sev", "irq1", "overall")
                ),
                hardware_correlation.get("emulator_record_sha256")
                == sha256(record_root / "record.json"),
                hardware_correlation.get("same_registered_artifact") is True,
                hardware_correlation.get("hardware_correlation_completed") is True,
                hardware_correlation.get("emulator_result") == "pass",
                hardware_correlation.get("hardware_result") == "pass",
                hardware_correlation.get("emulator_pass_hardware_fail_count") == 0,
                hardware_correlation.get("false_accept") is False,
                hardware_correlation.get("verdict") == "pass",
            )
        )
        add_check(
            checks,
            name,
            aligned,
            target=target.get("id"),
            runs=len(reports),
            repeat_blocks=probe.get("complete_marker_blocks"),
            hardware_uart_blocks=hardware_uart.get("complete_marker_blocks"),
            physical_function=hardware_correlation.get("hardware_result"),
            hardware_correlation=hardware_correlation.get("verdict"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, name, False, **error_details(error))


def verify_opt0_idle_profile(checks: List[Check], root: Path) -> None:
    """Verify the immutable OPT0-A profile, cost samples, and target inputs."""
    try:
        profile_path = (
            root
            / "firmware-validation/records/opt0-a-20260806-01/idle-profile.json"
        )
        expected_profile_sha = (
            "435c10d1e108ece74a8ff931f855f93fb8f04e9d61bdbde3c10ce8ae6ea6152d"
        )
        profile = load_json(profile_path)
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(
            item for item in registry["targets"] if item["id"] == "picotetris-r4"
        )
        counters = profile["counters"]
        thresholds = profile["histogram_thresholds_cycles"]
        blocked = profile["blocked_lengths"]
        safe = profile["proven_safe_lengths"]
        horizon = profile["initial_horizon_distances"]
        blocker_cycles = profile["blocker_cycles"]
        blocker_episodes = profile["blocker_episodes"]
        blocked_episodes = blocked["episodes_ge"][0]

        histograms_valid = all(
            len(histogram[field]) == 64
            and all(
                left >= right
                for left, right in zip(histogram[field], histogram[field][1:])
            )
            for histogram in (blocked, safe, horizon)
            for field in ("episodes_ge", "cycle_mass_ge")
        )
        aligned = all(
            (
                sha256(profile_path) == expected_profile_sha,
                profile.get("schema_version") == 1,
                profile.get("kind") == "rp2040_serial_idle_profile",
                profile.get("execution_model") == "Serial",
                profile.get("instrumented") is True,
                profile.get("valid_for_wall_time") is False,
                profile.get("step_quantum") == target["runner"]["quantum"] == 1,
                profile.get("stop_reason") == "scenario_done",
                profile.get("backend_build")
                == {
                    "commit": "ace66df91f87cfe18c7bec0ba47bcbc12f5c9345",
                    "dirty": False,
                },
                profile.get("firmware", {}).get("sha256")
                == target["artifacts"]["bin_sha256"],
                profile.get("run_cycles") == counters.get("total_master_cycles"),
                counters.get("total_master_cycles") == 927_528_660,
                counters.get("core0_executed_cycles") == 308_932_816,
                counters.get("core1_executed_cycles") == 0,
                counters.get("both_blocked_cycles") == 618_595_844,
                counters.get("proven_safe_cycles") == 0,
                counters.get("core0_executed_cycles")
                + counters.get("both_blocked_cycles")
                == counters.get("total_master_cycles"),
                blocked_episodes == 139,
                thresholds == [1 << bit for bit in range(64)],
                histograms_valid,
                blocked["cycle_mass_ge"][0] == counters["both_blocked_cycles"],
                safe["cycle_mass_ge"][0] == counters["proven_safe_cycles"],
                all(
                    value <= counters["both_blocked_cycles"]
                    for value in blocker_cycles.values()
                ),
                all(value <= blocked_episodes for value in blocker_episodes.values()),
            )
        )
        add_check(
            checks,
            "opt0-a:serial-idle-profile",
            aligned,
            backend_commit=profile.get("backend_build", {}).get("commit"),
            both_blocked_cycles=counters.get("both_blocked_cycles"),
            proven_safe_cycles=counters.get("proven_safe_cycles"),
            profile_sha256=sha256(profile_path),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, "opt0-a:serial-idle-profile", False, **error_details(error))

    try:
        semantic_path = (
            root
            / "firmware-validation/records/opt0-a-20260807-03/idle-profile.json"
        )
        expected_semantic_sha = (
            "03051600a195b05de067be65d264ccfb21238e70498520b32781dbb9ad237b2f"
        )
        semantic = load_json(semantic_path)
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(
            item for item in registry["targets"] if item["id"] == "picotetris-r4"
        )
        counters = semantic["counters"]
        thresholds = semantic["histogram_thresholds_cycles"]
        blocked = semantic["blocked_lengths"]
        safe = semantic["proven_safe_lengths"]
        horizon = semantic["initial_horizon_distances"]
        source_groups = (
            semantic["blocker_cycles"],
            semantic["blocker_episodes"],
            semantic["stationary_source_cycles"],
            semantic["stationary_source_episodes"],
            semantic["exact_bulk_source_cycles"],
            semantic["exact_bulk_source_episodes"],
        )
        expected_sources = {
            "pio",
            "dma",
            "pwm",
            "systick",
            "uart",
            "spi",
            "i2c",
            "adc",
            "timer",
            "pending_irq",
        }
        histograms_valid = all(
            len(histogram[field]) == 64
            and all(
                left >= right
                for left, right in zip(histogram[field], histogram[field][1:])
            )
            for histogram in (blocked, safe, horizon)
            for field in ("episodes_ge", "cycle_mass_ge")
        )
        blocked_episodes = blocked["episodes_ge"][0]
        aligned = all(
            (
                sha256(semantic_path) == expected_semantic_sha,
                semantic.get("schema_version") == 2,
                semantic.get("kind") == "rp2040_serial_idle_profile",
                semantic.get("execution_model") == "Serial",
                semantic.get("instrumented") is True,
                semantic.get("valid_for_wall_time") is False,
                semantic.get("step_quantum") == target["runner"]["quantum"] == 1,
                semantic.get("stop_reason") == "scenario_done",
                semantic.get("backend_build")
                == {
                    "commit": "9135f5ad09fe86a2330e51cd9a3ee106cb7c9642",
                    "dirty": False,
                },
                semantic.get("firmware", {}).get("sha256")
                == target["artifacts"]["bin_sha256"],
                semantic.get("run_cycles") == counters.get("total_master_cycles"),
                counters.get("total_master_cycles") == 927_528_660,
                counters.get("core0_executed_cycles") == 308_932_816,
                counters.get("core1_executed_cycles") == 0,
                counters.get("both_blocked_cycles") == 618_595_844,
                counters.get("proven_safe_cycles") == 618_595_844,
                counters.get("core0_executed_cycles")
                + counters.get("both_blocked_cycles")
                == counters.get("total_master_cycles"),
                blocked_episodes == safe["episodes_ge"][0] == 139,
                thresholds == [1 << bit for bit in range(64)],
                histograms_valid,
                blocked["cycle_mass_ge"][0] == counters["both_blocked_cycles"],
                safe["cycle_mass_ge"][0] == counters["proven_safe_cycles"],
                all(set(group) == expected_sources for group in source_groups),
                all(value == 0 for value in semantic["blocker_cycles"].values()),
                all(value == 0 for value in semantic["blocker_episodes"].values()),
                semantic["stationary_source_cycles"]["uart"]
                == counters["both_blocked_cycles"],
                semantic["exact_bulk_source_cycles"]["pwm"] == 528_360_292,
                all(
                    value <= counters["both_blocked_cycles"]
                    for value in semantic["stationary_source_cycles"].values()
                ),
                all(
                    value <= blocked_episodes
                    for value in semantic["stationary_source_episodes"].values()
                ),
            )
        )
        add_check(
            checks,
            "opt0-a:semantic-idle-profile",
            aligned,
            backend_commit=semantic.get("backend_build", {}).get("commit"),
            both_blocked_cycles=counters.get("both_blocked_cycles"),
            proven_safe_cycles=counters.get("proven_safe_cycles"),
            profile_sha256=sha256(semantic_path),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(
            checks, "opt0-a:semantic-idle-profile", False, **error_details(error)
        )

    try:
        cost_path = (
            root / "firmware-validation/records/opt0-a-20260806-02/idle-cost.json"
        )
        expected_cost_sha = (
            "98be437f5485c68b26609dd19119ccbb1a4d57964514489f0cae35c0524e0f30"
        )
        cost = load_json(cost_path)
        measurements = cost["measurements"]
        loop_median = measurements["loop_overhead"]["median_ns_per_op"]

        def measurement_valid(measurement: dict, subtract_loop: bool = True) -> bool:
            samples = measurement.get("samples_ns_per_op", [])
            raw_median = statistics.median(samples) if samples else math.nan
            expected_net = (
                max(0.0, raw_median - loop_median) if subtract_loop else raw_median
            )
            return (
                len(samples) == cost.get("retained_samples") == 10
                and all(isinstance(value, (int, float)) and value > 0 for value in samples)
                and math.isclose(
                    measurement.get("median_ns_per_op", math.nan),
                    raw_median,
                    rel_tol=1e-12,
                )
                and math.isclose(
                    measurement.get("median_net_of_loop_ns_per_op", math.nan),
                    expected_net,
                    rel_tol=1e-12,
                )
            )

        advances = measurements["quiescent_tick_peripherals_by_advance_cycles"]
        screening = cost["screening"]
        aligned = all(
            (
                sha256(cost_path) == expected_cost_sha,
                cost.get("schema_version") == 1,
                cost.get("kind") == "rp2040_serial_idle_cost_microbenchmark",
                cost.get("backend_build")
                == {
                    "commit": "5d01c8072c70841336cf48e46bc5aa7b8a669349",
                    "dirty": False,
                },
                cost.get("execution_model") == "Serial",
                cost.get("diagnostic") is True,
                cost.get("valid_for_realtime_baseline") is False,
                cost.get("iterations_per_sample") == 1_000_000,
                cost.get("warmup_iterations_per_family") == 10_000,
                cost.get("current_probe_scope", {}).get("complete_event_horizon")
                is False,
                cost.get("current_probe_scope", {}).get("lazy_deadline_sources")
                == ["timer"],
                measurement_valid(measurements["loop_overhead"], subtract_loop=False),
                measurement_valid(measurements["current_conservative_probe"]),
                measurement_valid(measurements["blocked_step_quantum_1"]),
                set(advances) == {"1", "64", "1024", "1048576"},
                all(measurement_valid(value) for value in advances.values()),
                screening.get("eligible_for_optimization_priority_decision")
                is False,
                screening.get("event_fire_and_route_cost_measured") is False,
                screening.get("clock_update_and_wake_check_cost_measured") is False,
                screening.get("full_all_source_horizon_cost_measured") is False,
            )
        )
        add_check(
            checks,
            "opt0-a:idle-cost-microbenchmark",
            aligned,
            backend_commit=cost.get("backend_build", {}).get("commit"),
            retained_samples=cost.get("retained_samples"),
            eligible_for_priority=screening.get(
                "eligible_for_optimization_priority_decision"
            ),
            record_sha256=sha256(cost_path),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(
            checks, "opt0-a:idle-cost-microbenchmark", False, **error_details(error)
        )

    try:
        complete_root = (
            root / "firmware-validation/records/opt0-a-20260808-04"
        )
        profile_path = complete_root / "idle-profile.json"
        cost_path = complete_root / "idle-cost.json"
        baseline_path = complete_root / "blocked-production-baseline.json"
        profile = load_json(profile_path)
        cost = load_json(cost_path)
        baseline = load_json(baseline_path)

        def retained_measurement_valid(record: dict, measurement: dict) -> bool:
            samples = measurement.get("samples_ns_per_op", [])
            loop_samples = record["measurements"]["loop_overhead"][
                "samples_ns_per_op"
            ]
            if not samples or not loop_samples:
                return False
            raw = statistics.median(samples)
            loop = statistics.median(loop_samples)
            return (
                len(samples) == record.get("retained_samples") == 10
                and all(value > 0 for value in samples)
                and math.isclose(
                    measurement.get("median_ns_per_op", math.nan),
                    raw,
                    rel_tol=1e-12,
                )
                and math.isclose(
                    measurement.get("median_net_of_loop_ns_per_op", math.nan),
                    max(0.0, raw - loop),
                    rel_tol=1e-12,
                )
            )

        counters = profile["counters"]
        event_lengths = profile["event_bounded_safe_lengths"]
        boundary_events = profile["horizon_boundary_events"]
        profile_valid = all(
            (
                sha256(profile_path)
                == "90eb5b92902e254e75e81fa84e17b70104bad0ba22f268057a234145e2abf447",
                profile.get("schema_version") == 3,
                profile.get("backend_build")
                == {
                    "commit": "8bd6809116ad9e38de9deea961603dfb2884101b",
                    "dirty": False,
                },
                counters.get("total_master_cycles") == 927_528_660,
                counters.get("both_blocked_cycles") == 618_595_844,
                counters.get("proven_safe_cycles") == 618_595_844,
                event_lengths["episodes_ge"][0] == 2_064_042,
                event_lengths["cycle_mass_ge"][0] == 618_595_844,
                boundary_events.get("pwm") == 2_063_903,
                boundary_events.get("timer") == 138,
                sum(boundary_events.values()) == 2_064_041,
                all(
                    left >= right
                    for field in ("episodes_ge", "cycle_mass_ge")
                    for left, right in zip(
                        event_lengths[field], event_lengths[field][1:]
                    )
                ),
            )
        )

        cost_measurements = cost["measurements"]
        cost_screening = cost["screening"]
        cost_valid = all(
            (
                sha256(cost_path)
                == "3e7dc98b8ecc48a134619b00a8d300611dc1147386514c9a1eb9e849671edf7f",
                cost.get("schema_version") == 3,
                cost.get("backend_build")
                == {
                    "commit": "67fc4bce7934885b439bc80629175dafeab2299f",
                    "dirty": False,
                },
                cost.get("current_probe_scope", {}).get("complete_event_horizon")
                is True,
                retained_measurement_valid(
                    cost, cost_measurements["full_all_source_horizon_probe"]
                ),
                retained_measurement_valid(
                    cost,
                    cost_measurements[
                        "quiescent_tick_peripherals_by_advance_cycles"
                    ]["1"],
                ),
                cost_screening.get("full_all_source_horizon_cost_measured")
                is True,
                cost_screening.get("event_fire_route_and_wake_increment_measured")
                is True,
                cost_screening.get("requires_matching_workload_horizon_profile")
                is True,
                cost_screening.get("eligible_for_optimization_priority_decision")
                is False,
            )
        )

        baseline_measurements = baseline["measurements"]
        baseline_valid = all(
            (
                sha256(baseline_path)
                == "d296768c2bd729ff253615124881dca0584a98cf1247320d376d8f2047ab7a25",
                baseline.get("schema_version") == 1,
                baseline.get("backend_build")
                == {
                    "commit": "67fc4bce7934885b439bc80629175dafeab2299f",
                    "dirty": False,
                },
                baseline.get("idle_profiler_compiled") is False,
                set(baseline_measurements["blocked_step_by_advance_cycles"])
                == {"1", "64", "125", "1024"},
                all(
                    retained_measurement_valid(baseline, measurement)
                    for measurement in baseline_measurements[
                        "blocked_step_by_advance_cycles"
                    ].values()
                ),
            )
        )
        add_check(
            checks,
            "opt0-a:complete-horizon-cost-decision",
            profile_valid and cost_valid and baseline_valid,
            profile_sha256=sha256(profile_path),
            cost_sha256=sha256(cost_path),
            production_baseline_sha256=sha256(baseline_path),
            event_bounded_segments=event_lengths["episodes_ge"][0],
            pwm_boundaries=boundary_events.get("pwm"),
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        statistics.StatisticsError,
        json.JSONDecodeError,
    ) as error:
        add_check(
            checks,
            "opt0-a:complete-horizon-cost-decision",
            False,
            **error_details(error),
        )


def verify_r5_performance(checks: List[Check], root: Path) -> None:
    """Verify the R5-preflight wall-time record against the active R4 target."""
    try:
        def summary_matches(recorded: dict, values: List[float]) -> bool:
            mean = statistics.mean(values)
            deviation = statistics.stdev(values)
            half_width = 2.262157 * deviation / math.sqrt(len(values))
            expected = {
                "mean": mean,
                "median": statistics.median(values),
                "sample_stddev": deviation,
                "minimum": min(values),
                "maximum": max(values),
            }
            scalars_match = all(
                math.isclose(
                    recorded.get(key, math.nan),
                    value,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
                for key, value in expected.items()
            )
            interval = recorded.get("mean_ci95")
            return (
                scalars_match
                and isinstance(interval, list)
                and len(interval) == 2
                and math.isclose(
                    interval[0], mean - half_width, rel_tol=1e-12, abs_tol=1e-9
                )
                and math.isclose(
                    interval[1], mean + half_width, rel_tol=1e-12, abs_tol=1e-9
                )
            )

        record = load_json(
            root
            / "firmware-validation/records/r5-preflight-20260806-01/realtime-performance.json"
        )
        r4_record = load_json(
            root / "firmware-validation/records/r4-20260806-01/report.json"
        )
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(item for item in registry["targets"] if item["id"] == "picotetris-r4")
        target_record = record["target"]
        measurements = record["measurements"]
        emulated_seconds = target_record["emulated_us"] / 1_000_000
        wall_seconds = [item["wall_ns"] / 1_000_000_000 for item in measurements]
        percentages = [emulated_seconds / wall * 100 for wall in wall_seconds]
        slowdowns = [wall / emulated_seconds for wall in wall_seconds]
        throughputs = [target_record["cycles"] / wall for wall in wall_seconds]
        recorded_wall = record["statistics"]["wall_seconds"]
        recorded_percent = record["statistics"]["real_time_percent"]
        recorded_throughput = record["statistics"]["emulated_cycles_per_wall_second"]
        recorded_slowdown = record["statistics"]["slowdown"]
        theory = record["theory"]
        virtual_hz = target_record["cycles"] / emulated_seconds
        host_hz = record["environment"]["reported_cpu_mhz"] * 1_000_000
        dispatch_hz = virtual_hz / target_record["step_quantum"]
        host_cycle_budget = host_hz / dispatch_hz
        per_run_valid = all(
            item.get("run") == index
            and isinstance(item.get("wall_ns"), int)
            and item["wall_ns"] > 0
            and math.isclose(
                item.get("real_time_percent", -1), percentages[index - 1], abs_tol=0.000001
            )
            and math.isclose(
                item.get("slowdown", -1), slowdowns[index - 1], abs_tol=0.000001
            )
            for index, item in enumerate(measurements, 1)
        )
        summaries_valid = all(
            (
                summary_matches(recorded_wall, wall_seconds),
                summary_matches(recorded_percent, percentages),
                summary_matches(recorded_throughput, throughputs),
                summary_matches(recorded_slowdown, slowdowns),
            )
        )
        theory_valid = all(
            (
                theory.get("real_time_target_percent") == 100.0,
                math.isclose(
                    theory.get("ideal_wall_seconds", math.nan), emulated_seconds
                ),
                math.isclose(
                    theory.get("required_emulated_cycles_per_wall_second", math.nan),
                    virtual_hz,
                    rel_tol=1e-12,
                ),
                math.isclose(
                    theory.get("host_cycles_per_dispatch_budget_at_100_percent", math.nan),
                    host_cycle_budget,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                ),
                math.isclose(
                    theory.get("one_host_cycle_per_dispatch_ceiling_percent", math.nan),
                    host_cycle_budget * 100,
                    rel_tol=1e-12,
                ),
                theory.get("ceiling_is_a_prediction") is False,
            )
        )
        deterministic = record["determinism"]
        firmware_regression = r4_record["firmware_regression"]
        aligned = all(
            (
                record.get("schema_version") == 1,
                record.get("record_id") == "r5-preflight-20260806-01",
                record.get("roadmap_package") == "R5",
                record.get("scope") == "preflight_realtime_performance_only",
                record.get("hardware_correlation_completed") is False,
                record.get("metric")
                == "real_time_percent = emulated_seconds / wall_seconds * 100",
                record.get("result") == "pass",
                target_record.get("id") == target["id"],
                target_record.get("revision") == target["revision"],
                target_record.get("firmware_sha256")
                == target["artifacts"]["bin_sha256"],
                target_record.get("backend_commit") == target["backend"]["accepted"],
                target_record.get("scenario_sha256") == target["scenario"]["sha256"],
                target_record.get("step_quantum") == target["runner"]["quantum"] == 1,
                target_record.get("cycles") == firmware_regression["cycles"],
                target_record.get("emulated_us") == firmware_regression["elapsed_us"],
                len(measurements) == record["method"].get("measured_runs") == 10,
                record["method"].get("warmup_runs_excluded") == 1,
                record["method"].get("build_time_included") is False,
                record["method"].get("target_validation_included") is False,
                record["method"].get("runner_startup_and_artifact_writes_included")
                is True,
                record["method"].get("all_measured_runs_accepted") is True,
                per_run_valid,
                summaries_valid,
                theory_valid,
                deterministic.get("all_reports_identical") is True,
                deterministic.get("report_sha256")
                == firmware_regression["raw_report_sha256"],
                deterministic.get("all_uart_identical") is True,
                deterministic.get("uart_sha256") == firmware_regression["uart_sha256"],
                deterministic.get("all_snapshots_identical") is True,
                deterministic.get("snapshot_png_sha256")
                == firmware_regression["snapshot_png_sha256"],
            )
        )
        add_check(
            checks,
            "r5:realtime-performance-baseline",
            aligned,
            target=target["id"],
            measured_runs=len(measurements),
            median_real_time_percent=recorded_percent["median"],
            hardware_correlation_completed=record["hardware_correlation_completed"],
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, "r5:realtime-performance-baseline", False, **error_details(error))


def verify_r5_hardware_correlation(checks: List[Check], root: Path) -> None:
    """Verify the R5 hardware correlation evidence record and its artifacts."""
    try:
        record_root = root / "firmware-validation/records/r5-hardware-20260808-01"
        record = load_json(record_root / "record.json")
        target_id = record.get("target", {}).get("id")
        target_revision = record.get("target", {}).get("revision")
        target_contract = record.get("target", {}).get("contract_sha256")
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(
            item
            for item in registry["targets"]
            if item.get("id") == target_id and item.get("revision") == target_revision
        )
        target_contract_expected = (
            picocalc.firmware_target_contract_sha256(target)
            if target_id and target_revision is not None
            else None
        )

        uart_path = record_root / record["artifacts"]["uart_log"]["path"]
        final_photo_path = record_root / record["artifacts"]["final_photo"]["path"]
        pcr_path = record_root / record["artifacts"]["keyboard_progress"]["path"]
        excerpt_path = record_root / record["artifacts"]["audible_tone_excerpt"]["path"]

        uart_text = uart_path.read_text(encoding="utf-8", errors="replace")
        preflight_record_path = root / record["correlation"]["emulator_preflight_record"]
        candidate_record_path = root / record["optimization"]["candidate_record"]
        preflight_record = load_json(preflight_record_path)
        candidate_record = load_json(candidate_record_path)

        progress = pcr_path.read_bytes()
        if len(progress) != 48:
            raise ValueError(
                f"PCR5KEY.DAT must be exactly 48 bytes, got {len(progress)}"
            )
        pressed = progress[16:25]
        released = progress[25:34]
        repeated = progress[34:43]
        progress_crc_target = struct.unpack("<I", progress[44:48])[0]
        progress_crc_actual = binascii.crc32(progress[:44]) & 0xFFFFFFFF
        bit_count = 67
        used_mask_last = (1 << (bit_count % 8)) - 1
        unused_bits_zero = all(
            (values[-1] & ~used_mask_last) == 0
            for values in (pressed, released, repeated)
        )
        reserved_byte_zero = progress[43] == 0
        pressed_count = sum(bit_is_set(pressed, index) for index in range(bit_count))
        released_count = sum(bit_is_set(released, index) for index in range(bit_count))
        up_repeat = bit_is_set(repeated, 64)
        down_repeat = bit_is_set(repeated, 65)
        completed = (
            pressed_count >= bit_count
            and released_count >= bit_count
            and up_repeat
            and down_repeat
        )

        artifact_checks = {
            "uart_log": (
                uart_path,
                "d9b2b8417bb88af4f6a5432235fd12a0bbe83e86500668998b6c349093b0181a",
            ),
            "final_photo": (
                final_photo_path,
                "7cb0e8789476b82168e8d0250385267290bfaa0fef42ea0bbfab48a38690ab1a",
            ),
            "keyboard_progress": (
                pcr_path,
                "0e6e09a6f787c2ee95ccc4671ef2bd67caab8d6434456071cf125ded1ca0c16e",
            ),
            "audible_tone_excerpt": (
                excerpt_path,
                "5266ee1337d58191ebde23d08dc1aeabbc65183b4068d9b2c60e113425687f19",
            ),
        }
        artifact_records = record.get("artifacts", {})
        artifact_hashes_ok = set(artifact_checks).issubset(artifact_records) and all(
            artifact_records[name].get("sha256") == expected_sha
            and sha256(path) == expected_sha
            for name, (path, expected_sha) in artifact_checks.items()
        )
        artifact_files_exist = all(path.is_file() for path, _ in artifact_checks.values())

        optimized_promoted = record.get("optimization", {}).get("status") == "promoted"
        final_verdict_line = record.get("physical_run", {}).get("final_verdict", "")
        audible = record.get("audible_tone", {})
        aligned = all(
            (
                record.get("result") == "pass",
                record.get("record_id") == "r5-hardware-20260808-01",
                target_id == "picotetris-r5",
                target_revision == 4,
                target_contract is not None,
                target_contract == target_contract_expected,
                record.get("source", {}).get("commit")
                == "9a40a905f3ddcc6dc835655e2a332fce88f98800",
                record.get("source", {}).get("bsp_source_commit")
                == "cbfc90467e2b8392fbd0429c83925b94ca365824",
                record.get("artifact", {}).get("bin_sha256")
                == "8b4ac5c0026bb582825fd767ecd26d5278710590a2e2312ce4b817d12c60adc0",
                record.get("artifact", {}).get("uf2_sha256")
                == "0e990cff819b8542a7a96765cd7004c7b23cb52b77494c745b914afd32f084f1",
                artifact_files_exist,
                artifact_hashes_ok,
                sha256(preflight_record_path)
                == record["correlation"].get("emulator_preflight_record_sha256")
                == "d63f9d77fa99f35025452a697da1b7657eea601cc8ad55ff07216dcefd40f3e6",
                sha256(candidate_record_path)
                == record["optimization"].get("candidate_record_sha256")
                == "0720ff9024de968e17ce32996eadb44a5a29ab3e994a0234886325d6c55f57d2",
                preflight_record.get("result") == "pass",
                candidate_record.get("result") == "pass",
                record.get("correlation", {}).get("hardware_correlation_completed") is True,
                record.get("correlation", {}).get("verdict") == "pass",
                record.get("artifact", {}).get("r5_identity_line", "")
                in uart_text,
                final_verdict_line in uart_text,
                final_photo_path.read_bytes()[:2] == b"\xFF\xD8",
                progress[:8] == b"PCR5KEY\x00",
                struct.unpack("<I", progress[8:12])[0] == 1,
                struct.unpack("<I", progress[12:16])[0]
                == binascii.crc32(
                    record.get("source", {}).get("commit", "")[:12].encode("ascii")
                )
                & 0xFFFFFFFF
                == 0x1309E999,
                progress_crc_actual == progress_crc_target,
                pressed_count == bit_count,
                released_count == bit_count,
                up_repeat,
                down_repeat,
                unused_bits_zero,
                reserved_byte_zero,
                completed is True,
                record.get("progress_file", {}).get("bytes") == len(progress),
                record.get("progress_file", {}).get("crc32")
                == f"0x{progress_crc_target:08x}",
                record.get("progress_file", {}).get("unused_bits_zero") is True,
                optimized_promoted,
                audible.get("result") == "pass",
                audible.get("expected_hz") == 1000,
                sha256(excerpt_path)
                == audible.get("stored_excerpt_sha256", ""),
            )
        )
        add_check(
            checks,
            "r5:hardware-correlation-evidence",
            aligned,
            record_id=record.get("record_id"),
            target=target_id,
            target_revision=target_revision,
            preflight_record=record["correlation"].get("emulator_preflight_record"),
            candidate_record=record["optimization"].get("candidate_record"),
            preflight_sha256=sha256(preflight_record_path),
            candidate_sha256=sha256(candidate_record_path),
            pressed_keys=pressed_count,
            released_keys=released_count,
            completed=completed,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        json.JSONDecodeError,
    ) as error:
        add_check(checks, "r5:hardware-correlation-evidence", False, **error_details(error))


def verify_r3_contract(checks: List[Check], root: Path) -> None:
    """Verify the portable R3 target, evidence record and recovery bundle."""
    try:
        manifest = load_json(root / "provenance/picotetris-r3.json")
        record = load_json(
            root / "firmware-validation/records/r3-20260806-01/report.json"
        )
        registry = picocalc.load_firmware_registry(
            root / "reference-projects/firmware-targets.json"
        )
        target = next(
            item for item in registry["targets"] if item["id"] == "picotetris-r3"
        )
        bundle_contract = manifest["bundle"]
        source_commit = manifest["regression_source_commit"]
        target_checks = {
            check["path"]: check["value"]
            for check in target["acceptance"]["report_checks"]
        }
        aligned = (
            manifest.get("schema_version") == 1
            and manifest.get("record_id") == "picotetris-r3-provenance"
            and manifest.get("remote") is None
            and re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None
            and target.get("status") == "active"
            and target["source"].get("commit") == source_commit
            and target["artifacts"].get("bin_sha256")
            == record.get("build", {}).get("bin_sha256")
            and target["artifacts"].get("uf2_sha256")
            == record.get("build", {}).get("uf2_sha256")
            and target["backend"].get("accepted")
            == record.get("firmware_regression", {}).get("backend_commit")
            and target["backend"].get("report_schema")
            == record.get("firmware_regression", {}).get("report_schema")
            and target.get("scenario", {}).get("sha256")
            == record.get("firmware_regression", {}).get("scenario_sha256")
            and target["source"].get("bsp")
            == manifest.get("bsp", {}).get("version")
            == record.get("source", {}).get("bsp_version")
            and target["source"].get("bsp_source_commit")
            == manifest.get("bsp", {}).get("source_commit")
            == record.get("source", {}).get("bsp_source_commit")
            and target["source"].get("bsp_tree_sha256")
            == manifest.get("bsp", {}).get("tree_sha256")
            == record.get("source", {}).get("bsp_tree_sha256")
            and target_checks.get("uart.sha256")
            == record.get("firmware_regression", {}).get("uart_sha256")
            and target_checks.get("framebuffer.rgb565_sha256")
            == record.get("firmware_regression", {}).get(
                "framebuffer_rgb565_sha256"
            )
            and target["acceptance"].get("normalized_report_sha256")
            == record.get("firmware_regression", {}).get("normalized_report_sha256")
            and target["acceptance"].get("timeline_sha256")
            == record.get("firmware_regression", {}).get("timeline_sha256")
            and record.get("source", {}).get("commit") == source_commit
            and record.get("provenance", {}).get("bundle_sha256")
            == bundle_contract.get("sha256")
            and bundle_contract.get("complete_history") is True
            and record.get("result") == "pass"
            and record.get("firmware_regression", {}).get("runs") == 3
            and record.get("firmware_regression", {}).get("passes") == 3
            and record.get("firmware_regression", {}).get(
                "all_compared_outputs_identical"
            )
            is True
        )
        add_check(
            checks,
            "r3:picotetris-contract",
            aligned,
            source_commit=source_commit,
            target=target.get("id"),
        )

        bundle = root / bundle_contract["path"]
        expected_hash = bundle_contract["sha256"]
        actual_hash = sha256(bundle) if bundle.is_file() else "missing"
        bundle_head = ""
        if bundle.is_file():
            completed = subprocess.run(
                ["git", "bundle", "list-heads", str(bundle), bundle_contract["ref"]],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.split():
                bundle_head = completed.stdout.split()[0]
        add_check(
            checks,
            "r3:picotetris-bundle",
            actual_hash == expected_hash and bundle_head == bundle_contract["head"],
            expected=expected_hash,
            actual=actual_hash,
            expected_head=bundle_contract["head"],
            actual_head=bundle_head or "missing",
        )

        run_problems: List[str] = []
        raw_hashes = []
        normalized_hashes = []
        timeline_hashes = []
        uart_hashes = []
        png_hashes = []
        expected_run = record["firmware_regression"]
        for run_number in range(1, 4):
            run_dir = (
                root
                / "firmware-validation/records/r3-20260806-01/runs"
                / "run-{}".format(run_number)
            )
            report_path = run_dir / "report.json"
            uart_path = run_dir / "uart.log"
            png_path = run_dir / "tetris-line-clear.png"
            if not all(path.is_file() for path in (report_path, uart_path, png_path)):
                run_problems.append("run-{} artifacts missing".format(run_number))
                continue
            run_report = load_json(report_path)
            raw_hashes.append(sha256(report_path))
            normalized_hashes.append(picocalc.normalized_json_sha256(run_report))
            timeline_hashes.append(
                picocalc.normalized_json_sha256(run_report["scenario"]["steps"])
            )
            uart_hashes.append(sha256(uart_path))
            png_hashes.append(sha256(png_path))
            if (
                run_report.get("verdict", {}).get("status") != "pass"
                or run_report.get("scenario", {}).get("status") != "pass"
                or len(run_report.get("scenario", {}).get("steps", [])) != 85
                or run_report.get("uart", {}).get("sha256") != sha256(uart_path)
                or run_report.get("framebuffer", {}).get("rgb565_sha256")
                != expected_run["framebuffer_rgb565_sha256"]
            ):
                run_problems.append("run-{} report/artifact mismatch".format(run_number))
        expected_sets = (
            (raw_hashes, expected_run["raw_report_sha256"], "raw report"),
            (
                normalized_hashes,
                expected_run["normalized_report_sha256"],
                "normalized report",
            ),
            (timeline_hashes, expected_run["timeline_sha256"], "timeline"),
            (uart_hashes, expected_run["uart_sha256"], "UART"),
            (png_hashes, expected_run["snapshot_png_sha256"], "PNG"),
        )
        for digests, expected_digest, label in expected_sets:
            if len(digests) != 3 or set(digests) != {expected_digest}:
                run_problems.append("{} digests differ".format(label))
        add_check(
            checks,
            "r3:firmware-run-evidence",
            not run_problems,
            runs=len(raw_hashes),
            errors=run_problems,
        )

        source_available = False
        source_is_ancestor = False
        clone_head = ""
        if bundle.is_file():
            with tempfile.TemporaryDirectory(prefix="picotetris-r3-bundle-") as temporary:
                checkout = Path(temporary) / "picotetris"
                cloned = subprocess.run(
                    ["git", "clone", "-q", "-b", "main", str(bundle), str(checkout)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if cloned.returncode == 0:
                    head_result = subprocess.run(
                        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    clone_head = head_result.stdout.strip()
                    source_available = subprocess.run(
                        ["git", "-C", str(checkout), "cat-file", "-e", source_commit],
                        capture_output=True,
                        check=False,
                    ).returncode == 0
                    source_is_ancestor = subprocess.run(
                        [
                            "git", "-C", str(checkout), "merge-base", "--is-ancestor",
                            source_commit, bundle_contract["head"],
                        ],
                        capture_output=True,
                        check=False,
                    ).returncode == 0
        add_check(
            checks,
            "r3:picotetris-bundle-recovery",
            clone_head == bundle_contract["head"]
            and source_available
            and source_is_ancestor,
            expected_head=bundle_contract["head"],
            actual_head=clone_head or "missing",
            source_commit=source_commit,
            source_available=source_available,
            source_is_ancestor=source_is_ancestor,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        AttributeError,
    ) as error:
        add_check(checks, "r3:picotetris-contract", False, **error_details(error))


def verify_r0_contract(checks: List[Check], root: Path) -> None:
    """Verify the portable half of the R0 generation/provenance contract."""
    try:
        manifest = load_json(root / "provenance/r0-baseline.json")
        starting_points = manifest["starting_points"]
        contracts = manifest["contracts"]
        repositories = {item["repository"] for item in starting_points}
        commits_valid = all(
            re.fullmatch(r"[0-9a-f]{40}", item["commit"]) is not None
            for item in starting_points
        )
        add_check(
            checks,
            "r0:baseline-contract",
            manifest.get("schema_version") == 1
            and manifest.get("record_id") == "r0-20260805"
            and repositories == {"picocalc_emu", "picoem-picocalc", "picotetris"}
            and commits_valid
            and contracts.get("project_metadata_schema") == 2
            and contracts.get("firmware_report_schema") == 6
            and contracts.get("host_report_schema") == 1
            and contracts.get("scenario_schema") == 1
            and contracts.get("firmware_target_registry_schema") == 1
            and contracts.get("capability_schema") == 1
            and contracts.get("runner_exit_codes")
            == {"0": "pass", "1": "judged_failure", "2": "could_not_judge"},
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        add_check(checks, "r0:baseline-contract", False, **error_details(error))

    try:
        metadata = load_json(root / "templates/rp2040-basic/.picocalc-project.json")
        bsp_version = (root / "bsp/VERSION").read_text(encoding="utf-8").strip()
        provenance = metadata["provenance"]
        bsp = provenance["bsp"]
        add_check(
            checks,
            "r0:generated-project-contract",
            metadata.get("schema_version") == 2
            and metadata.get("bsp_version") == bsp_version
            and provenance.get("kind") == "generated"
            and bsp.get("version") == bsp_version
            and bsp.get("source_path") == "bsp"
            and metadata.get("project_name") == "GENERATED_PROJECT_NAME"
            and provenance.get("generator", {}).get("commit")
            == "GENERATED_SOURCE_COMMIT"
            and bsp.get("source_commit") == "GENERATED_SOURCE_COMMIT"
            and bsp.get("tree_sha256") == "GENERATED_BSP_TREE_SHA256",
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        add_check(checks, "r0:generated-project-contract", False, **error_details(error))

    required_files = [
        "templates/rp2040-basic/LICENSE",
        "templates/rp2040-basic/THIRD_PARTY_NOTICES.md",
    ]
    missing = [path for path in required_files if not (root / path).is_file()]
    add_check(checks, "r0:generated-project-licenses", not missing, missing=missing)


def verify_r0_workspace(checks: List[Check], root: Path, workspace_root: Path) -> None:
    """Verify R0 fixed points and the reconstructed PicoTetris checkout."""
    try:
        manifest = load_json(root / "provenance/r0-baseline.json")
        fixed_points = {
            item["repository"]: item for item in manifest["fixed_points"]
        }
        required = {"picocalc_emu", "picoem-picocalc", "picotetris"}
        add_check(checks, "r0:fixed-points", set(fixed_points) == required)
        for name in sorted(required):
            item = fixed_points[name]
            repository = workspace_root / item["workspace_path"]
            commit = item["commit"]
            add_check(
                checks,
                "r0:fixed-commit:" + name,
                re.fullmatch(r"[0-9a-f]{40}", commit) is not None
                and git_has_commit(repository, commit),
                commit=commit,
                workspace_path=item["workspace_path"],
            )

        tetris = workspace_root / fixed_points["picotetris"]["workspace_path"]
        metadata = load_json(tetris / ".picocalc-project.json")
        bsp = metadata["provenance"]["bsp"]
        expected_hash = bsp["tree_sha256"]
        actual_hash = directory_sha256(tetris / "bsp")
        source_commit = bsp["source_commit"]
        source_tree = git_rev_parse(root, source_commit + ":bsp")
        add_check(
            checks,
            "r0:picotetris-provenance",
            metadata.get("schema_version") == 2
            and metadata.get("project_name") == "PicoTetris"
            and metadata.get("bsp_version") == bsp.get("version")
            and metadata.get("provenance", {}).get("kind") == "reconstructed"
            and expected_hash == actual_hash
            and git_has_commit(root, source_commit)
            and bsp.get("git_tree") == source_tree
            and (tetris / "LICENSE").is_file()
            and (tetris / "THIRD_PARTY_NOTICES.md").is_file(),
            expected_bsp_sha256=expected_hash,
            actual_bsp_sha256=actual_hash,
            bsp_source_commit=source_commit,
            bsp_source_tree=source_tree,
        )

        bundle = root / manifest["artifacts"]["picotetris_bundle"]["path"]
        expected_bundle_hash = manifest["artifacts"]["picotetris_bundle"]["sha256"]
        actual_bundle_hash = sha256(bundle) if bundle.is_file() else "missing"
        bundle_head = ""
        if bundle.is_file():
            completed = subprocess.run(
                ["git", "bundle", "list-heads", str(bundle), "refs/heads/main"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                bundle_head = completed.stdout.split()[0]
        add_check(
            checks,
            "r0:picotetris-bundle",
            actual_bundle_hash == expected_bundle_hash
            and bundle_head == manifest["artifacts"]["picotetris_bundle"]["head"],
            expected=expected_bundle_hash,
            actual=actual_bundle_hash,
            expected_head=manifest["artifacts"]["picotetris_bundle"]["head"],
            actual_head=bundle_head or "missing",
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        add_check(checks, "r0:workspace", False, **error_details(error))


def verify_references(
    checks: List[Check],
    root: Path,
    reference_root: Path,
    strict_commit: bool,
) -> None:
    try:
        catalog = load_json(root / "reference-projects/catalog.json")
        projects = catalog["projects"]
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        add_check(checks, "reference-catalog", False, **error_details(error))
        return

    for project in projects:
        try:
            name = project["name"]
            project_dir = reference_root / project["workspace_path"]
            head = git_head(project_dir) if project_dir.is_dir() else ""
            commit_ok = head == project["commit"]
            add_check(
                checks,
                "reference-commit:" + name,
                commit_ok or bool(head and not strict_commit),
                expected=project["commit"],
                actual=head or "missing",
                strict=strict_commit,
                git_url=project["git_url"],
            )
            for evidence in project["evidence"]:
                path = project_dir / evidence["path"]
                actual = sha256(path) if path.is_file() else "missing"
                add_check(
                    checks,
                    "reference-file:" + name + ":" + evidence["path"],
                    actual == evidence["sha256"],
                    expected=evidence["sha256"],
                    actual=actual,
                )
        except (OSError, UnicodeError, TypeError, KeyError) as error:
            add_check(
                checks,
                "reference-project:{}".format(project.get("name", "invalid")),
                False,
                **error_details(error),
            )


def make_report(checks: List[Check], mode: str) -> Dict[str, object]:
    failed = [check for check in checks if check["status"] != "pass"]
    return {
        "schema_version": 1,
        "mode": mode,
        "status": "pass" if not failed else "fail",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }


def emit_report(report: Dict[str, object], json_only: bool) -> None:
    if json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        print("[{}] {}".format(str(check["status"]).upper(), check["name"]))
        if check["status"] != "pass":
            print("       {}".format(json.dumps(check, ensure_ascii=False)))
    print(
        "RESULT mode={} status={} passed={} failed={}".format(
            report["mode"],
            report["status"],
            report["passed"],
            report["failed"],
        )
    )


class ReportArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        if "--json" in sys.argv[1:]:
            checks: List[Check] = []
            add_check(checks, "invocation:arguments", False, error=message)
            print(json.dumps(make_report(checks, "invalid"), indent=2))
            self.exit(2)
        super().error(message)


def main() -> int:
    parser = ReportArgumentParser()
    parser.add_argument(
        "--references",
        action="store_true",
        help="also verify external hardware-proven repositories",
    )
    parser.add_argument(
        "--strict-commit",
        action="store_true",
        help="require reference repositories to be at catalog commits",
    )
    parser.add_argument(
        "--reference-root",
        type=Path,
        help="directory containing catalog workspace_path repositories",
    )
    parser.add_argument(
        "--r0",
        action="store_true",
        help="also verify R0 fixed commits, PicoTetris provenance, and recovery bundle",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="directory containing the three R0 workspace repositories",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--scope",
        choices=("all", "core", "target-schema"),
        default="all",
        help=(
            "verification layer: all portable checks (default), core BSP checks "
            "without firmware contracts, or only target/schema contracts"
        ),
    )
    args = parser.parse_args()
    mode_parts = [
        "portable"
        if args.scope == "all"
        else "portable-core"
        if args.scope == "core"
        else "target-schema"
    ]
    if args.references:
        mode_parts.append("references")
    if args.r0:
        mode_parts.append("r0")
    mode = "+".join(mode_parts)
    checks: List[Check] = []

    if (args.strict_commit or args.reference_root is not None) and not args.references:
        add_check(
            checks,
            "invocation:arguments",
            False,
            error="--strict-commit/--reference-root require --references",
        )
        report = make_report(checks, "invalid")
        emit_report(report, args.json)
        return 2
    if args.workspace_root is not None and not args.r0:
        add_check(
            checks,
            "invocation:arguments",
            False,
            error="--workspace-root requires --r0",
        )
        report = make_report(checks, "invalid")
        emit_report(report, args.json)
        return 2
    if args.scope == "target-schema" and (args.references or args.r0):
        add_check(
            checks,
            "invocation:arguments",
            False,
            error="--scope target-schema cannot be combined with --references or --r0",
        )
        report = make_report(checks, "invalid")
        emit_report(report, args.json)
        return 2

    try:
        root = args.project_root.resolve()
        reference_root = (
            args.reference_root.resolve()
            if args.reference_root is not None
            else root.parent
        )
        if args.scope == "target-schema":
            verify_target_schema(checks, root)
        else:
            verify_portable(
                checks,
                root,
                include_target_schema=args.scope == "all",
            )
        if args.references:
            verify_references(checks, root, reference_root, args.strict_commit)
        if args.r0:
            workspace_root = (
                args.workspace_root.resolve()
                if args.workspace_root is not None
                else root.parent
            )
            verify_r0_workspace(checks, root, workspace_root)
    except Exception as error:  # Last-resort normalization for machine consumers.
        add_check(
            checks,
            "internal:verification",
            False,
            **error_details(error),
        )

    report = make_report(checks, mode)
    emit_report(report, args.json)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
