# Validated Realtime Preview: VRP-0〜VRP-4 contracts, evidence, and GUI

This directory contains the immutable, machine-readable inputs and local
evidence produced by VRP-0 through VRP-4. The registered-target complete
digest gate is closed for the two versioned targets recorded below. It is a
contract, provenance, admission, GUI, and bounded host-audio-monitor
implementation record.
The files are deliberately kept separate from `firmware-validation/records/`:
the latter are existing validation evidence, while these files describe the
preview transport, admission receipt, and thin frontend that consumes an
already validated run.

LOAD-0 is a fixed artificial sustained-load test case, not a numeric baseline
and not the current emulator's overall performance. A measurement obtained by
running LOAD-0 is meaningful only as a result for that fixed profile. The
120-second vertical slice is a preparation-stage path check; it does not by
itself establish a 1x UX baseline or trigger longer preparation runs
automatically.

The 1x UX project is explicitly suspended at this preparation boundary. The
`ux` mode remains concept-only and unimplemented; the suspension decision and
resume conditions are recorded in
[`VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md`](VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md).
The unfinished VRP gates are not the current work queue. Current performance
work preserves Serial guest-visible behavior and follows
[`../PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md`](../PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md).

## Canonical files

| File | Purpose |
|---|---|
| [`receipt-schema-v1.json`](receipt-schema-v1.json) | JSON Schema for a preview admission receipt |
| [`receipt-fixture-picotetris-opt1b-v1.json`](receipt-fixture-picotetris-opt1b-v1.json) | Schema-only receipt fixture for `picotetris-opt1b` rev.5 |
| [`receipt-fixture-picoedit-r1-v1.json`](receipt-fixture-picoedit-r1-v1.json) | Schema-only receipt fixture for `picoedit-r1` rev.1 |
| [`preview-ipc-schema-v1.json`](preview-ipc-schema-v1.json) | Frozen local preview wire protocol |
| [`preview-ipc-fixture-v1.json`](preview-ipc-fixture-v1.json) | Accepted and rejected byte-level IPC fixtures |
| [`preview-launch-descriptor-schema-v1.json`](preview-launch-descriptor-schema-v1.json) | Admitted descriptor and immutable launch-contract schema |
| [`VRP0_BASELINE_20260828.json`](VRP0_BASELINE_20260828.json) | Reproducibility and GUI-less screening baseline |
| [`VRP0_HOST_SPIKE_20260828.md`](VRP0_HOST_SPIKE_20260828.md) | WSLg GUI/audio capability probe and dependency policy |
| [`VRP1_RECEIPT_ADMISSION_20260828.md`](VRP1_RECEIPT_ADMISSION_20260828.md) | Receipt generation, revalidation, compatibility, and local acceptance |
| [`VRP2A_CURRENT_BACKEND_20260828.md`](VRP2A_CURRENT_BACKEND_20260828.md) | Current-backend target revisions, reports, and receipt admission |
| [`VRP2B_DESCRIPTOR_CONSUMER_20260829.md`](VRP2B_DESCRIPTOR_CONSUMER_20260829.md) | Headless descriptor consumer and PCRP hello/status/quit smoke gate |
| [`VRP2CD_MACHINE_UART_20260829.md`](VRP2CD_MACHINE_UART_20260829.md) | Machine API schema-1 golden transcript and UART RX/overrun evidence |
| [`VRP2E_REGISTERED_DIGEST_GATE_20260829.md`](VRP2E_REGISTERED_DIGEST_GATE_20260829.md) | Registered-target batch/machine/preview complete-digest gate (implementation and acceptance boundary) |
| [`VRP3_GUI_20260829.md`](VRP3_GUI_20260829.md) | Tk GUI, PicoCalc skin/LCD composition, UART0 console, input, reset/reload, and local WSLg acceptance |
| [`VRP4_AUDIO_MONITOR_20260829.md`](VRP4_AUDIO_MONITOR_20260829.md) | Bounded host PCM monitor, resampling, drop accounting, and local acceptance boundary |
| [`VRP_LOAD0_SUSTAINED_LOAD_20260829.md`](VRP_LOAD0_SUSTAINED_LOAD_20260829.md) | LOAD-0 r1のrepository-owned sustained-load profile。120秒vertical sliceまで確認済み、formal qualificationは中断 |
| [`VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md`](VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md) | 1倍速UXプロジェクトの中断判断、未完了gate、再開条件、commit／push境界 |
| [`UX_MODE_CONCEPT_20260830.md`](UX_MODE_CONCEPT_20260830.md) | `ux`モードの概念設計。検証用と体感評価用を分離し、LCD転送とCPU待機を一体で畳む方針。**概念のみで未採用・未実装**であり、採用には正典計画の§3／§9／VRP-5判定対象の修正を要する |
| [`CPU_HOTPATH_MEASUREMENT_20260830.md`](CPU_HOTPATH_MEASUREMENT_20260830.md) | `exact`モードCPU単体経路の差分測定結果。`step()`内側が2/3・外側ループが1/3、例外ポーリングが単独15〜17%。**約半分が未帰属**で、サンプリングプロファイルには`perf_event_paranoid`の緩和が必要 |
| [`../../firmware-validation/records/vrp4-picotetris-20260829-01/vrp4-audio-gate.json`](../../firmware-validation/records/vrp4-picotetris-20260829-01/vrp4-audio-gate.json) | Formal VRP-4 `off`/`on`/`forced-drop` registered-target evidence |

