# I2C-EXT E5 emulator evidence

This evidence records three local runs of the same `Picocalc_Clock.bin` using
the same `picocalc-rtc-env-v1` fixture and clean `picoem-picocalc` backend
commit. The runner returned `verdict=pass` on all three runs.

The sidecar is schema 2 and reports five attached addresses: keyboard `0x1f`,
DS3231 `0x68`, AT24C32 `0x57`, AHT20 `0x38`, and BMP280 `0x77`. All 26 address
phases ACKed; unknown addresses, data NACKs, and protocol errors are zero. The
transaction digest, primary report, UART bytes, and framebuffer PNG are byte
identical across all three runs.

This is the complete E5/E6 evidence. The exact UF2 listed in `manifest.json`
was run on a PicoCalc through the normal `uf2loader` path. The supplied physical
UART log confirms the same build identity (`git=f04982c`, `dirty=0`), the
startup probe for RTC, EEPROM and keyboard, and successful AHT20/BMP280 read
paths. Physical sensor values are environment-dependent and are not compared
with the deterministic emulator fixture. The target is active and the bounded
`i2c-external-rtc-env-v1` capability is recorded in
`firmware-validation/capability.json`.

The runner was invoked locally; GitHub Actions was not used.

## Physical correlation record

Use the normal PicoCalc `uf2loader` path for this exact artifact:

```text
/home/fuyuki/pico_dvl/codex/picocalc_emu_ext/i2c-ext-e5/build/Picocalc_Clock.uf2
SHA-256: 1d3223816f5d87f09a9ac3b56620037f838a43e0077f505254f87a52f89aa962
```

The received UART evidence contains:

1. `STARTUP PROBE rtc=PASS eeprom=PASS keyboard=PASS`;
2. a `Sensors:` section with a successful `AHT20` line and a successful
   `BMP280` line; and
3. the exact UF2 SHA above, recorded in `manifest.json` together with the
   original source-log SHA and normalized stored-log SHA.

The normalized stored log is `hardware-uart.log`; the original supplied log is
identified by `source_log_sha256` in `manifest.json`. No comparison of live
environment values against the emulator fixture is implied.
