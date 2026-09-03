# G3（DMA・audio正確性）記録

## 状態

**candidate-pass / 未統合**。

高速地点 `e985a9d...` からG1（CPU・multicore・割込み正確性）、G2（LCD・PIO・PSRAM正確性）を
戻した一時candidateへ、現在の `picocalc-audio-r1` が必要とするDMA・audio経路だけを戻した。
候補はbackend `main`へ統合していない。target registry、既存record、外部project、remote branchも
変更していない。

## マクロな位置づけ

この記録は、性能退行復旧・再構築計画R2のG3である。目的は、既存のaudio出力契約を高速Serial起点へ
戻し、必要な機能を追加したときの正確性と追加コストを次の判断へ渡すことである。1倍速、LOAD-0
（最大級の継続負荷性能テスト0番）、最終倍率のqualificationではない。

Tetris（軽ゲーム実装）の短probeは、機能を戻したことで明白な退行が出ていないかを見るscreeningで
あり、高速化達成率やCPU秒の改善を確定する測定ではない。今回のscreeningではhost timing sidecarを
使っていない。

## 起点と候補

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前G2: `aa9c868576f02c7bc6e3e450f5224143f09b93a6`
- G3候補: `151cbc0574756a3c76e2314bd46afb2dcd101c96`
- 候補commit: `recovery: restore DMA audio correctness`
- source差分: `g3-source-diff.patch`（6 files、1,213 insertions、19 deletions）
- source差分SHA-256: `851b13738472aa797efaee4d458080da4bb46a4c145a7c839165635f4e14836e`
- 候補worktree: `/tmp/picocalc-performance-recovery.QMNRcP/rebuild-e985`
- runner release SHA-256: `73253a3e251d3cb0de9a10d0164208fda51ecb333a6c76e449a66f57a73c0bd2`

G3では履歴commitを丸ごとcherry-pickせず、現行G2 candidateへ次の必要部分を移植した。

1. DMA timer 0〜3のfractional pacingとTREQ 59〜62のdue event処理を戻した。
2. DMA-to-PWM5_CCのaudio sinkを、期待値を指定したrunだけ有効にした。
3. 48 kHz streamのPCM digest、DMA設定、due-cycle、block boundary、service latencyをreportへ出力した。
4. timer missを記録するが、未消費eventを後からまとめて再生しない契約を戻した。

通常のTetris（軽ゲーム実装）runではaudio sink観測を有効にしていない。診断hashを全DMA writeへ
常時適用する実装にはしていない。

## 対象test

G3候補のclean worktreeで、以下を実行した。

- `cargo test --locked -p picocalc-board`: 74 tests、doctest 1、全pass
- `cargo test --locked -p rp2040-emu`: library 1,240、firmware 9、multicore 9、PSRAM／PIO edge 4、
  smoke 6、WFE IRQ wake 5、doctest 0、全pass
- `cargo test --locked -p picocalc-harness`: `opt0_blocked_baseline` 2、runner 41、全pass

新しいaudio sinkのunit test、timerの無効値・fractional cadence・rephase・miss非再生、DMA transfer
観測のtestを含む。workspace全体の既存format-only差分はG3へ混ぜていない。

## 正確性結果

### picocalc-audio-r1（音声DMA実装）

外部project `picocalc-audio` は変更せず、clean cloneのsource commit
`724b3ac74f1401a19d6310af387c65ad1e5476a4`を使った。SDKは
`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`、BSPは0.9.0、固定build timestampは
`2026-08-09T12:00:00Z`である。

生成artifactは既存active target `picocalc-audio-r1` revision 1と一致した。

| artifact | SHA-256 |
|---|---|
| `picocalc_app.bin` | `acaaf220fa9912a4cbd09de923f002ffe1fc0748d7c295ea997c1d28319b0cb6` |
| `picocalc_app.uf2` | `d6986103e74e153fd23ea7ce25111bba0a5752331959367b0aa63f6eb1c28677` |

