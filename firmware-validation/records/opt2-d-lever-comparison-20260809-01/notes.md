# OPT2-D candidate-lever comparison

## Purpose

OPT2-C proved that its narrow CPU instruction batching subset was exact, but it covered only
0.002498% of the run and made the host slower. OPT2-D therefore measures the two remaining
families independently before another production implementation is selected:

1. one-cycle peripheral horizon occupancy, preserving PIO/UART/DMA overlap;
2. CPU decode-cache reuse and the dynamic length of sequential cache-hit runs.

Neither metric is a safe batching window or a predicted speedup. They are opportunity bounds and
implementation-priority inputs only.

## Reproduction contract

- backend: `e482172565fc3073ba0960eb5e2642968a65ae52`, clean
- profiler feature: `event-horizon-profiler`
- profiler schema: 2
- target: `picotetris-opt1b`, revision 5
- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- Serial execution, quantum 1, PicoCalc, PIO RGB565 LCD, PSRAM, keyboard, FAT32 SD

The runner was built after `cargo clean` with `--locked --release`. The profile run is
instrumented and is not a wall-time measurement. A separate `behavior-trace` build/run supplied
the exactness evidence.

## Exactness result

The scenario passed 85/85 at 927,528,660 cycles and 3,715,000 virtual microseconds. It retained:

- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- behavior SHA-256 `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`;
- event-stream SHA-256 `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`;
- 173,498,680 events and all nine registered domain hashes/counts.

## Peripheral result

The 16-bucket signature records overlap rather than adding overlapping per-source counters.

| signature | cycle mass | running share |
|---|---:|---:|
| PIO only | 217,025,266 | 70.2500% |
| UART only | 34,901,586 | 11.2975% |
| DMA only | 22,000 | 0.0071% |
| PIO + DMA | 2,128 | 0.0007% |
| UART + DMA | 5,296,015 | 1.7143% |

The union is 257,246,995 cycles: 83.2696% of running cycles and 27.7347% of the complete run.
PIO-only occupancy is 23.3982% of all virtual cycles. This does **not** mean those cycles can be
skipped. It shows that a one-cycle PIO fallback is the dominant independent limiter and that
UART- or DMA-only work cannot expose the largest horizons first.

## CPU/decode result

Core 0 performed 172,417,748 cacheable hits and 297,282 misses: a 99.8279% hit rate. Core 1 did
not execute. There were 37,786,899 dynamic sequential hit runs, averaging 4.563 instructions.

| minimum run length | hit-instruction mass | share of all hit instructions |
|---:|---:|---:|
| 4 | 86,811,548 | 50.3495% |
| 8 | 47,058,537 | 27.2933% |
| 16 | 23,317,771 | 13.5240% |
| 32 | 942,517 | 0.5466% |
| 64 | 18,085 | 0.0105% |

The cache-hit rate makes CPU block work plausible, but the dynamic grouping span is modest. It
does not overturn the plan's separation: CPU/decode block caching remains OPT3 work and must keep
code-write invalidation, exceptions, MMIO and dual-core visibility exact.

## Decision

The next prototype is PIO-first exact event horizon and bulk advance. Its first gate is
correctness, not speed: for a bounded PIO subset, final state, every pin transition, device
response, FIFO/DREQ change, IRQ assertion and delivery cycle must equal the one-cycle reference.
Only after that proof may it receive a trace-OFF A/B wall measurement.

UART deadline promotion is second. Standalone DMA promotion is not selected because only 22,000
cycles are DMA-only and most DMA occupancy overlaps UART. CPU/decode block work remains available
for OPT3, after event scheduling is stable.
