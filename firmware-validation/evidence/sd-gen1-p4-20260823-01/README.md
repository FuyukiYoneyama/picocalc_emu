# SD-GEN-1-P4 evidence

Date: 2026-08-23

P4 connects the SD-GEN-1 multi-block model to the default PicoCalc board and
harness runtime.  A repository-owned Thumb fixture drives the real SPI0/CS
path, reads two blocks with CMD18, sends CMD12 without raising CS, and emits a
UART completion marker.  The existing U6, M-NESCO, FAT16, and FAT32 records
remain frozen; their complete traces were replayed again after the runtime
promotion.

## Default-runtime representative regression

| item | result |
|---|---|
| backend commit | `0126d1bd08495fa157cd038b68465937a74f7abe` |
| working tree | clean |
| runner feature | default `sd-gen1-multiblock` |
| firmware fixture SHA-256 | `4eb3940ccdc9e1ed3c5e1d9f6ad2f0f99c03f642d071aedb40c95e541be00a0d` |
| report SHA-256 | `65fcfe408bae1a6092484a68992cb5c0f88eff34117307bb8ec539fd660bf850` |
| SD trace file SHA-256 | `ea40f02089ea06681c151cacf078aa01a9291a701cf202cf06aefd656969ff0e` |
| verdict | `pass` |
| SD commands | CMD18, CMD12; unknown=0 |
| blocks read | 2 (512 bytes each) |
| protocol errors | 0 |
| UART marker | `SD_MB_FIXTURE` |

The trace's semantic streaming digest is
`18b36ccbeb98b7d9cf313949756f7d7fc45115ccb617a41241f27fb320138d43`.

The report and trace in this directory are the clean-run artifacts.  The
fixture source is the checked-in
`picoem-picocalc/crates/picocalc-harness/tests/cli_sd_multiblock_e2e.rs` test;
no generated firmware is required to reproduce it.

## Existing representative regressions

The P3 frozen traces were replayed locally after enabling the default feature:

| group | runs | events | digest | result |
|---|---:|---:|---|---|
| U6 uf2loader | 3 | 970 | `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3` | pass |
| M-NESCO SD | 3 | 2083 | `c3db672deded667f83e3daa4b6feedb8585aae709bf70850d287c649b6e87366` | pass |
| M-NESCO flash | 3 | 29 | `ac242c6aec780fee8793ca99c2b010017e08b411a7968a723ec5490691c85f23` | pass |
| FAT16 | 3 | 2081 | `e189b48cb6bcb9600697959cf5bff18b1544a32dfa56e3938b2935847d1dcf6c` | pass |
| FAT32 | 3 | 2083 | `c3db672deded667f83e3daa4b6feedb8585aae709bf70850d287c649b6e87366` | pass |
| U6 reattach | 1 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | pass |

These are trace replays of the existing source/artifact records, not a claim
that private external application workspaces were rebuilt in this checkout.

## Local reproduction

From the backend checkout:

```sh
cargo test --release -p picocalc-board
cargo test --release -p picocalc-harness
cargo test --release -p picocalc-harness --test cli_sd_multiblock_e2e
cargo test --release -p picocalc-board --no-default-features
cargo test --release -p picocalc-harness --no-default-features
```

The last two commands preserve the legacy single-block differential boundary;
they are not the production default.  From the emulator checkout, replay the
frozen traces with `tools/sd_trace_replay.py` using the paths in the P3
manifest.  No GitHub Actions run was used.

## Scope boundary

P4 proves the default runtime's CMD18/CMD12 read path and compatibility with
the existing U6/M-NESCO/FAT records.  It does not change `capability.json`,
rewrite versioned target records, or claim USB BOOTSEL/MSC, card-removal, or
write-protect support.  Capability and registry decisions remain the P5 gate.
