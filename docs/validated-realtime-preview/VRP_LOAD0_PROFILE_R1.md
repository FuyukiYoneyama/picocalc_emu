# LOAD-0（最大級の継続負荷性能テスト0番）— profile r1

Status: **prototype implemented; clean-clone build reproducible; 1- and 2-virtual-second runtime/input smokes passed; 120-second vertical slice and preview-only target admission passed; three-run determinism and preparation gate pending**
Recorded: 2026-08-30
Display name: **LOAD-0（最大級の継続負荷性能テスト0番）**. Stable internal fixture ID: `VRP-LOAD-0`.
Interpretation status: the 120-second result requires a role/adoption review before any longer preparation run.
Project state: **1x UX qualification suspended at this preparation boundary; `ux` remains concept-only and unimplemented.** See [`VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md`](VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md).

This is the first versioned implementation contract for the repository-owned
sustained-load fixture. It is not a `realtime-1x-qualified` verdict. The
preview-only vertical-slice target `vrp-load0-r1-vslice` revision 1 is active
only to exercise the existing receipt/admission/headless-preview path; it is
not the final LOAD-0 qualification target and does not claim 1x UX.

## Role in the performance plan

LOAD-0 is a fixed workload and test case, not a numeric baseline. It is an
artificial maximum sustained-load profile owned by `picocalc_emu`, intended to
exercise the display, audio, CPU, multicore, and virtual-time paths together.
It is not the current emulator as a whole, a game workload, or a claim that
the current implementation can reach 1x.

The baseline is the measurement result obtained by running a fixed workload
through a fixed measurement path. In this document, the 120-second result is
a preparation-stage observation for LOAD-0. It can be used as a comparison
point for the same profile only after the workload's role has been reviewed;
it is not the project-wide 1x UX baseline, and it does not replace the
Tetris（軽ゲーム実装）application workload baseline.

The 120-second vertical slice verifies the clean-clone build/run and the
report, receipt, admission, and headless-preview path. It is not a formal
LOAD-0 completion, a qualification run, or an optimization run. The plan must
review this result before starting repeated preparation runs; those runs are
not an automatic next step merely because the 120-second command completed.

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
- `README.md`: `687584c61832504242e68dafc8ccdb4c8ed350ec959e541c26772b4cdfb2fe9a`
- `app/main.cpp`: `a46167f921186a2b13266410d987a11dee1621fbeafb43ef41b3a19d162f8298`

The following artifact pair is a bounded, non-formal one-virtual-second smoke
build. Two independent clean clones of the source commit above, using the
same toolchain, fixed timestamp, and CMake cache, produced identical values:

- `build-smoke/picocalc_app.bin`: `4e66d504b6fe03bdf753242a8c82f900c80c398a50578b0e48c4d9671db361f8`
- `build-smoke/picocalc_app.uf2`: `1f24954bd25644f0079392f584a0a47deec0a7f60f53eab0f2950ca06c03b754`

These are smoke-build outputs, not a qualification artifact. The default
120-second artifact has a successful non-formal vertical-slice run recorded
below. A separate preview-only registry target now connects that artifact to
the existing receipt/admission path; LOAD-0 completion remains gated on
determinism and preparation evidence.

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
It remains the scenario for later qualification runs.

The checked-in scenario was separately exercised with a two-virtual-second
non-formal build. Its result was complete and the fixed 1,000 ms input offset
delivered all four events:

- BIN: `c0b2a03522102e7f0fd31799becca863a0e4e24cf018647cdf247e4481e0e64f`
- UF2: `5e15db4c9dc3d3a25e6c848dbeb3f09be8a05318df6c81d977563846f6281133`
- RESULT: `duration_us=2000000`, `elapsed_us=2000017`, `frames=60`,
  `audio_underruns=0`, `audio_write_drops=0`, `input_events=4`
