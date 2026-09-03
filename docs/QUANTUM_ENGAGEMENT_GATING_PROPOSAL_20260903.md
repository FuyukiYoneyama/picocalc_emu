# PicoCalc step_quantum の engagement gating 提案書

- Status: **レビュー済み候補。単純な現在状態判定は不採用。実装・測定は未開始。**
- 作成日: 2026-09-03
- 対象: `picoem-picocalc` の `picocalc-harness` / `rp2040-emu`
- 先行文書: [`history/PSRAM_QUANTUM_DYNAMIC_GATING_PROPOSAL_20260816.md`](history/PSRAM_QUANTUM_DYNAMIC_GATING_PROPOSAL_20260816.md)（2026-08-16、実施保留）
- 関連: [`RP2040_CPU_APPLICATION_OPTIMIZATION_IMPLEMENTATION_PLAN_20260830.md`](RP2040_CPU_APPLICATION_OPTIMIZATION_IMPLEMENTATION_PLAN_20260830.md)
- 現行計画: [`PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md`](PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md)

本書は高速化候補の根拠と反証条件を残すレビュー資料であり、正典計画ではない。実施順序と
採否は現行計画を優先する。実装・commit・push は本書だけを根拠に開始しない。

## レビュー判断

候補の着眼点には可能性があるが、当初案の「step開始時の現在状態＋1 stepヒステリシス」だけでは
安全ではない。`step_serial_with_external`はCPUをquantum分先に実行してから周辺装置を進めるため、
disengagedで始まったstepの途中でCPUがCS assert、PIO enable、DMA start、I2C startを行う
`false → true`遷移を事前に検出できない。

したがって本候補を実装へ進めるには、次をすべて満たす必要がある。

1. semantics-affectingなMMIO／GPIO書込みを実行した命令の直後でCPU batchを終了する
   **engagement transition barrier**を設ける。
2. TIMER、SysTick、DMA、PIO、外部入力scenarioなど、既知の次回deadlineを越えないようquantumを
   短縮する。
3. 初版候補は64ではなく16とし、q1へ保守的にfallbackできるようにする。
4. 機会量とバリア実装可能性を確認した後、代表2アプリの正確性とwall時間をscreeningし、効果が
   確認できた場合だけ全target回帰へ進む。

以下に残るH1、engagement条件、既存計測は候補の分析材料である。上記の補正なしに§4の当初案を
production実装してはならない。

## 0. 先行文書との関係

2026-08-16 の先行提案は、`--psram` 時の `step_quantum` を 1 から 16 へ緩め、edge 保証を
既存の per-cycle ループへ一本化する案だった。同文書 §5.3 の先行検証で成果物が変わり
（LCD 初期化が壊れる）、§4.1「per-cycle ループの欠陥を先に修正する」を前提条件として
実施保留になった。

本書はその判断を覆さない。**前提条件の立て方を変える。**

先行提案の前提条件は「per-cycle ループを直す」だった。本書は §3 で、per-cycle ループが
直せる種類の欠陥を持っていない可能性を示し、代わりに **quantum を緩める区間を、観測者が
存在しない区間だけに限定する**（engagement gating）を提案する。

先行提案 §5.2 は「登録済み 11 ターゲット全数の再 revision」を負担として挙げていた。
その 11 件は 2026-08-16 時点の `psram: true` 件数であり、2026-09-03 現在の登録済み
ターゲットは **22 件、うち `psram: true` は 22 件**、つまり全数である。本書で件数を
論じるときは 22 件を使う。

## 1. 要旨

`reference-projects/firmware-targets.json` の登録済み 22 ターゲットは、**全件が
`runner.quantum: 1`、全件が `runner.psram: true`** である。CPU 高速化プロジェクトの
計測 workload 2 本も同じである。

| target | revision | quantum | psram | lcd_variant | cycles |
|---|---:|---:|---|---|---:|
| `picotetris-opt1b-vrp5` | 10 | 1 | true | `pio-rgb565` | 8,000,000,000 |
| `picoedit-r1-vrp2f` | 4 | 1 | true | `pio-rgb565` | 4,000,000,000 |

`quantum=1` では `Emulator::step_serial_with_external` の本体が **エミュレート 1 サイクル
ごとに 1 回**実行される。M0+ の 1 命令は 1〜3 サイクルなので、命令あたり 1〜3 周である。

