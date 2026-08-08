# R5 emulator preflight notes

This record fixes the emulator half of the R5 single-BIN hardware-correlation
contract. The same registered `PicoTetris_R5.uf2` must be used on the physical
PicoCalc; no separately-built diagnostic firmware is accepted.

The firmware performs LCD, PSRAM, FAT/SD, audio-stream, deterministic line
clear, game-over, and restart checks before entering keyboard coverage. The
emulator scenario then supplies all 67 physical keys from the official
PicoCalc keyboard firmware table. Up and Down use the official repeat behavior
(`pressed`, `pressed`, `released`); Caps is sent last.

The hardware half intentionally does not require a continuous scripted key
sequence or a mid-game photograph. Keys may be pressed in any order and retried
without a timeout. Completed-key state is saved on the SD card and resumes after
power loss. The operator saves the full UART log, confirms the audible tone,
and takes one photograph only after the stable final PASS screen appears.

`result=pass` applies only to this reproducible build and emulator preflight.
`hardware_correlation_completed=false` remains authoritative until the physical
PicoCalc evidence is recorded.

`run-report.json` is the report produced through the registered
`picocalc.py test --target picotetris-r5` path; its `framebuffer.png` field is
therefore null because PNG output is not part of the target contract. `final.png`
was captured in an auxiliary run of the same BIN/backend/scenario with
`--fb-png`. Its RGB565 digest, cycle count, UART digest, and scenario timeline
match the registered run; the PNG is supporting visual evidence rather than an
input to the pass verdict.
