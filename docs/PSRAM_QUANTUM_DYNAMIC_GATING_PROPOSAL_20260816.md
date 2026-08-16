# PSRAM接続時のstep_quantum動的化 提案書

作成日: 2026-08-16
起票: Sol（実行速度の実測調査から）
対象: `picoem-picocalc` の `picocalc-harness` / `rp2040-emu`
状態: **提案のみ。実装・変更は未実施。先行検証の結果、前提条件（§4.1）が未達のため本提案は
現状では実施できない。**

## 1. 要旨

`--psram`を付けると`step_quantum`が**run全体で1に固定**される。PSRAMを実際にアクセスしていない
区間も同じ粒度で回り続けるため、PSRAMをほとんど使わないアプリでも**実測2倍**の実行時間を払う。

LCD/PIOは既に動的判定（PIO稼働中だけ細かく刻む）になっているのに対し、PSRAMだけが静的である。
この非対称を解消できれば、PSRAM接続runの速度が改善する見込みがある。

**ただし2026-08-16の先行検証（§5.3・§4.1.1）で、本提案は現状のままでは実施できないことが
判明した。** quantumを16へ緩めると成果物が変わり、LCD初期化が壊れる。原因は、この問題を
解決するはずのper-cycleループ（§3.1）が実際にはedgeを保存しきれていないことにある。

したがって本書は次の2部構成として読むこと。

- **先に必要な作業（§4.1）** — per-cycleループの欠陥調査と修正、stress test追加。
  これは本提案の可否に関わらず、**現状の実装に穴があるという独立した問題**である。
- **その後に検討する提案（§4本体）** — quantum緩和。§4.1が完了して初めて評価可能になり、
  さらに§5.1（IRQ遅延）と§5.2（登録済み11ターゲット全数）の判断が残る。

## 2. 実測根拠

同一ファームウェア（`templates/rp2040-basic`）、同一1.5億サイクル、`--psram`の有無だけを変えて
測定した。

| 条件 | step_quantum | 実時間 | PSRAM実アクセス |
|---|---:|---:|---|
| `--psram` あり | 1 | **8.93秒** | CS立ち下がり7回、書込24 byte、読出34 byte |
| `--psram` なし | 16 | **4.47秒** | — |

**PSRAMへの実アクセスは全runで7回・計58 byteに過ぎない。** それでも2倍の時間を要している。
16倍の粒度差が2倍に留まるのは、アイドル区間の`step_until`高速化（OPT1-A）が両方に効いている
ためと考えられる。

再現コマンドは§7に記す。

## 3. 現状の機構

### 3.1 LCD/PIO側は動的

`crates/rp2040-emu/src/lib.rs`のslow path:

```rust
if !pio_idle && consumed > 1 && self.bus.has_pin_watching_device() {
    for _ in 0..consumed {
        self.tick_pio_and_route_irqs(1);
        self.update_gpio();
    }
} else {
    self.tick_pio_and_route_irqs(consumed as u32);
    self.update_gpio();
}
```

`!pio_idle`により、**PIOが実際に動いている時だけ**per-cycleループへ入る。LCD転送が無い区間は
まとめて進む。

### 3.2 PSRAM側は静的

`crates/picocalc-harness/src/main.rs`:

```rust
let step_quantum = match (args.quantum, args.stop_pc.is_some(), args.psram, args.board) {
    (None, false, true, _)                => QUANTUM_PSRAM,  // = 1
    (None, false, false, Board::PicoCalc) => QUANTUM_BOARD,  // = 16
```

`--psram`の有無だけで起動時に一度決まり、以後runの全区間に適用される。PSRAMが実際に
アクセスされているかはこの判定に入らない。

### 3.3 両者は同一commit由来

`git log -S`で確認したところ、`QUANTUM_PSRAM`と`has_pin_watching_device`のper-cycleループは
**どちらも`0bfd3a9 Connect PIO/DMA PSRAM and fix sub-quantum edge loss (Gate 3)`で同時に
導入**されている。後付けで重複したのではなく、当初から二重の安全策として置かれた。