同一ファームで `--psram` の有無だけを変えた既存実測（先行提案 §2）は次のとおり。

| 条件 | `step_quantum` | 実時間 | PSRAM 実アクセス |
|---|---:|---:|---|
| `--psram` あり | 1 | **8.93 秒** | CS 立下り 7 回、計 58 byte |
| `--psram` なし | 16 | **4.47 秒** | — |

PSRAM が実際に使われたのは 7 回・58 バイトである。それでも 2 倍を支払っている。

この偏りは現行の記録でも確認できる。`rp2040-cpu-p1-a-correctness-20260901-01` の
baseline projection は次のとおりである。

| workload | cycles | `psram.cs_falling_count` | PSRAM byte 合計 |
|---|---:|---:|---:|
| `picotetris-opt1b-vrp5` | 927,528,659 | 7 | 58 |
| `picoedit-r1-vrp2f` | 827,799,818 | 250 | 2,625 |

本書は、この 2 倍のうち回収可能な部分を、正確性を落とさずに取ることを提案する。

## 2. 現状の機構（ソース）

### 2.1 quantum は起動時に静的決定される

`crates/picocalc-harness/src/main.rs`:

```rust
const QUANTUM_FREE_RUN: u32 = 64;   // :107
const QUANTUM_BOARD:    u32 = 16;   // :135
const QUANTUM_PSRAM:    u32 = 1;    // :157
```

`--psram` の有無だけで起動時に一度決まり、run 全体へ適用される（main.rs:5390）。PSRAM が
実際にアクセスされているかは判定に入らない。理由は `QUANTUM_PSRAM` のソースコメントに
記載があり、「PSRAM は free-running な PIO SM が DMA 経由で駆動するため、CPU は DMA の
busy flag しか見ておらず、`quantum > 1` では内側の SCK/CS edge が `update_gpio()` に
観測されないまま過ぎる」である。

**これは物理制約ではなく、モデルの取りこぼしに対する回避策である。**

### 2.2 quantum=1 が固定するコスト

`crates/rp2040-emu/src/lib.rs` の `step_serial_with_external`。1 サイクルごとに次が回る。

- 両コアの `is_halted` / `wfe_waiting` 判定、`set_active_core`、`drain_cache_invalidations`
- `refresh_sio_fifo_irqs`、`both_cores_blocked` 判定、`blocked_advance`
- fast_path 述語（`pio_all_idle` / `irq_pending` / SysTick / `all_peripherals_idle`）
- slow path: `Bus::tick_peripherals`（timer poll、uart0/1、SPI pad 観測、spi0/1、i2c0/1、
  external virtual time、adc、pwm、dma）、`tick_systick`、`tick_pio_and_route_irqs`、
  `update_gpio`、`drain_pending_irqs_to_cores`、wake checks

fast_path は `pio_all_idle` を要求する。lib.rs 同箇所のコメントが
「PicoCalc workloads keep an SM enabled for long periods; while it is active the slow path
is already mandatory」と述べるとおり、PicoCalc では fast_path はほとんど成立しない。

### 2.3 観測者は 2 種類ある

`Bus::has_pin_watching_device()`（bus/mod.rs:2697）:

```rust
self.psram.is_some() || !self.pin_devices.is_empty()
```

`update_gpio()`（lib.rs:1704）は pad merge の後に `Psram::tick(out)` と各 `pin_devices` の
`tick(out)` を呼ぶ。PicoCalc の `pio-rgb565` 構成では LCD も `pin_devices` 側にいる。
**したがって観測者は PSRAM だけではない。** 先行提案が PSRAM を主語にしていた点は、
ここで補正する。

`has_pin_watching_device()` が答えているのは「装置が**接続されているか**」であり、
「装置がいま**観測しうるか**」ではない。本提案の中心はこの一語の差である。

## 3. 仮説 H1 — per-cycle ループが保存しているのは PIO 側の粒度だけ

先行提案 §4.1.3 の第 1 項「原因調査（未調査）」に対する仮説を、ソース読解から提示する。
**検証前の仮説であり、確定した原因ではない。**

### 3.1 slow path の per-cycle ループ

lib.rs:1207-1215:

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

