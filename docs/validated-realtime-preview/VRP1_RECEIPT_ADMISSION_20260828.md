# VRP-1 receipt generation and preview admission

Status: **complete (2026-08-28)**

VRP-1 adds the common, fail-closed admission boundary needed before a preview
frontend can be started. It does not start a GUI, add a GUI/audio dependency,
or change the authoritative firmware runner.

## Generate a receipt

Run the existing authoritative firmware validation and request a persistent
report plus a receipt:

```sh
python3 tools/picocalc.py test --mode firmware \
  --target picotetris-opt1b \
  --firmware /absolute/path/to/PicoTetris.bin \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --json /absolute/path/to/validation-report.json \
  --receipt-out /absolute/path/to/validation-receipt.json
```

`--receipt-out` is firmware-mode only and requires `--json`. The receipt is
written only after the target contract, report checks, runner exit/verdict,
backend pin, and runner/BIN invariants pass. It is written with temporary-file
plus atomic-replace semantics; a failed or `cannot_judge` run never replaces an
older receipt.

The wrapper probes the selected runner for the optional heartbeat flags. A
historical accepted backend that predates heartbeat support is run without
those flags so the fixed target remains usable. If the caller explicitly asks
for `--run-id` or a non-default `--progress-interval` on such a backend, the
wrapper returns `cannot judge` instead of silently ignoring the request.

## Revalidate before preview launch

The admission command re-reads every referenced artifact and writes an
immutable-input descriptor. It deliberately stops before launching a GUI:

```sh
python3 tools/picocalc.py preview \
  --firmware /absolute/path/to/PicoTetris.bin \
  --receipt /absolute/path/to/validation-receipt.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --descriptor-out /absolute/path/to/preview-launch.json
```

Admission checks all of the following:

- receipt schema 1 and receipt identity;
- target ID/revision and target contract SHA against the registry;
- accepted validation-record path/SHA and `result=accepted`;
- firmware path/SHA and report schema 8, PASS verdict, board, firmware SHA;
- backend HEAD, clean tracked worktree, accepted commit, and runner SHA;
- the six schema-1 device fields (`board`, `lcd_variant`, `psram`, `keyboard`,
  `sd.attached`, `sd.format`);
- registry provenance and non-empty references.

Schema-only VRP-0 fixtures contain placeholders and `fixture_only=true`; they
are intentionally refused by `preview`. Hand-editing any referenced file or
receipt field therefore fails closed. Targets with an unprojected semantics-
affecting runner option (for example an optional I2C profile) are also refused
until a later receipt schema explicitly represents that option.

## Local acceptance evidence

On 2026-08-28 a clean worktree at backend commit
`e985a9d7ecb51ef760506a105edd34e31cf9b5f1` and the reproducible
`picotetris-opt1b` BIN were used. The authoritative run returned 0 and
generated:

```text
BIN SHA     0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62
UF2 SHA     44ec62270175aac16add07ca8d7c99abb0942bcff341c4c36c0d884fc857e274
runner SHA  0e955f6fbaad67fe2d1a9dbf79f3a1930ce0b164af8aa526919b83f5c0708aa2
report SHA  2749f0313347f72eea8515fedc492463e4e1d627f497d77a3a7203c2ddbf56ec
```

The subsequent `preview` admission returned `PASS` and produced a descriptor
with `status=admitted`. A receipt with a mutated firmware SHA and both VRP-0
schema-only fixtures were refused. The receipt and descriptor were temporary
test artifacts and are not runtime dependencies of this repository.

VRP-1 does not promote a capability, alter `capability.json`, or claim realtime
1x performance. The next production step is VRP-2 (shared session and preview
backend API).
