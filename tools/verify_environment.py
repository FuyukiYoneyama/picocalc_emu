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
from typing import Any, Dict, List, Mapping, Optional, Tuple

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


def verify_bsp_provenance_contract(checks: List[Check], root: Path) -> None:
    cmake_path = root / "bsp/CMakeLists.txt"
    helper_path = root / "bsp/cmake/bsp_provenance.py"
    try:
        cmake = cmake_path.read_text(encoding="utf-8")
        helper = helper_path.read_text(encoding="utf-8")
        cmake_required = (
            ".picocalc-project.json",
            "cmake/bsp_provenance.py",
            "PICOCALC_REQUIRE_CLEAN_BSP_PROVENANCE",
            "PICOCALC_BSP_GIT disagrees with generated project provenance",
            "set(PICOCALC_BSP_GIT \"untracked\")",
        )
        helper_required = (
            'metadata.get("schema_version") != 2',
            'provenance["tree_sha256"]',
            "directory_sha256(bsp_dir)",
            'parser.add_argument("--require-clean"',
        )
        missing = [token for token in cmake_required if token not in cmake]
        missing.extend(token for token in helper_required if token not in helper)
        inherited_git = "git rev-parse" in cmake or "git diff --quiet" in cmake
        add_check(
            checks,
            "source-fingerprint:bsp-provenance-contract",
            not missing and not inherited_git,
            path="bsp/CMakeLists.txt",
            helper="bsp/cmake/bsp_provenance.py",
            missing=missing,
            inherits_parent_git=inherited_git,
        )
    except (OSError, UnicodeError) as error:
        add_check(
            checks,
            "source-fingerprint:bsp-provenance-contract",
            False,
            path="bsp/CMakeLists.txt",
            helper="bsp/cmake/bsp_provenance.py",
            **error_details(error),
        )


def verify_audio_dma_restart(checks: List[Check], root: Path) -> None:
    """The EOF drain must leave the DMA channel reusable for the next track."""
    relative_path = "bsp/vendor/audio_picoment/platform/picocalc_audio_pwm.cpp"
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        start = text.index("void start_output()")
        end = text.index("bool init_common(", start)
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


def verify_audio_resource_claim_fail_safe(checks: List[Check], root: Path) -> None:
    """Audio init must fail cleanly before mutating pins when DMA is exhausted."""
    relative_path = "bsp/vendor/audio_picoment/platform/picocalc_audio_pwm.cpp"
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        start = text.index("bool init_common(")
        end = text.index("\n#if PICOMENT_FIXED_SINE_TEST", start)
        init_common = text[start:end]
        ordered_tokens = (
            "dma_claim_unused_channel(false)",
            "dma_claim_unused_timer(false)",
            "dma_channel_unclaim(static_cast<uint>(g_dma_channel))",
            "gpio_set_function(board::kAudioPwmLeft, GPIO_FUNC_PWM)",
        )
        positions = [init_common.index(token) for token in ordered_tokens]
        nonfatal_claims = (
            "dma_claim_unused_channel(true)" not in init_common
            and "dma_claim_unused_timer(true)" not in init_common
        )
        required = (
            "audio=init error=dma_channel_unavailable",
            "audio=init error=dma_timer_unavailable",
            "g_dma_channel = -1;",
            "return false;",
        )
        missing = [token for token in required if token not in init_common]
        add_check(
            checks,
            "source-fingerprint:audio-resource-claim-fail-safe",
            positions == sorted(positions) and nonfatal_claims and not missing,
            path=relative_path,
            claim_before_gpio=positions == sorted(positions),
            nonfatal_claims=nonfatal_claims,
            missing=missing,
        )
    except (OSError, UnicodeError, ValueError) as error:
        add_check(
            checks,
            "source-fingerprint:audio-resource-claim-fail-safe",
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

    quality_schema_path = directory / "project-quality-contract.schema.json"
    audio_analysis_schema_path = directory / "audio-analysis.schema.json"
    generic_audio_analysis_schema_path = directory / "audio-analysis-v2.schema.json"
    try:
        quality_schema = load_json(quality_schema_path)
        audio_analysis_schema = load_json(audio_analysis_schema_path)
        generic_audio_analysis_schema = load_json(generic_audio_analysis_schema_path)
        required = quality_schema.get("required", [])
        properties = quality_schema.get("properties", {})
        audio = (
            properties.get("required_capabilities", {})
            .get("properties", {})
            .get("audio_sink", {})
        )
        tool_source = (root / "tools/picocalc.py").read_text(encoding="utf-8")
        quality_errors = []
        if quality_schema.get("additionalProperties") is not False:
            quality_errors.append("schema must reject unknown top-level fields")
        if set(required) != {
            "schema_version",
            "contract_id",
            "report_schema",
            "required_capabilities",
            "report_checks",
        }:
            quality_errors.append("schema required fields are incomplete")
        if set(audio.get("required", [])) != {"expected_count", "expected_sha256"}:
            quality_errors.append("audio_sink oracle must require count and SHA-256")
        definitions = quality_schema.get("$defs", {})
        quality_v2 = definitions.get("qualityV2", {})
        quality_v3 = definitions.get("qualityV3", {})
        if set(quality_v2.get("required", [])) != {
            "minimum_max_window_rms",
            "maximum_rail_sample_ratio_ppm",
            "maximum_consecutive_rail_frames",
        }:
            quality_errors.append("schema 2 audio quality bounds are incomplete")
        if set(quality_v3.get("required", [])) != {
            "advisory_minimum_max_window_rms",
            "maximum_rail_sample_ratio_ppm",
            "maximum_consecutive_rail_frames",
        }:
            quality_errors.append("schema 3 audio quality bounds are incomplete")
        if audio_analysis_schema.get("additionalProperties") is not False:
            quality_errors.append("audio analysis schema must reject unknown fields")
        if generic_audio_analysis_schema.get("additionalProperties") is not False:
            quality_errors.append("generic audio analysis schema must reject unknown fields")
        if generic_audio_analysis_schema.get("properties", {}).get("schema_version") != {
            "const": 2
        }:
            quality_errors.append("generic audio analysis schema must be version 2")
        if generic_audio_analysis_schema.get("properties", {}).get("sample_rate_hz") != {
            "type": "integer",
            "minimum": 0,
        }:
            quality_errors.append("generic audio analysis schema must allow observed rates")
        analysis_required = set(audio_analysis_schema.get("required", []))
        for field in (
            "pcm_sha256",
            "max_window_rms",
            "rail_sample_ratio_ppm",
            "max_consecutive_rail_frames",
        ):
            if field not in analysis_required:
                quality_errors.append("audio analysis schema is missing {}".format(field))
        for token in (
            '"evaluation_status": evaluation_status',
            '"observation_status": observation_status',
            '"oracle_present": oracle_present',
            '"audio_sink_oracle_missing_or_mismatched"',
            '"audio_level_too_low"',
            '"audio_level_below_preferred_range"',
            '"audio_rail_ratio_excessive"',
            '"audio_sustained_rail_excessive"',
        ):
            if token not in tool_source:
                quality_errors.append("judge-report is missing {}".format(token))
        add_check(
            checks,
            "firmware-validation:project-quality-contract",
            not quality_errors,
            errors=quality_errors,
            schema=str(quality_schema_path.relative_to(root)),
            analysis_schema=str(audio_analysis_schema_path.relative_to(root)),
            generic_analysis_schema=str(generic_audio_analysis_schema_path.relative_to(root)),
        )
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        add_check(
            checks,
            "firmware-validation:project-quality-contract",
            False,
            **error_details(error),
        )

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
        "tools/judge_speaker_listening.py",
        "speaker-listening-human-verdict",
        [
            '"acceptable_quiet"',
            '"percussion_and_transients"',
            '"preserve_overall_reduce_percussion_or_transients"',
            '"adjust_from_accepted_safe_reference"',
            '"physical_volume") != "maximum"',
        ],
    )
    require_text(
        checks,
        root,
        "firmware-validation/speaker-listening-assessment.schema.json",
        "speaker-listening-assessment-schema",
        [
            '"physical_volume": {"const": "maximum"}',
            '"acceptable_quiet"',
            '"percussion_and_transients"',
            '"source_mix_comparison"',
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
            "g_initialized = picoment::audio_pwm::init_stream();",
            "g_initialized = picoment::audio_pwm::init_fixed_sine();",
            "picoment::audio_pwm::start_stream();",
            "picoment::audio_pwm::stop_stream();",
            "picoment::audio_pwm::write_sample(",
        ],
    )
    require_text(
        checks,
        root,
        "tools/analyze_speaker_calibration.py",
        "speaker-calibration-video-analyzer",
        [
            "def verify_plan(",
            "def sync_scores(",
            "def linear_fit(",
            "speaker_output_below_recording_noise",
            'speaker calibration: cannot_judge:',
            "def status_exit_code(",
            '"sha256": sha256_file(video)',
            'write_mono_wav(review_dir / f"{item[\'id\']}.wav",',
        ],
    )
    require_text(
        checks,
        root,
        "docs/SPEAKER_CALIBRATION.md",
        "speaker-calibration-responsibility-boundary",
        [
            "amp/speaker/筐体",
            "versioned hardware evidence",
            "cannot_judge",
            "analyze_speaker_calibration.py",
        ],
    )
    require_text(
        checks,
        root,
        "docs/SPEAKER_LISTENING_ACCEPTANCE.md",
        "speaker-listening-acceptance-policy",
        [
            "acceptable_quiet",
            "percussion_and_transients",
            "音量の最大化は合格条件ではありません",
            "v0.1.1",
            "v0.1.2",
            "judge_speaker_listening.py",
        ],
    )
    verify_bsp_provenance_contract(checks, root)
    verify_audio_resource_claim_fail_safe(checks, root)
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
    verify_rp2040_cpu_application_records(checks, root)


def _is_sha256_text(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _is_git_commit_text(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value))


def _verify_rp2040_cpu_schema_document(
    schema: object, schema_id: str, path: Path
) -> List[str]:
    problems: List[str] = []
    if not isinstance(schema, dict):
        return ["{} is not a JSON object".format(path)]
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        problems.append("{} is not draft 2020-12".format(path))
    if schema.get("type") != "object":
        problems.append("{} root type is not object".format(path))
    if schema.get("additionalProperties") is not False:
        problems.append("{} must be closed (additionalProperties=false)".format(path))
    required = schema.get("required")
    if not isinstance(required, list) or "schema_id" not in required or "schema_version" not in required:
        problems.append("{} must require schema_id and schema_version".format(path))
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        problems.append("{} properties is missing".format(path))
        return problems
    schema_id_property = properties.get("schema_id")
    if not isinstance(schema_id_property, dict) or schema_id_property.get("const") != schema_id:
        problems.append("{} schema_id const mismatch".format(path))
    schema_version_property = properties.get("schema_version")
    if not isinstance(schema_version_property, dict) or schema_version_property.get("const") != 1:
        problems.append("{} schema_version const mismatch".format(path))
    return problems


def _record_path_within(root: Path, value: object) -> Optional[Path]:
    if not isinstance(value, str) or not value:
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _rp2040_guest_observation_projection(report: object) -> Dict[str, Any]:
    """Return the projection used by the RP2040 CPU candidate runner.

    Backend identity is deliberately excluded because candidate and
    registered reports use different backend commits.  The two audio oracle
    expectation fields are harness inputs echoed into schema-8 reports, not
    guest observations; measured audio fields remain part of the projection.
    Keep this definition in lockstep with
    ``benchmark_rp2040_cpu_candidate.guest_observation_projection`` so the
    environment verifier validates the artifacts the runner actually writes.
    """
    if not isinstance(report, dict):
        return {}
    projection: Dict[str, Any] = {
        key: value
        for key, value in report.items()
        if key not in {"backend_build", "backend_commit"}
    }
    audio_sink = projection.get("audio_sink")
    if isinstance(audio_sink, dict):
        projection["audio_sink"] = {
            key: value
            for key, value in audio_sink.items()
            if key not in {"expected_count", "expected_sha256"}
        }
    return projection


def _expected_rp2040_cpu_schedule(workload_ids: List[str]) -> Dict[str, Dict[str, object]]:
    expected: Dict[str, Dict[str, object]] = {}
    run_number = 1
    for pair in range(1, 11):
        order = "AB" if pair % 2 else "BA"
        selected = workload_ids if pair % 2 else list(reversed(workload_ids))
        roles = ("baseline", "candidate") if order == "AB" else ("candidate", "baseline")
        for workload in selected:
            for role in roles:
                expected["run-{:03d}".format(run_number)] = {
                    "pair": pair, "order": order, "workload": workload, "role": role,
                }
                run_number += 1
    return expected


def _verify_rp2040_cpu_artifact_shape(
    path: Path, expected_schema_id: str, problems: List[str], validators: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    try:
        value = load_json(path)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        problems.append("{} is unreadable: {}".format(path, error))
        return None
    if not isinstance(value, dict):
        problems.append("{} is not an object".format(path))
        return None
    if value.get("schema_id") != expected_schema_id:
        problems.append("{} schema_id mismatch".format(path))
    if value.get("schema_version") != 1:
        problems.append("{} schema_version mismatch".format(path))
    if validators and expected_schema_id in validators:
        for error in validators[expected_schema_id].iter_errors(value):
            location = ".".join(str(part) for part in error.path)
            suffix = " at {}".format(location) if location else ""
            problems.append("{} schema validation failed{}: {}".format(path, suffix, error.message))
    required = {
            "picocalc.rp2040-cpu-profile": {
                "schema_id", "schema_version", "record_id", "candidate_id",
                "workload", "backend", "runner", "cpu", "interval", "cores",
                "overflowed", "profile_valid", "counters", "invariants", "feature_set",
        },
        "picocalc.rp2040-cpu-profile-comparison": {
            "schema_id", "schema_version", "candidate_id", "baseline_record", "candidate_record",
            "baseline_backend_commit", "candidate_backend_commit", "profile_runtime_parent",
            "profile_only_delta", "delta_files", "runtime_semantics_changed", "correctness_record",
            "profile_wall_time_is_acceptance_evidence", "method", "workloads", "combined", "decision",
        },
        "picocalc.rp2040-cpu-ab": {
            "schema_id", "schema_version", "record_id", "candidate_id", "artifact_type",
        },
        "picocalc.rp2040-cpu-decision": {
            "schema_id", "schema_version", "record_id", "candidate_id", "decision_kind", "status",
            "workloads", "backend_identities", "feature_set",
        },
    }[expected_schema_id]
    missing = sorted(field for field in required if field not in value)
    if missing:
        problems.append("{} is missing required fields: {}".format(path, ", ".join(missing)))
    if expected_schema_id == "picocalc.rp2040-cpu-ab":
        artifact_type = value.get("artifact_type")
        if artifact_type not in ("run", "summary", "correctness"):
            problems.append("{} has invalid artifact_type".format(path))
        elif artifact_type == "run":
            run_required = {
                "run_id", "workload", "pair", "order", "role", "backend_commit", "runner_sha256",
                "build_provenance_sha256",
                "cycles", "stop_reason", "elapsed_us", "wall_ns", "wall_seconds",
                "emulated_cycles_per_wall_second", "report_sha256", "guest_observation_sha256",
                "host_usage_delta",
            }
            missing_run = sorted(field for field in run_required if field not in value)
            if missing_run:
                problems.append("{} is missing run fields: {}".format(path, ", ".join(missing_run)))
        elif artifact_type == "summary":
            summary_required = {"pairs", "measured_runs", "workloads", "combined", "pair_results"}
            missing_summary = sorted(field for field in summary_required if field not in value)
            if missing_summary:
                problems.append("{} is missing summary fields: {}".format(path, ", ".join(missing_summary)))
        elif artifact_type == "correctness":
            correctness_required = {
                "workload", "trace_required", "baseline", "candidate",
                "baseline_guest_observation_sha256", "candidate_guest_observation_sha256",
                "guest_observation_equal", "behavior_equal",
            }
            missing_correctness = sorted(field for field in correctness_required if field not in value)
            if missing_correctness:
                problems.append("{} is missing correctness fields: {}".format(path, ", ".join(missing_correctness)))
    if expected_schema_id == "picocalc.rp2040-cpu-profile":
        if not isinstance(value.get("interval"), dict):
            problems.append("{} profile interval is missing or invalid".format(path))
        if not isinstance(value.get("cores"), list) or not value.get("cores"):
            problems.append("{} profile cores are missing or empty".format(path))
        if not isinstance(value.get("overflowed"), bool):
            problems.append("{} profile overflowed is not boolean".format(path))
        if not isinstance(value.get("profile_valid"), bool):
            problems.append("{} profile_valid is not boolean".format(path))
        if not isinstance(value.get("feature_set"), list) or not value.get("feature_set"):
            problems.append("{} profile feature_set is missing or empty".format(path))
        if value.get("profile_valid") is not True:
            problems.append("{} profile_valid is not true".format(path))
        if value.get("overflowed") is not False:
            problems.append("{} profile overflowed".format(path))
        invariants = value.get("invariants")
        if not isinstance(invariants, dict) or invariants.get("valid") is not True:
            problems.append("{} profile invariants are invalid".format(path))
    if expected_schema_id == "picocalc.rp2040-cpu-decision":
        decision_kind = value.get("decision_kind")
        if decision_kind not in {"admission", "correctness", "performance", "profile", "null-control", "invalid"}:
            problems.append("{} decision_kind is invalid".format(path))
        elif decision_kind == "invalid" and not isinstance(value.get("reasons"), list):
            problems.append("{} invalid decision has no reasons".format(path))
        elif decision_kind in {"performance", "null-control"} and (
            not isinstance(value.get("statistics"), dict)
            or not isinstance(value.get("correctness"), dict)
        ):
            problems.append("{} performance decision is missing statistics/correctness".format(path))
        elif decision_kind == "admission" and (
            not isinstance(value.get("evidence"), list)
            or not isinstance(value.get("correctness"), dict)
        ):
            problems.append("{} admission decision is missing evidence/correctness".format(path))
        elif decision_kind in {"correctness", "profile"} and not isinstance(value.get("correctness"), dict):
            problems.append("{} decision is missing correctness".format(path))
    return value


def _profile_counter(profile: Mapping[str, Any], *path: str) -> Optional[int]:
    value: Any = profile
    for component in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(component)
    return value if type(value) is int and value >= 0 else None


def _verify_pending_exception_poll_equation(
    profile_path: Path, profile: Mapping[str, Any], problems: List[str]
) -> None:
    """Require P2-A aggregate/core exception counter conservation."""
    counters = profile.get("counters")
    scopes: List[Tuple[str, Any]] = [("aggregate", counters)]
    cores = profile.get("cores")
    if not isinstance(cores, list):
        problems.append("{} P2-A profile cores are invalid".format(profile_path))
    else:
        scopes.extend(("core-{}".format(index), core) for index, core in enumerate(cores))
    for scope, source in scopes:
        exception = source.get("exception") if isinstance(source, Mapping) else None
        if not isinstance(exception, Mapping):
            problems.append("{} P2-A profile {} exception counters are missing".format(profile_path, scope))
            continue
        values = {}
        for field in ("polls", "reject_no_candidate", "reject_primask", "reject_active_handler", "entries"):
            value = exception.get(field)
            if type(value) is not int or value < 0:
                problems.append("{} P2-A profile {} exception {} is invalid".format(profile_path, scope, field))
            else:
                values[field] = value
        exception_source = exception.get("source")
        source_values = {}
        if not isinstance(exception_source, Mapping):
            problems.append("{} P2-A profile {} exception source is missing".format(profile_path, scope))
        else:
            for field in ("pendsv", "systick", "nvic"):
                value = exception_source.get(field)
                if type(value) is not int or value < 0:
                    problems.append("{} P2-A profile {} exception source {} is invalid".format(profile_path, scope, field))
                else:
                    source_values[field] = value
        if len(values) == 5 and values["polls"] != sum(
            values[field]
            for field in ("reject_no_candidate", "reject_primask", "reject_active_handler", "entries")
        ):
            problems.append(
                "{} P2-A profile {} exception polls != reject_no_candidate + reject_primask + reject_active_handler + entries".format(
                    profile_path, scope
                )
            )
        if len(source_values) == 3 and "entries" in values and values["entries"] != sum(source_values.values()):
            problems.append(
                "{} P2-A profile {} exception entries != source.pendsv + source.systick + source.nvic".format(
                    profile_path, scope
                )
            )
    invariants = profile.get("invariants")
    if (
        not isinstance(invariants, Mapping)
        or invariants.get("exception_poll_conservation") is not True
        or invariants.get("exception_source_conservation") is not True
    ):
        problems.append("{} P2-A profile exception invariants are invalid".format(profile_path))


def _profile_ratio_matches(actual: object, numerator: int, denominator: int) -> bool:
    if denominator <= 0 or not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return False
    return math.isclose(float(actual), numerator / denominator, rel_tol=1e-12, abs_tol=1e-15)


def _effect_summary_matches(recorded: object, log_ratios: List[float]) -> bool:
    """Recompute the fixed log-ratio summary used by CPU A/B records."""
    if not isinstance(recorded, Mapping) or not log_ratios:
        return False
    count = len(log_ratios)
    mean = statistics.mean(log_ratios)
    effects = [math.exp(value) - 1.0 for value in log_ratios]
    ordered = sorted(effects)
    midpoint = count // 2
    lower = ordered[:midpoint]
    upper = ordered[-midpoint:] if midpoint else ordered
    expected = {
        "n": count,
        "mean_log_ratio": mean,
        "geometric_mean_effect": math.exp(mean) - 1.0,
        "percent_effect": {
            "median": statistics.median(ordered),
            "q1": statistics.median(lower) if lower else ordered[0],
            "q3": statistics.median(upper) if upper else ordered[-1],
            "iqr": (
                (statistics.median(upper) if upper else ordered[-1])
                - (statistics.median(lower) if lower else ordered[0])
            ),
        },
    }
    for field in ("mean_log_ratio", "geometric_mean_effect"):
        value = recorded.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isclose(float(value), expected[field], rel_tol=1e-12, abs_tol=1e-15)
        ):
            return False
    if recorded.get("n") != count:
        return False
    percent = recorded.get("percent_effect")
    if not isinstance(percent, Mapping):
        return False
    for field, value in expected["percent_effect"].items():
        actual = percent.get(field)
        if (
            not isinstance(actual, (int, float))
            or isinstance(actual, bool)
            or not math.isclose(float(actual), value, rel_tol=1e-12, abs_tol=1e-15)
        ):
            return False
    if count > 1:
        deviation = statistics.stdev(log_ratios)
        critical = {10: 2.262157, 20: 2.093}.get(count, 1.96)
        half_width = critical * deviation / math.sqrt(count)
        expected_ci_log = [mean - half_width, mean + half_width]
        expected_ci_effect = [math.exp(value) - 1.0 for value in expected_ci_log]
        for field, values in (
            ("ci95_log_ratio", expected_ci_log),
            ("ci95_effect", expected_ci_effect),
        ):
            actual = recorded.get(field)
            if (
                not isinstance(actual, list)
                or len(actual) != 2
                or any(
                    not isinstance(item, (int, float))
                    or isinstance(item, bool)
                    or not math.isclose(float(item), expected, rel_tol=1e-12, abs_tol=1e-15)
                    for item, expected in zip(actual, values)
                )
            ):
                return False
        sample_sd = recorded.get("sample_sd_log_ratio")
        if (
            not isinstance(sample_sd, (int, float))
            or isinstance(sample_sd, bool)
            or not math.isclose(float(sample_sd), deviation, rel_tol=1e-12, abs_tol=1e-15)
        ):
            return False
    return True


