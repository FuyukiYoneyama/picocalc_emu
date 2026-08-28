# VRP-2-a current-backend versioned target revalidation

Status: **complete locally (2026-08-28)**

VRP-2-a revalidated the two VRP preview workloads against the current clean
`picoem-picocalc` checkout without changing the older target revisions or
their hardware-correlation evidence. The new entries are preview candidates;
they do not claim hardware correlation or realtime qualification.

## Fixed identities

| item | value |
|---|---|
| backend commit | `d3767c901921811b5744925832956661fd344457` |
| `picocalc-run` SHA-256 | `f436d7dc4965b433a65ee7355014b1d93148dbb433e251927cbd9064e019a6d7` |
| Pico SDK | 2.2.0 (`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`) |
| device projection | `picocalc`, `pio-rgb565`, PSRAM, keyboard, FAT32 SD |
| execution | serial, quantum 1 |

The backend worktree was checked for tracked changes before each run and the
runner report recorded `backend_build.dirty=false`. The two older entries
(`picotetris-opt1b` revision 5 and `picoedit-r1` revision 1) remain immutable.

## Revalidated targets

### `picotetris-opt1b-vrp2` revision 6

* source/BIN: `fed84f358d7dcadb1457752e687355ddb1875c48`,
  `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
* target contract SHA-256:
  `ef77c2cd2b31f9bf7fb305b43e89c75c9e7c8ed9492b68b659e2ed33fa30fa66`
* run: PASS, `927528659` cycles (`-1` versus superseded revision),
  `scenario_done`
* UART SHA-256:
  `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
* RGB565 framebuffer SHA-256:
  `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
* timeline SHA-256:
  `8403b8f9d8aa9e4cfb84b03ac0082529873d79c14e5079994085893e06f69589`
* normalized report SHA-256:
  `aca35844de16edd1465278c7d48463386115d6bce34d383be74530128b909751`

### `picoedit-r1-vrp2` revision 2

* source/BIN: `82a6e4c76272e8f520d2f8cba42f1a7e549d4933`,
  `17cb513b8dd3ea6525ce6bd92d1ce3081bb6ea9730c590c2afb86a9fa085e8f6`
* target contract SHA-256:
  `1f55a47ec0dd369d36ba9c92abe7f032432821866df1dbfb6b089d9e3f21f945`
* run: PASS, `827799818` cycles (`-4` versus superseded revision),
  `scenario_done`
* UART SHA-256:
  `2a37433c341bacf59ec0cbcafae6d4f29eb83cc7da17bb2237f0addc0009de33`
* RGB565 framebuffer SHA-256:
  `18d0809edef49bbc085f21aa3212bf47d9344b4eb9845e96f24f1fb768b920b9`
* timeline SHA-256:
  `f1da8985f2736b2b927245177f9390fa649fb27aca1dc80150e8af74d783617d`
* normalized report SHA-256:
  `7943d139398652d5f99beea8873355e5b6a24723da3a56180f6b11756d0413f5`

For both workloads, UART, framebuffer, and scenario timeline are byte/hash
identical to the superseded revision. The small cycle deltas are recorded as
observations, not rounded away and not classified as a hardware or behavior
failure. No new hardware test was performed.

## Evidence and local admission

The raw runner reports and LF-normalized UART transcripts are kept at:

* `firmware-validation/records/vrp2-a-picotetris-20260828-01/`
* `firmware-validation/records/vrp2-a-picoedit-20260828-01/`

The corresponding accepted validation documents are:

* `firmware-validation/validations/picotetris-opt1b-vrp2-r6.json`
* `firmware-validation/validations/picoedit-r1-vrp2-r2.json`

`python3 tools/picocalc.py verify` passed 84/84 locally. A receipt was
generated from each preserved PASS report and `python3 tools/picocalc.py
preview` revalidated both receipts, writing an admitted descriptor without
starting a GUI. Receipt and descriptor files were temporary artifacts under
`/tmp`; they are not runtime dependencies of the repository.

This closes only VRP-2-a. Descriptor consumption (VRP-2-b), machine API
compatibility (VRP-2-c), UART RX evidence (VRP-2-d), GUI, audio, and
qualification remain pending.
