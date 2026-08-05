# Scenario runner（Milestone 3）

## これは何か

`--keys`は起動前に文字列をキーFIFOへ積むだけで、**プログラムの状態を見て次の操作を
決められない**。画面の判定も、PNGを人間が見るしかなかった。この2つが
[`DOGFOODING_20260805.md`](DOGFOODING_20260805.md)で見つかった最も重い穴である。

scenarioはこれを埋める。JSONで書いた手順を**実行ループの内側**で評価するため、
1ステップが画面とUART出力を見てから次のキーを決められる。

```sh
picocalc-run --bin app.bin --board picocalc --lcd-variant pio-rgb565 \
  --scenario tetris-line-clear.json --snapshot-dir out/ --json report.json
```

終了コードは`picocalc.py`と同じ規約に従う。**0**=全ステップ合格、**1**=判定して不合格、
**2**=判定自体ができなかった（ファイルがない、scenarioが壊れている）。

## 時間の意味

msは**仮想時間**である。エミュレートしたサイクル数を、そのときファームウェアが
設定しているシステムクロックで割って求める。壁時計は一切読まない。

クロックはブート中に変わる（ROSC → PLL）。固定の除数を使うと、切り替え前に取った
時刻がすべて20倍ずれる。そのため`clk_sys`が変わるたびに換算を**再基準化**し、
経過済みの時間は測ったときのレートを保ち、以後の区間だけ新しいレートを使う。

レポートの`elapsed_us`が、その走行の最終仮想時刻である。

## 評価の頻度

条件の評価は毎サイクルではなく`poll_ms`（既定5 ms）ごとに行う。領域のハッシュは
面積に比例するため、140×280の井戸を5 msで監視すると仮想1秒あたり約800万画素の
読み出しになる。領域を広く取るときはこの費用を意識する。

**時間待ちだけは正確である。** `wait`と`wait_until`のタイムアウトは、その時刻ちょうどに
再ポーリングするよう予約されるので、`poll_ms`の粒度に丸められない。

## ファイル形式

```json
{
  "schema": 1,
  "name": "tetris-line-clear",
  "description": "任意",
  "poll_ms": 5,
  "steps": [ ... ]
}
```

### 操作

| `op` | 引数 | 意味 |
|---|---|---|
| `wait` | `ms` | 仮想時間を進める |
| `wait_cycles` | `cycles` | サイクル数で進める |
| `wait_until` | `condition`, `timeout_ms` | 条件成立まで進む。タイムアウトは**不合格** |
| `key` | `text`, `repeat`, `gap_ms` | キーを投入する。1文字＝押下＋解放 |
| `snapshot` | `png`（任意） | framebufferのhashを記録し、PNGを書く |
| `assert` | `condition` | いま条件を検査する。**不合格でも続行する** |

各ステップに`label`を付けられる。付けるとレポートと標準エラー出力の行がそれで名乗る。

`assert`が失敗しても走行を止めないのは、1回の実行で壊れた期待を**すべて**報告する
ためである。最初の1件で止めると、残りを知るのに再実行が要る。

### 条件

| `kind` | 引数 | 意味 |
|---|---|---|
| `pixel` | `x`, `y`, `equals` \| `not_equals` | viewportの1画素がRGB565の値と一致する／しない |
| `region_non_black` | `x`,`y`,`w`,`h`, `min`／`max` | 領域内の非黒画素数が範囲に入る |
| `region_hash` | `x`,`y`,`w`,`h`, `equals` | 領域のSHA-256が固定値と一致する |
| `region_stable` | `x`,`y`,`w`,`h`, `for_ms` | 領域が指定時間変わらない |
| `region_changed` | `x`,`y`,`w`,`h` | ステップ開始時点から領域が変わった |
| `uart_contains` | `text` | UART送信列にバイト列が現れた |

色は数値でも`"0xF81F"`でも書ける。JSONに16進リテラルがないためである。

