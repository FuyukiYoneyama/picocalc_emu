# R1（必要機能の棚卸し）記録

## 状態

**R1 complete / reconstruction implementation not started.**

ユーザー向けの目的を持つ機能と、性能実験・診断だけの変更を分離した。再構築laneの起点は
Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）がすでに動作していたbackend
`e985a9d7ecb51ef760506a105edd34e31cf9b5f1`とする。現在のmainを一括で持ち帰らず、下表の機能群を
G0から順番に、必要性と性能を確認しながら再構築する。

## 残す機能の判断

| 順序 | 表示名 | 主な対象 | 取り扱い | 最初の確認 |
|---|---|---|---|---|
| G0 | 基本Serial実行（既存Tetris／PicoEdit） | Tetris（軽ゲーム実装）、PicoEdit（テキスト編集実装） | `e985a9d...`をそのまま起点にする | 既存targetのUART、framebuffer、scenario、PSRAM／SD結果と短probe |
| G1 | CPU・multicore・割込み正確性 | `picocalc-multicore-r1/r2` | 現在accepted targetを維持するため移植候補 | NEXT-2Aの既存unit／integration／固定cycle run |
| G2 | LCD／PIO／PSRAMの追加wire正確性 | LCD variant A、SIO RAMRD、PSRAM edge | 現在のtargetが要求する部分だけ移植 | LCD／PSRAM edge testと該当target |
| G3 | DMA・audio正確性 | `picocalc-audio-r1`、PWM5_CC sink | 現在accepted audio契約を維持するため移植候補 | audio sink、DMA priority、UART／WAV E2E |
| G4 | headless実行基盤 | machine API、heartbeat、report入口 | 現在の利用者が使う入口だけ移植 | machine API golden、heartbeat、既存CLI |
| G5 | flash・SD・boot | SD-GEN-1、RAW SD、flash mutation、UF2 loader経路 | 公開capabilityを維持する最小範囲だけ移植 | SD wire／E2E、flash readback、既存uf2loader record |
| G6 | 外部I2C module | RTC／EEPROM／環境sensor | capabilityを維持する場合だけ移植 | I2C-EXT E0〜E6の既存test／record |
| G7 | preview API（中断済み1倍UXとは別） | preview／replay／bounded audio transport | 現在の通常利用に必要と確認できるまで移植しない | 当面は除外。1倍qualificationも再開しない |

G1〜G6は「現在の検証・利用契約を維持するための機能候補」であり、移植が自動承認されたことを
意味しない。各群の移植前に、Tetrisでactiveかinactiveか、未移植時の利用者影響、既存gate、予想する
host costを記録する。G7は1倍速UXの再開を意味しない。

## 持ち帰らない変更

- P1-A `decode-invalidation-tag-guard`
- P1-B `executable-sram-invalidation-filter`
- P2-A `pending-exception-fast-reject`
- dynamic quantum／exact batchingなどのOPT2〜OPT4候補
- CPU application profiler、running/idle profiler、performance-only counter
- decode cache、NVIC bitmap、active-PC compile-outなど過去に採用されなかったmicro-opt
- host timing sidecar、短probe、比較用patch（測定専用でありproduction sourceへ入れない）
- 1倍速UX、LOAD-0（最大級の継続負荷性能テスト0番）、外部projectのsource変更
- format-only、release文書、第三者noticeなど、backend runtimeの機能でない差分

測定・診断の変更は再構築candidateの外で使う。`default-off`を理由に候補runtimeを残さない。

## 機能群と履歴の対応

以下は移植候補を探すための履歴対応であり、commit全体の無条件cherry-pick指示ではない。

| 機能群 | 主な履歴commit | 移植時の注意 |
|---|---|---|
| G1 | `38683d6`、`c184d6c`、必要なら`d96f73b` | Serialのguest-visible interrupt結果を保つ。Threaded固有変更は混ぜない |
| G2 | `fc4a622`、`4a90864` | variant A／SIO readbackが必要なtargetだけ。既存PIO pathを置き換えない |
| G3 | `94818f8`、`d92db1b`、`7dd0c34` | DMA／timer／PWM sinkをactiveなaudio targetへ限定し、未使用Tetrisへ常時costを出さない |
| G4 | `f05d47b`、`8d1a06d` | machine API／heartbeatは外部入口。run_loopのguest処理を変えない |
| G5 | `5edca80`、`ae49c6c`、`749ba88`、`d1360cb`、`0e1288e`、`f6cd89d`、`84162a3`、`0126d1b`、`b0a4c05`、`4ee4d1d` | SD／flash／bootの依存順を保ち、bounded capabilityだけを戻す |
| G6 | `60ac700`、`f1ae8dc`、`5802b2e`、`0481474`、`f810d05` | I2C profile未使用時にdevice pollingやreport costを増やさない |
| G7 | `e78d11e`、`f133cf8`、`65c795e` | 中断済み1倍速計画の再開条件を作らない。通常利用の要求が出た場合に再審査 |

## 実装順序の開始条件

次の実装は、再構築laneのG0（`e985a9d...`）がcleanにbuildでき、Tetris正式scenarioとPicoEditの
最小実行が通り、R0の短probeを同じ計測patchで再現できた後に開始する。G1以降は一群ずつ移植し、
対象test、短probe、性能内訳を確認する。複数群を混ぜたcandidateや、全target長時間回帰は作らない。

R1の結果をもって、必要機能の選別は完了した。次の作業はG1（CPU・multicore・割込み正確性）の
最小移植であり、G1の性能退行が説明できない場合はG2へ進まない。
