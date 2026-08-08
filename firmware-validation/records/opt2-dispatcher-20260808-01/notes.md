# OPT2 dispatcher-only candidate investigation

**Date:** 2026-08-08  
**Result:** rejected and reverted  
**OPT2 overall:** incomplete

## Candidate

Backend `d43693cf26f7f947b389ea9f673995a686fda602` kept the registered hardware
quantum at 1 and repeated the existing exact serial substep internally, up to a
64-cycle outer-dispatch budget. It did not skip CPU, PIO, peripheral, GPIO, or
IRQ work. `stop_pc` runs retained the original one-call path.

## Exactness failure found during development

The first implementation allowed a batch to continue across a `clk_sys`
change. `VirtualClock::rebase()` is an outer-runner observation, so delaying it
changed the conversion between scenario time and emulated cycles.

- baseline cycles: `927,528,660`
- failing candidate cycles: `927,527,264`
- baseline first scenario observation: `127,528,660`
- failing candidate first scenario observation: `127,527,263`
- baseline streaming events: `173,498,680`
- failing candidate streaming events: `173,498,675`
- failing behavior SHA-256: `ba2f89a0b0e20116e095428d23efaf05568a51f685b0f41721c870d7fae467fc`
- failing event-stream SHA-256: `cfe9ca017ae8d26431b2379171215ea6ea195c1dd3206f65ffa94cd132a16b51`

UART and final framebuffer still matched. This is why final-output equality is
not an adequate exactness gate. The behavior/event contract correctly rejected
the candidate.

After making `sys_clk_hz` change an explicit batch boundary, the final
candidate reproduced the OPT1-B projection byte-for-byte except for backend
identity:

- cycles: `927,528,660`
- behavior SHA-256: `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`
- event-stream SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- streaming events: `173,498,680`
- all nine domain counts and hashes: identical
- UART SHA-256: `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- RGB565 framebuffer SHA-256: `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`

## Performance screening

Trace OFF, release, logical CPU 0, identical PicoTetris BIN/scenario/device
profile. Baseline and candidate were rebuilt from clean detached worktrees and
run as alternating pairs under the same host conditions.

| round | OPT1-B `e985a9d` | candidate `d43693c` |
|---:|---:|---:|
| 1 | 27.30 s | 26.71 s |
| 2 | 24.99 s | 26.54 s |
| 3 | 26.16 s | 26.39 s |
| median | **26.16 s** | **26.54 s** |

The candidate median was about 1.45% slower. This screening was intentionally
stopped at three paired runs: the candidate was not near the 5% improvement
threshold, so a formal ten-run promotion measurement and additional workload
gate were not justified.

## Decision

The exact candidate added complexity without reducing turnaround time. It was
reverted by `9a7387c9aca50aba6434323d2d5e24566a6e9436`. No target revision,
validation attestation, capability, or historical R5/OPT1 record was changed.

OPT2 remains open. A later candidate must reduce actual per-cycle orchestration
between proven CPU/device event horizons; merely aggregating outer runner calls
must not be retried as a presumed optimization. Clock-tree changes are now an
explicit required boundary alongside MMIO, GPIO input, FIFO/DREQ, IRQ,
PIO/device edges, timer/SysTick/PWM/DMA events, and scenario-owned boundaries.
