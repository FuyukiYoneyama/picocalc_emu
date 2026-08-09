#!/usr/bin/env python3
"""Generate and verify the NEXT-2B audio oracle sample stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

EXPECTED_HASH = "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a"
FRAME_COUNT = 49152
SAMPLE_RATE = 48000
PATTERN_PERIOD = 256
DEFAULT_FIRST_WORDS = 16


def generate_words(frame_count: int) -> List[int]:
    words: List[int] = []
    for i in range(frame_count):
        left_duty = (i * 17 + 3) & 255
        right_duty = 255 - ((i * 29 + 7) & 255)
        left_pcm = left_duty * 257 - 32768
        right_pcm = right_duty * 257 - 32768

        recovered_left = (left_pcm + 32768) // 257
        recovered_right = (right_pcm + 32768) // 257
        if recovered_left != left_duty or recovered_right != right_duty:
            raise AssertionError(
                f"PCM inverse mismatch at frame {i}: "
                f"left {left_duty}->{recovered_left}, right {right_duty}->{recovered_right}"
            )

        words.append((left_duty & 0xFFFF) | ((right_duty & 0xFFFF) << 16))
    return words


def compute_payload(frame_count: int) -> bytes:
    words = generate_words(frame_count)
    return b"".join(word.to_bytes(4, byteorder="little", signed=False) for word in words)


def build_report(frame_count: int, first_words: int) -> Dict[str, Any]:
    payload = compute_payload(frame_count)
    digest = hashlib.sha256(payload).hexdigest()
    words = generate_words(first_words) if first_words > 0 else []
    return {
        "frame_count": frame_count,
        "pattern_period": PATTERN_PERIOD,
        "duration": frame_count / SAMPLE_RATE,
        "first_words": words,
        "sha256": digest,
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frame-count",
        type=int,
        default=FRAME_COUNT,
        help="Number of packed PWM CC frames to generate",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify computed SHA-256 equals the fixed expected value",
    )
    parser.add_argument(
        "--expected-sha256",
        default=EXPECTED_HASH,
        help="Expected hash for verify mode",
    )
    parser.add_argument(
        "--first-words",
        type=int,
        default=DEFAULT_FIRST_WORDS,
        help="Count of initial words to include in report",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for JSON output (stdout if omitted)",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    arguments = parse_args(argv)

    if arguments.frame_count <= 0:
        raise ValueError("--frame-count must be greater than 0")
    if arguments.first_words < 0:
        raise ValueError("--first-words must be greater than or equal to 0")

    report = build_report(arguments.frame_count, arguments.first_words)
    actual = report["sha256"]

    if arguments.verify and actual != arguments.expected_sha256:
        report["verify"] = {
            "requested": True,
            "expected": arguments.expected_sha256,
            "actual": actual,
            "status": "mismatch",
        }
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if arguments.output is not None:
            arguments.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 1

    if arguments.verify:
        report["verify"] = {
            "requested": True,
            "expected": arguments.expected_sha256,
            "actual": actual,
            "status": "match",
        }

    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
