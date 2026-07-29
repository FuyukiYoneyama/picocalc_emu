#!/usr/bin/env python3
"""Create and build PicoCalc projects from the hardware-proven template."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/rp2040-basic"
BSP = ROOT / "bsp"
CATALOG = ROOT / "reference-projects/catalog.json"


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
    ]
    picotool_config = find_picotool_dir(picotool_value)
    if picotool_config is not None:
        configure.append("-Dpicotool_DIR={}".format(picotool_config))
    print("SDK     {}".format(sdk))
    if picotool_config is not None:
        print("picotool {}".format(picotool_config))
    if subprocess.run(configure, env=environment).returncode != 0:
        return 1
    return subprocess.run(
        ["cmake", "--build", str(build_dir), "-j", str(jobs)],
        env=environment,
    ).returncode


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
