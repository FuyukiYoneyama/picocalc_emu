# OPT0-A idle cost microbenchmark — 2026-08-06

This record measures components of the Serial both-blocked path on the same host used for the R5
preflight. It is a diagnostic screening result, not a realtime benchmark and not evidence that an
idle fast-forward implementation is safe.

## Provenance and method

| Item | Value |
|---|---|
| backend | `picoem-picocalc` `5d01c8072c70841336cf48e46bc5aa7b8a669349`, clean |
| build | release, locked, `idle-profiler`, `opt0-idle-cost` |
| host | AMD Ryzen 5 5600X, 12 logical CPUs |
| OS | Ubuntu 24.04.4 LTS under WSL2, Linux 6.18.33.2 |
| affinity | logical CPU 0 via `taskset -c 0` |
| retained samples | 10 |
| iterations per sample | 1,000,000 |
| warm-up | 10,000 operations per family |
| raw JSON SHA-256 | `98be437f5485c68b26609dd19119ccbb1a4d57964514489f0cae35c0524e0f30` |

Each value below is the median nanoseconds per operation after subtracting the measured loop
overhead median. All ten raw samples remain in `idle-cost.json`.

| Operation | Median net ns/op |
|---|---:|
| loop overhead (reported raw; no subtraction) | 0.418480 |
| current conservative probe | 10.771746 |
| existing both-blocked `step()`, quantum 1 | 52.647255 |
| quiescent `tick_peripherals(1)` | 37.746424 |
| quiescent `tick_peripherals(64)` | 37.108583 |
| quiescent `tick_peripherals(1024)` | 37.566470 |
| quiescent `tick_peripherals(1,048,576)` | 37.825914 |

The nearly flat bulk-advance values show that the currently idle peripheral update is effectively
constant-cost in `L`. The measured current probe checks every conservative blocker and finds the
minimum among today's lazy scheduled sources, but TIMER is the only source that currently supplies
an exact deadline. Active PIO, DMA, PWM, UART, SPI, I2C, ADC, SysTick, external input and IRQ
boundaries are blockers rather than computed horizons.

The JSON reports an optimistic one-cycle break-even when only current probe plus quiescent
`tick_peripherals` are compared with the existing blocked step. This is deliberately not an
implementation decision: clock update, boundary event handling, IRQ routing, wake checks and the
full active-source horizon are not included. `eligible_for_optimization_priority_decision=false`
is normative.

Combined with record 01, the current decision remains unchanged: PicoTetris has a large
both-blocked upper bound but a zero proven-safe lower bound. The next work is exact source-specific
next-event semantics or OPT1-B hot-path profiling; the one-cycle optimistic figure must not be used
as a promised speedup.

## Reproduction

```bash
BACKEND=/absolute/path/to/picoem-picocalc
OUT=/absolute/path/to/idle-cost.json

git -C "$BACKEND" checkout --detach 5d01c8072c70841336cf48e46bc5aa7b8a669349
test -z "$(git -C "$BACKEND" status --porcelain)"
cargo build --locked --release \
  --manifest-path "$BACKEND/Cargo.toml" \
  -p picocalc-harness --features idle-profiler --bin opt0-idle-cost
taskset -c 0 "$BACKEND/target/release/opt0-idle-cost" \
  --iterations 1000000 --samples 10 --json "$OUT"
sha256sum "$OUT"
```
