# OPT2-E PIO pull-stall bulk prototype

## Purpose

OPT2-D found that PIO-only fallback occupied 70.25% of running cycles. OPT2-E therefore tested the
smallest exact PIO bulk-advance subset before attempting a general PIO event scheduler.

The accepted state is deliberately narrow: every enabled state machine must already be stalled on
`PULL`, and its TX FIFO must be empty. During one `step_n_with_pins(n)` call the CPU and DMA cannot
refill that FIFO. The stall therefore cannot resolve, no instruction executes, no FIFO/DREQ/IRQ or
pin transition occurs, and only the clock-divider phase plus diagnostic stall accounting advance.
Those values are updated in closed form. Active state machines, mixed stalls, `WAIT`, RX-full and
refilled TX FIFO states retain the one-tick implementation.

The prototype does not skip GPIO sampling, PSRAM/LCD observation or the runner's outer dispatch.
This restriction is part of its exactness proof, not an implementation omission.

## Provenance

- clean candidate backend: `a7ac9020b9861c1c4803187b7092512b65f60835`
- candidate feature: `pio-exact-bulk-prototype`
- revert commit: `a7939e5` (`Revert "perf: prototype exact PIO pull-stall bulk advance"`)
- target: `picotetris-opt1b`, revision 5
- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- serial execution, quantum 1, PicoCalc, PIO RGB565 LCD, PSRAM, keyboard and FAT32 SD

The candidate was built from a detached clean checkout. The trace-ON run and trace-OFF wall-time
runs are separate; the 48.56-second trace run is not used as performance evidence.

## Reproduction outline

Create separate clean checkouts at the full candidate and revert commits. In the candidate checkout,
build the correctness runner with:

```bash
cargo clean
cargo build --locked --release -p picocalc-harness --bin picocalc-run \
  --features behavior-trace,pio-exact-bulk-prototype
```

Run `target/release/picocalc-run` with the fixed firmware/scenario hashes above and:

```bash
--bootrom roms/rp2040/bootrom-rp2040-b2.bin \
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

For wall time, rebuild the candidate with only `pio-exact-bulk-prototype`, build the revert checkout
without that feature, omit `--behavior-trace`, pin both processes to CPU 0, exclude one warm-up per
variant, and alternate the three measured pairs. The exact order and raw seconds are fixed in
`performance-screening.json`. Every run must first pass the same scenario and output hashes; wall
time from an incorrect run is discarded.

## Exactness result

The trace run passed all 85 scenario steps at 927,528,660 cycles and 3,715,000 virtual
microseconds. It retained the OPT1-B contract exactly:

- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- behavior SHA-256 `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`;
- event-stream SHA-256 `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`;
- 173,498,680 events, all nine domain counts and hashes, and PSRAM tick count 305,747,113.

Unit tests also cover integer, fractional, zero/infinite-style divider encodings, one million
cycles, zero-cycle no-op, TX refill fallback, mixed-stall fallback and PIO pad diagnostics. The
normal and feature builds passed the common, RP2040 and PicoCalc harness test suites and feature
Clippy checks.

## Opportunity and performance

The candidate reported:

- accepted calls: 371,982,564;
- accepted system cycles: 371,982,564;
- corresponding PIO ticks: 185,895,678.

Every accepted call was exactly one system cycle. The existing pin-watcher path invokes PIO before
each `update_gpio`, so the inner closed-form update never received a multi-cycle span in the real
workload.

Trace-OFF screening used clean builds, CPU 0 affinity, one excluded warm-up per variant and three
alternating pairs. Baseline median was 25.70 seconds and candidate median 25.64 seconds: a
0.233463% improvement. All six measured runs retained cycles, 85/85 steps, UART, framebuffer and
PSRAM results. The gain is below the 5% threshold, so a formal ten-run measurement would not alter
the adoption decision.

## Decision

The candidate is exact but rejected and reverted. No active target, validation attestation or
firmware pin changes. The candidate and revert commits remain reachable as provenance.

The result separates two questions: stationary PIO state is provable, but exploiting it requires a
larger exact contract for repeated constant-pin observations by the PSRAM/LCD devices and for
coalescing the outer `tick_pio` + `update_gpio` loop. That is the next PIO investigation; UART
deadline promotion remains the next independent peripheral alternative. CPU block/decode caching
remains OPT3.

## Artifact checksums

- `run-report.json`: `20b0c5fec74e12d02bbe904d87b868a515392d10307dfa1c9fc9cfcaa05375b2`
- `behavior-trace.json`: `569c25aa3176c07287319e7adcec55bcf71ff40538c814ec7e1f911499773df3`
