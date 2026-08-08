# R5 physical PicoCalc correlation notes

This record closes the physical-device half of the R5 single-artifact
correlation. The immutable emulator preflight remains in
`r5-preflight-20260808-01`; this directory adds the physical UART, stable final
PASS photograph, SD-persisted keyboard progress, and a compact excerpt of the
operator's microphone recording.

The UART contains two sessions. The first was interrupted after an early Caps
press. The second reports `resumed=1`, reruns every automatic check, completes
all 67 physical keys, and ends with the exact accepted verdict:

```text
[R5_DIAG_VERDICT] lcd=pass psram=pass sd=pass audio=pass tetris=pass keyboard=67/67 io_errors=0 progress=saved overall=pass
```

`PCR5KEY.DAT` independently confirms the persisted result. Its magic, schema,
R5 app tag, and CRC32 are valid; all 67 pressed and released bits are set; both
repeat-required Up and Down bits are set; and unused bits are zero.

The final photograph visibly reports `R5 ALL PASS` for LCD, PSRAM, SD FAT32,
audio path, Tetris, and keyboard 67/67. The first ten seconds of
`IMG_8923.MOV` were losslessly transcoded to `reference-tone.flac`. The dominant
FFT bin is 984.375 Hz, consistent with the firmware's 1 kHz reference tone.
The original video is kept outside Git because its SHA-pinned 314,676,611-byte
size exceeds GitHub's normal per-file limit.

The operator also observed that some physical keys felt less responsive and
needed retries. R5 therefore proves keyboard reachability and protocol
conformance, not input quality. A press that produces no controller event is
not visible in the UART log, so this evidence cannot measure miss rate,
actuation force, or press-to-event latency. That limitation remains explicit
and does not weaken the 67/67 reachability result.

With the same registered artifact passing emulator preflight and hardware,
OPT1-A moves from `candidate` to `promoted`. The historical OPT1-A and R5
preflight records are not rewritten.
