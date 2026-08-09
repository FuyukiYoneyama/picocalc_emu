# NEXT-2A v2 hardware correlation notes

## Verdict

The registered `picocalc-multicore-r2` artifact passed on the physical
ClockworkPi PicoCalc. This closes NEXT-2A's frozen v2 hardware-evidence
contract without changing its requirements after the run.

The USB CDC log contains 72 consecutive, byte-identical copies of the complete
five-marker block. Every fixed value and every phase verdict matches the frozen
contract. The final photograph independently shows `PASS` for LAUNCH, FIFO,
WFE/SEV, IRQ1, and OVERALL.

## Evidence history

The v1 hardware run already showed all five PASS rows, but its one-shot UART
markers were emitted before a late-attached USB CDC monitor could observe them.
That attempt remains preserved separately as incomplete evidence. The v2
contract was frozen before implementing periodic output; v2 changes only the
evidence transport and repeats the immutable final marker block once per second.

This record contains the first complete same-v2-UF2 evidence pair. The periodic
72-block log distinguishes v2 from the one-shot v1 program. The operator supplied
the photograph immediately after the log as the matching final-screen evidence.

## Privacy and preservation

`usb-cdc.log` preserves the supplied bytes, including CRLF line endings.
`final.jpg` is a repository-safe copy. EXIF, GPS, XMP, maker notes, and MPF were
removed while the ICC profile was retained. Its decoded RGB pixels are identical
to the supplied original; both the original-file SHA-256 and the decoded-pixel
SHA-256 are fixed in `record.json`.

## Scope boundary

This acceptance covers the frozen Serial-execution workload: core 1 launch,
bidirectional SIO FIFO, WFE/SEV, and core-local SIO IRQ delivery. It does not
claim Threaded-model conformance, simultaneous device access by both cores,
spinlock-contention timing, core 1 reset/relaunch, or DMA-paced PCM output.
NEXT-2B treats audio output as a separate contract.
