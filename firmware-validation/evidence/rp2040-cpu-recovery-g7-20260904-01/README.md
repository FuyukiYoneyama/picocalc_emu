# G7（preview境界／bounded transport：実アプリpreview接続）記録

## 状態

**candidate-pass / 未統合**。

このrecordは、性能退行復旧・再構築計画R2のG7として、高速起点へ現在のValidated
Realtime Preview（VRP）利用経路に必要な境界だけを戻した候補の記録である。backend
`main`、active target registry、既存validation record、外部project、remote branch、
実機は変更していない。

G7は1倍速qualification、LOAD-0（最大級の継続負荷性能テスト0番）の完走、または
性能改善を判定する段階ではない。CPU秒、wall時間、real-time比率はこのrecordの合否
指標にしていない。

## マクロな位置づけ

G0〜G6で、Tetris（軽ゲーム実装）を約14%で動かしていた高速backendへ、CPU／割込み、
LCD／PIO／PSRAM、DMA／audio、保存領域、loader、SD、外部I²Cの必要なguest-visible
機能を順に戻した。G7はその上で、既存VRP targetのpreview接続を失わないための最後の
境界を候補へ戻す作業である。既存のG4 machine API／heartbeatをやり直す作業ではない。

## 候補で戻したもの

- PCRP schema 1のpreview protocol（bounded payload、方向検査、未知入力のfail-closed）。
- batch／machine API／previewが同じ`MachineSession`とscenario replay境界を使う構成。
- UART TX/RX、RGB565 framebuffer、reset／quit、pacer／observation digestのpreview応答。
- 8ブロック上限のPCM presentation tapと、非同期runner出力queue。音声・frame・statusだけ
  を明示的にdrop可能とし、control／error／UART／goodbyeは失敗として扱う。
- authoritative batch report pathと通常Tetris実行を変更せず、preview commandのときだけ
  presentation tapを有効にする境界。

旧VRP-LOAD-0（高負荷テスト0番）やVRP-NES-0は、preview-only／歴史資料であり、G7の
 active target復元対象にしていない。

## 起点・差分・provenance

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前candidate: G6 `091c371df0baa664f8a082f44d1256f112152798`
- G7 candidate: `9db10c0313547e9463510ffe3ae6d7474e008494`
- source差分: [`g7-source-diff.patch`](g7-source-diff.patch)、13 files、2,797 insertions、204 deletions
- source差分SHA-256: `3d84204955c157c55e28646b45e1fdc853d6c44fcd41b3b80946aeca46c2be67`
- release runner: [`picocalc-run`](picocalc-run)
- runner SHA-256: `78d0124f730d40022fbf262f67e32da9a4b13ce143fa122cd31d39f7a2c875c4`
- candidate worktree: `/tmp`の一時detached worktree、commit済み、clean、remote branchなし
- backend build: candidate commit、`dirty=false`

## ローカル検証

- `cargo check --locked -p picocalc-harness`: pass
- `cargo test --locked -p picocalc-harness --test preview_api_e2e -- --nocapture`: **5 passed**
- `cargo test --locked -p picocalc-harness --bin picocalc-run`: pass
- `cargo test --locked -p rp2040-emu --lib`: **1,254 passed、0 failed**
- `cargo test --locked -p rp2040-emu audio_sink -- --nocapture`: **4 passed**
- `cargo test --locked -p rp2040-emu peripherals::uart::tests -- --nocapture`: **25 passed**
- `cargo build --locked --release -p picocalc-harness --bin picocalc-run`: pass
- 変更対象のrustfmt check、candidate `git diff --check`: pass

workspace全体の`cargo fmt --all -- --check`は、G7以外の既存candidateにある整形差分を
含むため合否に使っていない。この制約はshared failure logへ記録している。

## Tetris（軽ゲーム実装）回帰 screening

G6と同じ、SDK 2.2.0で再生成した登録済みPicoTetris binary、同じscenario、PicoCalc
board／PIO RGB565／PSRAM／keyboard／SD／Serial／quantum 1を使った。candidate runnerの
通常batch経路は次を満たした。

- stop reason `scenario_done`、verdict `pass`
- guest cycles `187,528,659`、guest elapsed `755,000 µs`
- UART 1,387 bytes、SHA-256 `db430d62e3e6164709d30ff7ebaac033408ef36f8261a4f313b478e3f8e8155a`
- framebuffer RGB565 SHA-256 `21738024c789675f1d2a7299004618dc648cc1d5af6f4971c33e392c2bac0162`
- PSRAM CS falling 7、written 24 bytes、read 34 bytes
- G6のnormalized guest-visible projectionとSHA-256 `fe658ee07415b6d55799e250c09e6997fe9ac98dcd43140efb452fcb4bed4da5`で一致

これはG7候補でこのprobeのguest-visible退行を観測しなかったという意味であり、
高速化を意味しない。full reportはcandidate backend identityを含むため、G6 reportとの
全体byte一致とは主張していない。

## 実アプリpreview smoke

同じPicoTetris binaryとscenarioを`--replay-scenario`で共通session境界まで進めた後、
`--preview-api`でPCRP接続し、明示quitで終了した。詳細な実行結果は
[`preview/preview-summary.json`](preview/preview-summary.json)にある。

- return code `0`、stderr空、Goodbye受信
- 14 framed messages、sequence `0..13`、status 3件、RGB565 frame 1件、PCM frame 8件
- 最初のreplay後statusでvirtual cycle `187,528,659`
- observation digest `e49ea1fcfd5b210bf7943a3e17ec8d872041932141bcc43ed8bfd6926cc0d7a9`
- audio monitorはsource `48,000 Hz`、7 complete blocks＋partial block、queue上限8 blocks、
  backend／IPC drop 0、state `streaming`

このsmokeのauthoritative audio projectionには既存のaudio timer miss観測があり、
projectionの`audio.status`は`fail`である。G7はaudio fidelity oracleを合格にしたものでは
なく、audio monitorのbounded transportがその状態を隠さず、drop counterとともに提示
できることだけを確認した。audio exactnessの判定はG3／VRP-4の既存契約に残す。

## 判定と次

preview protocol、shared replay/session、bounded audio transport、実アプリpreview process
接続を候補で確認できたため、G7はこの限定範囲で**candidate-pass**とする。ただし候補は
まだbackend `main`やactive targetへ統合しない。次はG7 evidence、G0〜G7の差分、既存target
契約をまとめて統合可否を人間が判断する段階である。統合後も、性能改善値や1倍速を自動的
に宣言しない。
