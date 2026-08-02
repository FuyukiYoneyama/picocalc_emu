# Firmware backend development direction

`picocalc_emu` will use [`FuyukiYoneyama/picoem-picocalc`](https://github.com/FuyukiYoneyama/picoem-picocalc) as the primary RP2040 firmware-execution backend.

`picoem-picocalc` is an independent derivative of `0x4D44/picoem`. It retains the upstream Git history and the original `MIT OR Apache-2.0` licensing, while being developed separately for PicoCalc integration. It is private during the initial feasibility and stabilization work, with the intention of making it public before `picocalc_emu` depends on it as a publicly buildable component.

## Role in picocalc_emu

The firmware backend runs the same RP2040 ELF, BIN, or UF2 firmware that is used on PicoCalc hardware. It connects the emulated RP2040 to deterministic PicoCalc board-device models and produces test artifacts such as UART logs, framebuffer images, traces, filesystem results, and structured reports.

The firmware backend complements the host-device-model backend; it does not replace it.

- **Host backend:** fast native execution for application logic, UI, input, files, sanitizers, and repeated scenario tests.
- **Firmware backend:** same-binary verification for RP2040-specific behavior, including GPIO, PIO, DMA, interrupts, multicore execution, and peripheral register use.

Most development tests should use the host backend. The firmware backend is used when binary-level or RP2040-specific behavior matters and its capability manifest declares the required subsystems supported.

`rp2040js` remains a comparison reference for RP2040 peripheral behavior,
implementation techniques, and test structure. It is not the primary backend
connected to `picocalc_emu`, and the two implementations are not forced into one
shared device path.

## Integration policy

- Keep `picoem-picocalc` in a separate repository rather than copying its source tree into `picocalc_emu`.
- Pin the backend to an exact commit and record the commit in test artifacts.
- Treat `ExecutionModel::Serial` as the correctness reference until the threaded model is proven equivalent for the relevant PicoCalc workloads.
- Keep PicoCalc-specific device behavior in board adapters and external-device models where possible; avoid embedding PicoCalc assumptions in the generic RP2040 core.
- Preserve upstream history, copyright notices, licenses, and attribution.
- Incorporate upstream changes selectively after review and regression testing; do not merge them automatically.
- General-purpose fixes suitable for the original project may be prepared separately for upstream contribution.

## Initial implementation order

1. Build and run the inherited `rp2040-emu` Serial test suite without PicoCalc modifications.
2. Load a PicoCalc BIN/ELF image and reach the `[PICOCALC][BOOT]` log line.
3. Decode the default PIO0 RGB565 LCD path and reproduce the initialization transaction.
4. Render deterministic 320x320 framebuffer output and compare hashes or PNG artifacts.
5. Connect the keyboard model through I2C1.
6. Add SPI0 SD-card support and deterministic filesystem fixtures.
7. Connect PIO1 PSRAM and its MISO feedback path.
8. Add PWM/DMA audio observation.
9. Validate multicore firmware, SIO FIFO, WFE/SEV, interrupts, PIO, and DMA interactions.
10. Add UF2 loading, GDB/debug support, and broader capability reporting as needed.

The first feasibility gate is deliberately limited to the default `pio-rgb565` LCD variant with LCD DMA disabled. The backend is promoted to a supported `picocalc_emu` component only after that path produces stable, repeatable results and the inherited emulator regression suite remains green.

## Public release requirement

A public `picocalc_emu` release must not require access to a private dependency. Before the firmware backend becomes a normal public build dependency, `picoem-picocalc` must be publicly accessible or replaced by an equivalent publicly reproducible source package. Third-party notices and license files must be preserved in both source and binary distributions.
