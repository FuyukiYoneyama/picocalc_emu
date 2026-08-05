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
from pathlib import Path
from typing import List, Optional, Tuple


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
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD"],
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
    dirty = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0
    return commit + ("-dirty" if dirty else "")


def project_commit(project: Path) -> str:
    """Return the app repository commit, or untracked for a source directory."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--short=12", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return "untracked"
    commit = completed.stdout.strip() if completed.returncode == 0 else ""
    return commit or "untracked"


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
    configure = [
        "cmake",
        "-S",
        str(project),
        "-B",
        str(build_dir),
        "-DPICO_BOARD=pico",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DPICOCALC_BUILD_TIMESTAMP={}".format(build_timestamp),
        "-DPICOCALC_BSP_GIT={}".format(source_commit()),
        "-DPICOCALC_APP_GIT={}".format(project_commit(project)),
        "-DPICOCALC_LCD_VARIANT={}".format(lcd_variant),
    ]
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
    if not FIRMWARE_TARGETS.is_file():
        return None
    with FIRMWARE_TARGETS.open("r", encoding="utf-8") as source:
        document = json.load(source)
    for target in document.get("targets", []):
        if target.get("id") == target_id:
            return target
    return None


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


def firmware_test(
    target_id: str,
    firmware: Path,
    backend_dir: Optional[Path],
    cycles: int,
    keys: Optional[str],
    sd: bool,
    sd_format: Optional[str],
    json_out: Optional[Path],
) -> int:
    """Run a conformance target on the pinned firmware backend.

    Exit codes: 0 pass, 1 mismatch or failure, 2 backend unavailable.
    Code 2 is the "cannot judge" case — the caller should treat it as
    hardware_required rather than as a failing run.
    """
    target = load_firmware_target(target_id)
    if target is None:
        print("unknown firmware target '{}'".format(target_id))
        print("known targets are listed in {}".format(FIRMWARE_TARGETS))
        return 1

    if not firmware.is_file():
        print("firmware image not found: {}".format(firmware))
        return 1

    digest = hashlib.sha256(firmware.read_bytes()).hexdigest()
    expected = target.get("artifacts", {}).get("bin_sha256")
    if expected and digest != expected:
        print("firmware does not match the pinned target")
        print("  expected {}".format(expected))
        print("  actual   {}".format(digest))
        print("rebuild it with the procedure in docs/IMPLEMENTATION_PLAN.md 3.2")
        return 1

    backend = resolve_backend(backend_dir)
    if backend is None or not backend.is_dir():
        print("firmware backend checkout not found")
        print("set PICOEM_PICOCALC_DIR or pass --backend-dir")
        return 2
    runner = backend / "target/release/picocalc-run"
    if not runner.is_file():
        print("backend runner not built: {}".format(runner))
        print("build it with: cargo build --release -p picocalc-harness")
        return 2

    pinned = target.get("backend", {}).get("accepted") or target.get("backend", {}).get(
        "commit"
    )
    head = subprocess.run(
        ["git", "-C", str(backend), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    actual_commit = head.stdout.strip() if head.returncode == 0 else "unknown"
    if pinned and actual_commit != pinned:
        print("warning: backend is at {} but the target pins {}".format(
            actual_commit[:12], str(pinned)[:12]
        ))

    with_json = json_out or (ROOT / "artifacts/firmware-test.json")
    with_json.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(runner),
        "--bin",
        str(firmware),
        "--board",
        "picocalc",
        "--psram",
        "--cycles",
        str(cycles),
        "--json",
        str(with_json),
        "--backend-commit",
        actual_commit,
    ]
    if keys:
        command.extend(["--keys", keys])
    if sd:
        command.extend(["--sd", "--sd-format", sd_format or "fat32"])

    print("running {} on backend {}".format(target_id, actual_commit[:12]))
    # The runner resolves its default bootrom path relative to its own
    # repository root, so run it from there.
    result = subprocess.run(command, cwd=str(backend))
    if result.returncode != 0:
        print("runner exited {}".format(result.returncode))
        return 1

    with with_json.open("r", encoding="utf-8") as source:
        report = json.load(source)
    unsupported = report.get("unsupported_mmio", [])
    exception = report.get("exception")
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
    print("report written to {}".format(with_json))

    failed = False
    if exception is not None:
        print("FAIL exception: {}".format(exception))
        failed = True
    if unsupported:
        print("FAIL {} unsupported MMIO accesses".format(len(unsupported)))
        failed = True
    return 1 if failed else 0


def verify(references: bool, strict_commit: bool, reference_root: Optional[Path]) -> int:
    command = [sys.executable, str(ROOT / "tools/verify_environment.py")]
    if references:
        command.append("--references")
    if strict_commit:
        command.append("--strict-commit")
    if reference_root is not None:
        command.extend(["--reference-root", str(reference_root)])
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
    test_parser.add_argument("--cycles", type=int, default=9_500_000_000)
    test_parser.add_argument("--keys", help="keys to inject through the keyboard FIFO")
    test_parser.add_argument(
        "--sd",
        action="store_true",
        help="firmware mode: attach an SD card; FAT32 is the default profile",
    )
    test_parser.add_argument(
        "--sd-format",
        choices=["fat32", "fat16"],
        help="firmware mode: initial SD filesystem profile (requires --sd)",
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
    args = parser.parse_args()
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
        )
    if args.command == "test":
        if args.sd_format is not None and not args.sd:
            parser.error("--sd-format requires --sd")
        if args.mode == "host":
            if args.sd or args.sd_format is not None:
                parser.error(
                    "--sd/--sd-format are firmware-mode options; "
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
            args.json_out,
        )
    if args.command == "verify":
        if (args.strict_commit or args.reference_root is not None) and not args.references:
            parser.error("--strict-commit/--reference-root require --references")
        return verify(args.references, args.strict_commit, args.reference_root)
    if args.command == "fetch-references":
        return fetch_references(args.output, args.dry_run)
    return 2


if __name__ == "__main__":
    sys.exit(main())
