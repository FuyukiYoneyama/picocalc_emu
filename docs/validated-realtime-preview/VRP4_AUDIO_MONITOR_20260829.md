# VRP-4 bounded host audio monitor

Status: **implemented locally; formal registered-target three-condition gate remains to be recorded**
Date: 2026-08-29

## Scope

VRP-4 adds an optional host PCM monitor to the VRP-3 preview GUI.  It is a
presentation aid, not an audio validation oracle and not a hardware speaker
model.  The emulated PWM/DMA/audio sink, virtual clock, UART, framebuffer,
device events, and schema-8/report-compatible observation digest continue to
advance without waiting for a host audio device.

The monitor is deliberately outside the authoritative exactness surface:

- no gain, mute, resampling, smoothing, EQ, compression, or host-player state
  is written into the emulated machine;
- failure to start or write to a host player is reported as monitor
  `timing-only` or `degraded`, never as an emulator PASS or FAIL;
- `audio.state=not_streamed` in the legacy status field remains intentional;
  `audio_monitor` is the separate host-transport status.

## Bounded pipeline

The path has independent bounds and counters so a slow display, player, or
pipe cannot create an unbounded PCM backlog:

| Layer | Bound / behaviour | Diagnostic counter |
|---|---|---|
| emulated audio tap | 8 blocks of at most 128 stereo source frames | `backend_drop` / `dropped_blocks` |
| runner → frontend PCRP output | 256 framed messages; audio, RGB565, and status are lossy when full; control/error/UART frames remain fail-closed | `ipc_dropped_audio_blocks`, `ipc_dropped_frame_count`, `ipc_dropped_status_count` |
| frontend ingress queue | 512 events; audio, frame, and status events are dropped with PCRP sequence validation intact; hello/UART/error/goodbye are retained | `ingress_drop_count`, presentation/status drop counters |
| host player queue | `--audio-queue-blocks` blocks, each up to 4096 host frames after resampling | `host_queue_drop_count`, `overrun_count` |

The runner output writer is a bounded asynchronous worker.  The emulation
thread uses `try_send`; it never performs a blocking stdout write.  A full
queue drops only the explicitly droppable presentation classes.  If a
non-droppable frame cannot be delivered, the preview session fails closed
instead of silently losing a control or diagnostic event.

The backend emits fixed 128-frame PCM transport blocks.  The source timer
fraction is still observed by the authoritative sink, and the block metadata
retains the source sample rate.  Applications using 32-frame DMA refills or a
22,050 Hz timer therefore remain observable; the monitor groups source frames
for transport and does not change the firmware's DMA/block semantics.  PCRP
schema 1 rejects an audio block larger than 128 frames before allocation.

## Host monitor and resampling

`AudioMonitor` is host-only Python code.  It accepts variable source rates and
channels, performs bounded stateful linear resampling to the requested host
rate, and retains only the interpolation tail between blocks.  A single input
block is limited to 128 frames and a resampled block to 4096 frames.  The
resampler clips only the host PCM integer conversion; it cannot alter the
backend observation digest.

The default player is `ffplay` when available.  A missing player is not an
emulation error: the monitor reports `timing-only` and continues consuming
bounded metadata.  A player that exits or raises a pipe error changes the
monitor to `degraded`; the virtual machine continues independently.

Launch options are available only on `preview-gui`:

```sh
python3 tools/picocalc.py preview-gui \
  --descriptor /absolute/path/to/admitted-descriptor.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --audio on \
  --audio-host-rate 48000 \
  --audio-queue-blocks 8
```

Use `--audio off` to disable host playback while retaining the same emulation
and protocol path.  `--audio-host-rate` and `--audio-queue-blocks` affect only
the host monitor.  They do not alter the descriptor, runner argv, BIN, or
validation receipt.

## Status and reset semantics

The GUI status line exposes source/host rates, resampling, queue depth,
underrun/overrun, backend/IPC/ingress/host drops, and `stream_epoch`.

- `off`: monitor explicitly disabled;
- `inactive`: enabled, but no source block has opened a player yet;
- `streaming`: a host player is alive and blocks are being submitted;
- `timing-only`: no compatible host player is available (emulation continues);
- `degraded`: a bounded queue, ingress, IPC, player, or payload failure lost
  host presentation data.

F5/reset starts a new stream epoch and clears pending host PCM plus source
  rate/resampler state.  Drop, underrun, overrun, and received/sent frame
  counters are cumulative for the GUI process so an earlier transport failure
  cannot disappear silently; `stream_epoch` separates runs.  Ctrl+R creates a
  new admitted child and advances the epoch as part of reload.

## Local verification boundary

The implementation is covered locally by:

```sh
# picocalc_emu
python3 -m unittest -q tests.test_preview_gui tests.test_tools
python3 -m py_compile tools/picocalc.py tools/picocalc_preview.py tools/verify_vrp0_contracts.py
python3 tools/verify_vrp0_contracts.py

# picoem-picocalc
cargo test --locked -p picocalc-harness
cargo test --locked -p picocalc-harness --test preview_api_e2e
cargo clippy --locked -p rp2040-emu -p picocalc-harness -- -D warnings
rustfmt --edition 2024 --check \
  crates/rp2040-emu/src/audio_sink.rs \
  crates/rp2040-emu/src/bus/mod.rs \
  crates/rp2040-emu/src/dma.rs \
  crates/rp2040-emu/src/lib.rs \
  crates/picocalc-harness/src/preview_api.rs \
  crates/picocalc-harness/src/preview_protocol.rs \
  crates/picocalc-harness/src/session.rs
```

The tests cover variable-rate/variable-block payloads, the 128-frame protocol
limit, bounded resampling, host queue drops, ingress drops, player exit,
missing-player timing-only operation, reset epoch semantics, authoritative
audio-tap isolation, and an asynchronous output queue whose droppable frames
are rejected without waiting for a stalled sink.  A full registered-target
`monitor off / on / forced drop` digest comparison is a follow-up evidence
record; until that record is created, VRP-4 must not be described as a
`realtime-1x-qualified` or hardware-audio capability.

No GitHub Actions run, push, release tag, or hardware write is part of this
implementation step.  The existing VRP-2/VRP-3 descriptor and exactness
contracts remain unchanged.
