# Validated Realtime Preview: VRP-0/VRP-1 contracts

This directory contains the immutable, machine-readable inputs produced by
VRP-0 and VRP-1. It is a contract, provenance, and admission fixture, not a
GUI implementation.
The files are deliberately kept separate from `firmware-validation/records/`:
the latter are existing validation evidence, while these files describe the
future preview transport and the receipt that will admit an already validated
run.

## Canonical files

| File | Purpose |
|---|---|
| [`receipt-schema-v1.json`](receipt-schema-v1.json) | JSON Schema for a preview admission receipt |
| [`receipt-fixture-picotetris-opt1b-v1.json`](receipt-fixture-picotetris-opt1b-v1.json) | Schema-only receipt fixture for `picotetris-opt1b` rev.5 |
| [`receipt-fixture-picoedit-r1-v1.json`](receipt-fixture-picoedit-r1-v1.json) | Schema-only receipt fixture for `picoedit-r1` rev.1 |
| [`preview-ipc-schema-v1.json`](preview-ipc-schema-v1.json) | Frozen local preview wire protocol |
| [`preview-ipc-fixture-v1.json`](preview-ipc-fixture-v1.json) | Accepted and rejected byte-level IPC fixtures |
| [`VRP0_BASELINE_20260828.json`](VRP0_BASELINE_20260828.json) | Reproducibility and GUI-less screening baseline |
| [`VRP0_HOST_SPIKE_20260828.md`](VRP0_HOST_SPIKE_20260828.md) | WSLg GUI/audio capability probe and dependency policy |
| [`VRP1_RECEIPT_ADMISSION_20260828.md`](VRP1_RECEIPT_ADMISSION_20260828.md) | Receipt generation, revalidation, compatibility, and local acceptance |

The two receipt fixtures are intentionally **not launchable receipts**. Their
firmware and runner paths use `<fresh-dir>` / `<backend-checkout>` placeholders;
they demonstrate the schema and provenance relationships without checking in
large binaries. A real receipt must be generated only after an authoritative
firmware validation and must use existing paths and hashes.

VRP-1's `python3 tools/picocalc.py preview` command is an admission gate only:
it revalidates a generated receipt and writes a launch descriptor, but it does
not start a GUI or emulator process. The receipt and descriptor are normally
kept beside the caller's validation artifacts; they are not required for
ordinary `new`/`build`/`test` use.

## Verification

From the repository root, run:

```sh
python3 tools/verify_vrp0_contracts.py
python3 tools/vrp0_host_spike.py --json /tmp/vrp0-host-spike.json
```

The first command checks the schema shape, target/validation provenance,
receipt fixtures, IPC frame lengths and payload semantics. It also checks that
the frozen baseline points at the exact registry revisions and hashes. The
second command is a local WSLg capability probe: it creates and closes a tiny
Tk window and opens a silent PulseAudio playback stream. It does not add a
runtime dependency, play audible data, or modify the emulator.

VRP-0 intentionally did not add `winit`, `cpal`, a GUI executable, or a
preview IPC implementation. VRP-1 adds only standard-library Python receipt
generation/admission and no Rust GUI/audio dependency. No capability is
promoted until the later preview and qualification gates pass.
