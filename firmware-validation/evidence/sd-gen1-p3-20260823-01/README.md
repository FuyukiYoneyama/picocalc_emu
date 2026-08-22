# SD-GEN-1-P3 evidence

Date: 2026-08-23

P3 fixes the validation loop around the feature-gated P2 model. It adds a
local replay tool for complete structured SD traces, connects feature-gated
protocol errors to the diagnostic runner verdict, and replays the frozen U6,
M-NESCO, FAT16, and FAT32 traces. No GitHub Actions run was used.

## Results

All six replay groups passed and were deterministic where three source runs
exist:

| group | repeats | events | digest |
|---|---:|---:|---|
| M-NESCO SD source | 3 | 2083 | `c3db672deded667f83e3daa4b6feedb8585aae709bf70850d287c649b6e87366` |
| M-NESCO flash source | 3 | 29 | `ac242c6aec780fee8793ca99c2b010017e08b411a7968a723ec5490691c85f23` |
| FAT16 | 3 | 2081 | `e189b48cb6bcb9600697959cf5bff18b1544a32dfa56e3938b2935847d1dcf6c` |
| FAT32 | 3 | 2083 | `c3db672deded667f83e3daa4b6feedb8585aae709bf70850d287c649b6e87366` |
| U6 uf2loader | 3 | 970 | `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3` |
| U6 reattach | 1 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

The replay tool recomputes the `SdTraceState` canonical streaming digest,
checks complete preview/sequence/CS/data invariants, and can compare repeated
traces. A mutated digest is rejected with exit status 1. The feature-enabled
runner unit test also verifies that a recorded SD protocol error becomes a
judged `sd_protocol_error` failure; the default runner has no new report field
or verdict behavior.

## Reproduction

From the `picocalc_emu` repository root:

```sh
python3 tools/sd_trace_replay.py \
  --trace firmware-validation/evidence/sd-gen1-p0-20260823-02/mnesco-m2-menu/m2-a-01.json \
  --trace firmware-validation/evidence/sd-gen1-p0-20260823-02/mnesco-m2-menu/m2-a-02.json \
  --trace firmware-validation/evidence/sd-gen1-p0-20260823-02/mnesco-m2-menu/m2-a-03.json \
  --compare-repeated \
  --allow-command 0 --allow-command 8 --allow-command 17 \
  --allow-command 41 --allow-command 55 --allow-command 58
```

Use the same command with the three FAT16/FAT32 or U6 trace paths listed in
`manifest.json`. The backend commit and tool hash are recorded there. The
feature runner checks are local commands:

```sh
cargo test --release -p picocalc-board --features sd-gen1-multiblock
cargo test --release -p picocalc-harness --features sd-gen1-multiblock
cargo test --release -p picocalc-board
cargo test --release -p picocalc-harness
```

P3 does not promote the multi-block feature into the default runtime and does
not change `capability.json`. P4 remains the gate for a representative
production-runtime/app regression before any promotion decision.
