# G6 test summary

| Check | Result |
|---|---|
| `cargo test --locked -p rp2040-emu -p picocalc-board -p picocalc-harness` | pass: board 99 + doctest 1; harness runner 66 + opt0 2 + SD E2E 1; rp2040-emu 1251 + firmware 9 + multicore 9 + PSRAM edge 4 + smoke 8 + WFE IRQ wake 5 + doctest 0 |
| `cargo test --locked -p picocalc-board --no-default-features` | pass: library 94 + doctest 1 |
| `cargo test --locked -p picocalc-harness --no-default-features` | pass: runner 65 + opt0 2; SD E2E 0 tests because the feature is disabled |
| `cargo build --locked --release -p picocalc-harness --bin picocalc-run` | pass |
| G6 added-file rustfmt check | pass |
| `git diff --check` | pass |
| I²C E5-compatible runtime screening | pass: 3 runs, byte-identical report/sidecar/UART/framebuffer |
| Tetris（軽ゲーム実装）short screening | pass: normalized projection matches G5-C |

The workspace-wide package format check is not claimed as a G6 pass because the candidate already
contains unrelated formatting drift; that condition is recorded in the shared failure log.
