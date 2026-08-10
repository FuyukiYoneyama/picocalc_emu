# NEXT3 SD CMD8 CRC A1 hardware correlation

The supplied UART log and photograph establish that the SD CMD8 CRC A1
positive control passes on PicoCalc hardware. The boot identity matches source
commit `f942b8eb0008`. CMD0 used argument `00000000`, CRC `0x95`, and returned
R1 `0x01`; CMD8 used argument `000001aa`, the canonical CRC `0x87`, and
returned R1 `0x01` plus R7 `000001aa`. Initialization and the application pass,
while filesystem access and key input remain absent by design.

The complete evidence marker repeats 39 times without changing. The photograph
shows the expected white top strip and green center and bottom regions, with no
red failure region. An independent Luna audit reached the same PASS
classification; the repository verifier checks the recorded hashes and fields
instead of relying on that narrative audit.

The operator used the frozen normal-user `uf2loader` path; BOOTSEL was not used.
The UART stream does not itself attest the loader path or UF2 SHA. Artifact
continuity therefore consists of the pre-deployment UF2 hash, two-build and
clean-clone reproducibility, embedded source/build identity, and the
operator-supplied evidence. This limitation is explicit.

The original photograph contains location-bearing metadata and remains
untouched in the operator log directory. The repository copy has metadata
removed, and the decoded RGB SHA is identical before and after sanitization.

A1 now satisfies both halves of the positive-control gate. Fault B source may
be implemented using only the frozen change budget. Its first emulator run is
still prohibited until the Fault UF2 matches the predeclared hardware oracle.
