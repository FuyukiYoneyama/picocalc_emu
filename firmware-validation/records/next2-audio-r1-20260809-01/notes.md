# NEXT-2B v3 formal emulator acceptance

The `picocalc-audio-r1` target passed three Serial, quantum-1 firmware runs on
backend `d92db1b...`. The report, UART stream, scenario timeline and LCD
snapshot are byte-identical across all three runs. Firmware authority reported
that the public API accepted and drained every producer frame; the independent
backend authority observed the exact post-quantizer DMA stream and timing
structure required by the v3 contract.

Two separate `git clone --no-local` builds of application commit `724b3ac...`
used Pico SDK 2.2.0, Ninja, `pio-rgb565` and the fixed timestamp
`2026-08-09T12:00:00Z`. Their BIN and UF2 files are byte-identical to the
registered artifacts. ELF files are intentionally not claimed reproducible
across build paths.

The two full negative runs used the unchanged passing BIN and deliberately
wrong sink expectations. A count of 49,151 and an all-zero expected digest each
produced exit 1 with `audio_sink_mismatch`, even though every firmware marker
and the final LCD screen still said PASS. `negative-mutations.json` separately
mutates each other contract domain in the saved report; all ten mutations are
rejected by both the field gate and the normalized-report gate. Focused backend
tests exercise malformed width, TREQ and cadence observations at the sink
source.

This is formal emulator acceptance, not physical audio correlation. The same
registered UF2 must still be flashed to a PicoCalc and accompanied by a
periodic UART block, final PASS photograph and acoustic capture. The physical
record is secondary and non-byte-exact; it cannot replace the backend's exact
digital sink oracle.
