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
from typing import Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/rp2040-basic"
BSP = ROOT / "bsp"
CATALOG = ROOT / "reference-projects/catalog.json"


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


def build_versions(project: Path, lcd_variant: Optional[str] = None) -> Tuple[str, str]:
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
    if "0.3.1-pio-rgb565" in app_text and "0.3.1-hwspi-rgb888" in app_text:
        app_version = (
            "0.3.1-pio-rgb565"
            if lcd_variant == "pio-rgb565"
            else "0.3.1-hwspi-rgb888"
        )
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
    shutil.copytree(TEMPLATE, destination)
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


def build_project(
    project: Path,
    sdk_value: Optional[str],
    picotool_value: Optional[str],
    lcd_variant: str,
    jobs: int,
) -> int:
    project = project.resolve()
    if not (project / "CMakeLists.txt").is_file():
        print("error: no CMakeLists.txt in {}".format(project), file=sys.stderr)
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
    build_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bsp_version, app_version = build_versions(project, lcd_variant)
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
    configure = [
        "cmake",
        "-S",
        str(project),
        "-B",
        str(build_dir),
        "-DPICO_BOARD=pico",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DPICOCALC_BUILD_TIMESTAMP={}".format(build_timestamp),
        "-DPICOCALC_BUILD_COMMIT={}".format(source_commit()),
        "-DPICOCALC_LCD_VARIANT={}".format(lcd_variant),
    ]
    picotool_config = find_picotool_dir(picotool_value)
    if picotool_config is not None:
        configure.append("-Dpicotool_DIR={}".format(picotool_config))
    print("SDK     {}".format(sdk))
    print("LCD     {}".format(lcd_variant))
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
    uf2 = build_dir / "picocalc_app.uf2"
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
            "uf2": str(uf2),
            "uf2_sha256": digest,
        },
    )
    print("UF2     {}".format(uf2))
    print("SHA256  {}".format(digest))
    print("history {}".format(history_path))
    return 0


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
        default="hwspi-rgb888",
        help="independent LCD BSP to build (default: hwspi-rgb888)",
    )
    build_parser.add_argument("--jobs", type=int, default=2)

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