## VRP-2-e real-target closure

The local gate passed on 2026-08-29 with clean backend commit
`c1c20d7d86a3006569375bc333cf72494e95eb46` (runner SHA
`f1a79384d0f90fafea1fbe9db249dc9c54327ef12bed0445c1e4bef23e3a050c`).
The accepted revisions are:

| Target | Revision | Four-way digest | Evidence |
|---|---:|---|---|
| `picotetris-opt1b-vrp2f` | 8 | `9604a3784bcaedfaccbd928357bba0b57dd2f584b06db08405ab988deabb59cc` | [`vrp2-f-picotetris-20260829-01`](../../firmware-validation/records/vrp2-f-picotetris-20260829-01/) |
| `picoedit-r1-vrp2f` | 4 | `9e79f1ddd84c6e507ac25ce89bf00a3b1a993cf2255fa27add25e4bac3c32fb3` | [`vrp2-f-picoedit-20260829-01`](../../firmware-validation/records/vrp2-f-picoedit-20260829-01/) |

Each evidence directory contains the fresh schema-8 report and audio sidecar,
versioned validation record, schema-1 receipt, admitted descriptor, and the
atomic complete-digest gate output. The real BINs and clean backend checkout
are external inputs whose SHA-256 values are recorded in the registry and
receipt; they are not committed as large binaries.

The r8/r4 records above remain immutable evidence of the local VRP-2-e gate.
Their backend pin `c1c20d7d86a3006569375bc333cf72494e95eb46` is not reachable
from a backend branch or tag as of 2026-08-29, so it is not a reusable VRP-5
qualification pin. VRP-5 requires a new versioned target, validation record,
and receipt on a reachable clean backend; this does not revoke the historical
record.

The two receipt fixtures are intentionally **not launchable receipts**. Their
firmware and runner paths use `<fresh-dir>` / `<backend-checkout>` placeholders;
they demonstrate the schema and provenance relationships without checking in
large binaries. A real receipt must be generated only after an authoritative
firmware validation and must use existing paths and hashes.

VRP-1's `python3 tools/picocalc.py preview` command is an admission gate only:
it revalidates a generated receipt and writes a launch descriptor, but it does
not start a GUI or emulator process. The receipt and descriptor are normally
kept beside the caller's validation artifacts; they are not required for
ordinary `new`/`build`/`test` use. VRP-2-c/d compatibility evidence is recorded
separately from the receipt fixtures: it protects the established machine API
and the directional UART RX queue without changing the authoritative firmware
report schema.

