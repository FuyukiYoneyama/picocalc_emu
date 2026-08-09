# NEXT-2A v2 USB late-attach evidence acceptance

The first physical run of v1 displayed all five PASS results but produced two empty USB serial
captures. That result is preserved in
`next2-multicore-hardware-attempt-20260809-01`; the frozen v1 requirement for a complete UART log
was not weakened after observation.

Contract `next2-multicore-hardware-evidence-v2-20260809` was committed before this application
change. Application commit `e9e99f0bfde7b2706fbe7f5a2a92331eed141c98` leaves every v1 phase,
fixed value, initial marker and LCD result unchanged. Only after the initial final verdict, it emits
the same complete five-marker block every 1,000 ms. It does not query USB state, wait for a monitor,
rerun a phase, or redraw the final screen.

The formal scenario still stops at the first verdict. Three normal CLI executions passed at
152,548,092 cycles and 615 ms; report, UART, timeline and PNG are byte-identical. The final RGB565
framebuffer hash and PNG hash are the same as v1. A separate 500,000,000-cycle probe continued
beyond scenario completion and observed exactly two copies of every marker with no exception or
unsupported MMIO, proving that late attachment has an evidence source.

Luna independently built detached clean clones in two separate `/tmp` paths using Pico SDK 2.2.0,
Ninja and timestamp `2026-08-09T11:30:00Z`. Both reproduced canonical BIN
`a8816759...0649` and UF2 `2e19d565...573f` exactly.

This record accepts the emulator and reproducible-build half of v2. Physical-device functionality
already passed on v1, but formal same-artifact hardware correlation remains pending until the v2
UF2 yields one complete repeated UART marker block and one final five-PASS photograph. No key input
or monitor-open timing is required.