`region_stable`と`region_changed`は**過去との比較**なので`assert`では使えない。
`wait_until`専用であり、`assert`に書くと解析時に理由を添えて拒否する。

座標はviewport（320×320）で検査する。範囲外は解析時に落ちる。

### 誤りの報告

scenarioは人間とAIが手で書くため、解析エラーは**必ずJSONパスを名乗る**。

```
tetris.json: steps[3].condition.y: required, must be a non-negative integer
tetris.json: steps[7].op: unknown operation 'sing' (expected wait, wait_cycles, ...)
tetris.json: steps[2].condition.kind: 'region_stable' compares against an earlier
             moment, so it only means something inside wait_until
```

## キー投入の制約：コントローラの深さは31イベント

**1回のバーストで31イベント（＝15キー）を超えて積んではいけない。**

ClockworkPi公式STM32 keyboard firmwareは`FIFO_SIZE 31`と`KEY_COUNT_MASK 0x1F`を定義する。
Canonical BSPもカウントを`key_info[0] & 0x1f`として読む。したがって32イベント
以上を保持したコントローラは**自分を空だと報告する**ことになり、実機はその状態に
なり得ない。

この上限をモデルに入れる前は、scenarioがバーストを積む速さがファームウェアの消費を
上回り、滞留が正確に224に達した。`224 & 0x1f == 0`。BSPのドライバはそこで
「キーなし」と判断し、**恒久的に読まなくなった**。エミュレーターにしか存在しない
状態である。

現在はモデルが31で頭打ちになり、溢れたイベントを`keyboard.key_events_dropped`に
数える。scenarioの走行中に1件でも捨てられたら、標準エラーへ警告が出る。

```
warning: the keyboard controller discarded 12 event(s) — input was queued faster
than the firmware drained it. Space the keys out with gap_ms; the controller holds
at most 31 events.
```

**これが出た走行の結果は信用してはならない。** 投入したキーと、ファームウェアが
見たキーが違うからである。`gap_ms`で間隔を空けるか、バーストを短くする。

公式controllerの既定CFGは到着した側を捨て、overflow interruptをlatchする。
内部`CFG_OVERFLOW_ON`を有効にした場合だけoldestを上書きする。ただし現行公式firmwareの
I2C `receiveEvent()`にはCFG write caseがないため、後者はconformance test用の内部設定でのみ
到達させ、consumerがI2Cから変更できるとは扱わない。詳細は
[`KEYBOARD_CONFORMANCE.md`](KEYBOARD_CONFORMANCE.md)にある。

## レポート

`--json`のレポートに`scenario`節が加わる。

```json
"scenario": {
  "file": "tetris-line-clear.json",
  "name": "tetris-line-clear",
  "status": "pass",
  "poll_ms": 5,
  "steps_total": 43,
  "error": null,
  "steps": [
    {"index": 0, "op": "wait_until", "label": "game started",
     "status": "pass", "at_ms": 315, "at_cycles": 78732288,
     "detail": "1433 UART bytes seen"}
  ]
}
```

`status`は4種類あり、意味が違う。

- `pass` — 全ステップが走り、全部合格した
- `fail` — ステップが走り、期待が成立しなかった。**ファームウェアについて何か言っている**
- `incomplete` — 走行がステップを残して終わった（サイクル切れ、HardFault）。
  ファームウェアがそこまで到達しなかっただけで、期待の正否は分かっていない
- `error` — scenarioを実行できなかった（モデル未接続、PNGが書けない）

3つとも終了コードは非0だが、次にやるべきことは違う。

scenarioが全ステップを終えると走行は`stop_reason=scenario_done`で止まる。
観測するものが残っていないのに残りのサイクル予算を焼いても壁時計を消費するだけである。

## 実例

[`../scenarios/tetris-line-clear.json`](../scenarios/tetris-line-clear.json)が
唯一の実例であり、**ドッグフーディングで一度も発火させられなかったライン消去を
発火させる**ためのものである。生成手順は
[`../scenarios/README.md`](../scenarios/README.md)にある。
