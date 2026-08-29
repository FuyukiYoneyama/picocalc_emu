# VRP-LOAD-0 sustained-load firmware

This is a repository-owned workload for the Validated Realtime Preview
qualification work. It is deliberately a small deterministic application,
not a fork or a modified checkout of another project.

The default build runs for 120 virtual seconds so the first implementation can
be exercised as a 1--2 virtual-minute vertical slice. The future qualification
target must pin `VRP_LOAD0_DURATION_SECONDS=600` (or longer) in its own build
record; changing that value changes the target contract and must not be hidden
inside an existing artifact record.

The workload does all of the following concurrently:

- updates the complete 320x320 RGB565 panel at a fixed 30 Hz schedule;
- keeps the public stereo PCM stream producer supplied while the BSP's 48 kHz
  PWM/DMA consumer runs;
- runs deterministic arithmetic on both RP2040 cores without sleep or WFE;
- consumes a fixed explicit keyboard event sequence; and
- emits machine-readable start, heartbeat, and completion records on UART0.

The app uses only `picocalc/bsp.h` and Pico SDK multicore APIs. It does not use
or require `Picocalc_NESco`.

## Build

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
python3 ../../tools/picocalc.py build \
  --project reference-projects/vrp-load0-sustained \
  --sdk "$PICO_SDK_PATH" \
  --picotool-dir /usr/local/lib/cmake/picotool \
  --lcd-variant pio-rgb565 \
  --generator Ninja \
  --build-timestamp 2026-08-29T00:00:00Z
```

The output is `build/picocalc_app.bin` and the corresponding UF2.
`picocalc.py build` records the build timestamp and source/BSP identity in its
local build ledger. Formal target registry values are added only after a clean
clone build and an emulator run produce the actual artifact and report hashes.

For a short compile/run smoke, a separate build directory or a clean cache may
pin `-DVRP_LOAD0_DURATION_SECONDS=1`; that is not the vertical-slice or
qualification artifact.
