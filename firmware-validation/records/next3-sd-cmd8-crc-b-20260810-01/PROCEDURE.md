# Fault B PicoCalc procedure

Use the normal PicoCalc application path through `uf2loader`. BOOTSEL is not
required.

1. Verify
   `/home/fuyuki/pico_dvl/codex/picocalc-next3-sd-crc-fault/build/picocalc_app.uf2`
   has SHA-256
   `43ea10982d6f9b1d1adf9565b2b88f8b1866ddd60410b4ae53fda8e2f9a3e958`.
2. Copy it to the SD card's `pico1-apps` directory under a clear name such as
   `NEXT3SDB.uf2`.
3. Start USB UART capture before launch, then start the UF2 from `uf2loader`.
4. Do not press any application keys. Wait until a complete
   `[NEXT3][SD_CMD8_B][EVIDENCE]` line has repeated at least three times.
5. Save the complete UART log and take one photograph of the stable final
   screen.

Do not retry a complete result merely because it differs from the oracle. If
the boot/source identity or complete final marker is absent because capture
started late, one capture retry is allowed. Otherwise the first complete
hardware result is authoritative.

The frozen expected result is:

- boot `app=next3-sd-cmd8-crc-b`, `app_git=e78cabbe2041`,
  `bsp_git=5a27dc7a0085-dirty`, build `2026-08-10T05:30:00Z`;
- card present;
- CMD0 argument `00000000`, CRC `0x95`, R1 `0x01`;
- CMD8 argument `000001aa`, transmitted CRC `0x85`, R1 `0x09`;
- R1 contains idle and COM_CRC_ERROR, without illegal-command, address-error,
  or parameter-error;
- initialization and application FAIL at CMD8, no later initialization command
  and no filesystem access;
- stable red center and bottom status regions.

If any field differs, preserve the result as `inconclusive` and do not run the
BIN in the emulator.
