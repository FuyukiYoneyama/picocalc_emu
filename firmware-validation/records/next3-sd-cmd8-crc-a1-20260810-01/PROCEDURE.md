# PicoCalc A1 hardware procedure

1. Confirm the UF2 SHA-256 is
   `be9c0e8deda02307e34a96c11cec21255f1e197902920d1fe8e05f9d472a9ffd`.
2. Copy `picocalc_app.uf2` to the PicoCalc SD card application directory.
3. Start it once from `uf2loader`. BOOTSEL is not required.
4. Do not press any application key. Wait until the screen is stable.
5. Save the complete USB UART log and take one final photograph.

The repeated decisive marker must show CMD0 argument `00000000`, CRC `0x95`,
R1 `0x01`, CMD8 argument `000001aa`, CRC `0x87`, R1 `0x01`, R7
`000001aa`, `filesystem=none`, and `app=pass`.
The final screen must have a white strip at the top and green centre/bottom
regions. A missing identity or truncated UART is a capture failure and may be
retried once. A valid protocol mismatch is evidence and must not be retried or
rewritten into the oracle.
