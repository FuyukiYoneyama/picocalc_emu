#!/usr/bin/env python3
"""Generate the NEXT-2B v3 producer and post-quantizer sink oracles."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXPECTED_PRODUCER_HASH = "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a"
EXPECTED_SINK_HASH = "1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f"
FRAME_COUNT = 49152
SAMPLE_RATE = 48000
PATTERN_PERIOD = 256
DEFAULT_EDGE_WORDS = 8


def trunc_div_toward_zero(numerator: int, denominator: int) -> int:
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def quantize(sample: int, error: int) -> Tuple[int, int]:
    target = sample + 32768
    shaped = target + trunc_div_toward_zero(error * 100, 100)
    shaped = min(65535, max(0, shaped))
    duty = (shaped + 128) >> 8
    duty = min(255, max(0, duty))
    return duty, shaped - duty * 257


def generate_streams(frame_count: int) -> Tuple[List[int], List[int]]:
    producer: List[int] = []
    sink: List[int] = []
    left_error = 0
    right_error = 0
    for index in range(frame_count):
        left_seed = (index * 17 + 3) & 255
        right_seed = 255 - ((index * 29 + 7) & 255)
        producer.append(left_seed | (right_seed << 16))

        left_pcm = left_seed * 257 - 32768
        right_pcm = right_seed * 257 - 32768
        left_duty, left_error = quantize(left_pcm, left_error)
        right_duty, right_error = quantize(right_pcm, right_error)
        sink.append(left_duty | (right_duty << 16))
    return producer, sink


def digest(words: List[int]) -> str:
    hasher = hashlib.sha256()
    for word in words:
        hasher.update(word.to_bytes(4, byteorder="little", signed=False))
    return hasher.hexdigest()


def build_report(frame_count: int, edge_words: int) -> Dict[str, Any]:
    producer, sink = generate_streams(frame_count)
    return {
        "contract_id": "next2-audio-v3-20260809",
        "frame_count": frame_count,
        "pattern_period": PATTERN_PERIOD,
        "duration": frame_count / SAMPLE_RATE,
        "producer": {
            "sha256": digest(producer),
            "first_words": producer[:edge_words],
            "last_words": producer[-edge_words:] if edge_words else [],
        },
        "sink": {
            "sha256": digest(sink),
            "first_words": sink[:edge_words],
            "last_words": sink[-edge_words:] if edge_words else [],
        },
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame-count", type=int, default=FRAME_COUNT)
    parser.add_argument("--edge-words", type=int, default=DEFAULT_EDGE_WORDS)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    arguments = parse_args(argv)
    if arguments.frame_count <= 0:
        raise ValueError("--frame-count must be greater than 0")
    if arguments.edge_words < 0:
        raise ValueError("--edge-words must be greater than or equal to 0")

    report = build_report(arguments.frame_count, arguments.edge_words)
    if arguments.verify:
        producer_match = report["producer"]["sha256"] == EXPECTED_PRODUCER_HASH
        sink_match = report["sink"]["sha256"] == EXPECTED_SINK_HASH
        report["verify"] = {
            "producer": "match" if producer_match else "mismatch",
            "sink": "match" if sink_match else "mismatch",
            "status": "match" if producer_match and sink_match else "mismatch",
        }

    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if arguments.output is not None:
        arguments.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0 if not arguments.verify or report["verify"]["status"] == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
