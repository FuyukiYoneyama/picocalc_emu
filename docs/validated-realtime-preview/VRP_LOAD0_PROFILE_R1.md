# VRP-LOAD-0 profile r1

Status: **prototype implemented; clean-clone build reproducible; 1 virtual-second runtime/input smoke passed; 120-second vertical slice pending**
Recorded: 2026-08-29

This is the first versioned implementation contract for the repository-owned
sustained-load fixture. It is a prototype profile, not a `realtime-1x-qualified`
verdict and not yet an active firmware target in the registry.

## Identity

| item | pinned value |
| --- | --- |
| source repository | `picocalc_emu` |
| source commit | `40a9e07ca34c895cb90b4a1af550e5ed236a26c6` |
| source path | `reference-projects/vrp-load0-sustained` |
| source license | repository root MIT license |
| application version | `vrp-load0-r1` |
| LCD variant | `pio-rgb565` |
| duration | 120 virtual seconds |
| scenario | `scenarios/vrp-load0-r1.json` |
| scenario SHA-256 | `bbd319321fe7e7373681d73bb823ea4bcb72d5054c40742fe7878caf2824be2d` |

Checked-in source file hashes:

- `CMakeLists.txt`: `d99f062e9bb01f3a442ea3a772955ddb67f31e4f9c881a2f0dca9bd8f07a3410`
- `README.md`: `6c53ebc65eaf6ed50946cb3680c53f64000d838fe5be0dd28bb5ddd87157be8d`
- `app/main.cpp`: `a46167f921186a2b13266410d987a11dee1621fbeafb43ef41b3a19d162f8298`

The following artifact pair is a bounded, non-formal one-virtual-second smoke
build. Two independent clean clones of the source commit above, using the
same toolchain, fixed timestamp, and CMake cache, produced identical values:

- `build-smoke/picocalc_app.bin`: `4e66d504b6fe03bdf753242a8c82f900c80c398a50578b0e48c4d9671db361f8`
- `build-smoke/picocalc_app.uf2`: `1f24954bd25644f0079392f584a0a47deec0a7f60f53eab0f2950ca06c03b754`

These are smoke-build outputs, not an active registry target and not a
qualification artifact. The default 120-second artifact remains pending.

## Bounded runtime smoke record

The final source commit was run with the clean backend runner below. This is a
pre-gate implementation smoke, not the required 1--2 virtual-minute
vertical-slice gate or a formal target validation.

| item | observed value |
| --- | --- |
| backend | `picoem-picocalc@65c795e87321e79b960ac8a7495a205de6a24ec0` |
| backend worktree | clean (`dirty=false`) |
| runner SHA-256 | `613aa318e546cea1b89934e2ee3091b640ca8cf4860abfefa7f668ec0395bf2c` |
| bootrom SHA-256 | `9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81` |
| execution | `picocalc`, `pio-rgb565`, PSRAM + keyboard, Serial, quantum 1 |
| input smoke scenario | temporary 50 ms offset / 25 ms gaps; SHA-256 `a517152143bc8aba9fd8b0a8da4b423bf55c519a28fa4ef1c063a66bfd18c292` |
| stop | `scenario_done`, 384,997,345 cycles, report elapsed 1,545,000 us |
| result interval | 1,000,028 us, 30 frames, frame digest `0xdae6681f`, max frame lag 45,565 us |
| LCD observation | 3,174,400 pixels written, 0 dropped, 320x320 framebuffer |
| audio result interval | 48,384 produced / 48,128 consumed, 0 firmware underruns, 0 write drops |
| audio sink observation | 48,000 Hz, 49,257 DMA writes, 0 unexpected gaps; report-wide timer misses 1,385 |
| CPU/input | core0 14,628 units; core1 27,459 units; 4 keyboard events delivered |

The audio sink and report-wide counters include the short post-result UART
observation window needed for the terminal marker. The firmware `RESULT` line
is the authoritative one-second interval record. The high frame lag and the
report-wide timer-miss diagnostic are recorded observations, not silently
converted into a pass. No threshold decision has been made.

Smoke output manifest (not checked in as formal evidence):

- report JSON: `863c198326cd7274060e9d5be6545dc39044d6c6675ac0ae0f1962eaee14487a`
- UART capture: `a72417653a37839ae7a4a090d718551a5ef506fe1bde8476b69ac8bb7c6e00db`
- audio-analysis JSON: `7cfae1ec44842b41b4e01138f59a346d0397e9c3c80cae1b9640c139886231b2`

The checked-in 1,000 ms-offset scenario was not used with this one-second
firmware build because its input sequence begins at the completion boundary.
It remains the scenario for the pending 120-second vertical slice and later
qualification runs.

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
- The ring is prefilled before launch; after core 1 starts, that core services
  the producer while core 0 performs display and arithmetic work. The BSP
  documents this core-1 producer/DMA-IRQ arrangement as the safe concurrent
  path. The completion record reports produced/consumed samples, IRQs,
  underruns, write drops, and ring level. The backend schema-8 `audio_sink` is
  the authoritative digital observation for a later target record.

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
git -C <repro-root>/source checkout --detach 40a9e07ca34c895cb90b4a1af550e5ed236a26c6
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

The pending formal 120-second headless run, using the clean backend runner, is:

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

This formal command has not yet been run successfully for r1. The earlier
exploratory run was intentionally stopped before the current source commit and
is not evidence. The bounded smoke above passed, but no validation record,
receipt, active registry target, threshold decision, or VRP-5 qualification
result is claimed by this profile.

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
