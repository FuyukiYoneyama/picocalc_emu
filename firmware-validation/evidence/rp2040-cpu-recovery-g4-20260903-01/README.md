# G4（ヘッドレス実行基盤：machine API・heartbeat・report入口）記録

## 状態

**candidate-pass / 未統合**。

高速地点 `e985a9d...` からG1（CPU・割込み正確性）、G2（LCD・PIO・PSRAM正確性）、G3（DMA・audio
正確性）を戻した一時candidateへ、現在の利用者が使うmachine APIとheartbeatを戻した。候補はbackend
`main`へ統合していない。target registry、既存record、外部project、remote branch、hardwareは変更
していない。

## マクロな位置づけ

これは性能退行復旧・再構築計画R2のG4である。目的は、各機能群の正確性を同じheadless操作で確認し、
長い処理でも人間が進行状況と終了を判断できる実行入口を確保することだ。machine APIの応答一致と
heartbeatの出力を確認したが、速度改善やCPU時間の短縮は主張しない。

G4はemulation hot pathへ新しい常時観測コストを加える段階ではない。heartbeatは明示的な
`--run-id`と`--progress-interval`を指定したときだけstderrへ出力し、report／verdict／hashには
混ぜない。machine APIはプロセス起動時に固定したfirmware、bootrom、backend、device設定のまま、
stdin/stdout JSONLの要求と応答を処理する。

## 起点と候補

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前G3 candidate: `151cbc0574756a3c76e2314bd46afb2dcd101c96`
- G4 candidate: `f2d4d52711af70cd7f4e1c74ffda667966df15cb`
- candidate commit: `recovery: restore headless runner API and heartbeat`
- source差分: `g4-source-diff.patch`（4 files、1,986 insertions、110 deletions）
- source差分SHA-256: `bacdafab52a87f230519bc3fa2d7496c71d1c2d1b9433c8452247a7b0a0e850d`
- candidate worktree: `/tmp`の一時worktree、detached、remote branchなし
- runner release SHA-256: `9578affb263e58c78b472392aff36d5b6253d3662a95be1fee0b58b75ed13d1d`

G4で戻したのは、次の必要部分だけである。

1. schema 1のmachine API（observe、step、run、run_until、input、subscribe、snapshot）とfail-closedな
   JSONL応答。
2. machine APIの起動時artifact／device設定の固定と、snapshot出力。
3. 複数runを区別する`run-id`、1秒単位などの明示的interval、start／heartbeat／finishのstderr通知。
4. tracked sourceの変更をbuild provenanceへ反映するbuild scriptの再実行条件。

preview API、audio解析、profiler、追加診断はG4へ混ぜていない。

## 対象test

G4 candidateのclean worktreeで次を実行した。

- `cargo test --locked -p picocalc-harness`: opt0 2、runner 62、全pass
- `cargo test --locked -p rp2040-emu`: library 1,240、firmware 9、multicore 9、PSRAM edge 4、smoke 6、
  WFE IRQ wake 5、doctest 0、全pass
- `cargo test --locked -p picocalc-board`: 74、doctest 1、全pass
- `cargo fmt --package picocalc-harness -- --check`: pass
- release runner build: pass

## machine API（ヘッドレス操作入口）の実行結果

現行backend mainのmachine API schema-1 golden fixture（8要求）からrequest列だけを取り出し、G4 runnerへ
同じ順序で3回入力した。firmwareは`uart_hello.bin`、bootromはRP2040 B2の
`bootrom-rp2040-b2.bin`、boardはPicoCalc、LCDはPIO RGB565、keyboard attachで固定した。

3回とも次が完全一致した。

- 8行の応答JSONLとgoldenのexpected response
- 応答transcript SHA-256: `6393bf03dffdff5900b421466cb5c76c025fef9073a91119a9958fa7c3ca08a6`
- `snapshot`操作が生成した `golden.png`
- snapshot SHA-256: `67452db642dfe52dd18e98102ba5b13187b9b94f6b91891bb2daab946d684581`
- machine API stderr（起動時のboot情報）

fixture全体、request列、expected response、各runのraw responseとPNGは`machine-api/`へ保存した。
これは同じAPI transcriptを再生できることの確認であり、emulatorの一般性能や1倍速を判定するものではない。

## heartbeat（長い処理の進行通知）の実行結果

Tetris（軽ゲーム実装）のR0短scenarioを、G3と同じfirmware／scenario／device構成で1回実行した。
runnerには`--run-id g4-tetris-heartbeat --progress-interval 1`を明示した。

- verdict: **pass**
- stop reason: `scenario_done`
- guest cycles: `187,528,659`
- guest elapsed: `755,000 µs`
- UART bytes: `1,387`
- framebuffer RGB565 SHA-256: `21738024c789675f1d2a7299004618dc648cc1d5af6f4971c33e392c2bac0162`
- heartbeat: 1秒間隔、`seq=1..15`の15行
- finish: `scenario_done`、exit `0`

G3のTetris短screeningとcycle、UART、framebufferが一致した。heartbeatのhost elapsedは長時間runの監視
機能を示す補助記録であり、性能baselineや改善率へ使用しない。heartbeatはstderrの
`heartbeat/heartbeat.stderr.log`にあり、report／UARTのdigestには含まれていない。

## 再現に使った入口

machine API:

```text
picocalc-run --backend-commit f2d4d52711af70cd7f4e1c74ffda667966df15cb \
  --bin uart_hello.bin --bootrom bootrom-rp2040-b2.bin \
  --board picocalc --lcd-variant pio-rgb565 --keyboard --machine-api \
  < machine-api/requests.jsonl > responses.jsonl
```

heartbeat:

```text
taskset -c 11 picocalc-run --backend-commit f2d4d52711af70cd7f4e1c74ffda667966df15cb \
  --bin PicoTetris.bin --bootrom bootrom-rp2040-b2.bin \
  --board picocalc --lcd-variant pio-rgb565 --psram --keyboard --sd \
  --scenario r0-scenario-probe.json --quantum 1 \
  --run-id g4-tetris-heartbeat --progress-interval 1 \
  --expect-stop scenario_done --expect-uart '[TETRIS] start'
```

実行時には各artifactの絶対パスを指定し、bootromはSHA-256を照合する。

## 判定と次の作業

G4は、現在必要なheadless machine APIのgolden再生とheartbeat通知をcandidateへ戻した段階として
**pass**とする。G3比のTetris guest-visible退行はなく、G4由来の性能改善は主張しない。

次はG5（flash・SD・boot：RAW SD、flash mutation、UF2 boot、multiblock）の必要部分を棚卸しする。
G5も、必要targetと既存recordを先に確定し、対象testとTetris（軽ゲーム実装）短screeningを通過した
場合だけ次へ進む。G4 candidateのproduction統合、target registry更新、正式性能baseline更新はまだ
行わない。
