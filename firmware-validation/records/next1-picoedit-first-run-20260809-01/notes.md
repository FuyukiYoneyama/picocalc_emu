# NEXT-1 PicoEdit first blind run

This directory was created and committed before the first firmware execution.
`input-contract.json`, the scenario, artifact hashes, backend commit and runner
parameters are therefore frozen independently of the observed result.

The first execution must write `run-report.json`, `uart.log`, and
`picoedit-final.png` here. A failure is retained as evidence and is not replaced
by a later successful run. No PicoEdit firmware has been run in the emulator at
the time of this pre-run commit.

The canonical application BIN and UF2 were produced by the same clean build.
The BIN is the emulator input; the UF2 is reserved unchanged for the later
physical PicoCalc correlation.
