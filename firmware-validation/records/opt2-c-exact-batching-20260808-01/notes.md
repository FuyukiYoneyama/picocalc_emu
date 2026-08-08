# OPT2-C bounded exact running batching evidence

**Date:** 2026-08-08  
**Result:** rejected and reverted  
**OPT2 overall:** incomplete

## Candidate

Backend `815ef5daa5117c29a8a7505d5e5f1929d92d5b99` implemented the smallest
pre-dispatch-safe OPT2-C prototype. Hardware quantum remained 1. A batch was
allowed only when all of the following were proven before execution:

- core 0 was running in Thread mode and core 1 was halted or waiting on WFE;
- no bus, NVIC, PendSV, or SysTick interrupt was pending;
- the complete conservative event horizon was at least two cycles away;
- no unresolved autonomous source or PWM wrap was inside the window;
- every instruction was already in the decode cache and belonged to a strict
  Thumb-16 subset that is sequential, bus-free, fault-free, system-state-free,
  and exactly one cycle;
- the batch ended before the caller-owned cycle boundary and `stop_pc`.

Branches, memory accesses, MMIO, GPIO input, FIFO/DREQ, hints, WFE/WFI/SEV,
CPS, barriers, MRS/MSR, exception paths, and cache misses always fell back to
the one-cycle reference. The cap was 64 cycles.

The first full trace run found one contract mismatch: PSRAM `tick_count` was
14,756 lower although electrical state and all nine event domains matched.
That counter records how many identical pin samples the model received. The
prototype was corrected to bulk-account the elided identical samples. The
final clean-candidate run then matched the entire OPT1-B behavior projection
byte-for-byte.

## Exactness result

- cycles / virtual time: `927,528,660` / `3,715,000 us`
- scenario: 85/85 pass
- behavior SHA-256: `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`
- streaming event SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- events: `173,498,680`; all nine domain counts and hashes identical
- UART SHA-256: `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- RGB565 framebuffer SHA-256: `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
- PSRAM tick count: `305,747,113`

The accepted windows were much smaller than the post-hoc OPT2-B opportunity:

| metric | value |
|---|---:|
| exact batches | 8,420 |
| batched cycles | 23,176 |
| dispatches elided | 14,756 |
| maximum batch | 13 cycles |
| batched cycles / full run | 0.002498% |

OPT2-B's observed gap is therefore not convertible into a useful safe CPU
batch under this strict instruction subset. The safety contract worked, but
the available mass was negligible.

## Trace-OFF performance screening

Baseline and candidate release binaries used the same source tree and differed
only by the feature-gated candidate. Both used logical CPU 0, the same BIN,
scenario, board devices, and quantum 1. Warmups were excluded and pair order
was alternated. The host was slower than the earlier OPT1-B session, so only
paired relative values are used for the decision.

| pair | baseline | candidate | candidate change |
|---:|---:|---:|---:|
| 1 | 51.38 s | 57.49 s | +11.89% |
| 2 | 51.36 s | 57.27 s | +11.51% |
| 3 | 54.66 s | 59.34 s | +8.56% |
| median | **51.38 s** | **57.49 s** | **+11.89%** |

All six runs retained 85/85, cycle count, UART, framebuffer, PNG, PSRAM
counter, and zero keyboard drops. Because every pair regressed and the result
was far from the required 5% improvement, the formal ten-run promotion test
was stopped at the same screening boundary used for the earlier rejected
dispatcher-only candidate.

## Decision

The candidate is exact but slower. Its proof and cache-scan cost is paid across
the running path while only 0.0025% of total cycles can use the batch. It was
reverted by `c44c87f1ed4235343c5fd18860fde47b64b54325`; no active target,
validation attestation, R5 evidence, or OPT1-B baseline changed.

OPT2 remains open. The next investigation must not retry this strict
instruction-run candidate as a presumed win. PIO/UART/DMA deadline promotion
and CPU/decode block work should be measured as separate levers, then compared
before another production implementation is selected.

## Artifact integrity

- `run-report.json`: `497edb7c625d6221b242bd2e34401370308ee1fc0e94c1a2ced1e0ac93b5cb1c`
- `behavior-trace.json`: `afed2d16bb77f823b10f1d6d2cb63ad974cc582f6fa4909719d3333e2ba2a147`
