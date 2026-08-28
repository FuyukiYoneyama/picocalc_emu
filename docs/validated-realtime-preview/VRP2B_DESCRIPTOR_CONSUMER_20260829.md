# VRP-2-b admitted descriptor consumer

Status: **complete locally (2026-08-29)**

`tools/picocalc.py preview-headless` is the first consumer of the admitted
descriptor. It does not accept a hand-written runner command. Before spawning
anything it rechecks the target contract and validation attestation, firmware
and report SHA-256, backend HEAD and tracked-worktree state, runner SHA-256,
bootrom SHA-256, device projection, and the embedded preview launch-contract
SHA-256. The embedded `argv` and `cwd` must also equal the canonical contract
derived from the registered target.

After admission the consumer starts the exact `picocalc-run --preview-api`
executable, validates every runner-to-preview PCRP frame, requires the order
`hello` → `status`, sends a schema-1 `quit` command, and requires `goodbye` and
exit code 0. Bad magic, unknown/direction-invalid kind, sequence discontinuity,
non-canonical JSON, malformed binary payload, timeout, runner error, or EOF
fails closed. A small optional JSON transcript records only the observed
message kinds and is not a conformance report.

## Usage

```sh
python3 tools/picocalc.py preview-headless \
  --descriptor /absolute/path/to/preview-launch.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --transcript-out /tmp/preview-headless.json
```

The command is a local smoke/consumer gate. It does not start a GUI, does not
claim realtime performance, and does not promote a capability.

## Local acceptance

Using the VRP-2-a descriptors for `picotetris-opt1b-vrp2` revision 6 and
`picoedit-r1-vrp2` revision 2, the consumer completed `hello`, initial RGB565
frame, `status`, `goodbye` and exit 0 for both targets. A descriptor mutation
was refused before spawn. The targeted Python tests also cover the descriptor
contract mutation and a fake PCRP runner's hello/status/quit exchange.

The next remaining VRP-2 packages are VRP-2-c (machine API schema-1
compatibility transcript) and VRP-2-d (UART RX positive/overrun evidence).
