# OPT3-C compact predecoded dispatch key

## Purpose

OPT3-C tested a compact top-level dispatch classification stored in the existing 12-byte
`DecodedOp` entry. The prototype used flags bits 1..6, added no successor copy, staging, or clear,
and kept Serial core 0 scheduling at one instruction per step. It was feature-gated with
`compact-dispatch-key-prototype`; no production optimization was added.

## Reproduction contract

- baseline backend: `e58e67f1be69357edec0bd47e879039f47a42648`
- candidate backend: `3819a9d093b8ce980a61724ac8ab33ffe3003ec3`
- revert: `04b2eb2fb26f126e848b5c041177324954a98290`
- candidate runner SHA-256: `604d0bc5f7f615c31791a283159e1aad4811cf1990366e700dbd45e579addbf0`
- baseline runner SHA-256: `332a6ea5938472447b313397fdd261c4e2a6753715b3b16659bb8f1077071a1c`
- target: `picotetris-opt1b`, revision 5
- Serial execution, quantum 1, PIO RGB565 LCD, PSRAM, keyboard, FAT32 SD

## Exactness result

The behavior artifact passed 85/85 steps at 927,528,660 cycles and 3,715,000 virtual microseconds.
UART, framebuffer, PSRAM tick count, behavior SHA, the 173,498,680-event stream and all nine domain
digests matched OPT1-B exactly.

## Performance result and decision

Trace/proof-OFF clean A/B/A/B/A/B screening produced baseline times 27.18, 26.26 and 26.72 seconds,
versus candidate times 25.31, 25.61 and 25.77 seconds. Medians were 26.72 and 25.61 seconds:
`4.1541916168%` improvement, below the required 5% threshold. Pair improvements were 6.8800588668%,
2.4752475248%, and 3.5553892216%. All six runs were exact, but the candidate was rejected and reverted;
formal ten-run promotion measurement was not performed.

The CI run `31299159125` completed successfully on revert head
`04b2eb2fb26f126e848b5c041177324954a98290`.