`PioBlock::step_n`（picoem-common/src/pio/mod.rs:401）は `step_n_with_pins`（:406）への
薄いラッパーで、その本体は `for _ in 0..n { self.step_with_pins(...) }` である。
したがって PIO 内部の時間分解能は、bulk 呼び出しでも per-cycle 呼び出しでも同一である。
per-cycle ループが追加で与えているのは、**PIO の各サイクル後に `update_gpio()` を挟むこと**、
すなわち PIO が作った pad edge を観測者へ届けることだけである。

なお `step_n_with_pins` は先頭に `if self.sm_enabled_mask == 0 { return; }` の早期脱出を
持つ（:407、回帰試験 `step_n_with_pins_short_circuits_on_idle_block`）。SM が全 disable
のときは既に短絡している。

### 3.2 保存されていない軸

`step_serial_with_external` の実行順は次である。

1. while ループで **CPU が quantum 分のサイクルを全部消費する**
2. その後に `tick_peripherals` / PIO / `update_gpio` が回る

CPU が quantum 内で SIO 経由に制御ピン（LCD の DC/CS 等）を書き換えた場合、その変更は 1 で
確定し、2 の per-cycle ループはすべて**変更後の pad 状態**に対して PIO を再生する。PIO 側の
edge は保存されるが、**CPU の pad 書き込みと PIO 転送の相対順序は quantum 粒度のまま**である。

これは先行提案 §4.1.1 の観測とよく一致する。`--quantum 16` で LCD 初期化コマンドが欠落し
（slpout 未実行、madctl=0x00、`unknown_commands` が 13 種→7 種）、一方で CPU が
BSY/TXSTALL ポーリングに架かっている転送本体は壊れなかった。LCD 初期化は
「DC 操作 → 書込 → 待ち → DC 操作」が CPU 側で密に交互する区間であり、転送本体は CPU が
park されている区間である。

H1 が正しければ、per-cycle ループは**この欠陥を修正できる種類のものではない**。
先行提案 §3.3 が「二重の安全策」と表現した状態の正確な形は、
**片方は最初から別の軸を守っていた**、である。

### 3.3 H1 の確認方法

最初から完全インターリーブ版を作らない。現行計画PERF-Q0のmid-quantum transition fixtureで、
CPU側書込みとPIO／device観測の順序差が再現するかを先に確認する。それで原因が特定できない場合だけ、
一つの`/tmp` scratch worktreeでCPU 1 cycle＋PIO 1 cycle＋`update_gpio`の実験版を作り、
`templates/rp2040-basic`のq1／q16成果物を比較する。本番tree、registry、正式targetは変更しない。

## 4. 提案 — engagement gating

### 4.1 変更内容

`step_quantum` を起動時の静的値から、**安全な上限をstepごとに評価する値**へ変える。

```
quantum = if engaged { 1 } else { min(16, cycles_to_next_known_deadline) }
```

`engaged` は「pin-watching device がstep開始時点でedgeを観測しうるか」を保守側に判定する
述語である。既存状態から作る初版候補を次に固定する。

- PSRAM が接続されており、CS が assert されている、**または**
- いずれかの PIO SM が enabled であり、かつ `stalled_on_empty_tx()`
  （picoem-common/src/pio/sm.rs:197）でない、**または**
- いずれかの DMA チャネルが busy である、**または**
- 外部 I2C device が接続されており、対応する I2C 周辺が idle でない、**または**
- 直前の step で engaged だった（1 step分の補助ヒステリシス）

`has_pin_watching_device()` は変更せず残す。engagement 述語はその上に重ねる。

この述語はstep途中の`false → true`を検出できないため、単独では使わない。CPUがCS、PIO、DMA、
I2Cその他の観測意味を変えるMMIO／GPIO書込みを行った場合は、その命令直後でbatchを終了し、
消費したcycle分だけ周辺装置を進めてからq1で再評価する。1 stepヒステリシスはこのbarrierの
代替ではない。

外部 I2C の項は、`Bus::tick_peripherals` の `advance_external_virtual_time()` が PSRAM /
PIO / DMA のいずれとも独立した経路であり、登録済み 22 件に I2C-EXT を使う
`picocalc-clock-i2c-env-e5` が含まれるために必要である。

### 4.2 なぜゲストの観測可能動作が構成的に保たれるか

`engaged == false`で、かつtransition barrierとdeadline capによりstep途中の状態変化を越えない
区間では、次が同時に成立する。

- PSRAM の CS が deassert されている → `Psram::tick` は CS/SCK edge を一切消費しない
  （picoem-devices/src/psram.rs:336、`if !cs` の内側でのみ shift 処理が走る）
