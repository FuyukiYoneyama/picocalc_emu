# OPT0-A Serial idle profile — 2026-08-06

This is a diagnostic optimization-priority record, not a firmware-target validation and not an
R5 hardware-correlation result. The instrumented run preserved the registered PicoTetris behavior
while measuring where the Serial emulator spends virtual cycles.

## Provenance

| Item | Value |
|---|---|
| backend | `picoem-picocalc` `ace66df91f87cfe18c7bec0ba47bcbc12f5c9345`, clean |
| build | release, `idle-profiler` feature, Serial execution |
| firmware | `PicoTetris.bin` |
| firmware SHA-256 | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| scenario | `scenarios/tetris-line-clear.json` |
| quantum | `1` |
| profile schema | `1` |
| profile SHA-256 | `435c10d1e108ece74a8ff931f855f93fb8f04e9d61bdbde3c10ce8ae6ea6152d` |

The profile is explicitly `instrumented=true` and `valid_for_wall_time=false`. Its process duration
must not be compared with the R5 preflight performance baseline.

## Correctness checks

The run exited 0 and retained all directly comparable `picotetris-r4` contract values:

- verdict `pass`, stop reason `scenario_done`, scenario 85/85
- `927,528,660` master cycles and `3,715,000` virtual microseconds
- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
- registered firmware SHA-256 unchanged

This diagnostic commit is not added to the active target registry. The ordinary schema-8 runner
and the historical `picotetris-r4` backend pin remain unchanged; OPT0-A emits a separate profile.

## Measurement

| Metric | Result |
|---|---:|
| total master cycles | 927,528,660 |
| core 0 executed cycles | 308,932,816 |
| core 1 executed cycles | 0 |
| both-core-blocked upper bound | 618,595,844 cycles (66.692909%) |
| both-core-blocked episodes | 139 |
| conservatively proven-safe lower bound | 0 cycles (0%) |

The upper bound is not a safe jump estimate. At least one currently modelled autonomous or
observable source blocked every both-core-blocked cycle. Blocker totals overlap:

| Source | blocked cycles | episodes containing source |
|---|---:|---:|
| UART | 618,595,844 | 139 |
| PIO | 593,598,272 | 138 |
| DMA | 528,360,292 | 133 |
| PWM | 528,360,292 | 133 |
| I2C | 528,360,292 | 133 |
| SysTick / SPI / ADC / timer / pending IRQ | 0 | 0 |

The strict lower bound of zero does not prove that exact fast-forward is impossible. It proves that
CPU blocking alone is insufficient and that the current quiescence-only gate cannot skip any of
this workload. A fast-forward implementation would first need exact next-event and bulk-update
semantics for active UART/PIO/DMA/PWM/I2C paths. Until that evidence exists, the 66.69% CPU-blocked
value must not be converted into a speedup claim.

The cumulative distribution in `idle-profile.json` shows 617,662,186 blocked cycles in episodes of
at least 2,097,152 cycles, and 84,992,703 cycles in episodes of at least 4,194,304 cycles. These are
still upper-bound masses; the proven-safe `S(K)` array is zero at every threshold.

## Reproduction

Use a clean backend checkout and the already reproduced registered BIN:

```bash
BACKEND=/absolute/path/to/picoem-picocalc
PICOCALC_EMU=/absolute/path/to/picocalc_emu
FIRMWARE=/absolute/path/to/PicoTetris.bin
OUT=/absolute/path/to/empty-output-directory

git -C "$BACKEND" checkout --detach ace66df91f87cfe18c7bec0ba47bcbc12f5c9345
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

The backend checkout must remain clean through the build so that both the ordinary report and idle
profile record `dirty=false`. The next OPT0-A task is to measure `Cblocked`, `Chorizon`,
`Cadvance(L)`, and `Cevent`; no implementation priority is selected from this upper-bound profile
alone.
