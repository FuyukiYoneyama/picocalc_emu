# VRP-LOAD-0 profile r1

Status: **build reproducible; runtime vertical slice pending**  
Recorded: 2026-08-29

This is the first versioned implementation contract for the repository-owned
sustained-load fixture. It is a prototype profile, not a `realtime-1x-qualified`
verdict and not yet an active firmware target in the registry.

## Identity

| item | pinned value |
| --- | --- |
| source repository | `picocalc_emu` |
| source commit | `5e950b523e2b76b45d5130e15c9cca58c7c48cfd` |
| source path | `reference-projects/vrp-load0-sustained` |
| source license | repository root MIT license |
| application version | `vrp-load0-r1` |
| LCD variant | `pio-rgb565` |
| duration | 120 virtual seconds |
| scenario | `scenarios/vrp-load0-r1.json` |
| scenario SHA-256 | `bbd319321fe7e7373681d73bb823ea4bcb72d5054c40742fe7878caf2824be2d` |

Checked-in source file hashes:

- `CMakeLists.txt`: `d99f062e9bb01f3a442ea3a772955ddb67f31e4f9c881a2f0dca9bd8f07a3410`
- `README.md`: `687584c61832504242e68dafc8ccdb4c8ed350ec959e541c26772b4cdfb2fe9a`
- `app/main.cpp`: `79c0d4533f1064639ad940c6ea8761e09a492e1c9bd33d477ea979dcf668424d`

The clean-clone build produced:

- `build/picocalc_app.bin`: `15b48017be735fcc89238e1abf6a392eb6d684dcc7f5db0f191fdde85e50ac28`
- `build/picocalc_app.uf2`: `b18fe82bfad991c2151f846d9f7f65e5842b8ba44c16498f4841db98b1882e3e`

The BIN and UF2 values above are build outputs from the source commit shown in
this table. They are not copied into the repository as a second source of
truth.

## Fixed workload contract

### Display

- Public pixel format: RGB565.
- Device profile: PicoCalc LCD B, `pio-rgb565`, 320x320.
- Every scheduled frame calls `picocalc::display::clear()` for the complete
  320x320 viewport. The BSP sends the full pixel transfer in its proven 160
  pixel units; there is no partial-rectangle update in this fixture.
- Frame `n` has the deterministic RGB565 colour derived from
  `xorshift32(0x4c4f4144 ^ (n * 0x9e3779b9))`.
- Frame deadlines are `start + floor(n * 1,000,000 / 30)` virtual microseconds.
  Overdue frames are rendered on later loop iterations; the application never
  drops a scheduled frame to catch up.
- The UART completion record includes the frame count, frame digest, and
  maximum completion lag observed against these deadlines.

### Audio

- Public path: `audio::init()` → signed 16-bit stereo `write_sample()` →
  `audio::start()`.
- Sample rate: the BSP's 48,000 Hz PWM/DMA stream, 512-sample SPSC ring, and
  128-sample DMA half-buffer.
- Sample pattern: a deterministic 96-sample (500 Hz) triangle-like ramp with
  seed `0x00480000`; left and right channels have opposite polarity.
- The producer is serviced throughout display and CPU work. The completion
  record reports produced/consumed samples, IRQs, underruns, write drops, and
  ring level. The backend schema-8 `audio_sink` is the authoritative digital
  observation for a later target record.

### CPU and multicore

- Core 0 executes a deterministic 96-round arithmetic batch between device
  services.
- Core 1 executes a continuous deterministic 256-round arithmetic batch and
  publishes a digest and unit count. It is launched before the start marker.
- During the measured interval the firmware calls no `sleep_ms`, `sleep_us`,
  `WFE`, or idle wait. The only `tight_loop_contents()` path is the
  fail-closed error path or the short post-completion observation window.
- The profile policy is `exact_idle_fast_forward=not_expected`: both cores are
  active during the load interval, so the backend's exact fast-forward of a
  proven both-cores-blocked interval must not be the normal execution path.
  A later report must retain the backend execution/blocked observation rather
  than infer this solely from the wall-clock ratio.
- No CPU cycle, emulated frame, IRQ, PIO/DMA event, device event, or virtual
  audio event is deliberately skipped by the workload.

### Input and stop condition

- Device configuration: board `picocalc`, LCD `pio-rgb565`, PSRAM attached,
  keyboard attached, SD detached, no optional I2C module.
- After the start marker, the scenario waits 1,000 virtual milliseconds and
  injects four fixed raw keyboard events with a 250 ms gap:
  `pressed(0x04)`, `released(0x04)`, `pressed(0x05)`, `released(0x05)`.
- The firmware consumes the events and includes their count and digest in its
  completion record. Host wall clock is not an input source.
- The scenario stops only after `[VRP-LOAD0][COMPLETE]` appears. The runner
  cycle budget is a safety bound, not the workload's time source.

## Reproduction commands

Build from a clean source checkout:

```sh
git clone https://github.com/FuyukiYoneyama/picocalc_emu.git <repro-root>/source
git -C <repro-root>/source checkout --detach 5e950b523e2b76b45d5130e15c9cca58c7c48cfd
python3 <repro-root>/source/tools/picocalc.py build \
  --project <repro-root>/source/reference-projects/vrp-load0-sustained \
  --sdk <pico-sdk-2.2.0> \
  --picotool-dir /usr/local/lib/cmake/picotool \
  --lcd-variant pio-rgb565 --jobs 2 \
  --build-timestamp 2026-08-29T00:00:00Z --generator Ninja
```

The toolchain used for the recorded build was:

- Pico SDK 2.2.0, Git `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`
- ARM GNU 13.2.1
- CMake 3.28.3
- Ninja 1.11.1
- picotool v2.2.0-a4

The intended headless run, after a clean backend runner is available, is:

```sh
<clean-backend>/target/release/picocalc-run \
  --bin <source>/reference-projects/vrp-load0-sustained/build/picocalc_app.bin \
  --bootrom <clean-backend>/roms/rp2040/bootrom-rp2040-b2.bin \
  --board picocalc --lcd-variant pio-rgb565 --quantum 1 \
  --cycles 40000000000 --psram --keyboard \
  --scenario <source>/scenarios/vrp-load0-r1.json \
  --expect-stop scenario_done \
  --expect-uart '[VRP-LOAD0][START]' \
  --expect-uart '[VRP-LOAD0][COMPLETE]'
```

This command has not yet completed successfully for r1. The earlier
exploratory run was intentionally stopped before the source commit and is not
evidence. No validation record, receipt, active registry target, threshold
decision, or VRP-5 qualification result is claimed by this profile.

The backend intended for the next run is
`picoem-picocalc@65c795e87321e79b960ac8a7495a205de6a24ec0`, built as a clean
temporary checkout. The repository backend currently has pre-existing dirty
formatting-like changes, so it is not used as the formal runner input.

## UX boundary

The r1 profile defines continuous-load timing inputs and outputs. It does not
yet claim `1x UX`: the headless runner's wall-clock timer is not an
input-to-visible-response measurement. A same-BIN preview API/GUI smoke and a
separate input-to-visible-response metric must be added before any UI-facing
label uses that term.
