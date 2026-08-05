#!/usr/bin/env python3
"""Deterministic source identities used by generated PicoCalc projects."""

import hashlib
import subprocess
from pathlib import Path
from typing import Iterable, Optional


def directory_sha256(root: Path) -> str:
    """Hash every regular file by relative path and content."""
    root = root.resolve()
    files: Iterable[Path] = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def git_dirty(root: Path, relative_path: Optional[str] = None) -> bool:
    command = ["git", "-C", str(root), "status", "--porcelain"]
    if relative_path is not None:
        command.extend(["--", relative_path])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode != 0 or bool(completed.stdout.strip())
