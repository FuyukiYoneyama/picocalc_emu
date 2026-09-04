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
| 全体性能checkpoint・R0高速化開始原点 | accepted: `927528660` cycles; process CPU `27.064558677` s; wall `25.969372348` s; real-time `14.305313006%` |
| 全体性能checkpoint・G7 candidate | **fail / critical regression**: `927528659` cycles; process CPU `167.759749206` s; wall `160.262119737` s; real-time `2.318077413%` |
| Tetris（軽ゲーム実装）actual preview process smoke | pass: PCRP Goodbye, return code 0, no stderr |
| R3 Tetris（軽ゲーム実装）formal scenario | pass: `scenario_done`; `927528659` cycles; UART/framebuffer/PSRAM/keyboard contract values recorded |
| R3 PicoEdit（テキスト編集実装）formal scenario | pass: `scenario_done`; `827799818` cycles; UART/framebuffer/PSRAM/SD/keyboard contract values recorded |
| Tetris（軽ゲーム実装）optional authoritative audio oracle probe | **not pass**: PCM count/SHA matched, but snapshot `timer_miss_count=154031`; excluded from the app acceptance claim |

workspace全体の`cargo fmt --all -- --check`は、G7以外の既存candidateにある整形差分を
含むためG7のpass条件にしていない。失敗経路と成功経路の切り分けはshared failure logに
記録している。全体性能checkpointの詳細は`whole-system-checkpoint/`にあり、G7候補の
局所機能passを全体性能passへ読み替えず、14.0%未満を失敗、10.0%未満を重大退行として扱う。