- 全 PIO SM が disabled か TX 待ち stall → PIO は pad を変化させない
- DMA が非稼働 → PIO FIFO への供給も起きない
- 外部 I2C 周辺が idle → 共有 virtual-time snapshot の消費者がいない

したがってこの限定区間では、quantumが1でも16でも、**ゲストが観測できる系列が同一である**と
期待できる。ただし当初案の現在状態判定だけでは、この限定区間を構成的に保証できない。
transition fixtureと実アプリ比較による確認を受入条件にする。

**ただしこの主張は「ゲストの観測可能動作」に限られる。report 全体の SHA には及ばない。**
理由を次項に分離して記す。

### 4.2.1 projection 一致の限界（先行草稿からの訂正）

本提案の先行草稿は「report SHA、behavior hash、cycle 数は変化しない」と書いていた。
これは**誤りである**。`guest_observation_projection` は `backend_build` と
`backend_commit` **だけ**を除去するため、次の 2 つの emulator 内部計上値が projection に
残る。

| field | 現行値（`picotetris-opt1b-vrp5`） | 現行値（`picoedit-r1-vrp2f`） | 本提案での挙動 |
|---|---:|---:|---|
| `psram.tick_count` | 305,719,534 | 158,844,047 | **必ず変化する** |
| `step_quantum` | 1 | 1 | **意味が変わる** |

`psram.tick_count` は `Psram::tick()` 先頭（psram.rs:316）で `if !cs` の**外側**を
無条件にインクリメントする**呼び出し回数カウンタ**であり、`update_gpio()` から毎回
呼ばれて報告 JSON へ出力される（main.rs:4658、5696）。本提案は disengaged 区間の
`update_gpio()` 呼び出し頻度を下げる提案なので、この値は定義上必ず変わる。
現行の比率は PicoTetris で `tick_count / cycles = 0.3296`、PicoEdit で `0.1919` である。

`step_quantum` は現在 run 全体の静的スカラとして projection に含まれる。step ごとの 2 値
へ変える設計では、この field が何を表すのかを定義し直す必要がある。

一方 `behavior_trace.rs` の `PsramObservation` は `cs_falling_count` / `bytes_written` /
`bytes_read` のみを持ち、`tick_count` を含まない。**behavior hash は影響を受けない。**

baseline projectionのcounter系fieldを棚卸しした結果は次のとおりである。

| field／group | 性質 | 判定 |
|---|---|---|
| `psram.tick_count` | host側のdevice tick呼出し回数 | 除外必須 |
| `step_quantum` | run全体を表す現行の静的スカラ | 除外し、dynamic時の意味を再定義 |
| `audio_sink.*`、TIMER／DMA event・miss counter | ゲスト駆動。既存quantum不変testの契約対象 | 一致必須 |
| `flash.erase_count`／`program_count`、`sd.block_count`、`scenario.*` | ゲスト動作または固定入力に由来 | 一致必須 |

したがって §6 の受入条件は、この 2 field を明示的に除外した projection で判定する。
除外がこの2 fieldだけである根拠は、上記棚卸しと、既存`dma_quantum_invariance.rs`が
`audio_sink`観測ブロック全体を含めて不変性を要求していることである。除外する field は本書で
固定し、これ以外の除外を後から追加しない。除外した 2 field は
別項目として、予測した方向にのみ動いたことを独立に確認する。

### 4.2.2 §8 との設計上の二択

per-cycle ループ（lib.rs:1207）の条件 `has_pin_watching_device()` は、PSRAM 接続時は
disengaged 区間でも真のままである。したがって次の二択になる。

- **ループを残す**: quantum=16でも`update_gpio`は16回回るため`tick_count`は保存され、
  節約は CPU 側 while ループと `tick_peripherals` の 1 step 化に限られる
- **ループを削る**（§8 の案）: 節約は大きいが `tick_count` が変わる

**この二択は §5 の disengaged 比率計測より前に決める。** どちらを選んだかを §7 の
測定計画と §6 の受入条件へ先に固定し、測定結果を見てから選び直さない。

### 4.3 IRQ 遅延

bulk pathではIRQ delivery latencyが伸び得る。TIMERのwindow matchだけを根拠に安全とは判定せず、
次のTIMER／SysTick／device／scenario deadlineまでのcycle数でquantumをcapする。deadlineを安全に
取得できないsourceが一つでもあれば、その状態ではq1へfallbackする。