- scenario stop: `scenario_done` after 634,997,246 cycles / 2,545,000 us
- report-wide LCD: 6,246,400 pixels written, 0 dropped
- report-wide audio sink: 48,000 Hz, 96,885 DMA writes, 0 unexpected gaps
- report SHA-256: `0cd93f98cc05dea6e17113c43a90e1a45fd3f90300755a656e40885cd8f9ebda`
- UART SHA-256: `b4acdddd175f6eb564f28e5fe2798407d301448da50875d066cfa2c2084f9e4a`
- audio-analysis SHA-256: `c0173cddf1fae29c529c45ce5df37fc0ad33c4dedc73ae63a082deab110c25f5`

This two-second run remains an integration smoke. It does not satisfy the
required 1--2 virtual-minute vertical slice or the 10-virtual-minute
preparation gate.

## 120-second vertical slice record

The checked-in r1 scenario was then run from the clean source clone with the
clean backend runner. This is a successful non-formal vertical slice. It is
now connected to the preview-only target `vrp-load0-r1-vslice` revision 1, but
that target does not close the three-run preparation gate or complete
`VRP-LOAD-0`.

| item | observed value |
| --- | --- |
| backend | `picoem-picocalc@65c795e87321e79b960ac8a7495a205de6a24ec0` |
| backend worktree | clean (`dirty=false`) |
| runner SHA-256 | `613aa318e546cea1b89934e2ee3091b640ca8cf4860abfefa7f668ec0395bf2c` |
| firmware BIN SHA-256 | `b7fd7608ee97186cfac4407aae204c7773b1eacd5d7026bcff0fe00f5929b229` |
| scenario SHA-256 | `bbd319321fe7e7373681d73bb823ea4bcb72d5054c40742fe7878caf2824be2d` |
| execution | `picocalc`, `pio-rgb565`, PSRAM + keyboard, Serial, quantum 1 |
| stop | `scenario_done`, 30,135,011,760 cycles, report elapsed 120,545,058 us |
| result interval | 120,000,000 us, 3,600 frames, frame digest `0xb2250c35`, max frame lag 45,737 us |
| LCD observation | 368,742,400 pixels written, 0 dropped, 320x320 framebuffer fully populated |
| audio result interval | 5,716,096 produced / 5,715,840 consumed, 0 firmware underruns, 0 write drops |
| audio sink observation | 48,000 Hz, 5,716,980 DMA writes, 0 unexpected gaps; 128-frame blocks |
| CPU/input | core0 1,924,159 units; core1 3,319,052 units; 4 keyboard events delivered |
| authoritative digests | core0 `0x26a1d301`; core1 `0xad30308a`; input `0xf3cd494e` |

The report-wide audio diagnostics also contain 45,664 timer misses and
44,663 block-boundary gaps. They are preserved as observed values; they are
not silently relabelled as underruns or discarded. The firmware RESULT line
and the `unexpected_gap_count=0` observation are kept separate from any later
threshold decision.

The canonical performance value is `real_time_percent`, defined as virtual
execution seconds divided by host wall-clock seconds, multiplied by 100. The
runner finished 120.0 virtual seconds in 6,219.928 wall-clock seconds, giving
`real_time_percent=1.929283%`. This is the current implementation's result for
this artificial LOAD-0 profile. Since `100%` means wall-clock 1x, it is
not the performance of the current emulator in general, not the Tetris
baseline, and not a 1x result. The raw record may retain the derived
virtual/wall ratio for machine compatibility, but it is not the headline
performance notation.

The complete non-formal artifact record is
`firmware-validation/records/vrp-load0-vslice-120s-20260829-01/record.json`.
The preserved artifacts are:

- report JSON SHA-256:
  `c25b83f3ed89eb3b97e57e23bf04797396a2c4b81ecb75b179c956cf8010b4a6`;
- audio-analysis JSON SHA-256:
  `dcfecd1173ad96e164373b31a6803bf65cb98c175191c6c49e78901171f99a47`;
- UART raw SHA-256:
  `01052749132c4604317bee51133e90ea37eb5db633fb6e677993e80654bffddf`;
- normalized report SHA-256:
  `ba9d276605531578e1baecf18f652c1253c1cd083c08c3f267f5589454f47dbd`;
