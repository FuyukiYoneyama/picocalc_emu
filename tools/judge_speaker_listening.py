#!/usr/bin/env python3
"""Turn the two required PicoCalc speaker-listening answers into a verdict."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


OVERALL_LEVELS = {
    "unacceptably_quiet",
    "acceptable_quiet",
    "appropriate",
    "too_loud",
}
TRANSIENT_LEVELS = {"too_quiet", "appropriate", "too_loud", "distorted"}
SOURCE_COMPARISONS = {
    "not_checked",
    "consistent_with_source",
    "port_changes_balance",
    "not_applicable",
}
LAUNCH_METHODS = {"uf2loader", "bootsel", "not_recorded", "other"}


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_assessment(document: object) -> list[str]:
    if not isinstance(document, dict):
        return ["root must be an object"]
    required = {
        "schema_version",
        "assessment_id",
        "application",
        "artifact",
        "evidence",
        "conditions",
        "porting_context",
        "human_assessment",
    }
    errors: list[str] = []
    if set(document) != required:
        errors.append("root fields do not match schema 1")
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(document.get("assessment_id"), str) or not document.get(
        "assessment_id"
    ):
        errors.append("assessment_id must be a non-empty string")

    application = document.get("application")
    if (
        not isinstance(application, dict)
        or set(application) != {"name", "version"}
        or not all(
            isinstance(application.get(field), str) and application.get(field)
            for field in ("name", "version")
        )
    ):
        errors.append("application must contain non-empty name and version")

    artifact = document.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {
        "bin_sha256",
        "uf2_sha256",
    }:
        errors.append("artifact must contain BIN and UF2 SHA-256")
    elif not is_sha256(artifact["bin_sha256"]) or not is_sha256(
        artifact["uf2_sha256"]
    ):
        errors.append("artifact hashes must be lowercase SHA-256")

    evidence = document.get("evidence")
    if (
        not isinstance(evidence, dict)
        or set(evidence) != {"video_file", "video_sha256"}
        or not isinstance(evidence.get("video_file"), str)
        or not evidence.get("video_file")
        or not is_sha256(evidence.get("video_sha256"))
    ):
        errors.append("evidence must contain video_file and lowercase SHA-256")

    conditions = document.get("conditions")
    if not isinstance(conditions, dict) or set(conditions) != {
        "audio_path",
        "physical_volume",
        "launch_method",
    }:
        errors.append("conditions fields do not match schema 1")
    elif (
        conditions.get("audio_path") != "built_in_speaker"
        or conditions.get("physical_volume") != "maximum"
        or conditions.get("launch_method") not in LAUNCH_METHODS
    ):
        errors.append(
            "conditions require built_in_speaker, maximum volume, and a known launch method"
        )

    porting = document.get("porting_context")
    if (
        not isinstance(porting, dict)
        or set(porting) != {"source_mix_comparison"}
        or porting.get("source_mix_comparison") not in SOURCE_COMPARISONS
    ):
        errors.append("porting_context.source_mix_comparison is invalid")

    assessment = document.get("human_assessment")
    if not isinstance(assessment, dict) or set(assessment) != {
        "overall_loudness",
        "percussion_and_transients",
        "adjustment_requested",
        "notes",
    }:
        errors.append("human_assessment fields do not match schema 1")
    elif (
        assessment.get("overall_loudness") not in OVERALL_LEVELS
        or assessment.get("percussion_and_transients") not in TRANSIENT_LEVELS
        or type(assessment.get("adjustment_requested")) is not bool
        or not isinstance(assessment.get("notes"), str)
    ):
        errors.append("human_assessment values are invalid")
    return errors


def judge(document: dict) -> dict:
    assessment = document["human_assessment"]
    overall = assessment["overall_loudness"]
    transients = assessment["percussion_and_transients"]
    accepted_overall = overall in {"acceptable_quiet", "appropriate"}
    accepted_transients = transients == "appropriate"
    status = "pass" if accepted_overall and accepted_transients else "fail"
    advisories: list[str] = []

    if status == "pass":
        if overall == "acceptable_quiet" and assessment["adjustment_requested"]:
            advisories.append("optional_loudness_adjustment")
            action = "adjust_from_accepted_safe_reference"
        else:
            action = "none"
    elif accepted_overall and transients in {"too_loud", "distorted"}:
        action = "preserve_overall_reduce_percussion_or_transients"
    elif accepted_overall and transients == "too_quiet":
        action = "preserve_overall_raise_percussion_or_transients"
    elif overall == "unacceptably_quiet" and transients == "appropriate":
        action = "raise_average_with_transient_control"
    elif overall == "too_loud":
        action = "reduce_overall_then_recheck_transients"
    else:
        action = "rebalance_transients_then_recheck_overall"

    return {
        "schema_version": 1,
        "assessment_id": document["assessment_id"],
        "status": status,
        "required_action": action,
        "advisories": advisories,
        "application": document["application"],
        "artifact": document["artifact"],
        "evidence": document["evidence"],
        "conditions": document["conditions"],
        "porting_context": document["porting_context"],
        "human_assessment": assessment,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("--json", dest="json_out", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.assessment.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"speaker listening: cannot_judge: {error}", file=sys.stderr)
        return 2
    errors = validate_assessment(document)
    if errors:
        for error in errors:
            print(f"speaker listening: cannot_judge: {error}", file=sys.stderr)
        return 2
    result = judge(document)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(encoded, encoding="utf-8")
    print(f"speaker listening: {result['status']}")
    print(f"  required action: {result['required_action']}")
    for advisory in result["advisories"]:
        print(f"  advisory: {advisory}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