`QUANTUM_PSRAM`のソースコメントは、静的固定の理由を明確に述べている。要約すると、PSRAMは
free-runningなPIO state machineがDMA経由で駆動するため、CPUはDMAのbusy flagしか見ておらず、
PIOのPCがtransferのどこにいるかを知らない。quantumが1より大きいと、その内側のSCK/CS edgeが
`update_gpio()`（`Psram::tick`を駆動する）に観測されないまま過ぎる、というものである。

**この懸念自体は正当である。** ただし§3.1のper-cycleループは、まさにその問題を動的に解決する
ために同時に入れられた機構であり、quantum > 1でもedgeを取りこぼさない設計になっている。
現状はquantum=1が先に効くため、`consumed > 1`が成立せず、**このループは実質的に発火しない**。

## 4. 提案

`--psram`時のstep_quantumを`QUANTUM_PSRAM`(1)から`QUANTUM_BOARD`(16)へ変更し、PSRAMのedge
保証を§3.1のper-cycleループへ一本化する。PIO稼働中はper-cycleで刻まれるためedgeは失われず、
PIOアイドル区間だけが16刻みへ戻る。

### 4.1 【必須の前提】per-cycleループの欠陥を先に修正する

**本提案は、この項が解決するまで実施できない。** §5.3の先行検証（実施済み）で、§3.1の
per-cycleループが実際にはedgeを保存しきれていないことが判明したためである。

#### 4.1.1 実測で確認された欠陥

同一ファームウェアを`--psram`付きで`quantum=1`と`quantum=16`で実行し、成果物を比較した
（手順は§7.2）。169フィールド中**26個が不一致**で、LCD初期化が壊れていた。

| 項目 | quantum=1 | quantum=16 |
|---|---|---|
| `lcd/init/slpout` | 1（実行済み） | **0（未実行）** |
| `lcd/state/sleeping` | False | **True（スリープのまま）** |
| `lcd/madctl` | 0x48 | **0x00（未設定）** |
| `psram/tick_count` | 4,532,105 | **1,537,371（約1/3）** |

`lcd/unknown_commands`はquantum=1で13種類（`0x35, 0xb1, 0xb4, 0xb7, 0xb9, 0xc0, 0xc1, 0xc2,
0xc5, 0xe0, 0xe1, 0xe8, 0xf0`）観測されるのに対し、quantum=16では7種類（`0xb4, 0xb9, 0xc0,
0xc1, 0xc5, 0xe8, 0xf0`）しか残らない。**SPIのedgeが取りこぼされ、コマンドが欠落している。**
`psram/tick_count`が約1/3になっているのも同じ現象である。

UARTだけはbyte一致したが、これはファームウェアがLCDの失敗を検知していないだけで、実質的には
LCDが起動していない。**UART一致だけを見て「変化なし」と判断してはならない。**

#### 4.1.2 これが意味すること

`QUANTUM_PSRAM = 1`のソースコメントが述べる懸念——「quantum > 1だとSCK/CS edgeが
`update_gpio()`に観測されないまま過ぎる」——は**実測で裏付けられた。**

重要なのは、§3.1のper-cycleループ（`!pio_idle && consumed > 1 && has_pin_watching_device()`）
が**まさにこの問題を解決するために存在するにもかかわらず、機能していない**点である。
quantum=16ではこのループが発火する条件（`consumed > 1`）を満たすはずだが、それでもedgeが
失われている。

つまり現状は、`QUANTUM_PSRAM = 1`という静的固定が**唯一の実効的な防御**であり、動的ループは
設計意図を果たせていない。二重の安全策のうち片方が実際には効いていない状態である。

#### 4.1.3 必要な作業（本提案の前提条件）

次の順序で実施する。いずれかを飛ばして§4のquantum緩和へ進んではならない。

1. **原因調査。** `consumed > 1`の分岐が期待通りedgeを保存しない理由を特定する。候補として、
   `tick_pio_and_route_irqs(1)`を`consumed`回呼んでも、その内部で参照する`bus.gpio_in`の
   スナップショット取得タイミングや、PIO側のclkdiv処理（clkdiv=2.0では2 master cycleに1
   PIO命令）との噛み合わせが疑われるが、**未調査である。推測で修正しない。**