## 5. 反証条件 — 先に測る

**PicoCalc で `engaged == false` の区間が十分に存在しなければ、本提案は無価値である。**
LCD の PIO SM が常時 enabled かつ非 stall なら、gate は常時 engaged になり、何も速くならない。

実装前に、これを 1 run で確定させる。

1. counting のみの scratch build を作る（本番 tree 非変更、feature-gated）。
   各 step で `engaged` を評価し、true/false の step 数とサイクル数だけを積算する。
   **quantum は 1 のまま変えない。** 成果物は変わらないので既存 target をそのまま使える。
2. `picotetris-opt1b-vrp5` と `picoedit-r1-vrp2f` を各 1 回実行する。
3. `disengaged_cycles / total_cycles` を、step開始時状態から求めた機会量の上限値として記録する。

transition barrierとdeadline capはwindow途中でbatchを打ち切るため、実際にまとめられるcycle比率は
この値以下になる。この比率をwall-time改善率または実効batch率として読まない。

判定は測定前に固定する。

| disengaged 比率 | 判定 |
|---|---|
| 両アプリとも < 20% | **本提案を取り下げる。** engagement の定義を緩めて再挑戦しない |
| どちらかが 20〜50% | transition barrierの実装可能性を確認する |
| どちらかが > 50% | transition barrierの実装可能性を優先して確認する |

比率が低かった場合に述語を緩めることを禁じる。緩めた述語は §4.2 の構成的同一性を壊す。

## 6. 完了条件

完了条件は現行計画のPERF-Q0〜Q5を正とする。要点は次のとおりである。

1. 代表2アプリのどちらかでdisengaged比率が20%以上あり、transition barrierとdeadline capを
   実装できる見通しがある。
2. 初版q16候補がtransition fixture、PSRAM stress、TIMER／DMA／audio／NVIC境界、SysTick境界、
   代表2アプリのguest-visible observationでq1と一致する。PSRAMは既存
   `psram_pio_edge_interleave.rs`、TIMER／DMA／audio／NVICは既存
   `dma_quantum_invariance.rs`、SysTickは既存SysTick／exception test群を拡張し、同じ契約を
   重複する新規test fileは作らない。
3. 代表2アプリのcombined wall短縮が採用screeningを通り、どちらにも3%超の退行がない。
4. 効果確認後に限って全target回帰、代表behavior trace、unit／integration／CLI／feature gateを
   通す。guest-visible差は例外を追加せず不採用とする。
5. 採用時はmainへ統合し、不採用時は判断記録を残してcandidate branch／worktreeを削除する。

## 7. 測定計画

**効果量に測定精度を合わせる。** CPU候補用の40 measured run＋27 anchor＋60秒cooldownは使わない。
正確性の小gateを通した後、Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）で
baseline／candidateをAB・BAの2 pairずつ実行し、wall時間を主指標にする。P2-A cleanup後の
clean commitを共通baselineとして固定し、candidateがそのcommitから派生していることを開始直前に
照合する。hostで利用可能な単一vCPUを一つ選び、全runを`--cpu`相当の同一affinityへ固定して、
選択値と固定方法をrecordへ保存する。affinityを固定できないhostでは測定を開始しない。

- combined wall短縮5%未満: 不採用
- 5%以上10%未満: コードを削減・単純化する場合だけ採用候補
- 10%以上: 全target回帰へ進む
- どちらか一方が3%超退行: combined値にかかわらず不採用

境界から2 percentage point以内の場合だけ1 pairを追加できる。効果が境界から離れているのに
run数を増やして有意差を探さない。

証拠は `firmware-validation/evidence/quantum-engagement-<YYYYMMDD>-NN/` へ、
コマンド、host 情報、raw 出力、成果物 SHA、判定を置く。CPU A/B の record schema は使わない。

## 8. 削除するもの

本提案が完了し、かつ §4.2.2 で「ループを削る」を選んだ場合、次を削除または縮小する。

- H1 が支持され、engagement gating が成立した場合、slow path の per-cycle ループ
  （`!pio_idle && consumed > 1 && has_pin_watching_device()`、lib.rs:1207）は
  **engaged な区間では quantum=1 なので発火せず、disengaged な区間では観測者がいない**。
  死んだ分岐になるため削除する。残す場合は残す理由を記録する。
