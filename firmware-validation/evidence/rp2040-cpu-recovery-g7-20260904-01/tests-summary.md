# G7 test summary

| Check | Result |
|---|---|
| `cargo check --locked -p picocalc-harness` | pass |
| `cargo test --locked -p picocalc-harness --test preview_api_e2e -- --nocapture` | pass: 5 tests |
| `cargo test --locked -p picocalc-harness --bin picocalc-run` | pass |
| `cargo test --locked -p rp2040-emu --lib` | pass: 1,254 tests, 0 failures |
| `cargo test --locked -p rp2040-emu audio_sink -- --nocapture` | pass: 4 tests |
| `cargo test --locked -p rp2040-emu peripherals::uart::tests -- --nocapture` | pass: 25 tests |
| `cargo build --locked --release -p picocalc-harness --bin picocalc-run` | pass |
| changed-file rustfmt check | pass |
| candidate `git diff --check` | pass |
| Tetris（軽ゲーム実装）exact pinned short screening | pass: stop `scenario_done`; normalized projection matches G6 |
| Tetris（軽ゲーム実装）actual preview process smoke | pass: PCRP Goodbye, return code 0, no stderr |

workspace全体の`cargo fmt --all -- --check`は、G7以外の既存candidateにある整形差分を
含むためG7のpass条件にしていない。失敗経路と成功経路の切り分けはshared failure logに
記録している。
