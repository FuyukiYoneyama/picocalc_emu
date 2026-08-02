# BSP 0.8.8 quality diagnostic

This is the dedicated HV-1 firmware. It does not mount or write the SD card and
does not start audio. It exercises the two pending canonical BSP record fields:

- 100 repeated LCD GRAM write/readback comparisons, including failure streak
  and recovery accounting.
- Guided Up, Down, Enter and Escape input. Up and Down must be held long enough
  to produce `Pressed`, `Hold` and `Released`; Enter and Escape require
  `Pressed` and `Released`.

The screen and UART show the current action. A failed phase does not prevent the
remaining phase from running. The final UART line is `[BSP_DIAG_VERDICT]`.

Build from the `picocalc_emu` root with a fixed timestamp:

```sh
python3 tools/picocalc.py build \
  --project diagnostics/bsp-quality \
  --lcd-variant pio-rgb565 \
  --build-timestamp YYYY-MM-DDTHH:MM:SSZ
```

The local test artifact name is always
`diagnostics/bsp-quality/build/PicoCalc_BSP_Diagnostic.uf2`.

