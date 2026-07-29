#!/usr/bin/env python3
"""Create and build PicoCalc projects from the hardware-proven template."""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/rp2040-basic"
BSP = ROOT / "bsp"


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
    text = metadata.read_text(encoding="utf-8")
    metadata.write_text(
        text[:-2] + ',\n  "project_name": "' + name + '"\n}\n',
        encoding="utf-8",
    )
    print("created {}".format(destination))
    print("edit    {}/app/main.cpp".format(destination))
    print("build   {} build --project {}".format(Path(__file__).name, destination))
    return 0


def find_sdk(requested: Optional[str]) -> Optional[Path]:
    candidates: List[Path] = []
    if requested:
        candidates.append(Path(requested))
    if os.environ.get("PICO_SDK_PATH"):
        candidates.append(Path(os.environ["PICO_SDK_PATH"]))
    candidates.extend(
        [
            Path("/home/fuyuki/pico/pico-sdk"),
            Path("/home/fuyuki/pico-sdk"),
        ]
    )
    for candidate in candidates:
        if (candidate / "external/pico_sdk_import.cmake").is_file():
            return candidate.resolve()
    return None


def build_project(project: Path, sdk_value: Optional[str], jobs: int) -> int:
    project = project.resolve()
    if not (project / "CMakeLists.txt").is_file():
        print("error: no CMakeLists.txt in {}".format(project), file=sys.stderr)
        return 2
    sdk = find_sdk(sdk_value)
    if sdk is None:
        print("error: Pico SDK not found; set PICO_SDK_PATH", file=sys.stderr)
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
    picotool_config = Path("/home/fuyuki/pico/picotool-install/lib/cmake/picotool")
    if picotool_config.is_dir():
        configure.append("-Dpicotool_DIR={}".format(picotool_config))
        environment["PATH"] = (
            "/home/fuyuki/pico/picotool-install/bin:"
            + environment.get("PATH", "")
        )
    print("SDK     {}".format(sdk))
    if subprocess.run(configure, env=environment).returncode != 0:
        return 1
    return subprocess.run(
        ["cmake", "--build", str(build_dir), "-j", str(jobs)],
        env=environment,
    ).returncode


def verify() -> int:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/verify_environment.py"), "--strict-commit"]
    ).returncode


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
    build_parser.add_argument("--jobs", type=int, default=2)

    subparsers.add_parser("verify", help="verify BSP and reference evidence")
    args = parser.parse_args()
    if args.command == "new":
        return create_project(args.name, args.output or (Path.cwd() / args.name))
    if args.command == "build":
        return build_project(args.project, args.sdk, max(1, args.jobs))
    if args.command == "verify":
        return verify()
    return 2


if __name__ == "__main__":
    sys.exit(main())
