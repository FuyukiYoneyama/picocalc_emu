# `picocalc-run` 複数起動・進捗heartbeat実装計画

作成日: 2026-08-13
対象: `picoem-picocalc` の `picocalc-run`、`picocalc_emu` の利用文書
状態: **計画固定。実装未着手。**

## 1. 目的

AIが複数の`picocalc-run` processを同時に実行するとき、各runを安定したIDで識別し、
長時間無出力のrunが進行中か停止したかを外部から判定できるようにする。

この変更はemulatorの正確性、合否判定、report schemaを拡張するものではない。
既存のdeterministic artifactを変えず、最小の追加で運用上の観測性だけを補う。

## 2. 現状と安全境界

`picocalc-run`を別processとして起動した場合、CPU、LCD、PSRAM、keyboard、現在のmemory-backed
SDはprocessごとに独立している。2026-08-13には、PicoCalc board、PSRAM、keyboard、FAT32 SDを
接続した2 processを異なる出力先で同時実行し、両方がexit 0となり、JSON reportとframebufferが
byte単位で一致することをローカルで確認した。

一方、次のpathは呼び出し側が指定する通常のファイルであり、同じpathを複数processへ渡すと
上書き・競合し得る。

- `--json`
- `--uart`
- `--fb-png`
- `--audio-analysis`
- `--audio-wav`
- `--snapshot-dir`
- profiler／trace出力

したがって、複数起動の保証は「runごとに別の出力directoryを使う」ことを前提にする。
初版では新しいartifact管理機構を作らず、この前提をCLI helpと利用文書へ明記する。
呼び出し側は起動前にrun専用directoryを作り、全出力optionをその配下へ向ける。同じpathを共有した
場合の安全性は保証しない。`--snapshot-dir`を省略するとcurrent directoryになるため、snapshotを
使う並列runでは省略しない。

並列実行はhost CPUを競合させる。virtual cycle、UART、framebuffer、behavior hashなどの
決定的結果は比較できるが、wall timeと実行速度の測定は並列実行中に行わない。

## 3. 初版に実装する最小契約

### 3.1 CLI

次の2 optionだけを追加する。

```text
--run-id <ID>
--progress-interval <SECONDS>
```

- `--progress-interval`を指定した場合、`--run-id`を必須とする。
- `--run-id`だけの指定も拒否し、2 optionは常に組で使う。
- heartbeatは明示指定時だけ有効にし、既定動作は変えない。
- intervalは整数秒の`u64`として解析し、1以上だけを受け付ける。
- IDは1〜64文字のASCII `A-Z a-z 0-9 . _ : -`に限定する。
- 空白、改行、制御文字を拒否し、log injectionを防ぐ。
- `--run-id`は観測用metadataであり、firmware reportやbehavior hashへ入れない。
- 同時実行中のIDは呼び出し側が一意に割り当てる。runnerはOS全体の一意性を検査しない。

例:

```bash
picocalc-run \
  --run-id mapper19-case-a \
  --progress-interval 10 \
  --bin app.bin \
  --json runs/mapper19-case-a/report.json \
  --uart runs/mapper19-case-a/uart.bin \
  --snapshot-dir runs/mapper19-case-a/snapshots
```

### 3.2 stderr出力

stdoutはreportとmachine APIのtransportに使われるため、観測行はstderrだけへ出す。
初版は既存のlogと親和性がある1種類のkey-value形式に固定し、JSONL選択機能は作らない。

```text
[PICOCALC][RUN] event=start run=mapper19-case-a pid=12345
[PICOCALC][RUN] event=heartbeat run=mapper19-case-a pid=12345 seq=1 cycles=1234000000 budget=9500000000 pct=12.989 elapsed_s=10.002 rate_mcycles_s=123.375
[PICOCALC][RUN] event=finish run=mapper19-case-a pid=12345 cycles=927528660 elapsed_s=25.382 stop=scenario_done exit=0
```

安定して機械解析するfieldは次に限定する。

