#!/usr/bin/env python3
"""Verify the VRP-0 receipt and preview IPC contract fixtures.

This verifier intentionally uses only the Python standard library.  It is a
preflight tool: no preview process, GUI, or audio device is launched here.
The receipt fixtures are schema-only and therefore use placeholder artifact
paths; committed validation reports and hashes are still checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "docs" / "validated-realtime-preview"
REGISTRY = ROOT / "reference-projects" / "firmware-targets.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(source)
    except OSError as error:
        fail(f"cannot read {path}: {error}")
    except json.JSONDecodeError as error:
        fail(f"invalid JSON {path}: {error}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def require_keys(value: Any, keys: Iterable[str], where: str) -> None:
    require(isinstance(value, dict), f"{where} must be an object")
    expected = set(keys)
    actual = set(value)
    require(actual == expected, f"{where} keys differ: expected {sorted(expected)}, got {sorted(actual)}")


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def is_commit(value: Any) -> bool:
    return isinstance(value, str) and COMMIT_RE.fullmatch(value) is not None


def path_from_repo(value: str) -> Path:
    candidate = Path(value)
    require(not candidate.is_absolute() and ".." not in candidate.parts,
            f"repository path must stay inside root: {value}")
    return ROOT / candidate


def load_registry() -> Dict[str, Any]:
    document = load(REGISTRY)
    require(isinstance(document, dict), "firmware target registry must be an object")
    require(document.get("schema_version") == 3, "firmware target registry schema must be 3")
    require(isinstance(document.get("targets"), list), "firmware target registry targets must be a list")
    return document


def target_contract_sha256(target: Dict[str, Any]) -> str:
    contract = {key: value for key, value in target.items() if key != "validation"}
    normalized = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_path_hash(value: Any, where: str, *, fixture_only: bool) -> None:
    require_keys(value, ("path", "sha256"), where)
    require(isinstance(value["path"], str) and value["path"], f"{where}.path must be non-empty")
    require(is_sha256(value["sha256"]), f"{where}.sha256 must be lowercase SHA-256")
    if not fixture_only:
        actual = path_from_repo(value["path"])
        require(actual.is_file(), f"{where}.path does not exist: {actual}")
        require(sha256(actual) == value["sha256"], f"{where}.sha256 does not match {actual}")


def verify_receipt(path: Path, registry: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    receipt = load(path)
    require_keys(
        receipt,
        ("schema_version", "fixture_only", "receipt_id", "target",
         "target_validation_record", "firmware", "backend", "report",
         "device", "provenance"),
        str(path.relative_to(ROOT)),
    )
    where = str(path.relative_to(ROOT))
    require(receipt["schema_version"] == 1, f"{where}.schema_version must be 1")
    require(receipt["fixture_only"] is True, f"{where} must be marked fixture_only")
    require(isinstance(receipt["receipt_id"], str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", receipt["receipt_id"]),
            f"{where}.receipt_id is invalid")

    target_value = receipt["target"]
    require_keys(target_value, ("id", "revision", "contract_sha256"), f"{where}.target")
    require(isinstance(target_value["id"], str) and target_value["id"], f"{where}.target.id is invalid")
    require(type(target_value["revision"]) is int and target_value["revision"] >= 1, f"{where}.target.revision is invalid")
    require(is_sha256(target_value["contract_sha256"]), f"{where}.target.contract_sha256 is invalid")

    targets = {item.get("id"): item for item in registry["targets"] if isinstance(item, dict)}
    target = targets.get(target_value["id"])
    require(target is not None, f"{where} names unknown target {target_value['id']}")
    require(target["revision"] == target_value["revision"], f"{where} target revision differs from registry")
    require(target_contract_sha256(target) == target_value["contract_sha256"], f"{where} target contract SHA differs")

    validation = receipt["target_validation_record"]
    check_path_hash(validation, f"{where}.target_validation_record", fixture_only=False)
    validation_path = path_from_repo(validation["path"])
    validation_doc = load(validation_path)
    require(validation_doc.get("schema_version") == 1, f"{validation_path} schema must be 1")
    require(validation_doc.get("result") == "accepted", f"{validation_path} is not accepted")
    require(validation_doc.get("target_id") == target_value["id"], f"{validation_path} target id differs")
    require(validation_doc.get("target_revision") == target_value["revision"], f"{validation_path} target revision differs")
    require(validation_doc.get("target_contract_sha256") == target_value["contract_sha256"], f"{validation_path} contract differs")
    require(target.get("validation", {}).get("record") == validation["path"], f"{where} validation path differs from registry")
    require(target.get("validation", {}).get("sha256") == validation["sha256"], f"{where} validation SHA differs from registry")

    check_path_hash(receipt["firmware"], f"{where}.firmware", fixture_only=True)
    backend = receipt["backend"]
    require_keys(backend, ("accepted_commit", "executable"), f"{where}.backend")
    require(is_commit(backend["accepted_commit"]), f"{where}.backend.accepted_commit is invalid")
    require(backend["accepted_commit"] == target["backend"]["accepted"], f"{where} backend commit differs from registry")
    check_path_hash(backend["executable"], f"{where}.backend.executable", fixture_only=True)

    report = receipt["report"]
    require_keys(report, ("path", "sha256", "schema_version"), f"{where}.report")
    require(report["schema_version"] == 8, f"{where}.report.schema_version must be 8")
    require(isinstance(report["path"], str) and report["path"], f"{where}.report.path is invalid")
    require(is_sha256(report["sha256"]), f"{where}.report.sha256 is invalid")
    report_path = path_from_repo(report["path"])
    require(report_path.is_file(), f"{where}.report.path does not exist: {report_path}")
    require(sha256(report_path) == report["sha256"], f"{where}.report.sha256 does not match {report_path}")
    report_doc = load(report_path)
    require(report_doc.get("schema_version") == 8, f"{report_path} schema must be 8")
    require(report_doc.get("verdict", {}).get("status") == "pass", f"{report_path} verdict is not pass")
    require(report_doc.get("backend_build", {}).get("commit") == backend["accepted_commit"], f"{report_path} backend commit differs")
    require(report_doc.get("firmware", {}).get("sha256") == receipt["firmware"]["sha256"], f"{report_path} firmware SHA differs")
    require(report_doc.get("board") == "picocalc", f"{report_path} board differs")

    device = receipt["device"]
    require_keys(device, ("board", "lcd_variant", "psram", "keyboard", "sd"), f"{where}.device")
    require(device["board"] == target["runner"]["board"] == "picocalc", f"{where}.device.board is invalid")
    require(device["lcd_variant"] == target["runner"]["lcd_variant"], f"{where}.device.lcd_variant differs")
    require(device["psram"] is target["runner"].get("psram"), f"{where}.device.psram differs")
    require(device["keyboard"] is target["runner"].get("keyboard"), f"{where}.device.keyboard differs")
    require_keys(device["sd"], ("attached", "format"), f"{where}.device.sd")
    require(device["sd"] == target["runner"].get("sd"), f"{where}.device.sd differs")
    require("i2c" not in target["runner"], f"{where} must not admit an I2C semantics profile in VRP-0")

    provenance = receipt["provenance"]
    require_keys(provenance, ("registry_path", "references"), f"{where}.provenance")
    require(provenance["registry_path"] == "reference-projects/firmware-targets.json", f"{where} registry path differs")
    require(isinstance(provenance["references"], list) and provenance["references"], f"{where}.provenance.references is empty")
    require(len(provenance["references"]) == len(set(provenance["references"])), f"{where}.provenance.references contains duplicates")
    return target_value["id"], report_doc


def parse_frame(frame: bytes, known_kinds: Dict[int, Dict[str, str]]) -> Tuple[int, int, bytes]:
    require(len(frame) >= 16, "frame is shorter than the 16-byte header")
    require(frame[:4] == b"PCRP", "bad frame magic")
    version, kind, payload_length, sequence = struct.unpack_from("<HHII", frame, 4)
    require(version == 1, f"unsupported protocol version {version}")
    require(kind in known_kinds, f"unknown message kind {kind}")
    require(payload_length <= 8 * 1024 * 1024, "payload exceeds the 8 MiB limit")
    require(len(frame) == 16 + payload_length, "truncated or overlong frame")
    return kind, sequence, frame[16:]


def canonical_json(payload: bytes) -> Any:
    try:
        text = payload.decode("utf-8")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"invalid JSON payload: {error}")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(encoded == payload, "JSON payload is not canonical UTF-8 JSON")
    return value


def check_binary_payload(kind: int, payload: bytes) -> None:
    if kind == 3:
        require(len(payload) >= 12, "RGB565 payload lacks prefix")
        _, width, height = struct.unpack_from("<QHH", payload)
        require(len(payload) == 12 + width * height * 2, "RGB565 payload length mismatch")
    elif kind == 4:
        require(len(payload) >= 16, "PCM payload lacks prefix")
        _, _rate, channels, frames = struct.unpack_from("<QIHH", payload)
        require(channels >= 1, "PCM channel count must be nonzero")
        require(len(payload) == 16 + frames * channels * 2, "PCM payload length mismatch")
    elif kind == 8:
        require(len(payload) == 9, "UART TX payload must be 9 bytes")
    elif kind == 9:
        require(len(payload) == 1, "UART RX payload must be 1 byte")
    elif kind in (6, 7):
        require(len(payload) == 0, "reset/quit payload must be empty")


def verify_ipc() -> None:
    schema_path = CONTRACT_DIR / "preview-ipc-schema-v1.json"
    fixture_path = CONTRACT_DIR / "preview-ipc-fixture-v1.json"
    schema = load(schema_path)
    fixture = load(fixture_path)
    require(schema.get("schema_version") == 1 and schema.get("protocol") == "picocalc-preview-ipc", "IPC schema identity is invalid")
    require(schema.get("status") == "frozen_for_vrp0", "IPC schema is not frozen")
    framing = schema.get("framing", {})
    require(framing.get("header_size_bytes") == 16 and framing.get("magic_hex") == "50435250", "IPC header contract differs")
    require(framing.get("version", {}).get("value") == 1, "IPC version differs")
    require(framing.get("payload_length", {}).get("maximum") == 8 * 1024 * 1024, "IPC payload limit differs")
    require(fixture.get("schema_version") == 1, "IPC fixture schema must be 1")
    require(fixture.get("contract") == "docs/validated-realtime-preview/preview-ipc-schema-v1.json", "IPC fixture contract path differs")

    kinds = {item["kind"]: item for item in schema["message_kinds"]}
    require(set(kinds) == set(range(1, 12)), "IPC kind assignment has gaps or duplicates")
    seen: Dict[str, int] = {"runner_to_preview": 0, "preview_to_runner": 0}
    for item in fixture["valid_frames"]:
        require(isinstance(item.get("frame_hex"), str), f"{item.get('name')} frame_hex missing")
        frame = bytes.fromhex(item["frame_hex"])
        kind, sequence, payload = parse_frame(frame, kinds)
        require(item["kind"] == kind and item["sequence"] == sequence, f"{item['name']} header differs from fixture metadata")
        require(item["direction"] == kinds[kind]["direction"], f"{item['name']} direction mismatches kind")
        require(payload.hex() == item["payload_hex"], f"{item['name']} payload_hex differs from frame")
        require(sequence == seen[item["direction"]], f"{item['name']} sequence is not contiguous for its direction")
        seen[item["direction"]] += 1
        if kind in (1, 2, 5, 10, 11):
            value = canonical_json(payload)
            if kind == 1:
                require(value == {"protocol": "preview-ipc", "role": "runner", "schema": 1}, "hello payload differs")
            if kind == 5:
                require(value.get("state") in ("down", "held", "up") and isinstance(value.get("key"), str), "key event payload differs")
        else:
            check_binary_payload(kind, payload)

    for item in fixture["reject_frames"]:
        require(item.get("expected_result") == "reject", f"{item.get('name')} must be a reject fixture")
        try:
            parse_frame(bytes.fromhex(item["frame_hex"]), kinds)
        except ValueError:
            pass
        else:
            fail(f"reject fixture unexpectedly accepted: {item.get('name')}")


def verify_baseline(registry: Dict[str, Any]) -> None:
    path = CONTRACT_DIR / "VRP0_BASELINE_20260828.json"
    baseline = load(path)
    require(baseline.get("schema_version") == 1, "VRP-0 baseline schema must be 1")
    require(baseline.get("status") == "screening_baseline_not_qualification", "VRP-0 baseline status is invalid")
    method = baseline.get("method", {})
    require(method.get("tool") == "tools/benchmark_firmware_realtime.py", "VRP-0 baseline tool differs")
    require(method.get("measured_runs_per_target") == 3 and method.get("warmup_runs_excluded") == 1, "VRP-0 baseline run count differs")
    require(method.get("execution") == "sequential; no parallel runs", "VRP-0 baseline must be sequential")
    backend = baseline.get("backend", {})
    require(backend.get("commit") == "e985a9d7ecb51ef760506a105edd34e31cf9b5f1", "VRP-0 baseline backend differs")
    require(backend.get("dirty") is False, "VRP-0 baseline backend must be clean")
    require(is_sha256(backend.get("runner_sha256")), "VRP-0 baseline runner SHA is invalid")

    targets = {item.get("id"): item for item in registry["targets"] if isinstance(item, dict)}
    entries = baseline.get("targets")
    require(isinstance(entries, list), "VRP-0 baseline targets must be a list")
    require({item.get("id") for item in entries} == {"picotetris-opt1b", "picoedit-r1"}, "VRP-0 baseline target set differs")
    for entry in entries:
        target_id = entry.get("id")
        target = targets.get(target_id)
        require(target is not None, f"VRP-0 baseline names unknown target {target_id}")
        require(entry.get("revision") == target["revision"], f"VRP-0 baseline revision differs for {target_id}")
        require(entry.get("target_contract_sha256") == target_contract_sha256(target), f"VRP-0 baseline contract differs for {target_id}")
        require(entry.get("source_commit") == target["source"]["commit"], f"VRP-0 baseline source differs for {target_id}")
        validation = entry.get("validation_record", {})
        require(validation.get("path") == target["validation"]["record"], f"VRP-0 baseline validation path differs for {target_id}")
        require(validation.get("sha256") == target["validation"]["sha256"], f"VRP-0 baseline validation SHA differs for {target_id}")
        require(entry.get("scenario_sha256") == target["scenario"]["sha256"], f"VRP-0 baseline scenario differs for {target_id}")
        firmware = entry.get("firmware", {})
        require(firmware.get("sha256") == target["artifacts"]["bin_sha256"], f"VRP-0 baseline BIN SHA differs for {target_id}")
        require(firmware.get("uf2_sha256") == target["artifacts"]["uf2_sha256"], f"VRP-0 baseline UF2 SHA differs for {target_id}")
        require(entry.get("determinism", {}).get("all_reports_identical") is True, f"VRP-0 baseline reports are not deterministic for {target_id}")
        require(entry.get("determinism", {}).get("all_uart_identical") is True, f"VRP-0 baseline UART is not deterministic for {target_id}")
        require(entry.get("determinism", {}).get("all_snapshots_identical") is True, f"VRP-0 baseline snapshots are not deterministic for {target_id}")
        measurements = entry.get("measurements", {})
        values = measurements.get("wall_seconds")
        require(isinstance(values, list) and len(values) == 3 and all(isinstance(value, (int, float)) and value > 0 for value in values), f"VRP-0 baseline wall measurements are invalid for {target_id}")
        require(measurements.get("median") == sorted(values)[1], f"VRP-0 baseline median is invalid for {target_id}")
        historical_reference = entry.get("historical_formal_reference", entry.get("historical_reference"))
        require(isinstance(historical_reference, str) and historical_reference, f"VRP-0 baseline historical reference missing for {target_id}")
        report_path = path_from_repo(historical_reference)
        require(report_path.is_file(), f"VRP-0 baseline historical record is missing: {report_path}")
        record = load(report_path)
        artifact_name = record.get("artifacts", {}).get("normal_report") or record.get("evidence", {}).get("run_report", {}).get("path", "").split("/")[-1]
        report_file = report_path.parent / artifact_name
        require(report_file.is_file(), f"VRP-0 baseline report is missing: {report_file}")
        expected_report_sha = entry["determinism"]["report_sha256"]
        require(sha256(report_file) == expected_report_sha, f"VRP-0 baseline report SHA differs for {target_id}")
        require(record.get("exactness", {}).get("backend_commit", record.get("firmware_run", {}).get("backend_commit")) == backend["commit"], f"VRP-0 baseline historical backend differs for {target_id}")


def verify_receipt_schema() -> None:
    schema = load(CONTRACT_DIR / "receipt-schema-v1.json")
    require(schema.get("$schema", "").endswith("draft/2020-12/schema"), "receipt schema dialect is not draft 2020-12")
    require(schema.get("properties", {}).get("schema_version", {}).get("const") == 1, "receipt schema version differs")
    required = set(schema.get("required", []))
    expected = {"schema_version", "receipt_id", "target", "target_validation_record", "firmware", "backend", "report", "device", "provenance"}
    require(required == expected, "receipt schema required fields differ")
    require(schema.get("additionalProperties") is False, "receipt schema must be closed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="picocalc_emu repository root")
    args = parser.parse_args()
    require(args.root.resolve() == ROOT.resolve(), "this verifier must run against its repository root")
    try:
        registry = load_registry()
        verify_receipt_schema()
        receipt_ids = []
        for path in sorted(CONTRACT_DIR.glob("receipt-fixture-*.json")):
            receipt_ids.append(verify_receipt(path, registry)[0])
        require(receipt_ids == ["picoedit-r1", "picotetris-opt1b"], "VRP-0 receipt fixture target set differs")
        verify_ipc()
        verify_baseline(registry)
        print("VRP-0 contracts: PASS")
        print("  receipts: " + ", ".join(receipt_ids))
        print("  IPC schema 1: valid and reject fixtures verified")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"VRP-0 contracts: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