2. **`tech_debt.md`のstress test追加。** 下記の既知項目を解消し、機構が全edgeを捉えることを
   テストで証明できる状態にする。

   > ### PSRAM PIO-integration tests cover only 1 edge/quantum
   > `pio_integration::pio_driven_write_then_read_round_trip`等は`step_quantum=4`でSCKが
   > 2 sysclkごとにtoggleするため、1 step あたり rising edge は1回。`update_gpio()`が
   > `consumed`回でなく2回しか走らなくてもtestは通ってしまう。`step_quantum=64`でSCKを
   > 毎sysclk toggleさせるstress testを追加し、interleave fixが本当に全edgeを捉えることを
   > 証明すべき。

   このstress testは、修正前は**落ちる**ことを先に確認する。落ちないなら、テストが
   §4.1.1の欠陥を再現できていない。
3. **修正。** 1の原因を除去し、2のstress testが通ることを確認する。
4. **§5.3の再実行。** quantum=1と16で成果物が一致することを実測で確認する。ここで初めて
   §4のquantum緩和が検討可能になる。

**4が成立しない限り、§4は実施しない。** 仮に4が成立しても、§5.1（IRQ遅延の変化）と
§5.2（登録済み11ターゲット全数への影響）は別途残る。

## 5. リスクと未解決事項

### 5.1 正確性が変わる（最大の懸念）

`lib.rs`のコメントが明記する通り、bulk pathではIRQ delivery latencyが「≤1 cycle」から
「≤step_quantum-1 cycles」へ伸びる。per-cycle path（PIO稼働中）は≤1 cycleを維持するが、
**PIOアイドル区間のIRQ遅延は変化する。**

したがって本変更は**exactness-preservingではない可能性が高い。** cycle数、report SHA、
behavior hashが変わりうる。これはこのプロジェクトが最も重視してきた性質であり、OPT2/OPT3が
性能条件未達で正式終了した経緯からも、性能のために正確性を譲る判断は容易ではない。

### 5.2 影響範囲は登録済みターゲット全数

`reference-projects/firmware-targets.json`を走査した結果、`psram: true`を持つターゲットは
次の11件で、これは実質的に登録済みターゲットの全数である。

```
picocalc-audio-r1, picocalc-helloworld-a, picocalc-multicore-r1,
picocalc-multicore-r2, picocalc-template-b, picoedit-r1,
picotetris-opt1a, picotetris-opt1b, picotetris-r3,
picotetris-r4, picotetris-r5
```

§5.1の通りartifactが変われば、**全ターゲットが新revisionを要する。** 実機相関済みの
R5/NEXT-1/NEXT-2A/NEXT-2B baselineとの同一性も再確認が必要になる。

### 5.3 先行検証（2026-08-16 実施済み・結果は不成立）

コード変更なしで効果と安全性を確かめるため、`--quantum 16 --psram`の明示指定による検証を
先に行った。現行CLIは`--quantum` overrideを既に受け付けるため、ソース変更もbuildも不要である。

**結果：成果物が変わり、LCD初期化が壊れた。** 詳細と数値は§4.1.1に記す。

この検証により、§4の提案は現状のままでは実施できないこと、そして§3.1のper-cycleループに
実際の欠陥があることが判明した。**先にコードを変更せず測定した判断は正しかった。**

なお本検証は成果物のbyte比較であり実行時間の測定ではないため、host CPUの競合状態に影響されない。
他プロセスがemulatorを使用中でも、出力先を分離すれば安全に再現できる。

## 6. 優先度

**§4.1（per-cycleループの欠陥修正）は「高」。** 当初は「PSRAMを使わないアプリが2倍のコストを
払っている」という性能問題として起票したが、先行検証の結果、**現行実装のedge保存機構に
実際の穴があることが判明した**。これは性能の話ではなく正確性の話であり、優先度が異なる。

現状は`QUANTUM_PSRAM = 1`がその穴を覆い隠しているため、既定設定で使う限り実害は出ていない。
しかし`--quantum`を明示指定できる以上、利用者が意図せず壊れた条件で実行し、
**LCDが起動していないのにUARTは一致するため気づかない**という経路が存在する。

