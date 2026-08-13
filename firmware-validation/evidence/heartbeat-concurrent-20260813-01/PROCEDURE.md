# Heartbeat / concurrent-run local acceptance evidence

Date: 2026-08-13

This is a functional acceptance artifact, not a roadmap validation record. It is intentionally
under `firmware-validation/evidence/`, not `firmware-validation/records/*/report.json`: the runner
JSON is schema 8 and must not be mistaken for the schema-1 roadmap records scanned by
`tools/verify_environment.py`.

## Inputs

- source checkout: `picocalc_emu` HEAD `10d2128f1184a8fa6baa96719f230716b870ac6b`
- backend checkout: `picoem-picocalc` HEAD `4b2fa2c7cf87b326cb265cb82d150802235442e2`
- backend working tree at build: dirty (`backend_build.dirty=true`), because this evidence was
  collected before committing the heartbeat implementation; the commit identity remains explicit
  in every report. A clean-build target registration is a separate follow-up after commit.
- runner: `target/release/picocalc-run` built locally with `cargo build --release -p picocalc-harness --bin picocalc-run --locked`
- firmware: `templates/rp2040-basic/build/picocalc_app.bin`
- firmware SHA-256: `3fdb8231c164dbec73c17b556a964d9c16da44ae7ae6cbf615d39b7b08b934a5`
- bootrom: `picoem-picocalc/roms/rp2040/bootrom-rp2040-b2.bin`
- host: WSL Ubuntu 24.04, serial release runner, no CI

The common runner options were:

```text
--bin templates/rp2040-basic/build/picocalc_app.bin
--bootrom /home/fuyuki/pico_dvl/codex/picoem-picocalc/roms/rp2040/bootrom-rp2040-b2.bin
--board picocalc --lcd-variant pio-rgb565 --psram --sd --keyboard
--cycles 100000000 --expect-stop cycle_limit
```

## Checks

1. `off100` ran without heartbeat options.
2. `on100` ran with `--run-id heartbeat-on --progress-interval 1`.
3. `run-a` and `run-b` ran concurrently with separate artifact directories and IDs.
4. All four runs returned exit 0 and report `verdict.status=pass`, `stop_reason=cycle_limit`,
   `cycles=100000000`.
5. `off100/report.json`, `on100/report.json`, `run-a/report.json`, and `run-b/report.json`
   are byte-identical (`da339cdf...`). Their UART and framebuffer report digests also match.
6. `off100/stderr.txt` is empty. `on100`, `run-a`, and `run-b` each contain start, heartbeat, and
   finish lines, and every line carries the correct run ID.
7. `concurrent-exit.txt` records `run-a=0` and `run-b=0`.

`interrupted-20m/` is an earlier short local smoke artifact retained only to explain an abandoned
long run; it is not part of the acceptance comparison.

## Reproduction

From the `picocalc_emu` root, build the runner as above, make one directory per run, and execute
the common command once without heartbeat and once with a distinct ID and interval. For the
concurrent check, start the two commands in the same shell in the background, each writing only
inside its own directory, then wait for both exit codes. Do not use the same JSON, UART, snapshot,
audio, profiler, or trace path for two processes.
