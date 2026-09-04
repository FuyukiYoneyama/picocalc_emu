# G7（preview境界／bounded transport：実アプリpreview接続）記録

## 状態

**機能candidate-pass／全体性能fail・停止／未統合**。

このrecordは、性能退行復旧・再構築計画R2のG7として、高速起点へ現在のValidated
Realtime Preview（VRP）利用経路に必要な境界だけを戻した候補の記録である。backend
`main`、active target registry、既存validation record、外部project、remote branch、
実機は変更していない。

G7の局所機能とpreview接続はcandidate範囲で確認できたが、後続の全体性能checkpointで
14.0%最低維持値と10.0%重大退行赤旗を下回った。したがってG7は全体性能として失敗・停止であり、
1倍速qualification、LOAD-0（最大級の継続負荷性能テスト0番）の完走、性能改善、統合可能性を
このrecordから主張しない。

## マクロな位置づけ

G0でTetris（軽ゲーム実装）が約14%で動いていた高速backendを全体性能の出発点として固定し、
G1〜G6でCPU／割込み、LCD／PIO／PSRAM、DMA／audio、保存領域、loader、SD、外部I²Cの必要な
guest-visible機能を候補へ順に戻した。G7はその上で、既存VRP targetのpreview接続を失わないための
最後の境界を候補へ戻す作業である。既存のG4 machine API／heartbeatをやり直す作業ではない。
ただしG1〜G7の局所candidate-passは、全体性能checkpointを通過するまで再構築段階の合格とはしない。

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

## 全体性能checkpoint（R2停止）

G7候補を次の統合段階へ進める前に、同じTetris（軽ゲーム実装）正式scenarioを、高速出発点とG7候補で
同じ条件により全体実行した。詳細な入力、timing sidecar、report、runner binaryは
[`whole-system-checkpoint/`](whole-system-checkpoint/)に保存した。

| 地点 | process CPU秒 | wall秒 | real-time比率 | 判定 |
|---|---:|---:|---:|---|
| G0高速出発点`e985a9d...` | 27.064558677 | 25.969372348 | **14.305313006%** | 14.0%以上、基準成立 |
| G7候補`9db10c0...` | 167.759749206 | 160.262119737 | **2.318077413%** | **14.0%未満かつ10.0%未満、重大退行** |

両runは同じfirmware、scenario、PicoCalc device configuration、Serial、quantum 1、CPU affinity 11で、
Tetris scenarioを`scenario_done`まで完走した。既知のguest cycle差は1 cycleだけで、約6.20倍のCPU時間差を
説明しない。したがってこれはguest-visible正確性の失敗ではなく、G1〜G7候補を積み重ねた全体性能の失敗である。

G7の機能candidate-passは局所的なpreview契約の記録として保持するが、全体性能の判定は**fail**とする。
R2（Recovery 2：高速地点からの段階再構築）はここで停止し、R3（Recovery 3：現行機能契約の受入）の
完了、R4（Recovery 4：現行mainへの統合可能性確認）、backend `main`への統合へ進まない。

## R3（現行機能契約の受入：実アプリ2本）

R3の最初の代表として、現在維持する2つの実アプリをG7 candidateで各1回実行した。
これは「preview接続が動くこと」と「既存targetのguest-visible契約を満たすこと」を確認する
受入であり、CPU秒、wall時間、real-time比率、1倍速の判定ではない。音声DMAのauthoritative
oracleは通常のTetris（軽ゲーム実装）target契約の必須条件に含めず、G3／VRP-4の独立契約に
残している。

### Tetris（軽ゲーム実装）

- target `picotetris-opt1b-vrp5` revision 10、source commit `fed84f358d7dcadb1457752e687355ddb1875c48`
- firmware SHA-256 `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256 `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- contract SHA-256 `1a296b1faa9088e22f9939bc61b3963475af7005343038361cf1db4ddcb28a5f`
- `scenario_done`／verdict `pass`、`927,528,659` cycles、`3,715,000 µs`
- UART SHA-256 `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- framebuffer RGB565 SHA-256 `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
- PSRAM `CS falling=7`、write `24` bytes、read `34` bytes、keyboard `362` events、SD protocol errors `0`

詳細な再現入力は[`tetris-formal/`](tetris-formal/)に保存した。音声期待値を追加した別診断では
PCM件数 `1000`とPCM SHA-256 `c978c5173c975f841e2b886d5f9af5f71e07fa3f6dc400b0697dc261758bc356`
自体は一致したが、authoritative snapshotはtimer miss `154031`を理由に`fail`となった。
この結果を音声passへ読み替えず、R3のTetris受入は上記の既存scenario契約のpassとして扱う。

### PicoEdit（テキスト編集実装）

- target `picoedit-r1-vrp2f` revision 4、source commit `82a6e4c76272e8f520d2f8cba42f1a7e549d4933`
- firmware SHA-256 `17cb513b8dd3ea6525ce6bd92d1ce3081bb6ea9730c590c2afb86a9fa085e8f6`
- scenario SHA-256 `d7af28965f49cd7363ca5ac68678572d3e6975eb426b6af828dd09a70505b718`
- contract SHA-256 `ad3b795ca89a9350766a6be7a833c09c35113c2bddebc0a3b6cc458e81b8a6c9`
- `scenario_done`／verdict `pass`、`827,799,818` cycles、`3,320,000 µs`
- UART SHA-256 `2a37433c341bacf59ec0cbcafae6d4f29eb83cc7da17bb2237f0addc0009de33`
- framebuffer RGB565 SHA-256 `18d0809edef49bbc085f21aa3212bf47d9344b4eb9845e96f24f1fb768b920b9`
- PSRAM `CS falling=250`、write `154` bytes、read `2471` bytes、SD `12` read／`13` write blocks、keyboard `30` events、protocol errors `0`

詳細な再現入力は[`picoedit-formal/`](picoedit-formal/)に保存した。sourceはmetadataのない一時
archiveではなく、target commitを持つclean git checkoutから生成したartifactを使用した。

この2本のpassはR3のアプリ代表2件について機能を確認した資料である。G7 preview transportの機能
candidate-passおよびG3のaudio oracle非合格状態を変更しない。全体性能checkpointが重大退行となったため、
これらの機能passだけでR3完了や統合開始へ進むことはできない。

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
接続は候補で確認できたため、G7の機能範囲だけはcandidate-passとして記録する。しかし全体性能checkpoint
が重大退行となったため、G7 recordの総合判定は**stopped-critical-regression**である。候補はbackend `main`や
active targetへ統合せず、次の作業はG7候補を積み上げることではなく、全体性能が14.0%以上だった最後の
checkpointへ戻って、どの差分が退行を生んだかを一群ずつ切り分けることである。
