# NEXT3 SD CMD8 CRC Fault B artifact freeze

Fault B is derived from hardware-passed A1 commit `f942b8eb0008`. Its three
executable changed paths contain only the application identity, final EVIDENCE
namespace and expected trace CRC identity, and transmitted CMD8 CRC byte
`0x87 -> 0x85`. CMD0, CMD8 argument, SPI setup, CS framing, polling, R7 parsing,
timeouts, filesystem and key behavior are unchanged. Two documentation files
describe only this already-frozen delta and the hardware-first boundary.

The expected trace comparison also changes to `0x85` deliberately. Leaving it
at `0x87` would make the application reject its own intentionally transmitted
test byte before the backend's response behavior could be classified. Fault B
therefore passes only if the trace shows `0x85` *and* the card model returns the
normal CMD8 response and initialization succeeds; hardware CRC rejection still
produces the frozen red FAIL result.

The canonical tree and an independent clean clone built with the same
generator commit, SDK, toolchain, Ninja generator, and timestamp produced
identical BIN and UF2 hashes. The source bundle contains the complete history
and resolves HEAD to `e78cabbe2041`.

Fault B has not been executed in the emulator. The UF2 must run on PicoCalc
hardware through `uf2loader` first. Only exact R1 `0x09` at CMD8, with the
predeclared reason fields and no unrelated failure, unlocks the first backend
run. Any other complete result is preserved as `inconclusive` without retry or
oracle adjustment.
