# NEXT-1 PicoEdit first blind run

This directory was created and committed before the first firmware execution.
`input-contract.json`, the scenario, artifact hashes, backend commit and runner
parameters are therefore frozen independently of the observed result.

The first execution wrote `run-report.json`, `uart.log`, `picoedit-final.png`,
and `final-framebuffer.png` here. It passed on the frozen backend without a
backend or expected-output change: 10/10 scenario steps, 765,299,822 cycles,
64-byte readback and the frozen output SHA-256, no exception, no unsupported
MMIO, and no dropped key event.

One final Ctrl release remained queued because the scenario completed as soon
as the save-pass UART marker appeared. The frozen acceptance contract requires
zero dropped events, not an empty queue, so this does not alter the first-run
PASS. A registered regression scenario may add a post-save drain wait as a new
scenario revision; this first observation and its original scenario hash stay
unchanged.

The canonical application BIN and UF2 were produced by the same clean build.
The BIN is the emulator input; the UF2 is reserved unchanged for the later
physical PicoCalc correlation.
