#!/usr/bin/env python3
"""Replay and validate structured SD trace artifacts locally.

The backend intentionally stores event summaries rather than every SPI byte.
This tool replays the trace event encoding used by ``SdTraceState`` to
recompute the streaming digest, checks event/CS/data invariants, and compares
multiple repeated traces byte-for-byte at the semantic event level.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any


BLOCK_SIZE = 512
READ_TOKEN = 0xFE
WRITE_TOKEN = 0xFE
ALLOWED_RUNTIME_COMMANDS = {0, 8, 17, 41, 55, 58}


def pack_u64(value: int) -> bytes:
    return struct.pack(">Q", value)


def data_canonical(data: dict[str, Any]) -> bytes:
    if not isinstance(data, dict):
        raise ValueError("data event must be an object")
    direction = data.get("direction")
    if direction not in {"read", "write"}:
        raise ValueError(f"invalid data direction: {direction!r}")
    crc = data.get("crc")
    if (
        not isinstance(crc, list)
        or len(crc) != 2
        or any(not isinstance(x, int) or not 0 <= x <= 0xFF for x in crc)
    ):
        raise ValueError("data CRC must contain two integer bytes")
    length = data.get("length")
    if length != BLOCK_SIZE:
        raise ValueError(f"data length must be {BLOCK_SIZE}, got {length!r}")
    block = data.get("block")
    token = data.get("token")
    if not isinstance(block, int) or not 0 <= block <= 0xFFFFFFFF:
        raise ValueError("data block must be a u32")
    if not isinstance(token, int) or not 0 <= token <= 0xFF:
        raise ValueError("data token must be a byte")
    expected_token = READ_TOKEN if direction == "read" else WRITE_TOKEN
    if token != expected_token:
        raise ValueError(f"unexpected {direction} token: 0x{token:02x}")
    return bytes([0 if direction == "read" else 1]) + struct.pack(">I", block) + bytes([token]) + pack_u64(length) + bytes(crc)


def event_canonical(event: dict[str, Any]) -> bytes:
    if not isinstance(event, dict):
        raise ValueError("trace event must be an object")
    kind = event.get("kind")
    sequence = event.get("sequence")
    epoch = event.get("cs_epoch")
    transfers = event.get("transfers")
    if not all(isinstance(value, int) and value >= 0 for value in (sequence, epoch, transfers)):
        raise ValueError("event sequence, cs_epoch, and transfers must be non-negative integers")
    prefix = pack_u64(sequence) + pack_u64(epoch) + pack_u64(transfers)
    if kind == "command":
        index = event.get("index")
        argument = event.get("argument")
        crc = event.get("crc")
        valid = event.get("crc_valid")
        response = event.get("response")
        if not isinstance(index, int) or not 0 <= index <= 63:
            raise ValueError("command index must be a 6-bit integer")
        if not isinstance(argument, int) or not 0 <= argument <= 0xFFFFFFFF:
            raise ValueError("command argument must be a u32")
        if not isinstance(crc, int) or not 0 <= crc <= 0xFF:
            raise ValueError("command CRC must be a byte")
        if not isinstance(valid, bool):
            raise ValueError("crc_valid must be boolean")
        if not isinstance(response, list) or any(not isinstance(x, int) or not 0 <= x <= 0xFF for x in response):
            raise ValueError("command response must be a byte array")
        data = event.get("data")
        encoded = bytes([1]) + prefix + bytes([index]) + struct.pack(">I", argument) + bytes([crc, int(valid)]) + struct.pack(">I", len(response)) + bytes(response)
        return encoded + (bytes([0]) if data is None else bytes([1]) + data_canonical(data))
    if kind == "block_data":
        data = event.get("data")
        if not isinstance(data, dict):
            raise ValueError("block_data requires data")
        return bytes([3]) + prefix + data_canonical(data)
    if kind == "deselect":
        return bytes([2]) + prefix
    raise ValueError(f"unknown trace event kind: {kind!r}")


def validate_trace(path: Path, allowed_commands: set[int] | None) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: trace root must be an object")
    if document.get("schema_version") != 1 or document.get("trace_kind") != "sd-spi-structured-v1":
        raise ValueError(f"{path}: unsupported SD trace schema")
    preview = document.get("preview")
    if document.get("preview_truncated") is not False or not isinstance(preview, list):
        raise ValueError(f"{path}: replay requires a complete preview")
    event_count = document.get("event_count")
    if not isinstance(event_count, int) or event_count < 0:
        raise ValueError(f"{path}: event_count must be a non-negative integer")
    if event_count != len(preview):
        raise ValueError(f"{path}: event_count {event_count} != preview length {len(preview)}")
    canonical = bytearray()
    commands: list[int] = []
    previous_epoch = 0
    for expected_sequence, event in enumerate(preview):
        if not isinstance(event, dict):
            raise ValueError(f"{path}: trace event {expected_sequence} must be an object")
        if event.get("sequence") != expected_sequence:
            raise ValueError(f"{path}: sequence gap at {expected_sequence}")
        epoch = event.get("cs_epoch")
        if not isinstance(epoch, int) or epoch < previous_epoch:
            raise ValueError(f"{path}: cs_epoch regressed")
        previous_epoch = epoch
        if event.get("kind") == "command":
            commands.append(event.get("index"))
            if allowed_commands is not None and event.get("index") not in allowed_commands:
                raise ValueError(f"{path}: command CMD{event.get('index')} is outside allowed set")
        canonical.extend(event_canonical(event))
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != document.get("digest_sha256"):
        raise ValueError(f"{path}: digest mismatch (computed {digest}, recorded {document.get('digest_sha256')})")
    return {
        "path": path.name,
        "event_count": event_count,
        "digest_sha256": digest,
        "commands": commands,
        "event_bytes_sha256": hashlib.sha256(bytes(canonical)).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="append", required=True, type=Path)
    parser.add_argument("--allow-command", action="append", type=int)
    parser.add_argument("--compare-repeated", action="store_true")
    args = parser.parse_args()
    allowed = set(args.allow_command) if args.allow_command else None
    try:
        summaries = [validate_trace(path, allowed) for path in args.trace]
        if args.compare_repeated and summaries:
            identity = [(item["event_count"], item["digest_sha256"], item["event_bytes_sha256"]) for item in summaries]
            if any(item != identity[0] for item in identity[1:]):
                raise ValueError("repeated traces are not deterministic")
        print(json.dumps({"status": "pass", "traces": summaries}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
