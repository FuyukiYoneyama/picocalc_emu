#!/usr/bin/env python3
"""Prove that the NEXT-2B target rejects representative corrupted observations."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import picocalc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT
    / "firmware-validation/records/next2-audio-r1-20260809-01/runs/run-1/report.json"
)
TARGET_ID = "picocalc-audio-r1"


def set_path(document: dict[str, Any], path: str, value: Any) -> None:
    cursor: Any = document
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value


def target_contract() -> dict[str, Any]:
    registry = json.loads(
        (ROOT / "reference-projects/firmware-targets.json").read_text(encoding="utf-8")
    )
    return next(target for target in registry["targets"] if target["id"] == TARGET_ID)


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    target = target_contract()
    acceptance = target["acceptance"]
    expected_normalized = acceptance["normalized_report_sha256"]

    mutations: list[tuple[str, str, Any]] = [
        ("saved_sample_stream_word", "audio_sink.pcm_sha256", "0" * 64),
        ("wrong_dma_destination", "audio_sink.other_pwm_cc_write_count", 1),
        ("wrong_transfer_width", "audio_sink.wrong_width_count", 1),
        ("wrong_treq", "audio_sink.wrong_treq_count", 1),
        ("intra_block_cadence", "audio_sink.unexpected_gap_count", 1),
        ("block_length_or_count", "audio_sink.malformed_block_count", 1),
        ("block_boundary_gap_stream", "audio_sink.block_boundary_gap_sha256", "0" * 64),
        ("sample_count", "audio_sink.dma_write_count", 49151),
        ("firmware_exception", "exception", "HardFault"),
        (
            "unsupported_mmio",
            "unsupported_mmio",
            [{"addr": "0x40000000", "pc": "0x10000000", "read": 1, "write": 0}],
        ),
    ]

    results = []
    for name, path, value in mutations:
        candidate = copy.deepcopy(report)
        set_path(candidate, path, value)
        field_failures = picocalc.check_report(candidate, acceptance["report_checks"])
        actual_normalized = picocalc.normalized_json_sha256(candidate)
        normalized_rejected = actual_normalized != expected_normalized
        results.append(
            {
                "mutation": name,
                "path": path,
                "field_gate_rejected": bool(field_failures),
                "normalized_gate_rejected": normalized_rejected,
                "rejected": bool(field_failures) and normalized_rejected,
                "field_failures": field_failures,
                "mutated_normalized_report_sha256": actual_normalized,
            }
        )

    return {
        "schema_version": 1,
        "contract": "next2-audio-v3-20260809",
        "target": TARGET_ID,
        "source_report": str(report_path.relative_to(ROOT)),
        "source_normalized_report_sha256": picocalc.normalized_json_sha256(report),
        "expected_normalized_report_sha256": expected_normalized,
        "mutations": results,
        "result": "pass" if all(item["rejected"] for item in results) else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = verify(args.report.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
