#!/usr/bin/env python3
"""Verify portable BSP fingerprints and optional hardware reference evidence."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def add_check(
    checks: List[Dict[str, object]], name: str, passed: bool, **details: object
) -> None:
    check: Dict[str, object] = {
        "name": name,
        "status": "pass" if passed else "fail",
    }
    check.update(details)
    checks.append(check)


def require_text(
    checks: List[Dict[str, object]],
    root: Path,
    relative_path: str,
    label: str,
    required: List[str],
) -> None:
    path = root / relative_path
    if not path.is_file():
        add_check(
            checks,
            "source-fingerprint:" + label,
            False,
            path=relative_path,
            error="missing",
        )
        return
    text = path.read_text(encoding="utf-8")
    missing = [token for token in required if token not in text]
    add_check(
        checks,
        "source-fingerprint:" + label,
        not missing,
        path=relative_path,
        missing=missing,
    )


def board_constants(path: Path) -> Dict[str, object]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"constexpr\s+(?:uint(?:8|16|32)_t|unsigned|int|float)\s+"
        r"(?P<name>[A-Za-z0-9_]+)\s*=\s*(?P<value>[^;]+);"
    )
    constants: Dict[str, object] = {}
    for match in pattern.finditer(text):
        raw = match.group("value").strip()
        try:
            hexadecimal = re.fullmatch(r"(0[xX][0-9a-fA-F]+)(?:[uUlL]+)?", raw)
            if hexadecimal:
                value: object = int(hexadecimal.group(1), 0)
            elif "." in raw:
                value = float(re.sub(r"[fF]$", "", raw))
            else:
                value = int(re.sub(r"[uUlL]+$", "", raw), 0)
            constants[match.group("name")] = value
        except ValueError:
            continue
    return constants


def nested(data: Dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        value = value[key]
    return value


def verify_profile(checks: List[Dict[str, object]], root: Path) -> None:
    profile_path = root / "profiles/picocalc-rp2040.json"
    board_path = root / "bsp/include/picocalc/board.h"
    if not profile_path.is_file() or not board_path.is_file():
        add_check(
            checks,
            "structured-profile:board",
            False,
            error="profile or board header missing",
        )
        return

    profile = load_json(profile_path)
    constants = board_constants(board_path)
    mappings = {
        "system_clock_khz": "kSystemClockKhz",
        "display.visible_width": "kDisplayWidth",
        "display.visible_height": "kDisplayHeight",
        "display.gram_width": "kDisplayGramWidth",
        "display.gram_height": "kDisplayGramHeight",
        "display.pins.sck": "kLcdSck",
        "display.pins.mosi": "kLcdMosi",
        "display.pins.miso": "kLcdMiso",
        "display.pins.cs": "kLcdCs",
        "display.pins.dc": "kLcdDc",
        "display.pins.reset": "kLcdReset",
        "display.max_pixels_per_cs": "kLcdMaxPixelsPerCs",
        "display.pio_clock_divider": "kLcdPioClockDivider",
        "keyboard.sda": "kKeyboardSda",
        "keyboard.scl": "kKeyboardScl",
        "keyboard.frequency_hz": "kKeyboardHz",
        "keyboard.address": "kKeyboardAddress",
        "sd.miso": "kSdMiso",
        "sd.cs": "kSdCs",
        "sd.sck": "kSdSck",
        "sd.mosi": "kSdMosi",
        "sd.detect": "kSdDetect",
        "sd.init_hz": "kSdInitHz",
        "sd.run_hz": "kSdRunHz",
        "psram.cs": "kPsramCs",
        "psram.sck": "kPsramSck",
        "psram.mosi": "kPsramMosi",
        "psram.miso": "kPsramMiso",
        "audio.left": "kAudioLeft",
        "audio.right": "kAudioRight",
    }
    mismatches = []
    for profile_key, constant_name in mappings.items():
        expected = nested(profile, profile_key)
        actual = constants.get(constant_name, "missing")
        if actual != expected:
            mismatches.append(
                {
                    "profile": profile_key,
                    "constant": constant_name,
                    "expected": expected,
                    "actual": actual,
                }
            )
    add_check(
        checks,
        "structured-profile:board",
        not mismatches,
        profile="profiles/picocalc-rp2040.json",
        mismatches=mismatches,
    )


def verify_portable(checks: List[Dict[str, object]], root: Path) -> None:
    verify_profile(checks, root)
    require_text(
        checks,
        root,
        "bsp/include/picocalc/board.h",
        "board-static-asserts",
        [
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
        "lcd-known-good-sequence",
        [
            "write_command1(0x3a, 0x65)",
            "write_command1(0x36, 0x48)",
            "write_command(0x11)",
            "write_command(0x21)",
            "write_command(0x29)",
            "board::kLcdMaxPixelsPerCs",
        ],
    )
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
        "templates/rp2040-basic/app/main.cpp",
        "template-smoke",
        [
            "picocalc::init()",
            "draw_test_pattern()",
            "filesystem::smoke_test()",
            "keyboard::read_event(",
            "[PICOCALC][SMOKE]",
        ],
    )

    catalog_path = root / "reference-projects/catalog.json"
    try:
        catalog = load_json(catalog_path)
        invalid = [
            project.get("name", "unnamed")
            for project in catalog.get("projects", [])
            if not project.get("git_url")
            or not project.get("commit")
            or not project.get("evidence")
        ]
        valid = catalog.get("schema_version") == 1 and not invalid
        add_check(
            checks,
            "catalog-schema",
            valid,
            invalid_projects=invalid,
        )
    except (OSError, ValueError, TypeError) as error:
        add_check(checks, "catalog-schema", False, error=str(error))


def verify_references(
    checks: List[Dict[str, object]],
    root: Path,
    reference_root: Path,
    strict_commit: bool,
) -> None:
    catalog = load_json(root / "reference-projects/catalog.json")
    for project in catalog["projects"]:
        project_dir = reference_root / project["workspace_path"]
        head = git_head(project_dir) if project_dir.is_dir() else ""
        commit_ok = head == project["commit"]
        add_check(
            checks,
            "reference-commit:" + project["name"],
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
                "reference-file:" + project["name"] + ":" + evidence["path"],
                actual == evidence["sha256"],
                expected=evidence["sha256"],
                actual=actual,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
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
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_ROOT,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if (args.strict_commit or args.reference_root is not None) and not args.references:
        parser.error("--strict-commit/--reference-root require --references")

    root = args.project_root.resolve()
    reference_root = (
        args.reference_root.resolve()
        if args.reference_root is not None
        else root.parent
    )
    checks: List[Dict[str, object]] = []
    verify_portable(checks, root)
    if args.references:
        verify_references(checks, root, reference_root, args.strict_commit)
    failed = [check for check in checks if check["status"] != "pass"]
    report = {
        "schema_version": 1,
        "mode": "portable+references" if args.references else "portable",
        "status": "pass" if not failed else "fail",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            print("[{}] {}".format(check["status"].upper(), check["name"]))
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
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
