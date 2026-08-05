#!/usr/bin/env python3
"""Verify portable BSP contracts and optional hardware reference evidence."""

import argparse
import hashlib
import json
import os
import re
import shutil
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
        supported = capability.get("supported", [])
        unsupported = capability.get("unsupported", [])
        errors: List[str] = []
        if capability.get("schema_version") != 1:
            errors.append("schema_version must be 1")
        if not isinstance(backend, dict) or not backend.get("repo"):
            errors.append("backend.repo is required")
        if backend.get("execution_model") != "Serial":
            errors.append("execution_model must be Serial while it is the reference")
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
        registry = picocalc.load_firmware_registry()
        schema = load_json(root / "reference-projects/firmware-targets.schema.json")
        targets = registry["targets"]
        active = [target for target in targets if target["status"] == "active"]
        problems: List[str] = []
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            problems.append("firmware target schema is not draft 2020-12")
        if schema.get("properties", {}).get("schema_version", {}).get("const") != 2:
            problems.append("firmware target schema does not pin version 2")
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


def verify_portable(checks: List[Check], root: Path) -> None:
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
    verify_template_smoke(checks, root)
    verify_catalog(checks, root)
    verify_firmware_targets(checks, root)
    verify_hardware_validation(checks, root)
    verify_firmware_validation(checks, root)
    verify_host_backend(checks, root)
    verify_release_conditions(checks, root)
    verify_r0_contract(checks, root)


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
    args = parser.parse_args()
    mode_parts = ["portable"]
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

    try:
        root = args.project_root.resolve()
        reference_root = (
            args.reference_root.resolve()
            if args.reference_root is not None
            else root.parent
        )
        verify_portable(checks, root)
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