def _verify_rp2040_cpu_profile_comparison(
    comparison_path: Path,
    comparison: Mapping[str, Any],
    record_dir: Path,
    records_root: Path,
    manifest: Mapping[str, Any],
    candidate_profiles: Mapping[str, Tuple[Path, Mapping[str, Any]]],
    schema_validators: Optional[Dict[str, Any]],
    problems: List[str],
) -> None:
    """Validate the derived profile comparison against both profile records.

    The JSON schema closes the shape; this check closes the references and the
    arithmetic so a hand-edited summary cannot silently become a performance
    input.  Profile comparisons remain diagnostic and never become wall-time
    acceptance evidence here.
    """
    if comparison.get("candidate_record") != record_dir.name:
        problems.append("{} candidate_record differs from containing record".format(comparison_path))
    if comparison.get("candidate_id") != manifest.get("candidate_id"):
        problems.append("{} candidate_id differs from manifest".format(comparison_path))
    if comparison.get("profile_wall_time_is_acceptance_evidence") is not False:
        problems.append("{} profile comparison is marked as wall-time evidence".format(comparison_path))
    identities = manifest.get("backend_identities")
    candidate_identity = identities.get("candidate_profile") if isinstance(identities, Mapping) else None
    if isinstance(candidate_identity, Mapping):
        if comparison.get("candidate_backend_commit") != candidate_identity.get("commit"):
            problems.append("{} candidate backend commit differs from manifest".format(comparison_path))
    baseline_record_name = comparison.get("baseline_record")
    baseline_record = _record_path_within(records_root, baseline_record_name)
    if baseline_record is None or baseline_record.parent != records_root.resolve() or not baseline_record.is_dir():
        problems.append("{} baseline_record is not a direct existing record".format(comparison_path))
        baseline_record = None
    baseline_profiles: Dict[str, Tuple[Path, Mapping[str, Any]]] = {}
    if baseline_record is not None:
        baseline_manifest_path = baseline_record / "manifest.json"
        try:
            baseline_manifest = load_json(baseline_manifest_path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            problems.append("{} baseline manifest is unreadable: {}".format(comparison_path, error))
            baseline_manifest = None
        if isinstance(baseline_manifest, Mapping):
            baseline_identity = baseline_manifest.get("backend_identities", {})
            baseline_profile_identity = (
                baseline_identity.get("candidate_profile")
                if isinstance(baseline_identity, Mapping)
                else None
            )
            if isinstance(baseline_profile_identity, Mapping) and (
                comparison.get("baseline_backend_commit") != baseline_profile_identity.get("commit")
            ):
                problems.append("{} baseline backend commit differs from referenced record".format(comparison_path))
        baseline_profile_dir = baseline_record / "profile"
        for profile_path in sorted(baseline_profile_dir.glob("*.json")) if baseline_profile_dir.is_dir() else []:
            if profile_path.name.endswith("-measurement.json"):
                continue
            profile = _verify_rp2040_cpu_artifact_shape(
                profile_path, "picocalc.rp2040-cpu-profile", problems, schema_validators
            )
            workload = profile.get("workload") if isinstance(profile, Mapping) else None
            workload_id = workload.get("id") if isinstance(workload, Mapping) else None
            if isinstance(workload_id, str):
                if workload_id in baseline_profiles:
                    problems.append("{} contains duplicate baseline profile workload {}".format(comparison_path, workload_id))
                else:
                    baseline_profiles[workload_id] = (profile_path, profile)

    comparison_workloads = comparison.get("workloads")
    expected_workload_ids = {"picotetris-opt1b-vrp5", "picoedit-r1-vrp2f"}
    if not isinstance(comparison_workloads, Mapping) or set(comparison_workloads) != expected_workload_ids:
        problems.append("{} workload keys do not match the fixed profile pair".format(comparison_path))
        return

    def require_counter(profile: Mapping[str, Any], label: str, *path: str) -> Optional[int]:
        value = _profile_counter(profile, *path)
        if value is None:
            problems.append("{} {} is missing or invalid".format(comparison_path, label))
        return value

    derived: Dict[str, Dict[str, int]] = {}
    for workload_id in sorted(expected_workload_ids):
        summary = comparison_workloads.get(workload_id)
        if not isinstance(summary, Mapping):
            problems.append("{} workload {} comparison is missing".format(comparison_path, workload_id))
            continue
        baseline_entry = baseline_profiles.get(workload_id)
        candidate_entry = candidate_profiles.get(workload_id)
        if baseline_entry is None or candidate_entry is None:
            problems.append("{} workload {} baseline/candidate profile is missing".format(comparison_path, workload_id))
            continue
        baseline_path, baseline_profile = baseline_entry
        candidate_path, candidate_profile = candidate_entry
        baseline_digest = sha256(baseline_path)
        candidate_digest = sha256(candidate_path)
        if summary.get("baseline_profile_sha256") != baseline_digest:
            problems.append("{} workload {} baseline profile SHA-256 differs".format(comparison_path, workload_id))
        if summary.get("candidate_profile_sha256") != candidate_digest:
            problems.append("{} workload {} candidate profile SHA-256 differs".format(comparison_path, workload_id))
        for profile_label, profile in (("baseline", baseline_profile), ("candidate", candidate_profile)):
            profile_workload = profile.get("workload") if isinstance(profile, Mapping) else None
            if not isinstance(profile_workload, Mapping) or profile_workload.get("id") != workload_id:
                problems.append("{} workload {} {} profile identity differs".format(comparison_path, workload_id, profile_label))
        baseline_misses = require_counter(baseline_profile, workload_id + " baseline decode misses", "counters", "decode", "misses")
        candidate_misses = require_counter(candidate_profile, workload_id + " candidate decode misses", "counters", "decode", "misses")
        retired = require_counter(candidate_profile, workload_id + " retired instructions", "counters", "retired_instructions")
        cycles = require_counter(candidate_profile, workload_id + " emulated cycles", "counters", "emulated_cycles")
        requests = require_counter(candidate_profile, workload_id + " invalidation requests", "counters", "invalidation", "requests")
        examined = require_counter(candidate_profile, workload_id + " examined slots", "counters", "invalidation", "examined_slots")
        unrelated = require_counter(candidate_profile, workload_id + " unrelated clears", "counters", "invalidation", "unrelated_would_clear")
        matching = require_counter(candidate_profile, workload_id + " matching clears", "counters", "invalidation", "matching_clears")
        wide = require_counter(candidate_profile, workload_id + " wide predecessor clears", "counters", "invalidation", "wide_predecessor_clears")
        if None in (baseline_misses, candidate_misses, retired, cycles, requests, examined, unrelated, matching, wide):
            continue
        assert baseline_misses is not None and candidate_misses is not None
        assert retired is not None and cycles is not None and requests is not None and examined is not None
        assert unrelated is not None and matching is not None and wide is not None
        expected_reduction = baseline_misses - candidate_misses
        expected_values = {
            "retired_instructions": retired,
            "emulated_cycles": cycles,
            "invalidation_requests": requests,
            "examined_slots": examined,
            "baseline_decode_misses": baseline_misses,
            "candidate_decode_misses": candidate_misses,
            "decode_miss_reduction": expected_reduction,
            "candidate_unrelated_would_clear": unrelated,
            "candidate_matching_clears": matching,
            "candidate_wide_predecessor_clears": wide,
        }
        for field, expected in expected_values.items():
            if summary.get(field) != expected:
                problems.append("{} workload {} {} differs from profile counters".format(comparison_path, workload_id, field))
        if not _profile_ratio_matches(summary.get("decode_miss_reduction_ratio"), expected_reduction, baseline_misses):
            problems.append("{} workload {} decode miss ratio is not derived from counters".format(comparison_path, workload_id))
        if not _profile_ratio_matches(summary.get("candidate_unrelated_would_clear_ratio"), unrelated, examined):
            problems.append("{} workload {} unrelated ratio is not derived from counters".format(comparison_path, workload_id))
        if summary.get("profile_valid") is not True or summary.get("core1_active") is not False:
            problems.append("{} workload {} profile validity/core1 state is invalid".format(comparison_path, workload_id))
        derived[workload_id] = {
            "baseline_decode_misses": baseline_misses,
            "candidate_decode_misses": candidate_misses,
            "decode_miss_reduction": expected_reduction,
            "candidate_unrelated_would_clear": unrelated,
            "candidate_examined_slots": examined,
            "candidate_invalidation_requests": requests,
        }

    combined = comparison.get("combined")
    if not isinstance(combined, Mapping) or set(derived) != expected_workload_ids:
        return
    combined_expected = {
        "baseline_decode_misses": sum(item["baseline_decode_misses"] for item in derived.values()),
        "candidate_decode_misses": sum(item["candidate_decode_misses"] for item in derived.values()),
        "decode_miss_reduction": sum(item["decode_miss_reduction"] for item in derived.values()),
        "candidate_unrelated_would_clear": sum(item["candidate_unrelated_would_clear"] for item in derived.values()),
        "candidate_examined_slots": sum(item["candidate_examined_slots"] for item in derived.values()),
        "candidate_invalidation_requests": sum(item["candidate_invalidation_requests"] for item in derived.values()),
    }
    for field, expected in combined_expected.items():
        if combined.get(field) != expected:
            problems.append("{} combined {} differs from workload sums".format(comparison_path, field))
    if not _profile_ratio_matches(
        combined.get("decode_miss_reduction_ratio"),
        combined_expected["decode_miss_reduction"],
        combined_expected["baseline_decode_misses"],
    ):
        problems.append("{} combined decode miss ratio is not derived from counters".format(comparison_path))
    if not _profile_ratio_matches(
        combined.get("candidate_unrelated_would_clear_ratio"),
        combined_expected["candidate_unrelated_would_clear"],
        combined_expected["candidate_examined_slots"],
    ):
        problems.append("{} combined unrelated ratio is not derived from counters".format(comparison_path))

    correctness_record_name = comparison.get("correctness_record")
    correctness_record = _record_path_within(records_root, correctness_record_name)
    if correctness_record is None or correctness_record.parent != records_root.resolve() or not correctness_record.is_dir():
        problems.append("{} correctness_record is not a direct existing record".format(comparison_path))
    else:
        try:
            correctness_manifest = load_json(correctness_record / "manifest.json")
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            problems.append("{} correctness manifest is unreadable: {}".format(comparison_path, error))
        else:
            correctness_identities = correctness_manifest.get("backend_identities", {})
            correctness_candidate = (
                correctness_identities.get("candidate_production")
                if isinstance(correctness_identities, Mapping)
                else None
            )
            if isinstance(correctness_candidate, Mapping) and (
                comparison.get("profile_runtime_parent") != correctness_candidate.get("commit")
            ):
                problems.append("{} profile_runtime_parent differs from correctness candidate".format(comparison_path))
    if comparison.get("profile_only_delta") != comparison.get("candidate_backend_commit"):
        problems.append("{} profile_only_delta must identify the profiled candidate commit".format(comparison_path))


def _verify_interleaved_anchor_summary(
    record_dir: Path,
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    run_by_id: Mapping[str, Mapping[str, Any]],
    problems: List[str],
) -> None:
    """Validate the fixed anchor layout and host-correction fields."""
    policy = manifest.get("measurement_policy")
    if not isinstance(policy, Mapping) or policy.get("calibration_method") != "interleaved-anchor-v1":
        return
    calibration = summary.get("calibration")
    if not isinstance(calibration, Mapping):
        problems.append("{} interleaved-anchor calibration is missing".format(record_dir))
        return
    # A protocol exception may be recorded before all anchors/runs exist.  Keep
    # that immutable failure record auditable without pretending that its
    # incomplete calibration is a valid measurement.
    if summary.get("status") == "invalid" and isinstance(calibration.get("error"), str):
        if calibration.get("valid") is not False:
            problems.append("{} failed interleaved-anchor calibration must be marked invalid".format(record_dir))
        return
    expected_ids = [
        "anchor-pre-001", "anchor-pre-002", "anchor-pre-003",
        "anchor-after-010", "anchor-after-020", "anchor-after-030",
        "anchor-post-001", "anchor-post-002", "anchor-post-003",
    ]
    if calibration.get("method") != "interleaved-anchor-v1":
        problems.append("{} calibration method is invalid".format(record_dir))
    if calibration.get("anchor_count") != len(expected_ids):
        problems.append("{} calibration anchor count is invalid".format(record_dir))
    anchors = calibration.get("anchors")
    if not isinstance(anchors, list) or [anchor.get("anchor_id") for anchor in anchors if isinstance(anchor, Mapping)] != expected_ids:
        problems.append("{} calibration anchor order is invalid".format(record_dir))
        return
    if calibration.get("anchor_run_ids") != expected_ids:
        problems.append("{} calibration anchor_run_ids differ from fixed policy".format(record_dir))
    expected_positions = [
        ("pre", 0), ("pre", 0), ("pre", 0),
        ("after-measured-run", 10), ("after-measured-run", 20), ("after-measured-run", 30),
        ("post", 40), ("post", 40), ("post", 40),
    ]
    expected_identity = manifest.get("backend_identities", {}).get("baseline_production", {})
    previous_elapsed = -1.0
    throughputs: List[float] = []
    for anchor, (expected_position, expected_run_index) in zip(anchors, expected_positions):
        if not isinstance(anchor, Mapping):
            problems.append("{} calibration anchor is not an object".format(record_dir))
            continue
        if anchor.get("position") != expected_position or anchor.get("after_measured_run") != expected_run_index:
            problems.append("{} calibration anchor position is invalid".format(record_dir))
        if anchor.get("workload") != "picotetris-opt1b-vrp5" or anchor.get("role") != "baseline":
            problems.append("{} calibration anchor workload/role is invalid".format(record_dir))
        elapsed = anchor.get("elapsed_seconds")
        throughput = anchor.get("throughput")
        if (
            not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not math.isfinite(float(elapsed))
            or float(elapsed) <= previous_elapsed
            or not isinstance(throughput, (int, float))
            or isinstance(throughput, bool)
            or not math.isfinite(float(throughput))
            or float(throughput) <= 0
        ):
            problems.append("{} calibration anchor timing/throughput is invalid".format(record_dir))
        else:
            previous_elapsed = float(elapsed)
            throughputs.append(float(throughput))
        for field in ("guest_observation_sha256", "runner_sha256", "build_provenance_sha256"):
            if not _is_sha256_text(anchor.get(field)):
                problems.append("{} calibration anchor {} is invalid".format(record_dir, field))
        if isinstance(expected_identity, Mapping):
            for field in ("backend_commit", "runner_sha256", "build_provenance_sha256"):
                expected_field = "commit" if field == "backend_commit" else field
                if anchor.get(field) != expected_identity.get(expected_field):
                    problems.append("{} calibration anchor {} differs from baseline identity".format(record_dir, field))
    model = calibration.get("anchor_model")
    reference: Optional[float] = None
    if not isinstance(model, Mapping):
        problems.append("{} calibration anchor model is missing".format(record_dir))
    else:
        if model.get("model") != "global-log-linear-v1":
            problems.append("{} calibration anchor model name is invalid".format(record_dir))
        max_residual = model.get("max_relative_residual")
        model_valid = model.get("valid")
        if (
            not isinstance(max_residual, (int, float))
            or isinstance(max_residual, bool)
            or not math.isfinite(float(max_residual))
            or model_valid is not (float(max_residual) <= 0.02)
        ):
            problems.append("{} calibration anchor residual gate is invalid".format(record_dir))
        reference = model.get("reference_throughput")
        if not isinstance(reference, (int, float)) or isinstance(reference, bool) or not math.isfinite(float(reference)) or float(reference) <= 0:
            problems.append("{} calibration reference throughput is invalid".format(record_dir))
            reference = None
    anchor_points: List[Tuple[float, float]] = []
    if len(throughputs) == len(expected_ids):
        anchor_points = [
            (float(anchor["elapsed_seconds"]), math.log(float(anchor["throughput"])))
            for anchor in anchors
            if isinstance(anchor, Mapping)
            and isinstance(anchor.get("elapsed_seconds"), (int, float))
            and isinstance(anchor.get("throughput"), (int, float))
            and not isinstance(anchor.get("elapsed_seconds"), bool)
            and not isinstance(anchor.get("throughput"), bool)
            and math.isfinite(float(anchor.get("elapsed_seconds")))
            and math.isfinite(float(anchor.get("throughput")))
            and float(anchor.get("throughput")) > 0
        ]
    if isinstance(model, Mapping) and len(anchor_points) == len(expected_ids):
        mean_x = statistics.mean(point[0] for point in anchor_points)
        mean_y = statistics.mean(point[1] for point in anchor_points)
        denominator = sum((x - mean_x) ** 2 for x, _ in anchor_points)
        if denominator > 0:
            expected_slope = sum((x - mean_x) * (y - mean_y) for x, y in anchor_points) / denominator
            expected_intercept = mean_y - expected_slope * mean_x
            expected_residuals = []
            for anchor, (x, y) in zip(anchors, anchor_points):
                predicted_log = expected_intercept + expected_slope * x
                expected_residuals.append(
                    {
                        "anchor_id": anchor.get("anchor_id"),
                        "observed_log_throughput": y,
                        "predicted_log_throughput": predicted_log,
                        "relative_residual": math.exp(abs(y - predicted_log)) - 1.0,
                    }
                )
            expected_max = max(item["relative_residual"] for item in expected_residuals)
            expected_rms = math.sqrt(
                statistics.mean(item["relative_residual"] ** 2 for item in expected_residuals)
            )
            expected_reference = math.exp(mean_y)
            for field, expected in (
                ("slope", expected_slope),
                ("intercept", expected_intercept),
                ("reference_throughput", expected_reference),
                ("max_relative_residual", expected_max),
                ("rms_relative_residual", expected_rms),
            ):
                actual = model.get(field)
                if (
                    not isinstance(actual, (int, float))
                    or isinstance(actual, bool)
                    or not math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-12)
                ):
                    problems.append("{} calibration anchor model {} is not derived from anchors".format(record_dir, field))
            recorded_residuals = model.get("residuals")
            if (
                not isinstance(recorded_residuals, list)
                or len(recorded_residuals) != len(expected_residuals)
            ):
                problems.append("{} calibration anchor residual list is invalid".format(record_dir))
            else:
                for recorded, expected in zip(recorded_residuals, expected_residuals):
                    if not isinstance(recorded, Mapping) or recorded.get("anchor_id") != expected["anchor_id"]:
                        problems.append("{} calibration anchor residual identity is invalid".format(record_dir))
                        continue
                    for field in ("observed_log_throughput", "predicted_log_throughput", "relative_residual"):
                        actual = recorded.get(field)
                        if (
                            not isinstance(actual, (int, float))
                            or isinstance(actual, bool)
                            or not math.isclose(float(actual), expected[field], rel_tol=1e-12, abs_tol=1e-12)
                        ):
                            problems.append("{} calibration anchor residual {} is not derived from anchors".format(record_dir, field))
        else:
            problems.append("{} calibration anchor model times are degenerate".format(record_dir))
    if calibration.get("pre_post_drift_gate_used") is not False:
        problems.append("{} pre/post drift was incorrectly used as the anchor gate".format(record_dir))
    affinity = calibration.get("cpu_affinity")
    measurement_cpu = manifest.get("measurement_cpu")
    if (
        not isinstance(affinity, Mapping)
        or affinity.get("requested") != measurement_cpu
        or affinity.get("effective_start") != [measurement_cpu]
        or affinity.get("effective_end") != [measurement_cpu]
    ):
        problems.append("{} calibration CPU affinity is invalid".format(record_dir))
    for snapshot_name in ("host_snapshot_start", "host_snapshot_end"):
        snapshot = calibration.get(snapshot_name)
        if not isinstance(snapshot, Mapping) or snapshot.get("allowed_cpus") != [measurement_cpu]:
            problems.append("{} calibration {} is invalid".format(record_dir, snapshot_name))
    if calibration.get("correctness_gate") != "pass":
        problems.append("{} calibration correctness gate is not passing".format(record_dir))
    if len(anchor_points) == len(expected_ids) and isinstance(model, Mapping) and isinstance(reference, (int, float)):
        for run_id, run in run_by_id.items():
            elapsed = run.get("protocol_elapsed_seconds")
            predicted = run.get("predicted_anchor_throughput")
            correction = run.get("host_speed_correction")
            corrected = run.get("corrected_emulated_cycles_per_wall_second")
            if (
                not isinstance(elapsed, (int, float))
                or isinstance(elapsed, bool)
                or not math.isfinite(float(elapsed))
                or float(elapsed) < anchor_points[0][0]
                or float(elapsed) > anchor_points[-1][0]
                or not isinstance(predicted, (int, float))
                or isinstance(predicted, bool)
                or not math.isfinite(float(predicted))
                or float(predicted) <= 0
                or not isinstance(correction, (int, float))
                or isinstance(correction, bool)
                or not math.isfinite(float(correction))
                or float(correction) <= 0
                or not isinstance(corrected, (int, float))
                or isinstance(corrected, bool)
                or not math.isfinite(float(corrected))
                or float(corrected) <= 0
            ):
                problems.append("{} run {} host correction fields are invalid".format(record_dir, run_id))
                continue
            for (left_x, left_y), (right_x, right_y) in zip(anchor_points, anchor_points[1:]):
                if float(elapsed) <= right_x:
                    fraction = (float(elapsed) - left_x) / (right_x - left_x)
                    expected_predicted = math.exp(left_y + fraction * (right_y - left_y))
                    break
            else:
                expected_predicted = math.exp(anchor_points[-1][1])
            if not math.isclose(float(predicted), expected_predicted, rel_tol=1e-12, abs_tol=1e-9):
                problems.append("{} run {} predicted anchor throughput is not interpolated".format(record_dir, run_id))
            expected_correction = float(reference) / expected_predicted
            if not math.isclose(float(correction), expected_correction, rel_tol=1e-12, abs_tol=1e-12):
                problems.append("{} run {} host correction is not derived from anchors".format(record_dir, run_id))
            raw_value = run.get("emulated_cycles_per_wall_second")
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool) and not math.isclose(
                float(corrected), float(raw_value) * float(correction), rel_tol=1e-12, abs_tol=1e-9
            ):
                problems.append("{} run {} corrected throughput is not derived from raw throughput".format(record_dir, run_id))
    sensitivity = calibration.get("pair_level_sensitivity")
    if (
        not isinstance(sensitivity, Mapping)
        or sensitivity.get("method") != "raw-vs-host-corrected-log-ratio-v1"
        or sensitivity.get("n") != 20
    ):
        problems.append("{} pair-level sensitivity is invalid".format(record_dir))
    else:
        deltas = []
        raw_values = []
        corrected_values = []
        for pair_result in summary.get("pair_results", []) if isinstance(summary.get("pair_results"), list) else []:
            raw = pair_result.get("pair_log_ratio") if isinstance(pair_result, Mapping) else None
            corrected = pair_result.get("corrected_pair_log_ratio") if isinstance(pair_result, Mapping) else None
            if (
                not isinstance(raw, (int, float))
                or isinstance(raw, bool)
                or not isinstance(corrected, (int, float))
                or isinstance(corrected, bool)
            ):
                continue
            raw_values.append(float(raw))
            corrected_values.append(float(corrected))
            deltas.append(float(corrected) - float(raw))
        if len(deltas) == 20:
            expected_sensitivity = {
                "mean_delta_log_ratio": statistics.mean(deltas),
                "max_abs_delta_log_ratio": max(abs(value) for value in deltas),
                "raw_combined_mean_log_ratio": statistics.mean(raw_values),
                "corrected_combined_mean_log_ratio": statistics.mean(corrected_values),
            }
            for field, expected in expected_sensitivity.items():
                actual = sensitivity.get(field)
                if (
                    not isinstance(actual, (int, float))
                    or isinstance(actual, bool)
                    or not math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-15)
                ):
                    problems.append("{} pair-level sensitivity {} is not derived from pair results".format(record_dir, field))

    pair_results = summary.get("pair_results")
    if isinstance(pair_results, list) and len(pair_results) == 20:
        manifest_workloads = manifest.get("workloads")
        workload_ids = [
            item.get("id") for item in manifest_workloads
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        ] if isinstance(manifest_workloads, list) else []
        if len(workload_ids) == 2:
            entries_by_workload = {
                workload_id: [
                    item for item in pair_results
                    if isinstance(item, Mapping) and item.get("workload") == workload_id
                ]
                for workload_id in workload_ids
            }
            for workload_id in workload_ids:
                entries = entries_by_workload[workload_id]
                raw_logs = [item.get("pair_log_ratio") for item in entries]
                corrected_logs = [item.get("corrected_pair_log_ratio") for item in entries]
                if (
                    len(entries) != 10
                    or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in raw_logs)
                    or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in corrected_logs)
                ):
                    problems.append("{} pair results are malformed for {}".format(record_dir, workload_id))
                    continue
                workload_summary = summary.get("workloads", {}).get(workload_id) if isinstance(summary.get("workloads"), Mapping) else None
                if not _effect_summary_matches(workload_summary, [float(value) for value in raw_logs]):
                    problems.append("{} workload effect summary is not derived for {}".format(record_dir, workload_id))
            by_pair = {
                pair: [
                    item for item in pair_results
                    if isinstance(item, Mapping) and item.get("pair_index") == pair
                ]
                for pair in range(1, 11)
            }
            if all(len(items) == len(workload_ids) for items in by_pair.values()):
                combined_logs = [
                    statistics.mean(float(item["pair_log_ratio"]) for item in by_pair[pair])
                    for pair in range(1, 11)
                ]
                if not _effect_summary_matches(summary.get("combined"), combined_logs):
                    problems.append("{} combined effect summary is not derived from pair results".format(record_dir))

            if manifest.get("candidate_id") == "P0-A2":
                null_control = summary.get("null_control")
                if not isinstance(null_control, Mapping):
                    problems.append("{} P0-A2 null-control summary is missing".format(record_dir))
                else:
                    if (
                        null_control.get("method") != "same-executable-null-v1"
                        or null_control.get("primary_mode") != "raw"
                        or null_control.get("workload_max_abs_effect") != 0.02
                        or null_control.get("combined_max_abs_effect") != 0.01
                    ):
                        problems.append("{} P0-A2 null-control policy is invalid".format(record_dir))
                    null_workloads = null_control.get("workloads")
                    null_combined = null_control.get("combined")
                    if not isinstance(null_workloads, Mapping) or set(null_workloads) != set(workload_ids):
                        problems.append("{} P0-A2 null-control workload set is invalid".format(record_dir))
                    else:
                        for workload_id in workload_ids:
                            entries = entries_by_workload[workload_id]
                            if len(entries) == 10:
                                raw_logs = [float(item["pair_log_ratio"]) for item in entries]
                                corrected_logs = [float(item["corrected_pair_log_ratio"]) for item in entries]
                                recorded_modes = null_workloads.get(workload_id)
                                if (
                                    not isinstance(recorded_modes, Mapping)
                                    or not _effect_summary_matches(recorded_modes.get("raw"), raw_logs)
                                    or not _effect_summary_matches(recorded_modes.get("host_corrected"), corrected_logs)
                                ):
                                    problems.append("{} P0-A2 null-control effects are not derived for {}".format(record_dir, workload_id))
                    if all(len(items) == len(workload_ids) for items in by_pair.values()) and isinstance(null_combined, Mapping):
                        combined_raw = [
                            statistics.mean(float(item["pair_log_ratio"]) for item in by_pair[pair])
                            for pair in range(1, 11)
                        ]
                        combined_corrected = [
                            statistics.mean(float(item["corrected_pair_log_ratio"]) for item in by_pair[pair])
                            for pair in range(1, 11)
                        ]
                        if (
                            not _effect_summary_matches(null_combined.get("raw"), combined_raw)
                            or not _effect_summary_matches(null_combined.get("host_corrected"), combined_corrected)
                        ):
                            problems.append("{} P0-A2 null-control combined effects are not derived".format(record_dir))
                    expected_checks = []
                    for workload_id in workload_ids:
                        entries = entries_by_workload[workload_id]
                        for mode, field in (("raw", "pair_log_ratio"), ("host_corrected", "corrected_pair_log_ratio")):
                            recorded_modes = null_workloads.get(workload_id)
                            values = [
                                float(item[field]) for item in entries
                                if isinstance(item.get(field), (int, float)) and not isinstance(item.get(field), bool)
                            ]
                            recorded_effect = (
                                recorded_modes.get(mode)
                                if isinstance(recorded_modes, Mapping)
                                else {}
                            )
                            recorded_effect_map = recorded_effect if isinstance(recorded_effect, Mapping) else {}
                            effect = (
                                len(values) == 10
                                and _effect_summary_matches(recorded_effect_map, values)
                            )
                            expected_checks.append(
                                {
                                    "scope": workload_id,
                                    "mode": mode,
                                    "max_abs_effect": 0.02,
                                    "absolute_effect_pass": effect and abs(float(recorded_effect_map.get("geometric_mean_effect", math.inf))) <= 0.02,
                                    "ci95_contains_zero": effect and isinstance(recorded_effect_map.get("ci95_effect"), list) and len(recorded_effect_map["ci95_effect"]) == 2 and float(recorded_effect_map["ci95_effect"][0]) <= 0 <= float(recorded_effect_map["ci95_effect"][1]),
                                }
                            )
                    for mode in ("raw", "host_corrected"):
                        recorded_effect = null_combined.get(mode) if isinstance(null_combined, Mapping) else {}
                        recorded_effect_map = recorded_effect if isinstance(recorded_effect, Mapping) else {}
                        effect_values = []
                        if all(len(items) == len(workload_ids) for items in by_pair.values()):
                            source_field = "pair_log_ratio" if mode == "raw" else "corrected_pair_log_ratio"
                            if all(
                                all(
                                    isinstance(item.get(source_field), (int, float))
                                    and not isinstance(item.get(source_field), bool)
                                    for item in by_pair[pair]
                                )
                                for pair in range(1, 11)
                            ):
                                effect_values = [
                                    statistics.mean(float(item[source_field]) for item in by_pair[pair])
                                    for pair in range(1, 11)
                                ]
                        effect = (
                            bool(effect_values)
                            and _effect_summary_matches(recorded_effect_map, effect_values)
                        )
                        expected_checks.append(
                            {
                                "scope": "combined",
                                "mode": mode,
                                "max_abs_effect": 0.01,
                                "absolute_effect_pass": effect and abs(float(recorded_effect_map.get("geometric_mean_effect", math.inf))) <= 0.01,
                                "ci95_contains_zero": effect and isinstance(recorded_effect_map.get("ci95_effect"), list) and len(recorded_effect_map["ci95_effect"]) == 2 and float(recorded_effect_map["ci95_effect"][0]) <= 0 <= float(recorded_effect_map["ci95_effect"][1]),
                            }
                        )
                    recorded_checks = null_control.get("checks")
                    if recorded_checks != expected_checks:
                        problems.append("{} P0-A2 null-control checks are not derived from effects".format(record_dir))
                    expected_pass = all(item["absolute_effect_pass"] and item["ci95_contains_zero"] for item in expected_checks)
                    if null_control.get("pass") is not expected_pass:
                        problems.append("{} P0-A2 null-control pass flag is invalid".format(record_dir))
                    expected_reasons = [
                        "{} {} effect/CI".format(item["scope"], item["mode"])
                        for item in expected_checks
                        if not item["absolute_effect_pass"] or not item["ci95_contains_zero"]
                    ]
                    if null_control.get("reasons") != expected_reasons:
                        problems.append("{} P0-A2 null-control reasons are not derived from checks".format(record_dir))


