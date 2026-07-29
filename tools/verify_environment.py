#!/usr/bin/env python3
"""Verify that the PicoCalc BSP still matches its hardware-proven contract."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent


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


def require_text(
    checks: List[Dict[str, object]], path: Path, label: str, required: List[str]
) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [token for token in required if token not in text]
    checks.append(
        {
            "name": label,
            "status": "pass" if not missing else "fail",
            "path": str(path.relative_to(ROOT)),
            "missing": missing,
        }
    )


def verify_contract(checks: List[Dict[str, object]]) -> None:
    require_text(
        checks,
        ROOT / "bsp/include/picocalc/board.h",
        "board-pin-and-clock-contract",
        [
            "kLcdSck = 10",
            "kLcdMosi = 11",
            "kLcdMiso = 12",
            "kLcdCs = 13",
            "kLcdDc = 14",
            "kLcdReset = 15",
            "kSdMiso = 16",
            "kSdCs = 17",
            "kSdSck = 18",
            "kSdMosi = 19",
            "kSdDetect = 22",
            "kKeyboardSda = 6",
            "kKeyboardScl = 7",
            "kKeyboardAddress = 0x1f",
            "kLcdMaxPixelsPerCs = 160",
        ],
    )
    require_text(
        checks,
        ROOT / "bsp/src/display.cpp",
        "lcd-known-good-contract",
        [
            "write_command1(0x3a, 0x65)",
            "write_command1(0x36, 0x48)",
            "write_command(0x11)",
            "write_command(0x21)",
            "write_command(0x29)",
            "board::kLcdMaxPixelsPerCs",
            "deselect();",
        ],
    )
    require_text(
        checks,
        ROOT / "bsp/src/sdcard.cpp",
        "sd-known-good-contract",
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
        ROOT / "bsp/src/filesystem.cpp",
        "fatfs-read-write-smoke-contract",
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
        ROOT / "templates/rp2040-basic/app/main.cpp",
        "template-smoke-contract",
        [
            "picocalc::init()",
            "draw_test_pattern()",
            "filesystem::smoke_test()",
            "keyboard::read_event(",
            "[PICOCALC][SMOKE]",
        ],
    )
    require_text(
        checks,
        ROOT / "bsp/include/picocalc/board.h",
        "audio-board-contract",
        [
            "kAudioLeft = 26",
            "kAudioRight = 27",
        ],
    )


def verify_references(checks: List[Dict[str, object]], strict_commit: bool) -> None:
    catalog = json.loads(
        (ROOT / "reference-projects/catalog.json").read_text(encoding="utf-8")
    )
    for project in catalog["projects"]:
        project_dir = WORKSPACE / project["workspace_path"]
        head = git_head(project_dir) if project_dir.is_dir() else ""
        commit_ok = head == project["commit"]
        checks.append(
            {
                "name": "reference-commit:" + project["name"],
                "status": "pass"
                if commit_ok or (head and not strict_commit)
                else "fail",
                "expected": project["commit"],
                "actual": head or "missing",
                "strict": strict_commit,
            }
        )
        for evidence in project["evidence"]:
            path = project_dir / evidence["path"]
            actual = sha256(path) if path.is_file() else "missing"
            checks.append(
                {
                    "name": "reference-file:"
                    + project["name"]
                    + ":"
                    + evidence["path"],
                    "status": "pass" if actual == evidence["sha256"] else "fail",
                    "expected": evidence["sha256"],
                    "actual": actual,
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict-commit",
        action="store_true",
        help="fail when a reference repository has moved from the recorded commit",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    checks: List[Dict[str, object]] = []
    verify_contract(checks)
    verify_references(checks, args.strict_commit)
    failed = [check for check in checks if check["status"] != "pass"]
    report = {
        "schema_version": 1,
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
            "RESULT status={} passed={} failed={}".format(
                report["status"], report["passed"], report["failed"]
            )
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
