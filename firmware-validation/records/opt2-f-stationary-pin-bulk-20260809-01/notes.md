# OPT2-F stationary pin-device bulk observation prototype

## Purpose

OPT2-E proved that a PIO block already stopped on an empty-TX `PULL` can be advanced in closed
form, but its real PicoTetris calls were all one system cycle because the outer runner retained
per-cycle PIO/GPIO/device observation. OPT2-F tested the next exact subset: advance that same
stationary PIO interval once and collapse repeated identical observations by the PSRAM, PIO LCD and
SPI side-band devices.

Unknown devices remained fail-closed. Each supported device explicitly opted into a constant-pin
contract. The first sample still used the normal edge-sensitive path; only the remaining identical
samples were collapsed. PSRAM retained its exact `tick_count`. Active PIO instructions, mixed
stalls, `WAIT`, refillable FIFO states and non-opted-in devices kept the original per-cycle path.

## Provenance

- clean candidate backend: `9ec1988ec4c5c4fa240a1f409ac9524364e017de`
- candidate feature: `stationary-pin-bulk-prototype`
- prerequisite PIO reapply commit: `eea6eaa`
- candidate revert: `cdb7584`
- prerequisite revert: `2671d0476c1a4286de7e3666bf91e20e27613854`
- final backend content equals baseline `a7939e550aee3f604e0e052159243bf0872fc285`
- target: `picotetris-opt1b`, revision 5
- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`

## Reproduction

Build the candidate from a clean checkout:

```bash
cargo build --locked --release -p picocalc-harness --bin picocalc-run \
  --features 'behavior-trace stationary-pin-bulk-prototype'
```

Run `picocalc-run` with the fixed firmware and scenario hashes above, plus:

```bash
--cycles 8000000000 --quantum 1 \
--board picocalc --lcd-variant pio-rgb565 \
--psram --keyboard --sd --sd-format fat32 \
--expect-stop scenario_done \
--expect-uart '[TETRIS] start' \
--expect-uart '[TETRIS] cleared=' \
--expect-uart 'score=1400 lines=13' \
--json /absolute/output/run-report.json \
--behavior-trace /absolute/output/behavior-trace.json
```

The trace-ON correctness run and trace-OFF performance runs are separate. For performance, build
baseline `a7939e5` without the prototype feature, build candidate `9ec1988` with only
`stationary-pin-bulk-prototype`, and execute three alternating A/B pairs. Every timed run must pass
the same output checks before its wall time is accepted.

## Exactness

The clean candidate passed all 85 scenario steps at 927,528,660 cycles and 3,715,000 virtual
microseconds. It matched OPT1-B exactly:

- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- behavior SHA-256 `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`;
- event SHA-256 `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`;
- 173,498,680 events and all nine domain counts/hashes;
- PSRAM tick count 305,747,113.

Device unit tests compare repeated reference samples with bulk samples at idle and first-edge
boundaries. The RP2040 integration test proves the real `step_serial` branch is exercised while the
existing PSRAM PIO write/read regressions remain exact. Feature-OFF and feature-ON tests and Clippy
all passed.

## Opportunity and performance

Every candidate run reported identical proof-of-use counters:

- outer bulk calls: 23,199,887;
- PIO bulk `system_cycles`: 371,982,564;
- eliminated repeated `update_gpio` calls: 37,012,745;
- PIO block calls: 302,454,671;
- PIO ticks: 185,895,678.

The clean trace-OFF A/B runs were pinned to CPU 0. Their medians were 26.18 seconds baseline and
26.00 seconds candidate. The candidate shortened median wall time by 0.687547746%, below the 5%
promotion threshold. All six
timed runs retained the cycle count, 85/85 scenario, UART, framebuffer and PSRAM results. A formal
ten-run measurement cannot change the threshold decision and was not performed.

## Decision

The candidate is exact but rejected for insufficient performance. Both prototype commits were
reverted without rewriting history. No active target, validation attestation or firmware pin was
changed.

The result shows that 37 million repeated GPIO/device observations are removable but are not the
dominant remaining cost. The next independent OPT2 candidate is UART deadline promotion, already
ranked second by OPT2-D. CPU/decode block caching remains OPT3.

## Artifact checksums

- `run-report.json`: `02f20a7f15ec28535813fd832503a07907b68eee1ce13668d754f66423743d9c`
- `behavior-trace.json`: `5175fc0c58951f798bfe34345ad033a8b4647a88f55eeb9edc256d826295dfae`
