# NEXT-3 SD CMD8 CRC A1 baseline

This record freezes the positive control before the bad-CRC firmware exists.
The application uses the canonical CMD8 CRC byte `0x87`, calls only direct SD
initialization, requires no key input, and performs no filesystem operation.

Two builds—one in the source repository and one from an independent clean
clone—produced identical BIN and UF2 hashes. The frozen backend run passed with
CMD0 R1 `0x01`, CMD8 argument `000001aa`, CRC `0x87`, R1 `0x01`, R7
`000001aa`, zero SD block reads/writes, no exception, and no unsupported MMIO.
The scenario waits for the complete evidence suffix before stopping so the UART
record cannot end halfway through the decisive marker.

The green final screen contains 80,384 non-black pixels. Its screenshot is an
emulator observation, not a substitute for the pending hardware photograph.

Fault B is deliberately absent. It remains forbidden to introduce CRC `0x85`
or run a fault BIN in the emulator until this exact UF2 passes once on PicoCalc
through the normal `uf2loader` path.

- UF2: `picocalc-next3-sd-crc-fault/build/picocalc_app.uf2`
- UF2 SHA-256: `be9c0e8deda02307e34a96c11cec21255f1e197902920d1fe8e05f9d472a9ffd`
- BIN SHA-256: `0ae9eea01f87c542cd7c41f1880c42d428c0f143c909dfe116c16e1cf5afce1b`
- source commit: `f942b8eb000858e6f00bb8fde255f27243dfbac8`
- source bundle SHA-256: `ed985de566638e07e0a20e974b351646729b434a6bb05edd349dc5fb162a05da`

The repository `README.md` is application-specific and contains the complete
build command. It supersedes the generic generated-template README that was
removed before this artifact was frozen.

No GitHub Actions run or push was used.
