# NEXT3 SD CMD8 CRC Fault B first emulator result

This directory preserves the first and only pre-fix emulator run of the exact
hardware-confirmed Fault B BIN. The hardware rejected bad CMD8 CRC `0x85` with
R1 `0x09` (idle plus COM_CRC_ERROR). Frozen backend `4a908648` instead discarded
that CRC, returned normal R1 `0x01` and R7 `000001aa`, completed initialization,
and reported application PASS. The closed classification is therefore
`false_accept`.

The scenario was intentionally outcome-unbiased: it stopped on the Fault B
EVIDENCE prefix whether the application said PASS or FAIL. Consequently the
captured UART ends in the middle of the repeating EVIDENCE line. It already
contains the complete CMD8 response, complete initialization result, and
complete PASS RESULT marker; the structured report also records verdict PASS,
and the snapshot records the green final state. This capture boundary is not a
reason to rerun or replace the first observation. Any later run must be labeled
supplemental or post-fix and must never overwrite this directory.

This record creates the first negative denominator. For this bounded dataset
only, detection is 0/1 and false acceptance is 1/1. It is not a general defect
detection or false-acceptance rate for the emulator.

Backend modification was forbidden until this result was preserved and
classified. That boundary is now complete. The next step is a new backend
revision that implements exact CMD8 CRC7 rejection, followed by local
A1/Fault/positive regression validation. No GitHub Actions run is required.
