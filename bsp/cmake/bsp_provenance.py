#!/usr/bin/env python3
"""Resolve a copied PicoCalc BSP identity without inheriting an app Git repo."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def directory_sha256(root: Path) -> str:
    root = root.resolve()
    files = sorted(
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


def is_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(char in "0123456789abcdef" for char in value)
    )


def resolve_identity(metadata_path: Path, bsp_dir: Path) -> tuple[str, bool]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 2:
        raise ValueError("project metadata schema_version must be 2")
    try:
        provenance = metadata["provenance"]["bsp"]
        commit = provenance["source_commit"]
        expected_tree = provenance["tree_sha256"]
    except (KeyError, TypeError) as error:
        raise ValueError("project metadata has no BSP provenance") from error
    if not is_hex(commit, 40):
        raise ValueError("BSP source_commit must be a full lowercase Git commit")
    if not is_hex(expected_tree, 64):
        raise ValueError("BSP tree_sha256 must be a lowercase SHA-256")
    dirty = directory_sha256(bsp_dir) != expected_tree
    return commit[:12] + ("-dirty" if dirty else ""), dirty


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--bsp", type=Path, required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    try:
        identity, dirty = resolve_identity(args.metadata, args.bsp)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print("BSP provenance cannot be evaluated: {}".format(error), file=sys.stderr)
        return 2
    print(identity)
    if args.require_clean and dirty:
        print("BSP tree does not match its generated provenance", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
