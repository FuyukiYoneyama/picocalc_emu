# VRP-2-c／d compatibility evidence（2026-08-29）

この記録は、Validated Realtime Preview backendのVRP-2-c／dをローカルで
受入した結果を固定する。これはGUI、音声ストリーミング、実機相関、または
`realtime-1x-qualified`を宣言する記録ではない。

## VRP-2-c: machine API schema 1

`picoem-picocalc/crates/picocalc-harness/tests/fixtures/machine-api-schema1-golden.jsonl`
に、既存machine APIの8交換をJSON Lines形式で固定した。

| 行 | operation | 確認内容 |
|---:|---|---|
| 1 | `observe` | `machine` domainの初期状態 |
| 2 | `step` | dispatch数とcycle advance |
| 3 | `subscribe` | framebuffer／stop／UARTの購読 |
| 4 | `run` | cycle budget停止 |
| 5 | `input` | pressed／held／releasedのキュー投入 |
| 6 | `observe` | machine／UART／framebuffer／unsupported-MMIO |
| 7 | `run_until` | cycle条件とpoll境界 |
| 8 | `snapshot` | deterministic PNGとRGB565 digest |

`machine_api_schema1_golden.rs`はrepository-ownedの`uart_hello.bin`と合成
bootromを実runnerへ渡し、各requestを順に送信する。応答のschema、id、cycle、
result、digestを構造化JSON値としてfixtureと完全一致比較し、最後に
`golden.png`の生成も確認する。preview専用の`observe` domainはこのtranscriptへ
混在させず、別のpreview E2Eで加法的変更として検査する。

実行したコマンドと結果:

```sh
cargo test -p picocalc-harness --test machine_api_schema1_golden --locked
# 1 passed
```

## VRP-2-d: UART RX正常系とoverrun

`preview_api_e2e.rs`内で、opaque binaryをリポジトリへ追加せず、決定的な
Thumb-1 raw-flash fixtureを生成する。このfixtureはUART0を設定し、ready marker
を送信した後、RX FIFOから読んだbyteをそのままTXへechoする。

previewへ`a`〜`q`の17 byteを連続投入した結果を次のように検査する。

- 最初の16 byteはacceptedとなり、guest echoが投入順で返る
- 17 byte目はbounded RX FIFOのoverrunとなる
- statusの`rx_accepted`／`rx_overrun`とdirection付きerrorが一致する
- 既存のRX disabled拒否経路も維持する
- clean `quit`は`goodbye`とexit 0で終わる

実行したコマンドと結果:

```sh
cargo test -p picocalc-harness --test preview_api_e2e --locked
# 5 passed
cargo clippy -p picocalc-harness --tests --locked -- -D warnings
# passed
```

fixtureは各テストの一時パスへ生成し、テスト終了時に自分の生成物だけを
削除する。host arrival timeはemulated cycleへ混入させず、UART RXはkeyboard
入力やprocess stdinとは別の経路である。

## 現在の境界

VRP-2-c／dのローカル互換性証拠は、VRP-2-aのversioned target／receiptと同じ
backend revisionで作成した。これによりmachine APIの既存domain不変性とUART RXの
positive／overflow semanticsは確認済みである。

ただしVRP-2全体の完了には、VRP-2-aのregistered targetを使ってbatch／machine
API／preview APIを同一virtual cycleで再実行し、report-compatible observation
projection／digestをreceipt／admissionへ接続する完全digest gateが残っている。
この記録だけでtarget capabilityを昇格してはならない。