- scenario timeline SHA-256:
  `71cd85d25ef16f0d8aed916d755048c7d9bc040bf9e455aeae118c9f87b0a572`.

The load-specific receipt/admission path is now accepted for the preview-only
vertical-slice target. The next gates are at least three deterministic runs
with the same fixture and the 10-virtual-minute preparation run. No realtime
threshold or `realtime-1x-qualified` claim is made here.

## Preview-only target and admission record

The target registry contains `vrp-load0-r1-vslice` revision 1. It is an
active, preview-only target for this 120-second slice, not the final
`VRP-LOAD-0` target. Its contract SHA-256 is
`a7d6f586e20b7a6c136f1dd0e408cb9707fac9cd571549340d19c025e737b94a`.

The formal validation record is
`firmware-validation/records/vrp-load0-r1-vslice-20260829-01/record.json`.
The wrapper revalidation report has normalized SHA-256
`d22f37fcee948043c168b6b981ec6bd91580f655d2482717e966c579dee43585`,
report SHA-256
`2b75916548241bcbb2de5f0aa7f800b078bbff16ae57d64dce333b992663daf6`,
and the same UART/timeline observations as the direct vertical-slice record.
The receipt, admitted descriptor, and headless transcript are preserved in the
same directory; their SHA-256 values are respectively
`ffd935cfd5ce1aa4056942a68dedb7cd991e1daf9eb91f4786e7a032c5438667`,
`f2800c6fdb042958234a772a035c3fd3f244fe11d2f6c757570fa0a03a72d330`, and
`c99013321d28ba8e7993174c04374986ab1c548729d776c2a802ba33d38bf508`.
Admission passed and the headless consumer returned `hello`,
`frame_rgb565`, two `status` messages, and `goodbye`.

The direct report used abbreviated expected UART marker labels, while the
wrapper report used the full `[VRP-LOAD0][START]` and
`[VRP-LOAD0][COMPLETE]` labels from the target contract. The raw UART bytes,
timeline, and workload observations match; this explains the two normalized
report fingerprints without hiding an execution difference.

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

The recorded non-formal 120-second vertical-slice command, using the clean
backend runner, was:

```sh
<clean-backend>/target/release/picocalc-run \
  --bin <source>/reference-projects/vrp-load0-sustained/build-vslice-120s/picocalc_app.bin \
  --bootrom <clean-backend>/roms/rp2040/bootrom-rp2040-b2.bin \
  --board picocalc --lcd-variant pio-rgb565 --quantum 1 \
  --cycles 40000000000 --backend-commit 65c795e87321e79b960ac8a7495a205de6a24ec0 \
  --psram --keyboard --audio-analysis <out>/audio-analysis.json \
  --json <out>/report.json --uart <out>/uart.bin \
  --scenario <source>/scenarios/vrp-load0-r1.json \
  --expect-stop scenario_done \
  --expect-uart '[VRP-LOAD0][START]' \
  --expect-uart '[VRP-LOAD0][COMPLETE]'
```

This command completed successfully for r1. The earlier exploratory run was
intentionally stopped before the current source commit and is not evidence.
The direct vertical-slice record remains non-formal; the separate
preview-only target validation, receipt/admission, and headless transcript are
recorded above. Neither record claims the LOAD-0 completion gate, threshold
decision, or VRP-5 qualification result.

The recorded backend was
`picoem-picocalc@65c795e87321e79b960ac8a7495a205de6a24ec0`, built as a clean
temporary checkout. The repository backend currently has pre-existing dirty
formatting-like changes, so it was not used for this run.

## UX boundary

The r1 profile defines continuous-load timing inputs and outputs. It does not
yet claim `1x UX`: the headless runner's wall-clock timer is not an
input-to-visible-response measurement. A same-BIN preview API/GUI smoke and a
separate input-to-visible-response metric must be added before any UI-facing
label uses that term.

The r1 scenario's four raw keyboard events (`0x04`, `0x05` press/release
pairs) are synthetic emulator inputs. They are not evidence of a human
operating the physical PicoCalc keyboard, and this record must not be used as
physical-input UX evidence.