- `QUANTUM_PSRAM` 定数と、`--psram` による quantum 静的決定の分岐（main.rs:157、5390）。

「ループを残す」を選んだ場合、前者は適用しない。その場合も `QUANTUM_PSRAM` の静的分岐は
削除対象に残る。

**追加のみで終わる変更にしない。** 純増になった場合は設計を見直す。

## 9. 実行順

| 順序 | 作業 | 成果物 | 失敗時 |
|---:|---|---|---|
| 1 | 機会量counterとmid-quantum transition fixture | 2 workloadの比率、危険遷移の再現 | 比率不足またはbarrier不能なら終了 |
| 2 | P2-A不採用runtimeの独立cleanupとbaseline再固定 | clean baseline commit | cleanup差分が混ざれば候補を作らない |
| 3 | q16＋transition barrier＋deadline cap | baselineから派生した最小candidateとunit test | q1意味論を保てなければ終了 |
| 4 | 小さい正確性gate | fixtureと代表2アプリの比較 | guest-visible差があれば終了 |
| 5 | 代表2アプリのwall-time screening | 同一affinityのAB／BA各2 pair | §7の性能条件未達なら終了 |
| 6 | 採用前の全target回帰 | regression record | 差が1件でもあれば終了 |
| 7 | 不要分岐の削除、統合、後始末 | decision、main commit | 不採用コードをmainへ残さない |

## 10. 中止条件

- §5 の比率が閾値未満なのに、述語を緩めて再測定した
- transition barrierなしで現在状態判定だけをproduction実装した
- 既知deadlineを越える可能性がある状態でq16を使った
- guest observationの不一致を、§4.2.1で固定した2 field以外の除外や例外規定で通した
- §7 の判定基準を結果を見た後に変更した
- 効果screening前に全targetの長時間回帰を開始した

いずれかに該当した時点で中止し、原因を記録して新しい提案として立て直す。

## 11. CPU 高速化プロジェクトとの関係

本提案が成立した場合、`picotetris-opt1b-vrp5` / `picoedit-r1-vrp2f` の今後の性能baselineは
変わる。ただし採用済みP1-Aの過去測定は、その時点のbaselineに対する不変記録であり無効には
ならない。P1-Aを再測定するためだけのrunは行わない。

したがって順序は本提案が先である。本提案の判定が出るまで、P2-T（threaded、CPU 計画 §856）、
P3（PGO、同 §882）を含む CPU 候補の新規 A/B を開始しない。P1-A の
`decode-invalidation-tag-guard` はcorrectness gateを通った採用済み変更として既定のまま残す。
今後、新しいCPU候補の限界効果を測る場合だけ、その時点のbackendをbaselineにする。

CPU 単体の直接測定（baseline 中央値 124.963556 MHz）と実アプリのスループット
（anchor 約 4.9M cycles/s）の比は、実アプリのホスト時間に占める CPU パスが**一桁%**である
可能性を示す。2 つの値はスコープが異なるため厳密な分解ではないが、§5 の disengaged 比率
計測は、同じ疑問に対するスコープの揃った最初の回答にもなる。

## 12. 未確認事項

- H1 は仮説である。§3.3 で検証するまで原因として扱わない。
- §4.1 の`engaged`述語、transition barrier、deadline capは初版案であり、PERF-Q0で実装可能性を
  確認するまで正しさは確定していない。
- §4.3 の IRQ 遅延の議論は、TIMER 以外の lazy source が将来追加された場合に再検討を要する。
- `pin_devices` 側（PicoCalc では LCD）の engagement 条件を、PIO SM の enable/stall 状態
  だけで十分に表現できるかは未確認である。§5 の計測で LCD PIO の稼働率が高すぎると
  分かった場合、それは本提案の反証であって、述語を細分化する理由にはしない。
- §4.1 の外部 I2C 項は、`advance_external_virtual_time()` の window 粒度が粗くなったときの
  device側モデルへの影響を確認していない。採用前の全target回帰に
  `picocalc-clock-i2c-env-e5`を含めるが、gate通過は事後確認であり、
  述語の十分性を先に示したものではない。
- §7 の測定計画は wall 時間のみを主指標とする。CPU 高速化計画が CPU-time を主指標に
  切り替えた経緯と契約が異なるため、両者の結果を同じ表に並べない。
- §1 の 8.93 秒 / 4.47 秒は先行提案が記録した実測値であり、本書で再測定していない。
