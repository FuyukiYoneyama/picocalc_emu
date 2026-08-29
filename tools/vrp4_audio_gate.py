#!/usr/bin/env python3
"""Run the formal VRP-4 registered-target host-audio monitor gate.

This gate replays one admitted descriptor three times with the same runner,
BIN, scenario, and virtual boundary.  The monitor is switched off, enabled
with a draining local test player, and forced into a full bounded host queue.
Only the host presentation path changes; the authoritative preview
observation, cycle, and message sequence must remain identical.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import picocalc  # noqa: E402  (repository-local helper)
import picocalc_preview  # noqa: E402  (repository-local host monitor)


GATE_NAME = "VRP-4-registered-target-audio-monitor"


def _fake_player_command() -> list[str]:
    """Return a deterministic local sink which drains PCM and never plays it."""

    return [
        sys.executable,
        "-c",
        "import sys\nwhile sys.stdin.buffer.read(65536):\n    pass\n",
    ]


def _wait_for_monitor_drain(monitor, timeout_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if monitor.status().get("queue_frames", 0) == 0:
            return
        time.sleep(0.005)


def _run_condition(
    mode: str,
    contract: dict,
    scenario: Path,
    cycle_limit: int,
    snapshot_dir: Path,
    timeout_seconds: float,
) -> dict:
    if mode == "off":
        monitor = picocalc_preview.AudioMonitor(enabled=False)
        monitor_context = nullcontext()
    elif mode == "on":
        monitor = picocalc_preview.AudioMonitor(
            enabled=True,
            host_rate_hz=48_000,
            queue_blocks=8,
            player_command=_fake_player_command(),
        )
        monitor_context = nullcontext()
    elif mode == "forced-drop":
        monitor = picocalc_preview.AudioMonitor(
            enabled=True,
            host_rate_hz=48_000,
            queue_blocks=1,
            player_command=_fake_player_command(),
        )
        # Fill the bounded host queue before the first real PCM block.  The
        # test uses the same consume_payload path as a live monitor, but the
        # injected item makes queue-full behaviour deterministic rather than
        # depending on thread scheduling or host audio timing.
        monitor._player_channels = 2
        monitor._queue.put_nowait((b"", 1))
        with monitor._lock:
            monitor._queued_frames = 1
        monitor_context = patch.object(monitor, "_ensure_player", return_value=True)
    else:
        raise ValueError("unknown VRP-4 condition: {}".format(mode))

    try:
        with monitor_context:
            _status, replay = picocalc._run_preview_replay(
                contract,
                scenario,
                cycle_limit,
                snapshot_dir,
                timeout_seconds,
                audio_monitor=monitor,
            )
        if mode == "on":
            _wait_for_monitor_drain(monitor)
        monitor_status = monitor.status()
        return {
            "cycle": replay["cycle"],
            "digest_sha256": replay["digest_sha256"],
            "projection": replay["projection"],
            "message_count": replay["message_count"],
            "message_kinds": replay["message_kinds"],
            "monitor": monitor_status,
        }
    finally:
        monitor.close()


def run_gate(
    descriptor_path: Path,
    backend_override: Path | None,
    timeout_seconds: float,
    evidence_out: Path | None,
    selected_condition: str | None = None,
) -> int:
    if timeout_seconds <= 0:
        print("vrp4-audio-gate: timeout must be positive", file=sys.stderr)
        return 2
    try:
        descriptor, target, _firmware, _backend, _runner, contract = (
            picocalc._validate_preview_descriptor(descriptor_path, backend_override)
        )
        scenario = picocalc._scenario_contract_path(target)
        modes = (selected_condition,) if selected_condition else ("off", "on", "forced-drop")
        with tempfile.TemporaryDirectory(prefix="picocalc-vrp4-audio-") as temporary:
            root = Path(temporary)
            conditions = {}
            for mode in modes:
                print("vrp4-audio-gate: start condition={}".format(mode), flush=True)
                conditions[mode] = _run_condition(
                    mode,
                    contract,
                    scenario,
                    target["runner"]["cycles"],
                    root / (mode.replace("-", "_") + "-snapshots"),
                    timeout_seconds,
                )
                print(
                    "vrp4-audio-gate: finish condition={} cycle={} digest={}".format(
                        mode,
                        conditions[mode]["cycle"],
                        conditions[mode]["digest_sha256"],
                    ),
                    flush=True,
                )

        if selected_condition is not None:
            condition = conditions[selected_condition]
            monitor = condition["monitor"]
            if selected_condition == "off":
                passed = monitor.get("state") == "off" and monitor.get("frames_received", 0) > 0
            elif selected_condition == "on":
                passed = (
                    monitor.get("enabled") is True
                    and monitor.get("frames_received", 0) > 0
                    and monitor.get("frames_sent", 0) > 0
                    and monitor.get("host_queue_drop_count", 0) == 0
                )
            else:
                passed = (
                    monitor.get("state") == "degraded"
                    and monitor.get("host_queue_drop_count", 0) > 0
                    and monitor.get("frames_received", 0) > 0
                )
            if not passed:
                raise ValueError("VRP-4 condition failed: {}".format(condition))
            evidence = {
                "schema_version": 1,
                "gate": GATE_NAME,
                "status": "pass",
                "descriptor": {
                    "path": picocalc._receipt_path(descriptor_path),
                    "sha256": picocalc._file_sha256(descriptor_path),
                },
                "target": descriptor["target"],
                "condition": selected_condition,
                "result": condition,
            }
            if evidence_out is not None:
                picocalc._write_json_atomic(evidence_out, evidence)
            print("vrp4-audio-gate: PASS condition={}".format(selected_condition), flush=True)
            return 0

        baseline = conditions["off"]
        comparisons = {
            mode: {
                "cycle_equal": conditions[mode]["cycle"] == baseline["cycle"],
                "digest_equal": conditions[mode]["digest_sha256"] == baseline["digest_sha256"],
                "projection_equal": conditions[mode]["projection"] == baseline["projection"],
                "message_sequence_equal": conditions[mode]["message_kinds"] == baseline["message_kinds"],
            }
            for mode in ("on", "forced-drop")
        }
        monitor_off = conditions["off"]["monitor"]
        monitor_on = conditions["on"]["monitor"]
        monitor_drop = conditions["forced-drop"]["monitor"]
        checks = {
            "monitor_off_state": monitor_off.get("state") == "off",
            "monitor_off_received_pcm": monitor_off.get("frames_received", 0) > 0,
            "monitor_on_enabled": monitor_on.get("enabled") is True,
            "monitor_on_received_pcm": monitor_on.get("frames_received", 0) > 0,
            "monitor_on_sent_pcm": monitor_on.get("frames_sent", 0) > 0,
            "monitor_on_no_host_drop": monitor_on.get("host_queue_drop_count", 0) == 0,
            "forced_drop_is_bounded": monitor_drop.get("host_queue_drop_count", 0) > 0,
            "forced_drop_is_degraded": monitor_drop.get("state") == "degraded",
            "forced_drop_received_pcm": monitor_drop.get("frames_received", 0) > 0,
            "authoritative_off_on_unchanged": all(comparisons["on"].values()),
            "authoritative_off_drop_unchanged": all(comparisons["forced-drop"].values()),
        }
        if not all(checks.values()):
            raise ValueError("VRP-4 acceptance checks failed: {}".format(checks))
        evidence = {
            "schema_version": 1,
            "gate": GATE_NAME,
            "status": "pass",
            "descriptor": {
                "path": picocalc._receipt_path(descriptor_path),
                "sha256": picocalc._file_sha256(descriptor_path),
            },
            "target": descriptor["target"],
            "backend": descriptor["backend"],
            "firmware": descriptor["firmware"],
            "scenario": {
                "path": picocalc._receipt_path(scenario),
                "sha256": picocalc._file_sha256(scenario),
            },
            "boundary": {
                "virtual_cycle": baseline["cycle"],
                "stop_reason": target["acceptance"]["expected_stop_reason"],
            },
            "conditions": conditions,
            "comparisons": comparisons,
            "checks": checks,
            "forced_drop": {
                "method": "deterministic host queue saturation before first PCM block",
                "authoritative_emulation_failure": False,
            },
        }
        if evidence_out is not None:
            picocalc._write_json_atomic(evidence_out, evidence)
        print(
            "vrp4-audio-gate: PASS target={} cycle={} digest={}".format(
                target["id"], baseline["cycle"], baseline["digest_sha256"]
            )
        )
        return 0
    except TimeoutError as error:
        print("vrp4-audio-gate: CANNOT JUDGE: {}".format(error), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, EOFError, ValueError, TypeError, json.JSONDecodeError) as error:
        print("vrp4-audio-gate: REFUSED: {}".format(error), file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--backend-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument(
        "--condition",
        choices=("off", "on", "forced-drop"),
        help="run one condition as a bounded diagnostic probe instead of the full three-condition gate",
    )
    args = parser.parse_args()
    return run_gate(
        args.descriptor,
        args.backend_dir,
        args.timeout_seconds,
        args.evidence_out,
        args.condition,
    )


if __name__ == "__main__":
    raise SystemExit(main())
