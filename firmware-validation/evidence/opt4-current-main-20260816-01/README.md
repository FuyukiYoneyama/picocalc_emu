# OPT4 current-main local regression evidence

Date: 2026-08-16

This directory freezes the local firmware-regression reports used for the
OPT4 decision. It is **evidence, not a versioned validation and not a
promotion record**. Existing target pins, promoted targets, and historical
records are intentionally unchanged.

## Provenance

- backend commit: `a67e81c9ad89fee548d4c3a9c96fe91c03438ad9`
- backend working tree: clean (`backend_build.dirty=false` in every current report)
- runner profile: release, `step_quantum=1`, serial execution
- report schema: 8
- execution location: local workspace; GitHub Actions was not used
- source reports: copied byte-for-byte from the completed local run outputs;
  the temporary source directories are not part of this evidence record

The current reports use the registry-pinned firmware artifacts. Their
firmware SHA-256 values are retained inside each report and are also listed
in the decision documents. The backend is deliberately the current-main
commit above rather than any target's accepted pin; this is an observational
regression record, not a new target validation.

## Current-main reports

| target | report | result | cycle result |
|---|---|---|---:|
| `picotetris-opt1b` | `current/report-picotetris-opt1b.json` | hold | `927528659` (pinned `927528660`, -1) |
| `picocalc-audio-r1` | `current/report-picocalc-audio-r1.json` | pass | `405523032` (pinned `405523032`) |
| `picocalc-multicore-r2` | `current/report-picocalc-multicore-r2.json` | hold | `152548097` (pinned `152548092`, +5) |
| `picoedit-r1` | `current/report-picoedit-r1.json` | hold | `827799818` (pinned `827799822`, -4) |
| `picocalc-helloworld-a` | `current/report-picocalc-helloworld-a.json` | registry-contract pass | `9500000000` (cycle limit exact) |

The three `hold` results are deliberate: cycle equality is an absolute
exactness condition. Matching UART, framebuffer, scenario, SD, PSRAM, or
audio observations do not silently absorb a cycle mismatch.

### Hello acceptance scope

The Hello result is a pass **for the registered acceptance fields**, not a
claim that every report field is byte-identical to the historical record. The
run used the registered `hwspi-rgb888` profile, keyboard input `HI`, PSRAM
8 MiB verification, and a 9.5 billion-cycle limit. The accepted fields were:

- required UART markers: 3/3
- PSRAM verification: `8388608 matched / 0 mismatched`
- unknown MMIO: `0`
- exception: `null`
- stop reason: `cycle_limit`
- process exit: `0`

## Cycle-difference boundary probes

The `boundary-948/` and `boundary-00b/` reports are the probe endpoints used
to classify the current differences. They show the same three target runs at
backend commits `94818f8` and `00b05f5` respectively:

| target | 948 probe | 00b checkpoint | current main |
|---|---:|---:|---:|
| PicoTetris | `927528658` | `927528659` | `927528659` |
| multicore | `152548095` | `152548097` | `152548097` |
| PicoEdit | `827799822` | `827799818` | `827799818` |

This bounds the change to the default runtime/peripheral-model update band
and shows that the later feature-gated candidates, diagnostics, and CLI test
additions did not change the default cycle fingerprint. It does **not** name
one exact responsible commit or prove hardware equivalence. The classification
is therefore provisional. The acceptance decision is already recorded:
affected targets remain on hold, old pins and promoted targets are unchanged,
and no versioned validation or hardware correlation is being started from this
record.

## Reproduction entry point

`tools/picocalc.py test --mode firmware --target <target-id>` is **not** the
reproduction command for this directory. That wrapper intentionally requires
the target's accepted backend pin, so it must reject the current-main commit
`a67e81c9...`. Using it would reproduce the historical pinned validation, not
this current-main observation.

Reproduce this record with the low-level runner and the exact target options
from `reference-projects/firmware-targets.json`:

```bash
BACKEND=/path/to/clean/picoem-picocalc-a67e81c9
git -C "$BACKEND" rev-parse HEAD       # a67e81c9ad89fee548d4c3a9c96fe91c03438ad9
git -C "$BACKEND" status --porcelain   # empty
cargo build --release --locked -p picocalc-harness --manifest-path "$BACKEND/Cargo.toml"
RUNNER="$BACKEND/target/release/picocalc-run"

"$RUNNER" --bin <registry-pinned-bin> --board <board> \
  --lcd-variant <lcd-variant> --quantum 1 --cycles <cycles> \
  --json <output>/report.json --uart <output>/uart.bin \
  --backend-commit a67e81c9ad89fee548d4c3a9c96fe91c03438ad9 \
  --expect-stop <expected-stop> [target options] \
  [--scenario <repository scenario> --snapshot-dir <output>/snapshots]
```

`[target options]` are copied without modification from the target registry:
`--psram`, `--psram-verify-range`, `--keyboard`, `--keys`,
`--sd --sd-format fat32`, audio-sink expectations, and every `--expect-uart`
marker.
The five target rows in this record use `picotetris-opt1b`,
`picocalc-audio-r1`, `picocalc-multicore-r2`, `picoedit-r1`, and
`picocalc-helloworld-a`; their BIN paths, scenarios, cycle limits, and marker
lists are the registry values at the commit that produced this record.

The direct run is an observation, so compare the resulting report with the
tables above and classify cycle differences as described here; do not add the
old pinned cycle, normalized-report hash, or timeline hash as a new acceptance
assertion. The Hello observation additionally uses
`--board picocalc --lcd-variant hwspi-rgb888 --psram --keyboard --keys HI
--cycles 9500000000 --psram-verify-range 0:8388608`.

The JSON reports and companion UART/framebuffer artifacts are the frozen
outputs of the completed run. Verify every file with `SHA256SUMS` before using
this directory as evidence.
