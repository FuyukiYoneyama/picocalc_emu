# Headless machine API（NEXT-4完了仕様）

## 1. 目的

NEXT-4では、PicoCalc firmwareをAI・自動試験・既存scenario runnerから同じ方法で操作する
小さなmachine APIを固定する。GUIや壁時計に依存せず、入力、前進、観測、snapshotをすべて
仮想cycle境界で決定的に扱う。

このAPIは合否判定を置き換えない。`picocalc-run`のfail-closed verdict、target registry、
versioned validationは引き続き権威ある回帰契約である。machine APIは、その下にある一回の
emulator sessionを再利用可能にする操作境界である。

## 2. 実装境界

- transportは標準入力・標準出力上のUTF-8 JSON Linesとする。socket、HTTP、GUI、壁時計
  pacingはv1に入れない。
- firmware、bootrom、backend identity、board/device構成はprocess起動時のCLIで固定する。
  session途中でartifactやdevice構成を交換しない。
- stdinの1行を1 request、stdoutの1行を対応する1 responseとする。firmware UARTと診断は
  stdoutへ混ぜない。診断はstderrへ送る。
- requestは逐次処理する。同時実行、background thread、request間で自発的に進む時間はない。
- requestが不正な場合はmachine stateを変更しない。未知fieldはv1ではerrorにする。
- 1 requestは改行を除いて1 MiB以下とする。超過行は`invalid_request`で拒否する。
- 個別requestの失敗はresponseの`ok=false`で表す。stdin EOFでtransportが正常終了したprocessは0、
  stdin/stdout I/Oまたはsession起動自体が失敗した場合だけprocessを2で終了する。

起動形は次とする。

```text
picocalc-run --machine-api --bin app.bin [既存device options]
```

`--machine-api`は`--scenario`、`--stop-pc`、最終report出力／期待値指定と併用しない。
API session自身は合否を推測せず、状態と明示的な停止理由を返す。

## 3. envelope

request:

```json
{"schema":1,"id":"r1","op":"observe","domains":["machine","uart"]}
```

success:

```json
{"schema":1,"id":"r1","ok":true,"cycle":1234,"result":{},"events":[]}
```

error:

```json
{"schema":1,"id":"r1","ok":false,"cycle":1234,"error":{"code":"invalid_request","message":"..."}}
```

`id`はstringまたは0以上のintegerとし、その値をbyte-levelで意味を変えずresponseへ返す。
`schema`、`id`、`op`は必須である。全responseは処理後のmaster cycleを含む。

安定error codeは次とする。

| code | 意味 |
|---|---|
| `invalid_json` | 1行がJSONとして読めない |
| `invalid_request` | 必須field、型、範囲、組合せが不正 |
| `unsupported_operation` | 未知の`op` |
| `unsupported_observation` | 未知または未接続deviceの観測要求 |
| `machine_stopped` | HardFault、NMI、emulator error等の後に前進を要求 |
| `model_error` | mutex poison、snapshot I/O、emulator内部error |
| `event_overflow` | 購読eventを欠落なく返せない |

## 4. v1 operation

### `run`

`max_cycles`を必須とし、現在cycleから相対budgetまで実行する。cycle budget、fatal exception、
emulator error、clock stallの最初の境界で停止する。instruction／schedulerのarchitectural
boundaryでbudgetをわずかに越える可能性があるため、responseは要求値ではなく実際の
`advanced_cycles`と`cycle`を返す。無制限runは禁止する。

### `step`

`count`回（既定1、上限1,000,000）のscheduler dispatchを行う。これは「厳密にN master
cycles」ではない。1 dispatchが消費したcycle数を`advanced_cycles`で返す。停止状態へ
到達した時点で残りcountを実行しない。

### `run_until`

condition、`max_cycles`、`poll_cycles`を必須とする。conditionを開始時にも評価し、成立、
budget、fatal stopの最初で止める。v1 conditionは`pc_equals`、`cycle_at_least`、
`uart_contains`、`pixel_equals`、`region_hash_equals`とする。LCD条件をLCD未接続で要求した場合は
falseではなく`unsupported_observation`である。timeoutを暗黙に成功扱いしない。

### `input`

