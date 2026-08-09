# OPT3-B short immutable-XIP decode cursor

## Purpose

OPT3-B tested whether copying up to three already-decoded sequential XIP instructions into a
short per-core cursor reduces decode-cache lookup overhead without changing instruction scheduling.
The scheduler remained one instruction per step. The prototype was feature-gated and was restricted
to Serial core 0 and the real immutable XIP flash range `0x10000000..0x14000000`.

## Safety boundary

The prototype never fetched or decoded ahead. It copied only existing valid `DecodedOp` entries from
the direct-mapped decode cache. It discarded the cursor on redirect, synchronous fault, prefetch
exception, XIP entry/region/all invalidation, or scope exit. SRAM, XIP-SRAM, ROM, Threaded execution
and core 1 were fail-closed exclusions. SRAM-only invalidation did not discard an XIP cursor.

## Exactness result

Candidate commit `0e22846186e68d2d726e49817a9f74c246f517ca` passed the complete PicoTetris
scenario: 85/85 steps, 927,528,660 cycles and 3,715,000 virtual microseconds. UART,
framebuffer, PSRAM tick count, behavior SHA, the 173,498,680-event stream and every count/hash in all
nine event domains matched OPT1-B exactly.

The proof-only build recorded 134,612,445 cursor hits, 38,102,585 misses, 57,047,061 installs,
168,959,816 staged entries and 32,017,974 clears on core 0. Core 1 remained disabled with zero
activity. This proves the candidate exercised the intended path; exactness did not result from a
dormant feature.

## Performance result and decision

A separate trace/proof-OFF clean A/B/A/B/A/B screen produced baseline times 26.44, 25.66 and
25.98 seconds, versus candidate times 26.71, 27.13 and 29.09 seconds. Medians were 25.98 and
27.13 seconds: `-4.4264819092%` improvement, i.e. a regression. All six runs remained exact.

The likely cost is eager cursor construction: 168.96 million entries were staged for 134.61 million
hits, while redirects and other boundaries caused 32.02 million clears. The copying and cursor-state
traffic cost more than the cache lookup it replaced. Because the screen clearly failed the 5% gate,
a formal ten-run promotion measurement was not performed.

The candidate was rejected and reverted by commit
`e58e67f1be69357edec0bd47e879039f47a42648`. The active backend source is byte-equivalent to baseline
`0b99b2eabe23205b3c6ac194dcdf016a53de554d`; no target, pin or validation attestation changed.
Backend CI run `31293556450` passed test, fmt and Clippy on the revert head.

The next investigation is OPT3-C: a compact predecoded dispatch key stored with each existing cache
entry, without eager successor copying. It remains feature-gated and must pass the same exactness and
performance gates before adoption.