| field | 意味 |
|---|---|
| `event` | `start`、`heartbeat`、`finish` |
| `run` | 呼び出し側が指定したstable ID |
| `pid` | 現process ID。補助識別子であり再試行をまたぐIDではない |
| `seq` | heartbeatごとに1から増える番号 |
| `cycles` | 現在のmaster cycle |
| `budget` | cycle budget。適用できないmodeでは省略 |
| `pct` | budgetがある場合だけ出す進捗率 |
| `elapsed_s` | process内の単調壁時計による経過秒 |
| `rate_mcycles_s` | 起動後平均の実行速度 |
| `stop` | 正常に結果を得た場合の停止理由 |
| `exit` | `picocalc-run`が決定した終了code |

`finish`はCLI処理が正常にverdictまで到達した場合、またはmachine APIが正常にEOFへ到達した場合の
process lifecycle完了を表す。argument／artifact読込み／report書込み等のfatal error、`SIGKILL`、
host crash、電源断では`finish`を保証しない。監督側はprocess終了codeと`finish`不在を組み合わせて
abnormal terminationと判定する。signal handlerや永続run registryは初版に入れない。

### 3.3 heartbeatの実装条件

- `std::time::Instant`の単調時計を使う。
- heartbeat無効時は時計取得とformatを実行loopへ持ち込まない。
- 有効時も全cycleで壁時計を読まず、軽量なdispatch counterで確認頻度を間引く。
- 通知はemulator dispatch境界でだけ行うbest-effortであり、指定秒数以内の厳密な発行を保証しない。
- cycle budgetがない、または進捗率を算出できないmodeでも`cycles`と`elapsed_s`は出す。
- 各行はstderrへ書いた直後にflushする。
- heartbeatの出力失敗をfirmwareのFAILへ変換しない。ただしpanicさせず、その後のheartbeatを停止する。
- UART、framebuffer、audio、scenario timeline、event traceへ一切混ぜない。

通常run、scenario、長いmachine API `run`／`run_until`は同じ小さな`ProgressReporter`型を使うが、
既存loopは共通化せず、それぞれから個別に呼び出す。machine APIではrun IDをprocess単位とし、startは
起動後1回、finishはstdin EOF後1回とする。各requestのIDはheartbeatへ複製しない。request単位の
識別が実測上必要になった場合だけ後続拡張とする。machine APIのstdout JSON Linesには観測行を
混ぜない。

## 4. 初版に入れないもの

最小の手数で安全に完了させるため、次は明示的に対象外とする。

- daemon、socket、HTTP server、web dashboard
- processを横断する中央run registry
- heartbeatの複数formatやJSONL option
- 自動的なrun directory作成・artifact名変更
- 既存の個別出力optionの廃止
- heartbeat再送、外部監視service、通知機能
- report schema、target registry、validation recordの変更
- OS全体でrun IDの一意性を検査するlock service
- SIGKILL時の終了記録保証
- GitHub Actions workflowの追加・変更・実行

これらが実測上必要になった場合だけ、別計画として追加する。

## 5. 実装順序

### HB-0 契約とparser test

1. CLI optionとrun ID validationを追加する。
2. intervalの正常値、0、負数、非整数、overflowをtestする。
3. IDの正常値、空、長過ぎ、空白、改行、非ASCIIをtestする。

この段階では実行loopを変更しない。

### HB-1 progress reporter

1. `ProgressReporter`を小さな独立型として実装する。
2. start、期限到達時heartbeat、finishをstderrへ出す。
3. disabled時は早期returnする。
4. normal／scenarioの`run_loop`、machine APIの`run`／`run_until`へ個別に接続する。

既存advance経路を共通化・再構成しない。heartbeat判定は各advance loopに置くが、`finish`はreport
生成とverdict決定が終わった最上位から出す。run loop内で終了codeを推測したり、verdict処理を
progress reporterへ移さない。

report生成、verdict、device modelには変更を入れない。

### HB-2 正確性と複数起動のローカル試験

1. 同じfirmwareをheartbeat OFF／ONで実行する。
2. reportからwall-clock metadataを除いた既存比較方法でbyte一致を確認する。
3. UART、framebuffer、scenario timeline、behavior/event hashの完全一致を確認する。
4. 異なるrun ID・異なる出力directoryで2〜4 processを同時起動する。
5. `[PICOCALC][RUN]` prefixを持つ全行が正しいrun IDを持ち、artifactが混在しないことを確認する。
6. 同じ出力pathを使ってはいけないことを文書例で明示する。

