# VRP-2-e: registered-target complete digest gate

Status: **complete for two registered targets; GUI/audio/qualification remain separate**
Date: 2026-08-29

## Purpose

`preview-digest-gate` is the final VRP-2 acceptance command.  It consumes the
schema-1 admitted descriptor produced by `picocalc.py preview`, revalidates the
descriptor and its registry target, and then runs the same registered BIN and
backend through three independent frontends:

1. authoritative batch scenario (`--scenario` and schema-8 report),
2. JSON Lines machine API (`--machine-api` plus `--replay-scenario`), and
3. framed preview API (`--preview-api` plus `--replay-scenario`).

The command also loads the report referenced by the admitted descriptor.  It
does not infer a target from a report and it does not rewrite an old
validation record.

## Complete comparison

The gate projects each report/status onto observation schema 1:

- the complete **schema-8 `audio_sink` DMA-to-PWM observation surface**:
  status, write/error counters, PCM digest, bounded edge words, timer/TREQ
  identity, due-cycle digest, block boundaries, gap counters/digest, and
  service-latency counters/digest (with the timer fraction normalized to
  numerator/denominator),
- 320x320 RGB565 framebuffer identity and non-black count,
- UART byte count and SHA-256,
- unsupported-MMIO entries, counts, PCs, and truncation state.

The Rust backend and this tool use the same canonical JSON rule: recursively
sorted object keys, compact UTF-8 JSON, and **no trailing LF** for the
observation digest.  Report-only provenance (`backend_build`, paths, elapsed
wall time, PNG names, and audio oracle fields) is not silently mixed into this
digest.  Host-side loudness/rail statistics from the separate
`--audio-analysis` artifact are also outside VRP-2's exactness surface; VRP-4
will define a versioned audio monitor contract if those values become an
acceptance input.  The provenance and report checks remain enforced separately
by descriptor admission and the registered target contract.

The following must all be equal before the gate can pass:

```text
registered report projection
batch report projection
machine-api preview projection
preview-api status projection
```

The final virtual cycle, scenario timeline, target report checks, and replay
status must also agree.  A missing `audio_sink` in the registered or fresh
batch report is a refusal, not a zero-filled default: a target must be
revalidated with `--audio-analysis` before it can be used for complete digest
acceptance.

## Local usage

```sh
python3 tools/picocalc.py preview-digest-gate \
  --descriptor /absolute/path/to/admitted-descriptor.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --timeout-seconds 900 \
  --evidence-out /absolute/path/to/vrp2-complete-digest.json
```

The command returns `0` only when all four projections, digests, cycles, and
contract checks pass.  It returns `1` for a descriptor/report/projection
mismatch and `2` when the run cannot be judged (for example a timeout).
Evidence is written atomically only after a pass.  Batch, machine-API, and
preview replay each receive a separate temporary snapshot directory, so one
frontend cannot overwrite another frontend's artifacts.  All run directories
and generated audio-analysis files are temporary; the caller-owned evidence
path is the only persistent output.

## Current status and non-claims

The implementation is covered by a repository-owned fake registered-target
test that exercises descriptor admission, batch/machine/preview execution,
projection normalization, canonical digest equality, cycle equality, and
atomic evidence output.  The real-target gate was then completed locally on
2026-08-29 using clean backend commit
`c1c20d7d86a3006569375bc333cf72494e95eb46` and runner SHA
`f1a79384d0f90fafea1fbe9db249dc9c54327ef12bed0445c1e4bef23e3a050c`.
The versioned targets `picotetris-opt1b-vrp2f` revision 8 and
`picoedit-r1-vrp2f` revision 4 each use a SHA-matched real BIN, a fresh
schema-8 report with the complete `audio_sink` surface, a schema-1 receipt,
an admitted descriptor, and a validation record.  The four-way registered /
batch / machine-API / preview-API projection digest and terminal cycle passed
for both targets.  Evidence is kept in:

- `firmware-validation/records/vrp2-f-picotetris-20260829-01/`
- `firmware-validation/records/vrp2-f-picoedit-20260829-01/`

Existing historical records and superseded target revisions remain immutable.

This gate does not add a GUI, host audio transport, hardware correlation, or
`realtime-1x-qualified` capability.  It proves only the registered-target
complete-digest contract; VRP-3 onward remains a separate plan.
