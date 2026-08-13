# Scenario：状態を見て入力する

起動前に文字列を積むだけの`--keys`ではなく、JSON scenarioを使うと、画面やUARTを待ってから
次のキーを投入できます。

## fresh cloneでrunnerを準備する

次の例は、まだtarget registryへ登録していない新規BINを直接観察する場合の準備です。
コマンドは`picocalc_emu`のrootで実行し、backendは別checkoutに置きます。

```sh
backend_root=/absolute/path/to/backends
git clone https://github.com/FuyukiYoneyama/picoem-picocalc.git \
  "$backend_root/picoem-picocalc"
backend="$backend_root/picoem-picocalc"

(cd "$backend" && cargo build --release -p picocalc-harness)

runner="$backend/target/release/picocalc-run"
bootrom="$backend/roms/rp2040/bootrom-rp2040-b2.bin"
test -x "$runner"
test -f "$bootrom"
```

`runner`と`bootrom`は絶対pathで指定します。backendのbranch headを正式な登録targetの
受入証拠として扱うことはできません。登録targetの回帰判定には、
[`TESTING.md`](TESTING.md)のwrapper手順でtarget registryが指定するBINと
`backend.accepted` commitを使ってください。

## 最小例

`scenario.json`を作ります。

```json
{
  "schema": 1,
  "name": "boot-check",
  "poll_ms": 5,
  "steps": [
    {"op": "wait_until", "condition": {"kind": "uart_contains", "text": "BOOT"}, "timeout_ms": 3000},
    {"op": "key", "text": "A", "gap_ms": 50},
    {"op": "snapshot", "png": "after-a.png"},
    {"op": "assert", "condition": {"kind": "region_non_black", "x": 0, "y": 0, "w": 320, "h": 320, "min": 1}}
  ]
}
```

直接runnerへ渡します。`--bin`、scenario、各出力先は実際のファイルへ置き換えてください。
この経路は登録targetのfail-closed判定ではなく、新規BINの観察用です。

```sh
out=/tmp/picocalc-scenario
mkdir -p "$out/snapshots"

"$runner" --bin /absolute/path/to/app.bin \
  --bootrom "$bootrom" \
  --board picocalc --lcd-variant pio-rgb565 --keyboard \
  --scenario /absolute/path/to/scenario.json \
  --snapshot-dir "$out/snapshots" \
  --uart "$out/uart.bin" \
  --json "$out/report.json"
```

長いrunを監視する場合は、`--run-id <id> --progress-interval 10`を追加します。
直接runnerではこの2 optionを組で指定してください。出力reportの`verdict`、UART、
snapshotを同じrunの成果物として確認し、古いreportを再利用しないでください。

登録targetのscenarioをwrapperから使う場合は、targetに固定されたSHA-256と完全一致する必要があります。

## 操作

| op | 役割 |
|---|---|
| `wait` | 仮想msを進める |
| `wait_cycles` | master cycleを進める |
| `wait_until` | 条件成立まで進める。timeoutはfailure |
| `key` | 押下・解放を投入する。`gap_ms`で間隔を空ける |
| `snapshot` | framebuffer SHAを記録し、PNGを保存する |
| `assert` | その時点の条件を検査する。failure後も続行する |

条件は`pixel`、`region_non_black`、`region_hash`、`region_stable`、`region_changed`、
`uart_contains`です。座標は320×320 viewportです。

## 時間と入力の注意

- `ms`は壁時計ではなく、ファームウェアが設定したclockから得る仮想時間です。
- 条件の通常pollは`poll_ms`（既定5ms）です。`wait`／`wait_until`のtimeout境界は別に正確です。
- keyboard controllerは最大31イベントを保持します。キーを大量投入するとdropになり、結果を信用できません。
- `gap_ms`を使い、1回のバーストを短くしてください。

## statusの意味

- `pass`: 全stepが成立
- `fail`: stepを実行したが期待が成立しなかった
- `incomplete`: cycle切れ等で残りstepまで到達しなかった
- `error`: scenario自体を実行できなかった

JSONの解析エラーは`steps[3].condition.y`のようなJSON pathを確認します。
schemaの全項目と制約は[`../docs/SCENARIO_RUNNER.md`](../docs/SCENARIO_RUNNER.md)、実例は
[`../scenarios/README.md`](../scenarios/README.md)を参照してください。
