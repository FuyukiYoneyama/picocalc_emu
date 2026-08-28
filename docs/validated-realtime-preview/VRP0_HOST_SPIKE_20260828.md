# VRP-0 host capability spike (2026-08-28)

This is a host-capability result, not a preview implementation. It was run in
the primary supported environment, Ubuntu 24.04 on WSL2/WSLg x86_64, with the
standard-library/native probe:

```sh
python3 tools/vrp0_host_spike.py --json /tmp/vrp0-host-spike.json
```

Observed environment:

| Check | Result |
|---|---|
| `DISPLAY` / `WAYLAND_DISPLAY` | `:0` / `wayland-0` |
| WSLg PulseAudio socket | `/mnt/wslg/PulseServer`, present |
| GUI window | Tk window opened, updated, and closed |
| Audio device | PulseAudio playback stream opened, wrote 480 silent mono frames at 48 kHz, drained, and closed |

The probe is intentionally silent and does not attempt to judge speaker
loudness. It only establishes that a future `winit` presentation and `cpal`
output path can be exercised on this host. `winit` and `cpal` are **not yet
dependencies** and no license obligation is introduced by VRP-0. Their exact
crate versions and license metadata must be reviewed before the VRP-1
lockfile/production dependency change. If the probe returns `inconclusive`,
VRP-0 host support is not claimed; do not silently substitute another display
or audio backend.