試行錯誤、build、test、lint、firmware regressionはすべてローカルで行う。CIをデバッグ用途に
使わず、workflowへ触れない。

### HB-3 利用文書

長い新規体系を作らず、次の3か所だけを整備する。

1. `picoem-picocalc/README.md`: option一覧と短い複数起動例
2. `picocalc_emu/docs/CONCURRENT_RUNS.md`: AI向けの起動・監視・停止・artifact分離手順
3. `picocalc_emu/AI_START_HERE.md`: 上記文書へのリンク1件

`CONCURRENT_RUNS.md`には次だけを記載する。

- run IDの決め方
- runごとの出力directory
- run IDだけではartifact衝突を防げず、同じpathの共有は未対応であること
- heartbeatの読み方
- process終了とfinish不在の扱い
- 並列実行中は性能測定しないこと
- 並列数をhostのCPU・memory容量に合わせること
- memory-backed SDは独立していること
- 将来のRAW SD imageは同一imageへ複数writerを許さないこと

## 6. 受入条件

次をすべて満たしたときだけ完了とする。

- heartbeat無効時のCLI動作と既存artifactが変更前と一致する。
- heartbeat有効時も既存の正確性artifactが一致する。
- start、複数heartbeat、finishが同じrun IDを持つ。
- 複数processのlogを結合してもrun IDで一意に分類できる。
- 監視側は`[PICOCALC][RUN]` prefixだけを解析対象にし、既存のdiagnostic stderr行をheartbeatと
  誤認しない。
- stdoutにheartbeatが混入しない。
- 不正なrun IDとintervalを実行開始前にfail-closedで拒否する。
- 2〜4 processの同時ローカル試験が合格する。
- unit test、format、Clippy、代表firmware regressionがローカルで合格する。
- README、AI入口、専用手順書の記述が実装と一致する。
- GitHub Actionsを新規に発生させていない。

性能改善は本作業の受入条件ではない。ただしheartbeat無効時に測定可能な退行があれば不採用とする。

## 7. 工数

この最小構成は次を目安とする。

| 作業 | 見積り |
|---|---:|
| HB-0 契約・CLI・parser test | 2〜3時間 |
| HB-1 reporter本体 | 3〜4時間 |
| HB-1 normal／scenarioへの接続 | 2〜3時間 |
| HB-1 machine APIへの接続 | 2〜4時間 |
| HB-2 正確性・複数起動試験 | 3〜4時間 |
| HB-3 文書整備 | 2〜3時間 |
| Solによる最終差分検収 | 1時間 |
| **合計** | **15〜22時間（中心見積り18時間）** |

実装中に既存advance経路の大きな再構成が必要と判明した場合は強行せず、一度停止して原因と
追加工数を報告する。report schema変更、target再pin、CI workflow変更が必要になった場合も同様に
所有者の判断を求める。

## 8. 将来のRAW SDとの関係

現在の`--sd`はprocessごとのmemory-backed imageなので共有書込み問題はない。将来`--sd-image`
などの永続RAW imageを追加するときは、本計画とは別に次を実装する。

- 同一writable imageへの複数writerをlockして拒否する。
- read-only共有またはrunごとのcopyを明示的に選べるようにする。
- lock取得失敗を黙ってmemory-backed動作へfallbackしない。

このRAW SD排他はheartbeat初版の工数に含めない。

## 9. 呼び出し元についての事実整理

`nes2/mapper_check/mapper19_validation/tools/run_invocation.py`の
`subprocess.Popen(argv, cwd=args.cwd)`は、PIPEや別fileを指定していないため、通常は子processの
stdout／stderrを親から継承する。従来文書にあった「出力を中継しない」という説明は誤りなので
採用しない。

ただし、さらに外側のAI実行環境が出力をbufferする場合、heartbeatの即時表示はその外側の仕様に
依存する。`picocalc-run`の責任範囲は、stderrへflush可能な1行を期限ごとに生成するところまでとする。