G3 candidate (`151cbc...`、clean、Serial、quantum 1)で、既存の `next2-audio-v3.json` を実行した。

- verdict: **pass**、stop reason: `scenario_done`
- guest cycles: `405,523,032`
- elapsed: `1,627,000 µs`
- UARTの5つのauthority marker: **全て検出**
- PCM DMA write: `49,152 / 49,152`
- PCM SHA-256: `1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f`（期待値一致）
- wrong width / wrong TREQ / missing due cycle: `0 / 0 / 0`
- timer: `3/15625`、due-cycle SHA-256一致、event `54,758`、miss `5,606`
- block: start `384`、boundary `383`、malformed `0`
- block gap: min `5,209`、max `10,417`、`5208=32,640`、`5209=16,128`、unexpected `0`
- service latency: min `0`、max `6`、digest一致
- framebuffer: RGB565 digest一致、non-black pixels `61,700`
- exception / unsupported MMIO: `なし / 0`

既存のaccepted audio record（backend `d92db1b...`）と、cycles、elapsed、UART、framebuffer、audio sink
観測値が一致した。既存recordは編集していない。raw report、UART、snapshotは `audio/` に保存した。

### Tetris（軽ゲーム実装）短screening

固定artifact（BIN SHA-256 `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`、
UF2 SHA-256 `44ec62270175aac16add07ca8d7c99abb0942bcff341c4c36c0d884fc857e274`）と、G2で使った
`r0-scenario-probe.json`を同じ条件で実行した。host affinityはlogical CPU 11、Serial、PicoCalc、
PIO RGB565、PSRAM／keyboard／FAT32 SD、quantum 1である。

| 構成 | cycles | elapsed | framebuffer | UART | 結果 |
|---|---:|---:|---|---|---|
| G2 candidate `aa9c868...` | 187,528,656 | 755,000 µs | `21738024...` | `db430d62...` | pass |
| G3 candidate `151cbc...` | 187,528,659 | 755,000 µs | `21738024...` | `db430d62...` | pass |

G3はaudio sink期待値を指定していないため、Tetris runの `audio_sink` reportは `null`であり、
PCM hash収集を行っていない。G3で変わったのは完了cycleとscenario内cycleの境界が一律3 cycle増えたこと、
および `psram.tick_count` が4減ったことだけである。後者はguest-visibleなPSRAM transaction数ではなく、
host側のtick呼び出しcounterである。CS falling、read/write bytes、LCD、keyboard、SD、PWM、PIO、
UART、framebufferの観測はG2と一致した。

この1回は短い機能screeningであり、CPU秒・wall秒の改善や退行を主張する測定ではない。3 cycle差は
Tetrisが初期化するaudio timer pacingの追加による候補境界差として記録し、隠れた性能改善へ丸め込まない。

## 証拠ファイル

- `audio/run-report.json`: G3 audio targetのschema-8 report
- `audio/uart.log`: audio target UART全文
- `audio/final.png`: audio authority PASS画面
- `audio/next2-audio-v3.json`: 実行scenarioのコピー
- `tetris-short/g3-candidate-report.json`: Tetris短screening report
- `tetris-short/g3-candidate-uart.bin`: Tetris短screening UART
- `tetris-short/r0-scenario-probe.json`: 短screening scenarioのコピー
- `g3-source-diff.patch`: G2 candidateからG3 candidateへ適用可能なsource差分
- `SHA256SUMS`: この記録のhash一覧

## 判定と次の作業

G3は、現行audio targetの必要なDMA・audio正確性を戻したcandidateとして **pass** とする。ただし、
production採用、backend `main`への統合、target registry更新、最終性能baseline更新はまだ行わない。

次はG4（headless実行基盤）の必要部分を棚卸しし、現在利用しているmachine API／heartbeat／report入口だけを
G3 candidateへ一群として移植する。G4でもtarget testを先に行い、Tetris（軽ゲーム実装）短screeningで
未説明のcostが出た場合はそこで停止する。G3の3 cycle差は、次段階で比較の起点として明示的に保持する。
