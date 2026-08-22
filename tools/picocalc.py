#!/usr/bin/env python3
"""Create and build PicoCalc projects from the hardware-proven template."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from provenance import directory_sha256, git_dirty, git_head
from sd_image import (
    SdImageError,
    add_cli as add_sd_cli,
    pack_tree,
    run_cli as run_sd_cli,
)
from uf2_image import (
    add_cli as add_uf2_cli,
    run_cli as run_uf2_cli,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/rp2040-basic"
BSP = ROOT / "bsp"
CATALOG = ROOT / "reference-projects/catalog.json"
FIRMWARE_TARGETS = ROOT / "reference-projects/firmware-targets.json"
CAPABILITY = ROOT / "firmware-validation/capability.json"


def read_version(path: Path, variable: str) -> str:
    if not path.is_file():
        return "unknown"
    text = path.read_text(encoding="utf-8")
    patterns = (
        r"set\s*\(\s*" + re.escape(variable) + r"\s+\"([^\"]+)\"",
        re.escape(variable) + r"=\\?\"([A-Za-z0-9_.-]+)\\?\"",
    )
    for expression in patterns:
        match = re.search(expression, text)
        if match:
            return match.group(1)
    return "unknown"


def build_versions(
    project: Path,
    lcd_variant: Optional[str] = None,
    coexistence_test: bool = False,
) -> Tuple[str, str]:
    bsp_file = project / "bsp/CMakeLists.txt"
    if not bsp_file.is_file():
        bsp_file = ROOT / "bsp/CMakeLists.txt"
    bsp_version = read_version(bsp_file, "PICOCALC_BSP_VERSION")
    if bsp_version == "unknown":
        version_file = bsp_file.parent / "VERSION"
        if version_file.is_file():
            bsp_version = version_file.read_text(encoding="utf-8").strip()
    app_cmake = project / "CMakeLists.txt"
    app_version = read_version(app_cmake, "PICOCALC_APP_VERSION")
    # The template selects the default app sub-version in a CMake conditional,
    # so a simple regex would always return the first branch. Keep build
    # history aligned with the actual --lcd-variant selected by CMake.
    try:
        app_text = app_cmake.read_text(encoding="utf-8")
    except OSError:
        app_text = ""
    branches = re.findall(
        r"set\s*\(\s*PICOCALC_APP_VERSION\s+\"([^\"]+)\"\s*\)", app_text
    )
    if len(branches) > 1:
        marker = "psram-lcd-coexist" if coexistence_test else (lcd_variant or "pio-rgb565")
        for candidate in branches:
            # The coexistence label also contains the LCD variant (for
            # example, "pio-rgb565"). Exclude it from a normal build so the
            # build history describes the same branch CMake selected.
            if marker in candidate and (
                coexistence_test or "psram-lcd-coexist" not in candidate
            ):
                app_version = candidate
                break
    return (bsp_version, app_version)


def source_commit() -> str:
    """Return the source repository commit used to produce a copied project."""
    return git_build_identity(ROOT)


def git_build_identity(path: Path) -> str:
    """Return a short commit plus -dirty when tracked or untracked source differs."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short=12", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return "untracked"
    commit = completed.stdout.strip() if completed.returncode == 0 else ""
    if not commit:
        return "untracked"
    try:
        status = subprocess.run(
            [
                "git", "-C", str(path), "status", "--porcelain",
                "--untracked-files=normal",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return commit + "-dirty"
    dirty = status.returncode != 0 or bool(status.stdout.strip())
    return commit + ("-dirty" if dirty else "")


def project_commit(project: Path) -> str:
    """Return an app-owned commit without inheriting a parent repository."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return "untracked"
    if completed.returncode != 0 or not completed.stdout.strip():
        return "untracked"
    repository_root = Path(completed.stdout.strip()).resolve()
    if repository_root != project.resolve():
        return "untracked"
    return git_build_identity(project)


def bsp_build_identity(project: Path) -> str:
    """Use the copied BSP's pinned source identity, not this tool's current HEAD."""
    metadata_path = project / ".picocalc-project.json"
    bsp_dir = project / "bsp"
    if not bsp_dir.is_dir():
        # The checked-in source template resolves the canonical ROOT/bsp and
        # legitimately uses this source repository's identity.
        return source_commit()
    if not metadata_path.is_file():
        # A copied/foreign BSP without generated provenance must never inherit
        # the picocalc_emu checkout used to invoke this tool.
        return "untracked"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict) or metadata.get("schema_version") != 2:
            raise ValueError("project metadata schema_version must be 2")
        bsp = metadata["provenance"]["bsp"]
        commit = bsp["source_commit"]
        expected_tree = bsp["tree_sha256"]
    except (OSError, UnicodeError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("BSP provenance is unreadable") from error
    if not is_git_commit(commit) or not is_sha256(expected_tree):
        raise ValueError("BSP provenance has an invalid commit or tree SHA-256")
    dirty = directory_sha256(bsp_dir) != expected_tree
    return commit[:12] + ("-dirty" if dirty else "")


def verify_project_provenance(project: Path) -> int:
    """Fail unless a generated project's copied BSP matches its pinned tree."""
    project = project.resolve()
    metadata = project / ".picocalc-project.json"
    bsp_dir = project / "bsp"
    helper = bsp_dir / "cmake/bsp_provenance.py"
    missing = [path for path in (metadata, bsp_dir, helper) if not path.exists()]
    if missing:
        print(
            "error: generated project provenance input is missing: {}".format(
                ", ".join(str(path) for path in missing)
            ),
            file=sys.stderr,
        )
        return 2
    command = [
        sys.executable,
        str(helper),
        "--metadata",
        str(metadata),
        "--bsp",
        str(bsp_dir),
        "--require-clean",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.stdout:
        print("BSP     {}".format(completed.stdout.strip()))
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode == 0:
        print("project provenance: pass")
    elif completed.returncode == 1:
        print("project provenance: fail", file=sys.stderr)
        transients = sorted(
            path.relative_to(bsp_dir).as_posix()
            for path in bsp_dir.rglob("*")
            if path.is_file()
            and ("__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"))
        )
        if transients:
            print(
                "remove generated BSP files before retrying: {}".format(
                    ", ".join(transients)
                ),
                file=sys.stderr,
            )
    else:
        print("project provenance: cannot judge", file=sys.stderr)
    return completed.returncode


def load_build_history(path: Path) -> dict:
    if not path.is_file():
        return {"schema_version": 1, "successful_builds": []}
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("warning: build history is unreadable: {}".format(path), file=sys.stderr)
        return {"schema_version": 1, "successful_builds": []}
    if not isinstance(history, dict) or not isinstance(
        history.get("successful_builds"), list
    ):
        print("warning: build history has an invalid format: {}".format(path), file=sys.stderr)
        return {"schema_version": 1, "successful_builds": []}
    return history


def append_build_history(path: Path, entry: dict) -> None:
    history = load_build_history(path)
    history.setdefault("schema_version", 1)
    history.setdefault("successful_builds", []).append(entry)
    path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def valid_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
        raise argparse.ArgumentTypeError(
            "name must start with a letter and contain only letters, digits, _ or -"
        )
    return value


def valid_run_id(value: str) -> str:
    """Validate the diagnostic ID passed to the firmware runner."""
    if not value:
        raise argparse.ArgumentTypeError("run id must not be empty")
    if len(value) > 64:
        raise argparse.ArgumentTypeError("run id must be at most 64 ASCII characters")
    if not value.isascii() or not all(
        character.isalnum() or character in "._:-" for character in value
    ):
        raise argparse.ArgumentTypeError(
            "run id may contain only ASCII letters, digits, '.', '_', ':' and '-'"
        )
    return value


def positive_int(value: str) -> int:
    """Parse a strictly positive integer CLI value."""
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    if number > (2**64 - 1):
        raise argparse.ArgumentTypeError("must fit in an unsigned 64-bit integer")
    return number


def create_project(name: str, output: Path) -> int:
    destination = output.resolve()
    if destination.exists():
        print("error: destination already exists: {}".format(destination), file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The checked-in template may contain a local build directory and its
    # historical build ledger. Neither belongs in a generated project: the
    # former carries an absolute CMakeCache path and the latter contains UF2
    # hashes from unrelated template builds.
    shutil.copytree(
        TEMPLATE,
        destination,
        ignore=shutil.ignore_patterns("build", ".picocalc-build-history.json"),
    )
    shutil.copytree(BSP, destination / "bsp")
    metadata = destination / ".picocalc-project.json"
    with metadata.open("r", encoding="utf-8") as source:
        project_metadata = json.load(source)
    project_metadata["project_name"] = name
    bsp_version = (BSP / "VERSION").read_text(encoding="utf-8").strip()
    source_commit = git_head(ROOT)
    project_metadata["bsp_version"] = bsp_version
    provenance = project_metadata["provenance"]
    provenance["generator"]["commit"] = source_commit
    provenance["generator"]["dirty"] = git_dirty(ROOT)
    provenance["bsp"]["version"] = bsp_version
    provenance["bsp"]["source_commit"] = source_commit
    provenance["bsp"]["source_dirty"] = git_dirty(ROOT, "bsp")
    provenance["bsp"]["tree_sha256"] = directory_sha256(BSP)
    with metadata.open("w", encoding="utf-8") as destination_file:
        json.dump(project_metadata, destination_file, ensure_ascii=False, indent=2)
        destination_file.write("\n")
    print("created {}".format(destination))
    print("edit    {}/app/main.cpp".format(destination))
    print("build   {} build --project {}".format(Path(__file__).name, destination))
    return 0


def find_sdk(requested: Optional[str]) -> Optional[Path]:
    candidate_value = requested or os.environ.get("PICO_SDK_PATH")
    if candidate_value:
        candidate = Path(candidate_value).expanduser()
        if (candidate / "external/pico_sdk_import.cmake").is_file():
            return candidate.resolve()
    return None


def find_picotool_dir(requested: Optional[str]) -> Optional[Path]:
    candidate_value = requested or os.environ.get("PICOTOOL_DIR")
    if candidate_value:
        candidate = Path(candidate_value).expanduser()
        if (candidate / "picotoolConfig.cmake").is_file():
            return candidate.resolve()
        return None

    executable = shutil.which("picotool")
    if executable:
        prefix = Path(executable).resolve().parent.parent
        candidate = prefix / "lib/cmake/picotool"
        if (candidate / "picotoolConfig.cmake").is_file():
            return candidate
    return None


def build_mode_definitions(
    coexistence_test: bool,
    diagnostic_mode: bool,
    supports_diagnostic: bool,
    hardware_validation_mode: bool = False,
    supports_hardware_validation: bool = False,
) -> list[str]:
    """Return explicit cache definitions so an old build cannot change mode."""
    definitions = [
        "-DPICOCALC_PSRAM_LCD_COEXIST_TEST={}".format(
            "ON" if coexistence_test else "OFF"
        )
    ]
    if supports_diagnostic:
        definitions.append(
            "-DPICOCALC_DIAGNOSTIC_MODE={}".format("ON" if diagnostic_mode else "OFF")
        )
    if supports_hardware_validation:
        definitions.append(
            "-DPICOCALC_HARDWARE_VALIDATION_MODE={}".format(
                "ON" if hardware_validation_mode else "OFF"
            )
        )
    return definitions


def build_project(
    project: Path,
    sdk_value: Optional[str],
    picotool_value: Optional[str],
    lcd_variant: str,
    jobs: int,
    coexistence_test: bool,
    build_timestamp_value: Optional[str] = None,
    diagnostic_mode: bool = False,
    hardware_validation_mode: bool = False,
    generator: Optional[str] = None,
) -> int:
    project = project.resolve()
    if not (project / "CMakeLists.txt").is_file():
        print("error: no CMakeLists.txt in {}".format(project), file=sys.stderr)
        return 2
    project_cmake = (project / "CMakeLists.txt").read_text(encoding="utf-8")
    supports_diagnostic = "PICOCALC_DIAGNOSTIC_MODE" in project_cmake
    supports_hardware_validation = "PICOCALC_HARDWARE_VALIDATION_MODE" in project_cmake
    if diagnostic_mode and not supports_diagnostic:
        print(
            "error: --diagnostic-mode is not supported by {}".format(project),
            file=sys.stderr,
        )
        return 2
    if hardware_validation_mode and not supports_hardware_validation:
        print(
            "error: --hardware-validation-mode is not supported by {}".format(project),
            file=sys.stderr,
        )
        return 2
    if diagnostic_mode and hardware_validation_mode:
        print(
            "error: --diagnostic-mode and --hardware-validation-mode are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    sdk = find_sdk(sdk_value)
    if sdk is None:
        print(
            "error: Pico SDK not found; use --sdk or set PICO_SDK_PATH",
            file=sys.stderr,
        )
        return 2
    if picotool_value and find_picotool_dir(picotool_value) is None:
        print(
            "error: invalid picotool CMake directory: {}".format(picotool_value),
            file=sys.stderr,
        )
        return 2
    try:
        bsp_identity = bsp_build_identity(project)
    except ValueError as error:
        print("error: {}".format(error), file=sys.stderr)
        return 2

    build_dir = project / "build"
    build_timestamp = build_timestamp_value or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", build_timestamp):
        print(
            "error: --build-timestamp must be UTC ISO-8601 YYYY-MM-DDTHH:MM:SSZ",
            file=sys.stderr,
        )
        return 2
    bsp_version, app_version = build_versions(project, lcd_variant, coexistence_test)
    # Keep the history outside build/ so a clean rebuild does not erase the
    # version-reuse warning evidence.
    history_path = project / ".picocalc-build-history.json"
    history = load_build_history(history_path)
    previous = [
        item
        for item in history["successful_builds"]
        if item.get("bsp_version") == bsp_version
        and item.get("app_version") == app_version
        and item.get("lcd_variant") == lcd_variant
        and item.get("coexistence_test", False) == coexistence_test
        and item.get("diagnostic_mode", False) == diagnostic_mode
        and item.get("hardware_validation_mode", False) == hardware_validation_mode
    ]
    if previous:
        print(
            "WARNING: regenerating same-version build #{}: bsp={} app={} variant={}.".format(
                len(previous) + 1, bsp_version, app_version, lcd_variant
            ),
            file=sys.stderr,
        )
        print(
            "         The UF2 will be generated. Increment the version only for a new release.",
            file=sys.stderr,
        )
    build_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PICO_SDK_PATH"] = str(sdk)
    # Keep the artifact a function of its inputs. The Pico SDK stamps
    # __DATE__ into the binary through PICO_PROGRAM_BUILD_DATE, so two
    # builds of identical source on different days produce different
    # hashes -- which defeats --build-timestamp and makes an evidence
    # build unreproducible the moment the day rolls over. The define is
    # a C preprocessor macro, not a CMake variable, so passing it with
    # -D does nothing but warn; it has to arrive through the compiler
    # flags. Appending to CFLAGS/CXXFLAGS is safe because CMake
    # concatenates them onto the toolchain's own flags, whereas setting
    # CMAKE_C_FLAGS would replace the architecture flags and break the
    # build outright.
    for variable in ("CFLAGS", "CXXFLAGS"):
        existing = environment.get(variable, "")
        flag = "-DPICO_NO_BI_PROGRAM_BUILD_DATE=1"
        if flag not in existing:
            environment[variable] = (existing + " " + flag).strip()
    configure = ["cmake"]
    if generator is not None:
        configure.extend(["-G", generator])
    configure.extend([
        "-S",
        str(project),
        "-B",
        str(build_dir),
        "-DPICO_BOARD=pico",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DPICOCALC_BUILD_TIMESTAMP={}".format(build_timestamp),
        "-DPICOCALC_BSP_GIT={}".format(bsp_identity),
        "-DPICOCALC_APP_GIT={}".format(project_commit(project)),
        "-DPICOCALC_LCD_VARIANT={}".format(lcd_variant),
    ])
    configure.extend(
        build_mode_definitions(
            coexistence_test,
            diagnostic_mode,
            supports_diagnostic,
            hardware_validation_mode,
            supports_hardware_validation,
        )
    )
    picotool_config = find_picotool_dir(picotool_value)
    if picotool_config is not None:
        configure.append("-Dpicotool_DIR={}".format(picotool_config))
    print("SDK     {}".format(sdk))
    print("LCD     {}".format(lcd_variant))
    mode = "psram-lcd-coexist" if coexistence_test else "standard"
    print(
        "MODE    {} diagnostic={} hardware-validation={}".format(
            mode,
            "on" if diagnostic_mode else "off",
            "on" if hardware_validation_mode else "off",
        )
    )
    if picotool_config is not None:
        print("picotool {}".format(picotool_config))
    if subprocess.run(configure, env=environment).returncode != 0:
        return 1
    built = subprocess.run(
        ["cmake", "--build", str(build_dir), "-j", str(jobs)],
        env=environment,
    )
    if built.returncode != 0:
        return built.returncode
    artifact_name = "picocalc_app"
    cache_file = build_dir / "CMakeCache.txt"
    if cache_file.is_file():
        cache_text = cache_file.read_text(encoding="utf-8")
        match = re.search(
            r"^PICOCALC_UF2_NAME(?::[^=]+)?=(.+)$", cache_text, re.MULTILINE
        )
        if match:
            artifact_name = match.group(1).strip()
    uf2 = build_dir / (artifact_name + ".uf2")
    if not uf2.is_file():
        print(
            "error: build succeeded but UF2 was not generated: {}".format(uf2),
            file=sys.stderr,
        )
        return 1
    digest = hashlib.sha256(uf2.read_bytes()).hexdigest()
    binary = build_dir / (artifact_name + ".bin")
    elf = build_dir / (artifact_name + ".elf")
    append_build_history(
        history_path,
        {
            "built_at": build_timestamp,
            "bsp_version": bsp_version,
            "app_version": app_version,
            "lcd_variant": lcd_variant,
            "coexistence_test": coexistence_test,
            "diagnostic_mode": diagnostic_mode,
            "hardware_validation_mode": hardware_validation_mode,
            "uf2": str(uf2),
            "uf2_sha256": digest,
            "bin_sha256": (
                hashlib.sha256(binary.read_bytes()).hexdigest() if binary.is_file() else None
            ),
            "elf_sha256": (
                hashlib.sha256(elf.read_bytes()).hexdigest() if elf.is_file() else None
            ),
            "app_git": project_commit(project),
            "bsp_git": bsp_identity,
            "generator": generator or os.environ.get("CMAKE_GENERATOR", "default"),
        },
    )
    print("PRODUCT {}".format(artifact_name))
    print("UF2     {}".format(uf2))
    print("SHA256  {}".format(digest))
    print("history {}".format(history_path))
    return 0


def resolve_backend(explicit: Optional[Path]) -> Optional[Path]:
    """Locate the picoem-picocalc checkout.

    The firmware backend is a separate repository pinned by commit, never
    vendored here. Order: explicit flag, PICOEM_PICOCALC_DIR, then a
    sibling checkout next to this repository.
    """
    if explicit is not None:
        return explicit
    from_env = os.environ.get("PICOEM_PICOCALC_DIR")
    if from_env:
        return Path(from_env)
    sibling = ROOT.parent / "picoem-picocalc"
    return sibling if sibling.is_dir() else None


def load_firmware_target(target_id: str) -> Optional[dict]:
    document = load_firmware_registry()
    for target in document["targets"]:
        if target.get("id") == target_id:
            return target
    return None


def load_firmware_registry(path: Optional[Path] = None) -> dict:
    """Load the versioned registry and reject incomplete conformance contracts."""
    registry_path = path if path is not None else FIRMWARE_TARGETS
    if not registry_path.is_file():
        raise ValueError("firmware target registry is missing: {}".format(registry_path))
    with registry_path.open("r", encoding="utf-8") as source:
        document = json.load(source)
    if not isinstance(document, dict):
        raise ValueError("firmware target registry must be a JSON object")
    if document.get("schema_version") != 3:
        raise ValueError("firmware target registry schema_version must be 3")
    if not isinstance(document.get("policy"), str) or not document["policy"]:
        raise ValueError("firmware target registry needs a non-empty policy")
    targets = document.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("firmware target registry needs a non-empty targets array")
    ids = set()
    for index, target in enumerate(targets):
        where = "targets[{}]".format(index)
        if not isinstance(target, dict):
            raise ValueError("{} must be an object".format(where))
        target_id = target.get("id")
        if not isinstance(target_id, str) or not target_id:
            raise ValueError("{}.id must be a non-empty string".format(where))
        if target_id in ids:
            raise ValueError("duplicate firmware target id '{}'".format(target_id))
        ids.add(target_id)
        if type(target.get("revision")) is not int or target["revision"] <= 0:
            raise ValueError("{}.revision must be a positive integer".format(where))
        supersedes = target.get("supersedes")
        if supersedes is not None and (
            not isinstance(supersedes, str) or not supersedes or supersedes == target_id
        ):
            raise ValueError("{}.supersedes must name another target or be null".format(where))
        if target.get("status") not in ("active", "pending-revalidation"):
            raise ValueError("{}.status must be active or pending-revalidation".format(where))
        for field in (
            "source", "toolchain", "build", "artifacts", "backend", "runner", "acceptance"
        ):
            if not isinstance(target.get(field), dict):
                raise ValueError("{}.{} must be an object".format(where, field))
        for field in ("source", "toolchain", "build"):
            if not target[field]:
                raise ValueError("{}.{} must not be empty".format(where, field))
        basename = target["artifacts"].get("bin_basename")
        if not isinstance(basename, str) or not basename:
            raise ValueError("{}.artifacts.bin_basename must be non-empty".format(where))
        digest = target["artifacts"].get("bin_sha256")
        if not is_sha256(digest):
            raise ValueError("{}.artifacts.bin_sha256 must be a SHA-256".format(where))
        for artifact in ("elf_sha256", "uf2_sha256"):
            if artifact in target["artifacts"] and not is_sha256(
                target["artifacts"][artifact]
            ):
                raise ValueError("{}.artifacts.{} must be a SHA-256".format(where, artifact))
        backend = target["backend"]
        if backend.get("repo") != "picoem-picocalc":
            raise ValueError("{}.backend.repo must be picoem-picocalc".format(where))
        if not isinstance(backend.get("branch"), str) or not backend["branch"]:
            raise ValueError("{}.backend.branch must be non-empty".format(where))
        if backend.get("report_schema") != 8:
            raise ValueError("{}.backend.report_schema must be 8".format(where))
        accepted = backend.get("accepted")
        if not is_git_commit(accepted):
            raise ValueError("{}.backend.accepted must be a full Git commit".format(where))
        runner = target["runner"]
        if runner.get("board") not in ("none", "picocalc"):
            raise ValueError("{}.runner.board is invalid".format(where))
        if runner.get("lcd_variant") not in ("hwspi-rgb888", "pio-rgb565"):
            raise ValueError("{}.runner.lcd_variant is invalid".format(where))
        if type(runner.get("cycles")) is not int or runner["cycles"] <= 0:
            raise ValueError("{}.runner.cycles must be positive".format(where))
        if type(runner.get("quantum")) is not int or runner["quantum"] <= 0:
            raise ValueError("{}.runner.quantum must be positive".format(where))
        for flag in ("psram", "keyboard"):
            if not isinstance(runner.get(flag), bool):
                raise ValueError("{}.runner.{} must be boolean".format(where, flag))
        audio_sink = runner.get("audio_sink")
        if audio_sink is not None:
            if not isinstance(audio_sink, dict):
                raise ValueError("{}.runner.audio_sink must be an object".format(where))
            if set(audio_sink) != {"expected_count", "expected_sha256"}:
                raise ValueError(
                    "{}.runner.audio_sink must contain expected_count and expected_sha256".format(
                        where
                    )
                )
            if (
                type(audio_sink.get("expected_count")) is not int
                or audio_sink["expected_count"] <= 0
            ):
                raise ValueError(
                    "{}.runner.audio_sink.expected_count must be a positive integer".format(
                        where
                    )
                )
            if not is_sha256(audio_sink.get("expected_sha256")):
                raise ValueError(
                    "{}.runner.audio_sink.expected_sha256 must be a SHA-256".format(where)
                )
        stop_pc = runner.get("stop_pc")
        if stop_pc is not None and not isinstance(stop_pc, str):
            raise ValueError("{}.runner.stop_pc must be a string or null".format(where))
        verify_range = runner.get("psram_verify_range")
        if verify_range is not None and (
            not isinstance(verify_range, str) or not verify_range or not runner["psram"]
        ):
            raise ValueError(
                "{}.runner.psram_verify_range needs attached PSRAM and a non-empty string".format(
                    where
                )
            )
        keys = runner.get("keys")
        if keys is not None and (not isinstance(keys, str) or not runner["keyboard"]):
            raise ValueError(
                "{}.runner.keys needs an attached keyboard and a string or null".format(where)
            )
        sd_contract = runner.get("sd")
        if (
            not isinstance(sd_contract, dict)
            or not isinstance(sd_contract.get("attached"), bool)
            or sd_contract.get("format") not in ("fat32", "fat16")
        ):
            raise ValueError("{}.runner.sd must contain attached and format".format(where))
        scenario = target.get("scenario")
        if scenario is not None:
            if (
                not isinstance(scenario, dict)
                or not isinstance(scenario.get("path"), str)
                or not scenario["path"]
            ):
                raise ValueError("{}.scenario must be null or contain path".format(where))
            scenario_path = Path(scenario["path"])
            if scenario_path.is_absolute() or ".." in scenario_path.parts:
                raise ValueError("{}.scenario.path must stay inside the repository".format(where))
            if not is_sha256(scenario.get("sha256")):
                raise ValueError("{}.scenario.sha256 must be a SHA-256".format(where))
        acceptance = target["acceptance"]
        if acceptance.get("expected_stop_reason") not in (
            "cycle_limit", "pc_match", "scenario_done"
        ):
            raise ValueError("{}.acceptance.expected_stop_reason is invalid".format(where))
        if acceptance["expected_stop_reason"] == "scenario_done" and scenario is None:
            raise ValueError("{}.scenario_done needs a scenario".format(where))
        if acceptance["expected_stop_reason"] == "pc_match" and stop_pc is None:
            raise ValueError("{}.pc_match needs runner.stop_pc".format(where))
        markers = acceptance.get("required_uart_markers")
        if not isinstance(markers, list) or not markers or not all(
            isinstance(marker, str) and marker for marker in markers
        ):
            raise ValueError("{}.acceptance.required_uart_markers needs non-empty strings".format(where))
        checks = acceptance.get("report_checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError("{}.acceptance.report_checks must be non-empty".format(where))
        for digest_field in ("normalized_report_sha256", "timeline_sha256"):
            if digest_field in acceptance and not is_sha256(acceptance[digest_field]):
                raise ValueError(
                    "{}.acceptance.{} must be a SHA-256".format(where, digest_field)
                )
        if "timeline_sha256" in acceptance and scenario is None:
            raise ValueError("{}.acceptance.timeline_sha256 needs a scenario".format(where))
        for check_index, check in enumerate(checks):
            check_where = "{}.acceptance.report_checks[{}]".format(where, check_index)
            if (
                not isinstance(check, dict)
                or not isinstance(check.get("path"), str)
                or not check["path"]
            ):
                raise ValueError("{} needs a path".format(check_where))
            if check.get("op") not in ("eq", "length_eq") or "value" not in check:
                raise ValueError("{} needs op eq|length_eq and value".format(check_where))
            if check["op"] == "length_eq" and (
                type(check["value"]) is not int or check["value"] < 0
            ):
                raise ValueError("{} length_eq value must be a non-negative integer".format(
                    check_where
                ))
        validation = target.get("validation")
        if not isinstance(validation, dict):
            raise ValueError("{}.validation must be an object".format(where))
        if set(validation) != {"record", "sha256"}:
            raise ValueError("{}.validation must contain only record and sha256".format(where))
        record = validation.get("record")
        if not isinstance(record, str) or not record:
            raise ValueError("{}.validation.record must be non-empty".format(where))
        record_path = Path(record)
        if record_path.is_absolute() or ".." in record_path.parts:
            raise ValueError("{}.validation.record must stay inside the repository".format(where))
        if not is_sha256(validation.get("sha256")):
            raise ValueError("{}.validation.sha256 must be a SHA-256".format(where))
    targets_by_id = {target["id"]: target for target in targets}
    for index, target in enumerate(targets):
        supersedes = target.get("supersedes")
        if supersedes is not None and supersedes not in ids:
            raise ValueError("targets[{}].supersedes names an unknown target".format(index))
        if supersedes is not None and target["revision"] <= targets_by_id[supersedes]["revision"]:
            raise ValueError("targets[{}].revision must increase over supersedes".format(index))
    return document


def is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def normalized_json_sha256(value: object) -> str:
    """Hash compact UTF-8 JSON with recursively sorted object keys and a final LF."""
    normalized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def firmware_target_contract_sha256(target: dict) -> str:
    """Hash a target contract without its external validation attestation."""
    contract = {key: value for key, value in target.items() if key != "validation"}
    return normalized_json_sha256(contract)


def is_git_commit(value) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        char in "0123456789abcdef" for char in value
    )


def report_value(report: object, path: str):
    current = report
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            raise KeyError(path)
        current = current[component]
    return current


def check_report(report: dict, checks: List[dict]) -> List[str]:
    failures: List[str] = []
    for check in checks:
        path = check["path"]
        try:
            actual = report_value(report, path)
        except KeyError:
            failures.append("{} is missing".format(path))
            continue
        expected = check["value"]
        if check["op"] == "length_eq":
            if not isinstance(actual, (list, dict, str)):
                failures.append("{} has no length".format(path))
            elif len(actual) != expected:
                failures.append("{} length expected {} but got {}".format(
                    path, expected, len(actual)
                ))
        elif check["op"] in ("ge", "le"):
            if type(actual) not in (int, float) or type(expected) not in (int, float):
                failures.append("{} is not numeric".format(path))
            elif check["op"] == "ge" and actual < expected:
                failures.append("{} expected >= {} but got {}".format(
                    path, expected, actual
                ))
            elif check["op"] == "le" and actual > expected:
                failures.append("{} expected <= {} but got {}".format(
                    path, expected, actual
                ))
        elif type(actual) is not type(expected) or actual != expected:
            failures.append("{} expected {!r} but got {!r}".format(
                path, expected, actual
            ))
    return failures


def load_project_quality_contract(path: Path) -> dict:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("quality contract is unreadable: {}".format(error)) from error
    required_keys = {
        "schema_version",
        "contract_id",
        "report_schema",
        "required_capabilities",
        "report_checks",
    }
    if not isinstance(contract, dict) or set(contract) != required_keys:
        raise ValueError("quality contract fields do not match schema 1")
    if contract["schema_version"] not in (1, 2, 3) or contract["report_schema"] != 8:
        raise ValueError("quality contract requires schema 1/2/3 and runner report schema 8")
    if not isinstance(contract["contract_id"], str) or not contract["contract_id"]:
        raise ValueError("quality contract_id must be a non-empty string")
    capabilities = contract["required_capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != {"audio_sink"}:
        raise ValueError("required_capabilities must contain exactly audio_sink")
    audio = capabilities["audio_sink"]
    expected_audio_fields = {"expected_count", "expected_sha256"}
    if contract["schema_version"] in (2, 3):
        expected_audio_fields.add("quality")
    if not isinstance(audio, dict) or set(audio) != expected_audio_fields:
        raise ValueError(
            "audio_sink fields do not match quality contract schema {}".format(
                contract["schema_version"]
            )
        )
    if type(audio["expected_count"]) is not int or audio["expected_count"] <= 0:
        raise ValueError("audio_sink.expected_count must be a positive integer")
    if not is_sha256(audio["expected_sha256"]):
        raise ValueError("audio_sink.expected_sha256 must be a SHA-256")
    if contract["schema_version"] in (2, 3):
        quality = audio["quality"]
        minimum_field = (
            "minimum_max_window_rms"
            if contract["schema_version"] == 2
            else "advisory_minimum_max_window_rms"
        )
        quality_fields = {
            minimum_field,
            "maximum_rail_sample_ratio_ppm",
            "maximum_consecutive_rail_frames",
        }
        if not isinstance(quality, dict) or set(quality) != quality_fields:
            raise ValueError("audio_sink.quality fields are invalid")
        minimum_rms = quality[minimum_field]
        maximum_rail_ratio = quality["maximum_rail_sample_ratio_ppm"]
        maximum_rail_run = quality["maximum_consecutive_rail_frames"]
        if type(minimum_rms) is not int or not 1 <= minimum_rms <= 32768:
            raise ValueError("{} must be in 1..32768".format(minimum_field))
        if (
            type(maximum_rail_ratio) is not int
            or not 0 <= maximum_rail_ratio <= 1_000_000
        ):
            raise ValueError("maximum_rail_sample_ratio_ppm must be in 0..1000000")
        if type(maximum_rail_run) is not int or maximum_rail_run < 0:
            raise ValueError("maximum_consecutive_rail_frames must be non-negative")
    checks = contract["report_checks"]
    if not isinstance(checks, list):
        raise ValueError("report_checks must be an array")
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or set(check) != {"path", "op", "value"}:
            raise ValueError("report_checks[{}] has invalid fields".format(index))
        if not isinstance(check["path"], str) or not check["path"]:
            raise ValueError("report_checks[{}].path must be non-empty".format(index))
        if check["op"] not in ("eq", "length_eq", "ge", "le"):
            raise ValueError("report_checks[{}].op is invalid".format(index))
        if check["op"] == "length_eq" and (
            type(check["value"]) is not int or check["value"] < 0
        ):
            raise ValueError(
                "report_checks[{}].value must be a non-negative integer".format(index)
            )
        if check["op"] in ("ge", "le") and type(check["value"]) not in (int, float):
            raise ValueError("report_checks[{}].value must be numeric".format(index))
    return contract


def audio_analysis_errors(analysis: object) -> List[str]:
    """Validate the standalone schema-1/2 PWM level artifact without extra packages."""
    if not isinstance(analysis, dict):
        return ["root must be an object"]
    required = {
        "schema_version",
        "boundary",
        "interpretation",
        "backend_build",
        "firmware",
        "observation_status",
        "pcm_sha256",
        "pcm_format",
        "sample_rate_hz",
        "channel_count",
        "frame_count",
        "window_frames",
        "active_abs_threshold",
        "peak_abs_left",
        "peak_abs_right",
        "stream_rms",
        "max_window_rms",
        "dc_offset_left",
        "dc_offset_right",
        "active_frame_count",
        "active_frame_ratio_ppm",
        "rail_sample_count",
        "rail_sample_ratio_ppm",
        "max_consecutive_rail_frames",
        "out_of_range_duty_sample_count",
        "rail_interpretation",
    }
    errors: List[str] = []
    if set(analysis) != required:
        errors.append("fields do not match audio analysis schema 1/2")
    constants = {
        "boundary": "dma_to_pwm5_cc",
        "interpretation": "digital_level_only_not_speaker_loudness",
        "pcm_format": "stereo_s16le_from_pwm8_duty",
        "channel_count": 2,
        "window_frames": 1024,
        "active_abs_threshold": 512,
        "rail_interpretation": "post_quantizer_pwm_rail_usage_not_source_clip_count",
    }
    for name, expected in constants.items():
        if analysis.get(name) != expected or type(analysis.get(name)) is not type(expected):
            errors.append("{} must be {!r}".format(name, expected))
    schema_version = analysis.get("schema_version")
    if type(schema_version) is not int or schema_version not in (1, 2):
        errors.append("schema_version must be 1 or 2")
    sample_rate_hz = analysis.get("sample_rate_hz")
    if type(sample_rate_hz) is not int or sample_rate_hz < 0:
        errors.append("sample_rate_hz must be a non-negative integer")
    elif schema_version == 1 and sample_rate_hz != 48_000:
        errors.append("schema 1 sample_rate_hz must be 48000")
    backend = analysis.get("backend_build")
    if (
        not isinstance(backend, dict)
        or set(backend) != {"commit", "dirty"}
        or not is_git_commit(backend.get("commit"))
        or type(backend.get("dirty")) is not bool
    ):
        errors.append("backend_build is invalid")
    firmware = analysis.get("firmware")
    if (
        not isinstance(firmware, dict)
        or set(firmware) != {"file", "sha256"}
        or not isinstance(firmware.get("file"), str)
        or not firmware.get("file")
        or not is_sha256(firmware.get("sha256"))
    ):
        errors.append("firmware is invalid")
    if analysis.get("observation_status") not in ("inactive", "pass", "fail"):
        errors.append("observation_status is invalid")
    if not is_sha256(analysis.get("pcm_sha256")):
        errors.append("pcm_sha256 is invalid")

    ranges = {
        "frame_count": (0, None),
        "peak_abs_left": (0, 32768),
        "peak_abs_right": (0, 32768),
        "stream_rms": (0, 32768),
        "max_window_rms": (0, 32768),
        "dc_offset_left": (-32768, 32767),
        "dc_offset_right": (-32768, 32767),
        "active_frame_count": (0, None),
        "active_frame_ratio_ppm": (0, 1_000_000),
        "rail_sample_count": (0, None),
        "rail_sample_ratio_ppm": (0, 1_000_000),
        "max_consecutive_rail_frames": (0, None),
        "out_of_range_duty_sample_count": (0, None),
    }
    for name, (minimum, maximum) in ranges.items():
        value = analysis.get(name)
        if (
            type(value) is not int
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            errors.append("{} is out of range".format(name))

    frame_count = analysis.get("frame_count")
    if type(frame_count) is int and frame_count >= 0:
        if (
            type(analysis.get("active_frame_count")) is int
            and analysis["active_frame_count"] > frame_count
        ):
            errors.append("active_frame_count exceeds frame_count")
        if (
            type(analysis.get("rail_sample_count")) is int
            and analysis["rail_sample_count"] > frame_count * 2
        ):
            errors.append("rail_sample_count exceeds stereo sample count")
        if (
            type(analysis.get("max_consecutive_rail_frames")) is int
            and analysis["max_consecutive_rail_frames"] > frame_count
        ):
            errors.append("max_consecutive_rail_frames exceeds frame_count")
        active_count = analysis.get("active_frame_count")
        active_ratio = analysis.get("active_frame_ratio_ppm")
        if type(active_count) is int and type(active_ratio) is int:
            expected_active_ratio = (
                active_count * 1_000_000 // frame_count if frame_count else 0
            )
            if active_ratio != expected_active_ratio:
                errors.append("active_frame_ratio_ppm is inconsistent")
        rail_count = analysis.get("rail_sample_count")
        rail_ratio = analysis.get("rail_sample_ratio_ppm")
        if type(rail_count) is int and type(rail_ratio) is int:
            sample_count = frame_count * 2
            expected_rail_ratio = (
                rail_count * 1_000_000 // sample_count if sample_count else 0
            )
            if rail_ratio != expected_rail_ratio:
                errors.append("rail_sample_ratio_ppm is inconsistent")
    return errors


def judge_project_report(
    contract_path: Path,
    report_path: Path,
    audio_analysis_path: Optional[Path],
    json_out: Optional[Path],
) -> int:
    """Apply an explicit project audio oracle to a raw backend report."""
    try:
        contract = load_project_quality_contract(contract_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        audio_analysis = (
            json.loads(audio_analysis_path.read_text(encoding="utf-8"))
            if audio_analysis_path is not None
            else None
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print("cannot judge project report: {}".format(error), file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print("cannot judge project report: runner report must be an object", file=sys.stderr)
        return 2

    cannot_judge: List[str] = []
    failures: List[str] = []
    report_schema = report.get("schema_version")
    if report_schema != contract["report_schema"]:
        cannot_judge.append("report_schema_mismatch")

    verdict = report.get("verdict")
    verdict_status = verdict.get("status") if isinstance(verdict, dict) else None
    if verdict_status == "fail":
        failures.append("runner_verdict_fail")
    elif verdict_status == "cannot_judge":
        cannot_judge.append("runner_cannot_judge")
    elif verdict_status != "pass":
        cannot_judge.append("runner_verdict_missing")

    required_audio = contract["required_capabilities"]["audio_sink"]
    audio = report.get("audio_sink")
    observation_status = audio.get("status") if isinstance(audio, dict) else None
    oracle_present = isinstance(audio, dict) and (
        audio.get("expected_count") is not None
        and audio.get("expected_sha256") is not None
    )
    oracle_matches = isinstance(audio, dict) and (
        audio.get("expected_count") == required_audio["expected_count"]
        and audio.get("expected_sha256") == required_audio["expected_sha256"]
    )
    if not isinstance(audio, dict):
        cannot_judge.append("audio_sink_missing")
        evaluation_status = "not_evaluated"
    elif not oracle_matches:
        cannot_judge.append("audio_sink_oracle_missing_or_mismatched")
        evaluation_status = "not_evaluated"
    elif observation_status != "pass":
        failures.append("audio_sink_mismatch")
        evaluation_status = "fail"
    else:
        evaluation_status = "pass"

    quality_evaluation = "not_required"
    quality_provenance_matches: Optional[bool] = None
    advisories: List[str] = []
    if contract["schema_version"] in (2, 3):
        quality_evaluation = "not_evaluated"
        quality_failures: List[str] = []
        if not isinstance(audio_analysis, dict):
            cannot_judge.append("audio_quality_missing")
        elif audio_analysis.get("schema_version") not in (1, 2):
            cannot_judge.append("audio_quality_schema_mismatch")
        elif audio_analysis_errors(audio_analysis):
            cannot_judge.append("audio_quality_artifact_invalid")
        else:
            report_backend = report.get("backend_build")
            report_firmware = report.get("firmware")
            report_audio = report.get("audio_sink")
            analysis_backend = audio_analysis.get("backend_build")
            analysis_firmware = audio_analysis.get("firmware")
            provenance_matches = (
                isinstance(report_backend, dict)
                and isinstance(report_firmware, dict)
                and isinstance(report_audio, dict)
                and isinstance(analysis_backend, dict)
                and isinstance(analysis_firmware, dict)
                and analysis_backend.get("commit") == report_backend.get("commit")
                and analysis_backend.get("dirty") == report_backend.get("dirty")
                and analysis_firmware.get("sha256") == report_firmware.get("sha256")
                and audio_analysis.get("pcm_sha256") == report_audio.get("pcm_sha256")
                and audio_analysis.get("frame_count") == report_audio.get("dma_write_count")
            )
            quality_provenance_matches = provenance_matches
            if not provenance_matches:
                cannot_judge.append("audio_quality_provenance_mismatch")
            elif audio_analysis.get("observation_status") != "pass":
                quality_failures.append("audio_quality_observation_fail")
                quality_evaluation = "fail"
            else:
                quality = required_audio["quality"]
                metrics = (
                    "max_window_rms",
                    "rail_sample_ratio_ppm",
                    "max_consecutive_rail_frames",
                )
                if any(type(audio_analysis.get(name)) is not int for name in metrics):
                    cannot_judge.append("audio_quality_metrics_missing")
                else:
                    minimum_field = (
                        "minimum_max_window_rms"
                        if contract["schema_version"] == 2
                        else "advisory_minimum_max_window_rms"
                    )
                    if audio_analysis["max_window_rms"] < quality[minimum_field]:
                        if contract["schema_version"] == 2:
                            quality_failures.append("audio_level_too_low")
                        else:
                            advisories.append("audio_level_below_preferred_range")
                    if (
                        audio_analysis["rail_sample_ratio_ppm"]
                        > quality["maximum_rail_sample_ratio_ppm"]
                    ):
                        quality_failures.append("audio_rail_ratio_excessive")
                    if (
                        audio_analysis["max_consecutive_rail_frames"]
                        > quality["maximum_consecutive_rail_frames"]
                    ):
                        quality_failures.append("audio_sustained_rail_excessive")
                    quality_evaluation = "fail" if quality_failures else "pass"
        failures.extend(quality_failures)

    failures.extend(check_report(report, contract["report_checks"]))
    if report_schema != contract["report_schema"]:
        # An incompatible schema makes every parsed field non-authoritative.
        status = "cannot_judge"
        exit_code = 2
    elif failures:
        status = "fail"
        exit_code = 1
    elif cannot_judge:
        status = "cannot_judge"
        exit_code = 2
    else:
        status = "pass"
        exit_code = 0
    result = {
        "schema_version": 3 if contract["schema_version"] == 3 else 2,
        "contract_id": contract["contract_id"],
        "status": status,
        "reasons": failures + cannot_judge,
        "source_report": {
            "schema_version": report_schema,
            "verdict_status": verdict_status,
        },
        "capabilities": {
            "audio_sink": {
                "required": True,
                "oracle_declared": True,
                "oracle_present": oracle_present,
                "oracle_matches_contract": oracle_matches,
                "observation_status": observation_status,
                "evaluation_status": evaluation_status,
            },
            "audio_quality": {
                "required": contract["schema_version"] in (2, 3),
                "analysis_present": isinstance(audio_analysis, dict),
                "analysis_schema_version": (
                    audio_analysis.get("schema_version")
                    if isinstance(audio_analysis, dict)
                    else None
                ),
                "provenance_matches_report": quality_provenance_matches,
                "evaluation_status": quality_evaluation,
                "required_bounds": required_audio.get("quality"),
                "observed": (
                    {
                        name: audio_analysis.get(name)
                        for name in (
                            "max_window_rms",
                            "rail_sample_ratio_ppm",
                            "max_consecutive_rail_frames",
                        )
                    }
                    if isinstance(audio_analysis, dict)
                    else None
                ),
            },
        },
    }
    if contract["schema_version"] == 3:
        result["advisories"] = advisories
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(encoded, encoding="utf-8")
    print("project quality: {}".format(status))
    for reason in result["reasons"]:
        print("  {}".format(reason))
    for advisory in advisories:
        print("  advisory: {}".format(advisory))
    return exit_code


def host_test(
    build_dir: Optional[Path],
    repeat: int,
    json_out: Optional[Path],
) -> int:
    """Build and run the host backend's smoke application.

    This is Milestone 2's completion condition: a dedicated application
    starts on the PC and produces screen, key and file results
    deterministically. Determinism is checked from the outside — the
    program is run `repeat` times and the output compared byte for byte
    — because nothing inside it may read a wall clock, a random source,
    or an address.

    Exit codes match the firmware mode: 0 pass, 1 the run was judged and
    failed, 2 it could not be judged (no compiler, configure failed).
    """
    host_source = ROOT / "bsp" / "host"
    if not host_source.is_dir():
        print("host backend not found at {}".format(host_source))
        return 2

    build = build_dir if build_dir is not None else ROOT / "build-host"
    steps = (
        ["cmake", "-S", str(host_source), "-B", str(build)],
        ["cmake", "--build", str(build), "-j"],
    )
    for command in steps:
        print("$ {}".format(" ".join(command)))
        try:
            result = subprocess.run(command, check=False)
        except OSError as error:
            print("cannot run {}: {}".format(command[0], error))
            print("the host backend needs cmake and a C++17 compiler")
            return 2
        if result.returncode != 0:
            # A configure or compile failure is not a verdict about the
            # application; it means the run never happened.
            return 2

    # Run the model-level tests once before repeating the application.
    # This includes both FAT32-default and explicit-FAT16 filesystem
    # smoke paths; a failure is a judged host-backend failure.
    try:
        ctest = subprocess.run(
            ["ctest", "--test-dir", str(build), "--output-on-failure"],
            check=False,
        )
    except OSError as error:
        print("cannot run ctest: {}".format(error))
        return 2
    if ctest.returncode != 0:
        return 1

    binary = build / "tests" / "emu_smoke"
    if not binary.is_file():
        print("emu_smoke was not produced at {}".format(binary))
        return 2

    outputs: List[str] = []
    codes: List[int] = []
    for index in range(repeat):
        run = subprocess.run([str(binary)], check=False, capture_output=True, text=True)
        outputs.append(run.stdout)
        codes.append(run.returncode)
        if index == 0:
            print(run.stdout, end="")

    deterministic = all(text == outputs[0] for text in outputs)
    passed = all(code == 0 for code in codes)
    digest = hashlib.sha256(outputs[0].encode("utf-8")).hexdigest()

    print("host backend: {} run(s), {}, output sha256 {}".format(
        repeat,
        "byte-identical" if deterministic else "OUTPUTS DIFFER",
        digest[:16],
    ))

    if json_out is not None:
        report = {
            "schema_version": 1,
            "mode": "host",
            "status": "pass" if (passed and deterministic) else "fail",
            "runs": repeat,
            "deterministic": deterministic,
            "stdout_sha256": digest,
            "exit_codes": codes,
        }
        json_out.parent.mkdir(parents=True, exist_ok=True)
        with json_out.open("w", encoding="utf-8") as sink:
            json.dump(report, sink, indent=2, sort_keys=True)
            sink.write("\n")
        print("wrote {}".format(json_out))

    if not deterministic:
        print("the same program produced different output on repeated runs")
        return 1
    return 0 if passed else 1


def _write_json_atomic(path: Path, value: object) -> None:
    """Write a machine-readable sidecar without exposing a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def firmware_test(
    target_id: str,
    firmware: Path,
    backend_dir: Optional[Path],
    cycles: Optional[int],
    keys: Optional[str],
    sd: Optional[bool],
    sd_format: Optional[str],
    lcd_variant: Optional[str],
    scenario_override: Optional[Path],
    snapshot_dir: Optional[Path],
    uart_out: Optional[Path],
    json_out: Optional[Path],
    run_id: Optional[str] = None,
    progress_interval: int = 10,
    no_progress: bool = False,
    sd_dir: Optional[Path] = None,
    sd_image_out: Optional[Path] = None,
    sd_manifest_out: Optional[Path] = None,
) -> int:
    """Run a conformance target on the pinned firmware backend.

    Exit codes: 0 pass, 1 mismatch or failure, 2 backend unavailable.
    Code 2 is the "cannot judge" case — the caller should treat it as
    hardware_required rather than as a failing run.
    """
    if run_id is not None:
        try:
            valid_run_id(run_id)
        except argparse.ArgumentTypeError as error:
            print("invalid --run-id: {}".format(error))
            return 2
    if progress_interval < 1:
        print("invalid --progress-interval: must be at least 1")
        return 2
    if no_progress and (run_id is not None or progress_interval != 10):
        print("--no-progress cannot be combined with --run-id or --progress-interval")
        return 2

    # The wrapper owns the default ID so every normal firmware invocation has
    # an observable, process-local identity.  --no-progress intentionally
    # leaves both heartbeat options off the runner command entirely.
    effective_run_id = run_id or "{}-{}".format(target_id, os.getpid())
    try:
        valid_run_id(effective_run_id)
    except argparse.ArgumentTypeError as error:
        print("invalid generated --run-id: {}".format(error))
        return 2
    try:
        target = load_firmware_target(target_id)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        print("cannot load firmware target registry: {}".format(error))
        return 2
    if target is None:
        print("unknown firmware target '{}'".format(target_id))
        print("known targets are listed in {}".format(FIRMWARE_TARGETS))
        return 1
    if target.get("status") != "active":
        print("firmware target '{}' is not active: {}".format(
            target_id, target.get("status_reason", target.get("status"))
        ))
        return 2

    if not firmware.is_file():
        print("firmware image not found: {}".format(firmware))
        return 1

    digest = hashlib.sha256(firmware.read_bytes()).hexdigest()
    expected = target.get("artifacts", {}).get("bin_sha256")
    if expected and digest != expected:
        print("firmware does not match the pinned target")
        print("  expected {}".format(expected))
        print("  actual   {}".format(digest))
        procedure = target.get("build", {}).get("reproduction_document")
        if procedure:
            print("rebuild it with the procedure in {}".format(procedure))
        else:
            print("rebuild it with the source/toolchain contract in the target registry")
        return 1

    runner_contract = target["runner"]
    target_sd = runner_contract.get("sd", {"attached": False, "format": "fat32"})
    conflicts = []
    if cycles is not None and cycles != runner_contract["cycles"]:
        conflicts.append("cycles {} (target requires {})".format(
            cycles, runner_contract["cycles"]
        ))
    if keys is not None and keys != runner_contract.get("keys"):
        conflicts.append("keys {!r} (target requires {!r})".format(
            keys, runner_contract.get("keys")
        ))
    if sd is True and not target_sd.get("attached", False):
        conflicts.append("SD attached (target requires detached)")
    if sd_format is not None and sd_format != target_sd.get("format"):
        conflicts.append("SD format {} (target requires {})".format(
            sd_format, target_sd.get("format")
        ))
    if sd_dir is not None:
        if sd is True:
            conflicts.append("SD directory snapshot cannot be combined with --sd")
        if sd_format is not None:
            conflicts.append("--sd-dir always uses the deterministic FAT32 snapshot profile")
        if not target_sd.get("attached", False):
            conflicts.append("SD directory snapshot (target requires attached SD)")
        if target_sd.get("format") != "fat32":
            conflicts.append("SD directory snapshot requires a FAT32 target profile")
    if sd_image_out is not None and sd_dir is None:
        conflicts.append("--sd-image-out requires --sd-dir in picocalc.py test")
    if sd_manifest_out is not None and sd_dir is None:
        conflicts.append("--sd-manifest requires --sd-dir")
    if sd_dir is not None and sd_manifest_out is not None and _path_is_inside(sd_manifest_out, sd_dir):
        conflicts.append("--sd-manifest must be outside the input directory snapshot")
    if sd_dir is not None and sd_image_out is not None and _path_is_inside(sd_image_out, sd_dir):
        conflicts.append("--sd-image-out must be outside the input directory snapshot")
    if sd_image_out is not None and sd_manifest_out is not None:
        try:
            same_output = sd_image_out.resolve() == sd_manifest_out.resolve()
        except OSError:
            same_output = sd_image_out.absolute() == sd_manifest_out.absolute()
        if same_output:
            conflicts.append("--sd-image-out and --sd-manifest must be different paths")
    if lcd_variant is not None and lcd_variant != runner_contract["lcd_variant"]:
        conflicts.append("LCD variant {} (target requires {})".format(
            lcd_variant, runner_contract["lcd_variant"]
        ))
    if conflicts:
        print("command line conflicts with target '{}':".format(target_id))
        for conflict in conflicts:
            print("  {}".format(conflict))
        return 1

    scenario_contract = target.get("scenario")
    if scenario_contract is None:
        if scenario_override is not None:
            print("target '{}' does not permit a scenario".format(target_id))
            return 1
        scenario_path = None
    else:
        scenario_path = scenario_override or (ROOT / scenario_contract["path"])
        if not scenario_path.is_file():
            print("target scenario not found: {}".format(scenario_path))
            return 2
        scenario_digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
        if scenario_digest != scenario_contract["sha256"]:
            print("scenario does not match the pinned target")
            print("  expected {}".format(scenario_contract["sha256"]))
            print("  actual   {}".format(scenario_digest))
            return 1

    backend = resolve_backend(backend_dir)
    if backend is None or not backend.is_dir():
        print("firmware backend checkout not found")
        print("set PICOEM_PICOCALC_DIR or pass --backend-dir")
        return 2
    pinned = target["backend"]["accepted"]
    try:
        head = subprocess.run(
            ["git", "-C", str(backend), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print("cannot inspect backend commit: {}".format(error))
        return 2
    if head.returncode != 0:
        print("cannot determine backend commit")
        return 2
    actual_commit = head.stdout.strip()
    if actual_commit != pinned:
        print("backend does not match the pinned target")
        print("  expected {}".format(pinned))
        print("  actual   {}".format(actual_commit))
        return 1
    try:
        dirty = subprocess.run(
            ["git", "-C", str(backend), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print("cannot inspect backend worktree: {}".format(error))
        return 2
    if dirty.returncode != 0:
        print("cannot inspect backend worktree")
        return 2
    if dirty.stdout.strip():
        print("backend worktree has tracked changes; the accepted pin must be clean")
        return 1

    runner = backend / "target/release/picocalc-run"
    if not runner.is_file():
        print("backend runner not built: {}".format(runner))
        print("build it with: cargo build --release -p picocalc-harness")
        return 2

    sd_snapshot_report = None
    with tempfile.TemporaryDirectory(prefix="picocalc-r2-") as temporary:
        report_path = Path(temporary) / "report.json"
        uart_path = Path(temporary) / "uart.bin"
        sd_image_path: Optional[Path] = None
        if sd_dir is not None:
            sd_image_path = Path(temporary) / "sd-snapshot.img"
            try:
                sd_snapshot_report = pack_tree(
                    sd_dir,
                    sd_image_path,
                    fat_type="fat32",
                    size_mib=64,
                    volume_label="PICOCALC",
                )
            except (SdImageError, OSError, UnicodeError) as error:
                print("cannot create SD directory snapshot: {}".format(error))
                return 2
            if sd_manifest_out is not None:
                try:
                    _write_json_atomic(sd_manifest_out, sd_snapshot_report)
                except OSError as error:
                    print("cannot write SD snapshot manifest: {}".format(error))
                    return 2
        command = [
            str(runner),
            "--bin", str(firmware),
            "--board", runner_contract["board"],
            "--lcd-variant", runner_contract["lcd_variant"],
            "--quantum", str(runner_contract["quantum"]),
            "--cycles", str(runner_contract["cycles"]),
            "--json", str(report_path),
            "--backend-commit", pinned,
            "--expect-stop", target["acceptance"]["expected_stop_reason"],
        ]
        for marker in target["acceptance"]["required_uart_markers"]:
            command.extend(["--expect-uart", marker])
        if runner_contract.get("stop_pc") is not None:
            command.extend(["--stop-pc", str(runner_contract["stop_pc"])])
        if runner_contract.get("psram", False):
            command.append("--psram")
        if runner_contract.get("psram_verify_range"):
            command.extend(["--psram-verify-range", runner_contract["psram_verify_range"]])
        if runner_contract.get("keyboard", False):
            command.append("--keyboard")
        if runner_contract.get("keys"):
            command.extend(["--keys", runner_contract["keys"]])
        if target_sd.get("attached", False):
            if sd_image_path is not None:
                command.extend(["--sd-image", str(sd_image_path)])
                if sd_image_out is not None:
                    command.extend(["--sd-image-out", str(sd_image_out)])
            else:
                command.extend(["--sd", "--sd-format", target_sd["format"]])
        audio_sink = runner_contract.get("audio_sink")
        if audio_sink is not None:
            command.extend(
                [
                    "--expect-audio-sink-count",
                    str(audio_sink["expected_count"]),
                    "--expect-audio-sink-sha256",
                    audio_sink["expected_sha256"],
                ]
            )
        if scenario_path is not None:
            snapshots = (
                snapshot_dir.resolve()
                if snapshot_dir is not None
                else Path(temporary) / "snapshots"
            )
            snapshots.mkdir(parents=True, exist_ok=True)
            command.extend(["--scenario", str(scenario_path)])
            command.extend(["--snapshot-dir", str(snapshots)])
        if uart_out is not None:
            command.extend(["--uart", str(uart_path)])
        if not no_progress:
            command.extend(
                [
                    "--run-id",
                    effective_run_id,
                    "--progress-interval",
                    str(progress_interval),
                ]
            )

        print("running {} on backend {}".format(target_id, actual_commit[:12]))
        try:
            result = subprocess.run(command, cwd=str(backend))
        except OSError as error:
            print("cannot run backend: {}".format(error))
            return 2
        if not report_path.is_file():
            print("runner did not produce a report")
            return 2
        try:
            report_bytes = report_path.read_bytes()
            report = json.loads(report_bytes)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            print("runner report is unreadable: {}".format(error))
            return 2
        if not isinstance(report, dict):
            print("runner report must be a JSON object")
            return 2
        if uart_out is not None:
            if not uart_path.is_file():
                print("runner did not produce a UART log")
                return 2
            uart_out.parent.mkdir(parents=True, exist_ok=True)
            uart_out.write_bytes(uart_path.read_bytes())
        if json_out is not None:
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_bytes(report_bytes)

    required_checks = [
        {"path": "schema_version", "op": "eq", "value": 8},
        {"path": "backend_commit", "op": "eq", "value": pinned},
        {"path": "backend_build.commit", "op": "eq", "value": pinned},
        {"path": "backend_build.dirty", "op": "eq", "value": False},
        {"path": "firmware.sha256", "op": "eq", "value": digest},
        {"path": "board", "op": "eq", "value": runner_contract["board"]},
        {"path": "lcd_variant", "op": "eq", "value": runner_contract["lcd_variant"]},
        {"path": "step_quantum", "op": "eq", "value": runner_contract["quantum"]},
        {"path": "cycle_limit", "op": "eq", "value": runner_contract["cycles"]},
        {"path": "exception", "op": "eq", "value": None},
        {"path": "error", "op": "eq", "value": None},
        {"path": "unsupported_mmio", "op": "length_eq", "value": 0},
    ]
    if sd_snapshot_report is not None:
        required_checks.extend(
            [
                {
                    "path": "sd.raw_image.bytes",
                    "op": "eq",
                    "value": sd_snapshot_report["image_bytes"],
                },
                {
                    "path": "sd.raw_image.source_sha256",
                    "op": "eq",
                    "value": sd_snapshot_report["image_sha256"],
                },
            ]
        )
    failures = check_report(report, required_checks + target["acceptance"]["report_checks"])
    expected_report_sha = target["acceptance"].get("normalized_report_sha256")
    if expected_report_sha is not None:
        actual_report_sha = normalized_json_sha256(report)
        if actual_report_sha != expected_report_sha:
            failures.append(
                "normalized report SHA-256 expected {} but got {}".format(
                    expected_report_sha, actual_report_sha
                )
            )
    expected_timeline_sha = target["acceptance"].get("timeline_sha256")
    if expected_timeline_sha is not None:
        scenario_report = report.get("scenario")
        actual_timeline_sha = None
        if not isinstance(scenario_report, dict) or "steps" not in scenario_report:
            failures.append("scenario.steps is missing")
        else:
            actual_timeline_sha = normalized_json_sha256(scenario_report["steps"])
        if actual_timeline_sha is not None and actual_timeline_sha != expected_timeline_sha:
            failures.append(
                "scenario timeline SHA-256 expected {} but got {}".format(
                    expected_timeline_sha, actual_timeline_sha
                )
            )
    verdict_status = report.get("verdict", {}).get("status")
    expected_code = {"pass": 0, "fail": 1, "cannot_judge": 2}.get(verdict_status)
    if expected_code is None:
        print("runner report has no valid verdict.status")
        return 2
    elif result.returncode != expected_code:
        print("runner exit {} disagrees with verdict.status {}".format(
            result.returncode, verdict_status
        ))
        return 2

    print("stop_reason={} cycles={}".format(
        report.get("stop_reason"), report.get("cycles")
    ))
    if report.get("psram", {}).get("verify"):
        verify_result = report["psram"]["verify"]
        print("psram verify matched={} mismatched={}".format(
            verify_result.get("matched"), verify_result.get("mismatched")
        ))
    if report.get("framebuffer"):
        print("framebuffer {}".format(report["framebuffer"].get("rgb565_sha256")))
    if json_out is not None:
        print("report written to {}".format(json_out))
    if uart_out is not None:
        print("UART written to {}".format(uart_out))
    if any(failure.endswith(" is missing") or failure.endswith(" has no length")
           for failure in failures):
        print("runner report is missing required structured fields:")
        for failure in failures:
            print("  {}".format(failure))
        return 2
    if result.returncode == 2:
        return 2
    if result.returncode == 1:
        return 1
    if failures:
        print("target report does not satisfy the registry contract:")
        for failure in failures:
            print("  FAIL {}".format(failure))
        return 1
    return result.returncode


def verify(
    references: bool,
    strict_commit: bool,
    reference_root: Optional[Path],
    r0: bool,
    workspace_root: Optional[Path],
) -> int:
    command = [sys.executable, str(ROOT / "tools/verify_environment.py")]
    if references:
        command.append("--references")
    if strict_commit:
        command.append("--strict-commit")
    if reference_root is not None:
        command.extend(["--reference-root", str(reference_root)])
    if r0:
        command.append("--r0")
    if workspace_root is not None:
        command.extend(["--workspace-root", str(workspace_root)])
    return subprocess.run(command).returncode


def fetch_references(output: Path, dry_run: bool) -> int:
    with CATALOG.open("r", encoding="utf-8") as source:
        catalog = json.load(source)
    output = output.resolve()
    destinations = [
        (project, output / project["workspace_path"])
        for project in catalog["projects"]
    ]
    existing = [str(destination) for _, destination in destinations if destination.exists()]
    if existing:
        print(
            "error: reference destination already exists: {}".format(", ".join(existing)),
            file=sys.stderr,
        )
        return 2
    if dry_run:
        for project, destination in destinations:
            print(
                "fetch {} {} @ {}".format(
                    project["git_url"], destination, project["commit"]
                )
            )
        return 0

    output.mkdir(parents=True, exist_ok=True)
    for project, destination in destinations:
        print("cloning {}".format(project["name"]))
        cloned = subprocess.run(
            ["git", "clone", "--no-checkout", project["git_url"], str(destination)]
        )
        if cloned.returncode != 0:
            return 1
        checked_out = subprocess.run(
            [
                "git",
                "-C",
                str(destination),
                "checkout",
                "--detach",
                project["commit"],
            ]
        )
        if checked_out.returncode != 0:
            return 1
    print("references ready in {}".format(output))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="picocalc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="create a pinned PicoCalc project")
    new_parser.add_argument("name", type=valid_name)
    new_parser.add_argument(
        "--output",
        type=Path,
        help="destination (default: current directory/name)",
    )

    build_parser = subparsers.add_parser("build", help="build a project")
    build_parser.add_argument("--project", type=Path, default=Path.cwd())
    build_parser.add_argument("--sdk", help="Pico SDK directory")
    build_parser.add_argument(
        "--picotool-dir",
        help="directory containing picotoolConfig.cmake (or set PICOTOOL_DIR)",
    )
    build_parser.add_argument(
        "--lcd-variant",
        choices=("hwspi-rgb888", "pio-rgb565"),
        default="pio-rgb565",
        help="independent LCD BSP to build (default: pio-rgb565)",
    )
    build_parser.add_argument("--jobs", type=int, default=2)
    build_parser.add_argument(
        "--generator",
        choices=("Ninja", "Unix Makefiles"),
        help="explicit CMake generator for reproducible builds",
    )
    build_parser.add_argument(
        "--build-timestamp",
        help="fixed UTC build timestamp for reproducible evidence builds (YYYY-MM-DDTHH:MM:SSZ)",
    )
    build_parser.add_argument(
        "--psram-lcd-coexist-test",
        action="store_true",
        help="build the PSRAM clock/LCD update coexistence test (PIO RGB565 only)",
    )
    build_parser.add_argument(
        "--diagnostic-mode",
        action="store_true",
        help="enable destructive/verbose app diagnostics (default: OFF for product builds)",
    )
    build_parser.add_argument(
        "--hardware-validation-mode",
        action="store_true",
        help="auto-test only machine-owned validation media (default: OFF)",
    )

    verify_project_parser = subparsers.add_parser(
        "verify-project",
        help="require a generated project's copied BSP to match its pinned provenance",
    )
    verify_project_parser.add_argument("--project", type=Path, default=Path.cwd())

    judge_report_parser = subparsers.add_parser(
        "judge-report",
        help="judge a raw runner report with an explicit project capability contract",
    )
    judge_report_parser.add_argument("--contract", type=Path, required=True)
    judge_report_parser.add_argument("--report", type=Path, required=True)
    judge_report_parser.add_argument(
        "--audio-analysis",
        type=Path,
        help="schema 1/2 audio-level artifact required by quality contract schema 2/3",
    )
    judge_report_parser.add_argument("--json", dest="json_out", type=Path)

    test_parser = subparsers.add_parser(
        "test", help="run a conformance target on the firmware or host backend"
    )
    test_parser.add_argument(
        "--mode",
        choices=["firmware", "host"],
        required=True,
        help=(
            "'firmware' runs the real image on the RP2040 emulator and is the "
            "authority on hardware behaviour; 'host' builds the BSP against host "
            "models and runs application logic natively, in a fraction of a second"
        ),
    )
    test_parser.add_argument(
        "--target",
        default="picocalc-helloworld-a",
        help="firmware mode: target id from reference-projects/firmware-targets.json",
    )
    test_parser.add_argument(
        "--firmware",
        type=Path,
        help="firmware mode: BIN to run; its SHA-256 must match the pinned target",
    )
    test_parser.add_argument(
        "--build-dir",
        type=Path,
        help="host mode: where to configure and build (default: build-host/)",
    )
    test_parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="host mode: runs to compare for determinism (default: 3)",
    )
    test_parser.add_argument(
        "--backend-dir",
        type=Path,
        help="picoem-picocalc checkout (default: PICOEM_PICOCALC_DIR or ../picoem-picocalc)",
    )
    test_parser.add_argument(
        "--cycles",
        type=int,
        help="firmware mode: must match the selected target contract",
    )
    test_parser.add_argument("--keys", help="keys to inject through the keyboard FIFO")
    test_parser.add_argument(
        "--lcd-variant",
        choices=("hwspi-rgb888", "pio-rgb565"),
        help="firmware mode: optional assertion; must match the target",
    )
    test_parser.add_argument(
        "--scenario",
        type=Path,
        help="firmware mode: optional scenario override with the target's exact SHA-256",
    )
    test_parser.add_argument(
        "--snapshot-dir",
        type=Path,
        help="firmware mode: preserve scenario snapshots in this directory",
    )
    test_parser.add_argument(
        "--uart",
        dest="uart_out",
        type=Path,
        help="firmware mode: preserve the raw UART0 byte stream",
    )
    test_parser.add_argument(
        "--sd",
        action="store_true",
        default=None,
        help="firmware mode: attach an SD card; FAT32 is the default profile",
    )
    test_parser.add_argument(
        "--sd-format",
        choices=["fat32", "fat16"],
        help="firmware mode: initial SD filesystem profile (requires --sd)",
    )
    test_parser.add_argument(
        "--sd-dir",
        type=Path,
        help=(
            "firmware mode: pack this host directory into a deterministic FAT32 "
            "snapshot for the attached SD card"
        ),
    )
    test_parser.add_argument(
        "--sd-image-out",
        type=Path,
        help="firmware mode: preserve the snapshot's post-run RAW image (requires --sd-dir)",
    )
    test_parser.add_argument(
        "--sd-manifest",
        type=Path,
        help="firmware mode: write the deterministic SD snapshot manifest (requires --sd-dir)",
    )
    test_parser.add_argument(
        "--run-id",
        type=valid_run_id,
        help="firmware mode: heartbeat run ID (default: <target>-<wrapper-pid>)",
    )
    test_parser.add_argument(
        "--progress-interval",
        type=positive_int,
        help="firmware mode: heartbeat interval in seconds (default: 10)",
    )
    test_parser.add_argument(
        "--no-progress",
        action="store_true",
        help="firmware mode: disable runner heartbeat output",
    )
    test_parser.add_argument("--json", dest="json_out", type=Path)

    verify_parser = subparsers.add_parser(
        "verify", help="verify portable BSP fingerprints and optional reference evidence"
    )
    verify_parser.add_argument(
        "--references",
        action="store_true",
        help="also verify hardware-proven reference repositories",
    )
    verify_parser.add_argument(
        "--strict-commit",
        action="store_true",
        help="require reference repositories to be at catalog commits",
    )
    verify_parser.add_argument(
        "--reference-root",
        type=Path,
        help="directory containing reference repositories",
    )
    verify_parser.add_argument(
        "--r0",
        action="store_true",
        help="also verify the local R0 fixed points and PicoTetris recovery bundle",
    )
    verify_parser.add_argument(
        "--workspace-root",
        type=Path,
        help="directory containing picocalc_emu, picoem-picocalc, and picotetris",
    )
    fetch_parser = subparsers.add_parser(
        "fetch-references",
        help="clone catalog reference repositories at pinned commits",
    )
    fetch_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new directory that will contain reference repositories",
    )
    fetch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show repositories and commits without cloning",
    )
    add_sd_cli(subparsers)
    add_uf2_cli(subparsers)
    args, unknown = parser.parse_known_args()
    if unknown:
        # Unrecognized flags surface on the top-level parser regardless of
        # which subcommand was invoked, so its bare usage line never shows
        # the subcommand's actual options. Print the subcommand's own usage
        # first so an invented flag is diagnosable without a second --help.
        subparser = subparsers.choices.get(args.command)
        if subparser is not None:
            subparser.print_usage(sys.stderr)
        parser.error("unrecognized arguments: {}".format(" ".join(unknown)))
    if args.command == "new":
        return create_project(args.name, args.output or (Path.cwd() / args.name))
    if args.command == "build":
        return build_project(
            args.project,
            args.sdk,
            args.picotool_dir,
            args.lcd_variant,
            max(1, args.jobs),
            args.psram_lcd_coexist_test,
            args.build_timestamp,
            args.diagnostic_mode,
            args.hardware_validation_mode,
            args.generator,
        )
    if args.command == "verify-project":
        return verify_project_provenance(args.project)
    if args.command == "judge-report":
        return judge_project_report(
            args.contract,
            args.report,
            args.audio_analysis,
            args.json_out,
        )
    if args.command == "test":
        if args.sd and args.sd_dir is not None:
            parser.error("--sd-dir cannot be combined with --sd")
        if args.sd_format is not None and args.sd_dir is not None:
            parser.error("--sd-dir always uses the deterministic FAT32 snapshot profile")
        if args.sd_format is not None and not args.sd:
            parser.error("--sd-format requires --sd")
        if args.sd_image_out is not None and args.sd_dir is None:
            parser.error("--sd-image-out requires --sd-dir")
        if args.sd_manifest is not None and args.sd_dir is None:
            parser.error("--sd-manifest requires --sd-dir")
        if args.no_progress and (
            args.run_id is not None or args.progress_interval is not None
        ):
            parser.error("--no-progress cannot be combined with --run-id or --progress-interval")
        if args.mode == "host":
            if (
                args.sd
                or args.sd_dir is not None
                or args.sd_image_out is not None
                or args.sd_manifest is not None
                or args.sd_format is not None
                or args.cycles is not None
                or args.keys is not None
                or args.lcd_variant is not None
                or args.scenario is not None
                or args.snapshot_dir is not None
                or args.uart_out is not None
                or args.run_id is not None
                or args.progress_interval is not None
                or args.no_progress
            ):
                parser.error(
                    "--cycles/--keys/--lcd-variant/--scenario/--snapshot-dir/--uart/--sd/--sd-dir/--sd-image-out/--sd-manifest/--sd-format/--run-id/--progress-interval/--no-progress are firmware-mode options; "
                    "host mode tests FAT32 and FAT16 automatically"
                )
            return host_test(args.build_dir, max(1, args.repeat), args.json_out)
        if args.firmware is None:
            parser.error("--mode firmware requires --firmware <path>")
        return firmware_test(
            args.target,
            args.firmware,
            args.backend_dir,
            args.cycles,
            args.keys,
            args.sd,
            args.sd_format,
            args.lcd_variant,
            args.scenario,
            args.snapshot_dir,
            args.uart_out,
            args.json_out,
            args.run_id,
            args.progress_interval if args.progress_interval is not None else 10,
            args.no_progress,
            sd_dir=args.sd_dir,
            sd_image_out=args.sd_image_out,
            sd_manifest_out=args.sd_manifest,
        )
    if args.command == "verify":
        if (args.strict_commit or args.reference_root is not None) and not args.references:
            parser.error("--strict-commit/--reference-root require --references")
        if args.workspace_root is not None and not args.r0:
            parser.error("--workspace-root requires --r0")
        return verify(
            args.references,
            args.strict_commit,
            args.reference_root,
            args.r0,
            args.workspace_root,
        )
    if args.command == "fetch-references":
        return fetch_references(args.output, args.dry_run)
    if args.command == "sd":
        return run_sd_cli(args)
    if args.command == "uf2":
        return run_uf2_cli(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
