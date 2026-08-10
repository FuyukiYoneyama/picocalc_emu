# Fault B PicoCalc procedure

Use the normal PicoCalc application path. BOOTSEL is not required.

1. Verify `picocalc-next3-lcd-fault/build/picocalc_app.uf2` has SHA-256
   `8f45245d8b0c8f1d543d1f909368ca4c48438e898352b48c3afcdaa172cb291f`.
2. Copy it to the SD card's `pico1-apps` directory under a clearly identifiable
   name such as `NEXT3V2B.uf2`.
3. Start it from `uf2loader` and capture USB UART from the first boot line.
4. Do not press any keys. Wait until the
   `[NEXT3][LCD_CS_V2_B][EVIDENCE]` line has repeated at least three times.
5. Save the complete UART log and take one photograph of the stable final
   screen.

Do not repeatedly retry a complete run. If boot identity is absent because the
serial capture started late, restart once with capture active. If identity is
present, the first complete LCD result is authoritative even when it differs
from the oracle.

Expected frozen result:

- black/white/red/green/blue solid fills: all PASS;
- final pattern readback: red, red, red, red;
- pattern mismatches: 3;
- `app=fail`, `sd=pass`.

If any field differs, preserve it as `inconclusive` and do not run the BIN in
the emulator.