**§4本体（quantum緩和）は「中」。** 性能改善であり、§4.1完了後に§5.1・§5.2を踏まえて
判断する。§4.1の結果次第では、そもそも緩和が不可能と結論づく可能性もある。

## 7. 再現手順

以下は共通の前提。実行中の他プロセスへ影響させないため、runnerを`/tmp`へ退避してから使い、
出力先もrunごとに分離する。

```sh
R=/path/to/picoem-picocalc
E=/path/to/picocalc_emu
BIN="$E/templates/rp2040-basic/build/picocalc_app.bin"
cp "$R/target/release/picocalc-run" /tmp/q-audit-runner
```

### 7.1 §2の速度比較（PSRAM有無）

```sh
# PSRAM あり（quantum=1）
/usr/bin/time -f "wall=%e s" /tmp/q-audit-runner --bin "$BIN" \
  --bootrom "$R/roms/rp2040/bootrom-rp2040-b2.bin" \
  --board picocalc --lcd-variant pio-rgb565 --psram --sd --keyboard \
  --cycles 150000000 --expect-stop cycle_limit --json /tmp/on.json

# PSRAM なし（quantum=16）
/usr/bin/time -f "wall=%e s" /tmp/q-audit-runner --bin "$BIN" \
  --bootrom "$R/roms/rp2040/bootrom-rp2040-b2.bin" \
  --board picocalc --lcd-variant pio-rgb565 --sd --keyboard \
  --cycles 150000000 --expect-stop cycle_limit --json /tmp/off.json
```

### 7.2 §4.1.1のedge欠落検証（PSRAM固定、quantumのみ変更）

**この検証は成果物のbyte比較であり実行時間を測らないため、host CPUが競合していても結果は
変わらない。** 他プロセスがemulatorを使用中でも安全に実行できる。

```sh
mkdir -p /tmp/q-audit/q1 /tmp/q-audit/q16
for tag in q1 q16; do
  [ "$tag" = q1 ] && QOPT="" || QOPT="--quantum 16"
  /tmp/q-audit-runner --bin "$BIN" \
    --bootrom "$R/roms/rp2040/bootrom-rp2040-b2.bin" \
    --board picocalc --lcd-variant pio-rgb565 --psram --sd --keyboard \
    --cycles 40000000 --expect-stop cycle_limit $QOPT \
    --json /tmp/q-audit/$tag/report.json \
    --uart /tmp/q-audit/$tag/uart.log
done
```

比較時は`step_quantum`フィールド自体の差を除外し、残りのフィールドを突き合わせる。
**UARTのbyte一致だけで「変化なし」と判断しないこと**（§4.1.1）。確認すべき主要フィールドは
`lcd/init/slpout`、`lcd/state/sleeping`、`lcd/madctl`、`lcd/unknown_commands`、
`psram/tick_count`である。

### 7.3 測定環境

WSL Ubuntu 24.04、12 logical CPU、release runner、backend `ae49c6c`。
§7.1のwall time測定時のloadaverageは完全静穏ではないため、正式な採否判断には
`docs/history/R5_REALTIME_PERFORMANCE.md`の手順（単独・逐次・warm-up 1回＋10回・中央値・
95% CI）で取り直すこと。本書の速度値は傾向を示すものである。
§7.2のartifact比較はこの制約を受けない。

## 8. 参考

- `crates/picocalc-harness/src/main.rs`（`QUANTUM_PSRAM`定数とその根拠コメント、quantum選択）
- `crates/rp2040-emu/src/lib.rs`（`!pio_idle && consumed > 1 && has_pin_watching_device()`）
- `picoem-picocalc/tech_debt.md`「PSRAM PIO-integration tests cover only 1 edge/quantum」
- commit `0bfd3a9 Connect PIO/DMA PSRAM and fix sub-quantum edge loss (Gate 3)`
- `docs/history/OPT2_D_LEVER_COMPARISON.md`（PIO occupancy 70.25%、running比の内訳）
- `docs/history/R5_REALTIME_PERFORMANCE.md`（正式な性能測定手順）
