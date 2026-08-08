# OPT0-A complete horizon and cost decision — 2026-08-08

This record completes the OPT0-A screening model. It combines a schema 3 PicoTetris workload
profile, a horizon/boundary microbenchmark, and a separately compiled production-path blocked-step
baseline. It selects the first OPT1 candidate; it is not evidence that fast-forward has already
been implemented or measured end to end.

## Provenance

| Item | Value |
|---|---|
| horizon/profile backend | `picoem-picocalc` `8bd6809116ad9e38de9deea961603dfb2884101b`, clean |
| final cost/baseline backend | `picoem-picocalc` `67fc4bce7934885b439bc80629175dafeab2299f`, clean |
| firmware | registered `PicoTetris.bin` |
| firmware SHA-256 | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| scenario | `scenarios/tetris-line-clear.json` |
| execution | Serial, release, locked; profile quantum 1 |
| host | AMD Ryzen 5 5600X, WSL2 Linux `6.18.33.2`, logical CPU 0 |
| Rust | `1.97.1` |
| idle profile SHA-256 | `90eb5b92902e254e75e81fa84e17b70104bad0ba22f268057a234145e2abf447` |
| horizon cost SHA-256 | `3e7dc98b8ecc48a134619b00a8d300611dc1147386514c9a1eb9e849671edf7f` |
| production baseline SHA-256 | `d296768c2bd729ff253615124881dca0584a98cf1247320d376d8f2047ab7a25` |

Commit `67fc4bc` changes only diagnostic executables after `8bd6809`; it does not alter the emulator
horizon semantics used by the workload profile.

## Complete conservative horizon

The read-only horizon probe accounts for every source in the current RP2040 model. TIMER alarms,
PWM wraps, and caller-owned external boundaries have exact deadlines. PIO, DMA, SysTick, UART, SPI,
I2C, ADC, and already-routable TIMER/PWM state use a one-cycle fallback until a longer exact formula
is promoted. A fallback can hide an optimization opportunity but cannot permit an event to be
skipped.

Masked TIMER alarms are included because they still change `ARMED` and `INTR`. PWM wrap is included
even with its NVIC line masked because CTR/INTR changes remain observable. The production execution
path is unchanged; all horizon/profile code remains diagnostic-only.

## Correctness gate

The schema 3 PicoTetris run exited 0 and retained the registered behavior:

- verdict `pass`, stop `scenario_done`, scenario 85/85;
- `927,528,660` master cycles;
- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- firmware SHA-256 unchanged.

## Workload horizon result

| Metric | Result |
|---|---:|
| both-blocked/proven-safe cycles | 618,595,844 |
| event-bounded safe segments | 2,064,042 |
| PWM boundaries | 2,063,903 |
| TIMER boundaries | 138 |
| safe mass in segments at least 256 cycles | 618,560,928 |
| safe mass in segments at least 512 cycles | 90,235,552 |

The earlier 139 CPU-blocked episodes are therefore not 139 directly skippable intervals. PWM
splits them into about 2.064 million exact boundaries. This corrects the idealized 3.002364
virtual-dispatch ceiling without discarding the underlying 66.692909% blocked-cycle observation.

The runner-owned scenario/input horizon is not yet passed into the emulator probe. OPT1-A must add
that boundary before it can jump. Its 5 ms polling/input deadlines are much farther apart than the
dominant PWM boundary and therefore do not change the priority decision, but they remain a strict
correctness requirement.

## Cost results

All values are medians of 10 retained samples with 1,000,000 operations per sample and CPU affinity
fixed to logical CPU 0.

| Component | Median net ns/op |
|---|---:|
| production `Cblocked`, quantum 1, profiler not compiled | 48.621175 |
| complete `Chorizon` | 30.388395 |
| quiescent `Cadvance(1)` | 39.412803 |
| quiescent `Cadvance(1,048,576)` | 39.247090 |
| TIMER event/route/wake increment over no-event 125-cycle step | 7.122434 |

The production baseline is a separate no-feature binary. The `step()` measurements inside
`idle-cost.json` are diagnostic-build values and must not be substituted for `Cblocked`.

Using the conservative timer boundary increment for every recorded event gives a screening
break-even of 2 cycles:

```text
ceil((Chorizon + Cadvance + Cevent) / Cblocked) = 2
```

Applying the measured segment count gives:

```text
current blocked-path estimate  = 618,595,844 * 48.621175 ns = 30.076856 s
candidate scheduling estimate  = 2,064,042 * (30.388395 + 39.412803) ns
                               + 2,064,041 * 7.122434 ns
                               = 0.158774 s
screening-only saved time       = 29.918083 s
```

Applied to the existing 63.247 s wall baseline, the arithmetic projection is 33.329 s and 11.146%
realtime. This is **not a measured optimized result**. It omits candidate branch integration,
scenario horizon plumbing, cache effects, and any unmodelled hardware correction found at R5.

Even an optimistic 2x reduction of the entire non-blocked remainder projects only 46.662 s and
7.962% realtime. The measured screening advantage is therefore large enough to select OPT1-A
exact idle fast-forward before OPT1-B hot-path cleanup.

## Decision

OPT0-A is complete for priority selection. The next work is OPT0-B's behavior/streaming event
contract, followed by OPT1-A as the first candidate optimization. OPT1-A remains provisional until
all correctness/performance gates and R5 hardware correlation pass.

## Reproduction

Build and run the cost tools from clean commit `67fc4bce7934885b439bc80629175dafeab2299f`:

```bash
cargo build --locked --release -p picocalc-harness --bin opt0-blocked-baseline
taskset -c 0 target/release/opt0-blocked-baseline \
  --iterations 1000000 --samples 10 --json blocked-production-baseline.json

cargo build --locked --release -p picocalc-harness \
  --features idle-profiler --bin opt0-idle-cost
taskset -c 0 target/release/opt0-idle-cost \
  --iterations 1000000 --samples 10 --json idle-cost.json
```

For the workload profile, use the registered PicoTetris BIN and the command from record
`opt0-a-20260807-03`, substituting backend commit `8bd6809116ad9e38de9deea961603dfb2884101b`.
The resulting `idle-profile.json` must match the SHA-256 above.
