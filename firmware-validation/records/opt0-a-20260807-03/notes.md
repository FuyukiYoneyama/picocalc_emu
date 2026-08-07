# OPT0-A semantic idle profile — 2026-08-07

This record supersedes the interpretation, but not the immutable evidence, of the schema 1 profile
in `opt0-a-20260806-01`. The original profiler reused production fast-path `is_idle()` predicates.
Those predicates correctly force conservative execution, but they combine time-advancing work with
static FIFO and interrupt state and therefore were not a valid semantic fast-forward classifier.

## Provenance

| Item | Value |
|---|---|
| backend | `picoem-picocalc` `9135f5ad09fe86a2330e51cd9a3ee106cb7c9642`, clean |
| build | release, locked, `idle-profiler`, Serial execution |
| firmware | `PicoTetris.bin` |
| firmware SHA-256 | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| scenario | `scenarios/tetris-line-clear.json` |
| quantum | `1` |
| profile schema | `2` |
| profile SHA-256 | `03051600a195b05de067be65d264ccfb21238e70498520b32781dbb9ad237b2f` |

The diagnostic remains `instrumented=true` and `valid_for_wall_time=false`.

## Classification correction

Schema 2 separates three overlapping meanings:

- `blocker_*`: state that advances with time or can wake a stopped core and therefore needs an
  exact event horizon before a jump;
- `stationary_source_*`: observable FIFO, latch, masked-IRQ, or empty-TX-stalled PIO state that
  cannot change while both CPUs and DMA are stopped;
- `exact_bulk_source_*`: active state already advanced exactly by an existing O(1) bulk tick.

In particular, an empty UART TX FIFO with TXRIS set is stationary, not active transmission. An
enabled PIO SM stalled on an empty blocking PULL cannot change PC or pins until CPU or DMA supplies
data. PWM with no wake-capable IRQ is advanced by its exact bulk tick. A peripheral IRQ level whose
NVIC line is disabled on both cores is also stationary during a both-blocked interval.

Production `is_idle()` predicates and the ordinary execution path were not loosened. All new
classification code remains behind the `idle-profiler` feature.

## Correctness gate

The full run exited 0 and preserved every registered behavior value:

- verdict `pass`, stop reason `scenario_done`, scenario 85/85;
- `927,528,660` master cycles and `3,715,000` virtual microseconds;
- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- firmware SHA-256 unchanged.

## Measurement and interpretation

| Metric | Result |
|---|---:|
| total master cycles | 927,528,660 |
| core 0 executed cycles | 308,932,816 |
| both-core-blocked cycles | 618,595,844 (66.692909%) |
| both-core-blocked episodes | 139 |
| semantically proven-safe cycles at observed quantum-1 boundaries | 618,595,844 |
| safe cycle mass in episodes at least 2,097,152 cycles | 617,662,186 |
| safe cycle mass in episodes at least 4,194,304 cycles | 84,992,703 |

No temporal blocker was observed during a both-blocked cycle in this workload. Stationary-source
totals still overlap: UART 618,595,844; PIO 593,598,272; DMA/PWM/I2C 528,360,292 each. PWM was also
exact-bulk work for 528,360,292 cycles.

Eliminating every measured blocked cycle would reduce the number of individually dispatched virtual
cycles by at most `927,528,660 / 308,932,816 = 3.002364`. This is a cycle-elimination ratio, **not a
wall-time speedup prediction**. Probe, horizon, clock update, boundary event, IRQ routing, wake, and
remaining running-cycle costs must be included before choosing an implementation or revising a
real-time target. The schema 1 cost microbenchmark remains partial and is not reinterpreted as a
complete prediction.

## Reproduction

Use a clean checkout of the recorded backend commit and the registered firmware BIN:

```bash
BACKEND=/absolute/path/to/picoem-picocalc
PICOCALC_EMU=/absolute/path/to/picocalc_emu
FIRMWARE=/absolute/path/to/PicoTetris.bin
OUT=/absolute/path/to/empty-output-directory

git -C "$BACKEND" checkout --detach 9135f5ad09fe86a2330e51cd9a3ee106cb7c9642
test -z "$(git -C "$BACKEND" status --porcelain)"
printf '%s  %s\n' \
  0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62 \
  "$FIRMWARE" | sha256sum --check

cargo build --locked --release \
  --manifest-path "$BACKEND/Cargo.toml" \
  -p picocalc-harness --features idle-profiler

"$BACKEND/target/release/picocalc-run" \
  --bin "$FIRMWARE" \
  --bootrom "$BACKEND/roms/rp2040/bootrom-rp2040-b2.bin" \
  --cycles 8000000000 --quantum 1 \
  --board picocalc --lcd-variant pio-rgb565 \
  --psram --keyboard --sd --sd-format fat32 \
  --scenario "$PICOCALC_EMU/scenarios/tetris-line-clear.json" \
  --snapshot-dir "$OUT/snapshots" \
  --expect-stop scenario_done \
  --expect-uart '[TETRIS] start' \
  --expect-uart '[TETRIS] cleared=' \
  --expect-uart 'score=1400 lines=13' \
  --json "$OUT/report.json" \
  --uart "$OUT/uart.log" \
  --idle-profile "$OUT/idle-profile.json"

sha256sum "$OUT/idle-profile.json"
```

The next task remains completion of the all-source horizon and boundary/event cost model. Only then
may the idle fast-forward and running hot-path candidates be compared on the same wall-time basis.