## Verification

From the repository root, run:

```sh
python3 tools/verify_vrp0_contracts.py
python3 tools/vrp0_host_spike.py --json /tmp/vrp0-host-spike.json
```

The first command checks the schema shape, target/validation provenance,
receipt fixtures, IPC frame lengths and payload semantics. It also checks that
the frozen baseline points at the exact registry revisions and hashes. The
second command is a local WSLg capability probe: it creates and closes a tiny
Tk window and opens a silent PulseAudio playback stream. It does not add a
runtime dependency, play audible data, or modify the emulator.

The VRP-2-c/d backend tests are run in the `picoem-picocalc` checkout:

```sh
cargo test -p picocalc-harness --test machine_api_schema1_golden --locked
cargo test -p picocalc-harness --test preview_api_e2e --locked
cargo clippy -p picocalc-harness --tests --locked -- -D warnings
```

These are local compatibility tests. They do not perform hardware correlation,
do not claim audio streaming, and do not promote the preview capability.

The final registered-target gate is run locally after a fresh target revision
has a clean backend pin, an externally supplied BIN, and a report containing
the complete audio observation.  The command used for the accepted evidence
is:

```sh
python3 tools/picocalc.py preview-digest-gate \
  --descriptor /absolute/path/to/admitted-descriptor.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --evidence-out /absolute/path/to/vrp2-complete-digest.json
```

It compares the registered report with fresh batch, machine-API, and
preview-API projections at the same virtual cycle.  Missing observation data
is refused rather than filled with defaults.  The command is a local gate and
does not invoke GitHub Actions.

The VRP-2 digest's audio member is the complete bounded DMA-to-PWM surface
already present in schema-8 `audio_sink` (including due-cycle, block-gap, and
service-latency digests).  The optional `--audio-analysis` loudness/rail
statistics are deliberately not mixed into this digest; they require a
separate host-monitor path.  VRP-4 now provides that path for the interactive
preview, but its PCM transport, player state, resampling, and drop counters
remain outside the exactness digest.  The formal registered-target
three-condition gate for this monitor is closed locally; its evidence is
listed below.

VRP-0 intentionally did not add `winit`, `cpal`, a GUI executable, or a
preview IPC implementation. VRP-1/2 added receipt/admission and the
authoritative preview backend. VRP-3 adds the standard-library Python/Tk
frontend, but no Rust GUI/audio dependency and no emulator-core copy. VRP-4
adds a bounded, optional host PCM monitor using the existing PCRP stream and
an external `ffplay` process when available. The GUI and monitor do not
promote hardware correlation or `realtime-1x-qualified`; those gates are
suspended and are not the current work queue.

## VRP-4 host audio monitor

The monitor is host presentation only.  The backend's emulated PWM/DMA sink
always advances independently, while a fixed-capacity tap and asynchronous
PCRP writer prevent a slow GUI or player from blocking virtual time.  The
frontend event queue and host-player queue are also bounded; audio, frame, and
status presentation data may be dropped under pressure and each layer reports
its own counter.  UART, error, goodbye, and other control/diagnostic frames
remain fail-closed.

PCRP audio blocks contain at most 128 source frames and retain their source
sample rate.  The host monitor accepts variable rates such as 22,050 and
48,000 Hz, performs bounded stateful resampling to `--audio-host-rate`, and
guards the resampled block at 4096 frames.  `--audio off` disables playback
without changing the emulated run.  A missing player is `timing-only`; a
player/queue/ingress/IPC loss is `degraded`, not an emulator verdict.

The implementation details, status fields, reset `stream_epoch` semantics,
local commands, and the formal three-condition gate result are recorded in
[`VRP4_AUDIO_MONITOR_20260829.md`](VRP4_AUDIO_MONITOR_20260829.md).  The gate
uses target `picotetris-opt1b-vrp4` revision 9 and is retained as the
versioned record under `firmware-validation/records/`.