公式keyboard firmwareと同じ8-bit eventを投入する。`text`は各byteのpressed/released pair、
`events`は`pressed`／`held`／`released`とcode 0..255の明示列で、どちらか一方だけを許可する。
keyboard未接続、FIFO drop、mutex failureを黙って成功にしない。responseはaccepted、dropped、
queuedを返す。

### `observe`

指定domainの現在値を副作用なしで返す。v1 domainは次である。

- `machine`: cycle、virtual time、両core PC／park state、sticky stop
- `uart`: session開始からのbyte数、SHA-256、UTF-8 lossy text
- `framebuffer`: width、height、RGB565 SHA-256、non-black pixel数
- `keyboard`: queued、delivered、dropped、overwritten、lock状態
- `sd`: format、command/read/write/error counters
- `unsupported_mmio`: sorted entriesとtruncated状態

### `subscribe`

購読domainを置換する。v1はbackground pushを行わない。以後の各state-changing response末尾の
`events`へ、前responseから変化した購読domainをsequence番号付きで添付する。このpull型設計により
host schedulingでevent順序が変わらない。UARTは追加byteだけをevent化し、buffer上限超過は
`event_overflow`として明示する。

### `snapshot`

現在framebufferのmetadataを返す。任意の`png`はprocess起動時の`--snapshot-dir`配下のbasename
だけを許可し、絶対path、`..`、path separatorを拒否する。responseへabsolute pathを出さない。

## 5. scenario runnerとの関係

実装は次の一方向依存にする。

```text
RP2040 Emulator + PicoCalc devices
              ↓
       Machine session core
         ↙             ↘
picocalc-run scenario   JSONL machine API
```

既存scenario engineは独自のstep loopを持たず、machine sessionの`advance`、`input`、
`observation`、`snapshot`を使う。既存report schema 8、scenario timeline、UART、framebuffer、
behavior event契約は変更しない。API追加を理由にtargetのpinを更新しない。

## 6. 実装順序と受入条件

1. **NEXT4-0 契約固定** — 本書、request/response parser、純粋protocol unit test。
2. **NEXT4-1 session抽出** — emulator、virtual clock、UART、board handles、停止判定を共有型へ
   集約し、既存`run_loop`をその利用者へ変える。
3. **NEXT4-2 JSONL v1** — 7 operation、stable error、stdout分離、path境界を実装する。
4. **NEXT4-3 scenario互換** — 登録済みrepresentative firmwareを旧入力と同じ条件で実行し、
   cycle、scenario timeline、UART、framebuffer、behavior eventを完全一致させる。

完了条件:

- protocol/parserの正常・異常unit testが合格する。
- 同一request列を3回実行し、response byte列（明示的に除外するhost pathなし）が一致する。
- malformed request、未知op/domain、無制限run、未接続device、FIFO drop、snapshot path escapeが
  fail-closedになる。
- 既存scenario runnerのunit testと代表firmware回帰が変更前と一致する。
- 通常のbuild/test/lint/firmware validationはローカルで実行する。NEXT-4の試行錯誤に
  GitHub Actionsを使わず、workflowを変更しない。

## 7. 実装結果（2026-08-10）

NEXT4-0〜3を完了した。`picocalc-run --machine-api`へschema 1を実装し、既存batch scenarioも
同じ`MachineSession`のadvance、virtual clock、UART、board observationを使う。protocol／dispatcher／
scenarioのall-feature test 62件、Clippy `-D warnings`、formatが合格した。

`uart_hello.bin`へ6 requestを与えるtranscriptを3回実行し、3出力はすべてSHA-256
`e4755d92720df7d1067bffc9e3140fa65b74a286c6d8d37739af4d942a89e1fb`でbyte一致した。UART eventはoffset 0から
欠落・重複なしで1件、snapshotは320×320 PNG、stdoutはresponseだけ、boot診断はstderrだけだった。

登録済みPicoTetris BIN `0784d80d...e62`をclean local cloneから再現し、変更前HEADと候補を同じ85-step
scenarioで比較した。両方とも85/85、927,528,659 cycle、3,715,000 us、UART
`bff1f245...66c`、framebuffer `f63b598f...4a2`で一致し、backend provenanceだけを正規化したreportは
byte一致した。GitHub Actionsとworkflowは使用・変更していない。
