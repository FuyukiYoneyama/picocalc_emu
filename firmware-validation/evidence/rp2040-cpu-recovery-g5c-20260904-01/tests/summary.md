# G5-C test summary

This file records the observed command/result summary for the clean G5-C candidate. The detailed
machine-readable U6 result is [`../u6-gate.json`](../u6-gate.json); this record does not claim that
the old U6 raw UF2 files were retained.

| Check | Result |
|---|---|
| `cargo test --locked -p picocalc-board` | pass: library 87, doctest 1 |
| `cargo test --locked -p picocalc-harness` | pass: opt0 2, runner 63, SD E2E 1 |
| `cargo test --locked -p picocalc-board --no-default-features` | pass: library 82, doctest 1 |
| `cargo test --locked -p picocalc-harness --no-default-features` | pass: opt0 2, runner 62 |
| `cargo fmt --package picocalc-board --package picocalc-harness -- --check` | pass |
| `git diff --check` | pass |
| `cargo build --locked --release -p picocalc-harness --bin picocalc-run` | pass |
| release `cli_sd_multiblock_e2e` | pass: 1 test, 3 repetitions |

The strict workspace Clippy result is not a G5-C gate because the previously recorded existing
warnings remain outside this candidate's source diff.
