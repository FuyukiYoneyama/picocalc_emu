# OPT3-A immutable-XIP decode cursor profile

## Purpose

OPT3-A measures whether a CPU-side decode cursor is worth prototyping after OPT2 closed without a
production promotion. The profiler does not batch instructions and does not change the scheduler.
It records where decode-cache lookups occur and the dynamic length of hit-only sequential runs in
the current immutable XIP model.

The profile is an opportunity bound, not a speedup prediction. It is instrumented and is not valid
for wall-time comparison.

## Reproduction contract

- backend: `0b99b2eabe23205b3c6ac194dcdf016a53de554d`, clean
- profiler feature: `event-horizon-profiler`
- profiler schema: 3
- target: `picotetris-opt1b`, revision 5
- firmware source: `picotetris` commit `fed84f358d7dcadb1457752e687355ddb1875c48`
- firmware BIN SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- Serial execution, quantum 1, PIO RGB565 LCD, PSRAM, keyboard, FAT32 SD

The firmware was regenerated from the fixed source with Pico SDK 2.2.0. Its UF2 SHA-256 was
`44ec62270175aac16add07ca8d7c99abb0942bcff341c4c36c0d884fc857e274`, matching the registered
artifact. The profile runner was built clean with:

```bash
cargo build --release --locked -p picocalc-harness \
  --features event-horizon-profiler --bin picocalc-run
```

The canonical run command is the OPT2-D command with the same firmware, boot ROM and scenario,
writing `--event-horizon-profile running-event-horizon-profile.json`. Exact behavior was checked in
a separate clean `behavior-trace` build/run; profile and behavior capture were not combined.

## Exactness

Both runs passed all 85 scenario steps at 927,528,660 cycles and 3,715,000 virtual microseconds.
They retained the registered values:

- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`;
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`;
- PSRAM tick count `305747113`;
- behavior SHA-256 `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`;
- event stream SHA-256 `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`,
  173,498,680 events and all nine domain digests.

## Result

Core 0 made 172,373,954 immutable-XIP cache hits and 295,794 misses, a 99.8287% hit rate.
Immutable XIP supplied 99.9746% of all cache hits. Core 1 did not execute.

There were 37,776,563 immutable-XIP hit-only sequential runs, averaging 4.563 instructions.

| minimum run length | hit-instruction mass | immutable-XIP hit share |
|---:|---:|---:|
| 2 | 172,338,762 | 99.9796% |
| 4 | 86,778,680 | 50.3433% |
| 8 | 47,044,211 | 27.2919% |
| 16 | 23,313,232 | 13.5248% |
| 32 | 942,483 | 0.5468% |
| 64 | 18,085 | 0.0105% |

Runs ended 37,756,069 times on post-execute PC redirect, 20,218 times on an XIP miss and 275
times before a pending exception fetch. One run remained open and was included only by the
non-mutating final snapshot. The termination sum plus that open run equals the episode count.

During the measured interval, 9,243,286 invalidation addresses were observed, all in SRAM. There
were no XIP, ROM, bulk or all-cache invalidations. This supports the current-model immutability
assumption for the measured XIP workload; it does not waive future invalidation requirements if
SSI program/erase is implemented.

## Decision

The data supports a small OPT3-B prototype, but not a large block-batching design. Half of the hit
instruction mass lies in runs of at least four instructions, while only 0.547% lies in runs of at
least 32. Nearly every run ends at a branch or other PC redirect.

OPT3-B is therefore restricted to a short immutable-XIP decode cursor. It must keep Serial
scheduling at one instruction, preserve every per-instruction exception/IRQ/peripheral boundary,
and fail closed outside actual XIP flash. SRAM, XIP-SRAM, ROM mutation, dual-core shared code and
Threaded execution remain excluded. Only an exact candidate may proceed to trace-OFF A/B timing.
