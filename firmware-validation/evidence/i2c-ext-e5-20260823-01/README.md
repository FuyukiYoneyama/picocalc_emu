# I2C-EXT E5 emulator evidence

This evidence records three local runs of the same `Picocalc_Clock.bin` using
the same `picocalc-rtc-env-v1` fixture and clean `picoem-picocalc` backend
commit. The runner returned `verdict=pass` on all three runs.

The sidecar is schema 2 and reports five attached addresses: keyboard `0x1f`,
DS3231 `0x68`, AT24C32 `0x57`, AHT20 `0x38`, and BMP280 `0x77`. All 26 address
phases ACKed; unknown addresses, data NACKs, and protocol errors are zero. The
transaction digest, primary report, UART bytes, and framebuffer PNG are byte
identical across all three runs.

This is the emulator half of E5 and the versioned-validation input for E6. It
does not claim physical correlation. The pending target remains
`pending-revalidation`, and `capability.json` is intentionally unchanged until
the exact UF2 listed in `manifest.json` is run on a PicoCalc and the physical
UART confirms the same address/read paths. The historical `RTC/` hardware logs
are not substituted for this same-artifact run.

The runner was invoked locally; GitHub Actions was not used.

## Remaining physical step

Use the normal PicoCalc `uf2loader` path for this exact artifact:

```text
/home/fuyuki/pico_dvl/codex/picocalc_emu_ext/i2c-ext-e5/build/Picocalc_Clock.uf2
SHA-256: 1d3223816f5d87f09a9ac3b56620037f838a43e0077f505254f87a52f89aa962
```

After boot, collect the UART output and send one line, `help`, followed by a
newline. The required human-supplied evidence is:

1. `STARTUP PROBE rtc=PASS eeprom=PASS keyboard=PASS`;
2. a `Sensors:` section with a successful `AHT20` line and a successful
   `BMP280` line; and
3. the exact UF2 SHA above, plus the UART log and a photo or screenshot of the
   running application if available.

The measured sensor values do not have to equal the deterministic emulator
fixture. A failed or missing line is not silently converted to pass; it leaves
the target pending and keeps `capability.json` unchanged.
