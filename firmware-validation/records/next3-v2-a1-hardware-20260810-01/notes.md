# NEXT3 v2 A1 hardware correlation

The supplied UART log and photograph establish that the A1 positive control
passes on PicoCalc hardware. The boot identity matches canonical source commit
`168a65d9f820`; all five solid fills and the red/green/blue/white pattern read
back exactly, SD and PSRAM pass, and the final evidence marker repeats 14 times
without changing.

The operator performed the frozen normal-user deployment procedure through
`uf2loader`; BOOTSEL was not used. The UART stream does not itself encode the
loader path or the UF2 SHA. Artifact continuity therefore consists of the
pre-deployment UF2 hash, clean-clone reproducibility, the embedded source/build
identity, and the operator-supplied run evidence. This limitation is explicit
rather than presented as an in-band cryptographic attestation.

The original photograph contains GPS-bearing EXIF. It remains untouched in the
operator log directory. The repository copy removes metadata; decoded RGB SHA
is identical before and after sanitization.

A1 now satisfies both halves of the positive-control gate. Fault B may be
implemented, but it must change only write-side CS framing and firmware
identity. It must be run on hardware before its first emulator execution.