def _verify_rp2040_cpu_behavior_pair(
    baseline_path: Path, candidate_path: Path, comparison: Mapping[str, Any], problems: List[str],
    expected_commits: Optional[Mapping[str, str]] = None,
) -> None:
    artifacts = {}
    for role, path in (("baseline", baseline_path), ("candidate", candidate_path)):
        try:
            artifact = load_json(path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            problems.append("{} is unreadable: {}".format(path, error))
            continue
        if not isinstance(artifact, dict):
            problems.append("{} is not an object".format(path))
            continue
        if artifact.get("schema_version") != 1:
            problems.append("{} behavior schema_version is invalid".format(path))
        if artifact.get("normal_report_schema_version") != 8:
            problems.append("{} behavior report schema version is invalid".format(path))
        if artifact.get("mode") != "correctness_trace_on":
            problems.append("{} behavior mode is invalid".format(path))
        if artifact.get("valid_for_wall_time") is not False:
            problems.append("{} behavior artifact is marked valid for wall time".format(path))
        if artifact.get("behavior_projection_encoding") != "sorted-json-v1":
            problems.append("{} behavior projection encoding is invalid".format(path))
        backend = artifact.get("backend_build")
        projection = artifact.get("behavior_projection")
        digest = artifact.get("behavior_sha256")
        if not isinstance(backend, dict) or backend.get("dirty") is not False:
            problems.append("{} behavior backend is missing or dirty".format(path))
        elif not _is_git_commit_text(backend.get("commit")):
            problems.append("{} behavior backend commit is invalid".format(path))
        elif expected_commits and backend.get("commit") != expected_commits.get(role):
            problems.append("{} behavior backend commit differs from expected identity".format(path))
        if not isinstance(projection, dict) or not _is_sha256_text(digest):
            problems.append("{} behavior projection or digest is invalid".format(path))
        elif _canonical_json_sha256(projection) != digest:
            problems.append("{} behavior digest does not match projection".format(path))
        if isinstance(projection, dict):
            event_trace = projection.get("event_trace")
            if not isinstance(event_trace, dict):
                problems.append("{} behavior event trace is missing".format(path))
                domain_summary = []
                artifact["_verified_domain_summary"] = domain_summary
                artifacts[role] = artifact
                continue
            if event_trace.get("schema_version") != 2:
                problems.append("{} behavior event trace schema version is invalid".format(path))
            if event_trace.get("canonical_encoding") != "PICOEM-EVENT-v1":
                problems.append("{} behavior event trace encoding is invalid".format(path))
            if event_trace.get("streaming") is not True or event_trace.get("retains_event_array") is not False:
                problems.append("{} behavior event trace is not the streaming form".format(path))
            total_events = event_trace.get("total_events")
            if type(total_events) is not int or total_events < 0:
                problems.append("{} behavior event total is invalid".format(path))
            if not _is_sha256_text(event_trace.get("sha256")):
                problems.append("{} behavior event stream SHA-256 is invalid".format(path))
            domains = event_trace.get("domains") if isinstance(event_trace, dict) else None
            domain_summary = []
            if not isinstance(domains, list):
                problems.append("{} behavior domains are missing".format(path))
            else:
                names = set()
                domain_total = 0
                for domain in domains:
                    if (
                        not isinstance(domain, dict)
                        or not isinstance(domain.get("name"), str)
                        or type(domain.get("events")) is not int
                        or domain["events"] < 0
                        or not _is_sha256_text(domain.get("sha256"))
                    ):
                        problems.append("{} behavior domain is invalid".format(path))
                    else:
                        if domain["name"] in names:
                            problems.append("{} behavior domain names are duplicated".format(path))
                        names.add(domain["name"])
                        domain_total += domain["events"]
                        domain_summary.append(
                            {
                                "name": domain["name"],
                                "events": domain["events"],
                                "sha256": domain["sha256"],
                            }
                        )
                if type(total_events) is int and domain_total != total_events:
                    problems.append("{} behavior event total differs from domain totals".format(path))
        else:
            domain_summary = []
        artifact["_verified_domain_summary"] = domain_summary
        artifacts[role] = artifact
    if set(artifacts) != {"baseline", "candidate"}:
        return
    left = artifacts["baseline"].get("behavior_projection")
    right = artifacts["candidate"].get("behavior_projection")
    if left != right:
        problems.append("behavior projections differ for {}".format(comparison.get("workload")))
    recorded = comparison.get("behavior")
    if not isinstance(recorded, dict):
        problems.append("behavior summary is missing for {}".format(comparison.get("workload")))
        return
    for role, artifact in artifacts.items():
        projection = artifact.get("behavior_projection")
        digest = artifact.get("behavior_sha256")
        summary = recorded.get(role)
        expected_summary = {
            "behavior_sha256": digest,
            "projection": projection,
            "domain_summary": artifact.get("_verified_domain_summary", []),
        }
        if summary != expected_summary:
            problems.append("recorded behavior summary differs for {} {}".format(comparison.get("workload"), role))


def verify_rp2040_cpu_application_records(checks: List[Check], root: Path) -> None:
    """Verify the optional RP2040 CPU candidate schema and record namespace.

    No particular candidate phase is assumed.  Once a record exists, this
    check is intentionally fail-closed on
    identity, path escape, malformed JSON, and the phase-specific required
    artifacts.  It does not inspect the older VRP records because those have a
    different schema and acceptance contract.
    """
    base = root / "firmware-validation"
    schema_specs = (
        ("rp2040-cpu-build-provenance.schema.json", "picocalc.rp2040-build-provenance"),
        ("rp2040-cpu-profile.schema.json", "picocalc.rp2040-cpu-profile"),
        (
            "rp2040-cpu-profile-comparison.schema.json",
            "picocalc.rp2040-cpu-profile-comparison",
        ),
        ("rp2040-cpu-ab.schema.json", "picocalc.rp2040-cpu-ab"),
        ("rp2040-cpu-decision.schema.json", "picocalc.rp2040-cpu-decision"),
    )
    schema_problems: List[str] = []
    schema_validators: Dict[str, Any] = {}
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        # A schema-shaped manual checker is not an equivalent substitute for
        # the declared Draft 2020-12 contract.  The target-schema check must
        # fail closed when the validator dependency is unavailable.
        schema_problems.append(
            "python jsonschema package with Draft202012Validator is required: {}".format(error)
        )
        Draft202012Validator = None  # type: ignore[assignment,misc]
    for filename, schema_id in schema_specs:
        path = base / filename
        if not path.is_file():
            schema_problems.append("missing {}".format(path))
            continue
        try:
            schema = load_json(path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            schema_problems.append("{} is unreadable: {}".format(path, error))
            continue
        if Draft202012Validator is not None:
            try:
                Draft202012Validator.check_schema(schema)
                schema_validators[schema_id] = Draft202012Validator(schema)
            except Exception as error:
                schema_problems.append("{} schema is invalid: {}".format(path, error))
        schema_problems.extend(_verify_rp2040_cpu_schema_document(schema, schema_id, path))
    add_check(
        checks,
        "firmware-validation:rp2040-cpu-schemas",
        not schema_problems,
        errors=schema_problems,
    )

    records_root = base / "records"
    record_dirs = sorted(records_root.glob("rp2040-cpu-*")) if records_root.is_dir() else []
    linked_profile_names = set()
    for candidate_dir in record_dirs:
        candidate_manifest_path = candidate_dir / "manifest.json"
        try:
            candidate_manifest = load_json(candidate_manifest_path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            continue
        profile_name = (
            candidate_manifest.get("diagnostic_profile_record")
            if isinstance(candidate_manifest, Mapping)
            and candidate_manifest.get("candidate_id") == "P2-A"
            else None
        )
        if isinstance(profile_name, str) and profile_name.startswith("rp2040-cpu-") and Path(profile_name).name == profile_name:
            linked_profile_names.add(profile_name)
    problems: List[str] = []
    for record_dir in record_dirs:
        if not record_dir.is_dir():
            problems.append("{} is not a directory".format(record_dir))
            continue
        try:
            resolved_record_dir = record_dir.resolve()
            if resolved_record_dir.parent != records_root.resolve():
                problems.append("{} is not a direct record directory".format(record_dir))
        except OSError as error:
            problems.append("{} cannot be resolved: {}".format(record_dir, error))
        manifest_path = record_dir / "manifest.json"
        decision_path = record_dir / "decision.json"
        if not manifest_path.is_file():
            problems.append("{} is missing manifest.json".format(record_dir))
            continue
        try:
            manifest = load_json(manifest_path)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            problems.append("{} manifest is unreadable: {}".format(record_dir, error))
            continue
        if not isinstance(manifest, dict):
            problems.append("{} manifest is not an object".format(record_dir))
            continue
        if manifest.get("record_type") != "picocalc.rp2040-cpu-record":
            problems.append("{} manifest record_type is invalid".format(record_dir))
        if manifest.get("record_version") != 1:
            problems.append("{} manifest record_version is invalid".format(record_dir))
        if not isinstance(manifest.get("record_id"), str) or not manifest["record_id"]:
            problems.append("{} manifest record_id is missing".format(record_dir))
        elif manifest["record_id"] != record_dir.name:
            problems.append("{} manifest record_id differs from directory".format(record_dir))
        if not isinstance(manifest.get("feature_set", []), list) or not all(
            isinstance(feature, str) and feature for feature in manifest.get("feature_set", [])
        ):
            problems.append("{} manifest feature_set is invalid".format(record_dir))
        workloads = manifest.get("workloads")
        workload_ids: List[str] = []
        if not isinstance(workloads, list) or not workloads:
            problems.append("{} manifest workloads is empty".format(record_dir))
        else:
            for workload in workloads:
                if not isinstance(workload, dict):
                    problems.append("{} manifest workload is not an object".format(record_dir))
                    continue
                if not isinstance(workload.get("id"), str) or not workload["id"]:
                    problems.append("{} manifest workload id is missing".format(record_dir))
                else:
                    workload_ids.append(workload["id"])
                    try:
                        target = picocalc.load_firmware_target(workload["id"])
                    except (KeyError, OSError, TypeError, ValueError):
                        target = None
                    if not isinstance(target, dict) or target.get("status") != "active":
                        problems.append("{} manifest workload is not an active registered target".format(record_dir))
                    else:
                        artifacts = target.get("artifacts") if isinstance(target.get("artifacts"), dict) else {}
                        if workload.get("revision") != target.get("revision"):
                            problems.append("{} manifest workload revision differs from registry".format(record_dir))
                        if workload.get("firmware_sha256") != artifacts.get("bin_sha256"):
                            problems.append("{} manifest firmware SHA-256 differs from registry".format(record_dir))
                        expected_scenario_sha = (
                            target.get("scenario", {}).get("sha256")
                            if isinstance(target.get("scenario"), dict)
                            else None
                        )
                        if workload.get("scenario_sha256") != expected_scenario_sha:
                            problems.append("{} manifest scenario SHA-256 differs from registry".format(record_dir))
                        try:
                            expected_contract_sha = picocalc.firmware_target_contract_sha256(target)
                        except (KeyError, TypeError, ValueError):
                            expected_contract_sha = None
                        if workload.get("contract_sha256") != expected_contract_sha:
                            problems.append("{} manifest contract SHA-256 differs from registry".format(record_dir))
                if not _is_sha256_text(workload.get("firmware_sha256")):
                    problems.append("{} manifest firmware SHA-256 is invalid".format(record_dir))
                scenario_sha = workload.get("scenario_sha256")
                if scenario_sha is not None and not _is_sha256_text(scenario_sha):
                    problems.append("{} manifest scenario SHA-256 is invalid".format(record_dir))
                if not _is_sha256_text(workload.get("contract_sha256")):
                    problems.append("{} manifest contract SHA-256 is invalid".format(record_dir))
            if len(set(workload_ids)) != len(workload_ids):
                problems.append("{} manifest workload IDs are duplicated".format(record_dir))
            if set(workload_ids) != {"picotetris-opt1b-vrp5", "picoedit-r1-vrp2f"}:
                problems.append(
                    "{} manifest workload set must be the fixed PicoTetris/PicoEdit pair".format(
                        record_dir
                    )
                )
        identities = manifest.get("backend_identities")
        if not isinstance(identities, dict) or not identities:
            problems.append("{} manifest backend identities are missing".format(record_dir))
        else:
            allowed_roles = {
                "baseline_production", "candidate_production", "baseline_trace",
                "candidate_trace", "candidate_profile",
            }
            identity_feature_union = set()
            shared_production_labels = []
            for label, identity in identities.items():
                if label not in allowed_roles:
                    problems.append("{} backend identity label {} is invalid".format(record_dir, label))
                if not isinstance(identity, dict) or not _is_git_commit_text(identity.get("commit")):
                    problems.append("{} backend identity {} commit is invalid".format(record_dir, label))
                if not isinstance(identity, dict) or identity.get("dirty") is not False:
                    problems.append("{} backend identity {} is dirty".format(record_dir, label))
                if isinstance(identity, dict) and not _is_sha256_text(identity.get("runner_sha256")):
                    problems.append("{} backend identity {} runner SHA-256 is invalid".format(record_dir, label))
                if isinstance(identity, dict) and not _is_sha256_text(identity.get("build_provenance_sha256")):
                    problems.append("{} backend identity {} build provenance SHA-256 is invalid".format(record_dir, label))
                if isinstance(identity, dict) and (
                    not isinstance(identity.get("feature_set", []), list)
                    or not all(
                        isinstance(feature, str) and feature
                        for feature in identity.get("feature_set", [])
                    )
                ):
                    problems.append("{} backend identity {} feature_set is invalid".format(record_dir, label))
                if isinstance(identity, dict):
                    role = identity.get("role", label)
                    if role not in allowed_roles:
                        problems.append("{} backend identity {} role is invalid".format(record_dir, label))
                    feature_set = identity.get("feature_set", [])
                    if isinstance(feature_set, list):
                        identity_feature_union.update(feature_set)
                    provenance_role = identity.get("provenance_role")
                    if provenance_role is None:
                        problems.append("{} backend identity {} provenance_role is missing".format(record_dir, label))
                    elif provenance_role == "production":
                        shared_production_labels.append(label)
                    elif provenance_role != role:
                        problems.append("{} backend identity {} provenance_role differs from role".format(record_dir, label))
                    if isinstance(feature_set, list) and "sd-gen1-multiblock" not in feature_set:
                        problems.append("{} backend identity {} omits the harness default feature".format(record_dir, label))
                    if role in {"baseline_trace", "candidate_trace"} and isinstance(feature_set, list) and "behavior-trace" not in feature_set:
                        problems.append("{} backend identity {} omits behavior-trace".format(record_dir, label))
                    if role == "candidate_profile" and isinstance(feature_set, list) and "cpu-application-profiler" not in feature_set:
                        problems.append("{} backend identity {} omits cpu-application-profiler".format(record_dir, label))
                    if (
                        role == "candidate_profile"
                        and manifest.get("candidate_id") == "P2-A"
                        and isinstance(feature_set, list)
                        and "pending-exception-fast-reject" not in feature_set
                    ):
                        problems.append(
                            "{} backend identity {} omits pending-exception-fast-reject for P2-A".format(
                                record_dir, label
                            )
                        )
            if shared_production_labels:
                if (
                    manifest.get("candidate_id") != "P0-A2"
                    or set(shared_production_labels) != {"baseline_production", "candidate_production"}
                    or identities.get("baseline_production", {}).get("runner_sha256")
                    != identities.get("candidate_production", {}).get("runner_sha256")
                ):
                    problems.append(
                        "{} production provenance role is allowed only for the shared P0-A2 runner".format(
                            record_dir
                        )
                    )
            manifest_features = manifest.get("feature_set")
            if isinstance(manifest_features, list) and sorted(set(manifest_features)) != sorted(identity_feature_union):
                problems.append("{} manifest feature_set differs from role identity feature union".format(record_dir))
        measurement_policy = manifest.get("measurement_policy")
        if measurement_policy is not None:
            policy_valid = (
                isinstance(measurement_policy, dict)
                and type(measurement_policy.get("inter_run_cooldown_seconds")) in (int, float)
                and measurement_policy.get("inter_run_cooldown_seconds") >= 0
            )
            if policy_valid and "calibration_method" in measurement_policy:
                policy_valid = policy_valid and measurement_policy == {
                    "inter_run_cooldown_seconds": 60.0,
                    "calibration_method": "interleaved-anchor-v1",
                    "anchor_layout": {
                        "pre_count": 3,
                        "after_measured_runs": [10, 20, 30],
                        "post_count": 3,
                    },
                    "anchor_run_ids": [
                        "anchor-pre-001", "anchor-pre-002", "anchor-pre-003",
                        "anchor-after-010", "anchor-after-020", "anchor-after-030",
                        "anchor-post-001", "anchor-post-002", "anchor-post-003",
                    ],
                    "correction_method": "piecewise-linear-interpolation-of-log-baseline-anchor-throughput-v1",
                    "anchor_residual_threshold": 0.02,
                    "pair_level_sensitivity_method": "raw-vs-host-corrected-log-ratio-v1",
                }
            elif policy_valid and set(measurement_policy) != {"inter_run_cooldown_seconds"}:
                policy_valid = False
            if not policy_valid:
                problems.append("{} manifest measurement_policy is invalid".format(record_dir))
        if not decision_path.is_file():
            problems.append("{} is missing decision.json".format(record_dir))
            decision = None
        else:
            decision = _verify_rp2040_cpu_artifact_shape(
                decision_path, "picocalc.rp2040-cpu-decision", problems, schema_validators
            )
        if decision is not None:
            if decision.get("record_id") != manifest.get("record_id"):
                problems.append("{} decision record_id differs from manifest".format(record_dir))
            if decision.get("candidate_id") != manifest.get("candidate_id"):
                problems.append("{} decision candidate_id differs from manifest".format(record_dir))
            if decision.get("workloads") != manifest.get("workloads"):
                problems.append("{} decision workloads differ from manifest".format(record_dir))
            if decision.get("backend_identities") != manifest.get("backend_identities"):
                problems.append("{} decision backend identities differ from manifest".format(record_dir))
            if decision.get("feature_set") != manifest.get("feature_set"):
                problems.append("{} decision feature_set differs from manifest".format(record_dir))
            if decision.get("measurement_policy") != measurement_policy:
                problems.append("{} decision measurement_policy differs from manifest".format(record_dir))
            if decision.get("status") not in {
                "pass", "fail", "bank", "pending", "invalid", "not_run"
            }:
                problems.append("{} decision status is invalid".format(record_dir))

        admission_dir = record_dir / "admission"
        if manifest.get("candidate_id") != "P0-0" and not admission_dir.exists():
            # Later phase roots point at the immutable P0-0 admission record
            # through --admission-record; they do not duplicate its receipts.
            pass
        elif not admission_dir.is_dir():
            problems.append("{} is missing admission receipts".format(record_dir))
        else:
            expected_receipts = {
                "admission-{}.json".format(workload_id) for workload_id in workload_ids
            }
            receipt_paths = sorted(admission_dir.glob("*.json"))
            if {path.name for path in receipt_paths} != expected_receipts:
                problems.append("{} admission receipts do not cover the manifest workloads".format(record_dir))
            decision_evidence = decision.get("evidence") if isinstance(decision, dict) else None
            if not isinstance(decision_evidence, list) or len(decision_evidence) != len(workload_ids):
                problems.append("{} admission decision evidence does not cover the manifest workloads".format(record_dir))
            evidence_by_workload = {
                item.get("workload"): item
                for item in decision_evidence
                if isinstance(item, dict) and isinstance(item.get("workload"), str)
            } if isinstance(decision_evidence, list) else {}
            if set(evidence_by_workload) != set(workload_ids):
                problems.append("{} admission decision evidence has duplicate or unknown workloads".format(record_dir))
            for receipt_path in receipt_paths:
                receipt = _verify_rp2040_cpu_artifact_shape(
                    receipt_path, "picocalc.rp2040-cpu-decision", problems, schema_validators
                )
                if receipt is None:
                    continue
                workload_id = receipt.get("workload")
                if receipt != evidence_by_workload.get(workload_id):
                    problems.append("{} receipt differs from decision evidence".format(receipt_path))
                if receipt.get("record_id") != manifest.get("record_id"):
                    problems.append("{} receipt record_id differs from manifest".format(receipt_path))
                if receipt.get("candidate_id") != "P0-0" or receipt.get("decision_kind") != "admission":
                    problems.append("{} receipt decision identity is invalid".format(receipt_path))
                if receipt.get("status") != "pass":
                    problems.append("{} receipt status is not pass".format(receipt_path))
                if receipt.get("correctness") != {"status": "pass", "workload": workload_id}:
                    problems.append("{} receipt correctness is not passing".format(receipt_path))
                if receipt.get("workloads") != manifest.get("workloads"):
                    problems.append("{} receipt workloads differ from manifest".format(receipt_path))
                if receipt.get("backend_identities") != manifest.get("backend_identities"):
                    problems.append("{} receipt backend identities differ from manifest".format(receipt_path))
                if receipt.get("feature_set") != manifest.get("feature_set"):
                    problems.append("{} receipt feature_set differs from manifest".format(receipt_path))
                if not isinstance(workload_id, str) or workload_id not in workload_ids:
                    problems.append("{} receipt workload is unknown".format(receipt_path))
                runs = receipt.get("runs")
                if not isinstance(runs, list) or len(runs) != 2 or receipt.get("evidence") != runs:
                    problems.append("{} receipt run evidence is invalid".format(receipt_path))
                if not _is_sha256_text(receipt.get("registered_guest_observation_sha256")):
                    problems.append("{} receipt registered projection SHA-256 is invalid".format(receipt_path))
                identity = (
                    manifest.get("backend_identities", {}).get("baseline_production")
                    if isinstance(manifest.get("backend_identities"), dict)
                    else None
                )
                if isinstance(identity, dict):
                    if receipt.get("backend_commit") != identity.get("commit"):
                        problems.append("{} receipt backend commit differs from manifest".format(receipt_path))
                    if receipt.get("runner_sha256") != identity.get("runner_sha256"):
                        problems.append("{} receipt runner SHA-256 differs from manifest".format(receipt_path))
                    if receipt.get("build_provenance_sha256") != identity.get("build_provenance_sha256"):
                        problems.append("{} receipt build provenance SHA-256 differs from manifest".format(receipt_path))
                    for run in runs if isinstance(runs, list) else []:
                        if not isinstance(run, dict):
                            continue
                        if run.get("backend_commit") != identity.get("commit"):
                            problems.append("{} receipt run backend commit differs from manifest".format(receipt_path))
                        if run.get("runner_sha256") != identity.get("runner_sha256"):
                            problems.append("{} receipt run runner SHA-256 differs from manifest".format(receipt_path))
                        if run.get("build_provenance_sha256") != identity.get("build_provenance_sha256"):
                            problems.append("{} receipt run build provenance SHA-256 differs from manifest".format(receipt_path))
                        if run.get("guest_observation_sha256") != receipt.get("registered_guest_observation_sha256"):
                            problems.append("{} receipt run projection differs from registered digest".format(receipt_path))

        summary_path = record_dir / "summary.json"
        ab_dir = record_dir / "ab"
        run_by_id: Dict[str, Dict[str, Any]] = {}
        if ab_dir.exists():
            if manifest.get("candidate_id") == "P2-A":
                profile_name = manifest.get("diagnostic_profile_record")
                profile_record_dir = (
                    records_root / profile_name
                    if isinstance(profile_name, str)
                    and profile_name.startswith("rp2040-cpu-")
                    and Path(profile_name).name == profile_name
                    else None
                )
                if profile_record_dir is None or profile_record_dir == record_dir or not profile_record_dir.is_dir():
                    problems.append("{} P2-A AB diagnostic_profile_record is missing or invalid".format(record_dir))
                else:
                    linked_manifest_path = profile_record_dir / "manifest.json"
                    try:
                        linked_manifest = load_json(linked_manifest_path)
                    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                        linked_manifest = None
                        problems.append("{} P2-A linked profile manifest is unreadable: {}".format(record_dir, error))
                    if isinstance(linked_manifest, Mapping):
                        if linked_manifest.get("candidate_id") != "P2-A":
                            problems.append("{} P2-A linked profile candidate_id is invalid".format(record_dir))
                        if linked_manifest.get("workloads") != manifest.get("workloads"):
                            problems.append("{} P2-A linked profile workloads differ from AB".format(record_dir))
                        if linked_manifest.get("measurement_cpu") != manifest.get("measurement_cpu"):
                            problems.append("{} P2-A linked profile CPU differs from AB".format(record_dir))
                        linked_profile_features = linked_manifest.get("feature_set")
                        if (
                            not isinstance(linked_profile_features, list)
                            or "cpu-application-profiler" not in linked_profile_features
                            or "pending-exception-fast-reject" not in linked_profile_features
                        ):
                            problems.append("{} P2-A linked profile features are incomplete".format(record_dir))
                        try:
                            linked_decision = load_json(profile_record_dir / "decision.json")
                        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                            linked_decision = None
                            problems.append("{} P2-A linked profile decision is unreadable: {}".format(record_dir, error))
                        if (
                            not isinstance(linked_decision, Mapping)
                            or linked_decision.get("decision_kind") != "profile"
                            or linked_decision.get("status") != "pass"
                        ):
                            problems.append("{} P2-A linked profile decision is not passing".format(record_dir))
                        ab_candidate = (
                            manifest.get("backend_identities", {}).get("candidate_production")
                            if isinstance(manifest.get("backend_identities"), Mapping)
                            else None
                        )
                        profile_candidate = (
                            linked_manifest.get("backend_identities", {}).get("candidate_profile")
                            if isinstance(linked_manifest.get("backend_identities"), Mapping)
                            else None
                        )
                        if not isinstance(ab_candidate, Mapping) or not isinstance(profile_candidate, Mapping) or ab_candidate.get("commit") != profile_candidate.get("commit"):
                            problems.append("{} P2-A linked profile backend commit differs from AB candidate".format(record_dir))
            summary = None
            if not summary_path.is_file():
                problems.append("{} AB record is missing summary.json".format(record_dir))
            else:
                summary = _verify_rp2040_cpu_artifact_shape(
                    summary_path, "picocalc.rp2040-cpu-ab", problems, schema_validators
                )
                if summary is not None:
                    if summary.get("record_id") != manifest.get("record_id"):
                        problems.append("{} summary record_id differs from manifest".format(record_dir))
                    if summary.get("pairs") != 10 or summary.get("measured_runs") != 40:
                        problems.append("{} summary does not describe the fixed 10-pair/40-run batch".format(record_dir))
                    if summary.get("measurement_policy") != measurement_policy:
                        problems.append("{} summary measurement_policy differs from manifest".format(record_dir))
                    summary_is_invalid = summary.get("status") == "invalid"
                    if not isinstance(summary.get("workloads"), dict):
                        problems.append("{} summary workloads is not an object".format(record_dir))
                    elif not summary_is_invalid and set(summary["workloads"]) != set(
                        workload_ids if isinstance(workloads, list) else []
                    ):
                        problems.append("{} summary workload set differs from manifest".format(record_dir))
                    if not isinstance(summary.get("pair_results"), list):
                        problems.append("{} summary pair_results is not an array".format(record_dir))
                    elif summary_is_invalid:
                        calibration = summary.get("calibration")
                        calibration_failed = (
                            isinstance(calibration, Mapping)
                            and calibration.get("valid") is False
                        )
                        has_projection_mismatch = any(
                            isinstance(item, Mapping)
                            and item.get("guest_observation_equal") is not True
                            for item in summary["pair_results"]
                        )
                        null_control = summary.get("null_control")
                        null_failed = (
                            manifest.get("candidate_id") == "P0-A2"
                            and isinstance(null_control, Mapping)
                            and null_control.get("pass") is False
                        )
                        if not (calibration_failed or has_projection_mismatch or null_failed):
                            problems.append(
                                "{} invalid summary does not preserve a calibration, projection, or null-control failure".format(
                                    record_dir
                                )
                            )
                        if len(summary["pair_results"]) not in {0, 20}:
                            problems.append("{} invalid summary pair_results has an unexpected size".format(record_dir))
                        if len(summary["pair_results"]) == 0 and summary.get("workloads") != {}:
                            problems.append("{} invalid summary without pair results must have empty workloads".format(record_dir))
                    elif len(summary["pair_results"]) != 20:
                        problems.append("{} summary pair_results is not the fixed 20-entry set".format(record_dir))
            run_paths = sorted(ab_dir.glob("run-*.json")) if ab_dir.is_dir() else []
            if not run_paths:
                problems.append("{} AB directory has no run artifacts".format(record_dir))
            if len(run_paths) != 40:
                problems.append("{} AB directory must contain exactly 40 run artifacts".format(record_dir))
            expected_schedule = _expected_rp2040_cpu_schedule(workload_ids) if isinstance(workloads, list) and len(workload_ids) == 2 else {}
            seen_run_ids = set()
            for run_path in run_paths:
                run = _verify_rp2040_cpu_artifact_shape(
                    run_path, "picocalc.rp2040-cpu-ab", problems, schema_validators
                )
                if run is not None:
                    if run.get("record_id") != manifest.get("record_id"):
                        problems.append("{} run record_id differs from manifest".format(run_path))
                    if not _is_sha256_text(run.get("guest_observation_sha256")):
                        problems.append("{} guest projection SHA-256 is invalid".format(run_path))
                    run_id = run.get("run_id")
                    expected_run = expected_schedule.get(run_id) if isinstance(run_id, str) else None
                    if expected_run is None:
                        problems.append("{} run_id is not in the fixed schedule".format(run_path))
                    else:
                        if any(run.get(field) != expected_run[field] for field in ("pair", "order", "workload", "role")):
                            problems.append("{} run fields differ from the fixed schedule".format(run_path))
                    if isinstance(run_id, str):
                        if run_id in seen_run_ids:
                            problems.append("{} run_id is duplicated".format(run_path))
                        seen_run_ids.add(run_id)
                        run_by_id[run_id] = run
                    role_label = "{}_production".format(run.get("role"))
                    identity = identities.get(role_label) if isinstance(identities, dict) else None
                    if not isinstance(identity, dict):
                        problems.append("{} has no manifest identity for {}".format(run_path, role_label))
                    else:
                        if run.get("backend_commit") != identity.get("commit"):
                            problems.append("{} backend commit differs from manifest".format(run_path))
                        if run.get("runner_sha256") != identity.get("runner_sha256"):
                            problems.append("{} runner SHA-256 differs from manifest".format(run_path))
                        if run.get("build_provenance_sha256") != identity.get("build_provenance_sha256"):
                            problems.append("{} build provenance SHA-256 differs from manifest".format(run_path))
            if expected_schedule and seen_run_ids != set(expected_schedule):
                problems.append("{} AB run IDs do not cover the fixed schedule".format(record_dir))
            if isinstance(summary, dict) and isinstance(summary.get("pair_results"), list):
                seen_pairs = set()
                for pair_result in summary["pair_results"]:
                    if not isinstance(pair_result, dict):
                        problems.append("{} contains a non-object pair result".format(summary_path))
                        continue
                    workload_id = pair_result.get("workload")
                    pair_index = pair_result.get("pair_index")
                    key = (workload_id, pair_index)
                    if key in seen_pairs:
                        problems.append("{} contains a duplicate pair result for {}".format(summary_path, key))
                    seen_pairs.add(key)
                    run_ids = pair_result.get("run_ids")
                    if not isinstance(run_ids, list) or len(run_ids) != 2 or not all(
                        isinstance(run_id, str) for run_id in run_ids
                    ):
                        problems.append("{} has invalid pair run_ids".format(summary_path))
                        continue
                    pair_runs = [run_by_id.get(run_id) for run_id in run_ids]
                    if any(run is None for run in pair_runs):
                        problems.append("{} pair result references an unknown run".format(summary_path))
                        continue
                    baseline_run, candidate_run = pair_runs
                    if baseline_run.get("role") != "baseline" or candidate_run.get("role") != "candidate":
                        problems.append("{} pair result run roles are invalid".format(summary_path))
                    if baseline_run.get("workload") != workload_id or candidate_run.get("workload") != workload_id:
                        problems.append("{} pair result workload disagrees with run artifacts".format(summary_path))
                    if baseline_run.get("pair") != pair_index or candidate_run.get("pair") != pair_index:
                        problems.append("{} pair result index disagrees with run artifacts".format(summary_path))
                    if pair_result.get("order") != baseline_run.get("order") or pair_result.get("order") != candidate_run.get("order"):
                        problems.append("{} pair result order disagrees with run artifacts".format(summary_path))
                    for role, run in (("baseline", baseline_run), ("candidate", candidate_run)):
                        digest_field = role + "_guest_observation_sha256"
                        if pair_result.get(digest_field) != run.get("guest_observation_sha256"):
                            problems.append("{} pair result {} digest disagrees with run artifacts".format(summary_path, role))
                    expected_equal = (
                        baseline_run.get("guest_observation_sha256")
                        == candidate_run.get("guest_observation_sha256")
                    )
                    if pair_result.get("guest_observation_equal") != expected_equal:
                        problems.append("{} pair result guest equality disagrees with run artifacts".format(summary_path))

            if isinstance(summary, Mapping):
                _verify_interleaved_anchor_summary(record_dir, manifest, summary, run_by_id, problems)
                if manifest.get("candidate_id") == "P0-A2":
                    null_control = summary.get("null_control")
                    if isinstance(null_control, Mapping):
                        null_pass = null_control.get("pass") is True
                        has_projection_mismatch = any(
                            isinstance(item, Mapping)
                            and item.get("guest_observation_equal") is not True
                            for item in summary.get("pair_results", [])
                        )
                        decision_is_invalid = (
                            isinstance(decision, Mapping)
                            and decision.get("decision_kind") == "invalid"
                            and decision.get("status") == "invalid"
                        )
                        decision_is_passing_null = (
                            isinstance(decision, Mapping)
                            and decision.get("decision_kind") == "null-control"
                            and decision.get("status") == "pass"
                        )
                        if has_projection_mismatch:
                            if summary.get("status") != "invalid" or not decision_is_invalid:
                                problems.append(
                                    "{} guest projection mismatch must fail closed with invalid P0-A2 summary and decision".format(
                                        record_dir
                                    )
                                )
                        elif null_pass:
                            if summary.get("status") != "pass" or not decision_is_passing_null:
                                problems.append("{} passing P0-A2 null-control must have a passing null-control summary and decision".format(record_dir))
                        elif summary.get("status") != "invalid" or not decision_is_invalid:
                            problems.append("{} failing P0-A2 null-control must have invalid summary and decision".format(record_dir))

        profile_dir = record_dir / "profile"
        candidate_profiles: Dict[str, Tuple[Path, Mapping[str, Any]]] = {}
        if profile_dir.exists():
            profile_paths = (
                sorted(
                    path for path in profile_dir.glob("*.json")
                    if not path.name.endswith("-measurement.json")
                )
                if profile_dir.is_dir()
                else []
            )
            if not profile_paths:
                problems.append("{} profile directory has no artifacts".format(record_dir))
            for profile_path in profile_paths:
                profile = _verify_rp2040_cpu_artifact_shape(
                    profile_path, "picocalc.rp2040-cpu-profile", problems, schema_validators
                )
                if profile is not None and isinstance(identities, dict):
                    if profile.get("candidate_id") != manifest.get("candidate_id"):
                        problems.append("{} profile candidate_id differs from manifest".format(profile_path))
                    workload = profile.get("workload")
                    workload_id = workload.get("id") if isinstance(workload, Mapping) else None
                    if isinstance(workload_id, str):
                        if workload_id in candidate_profiles:
                            problems.append("{} contains duplicate profile workload {}".format(record_dir, workload_id))
                        else:
                            candidate_profiles[workload_id] = (profile_path, profile)
                    identity = identities.get("candidate_profile")
                    backend = profile.get("backend")
                    runner = profile.get("runner")
                    if isinstance(identity, dict) and isinstance(backend, dict):
                        if backend.get("commit") != identity.get("commit"):
                            problems.append("{} profile backend commit differs from manifest".format(profile_path))
                    if isinstance(identity, dict) and isinstance(runner, dict):
                        if runner.get("sha256") != identity.get("runner_sha256"):
                            problems.append("{} profile runner SHA-256 differs from manifest".format(profile_path))
                        if runner.get("build_provenance_sha256") != identity.get("build_provenance_sha256"):
                            problems.append("{} profile build provenance SHA-256 differs from manifest".format(profile_path))
                    if isinstance(identity, dict) and profile.get("feature_set") != identity.get("feature_set", []):
                        problems.append("{} profile feature_set differs from manifest".format(profile_path))
                    if manifest.get("candidate_id") == "P2-A":
                        profile_features = profile.get("feature_set")
                        if (
                            not isinstance(profile_features, list)
                            or "cpu-application-profiler" not in profile_features
                            or "pending-exception-fast-reject" not in profile_features
                        ):
                            problems.append(
                                "{} P2-A profile feature_set must include cpu-application-profiler and pending-exception-fast-reject".format(
                                    profile_path
                                )
                            )
                        _verify_pending_exception_poll_equation(profile_path, profile, problems)

            if manifest.get("candidate_id") == "P2-A":
                expected_profile_workloads = set(workload_ids)
                if set(candidate_profiles) != expected_profile_workloads:
                    problems.append(
                        "{} P2-A profiles must cover exactly the two manifest workloads".format(record_dir)
                    )
        elif manifest.get("candidate_id") == "P2-A" and record_dir.name in linked_profile_names:
            problems.append("{} P2-A profile directory is missing".format(record_dir))

        profile_comparison_path = record_dir / "profile-comparison.json"
        if profile_comparison_path.is_file():
            profile_comparison = _verify_rp2040_cpu_artifact_shape(
                profile_comparison_path,
                "picocalc.rp2040-cpu-profile-comparison",
                problems,
                schema_validators,
            )
            if profile_comparison is not None:
                _verify_rp2040_cpu_profile_comparison(
                    profile_comparison_path,
                    profile_comparison,
                    record_dir,
                    records_root,
                    manifest,
                    candidate_profiles,
                    schema_validators,
                    problems,
                )
        elif manifest.get("candidate_id") == "P1-A" and profile_dir.is_dir():
            problems.append("{} P1-A profile is missing profile-comparison.json".format(record_dir))

        correctness_dir = record_dir / "correctness"
        if correctness_dir.exists():
            workload_dirs = [path for path in correctness_dir.iterdir() if path.is_dir()] if correctness_dir.is_dir() else []
            if not workload_dirs:
                problems.append("{} correctness directory has no workload".format(record_dir))
            for workload_dir in workload_dirs:
                comparison_path = workload_dir / "comparison.json"
                if not comparison_path.is_file():
                    problems.append("{} is missing comparison.json".format(workload_dir))
                else:
                    comparison = _verify_rp2040_cpu_artifact_shape(
                        comparison_path, "picocalc.rp2040-cpu-ab", problems, schema_validators
                    )
                    if comparison is not None:
                        if comparison.get("record_id") != manifest.get("record_id"):
                            problems.append("{} comparison record_id differs from manifest".format(workload_dir))
                        if comparison.get("workload") != workload_dir.name:
                            problems.append("{} comparison workload differs from directory".format(workload_dir))
                        if comparison.get("behavior_equal") is not True:
                            problems.append("{} correctness behavior gate is not passing".format(workload_dir))
                        if (
                            ab_dir.exists()
                            and comparison.get("trace_required") is False
                            and manifest.get("candidate_id") != "P0-A2"
                        ):
                            problems.append(
                                "{} final-report-only correctness is allowed only for P0-A2".format(
                                    workload_dir
                                )
                            )
                        report_commits: Dict[str, str] = {}
                        for role in ("baseline", "candidate"):
                            report_path = workload_dir / "{}-report.json".format(role)
                            projection_path = workload_dir / "{}-projection.json".format(role)
                            if not report_path.is_file() or not projection_path.is_file():
                                problems.append("{} is missing {} report/projection".format(workload_dir, role))
                                continue
                            try:
                                report = load_json(report_path)
                                projection = load_json(projection_path)
                            except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                                problems.append("{} {} report/projection is unreadable: {}".format(workload_dir, role, error))
                                continue
                            if not isinstance(report, dict) or not isinstance(projection, dict):
                                problems.append("{} {} report/projection is not an object".format(workload_dir, role))
                                continue
                            expected_projection = _rp2040_guest_observation_projection(report)
                            if projection != expected_projection:
                                problems.append("{} {} projection differs from report".format(workload_dir, role))
                            digest = _canonical_json_sha256(projection)
                            if comparison.get("{}_guest_observation_sha256".format(role)) != digest:
                                problems.append("{} {} correctness digest differs from projection".format(workload_dir, role))
                            backend = report.get("backend_build")
                            if not isinstance(backend, dict) or not _is_git_commit_text(backend.get("commit")) or backend.get("dirty") is not False:
                                problems.append("{} {} report backend identity is invalid".format(workload_dir, role))
                            else:
                                report_commits[role] = backend["commit"]
                                if isinstance(identities, dict):
                                    identity = identities.get("{}_production".format(role))
                                    if isinstance(identity, dict) and backend.get("commit") != identity.get("commit"):
                                        problems.append("{} {} report backend commit differs from manifest".format(workload_dir, role))
                            measurement = comparison.get(role)
                            if not isinstance(measurement, dict):
                                problems.append("{} {} correctness measurement is missing".format(workload_dir, role))
                            elif isinstance(identities, dict):
                                identity = identities.get("{}_production".format(role))
                                if isinstance(identity, dict):
                                    if measurement.get("backend_commit") != identity.get("commit"):
                                        problems.append(
                                            "{} {} correctness measurement backend commit differs from manifest".format(
                                                workload_dir, role
                                            )
                                        )
                                    if measurement.get("runner_sha256") != identity.get("runner_sha256"):
                                        problems.append(
                                            "{} {} correctness measurement runner SHA-256 differs from manifest".format(
                                                workload_dir, role
                                            )
                                        )
                                    if measurement.get("build_provenance_sha256") != identity.get("build_provenance_sha256"):
                                        problems.append(
                                            "{} {} correctness measurement build provenance SHA-256 differs from manifest".format(
                                                workload_dir, role
                                            )
                                        )
                        if comparison.get("trace_required") is True:
                            if not isinstance(identities, dict) or not all(
                                isinstance(identities.get("{}_trace".format(role)), dict)
                                for role in ("baseline", "candidate")
                            ):
                                problems.append(
                                    "{} trace-required correctness is missing trace backend identities".format(
                                        workload_dir
                                    )
                                )
                            behavior_paths = [
                                workload_dir / "baseline-behavior.json",
                                workload_dir / "candidate-behavior.json",
                            ]
                            if not all(path.is_file() for path in behavior_paths):
                                for behavior_path in behavior_paths:
                                    if not behavior_path.is_file():
                                        problems.append("{} is missing {}".format(workload_dir, behavior_path.name))
                            else:
                                expected_behavior_commits = dict(report_commits)
                                if isinstance(identities, dict):
                                    for role in ("baseline", "candidate"):
                                        trace_identity = identities.get("{}_trace".format(role))
                                        if isinstance(trace_identity, dict) and _is_git_commit_text(
                                            trace_identity.get("commit")
                                        ):
                                            expected_behavior_commits[role] = trace_identity["commit"]
                                _verify_rp2040_cpu_behavior_pair(
                                    behavior_paths[0], behavior_paths[1], comparison, problems,
                                    expected_commits=expected_behavior_commits,
                                )

        sums_path = record_dir / "SHA256SUMS"
        if not sums_path.is_file():
            problems.append("{} is missing SHA256SUMS".format(record_dir))
        else:
            try:
                listed_paths = set()
                for line in sums_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    digest, relative = line.split("  ", 1)
                    artifact_path = _record_path_within(record_dir, relative)
                    if not _is_sha256_text(digest) or artifact_path is None or not artifact_path.is_file():
                        problems.append("{} contains an invalid artifact entry".format(sums_path))
                        continue
                    if artifact_path in listed_paths:
                        problems.append("{} contains a duplicate artifact entry for {}".format(sums_path, relative))
                        continue
                    listed_paths.add(artifact_path)
                    if sha256(artifact_path) != digest:
                        problems.append("{} digest mismatch for {}".format(sums_path, relative))
                for artifact_path in record_dir.rglob("*"):
                    resolved_artifact = artifact_path.resolve()
                    if resolved_artifact.is_file() and resolved_artifact.name != "SHA256SUMS" and resolved_artifact not in listed_paths:
                        problems.append("{} is missing an artifact entry for {}".format(sums_path, artifact_path.relative_to(record_dir)))
            except (OSError, UnicodeError, ValueError) as error:
                problems.append("{} is unreadable: {}".format(sums_path, error))
    add_check(
        checks,
        "firmware-validation:rp2040-cpu-records",
        not problems,
        records=len(record_dirs),
        errors=problems,
    )


def verify_next3_negative_conformance(checks: List[Check], root: Path) -> None:
    """Verify NEXT-3 definitions, audits, fault artifact, and hardware attempt."""
    name = "next3:negative-conformance-contract"
    base = root / "firmware-validation"
    paths = {
        "case_schema": base / "negative-conformance-case.schema.json",
        "kpi_schema": base / "negative-conformance-kpi.schema.json",
        "contract": base / "contracts/next3-negative-conformance-v1.json",
        "v2_contract": base / "contracts/next3-lcd-cs-fault-v2.json",
        "sd_crc_contract": base / "contracts/next3-sd-cmd8-crc-v1.json",
        "sd_crc_baseline": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/record.json",
        "sd_crc_baseline_notes": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/notes.md",
        "sd_crc_baseline_procedure": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/PROCEDURE.md",
        "sd_crc_baseline_scenario": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/scenario.json",
        "sd_crc_baseline_report": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/run-report.json",
        "sd_crc_baseline_uart": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/uart.log",
        "sd_crc_baseline_snapshot": base
        / "records/next3-sd-cmd8-crc-a1-20260810-01/final.png",
        "sd_crc_baseline_hardware": base
        / "records/next3-sd-cmd8-crc-a1-hardware-20260810-01/record.json",
        "sd_crc_baseline_hardware_notes": base
        / "records/next3-sd-cmd8-crc-a1-hardware-20260810-01/notes.md",
        "sd_crc_baseline_hardware_kpi": base
        / "records/next3-sd-cmd8-crc-a1-hardware-20260810-01/kpi.json",
        "sd_crc_baseline_hardware_uart": base
        / "records/next3-sd-cmd8-crc-a1-hardware-20260810-01/evidence/uf2loader-uart.log",
        "sd_crc_baseline_hardware_photo": base
        / "records/next3-sd-cmd8-crc-a1-hardware-20260810-01/evidence/final.jpg",
        "sd_crc_fault": base
        / "records/next3-sd-cmd8-crc-b-20260810-01/record.json",
        "sd_crc_fault_notes": base
        / "records/next3-sd-cmd8-crc-b-20260810-01/notes.md",
        "sd_crc_fault_procedure": base
        / "records/next3-sd-cmd8-crc-b-20260810-01/PROCEDURE.md",
        "sd_crc_fault_hardware": base
        / "records/next3-sd-cmd8-crc-b-hardware-20260810-01/record.json",
        "sd_crc_fault_hardware_notes": base
        / "records/next3-sd-cmd8-crc-b-hardware-20260810-01/notes.md",
        "sd_crc_fault_hardware_uart": base
        / "records/next3-sd-cmd8-crc-b-hardware-20260810-01/evidence/uf2loader-uart.log",
        "sd_crc_fault_hardware_photo": base
        / "records/next3-sd-cmd8-crc-b-hardware-20260810-01/evidence/final.jpg",
        "sd_crc_fault_first": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/record.json",
        "sd_crc_fault_first_notes": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/notes.md",
        "sd_crc_fault_first_kpi": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/kpi.json",
        "sd_crc_fault_first_report": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/run-report.json",
        "sd_crc_fault_first_uart": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/uart.log",
        "sd_crc_fault_first_scenario": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/scenario.json",
        "sd_crc_fault_first_snapshot": base
        / "records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/snapshots/next3-sd-b-first.png",
        "sd_crc_post_fix": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/record.json",
        "sd_crc_post_fix_notes": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/notes.md",
        "sd_crc_post_fix_kpi": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/kpi.json",
        "sd_crc_post_fix_report": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/run-report.json",
        "sd_crc_post_fix_uart": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/uart.log",
        "sd_crc_post_fix_scenario": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/scenario.json",
        "sd_crc_post_fix_snapshot": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/snapshots/next3-sd-b-post-fix.png",
        "sd_crc_post_fix_a1_report": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/a1-positive/run-report.json",
        "sd_crc_post_fix_a1_uart": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/a1-positive/uart.log",
        "sd_crc_post_fix_a1_snapshot": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/a1-positive/snapshots/next3-sd-a1-final.png",
        "v2_baseline": base / "records/next3-v2-a1-20260810-01/record.json",
        "v2_hardware": base
        / "records/next3-v2-a1-hardware-20260810-01/record.json",
        "v2_hardware_notes": base
        / "records/next3-v2-a1-hardware-20260810-01/notes.md",
        "v2_hardware_uart": base
        / "records/next3-v2-a1-hardware-20260810-01/evidence/uf2loader-uart.log",
        "v2_hardware_photo": base
        / "records/next3-v2-a1-hardware-20260810-01/evidence/final.jpg",
        "v2_fault": base / "records/next3-v2-b-20260810-01/record.json",
        "v2_fault_notes": base / "records/next3-v2-b-20260810-01/notes.md",
        "v2_fault_procedure": base / "records/next3-v2-b-20260810-01/PROCEDURE.md",
        "v2_fault_hardware": base
        / "records/next3-v2-b-hardware-attempt-20260810-01/record.json",
        "v2_fault_hardware_notes": base
        / "records/next3-v2-b-hardware-attempt-20260810-01/notes.md",
        "v2_fault_hardware_kpi": base
        / "records/next3-v2-b-hardware-attempt-20260810-01/kpi.json",
        "v2_fault_hardware_uart": base
        / "records/next3-v2-b-hardware-attempt-20260810-01/evidence/uf2loader-uart.log",
        "v2_fault_hardware_photo": base
        / "records/next3-v2-b-hardware-attempt-20260810-01/evidence/uf2loader-final.jpg",
        "v2_gap_analysis": base
        / "records/next3-v2-gap-analysis-20260810-01/record.json",
        "initial_kpi": base / "records/next3-0-20260810-01/kpi.json",
        "audit": base / "records/next3-lcd-031-audit-20260810-01/record.json",
        "post_audit_kpi": base / "records/next3-1-20260810-01/kpi.json",
        "fault": base / "records/next3-lcd-cs-fault-v1-20260810-01/record.json",
        "pre_hardware_kpi": base / "records/next3-fault-build-20260810-01/kpi.json",
        "fault_hardware": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/record.json",
        "pre_a1_kpi": base / "records/next3-hardware-attempt-20260810-01/kpi.json",
        "current_kpi": base
        / "records/next3-sd-cmd8-crc-b-post-fix-20260810-01/kpi.json",
        "hardware_notes": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/notes.md",
        "hardware_uart": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/evidence/uf2loader-uart.log",
        "hardware_photo": base
        / "records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/evidence/uf2loader-final.jpg",
        "fault_bundle": root / "provenance/picocalc-next3-lcd-fault-v1.bundle",
        "v2_fault_bundle": root / "provenance/picocalc-next3-lcd-fault-v2-b.bundle",
        "sd_crc_baseline_bundle": root
        / "provenance/picocalc-next3-sd-crc-a1.bundle",
        "sd_crc_fault_bundle": root / "provenance/picocalc-next3-sd-crc-b.bundle",
        "document": root / "docs/NEXT3_NEGATIVE_CONFORMANCE.md",
        "v2_document": root / "docs/NEXT3_V2_CANDIDATE_DESIGN.md",
        "sd_crc_document": root / "docs/NEXT3_SD_CMD8_CRC_CANDIDATE.md",
    }
    expected_hashes = {
        "case_schema": "3153f4a902f8a99b938a01bafadffd019f9a9180fe3d4c79eaf890f84359c0ef",
        "kpi_schema": "bef7639eba4a60af8d2ceed9176655b31b6f26763f3d8777a344e00f873a82a5",
        "contract": "c2cc54339efcc5a3eb888a216d76ac0c067f53bd98397e0fad098afb6e77eb80",
        "v2_contract": "b0df0227b538c9efd507d6653547c5d9f3d543d2b1b673b5198f8554e229c680",
        "sd_crc_contract": "6b1bda91096f582ccca5fc76a73bca8ec0dc1a47cdc46e3b59fd1d126e07e9d1",
        "sd_crc_baseline": "eed8e205bcb30d87fa6079f9071a29d352f7aac7e6a83ca130d7d7220be555d6",
        "sd_crc_baseline_notes": "4fd7cad89bedffc96eec8b68a6d483d3b244e0fdf4b85f5e231abb596f6a0792",
        "sd_crc_baseline_procedure": "7f1bd58447124c43c7e04298d6c269e8030b2d433724848a57986e4e3f4f91ed",
        "sd_crc_baseline_scenario": "3f11d13dac356fa2c2183b7ba36e826acbad852ea357f7d6e3c577d883e72c6c",
        "sd_crc_baseline_report": "0c6a812a9ae60dda1c9b7ffae890a5150f996b77988cbf7339f0a6dea46026c2",
        "sd_crc_baseline_uart": "d20a01901bd9c996b47dcd54001951c1a6f279ad5a0b6e4c24fe33952759fbd0",
        "sd_crc_baseline_snapshot": "cbf66f14a737bb86d110c9b8dbc24c94c71c3be8545964d47181b60c45a4e04b",
        "sd_crc_baseline_hardware": "55777e8453ce9cd4cca48fec477181729eb446f50b9ed24f764e802191dd960e",
        "sd_crc_baseline_hardware_notes": "59c63b28d97e71db139087abcc473ac8e8a4de18af1f46a69bcdee2f9ab288eb",
        "sd_crc_baseline_hardware_kpi": "ae999828b9967104fc677e620ebb23b186f86b99e3274c491d54ba472c67be11",
        "sd_crc_baseline_hardware_uart": "24e0591562cedb4720593a4df3606c99c1f0f28addc4ac162570851eb847db45",
        "sd_crc_baseline_hardware_photo": "75e4931ff20d88dc0d1db1d051b24e8d30f912c0336dcdff7f4aafe188f1c5a9",
        "sd_crc_fault": "7b56b578512993d844a725d4e2e3e8a06aab36ed403693abfb951ccda958d7e8",
        "sd_crc_fault_notes": "5a87035578dffe3cd9a2b30f450dc14c23cc30167986eafd44d36aaff79d112d",
        "sd_crc_fault_procedure": "d246ef5333bca1a82c1808e8e9c75e145685e85852cb84294922f9042025c840",
        "sd_crc_fault_hardware": "d88489688958e3b7a09a7ec3fe70846759e312f82e8bfbe34165cb53b77d6c5f",
        "sd_crc_fault_hardware_notes": "7743db67b16e61e2ea68368657b6ee16174ef4782f2f429de40c352eb64a8ba9",
        "sd_crc_fault_hardware_uart": "fe807c7c440f4ea8e73996d87381a6491b5279db59a244f02424260e6bdaa637",
        "sd_crc_fault_hardware_photo": "ad7d4c28f7ca17d43420dd5d71eaaadbdf9e84b9fbc0b66884da3a08c788c13d",
        "sd_crc_fault_first": "951d954afdb24fcc3df2826a651f8c385d9f664a67617c98c12aa03efc602297",
        "sd_crc_fault_first_notes": "a552963292c200b53362260d064eb8cc0a576316842b282dfdebe63cf7a696d4",
        "sd_crc_fault_first_kpi": "788dad9fc6ba7883e9b97c167c17dbb314f93cd9ff4ae9dc193b1ec48276c819",
        "sd_crc_fault_first_report": "ad13793fc8124d325d913600404f7c710f132a02f6c4d0a91f0a343fae65d047",
        "sd_crc_fault_first_uart": "b630efd489bf4cd2119f8979296b71873eb011b711f470258336d247de4a212b",
        "sd_crc_fault_first_scenario": "360ec5eb4809e0646532dd31a78886cd5366e0d4adb13686f8590288ba83bcda",
        "sd_crc_fault_first_snapshot": "cbf66f14a737bb86d110c9b8dbc24c94c71c3be8545964d47181b60c45a4e04b",
        "sd_crc_post_fix": "6df91f1471f192ba0f26964b018f23496b2b73aaad3deafbf5f36f8ee949a6ac",
        "sd_crc_post_fix_notes": "521c9845441eedc8b6b5ad16f515a45ce1c6d1faa6b78554f5fd320a64229fc7",
        "sd_crc_post_fix_kpi": "12deec2b49718859d3b04aa0481d6b035455d53503b0d654cdf63b036f08a9e0",
        "sd_crc_post_fix_report": "64bc4cca7bd72763b477e40a24ace2bbb1c730c8669c85cffc84fb5061b9ab0d",
        "sd_crc_post_fix_uart": "e1be937c078f4f7ff5c2e780501380c0fb604500336ae9a82f67a11aaf658b03",
        "sd_crc_post_fix_scenario": "30aaa2db01513d8bc218572e64e853b4190e8c798e26c7452952b6b7df625941",
        "sd_crc_post_fix_snapshot": "3bff8592f0909fee5c6c5e67637934c2d5a5292c043ea1bb716726002a4d3bc3",
        "sd_crc_post_fix_a1_report": "68f18e728bb6c3e47175ceee25b775307edd988699c7813574ca98cc3384395e",
        "sd_crc_post_fix_a1_uart": "d20a01901bd9c996b47dcd54001951c1a6f279ad5a0b6e4c24fe33952759fbd0",
        "sd_crc_post_fix_a1_snapshot": "cbf66f14a737bb86d110c9b8dbc24c94c71c3be8545964d47181b60c45a4e04b",
        "v2_baseline": "09593899724148dfa8bdf4b85f85c960f357c9c69c14f7d8aa1de1c62c13546a",
        "v2_hardware": "6512202c3add131141dcabfddf25b67d3973bf406c07e4b5bdff05717ab35bd5",
        "v2_hardware_notes": "73c91e56c71cb02f347126c704819f5c1d2e837a6814d2bbbcda876f0f88ccf0",
        "v2_hardware_uart": "c81af57000c634507944be2db0a38f652c778eb715b0da584d273c36f3db8500",
        "v2_hardware_photo": "33764382ac3b5273a348298501e6a322d6907fc5ff3c98da1e6cbe501091f67f",
        "v2_fault": "8e68cfe5d93dc1c7beac93c662134373f136f6ecc860c251393a23ca756e9547",
        "v2_fault_notes": "d609c10592d463c4db31fe873e1c7e530a64d5307a7bc46cf4821a65f72d1bc0",
        "v2_fault_procedure": "64553f5d8866091c0a8a4d50b93c5b6fe44eec05c8496a46575390ca556c587a",
        "v2_fault_hardware": "917ae54b010cded047c3875178a5884d9dcf8632484bdc4af83db053a88cce75",
        "v2_fault_hardware_notes": "5717939a484d75ad4e3746228be90dd0000e8a428843e6269aaa7d601d787d99",
        "v2_fault_hardware_kpi": "7a8a274088067359f63ff22e57b60ddcd56d52c8116ebb7ae047e4a3f2c293fc",
        "v2_fault_hardware_uart": "5ce18ee718aca94522298525b0906e4854a26281747b79a310b36da9d686a726",
        "v2_fault_hardware_photo": "2b4ca43e6c240c4e25fe7f4c3d4bfaa97dfef8664c841863eb91f8e0e31a7a1f",
        "v2_gap_analysis": "787b3c0226cbd65ea95d1149ee1f788952cb1fa14eea11a3e40cde5df7529e8f",
        "initial_kpi": "32461e423f912c766cb3a0cf335f5d508c42955b05bf18111757ed7e35bb3913",
        "audit": "a02130b8c0b6326b45218a26712d6f02ac0af9977ec462c076643caed90ead4c",
        "post_audit_kpi": "39e962d3d802c6d6a6348b0133f311affaaf367aa7385350f9581125ddd10157",
        "fault": "056642382c11d553b137054b4e2385557fa67b179bfd47965012ae9217c3c4ab",
        "pre_hardware_kpi": "dc5f2f2f6cc00d7de83fde1deffdc908cf266c0b03e0591ce8fd8e5c9ec4b771",
        "fault_hardware": "60187ecb99c179ae7d234f02d99dbee18ca641f8793911265265b699d8287a14",
        "pre_a1_kpi": "57e6300596a0191a1f9b0a2af5619f2debf5d06ea74b4cf3af8b7f3417b32998",
        "current_kpi": "12deec2b49718859d3b04aa0481d6b035455d53503b0d654cdf63b036f08a9e0",
        "hardware_notes": "21611323ed4552e7718d06534efc4ce6e1205c4ac841f6217787632604c6986d",
        "hardware_uart": "e3187f9a2ce38eaae9361a0a2e1723ef561f7716d9d51f67cc03909fff755550",
        "hardware_photo": "84ba4e05ff16b8a5fa20a35a18f43bc5dfa6bd62cdd2e0533638a9cf58324f20",
        "fault_bundle": "8824baed4577441da7d58b3a52502c8a7392e029e2bfb53cbfddd4912b7b4ad6",
        "v2_fault_bundle": "876a1889897517d01a18ee813922a725f602c52df988627b8eccaf1b71534de0",
        "sd_crc_baseline_bundle": "ed985de566638e07e0a20e974b351646729b434a6bb05edd349dc5fb162a05da",
        "sd_crc_fault_bundle": "3e3fded89db4d4feb9a0d1c810d388e18ccc49c698ab466a371e3c2c94f1739a",
        "document": "6abf7500ddefa67677dff3a8a1a31980f1818b559bcdb94428b47725ba819520",
        "v2_document": "5f0cc1a739cbc002c0097be5545ee953edb8dd05c4a71ae3f5991950683ae704",
        "sd_crc_document": "cfd6cb741f4fde135a00591cb412d87f295c4d8e40965744c77e2bbd2de84ec6",
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
        positive_count: int = 5,
        hardware_cases: int = 0,
        correct_detections: int = 0,
        false_accepts: int = 0,
    ) -> bool:
        if not isinstance(snapshot, dict):
            return False
        positive = snapshot.get("positive_correlations", {})
        negative = snapshot.get("negative_conformance", {})
        rates = snapshot.get("rates", {})
        positive_records = positive.get("records")
        negative_records = negative.get("records")
        if hardware_cases == 0:
            rates_valid = all(
                (
                    rates.get("state") == "no_negative_denominator",
                    rates.get("denominator") == 0,
                    rates.get("detection_rate") is None,
                    rates.get("false_accept_rate") is None,
                )
            )
        else:
            rates_valid = all(
                (
                    rates.get("state") == "measured",
                    rates.get("denominator") == hardware_cases,
                    rates.get("detection_rate")
                    == correct_detections / hardware_cases,
                    rates.get("false_accept_rate") == false_accepts / hardware_cases,
                )
            )
        return all(
            (
                snapshot.get("schema_version") == 1,
                snapshot.get("roadmap_package") == "NEXT-3",
                snapshot.get("contract_id") == "next3-negative-conformance-v1-20260810",
                positive.get("completed_count") == positive_count,
                positive.get("completed_count") == len(positive_records),
                positive.get("emulator_pass_hardware_fail_count") == 0,
                evidence_records_valid(positive_records),
                negative.get("candidates_audited") == candidates,
                negative.get("hardware_confirmed_cases") == hardware_cases,
                negative.get("correct_detections") == correct_detections,
                negative.get("false_accepts") == false_accepts,
                negative.get("wrong_reason_failures") == 0,
                negative.get("artifact_audit_failures") == audit_failures,
                negative.get("inconclusive_cases") == inconclusive,
                len(negative_records) == records,
                evidence_records_valid(negative_records),
                rates.get("denominator") == negative.get("hardware_confirmed_cases"),
                correct_detections + false_accepts <= hardware_cases,
                rates_valid,
            )
        )

    try:
        case_schema = load_json(paths["case_schema"])
        kpi_schema = load_json(paths["kpi_schema"])
        contract = load_json(paths["contract"])
        v2_contract = load_json(paths["v2_contract"])
        sd_crc_contract = load_json(paths["sd_crc_contract"])
        sd_crc_baseline = load_json(paths["sd_crc_baseline"])
        sd_crc_baseline_scenario = load_json(paths["sd_crc_baseline_scenario"])
        sd_crc_baseline_report = load_json(paths["sd_crc_baseline_report"])
        sd_crc_baseline_hardware = load_json(paths["sd_crc_baseline_hardware"])
        sd_crc_baseline_hardware_kpi = load_json(
            paths["sd_crc_baseline_hardware_kpi"]
        )
        sd_crc_fault = load_json(paths["sd_crc_fault"])
        sd_crc_fault_hardware = load_json(paths["sd_crc_fault_hardware"])
        sd_crc_fault_first = load_json(paths["sd_crc_fault_first"])
        sd_crc_fault_first_kpi = load_json(paths["sd_crc_fault_first_kpi"])
        sd_crc_fault_first_report = load_json(paths["sd_crc_fault_first_report"])
        sd_crc_fault_first_scenario = load_json(paths["sd_crc_fault_first_scenario"])
        sd_crc_post_fix = load_json(paths["sd_crc_post_fix"])
        sd_crc_post_fix_report = load_json(paths["sd_crc_post_fix_report"])
        sd_crc_post_fix_scenario = load_json(paths["sd_crc_post_fix_scenario"])
        sd_crc_post_fix_a1_report = load_json(paths["sd_crc_post_fix_a1_report"])
        v2_baseline = load_json(paths["v2_baseline"])
        v2_hardware = load_json(paths["v2_hardware"])
        v2_fault = load_json(paths["v2_fault"])
        v2_fault_hardware = load_json(paths["v2_fault_hardware"])
        v2_fault_hardware_kpi = load_json(paths["v2_fault_hardware_kpi"])
        v2_gap_analysis = load_json(paths["v2_gap_analysis"])
        initial = load_json(paths["initial_kpi"])
        audit = load_json(paths["audit"])
        post_audit = load_json(paths["post_audit_kpi"])
        fault = load_json(paths["fault"])
        pre_hardware = load_json(paths["pre_hardware_kpi"])
        fault_hardware = load_json(paths["fault_hardware"])
        pre_a1 = load_json(paths["pre_a1_kpi"])
        current = load_json(paths["current_kpi"])
        candidate = contract["first_candidate"]
        admission = contract["admission"]
        kpi_policy = contract["kpi_policy"]
        artifact = audit["artifact_audit"]
        fault_artifact = fault["artifact_audit"]
        v2_evidence = v2_contract["confirmed_evidence"]
        v2_cause = v2_contract["cause_analysis"]
        v2_post_hardware = v2_contract["post_hardware_analysis"]
        v2_experiment = v2_contract["controlled_experiment"]
        v2_oracle = v2_contract["fault_oracle"]
        v2_progress = v2_contract["baseline_progress"]
        v2_fault_progress = v2_contract["fault_progress"]
        sd_crc_sources = sd_crc_contract["frozen_sources"]
        sd_crc_gap = sd_crc_contract["predicted_model_gap"]
        sd_crc_design = sd_crc_contract["firmware_design"]
        sd_crc_progress = sd_crc_contract["baseline_progress"]
        sd_crc_fault_progress = sd_crc_contract["fault_progress"]
        sd_crc_post_fix_progress = sd_crc_contract["post_fix_progress"]
        sd_crc_oracle = sd_crc_contract["frozen_hardware_oracle"]
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
                v2_contract.get("schema_version") == 1,
                v2_contract.get("contract_id")
                == "next3-lcd-cs-fault-v2-predesign-20260810",
                v2_contract.get("parent_contract_id")
                == "next3-negative-conformance-v1-20260810",
                v2_contract.get("status")
                == "fault_hardware_oracle_mismatch_inconclusive",
                v2_progress.get("implementation_commit")
                == "168a65d9f8206d2767641c589f21f359c1ce7b1b",
                v2_progress.get("bin_sha256")
                == "28c42956d63b162fa6a0487ba82cfcdb1e63fc62b13ce0672c0344cdaf7f5f6c",
                v2_progress.get("uf2_sha256")
                == "ce15219188b35ef54edebfcb6b6df09ec8632145d8e1ce28ea750f2444742c99",
                v2_progress.get("clean_clone_reproducible") is True,
                v2_progress.get("emulator_backend_commit")
                == "4a90864816ef58286f2b292df0e7fe44fbcd4809",
                v2_progress.get("emulator_result") == "pass",
                v2_progress.get("hardware_result") == "pass",
                v2_progress.get("record")
                == "firmware-validation/records/next3-v2-a1-20260810-01/record.json",
                v2_progress.get("hardware_record")
                == "firmware-validation/records/next3-v2-a1-hardware-20260810-01/record.json",
                v2_progress.get("fault_implementation_allowed") is True,
                v2_fault_progress.get("implementation_commit")
                == "3a073fbf206b02993dd80a0a7158c1e3c865efff",
                v2_fault_progress.get("bin_sha256")
                == "f9f5a347c36b38fbcb93967cd6a6bcd7caafb8d19805d235e0bfc7a27c5a18a4",
                v2_fault_progress.get("uf2_sha256")
                == "8f45245d8b0c8f1d543d1f909368ca4c48438e898352b48c3afcdaa172cb291f",
                v2_fault_progress.get("source_bundle")
                == "provenance/picocalc-next3-lcd-fault-v2-b.bundle",
                v2_fault_progress.get("source_bundle_sha256")
                == expected_hashes["v2_fault_bundle"],
                v2_fault_progress.get("clean_clone_reproducible") is True,
                v2_fault_progress.get("change_budget_audit") == "pass",
                v2_fault_progress.get("hardware_result") == "fail_oracle_mismatch",
                v2_fault_progress.get("hardware_record")
                == "firmware-validation/records/next3-v2-b-hardware-attempt-20260810-01/record.json",
                v2_fault_progress.get("hardware_record_sha256")
                == expected_hashes["v2_fault_hardware"],
                v2_fault_progress.get("classification") == "inconclusive",
                v2_fault_progress.get("emulator_result") == "not_run_by_contract",
                v2_fault_progress.get("emulator_backend_commit_reserved_for_first_run")
                == "4a90864816ef58286f2b292df0e7fe44fbcd4809",
                v2_fault_progress.get("emulator_run_allowed") is False,
                v2_fault_progress.get("record")
                == "firmware-validation/records/next3-v2-b-20260810-01/record.json",
                v2_fault_progress.get("next_action") == "candidate_closed_inconclusive",
                v2_evidence.get("historical_failure", {}).get("source_commit")
                == "5b12a7cbff45a928c440a70a4e3a77750c1daa13",
                v2_evidence.get("historical_failure", {}).get("display_source_sha256")
                == "8f297c88c9ccfda7fc5f1b7344fdd6b3049e8cc1dd69c48b2c35c5b39bc80f38",
                v2_evidence.get("v1_inconclusive_attempt", {}).get(
                    "write_framing_matches_historical_defect"
                )
                is True,
                v2_evidence.get("v1_inconclusive_attempt", {}).get(
                    "observer_matches_historical_failure"
                )
                is False,
                v2_cause.get("confirmed_major_confounder")
                == "v1 reproduced the historical write-side CS boundaries but retained a different RAMRD observer, so it was not the complete measurement setup that produced the frozen historical oracle",
                "not sufficient to recover the historical oracle"
                in v2_cause.get("causal_status", ""),
                v2_post_hardware.get("record")
                == "firmware-validation/records/next3-v2-gap-analysis-20260810-01/record.json",
                v2_post_hardware.get("record_sha256")
                == expected_hashes["v2_gap_analysis"],
                v2_post_hardware.get("highest_ranked_remaining_variable")
                == "160x160 fill tiling and resulting window/CS boundary sequence",
                v2_post_hardware.get("v2_closed") is True,
                v2_post_hardware.get("emulator_run_allowed") is False,
                v2_post_hardware.get("historical_oracle_changed") is False,
                v2_post_hardware.get("next_candidate_contract")
                == "firmware-validation/contracts/next3-sd-cmd8-crc-v1.json",
                v2_post_hardware.get("next_candidate_contract_sha256")
                == "bdb9c981d4a76b82972ae76e94febf724831f4e74f00b0e13ee849f9b7b4e903",
                v2_post_hardware.get("next_action")
                == "implement_sd_cmd8_crc_a1_baseline",
                sd_crc_contract.get("schema_version") == 1,
                sd_crc_contract.get("contract_id")
                == "next3-sd-cmd8-crc-v1-predesign-20260810",
                sd_crc_contract.get("parent_contract_id")
                == "next3-negative-conformance-v1-20260810",
                sd_crc_contract.get("status")
                == "closed_correct_detection_after_false_accept_fix",
                sd_crc_contract.get("specification_authority", {}).get("section")
                == "7.2.2 Bus Transfer Protection",
                sd_crc_sources.get("generator_commit")
                == "5a27dc7a00852004f797d4331bde942a4d821a0f",
                sd_crc_sources.get("sd_driver_sha256")
                == "215b99d02fb39c179caa5eb55bf5a8efbab3be518ded621afaf5c733b26ec47a",
                sd_crc_sources.get("backend_commit_reserved_for_first_fault_run")
                == "4a90864816ef58286f2b292df0e7fe44fbcd4809",
                sd_crc_sources.get("backend_sd_model_sha256")
                == "e4aaad6d73acc13669c16549ccafb843964dcc53d095edfbac27c0aa28890e91",
                sd_crc_gap.get("firmware_correct_cmd8_crc_byte") == "87",
                sd_crc_gap.get("fault_cmd8_crc_byte") == "85",
                sd_crc_gap.get("fault_crc_end_bit_remains_one") is True,
                sd_crc_gap.get("prediction_is_not_a_result") is True,
                sd_crc_gap.get("backend_change_before_first_fault_run_allowed")
                is False,
                sd_crc_design.get("filesystem_mount_or_write_allowed") is False,
                sd_crc_design.get("manual_key_input_required") is False,
                sd_crc_design.get("fault", {}).get("allowed_changes_from_baseline")
                == [
                    "application identity and evidence marker",
                    "the transmitted CMD8 CRC literal from 0x87 to 0x85",
                    "the expected command-trace CRC identity from 0x87 to 0x85 so the test measures backend acceptance rather than rejecting its own injected byte",
                    "documentation that describes only these frozen changes and the hardware-first boundary",
                ],
                sd_crc_progress.get("source_commit")
                == "f942b8eb000858e6f00bb8fde255f27243dfbac8",
                sd_crc_progress.get("embedded_app_git") == "f942b8eb0008",
                sd_crc_progress.get("embedded_bsp_git")
                == "5a27dc7a0085-dirty",
                sd_crc_progress.get("bin_sha256")
                == "0ae9eea01f87c542cd7c41f1880c42d428c0f143c909dfe116c16e1cf5afce1b",
                sd_crc_progress.get("uf2_sha256")
                == "be9c0e8deda02307e34a96c11cec21255f1e197902920d1fe8e05f9d472a9ffd",
                sd_crc_progress.get("source_bundle")
                == "provenance/picocalc-next3-sd-crc-a1.bundle",
                sd_crc_progress.get("source_bundle_sha256")
                == expected_hashes["sd_crc_baseline_bundle"],
                sd_crc_progress.get("clean_clone_reproducible") is True,
                sd_crc_progress.get("emulator_backend_commit")
                == "4a90864816ef58286f2b292df0e7fe44fbcd4809",
                sd_crc_progress.get("emulator_result") == "pass",
                sd_crc_progress.get("record")
                == "firmware-validation/records/next3-sd-cmd8-crc-a1-20260810-01/record.json",
                sd_crc_progress.get("hardware_result") == "pass",
                sd_crc_progress.get("hardware_record")
                == "firmware-validation/records/next3-sd-cmd8-crc-a1-hardware-20260810-01/record.json",
                sd_crc_progress.get("hardware_record_sha256")
                == expected_hashes["sd_crc_baseline_hardware"],
                sd_crc_progress.get("kpi_snapshot")
                == "firmware-validation/records/next3-sd-cmd8-crc-a1-hardware-20260810-01/kpi.json",
                sd_crc_progress.get("kpi_snapshot_sha256")
                == expected_hashes["sd_crc_baseline_hardware_kpi"],
                sd_crc_progress.get("fault_implementation_allowed") is True,
                sd_crc_progress.get("fault_emulator_run_allowed") is False,
                sd_crc_fault_progress.get("source_commit")
                == "e78cabbe20416eb2347e0db09408bf906d41c698",
                sd_crc_fault_progress.get("embedded_app_git") == "e78cabbe2041",
                sd_crc_fault_progress.get("embedded_bsp_git")
                == "5a27dc7a0085-dirty",
                sd_crc_fault_progress.get("bin_sha256")
                == "6665ca51944e2c1fb2f7e2ba7adb01ce6878290aac0dfb929202714b83509bd0",
                sd_crc_fault_progress.get("uf2_sha256")
                == "43ea10982d6f9b1d1adf9565b2b88f8b1866ddd60410b4ae53fda8e2f9a3e958",
                sd_crc_fault_progress.get("source_bundle")
                == "provenance/picocalc-next3-sd-crc-b.bundle",
                sd_crc_fault_progress.get("source_bundle_sha256")
                == expected_hashes["sd_crc_fault_bundle"],
                sd_crc_fault_progress.get("clean_clone_reproducible") is True,
                sd_crc_fault_progress.get("change_budget_audit") == "pass",
                sd_crc_fault_progress.get("record")
                == "firmware-validation/records/next3-sd-cmd8-crc-b-20260810-01/record.json",
                sd_crc_fault_progress.get("record_sha256")
                == expected_hashes["sd_crc_fault"],
                sd_crc_fault_progress.get("hardware_result")
                == "fail_oracle_match",
                sd_crc_fault_progress.get("hardware_record")
                == "firmware-validation/records/next3-sd-cmd8-crc-b-hardware-20260810-01/record.json",
                sd_crc_fault_progress.get("hardware_record_sha256")
                == expected_hashes["sd_crc_fault_hardware"],
                sd_crc_fault_progress.get("emulator_result")
                == "pass_false_accept",
                sd_crc_fault_progress.get("emulator_backend_dirty") is False,
                sd_crc_fault_progress.get("first_emulator_record")
                == "firmware-validation/records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/record.json",
                sd_crc_fault_progress.get("first_emulator_record_sha256")
                == expected_hashes["sd_crc_fault_first"],
                sd_crc_fault_progress.get("first_emulator_report_sha256")
                == expected_hashes["sd_crc_fault_first_report"],
                sd_crc_fault_progress.get("first_emulator_uart_sha256")
                == expected_hashes["sd_crc_fault_first_uart"],
                sd_crc_fault_progress.get("classification") == "false_accept",
                sd_crc_fault_progress.get("emulator_run_allowed") is False,
                sd_crc_fault_progress.get("backend_change_allowed") is True,
                sd_crc_baseline.get("record_id")
                == "next3-sd-cmd8-crc-a1-20260810-01",
                sd_crc_baseline.get("stage")
                == "baseline_emulator_pass_hardware_pending",
                sd_crc_baseline.get("classification")
                == "positive_control_pending_hardware",
                sd_crc_baseline.get("firmware", {}).get("commit")
                == sd_crc_progress.get("source_commit"),
                sd_crc_baseline.get("firmware", {}).get("bin_sha256")
                == sd_crc_progress.get("bin_sha256"),
                sd_crc_baseline.get("firmware", {}).get("uf2_sha256")
                == sd_crc_progress.get("uf2_sha256"),
                sd_crc_baseline.get("firmware", {}).get("clean_clone_reproducible")
                is True,
                sd_crc_baseline.get("source_bundle", {}).get("sha256")
                == expected_hashes["sd_crc_baseline_bundle"],
                sd_crc_baseline.get("protocol", {}).get("cmd0_r1") == "01",
                sd_crc_baseline.get("protocol", {}).get("cmd8_argument")
                == "000001aa",
                sd_crc_baseline.get("protocol", {}).get("cmd8_crc") == "87",
                sd_crc_baseline.get("protocol", {}).get("cmd8_r1") == "01",
                sd_crc_baseline.get("protocol", {}).get("cmd8_r7")
                == "000001aa",
                sd_crc_baseline.get("protocol", {}).get("filesystem_access")
                == "none",
                sd_crc_baseline.get("emulator", {}).get("verdict") == "pass",
                sd_crc_baseline.get("emulator", {}).get("backend_commit")
                == sd_crc_progress.get("emulator_backend_commit"),
                sd_crc_baseline.get("emulator", {}).get("report_sha256")
                == expected_hashes["sd_crc_baseline_report"],
                sd_crc_baseline.get("emulator", {}).get("uart_sha256")
                == expected_hashes["sd_crc_baseline_uart"],
                sd_crc_baseline.get("emulator", {}).get("snapshot_png_sha256")
                == expected_hashes["sd_crc_baseline_snapshot"],
                sd_crc_baseline.get("emulator", {}).get("sd_blocks_read") == 0,
                sd_crc_baseline.get("emulator", {}).get("sd_blocks_written") == 0,
                sd_crc_baseline.get("emulator", {}).get("exception") is None,
                sd_crc_baseline.get("emulator", {}).get("unsupported_mmio_count")
                == 0,
                sd_crc_baseline.get("hardware", {}).get("result") == "pending",
                sd_crc_baseline.get("fault_gate", {}).get(
                    "fault_source_implementation_allowed"
                )
                is False,
                sd_crc_baseline.get("fault_gate", {}).get("fault_emulator_run_allowed")
                is False,
                sd_crc_baseline_scenario.get("name") == "next3-sd-cmd8-crc-a1",
                sd_crc_baseline_scenario.get("steps", [{}])[0]
                .get("condition", {})
                .get("text")
                == "filesystem=none keys=none app=pass",
                sd_crc_baseline_report.get("backend_commit")
                == sd_crc_progress.get("emulator_backend_commit"),
                sd_crc_baseline_report.get("firmware", {}).get("sha256")
                == sd_crc_progress.get("bin_sha256"),
                sd_crc_baseline_report.get("verdict", {}).get("status") == "pass",
                sd_crc_baseline_report.get("stop_reason") == "scenario_done",
                sd_crc_baseline_report.get("exception") is None,
                sd_crc_baseline_report.get("unsupported_mmio") == [],
                sd_crc_baseline_report.get("sd", {}).get("blocks_read") == 0,
                sd_crc_baseline_report.get("sd", {}).get("blocks_written") == 0,
                sd_crc_baseline_report.get("scenario", {}).get("status") == "pass",
                sd_crc_baseline_hardware.get("record_id")
                == "next3-sd-cmd8-crc-a1-hardware-20260810-01",
                sd_crc_baseline_hardware.get("result") == "pass",
                sd_crc_baseline_hardware.get("source", {}).get("commit")
                == sd_crc_progress.get("source_commit"),
                sd_crc_baseline_hardware.get("artifact", {}).get("bin_sha256")
                == sd_crc_progress.get("bin_sha256"),
                sd_crc_baseline_hardware.get("artifact", {}).get("uf2_sha256")
                == sd_crc_progress.get("uf2_sha256"),
                sd_crc_baseline_hardware.get("deployment", {}).get("path")
                == "uf2loader",
                sd_crc_baseline_hardware.get("deployment", {}).get("bootsel_used")
                is False,
                sd_crc_baseline_hardware.get("physical_run", {}).get("card_detect")
                == "present",
                sd_crc_baseline_hardware.get("physical_run", {})
                .get("protocol", {})
                .get("cmd0_crc")
                == "95",
                sd_crc_baseline_hardware.get("physical_run", {})
                .get("protocol", {})
                .get("cmd0_r1")
                == "01",
                sd_crc_baseline_hardware.get("physical_run", {})
                .get("protocol", {})
                .get("cmd8_crc")
                == "87",
                sd_crc_baseline_hardware.get("physical_run", {})
                .get("protocol", {})
                .get("cmd8_r1")
                == "01",
                sd_crc_baseline_hardware.get("physical_run", {})
                .get("protocol", {})
                .get("cmd8_r7")
                == "000001aa",
                sd_crc_baseline_hardware.get("physical_run", {}).get(
                    "evidence_marker_count"
                )
                == 39,
                sd_crc_baseline_hardware.get("physical_run", {}).get(
                    "evidence_marker_stable"
                )
                is True,
                sd_crc_baseline_hardware.get("correlation", {}).get(
                    "hardware_correlation_completed"
                )
                is True,
                sd_crc_baseline_hardware.get("correlation", {}).get(
                    "emulator_result"
                )
                == "pass",
                sd_crc_baseline_hardware.get("correlation", {}).get(
                    "hardware_result"
                )
                == "pass",
                sd_crc_baseline_hardware.get("negative_kpi_effect", {}).get(
                    "hardware_confirmed_negative_cases_delta"
                )
                == 0,
                sd_crc_baseline_hardware.get("gate", {}).get(
                    "fault_source_implementation_allowed"
                )
                is True,
                sd_crc_baseline_hardware.get("gate", {}).get(
                    "fault_emulator_run_allowed"
                )
                is False,
                snapshot_valid(
                    sd_crc_baseline_hardware_kpi,
                    candidates=3,
                    audit_failures=1,
                    inconclusive=2,
                    records=3,
                    positive_count=7,
                ),
                sd_crc_fault.get("record_id")
                == "next3-sd-cmd8-crc-b-20260810-01",
                sd_crc_fault.get("stage")
                == "fault_artifact_frozen_hardware_pending",
                sd_crc_fault.get("classification") == "pending_hardware_oracle",
                sd_crc_fault.get("fault_source", {}).get("commit")
                == sd_crc_fault_progress.get("source_commit"),
                sd_crc_fault.get("fault_source", {}).get(
                    "executable_changed_paths_from_a1"
                )
                == ["CMakeLists.txt", "app/main.cpp", "bsp/src/sdcard.cpp"],
                sd_crc_fault.get("fault_source", {}).get("change_budget_audit", {}).get(
                    "result"
                )
                == "pass",
                all(
                    sd_crc_fault.get("fault_source", {})
                    .get("change_budget_audit", {})
                    .get(field)
                    is False
                    for field in (
                        "cmd0_changed",
                        "cmd8_argument_changed",
                        "spi_clock_mode_or_bit_order_changed",
                        "chip_select_or_polling_changed",
                        "r7_parsing_or_timeout_changed",
                        "filesystem_or_key_behavior_changed",
                        "backend_changed",
                    )
                ),
                sd_crc_fault.get("fault_injection", {}).get("baseline_crc_byte")
                == "87",
                sd_crc_fault.get("fault_injection", {}).get("fault_crc_byte")
                == "85",
                sd_crc_fault.get("fault_injection", {}).get("end_bit_remains_one")
                is True,
                sd_crc_fault.get("fault_injection", {}).get(
                    "expected_trace_identity_changed_to_fault_crc"
                )
                is True,
                sd_crc_fault.get("artifact", {}).get("bin_sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_fault.get("artifact", {}).get("uf2_sha256")
                == sd_crc_fault_progress.get("uf2_sha256"),
                sd_crc_fault.get("artifact", {}).get("clean_clone_reproducible")
                is True,
                sd_crc_fault.get("artifact", {}).get("source_bundle_sha256")
                == expected_hashes["sd_crc_fault_bundle"],
                sd_crc_fault.get("frozen_hardware_oracle", {}).get("cmd8_crc")
                == "85",
                sd_crc_fault.get("frozen_hardware_oracle", {}).get("cmd8_r1")
                == "09",
                sd_crc_fault.get("frozen_hardware_oracle", {}).get(
                    "later_initialization_commands_allowed"
                )
                is False,
                sd_crc_fault.get("frozen_hardware_oracle", {}).get(
                    "post_hoc_change_allowed"
                )
                is False,
                sd_crc_fault.get("hardware", {}).get("path") == "uf2loader",
                sd_crc_fault.get("hardware", {}).get("result") == "pending",
                sd_crc_fault.get("emulator", {}).get("result")
                == "not_run_by_contract",
                sd_crc_fault.get("emulator", {}).get("run_allowed") is False,
                sd_crc_fault.get("negative_kpi_effect", {}).get(
                    "hardware_confirmed_negative_cases_delta"
                )
                == 0,
                sd_crc_fault_hardware.get("record_id")
                == "next3-sd-cmd8-crc-b-hardware-20260810-01",
                sd_crc_fault_hardware.get("status") == "hardware_observed",
                sd_crc_fault_hardware.get("classification") == "pending",
                sd_crc_fault_hardware.get("artifact_audit", {}).get(
                    "source_commit"
                )
                == sd_crc_fault_progress.get("source_commit"),
                sd_crc_fault_hardware.get("artifact_audit", {}).get("bin_sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_fault_hardware.get("artifact_audit", {}).get("uf2_sha256")
                == sd_crc_fault_progress.get("uf2_sha256"),
                sd_crc_fault_hardware.get("hardware_observation", {}).get("status")
                == "complete",
                sd_crc_fault_hardware.get("hardware_observation", {}).get("result")
                == "fail",
                sd_crc_fault_hardware.get("hardware_observation", {}).get("reason")
                == "the physical SD card rejected CMD8 CRC 0x85 with R1 0x09, containing idle-state plus COM_CRC_ERROR, and initialization stopped at the frozen CMD8 CRC failure stage",
                len(
                    sd_crc_fault_hardware.get("hardware_observation", {}).get(
                        "evidence", []
                    )
                )
                == 9,
                sd_crc_fault_hardware.get("emulator_observation", {}).get("status")
                == "pending",
                sd_crc_fault_hardware.get("emulator_observation", {}).get("result")
                == "pending",
                sd_crc_fault_hardware.get("reason_match", {}).get("status")
                == "pending",
                sd_crc_fault_hardware.get("reason_match", {}).get("hardware_reason")
                == sd_crc_fault_hardware.get("reason_match", {}).get(
                    "expected_reason"
                ),
                sd_crc_fault_hardware.get("kpi_effect")
                == {
                    "negative_denominator_delta": 1,
                    "correct_detection_delta": 0,
                    "false_accept_delta": 0,
                },
                sd_crc_fault_first.get("record_id")
                == "next3-sd-cmd8-crc-b-first-emulator-20260810-01",
                sd_crc_fault_first.get("status") == "closed",
                sd_crc_fault_first.get("classification") == "false_accept",
                sd_crc_fault_first.get("artifact_audit", {}).get("bin_sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_fault_first.get("hardware_observation", {}).get("status")
                == "complete",
                sd_crc_fault_first.get("hardware_observation", {}).get("result")
                == "fail",
                sd_crc_fault_first.get("emulator_observation", {}).get("status")
                == "complete",
                sd_crc_fault_first.get("emulator_observation", {}).get("result")
                == "pass",
                sd_crc_fault_first.get("reason_match", {}).get("status")
                == "mismatch",
                sd_crc_fault_first.get("kpi_effect")
                == {
                    "negative_denominator_delta": 1,
                    "correct_detection_delta": 0,
                    "false_accept_delta": 1,
                },
                sd_crc_fault_first_report.get("backend_build", {}).get("commit")
                == sd_crc_sources.get("backend_commit_reserved_for_first_fault_run"),
                sd_crc_fault_first_report.get("backend_build", {}).get("dirty")
                is False,
                sd_crc_fault_first_report.get("firmware", {}).get("sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_fault_first_report.get("verdict", {}).get("status") == "pass",
                sd_crc_fault_first_report.get("stop_reason") == "scenario_done",
                sd_crc_fault_first_report.get("exception") is None,
                sd_crc_fault_first_report.get("unsupported_mmio") == [],
                sd_crc_fault_first_report.get("sd", {}).get("blocks_read") == 0,
                sd_crc_fault_first_report.get("sd", {}).get("blocks_written") == 0,
                sd_crc_fault_first_report.get("uart", {}).get("sha256")
                == expected_hashes["sd_crc_fault_first_uart"],
                sd_crc_fault_first_report.get("framebuffer", {}).get(
                    "rgb565_sha256"
                )
                == "a40734de3413157f1a121de37a66f286c315226f155896d5af27e6eaf7c74274",
                sd_crc_fault_first_scenario.get("name")
                == "next3-sd-cmd8-crc-b-first-emulator",
                sd_crc_fault_first_scenario.get("steps", [{}])[0]
                .get("condition", {})
                .get("text")
                == "[NEXT3][SD_CMD8_B][EVIDENCE]",
                sd_crc_post_fix_progress.get("backend_commit")
                == "5edca80ae3cd9f73d381399628a7cc1ab801bdf3",
                sd_crc_post_fix_progress.get("backend_dirty") is False,
                sd_crc_post_fix_progress.get("backend_sd_model_sha256")
                == "48f2a6d7f3198d9ad7d27d9dfe6b40b8088ac5ae2e8edd762091e9402fe29622",
                sd_crc_post_fix_progress.get("backend_sd_wire_sha256")
                == "9825f21595c0b7ce04470deb4dff2d9c2a8767e696a3a3b6a8f1b93c51a14092",
                sd_crc_post_fix_progress.get("fault_bin_sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_post_fix_progress.get("fault_result") == "fail_oracle_match",
                sd_crc_post_fix_progress.get("classification")
                == "correct_negative_detection",
                sd_crc_post_fix_progress.get("record_sha256")
                == expected_hashes["sd_crc_post_fix"],
                sd_crc_post_fix_progress.get("kpi_snapshot_sha256")
                == expected_hashes["sd_crc_post_fix_kpi"],
                sd_crc_post_fix_progress.get("a2_is_exact_a1_artifact") is True,
                sd_crc_post_fix_progress.get("a2_bin_sha256")
                == sd_crc_progress.get("bin_sha256"),
                sd_crc_post_fix_progress.get("a2_uf2_sha256")
                == sd_crc_progress.get("uf2_sha256"),
                sd_crc_post_fix_progress.get("a2_emulator_result") == "pass",
                sd_crc_post_fix_progress.get("a2_emulator_report_sha256")
                == expected_hashes["sd_crc_post_fix_a1_report"],
                sd_crc_post_fix_progress.get("a2_uart_matches_a1") is True,
                sd_crc_post_fix_progress.get("a2_snapshot_matches_a1") is True,
                sd_crc_post_fix_progress.get("third_hardware_run_required") is False,
                sd_crc_post_fix_progress.get("local_backend_workspace_tests")
                == "pass",
                sd_crc_post_fix_progress.get("ci_run") is False,
                sd_crc_post_fix.get("record_id")
                == "next3-sd-cmd8-crc-b-post-fix-20260810-01",
                sd_crc_post_fix.get("status") == "closed",
                sd_crc_post_fix.get("classification")
                == "correct_negative_detection",
                sd_crc_post_fix.get("artifact_audit", {}).get("bin_sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_post_fix.get("hardware_observation", {}).get("status")
                == "complete",
                sd_crc_post_fix.get("hardware_observation", {}).get("result")
                == "fail",
                sd_crc_post_fix.get("emulator_observation", {}).get("status")
                == "complete",
                sd_crc_post_fix.get("emulator_observation", {}).get("result")
                == "fail",
                sd_crc_post_fix.get("reason_match", {}).get("status") == "match",
                sd_crc_post_fix.get("reason_match", {}).get("emulator_reason")
                == sd_crc_post_fix.get("reason_match", {}).get("hardware_reason"),
                sd_crc_post_fix.get("kpi_effect")
                == {
                    "negative_denominator_delta": 1,
                    "correct_detection_delta": 1,
                    "false_accept_delta": 0,
                },
                sd_crc_post_fix_report.get("backend_build", {}).get("commit")
                == sd_crc_post_fix_progress.get("backend_commit"),
                sd_crc_post_fix_report.get("backend_build", {}).get("dirty") is False,
                sd_crc_post_fix_report.get("firmware", {}).get("sha256")
                == sd_crc_fault_progress.get("bin_sha256"),
                sd_crc_post_fix_report.get("verdict", {}).get("status") == "pass",
                sd_crc_post_fix_report.get("stop_reason") == "scenario_done",
                sd_crc_post_fix_report.get("exception") is None,
                sd_crc_post_fix_report.get("unsupported_mmio") == [],
                sd_crc_post_fix_report.get("sd", {}).get("commands_seen") == 2,
                sd_crc_post_fix_report.get("sd", {}).get("blocks_read") == 0,
                sd_crc_post_fix_report.get("sd", {}).get("blocks_written") == 0,
                sd_crc_post_fix_report.get("uart", {}).get("sha256")
                == expected_hashes["sd_crc_post_fix_uart"],
                sd_crc_post_fix_report.get("framebuffer", {}).get("rgb565_sha256")
                == "3b5c66d920a073e181cab50e4362df741d9b1188481e09abf15c5e2cd9790cf3",
                sd_crc_post_fix_scenario.get("name")
                == "next3-sd-cmd8-crc-b-post-fix",
                sd_crc_post_fix_scenario.get("steps", [{}])[0]
                .get("condition", {})
                .get("text")
                == "filesystem=none keys=none app=fail",
                sd_crc_post_fix_a1_report.get("backend_build", {}).get("commit")
                == sd_crc_post_fix_progress.get("backend_commit"),
                sd_crc_post_fix_a1_report.get("firmware", {}).get("sha256")
                == sd_crc_progress.get("bin_sha256"),
                sd_crc_post_fix_a1_report.get("verdict", {}).get("status") == "pass",
                sd_crc_post_fix_a1_report.get("sd", {}).get("commands_seen") == 9,
                sd_crc_post_fix_a1_report.get("sd", {}).get("blocks_read") == 0,
                sd_crc_post_fix_a1_report.get("sd", {}).get("blocks_written") == 0,
                sd_crc_post_fix_a1_report.get("uart", {}).get("sha256")
                == expected_hashes["sd_crc_baseline_uart"]
                == expected_hashes["sd_crc_post_fix_a1_uart"],
                expected_hashes["sd_crc_baseline_snapshot"]
                == expected_hashes["sd_crc_post_fix_a1_snapshot"],
                sd_crc_oracle.get("deployment_path") == "uf2loader",
                sd_crc_oracle.get("bootsel_required") is False,
                sd_crc_oracle.get("cmd0_r1") == "01",
                sd_crc_oracle.get("cmd8_crc_byte") == "85",
                sd_crc_oracle.get("cmd8_r1") == "09",
                sd_crc_oracle.get("failure_stage") == "cmd8_crc",
                sd_crc_oracle.get("later_initialization_commands_allowed") is False,
                sd_crc_oracle.get("filesystem_access_allowed") is False,
                sd_crc_oracle.get("post_hoc_change_allowed") is False,
                sd_crc_contract.get("human_operations", {}).get(
                    "required_hardware_runs"
                )
                == 2,
                sd_crc_contract.get("human_operations", {}).get(
                    "completed_hardware_runs"
                )
                == 2,
                sd_crc_contract.get("human_operations", {}).get(
                    "remaining_hardware_runs"
                )
                == 0,
                sd_crc_contract.get("human_operations", {}).get("keys_required") == 0,
                sd_crc_contract.get("media_and_loader_controls", {}).get(
                    "application_must_not_mount_format_write_or_remove_files"
                )
                is True,
                sd_crc_contract.get("ci_policy", {}).get(
                    "local_validation_only_during_development"
                )
                is True,
                v2_experiment.get("independent_variable")
                == "write-side CS framing for CASET, RASET, RAMWR, and pixel payload",
                v2_experiment.get("baseline", {}).get("readback_observer")
                == v2_experiment.get("fault", {}).get("readback_observer")
                == v2_experiment.get("fixed", {}).get("readback_observer")
                == "historical SIO bitbang RAMRD",
                v2_oracle.get("frozen_before_v2_implementation") is True,
                len(v2_oracle.get("solid_fills", [])) == 5,
                all(
                    solid.get("mismatches") == 0
                    for solid in v2_oracle.get("solid_fills", [])
                ),
                v2_oracle.get("pattern", {}).get("observed_rgb565")
                == ["f800", "f800", "f800", "f800"],
                v2_oracle.get("pattern", {}).get("mismatches") == 3,
                v2_oracle.get("post_hoc_oracle_change_allowed") is False,
                v2_contract.get("hardware_path", {}).get("primary") == "uf2loader",
                v2_contract.get("hardware_path", {}).get("bootsel_required") is False,
                v2_contract.get("ci_policy", {}).get(
                    "local_validation_only_during_development"
                )
                is True,
                v2_baseline.get("schema_version") == 1,
                v2_baseline.get("record_id") == "next3-v2-a1-20260810-01",
                v2_baseline.get("contract_id")
                == "next3-lcd-cs-fault-v2-predesign-20260810",
                v2_baseline.get("stage")
                == "baseline_emulator_pass_hardware_pending",
                v2_baseline.get("firmware", {}).get("commit")
                == v2_progress.get("implementation_commit"),
                v2_baseline.get("firmware", {}).get("bin_sha256")
                == v2_progress.get("bin_sha256"),
                v2_baseline.get("firmware", {}).get("uf2_sha256")
                == v2_progress.get("uf2_sha256"),
                v2_baseline.get("firmware", {}).get("clean_clone_reproducible") is True,
                v2_baseline.get("emulator", {}).get("backend_commit")
                == v2_progress.get("emulator_backend_commit"),
                v2_baseline.get("emulator", {}).get("backend_dirty") is False,
                v2_baseline.get("emulator", {}).get("verdict") == "pass",
                v2_baseline.get("emulator", {}).get("solid_fills") == "pass",
                v2_baseline.get("emulator", {}).get("pattern") == "pass",
                v2_baseline.get("emulator", {}).get("pattern_mismatches") == 0,
                v2_baseline.get("emulator", {}).get("exception") is None,
                v2_baseline.get("emulator", {}).get("unsupported_mmio_count") == 0,
                v2_baseline.get("variant_b_non_regression", {}).get("result") == "pass",
                v2_baseline.get("hardware", {}).get("path") == "uf2loader",
                v2_baseline.get("hardware", {}).get("result") == "pending",
                v2_baseline.get("hardware", {}).get("bootsel_required") is False,
                v2_baseline.get("negative_kpi_effect", {}).get(
                    "hardware_confirmed_negative_cases_delta"
                )
                == 0,
                v2_hardware.get("schema_version") == 1,
                v2_hardware.get("record_id") == "next3-v2-a1-hardware-20260810-01",
                v2_hardware.get("result") == "pass",
                v2_hardware.get("source", {}).get("commit")
                == v2_progress.get("implementation_commit"),
                v2_hardware.get("artifact", {}).get("bin_sha256")
                == v2_progress.get("bin_sha256"),
                v2_hardware.get("artifact", {}).get("uf2_sha256")
                == v2_progress.get("uf2_sha256"),
                v2_hardware.get("deployment", {}).get("path") == "uf2loader",
                v2_hardware.get("deployment", {}).get("bootsel_used") is False,
                v2_hardware.get("physical_run", {}).get("lcd", {}).get(
                    "pattern_mismatches"
                )
                == 0,
                v2_hardware.get("physical_run", {}).get("evidence_marker_count") == 14,
                v2_hardware.get("correlation", {}).get("hardware_correlation_completed")
                is True,
                v2_hardware.get("correlation", {}).get("emulator_result") == "pass",
                v2_hardware.get("correlation", {}).get("hardware_result") == "pass",
                v2_hardware.get("correlation", {}).get(
                    "emulator_pass_hardware_fail_count"
                )
                == 0,
                v2_hardware.get("gate", {}).get("fault_b_implementation_allowed") is True,
                v2_hardware.get("artifacts", {}).get("uart_log", {}).get("sha256")
                == expected_hashes["v2_hardware_uart"],
                v2_hardware.get("artifacts", {}).get("final_photo", {}).get("sha256")
                == expected_hashes["v2_hardware_photo"],
                v2_hardware.get("artifacts", {}).get("final_photo", {}).get(
                    "decoded_rgb_sha256"
                )
                == "6d015ee50b880a604556c5abfdbfba17e9b69ba45b10208dc02a1a48a266e3a1",
                v2_fault.get("schema_version") == 1,
                v2_fault.get("record_id") == "next3-v2-b-20260810-01",
                v2_fault.get("contract_id")
                == "next3-lcd-cs-fault-v2-predesign-20260810",
                v2_fault.get("stage") == "fault_artifact_frozen_hardware_pending",
                v2_fault.get("classification") == "pending_hardware_oracle",
                v2_fault.get("baseline", {}).get("hardware_record_sha256")
                == expected_hashes["v2_hardware"],
                v2_fault.get("fault_source", {}).get("commit")
                == v2_fault_progress.get("implementation_commit"),
                v2_fault.get("fault_source", {}).get("changed_paths_from_a1")
                == [
                    "CMakeLists.txt",
                    "app/main.cpp",
                    "bsp/vendor/lcd_hwspi_rgb888.cpp",
                ],
                v2_fault.get("fault_source", {}).get("change_budget_audit", {}).get(
                    "result"
                )
                == "pass",
                v2_fault.get("fault_source", {}).get("change_budget_audit", {}).get(
                    "readback_observer_changed"
                )
                is False,
                v2_fault.get("fault_injection", {}).get("observer_frozen_from_a1")
                is True,
                v2_fault.get("artifact", {}).get("bin_sha256")
                == v2_fault_progress.get("bin_sha256"),
                v2_fault.get("artifact", {}).get("uf2_sha256")
                == v2_fault_progress.get("uf2_sha256"),
                v2_fault.get("artifact", {}).get("clean_clone_reproducible") is True,
                v2_fault.get("artifact", {}).get("source_bundle_sha256")
                == expected_hashes["v2_fault_bundle"],
                v2_fault.get("frozen_hardware_oracle", {}).get(
                    "pattern_observed_rgb565"
                )
                == ["f800", "f800", "f800", "f800"],
                v2_fault.get("frozen_hardware_oracle", {}).get("pattern_mismatches")
                == 3,
                v2_fault.get("frozen_hardware_oracle", {}).get("app_status") == "fail",
                v2_fault.get("frozen_hardware_oracle", {}).get("sd_status") == "pass",
                v2_fault.get("frozen_hardware_oracle", {}).get(
                    "post_hoc_change_allowed"
                )
                is False,
                v2_fault.get("hardware", {}).get("path") == "uf2loader",
                v2_fault.get("hardware", {}).get("bootsel_required") is False,
                v2_fault.get("hardware", {}).get("result") == "pending",
                v2_fault.get("emulator", {}).get("result") == "not_run_by_contract",
                v2_fault.get("emulator", {}).get("backend_commit_reserved_for_first_run")
                == "4a90864816ef58286f2b292df0e7fe44fbcd4809",
                v2_fault.get("emulator", {}).get("run_allowed") is False,
                v2_fault.get("negative_kpi_effect", {}).get(
                    "hardware_confirmed_negative_cases_delta"
                )
                == 0,
                v2_fault.get("procedure") == "PROCEDURE.md",
                v2_fault.get("next_action").startswith("run the exact UF2 through uf2loader"),
                v2_fault_hardware.get("schema_version") == 1,
                v2_fault_hardware.get("record_id")
                == "next3-v2-b-hardware-attempt-20260810-01",
                v2_fault_hardware.get("contract_id")
                == "next3-negative-conformance-v1-20260810",
                v2_fault_hardware.get("status") == "hardware_observed",
                v2_fault_hardware.get("classification") == "inconclusive",
                v2_fault_hardware.get("artifact_audit", {}).get("source_commit")
                == v2_fault_progress.get("implementation_commit"),
                v2_fault_hardware.get("artifact_audit", {}).get("bin_sha256")
                == v2_fault_progress.get("bin_sha256"),
                v2_fault_hardware.get("artifact_audit", {}).get("uf2_sha256")
                == v2_fault_progress.get("uf2_sha256"),
                v2_fault_hardware.get("artifact_audit", {}).get(
                    "same_build_bin_and_uf2"
                )
                is True,
                v2_fault_hardware.get("defect_oracle", {}).get(
                    "frozen_before_emulator_run"
                )
                is True,
                v2_fault_hardware.get("hardware_observation", {}).get("status")
                == "complete",
                v2_fault_hardware.get("hardware_observation", {}).get("result")
                == "fail",
                len(
                    v2_fault_hardware.get("hardware_observation", {}).get(
                        "evidence", []
                    )
                )
                == 8,
                v2_fault_hardware.get("emulator_observation", {}).get("status")
                == "pending",
                v2_fault_hardware.get("emulator_observation", {}).get("result")
                == "pending",
                v2_fault_hardware.get("reason_match", {}).get("status") == "mismatch",
                v2_fault_hardware.get("reason_match", {}).get("emulator_reason") is None,
                v2_fault_hardware.get("kpi_effect")
                == {
                    "negative_denominator_delta": 0,
                    "correct_detection_delta": 0,
                    "false_accept_delta": 0,
                },
                v2_gap_analysis.get("schema_version") == 1,
                v2_gap_analysis.get("record_id")
                == "next3-v2-gap-analysis-20260810-01",
                v2_gap_analysis.get("stage")
                == "post_hardware_source_gap_analysis",
                v2_gap_analysis.get("inputs", {}).get("historical_source_commit")
                == "5b12a7cbff45a928c440a70a4e3a77750c1daa13",
                v2_gap_analysis.get("inputs", {}).get("v2_fault_source_commit")
                == v2_fault_progress.get("implementation_commit"),
                v2_gap_analysis.get("inputs", {}).get("v2_hardware_record_sha256")
                == expected_hashes["v2_fault_hardware"],
                v2_gap_analysis.get("ranked_remaining_variables", [{}])[0].get(
                    "variable"
                )
                == "160x160 fill tiling and resulting window/CS boundary sequence",
                v2_gap_analysis.get("decision", {}).get("v2_classification")
                == "inconclusive",
                v2_gap_analysis.get("decision", {}).get("v2_emulator_run_allowed")
                is False,
                v2_gap_analysis.get("decision", {}).get(
                    "continue_v2_by_combining_uncontrolled_changes"
                )
                is False,
                v2_gap_analysis.get("decision", {}).get("next_candidate_status")
                == "design_only_not_implemented",
                snapshot_valid(
                    v2_fault_hardware_kpi,
                    candidates=3,
                    audit_failures=1,
                    inconclusive=2,
                    records=3,
                    positive_count=6,
                ),
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
                    pre_a1, candidates=2, audit_failures=1, inconclusive=1, records=2
                ),
                snapshot_valid(
                    sd_crc_fault_first_kpi,
                    candidates=4,
                    audit_failures=1,
                    inconclusive=2,
                    records=4,
                    positive_count=7,
                    hardware_cases=1,
                    correct_detections=0,
                    false_accepts=1,
                ),
                snapshot_valid(
                    current,
                    candidates=4,
                    audit_failures=1,
                    inconclusive=2,
                    records=4,
                    positive_count=7,
                    hardware_cases=1,
                    correct_detections=1,
                    false_accepts=0,
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
            positive_correlations=current.get("positive_correlations", {}).get(
                "completed_count"
            ),
            negative_denominator=current.get("rates", {}).get("denominator"),
            rate_state=current.get("rates", {}).get("state"),
            candidates_audited=current.get("negative_conformance", {}).get(
                "candidates_audited"
            ),
            first_candidate_classification=audit.get("classification"),
            explicit_fault_status=fault_hardware.get("status"),
            explicit_fault_classification=fault_hardware.get("classification"),
            inconclusive_cases=current.get("negative_conformance", {}).get(
                "inconclusive_cases"
            ),
            correct_detections=current.get("negative_conformance", {}).get(
                "correct_detections"
            ),
            false_accepts=current.get("negative_conformance", {}).get(
                "false_accepts"
            ),
            false_accept_rate=current.get("rates", {}).get("false_accept_rate"),
            emulator_first_run=sd_crc_fault_first.get("emulator_observation", {}).get(
                "status"
            ),
            v2_contract_id=v2_contract.get("contract_id"),
            v2_status=v2_contract.get("status"),
            v2_fault_hardware_status=v2_fault_hardware.get("status"),
            v2_fault_classification=v2_fault_hardware.get("classification"),
            v2_next_step="NEXT-3_complete",
            v2_top_remaining_variable=v2_post_hardware.get(
                "highest_ranked_remaining_variable"
            ),
            v2_emulator_run_allowed=False,
            sd_crc_contract_id=sd_crc_contract.get("contract_id"),
            sd_crc_status=sd_crc_contract.get("status"),
            sd_crc_required_hardware_runs=sd_crc_contract.get(
                "human_operations", {}
            ).get("required_hardware_runs"),
            sd_crc_fault_emulator_run_allowed=sd_crc_fault_progress.get(
                "emulator_run_allowed"
            ),
            sd_crc_fault_classification=sd_crc_fault_progress.get("classification"),
            sd_crc_backend_change_allowed=sd_crc_fault_progress.get(
                "backend_change_allowed"
            ),
            sd_crc_post_fix_backend=sd_crc_post_fix_progress.get("backend_commit"),
            sd_crc_post_fix_classification=sd_crc_post_fix_progress.get(
                "classification"
            ),
            sd_crc_a2_exact_a1=sd_crc_post_fix_progress.get(
                "a2_is_exact_a1_artifact"
            ),
            sd_crc_fault_implementation_allowed=sd_crc_progress.get(
                "fault_implementation_allowed"
            ),
            sd_crc_fault_artifact_result=sd_crc_fault.get("stage"),
            sd_crc_fault_hardware_result=sd_crc_fault_progress.get(
                "hardware_result"
            ),
            sd_crc_hardware_negative_denominator_delta=sd_crc_fault_hardware.get(
                "kpi_effect", {}
            ).get("negative_denominator_delta"),
            sd_crc_baseline_result=sd_crc_progress.get("emulator_result"),
            sd_crc_baseline_hardware_result=sd_crc_progress.get("hardware_result"),
            sd_crc_baseline_record=sd_crc_progress.get("record"),
            sd_crc_baseline_hardware_record=sd_crc_progress.get("hardware_record"),
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
                "0a65485ce1ce4a3173e8bdd2fcab0962d7136dcee4aa1074725b6c6d87d9e675",
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
