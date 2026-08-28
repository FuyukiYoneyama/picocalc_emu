# Validated Realtime Preview 提案

Status: Proposal (review revised)  
Date: 2026-08-28  
Owner: FuyukiYoneyama  
Tracking issue / PR: 未作成。P0 実装開始前に作成し、本書から相互リンクする。

関連文書:

- [Firmware backend](FIRMWARE_BACKEND.md)
- [Requirements](../REQUIREMENTS.md)
- [Headless machine API](HEADLESS_MACHINE_API.md)
- [Concurrent runs](CONCURRENT_RUNS.md)
- [Versioning](VERSIONING.md)
- [Firmware target registry](../reference-projects/firmware-targets.json)

## 0. 用語

本書では名称を次に固定する。

- **Firmware backend**: `picoem-picocalc` を用いる権威ある firmware 検証経路。`ExecutionModel::Serial`、schema 8 verdict、target registry、artifact / backend identity の fail-closed 判定を含む。
- **Validated Realtime Preview**: Firmware backend を通過済みの同一 source / build identity だけを、wall-clock 1× を目標に対話実行する UX 確認層。以下 **preview** と略す。
- **validation receipt**: Firmware backend の PASS と対象 source / artifact を参照する preview 用索引。receipt 自体は信頼の起点ではない。

「確実版」「簡略版」は会話上の説明語としてのみ使い、仕様上の正式名称にはしない。

## 1. 目的

`picocalc_emu` に、**Firmware backend で合格した source / build identity だけを対象に、実時間 1× を目標として人間または AI が画面・入力・音・待ち時間を確認する Validated Realtime Preview** を追加する。

preview の目的はハードウェア互換性の判定ではない。すでに authoritative validation を通過した対象について、次を低コストで確認することである。

- 起動から最初の画面までの待ち時間
- メニュー遷移のテンポ
- キー押下、長押し、release の反応
- アニメーションやゲーム進行の体感速度
- 画面更新の見え方
- 音の開始・停止・テンポの概略
- reset / reload を含む反復 UX

P0 では新しい emulator core を作らない。既存 `picoem-picocalc` の RP2040 / PicoCalc device path、MachineSession、wall-clock pacer を最大限再利用し、対話 frontend を薄く追加する。

## 2. 最重要原則

### 2.1 順序を逆転させない

通常フローは必ず次とする。

```text
source
  |
  v
Firmware backend authoritative validation
  |
  | PASS
  v
validated source/build identity
  |
  v
Validated Realtime Preview
  |
  v
UX inspection
  |
  v
必要なら hardware final check
```

次は正しい。

```text
Firmware backend PASS -> preview
```

次の推論は禁止する。

```text
preview looks good -> hardware compatible
```

同様に、preview の異常・無異常についても対称に限定する。

- **preview で見えた不具合が実機にも存在する保証はない。** host scheduling、realtime underrun、GUI repaint、host audio sink、対話入力タイミングなど preview 固有の artifact である可能性がある。
- **preview で不具合が見えなかったことは、実機に不具合がない保証にならない。** hardware 固有の差、物理 LCD、物理 keyboard、speaker / enclosure、未モデル化条件は残る。

preview は「検証済み対象の UX 観測器」であり、正負どちらの方向にも hardware verdict を生成しない。

### 2.2 preview は検証器ではない

[`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md) が定義する Firmware backend は、PIO、DMA、GPIO、interrupt、multicore など binary / hardware 固有挙動を検証する正確性側の backend であり、`ExecutionModel::Serial` を正確性基準とする。

preview はこの責務を持たない。scenario assertion、target promotion、hardware correlation、authoritative verdict は Firmware backend 側に残す。

### 2.3 source / build input が変われば再検証する

一度 PASS した後でも、snapshot identity が変化した時点で preview 資格を失う。

```text
source A -> firmware PASS -> preview OK
source A'                    -> preview REFUSED
source A' -> firmware PASS -> preview OK
```

初期実装ではコメントや空白だけの差を特別扱いしない。build に投入された identity と一致しなければ安全側に倒して拒否する。

## 3. 現在の構成との整合

既存要求は Host backend と Firmware backend を分離している。Firmware backend は raw Pico SDK BIN を direct boot し、同一 build から作られる UF2 と payload identity を結び、schema 8 report、backend/source identity、artifact hash、device arguments、期待値を fail-closed で判定する。

また `picoem-picocalc` には wall-clock real-time pacing があり、MachineSession は scenario runner と headless machine API で共有されている。そのため preview は第三の core を作るのではなく、既存 session core に wall-clock / GUI / interactive input / host audio monitor を接続する層とする。

| 層 | 主目的 | hardware correctness の権限 | 時間特性 |
|---|---|---|---|
| Host backend | アプリロジック、UI、file 処理の高速反復 | なし | 最速 |
| Firmware backend | RP2040 / PicoCalc 固有挙動の合否判定 | **あり** | 任意 |
| Validated Realtime Preview | 検証済み対象の UX 観測 | **なし** | wall-clock 1× target |

## 4. UX workload から見える必要条件

NES 系 workload のような PicoCalc アプリでは、画面・入力・音・時間が PIO、DMA、I2C、PWM、multicore と密結合している。60 fps 系の描画では約 16.7 ms ごとの進行、継続 audio DMA、keyboard press / release が同時に UX へ影響する。

したがって preview を「最終 framebuffer を表示するだけ」の実装にはしない。少なくとも次を一つの連続 session として扱う。

- virtual time と wall clock の関係
- LCD framebuffer の時系列更新
- key down / held / up
- reset / reboot
- audio producer / DMA の時間進行
- UX に現れる SD wait

ただし wire-level の正しさを preview で再判定しない。その責務は先行する Firmware backend にある。

## 5. trust root と validation receipt

### 5.1 receipt は信頼の起点ではなく索引

`status: validated` と書かれた JSON を手作業で置くだけでは preview を起動できない。

validation receipt は `tools/picocalc.py` が **成功した schema 8 report から派生生成する索引**とする。Firmware backend の report schema 8 自体は変更しない。

概念例:

```json
{
  "schema": 1,
  "source_identity": "<identity>",
  "target": "<target-id/revision>",
  "firmware_bin_sha256": "<sha256>",
  "backend_commit": "<full sha>",
  "report": "<schema 8 report path>",
  "report_sha256": "<sha256>"
}
```

receipt 内の `status` や `verdict` のコピー値は trust root として使わない。

### 5.2 preview 起動時に必ず再検証するもの

preview launcher は receipt の値だけを信用せず、起動ごとに少なくとも次を再検証する。

1. 参照先 report が存在し、期待する schema 8 であること
2. report の `verdict.status` が `pass` であること
3. report / target registry が指す target id と revision が一致すること
4. target registry が固定する accepted backend commit と、実際に preview で使用する `picoem-picocalc` の full commit SHA が一致すること
5. ディスク上の firmware BIN を再 SHA-256 し、report / target に固定された artifact hash と一致すること
6. source/build snapshot identity が validation 時と一致すること
7. source tree が clean を要求する target では dirty でないこと

不一致は warning ではなく起動拒否とする。

### 5.3 snapshot identity が最低限カバーする対象

snapshot identity は少なくとも、実際の build 結果を変え得る次をカバーする。

- アプリ source 一式
- `CMakeLists.txt`、Makefile、toolchain file、生成設定など build-control file
- Canonical BSP または参照 BSP の version / tree identity
- submodule / nested repository / external source の exact commit
- Pico SDK version と、固定可能な場合は exact commit
- compiler、CMake、Ninja / Make、picotool など target が要求する toolchain identity
- CMake option、board / LCD variant、再現 build define など build parameter
- firmware BIN SHA-256
- target id / revision
- `picoem-picocalc` backend full commit SHA

Git commit だけで build input 全体を表せない generated project では、target registry が採用している tree hash、BSP tree hash、reproducible build metadata 等を組み合わせる。方式の細部は実装時に schema 化してよいが、上の対象を省略してよいという意味ではない。

### 5.4 backend 更新時の失効

「より新しい backend」だから自動的に receipt を有効とはみなさない。

preview は **validation に使った accepted backend commit と同一の backend build** で起動する。backend checkout / binary identity が変わった場合、その receipt はその backend に対して無効であり、新 backend で Firmware backend validation をやり直して新しい receipt を生成する。

これは [`VERSIONING.md`](VERSIONING.md) の exact commit / target pin 方針と同じである。

## 6. preview 実行契約

### 6.1 起動条件

preview は次をすべて満たすときだけ起動する。

- authoritative schema 8 report が PASS
- report、target registry、artifact、source/build identity が整合
- backend full commit が validation 時の accepted backend と一致
- source/build input に validation 後の変更がない

拒否例:

```text
Validated Realtime Preview refused
reason: firmware SHA-256 differs from validated artifact
next: run firmware validation again
```

### 6.2 UI で常時見せる状態

最低限、次を常時表示する。

```text
Validated Realtime Preview
Validation: source/build identity verified
Target speed: 1.000x
Measured speed: 0.997x
Timing: UNCALIBRATED / REALTIME OK / REALTIME NOT MET
Audio: monitor on / muted / degraded / timing-only
Hardware verdict: NOT PROVIDED BY THIS MODE
```

P0 baseline 中は realtime 許容幅が未固定なので `Timing: UNCALIBRATED` を許す。ただし明確に wall clock へ追従できず backlog が増加している場合は `REALTIME NOT MET` を優先表示する。

「Validated」は preview 自身が PASS を出したという意味ではなく、入口 identity が Firmware backend を通過済みという意味だけである。

### 6.3 1× の定義

`1×` は全電気的タイミングの再現ではない。virtual time の進行を wall clock に合わせ、少なくとも次の UX 時間を人間が比較できる状態を指す。

- firmware delay
- frame pacing
- menu wait
- animation interval
- key repeat / hold
- audio stream timing

速度変更は P0 に入れない。0.5×、2×、turbo は UX 判定を曖昧にするためである。

実測は少なくとも session 全体の `virtual_time / wall_time`、rolling ratio、pacer overrun / backlog、host presentation drop count、audio underrun / overrun を記録する。

### 6.4 1× 未達時の劣化ポリシー

preview は **1× に見せかけるために emulated semantics を捨てない**。

P0 の劣化順序を次に固定する。

1. authoritative validation 用の scenario assertion、evidence、trace、不要な診断出力を preview session では実行しない。
2. host audio playback が負荷要因なら、host 側の再生 buffer を drop / mute してよい。ただし emulated PWM / DMA / audio producer の virtual-time 進行は省略しない。UI に `Audio: degraded` または `muted` と underrun / drop count を表示する。
3. GUI repaint が負荷要因なら host window の repaint を coalesce / drop してよい。ただし emulated LCD command、framebuffer 更新、virtual frame timing は省略しない。UI に presentation drop count を表示する。
4. それでも emulator core / device path 自体が 1× に追従できない場合、P0 では CPU cycle、IRQ、PIO、DMA、device event、emulated frame、virtual audio event を飛ばして 1× を偽装しない。

4 に達した session はそのまま遅く実行を継続してもよいが、UI に **`REALTIME NOT MET — TIMING / AUDIO UX JUDGEMENT INVALID`** を常時表示する。その session はレイアウト、機能、入力経路など非時間的な観測には使えるが、実機のテンポ、入力 latency、audio quality の根拠には使わない。

密結合 workload では、host presentation を落としても core が追従できない可能性を正式に認める。その場合は「P0 の実速度が限界」であり、P2 の最適化が成立するまでは realtime UX preview 未達とする。

### 6.5 realtime 許容幅

数値 threshold は測定前に決めない。

P0 は baseline を収集し、後続の設計記録で rolling / sustained ratio、許容 overrun、audio underrun 等の gate を固定する。threshold が固定されるまでは `REALTIME OK` を authoritative な受入表示には使わない。

## 7. 対話 UI、AI 操作、同時実行

### 7.1 最小 GUI

P0 の最小 UI:

- PicoCalc LCD 表示
- PC keyboard -> PicoCalc keyboard event
- key down / held / up
- reset
- reload validated artifact
- screenshot
- host audio monitor 状態
- realtime status / measured ratio / drop counters
- quit

概念 CLI:

```sh
python3 tools/picocalc.py preview \
  --receipt artifacts/validation-receipt.json \
  --backend-dir ../picoem-picocalc
```

ショートカット例:

```text
F5       reset
Ctrl+R   reload validated artifact
F12      screenshot
M        mute/unmute host audio monitor
Esc      quit
```

mute は host monitor sink だけに作用し、emulated audio device state や PWM / DMA の時間進行を変えない。

### 7.2 headless machine API との関係

既存 [`HEADLESS_MACHINE_API.md`](HEADLESS_MACHINE_API.md) の `--machine-api` は仮想 cycle 境界で決定的に操作する API であり、wall-clock pacing を契約に含めない。したがって **machine API をそのまま realtime preview と呼び替えない**。

preview は同じ `MachineSession` の input / observe / snapshot primitive を再利用する別 frontend とする。AI-assisted UX inspection では、preview frontend が同じ semantic operation を使って programmatic input と framebuffer snapshot を行えるようにするが、既存 machine API schema 1 の決定性契約や authoritative verdict を変更しない。

### 7.3 同時実行

一つの preview process は一つの validated session を所有する。複数 process の同時起動自体は許可できるが、[`CONCURRENT_RUNS.md`](CONCURRENT_RUNS.md) と同様に run id / output directory / screenshot / audio output artifact を共有しない。

**realtime performance baseline や 1× qualification は並列実行中に測定しない。** host contention を実機 UX と誤認しないためである。

## 8. 音声の扱い

preview では次を分離する。

1. **Emulated audio timing**: PWM / DMA / audio producer の virtual-time 進行。UX timing に効くため保持する。
2. **Host audio monitor**: PC speaker へ出す best-effort 再生。人間が開始・停止・テンポを確認する補助機能であり、hardware speaker の再現ではない。

P0 では backend が対象 audio stream を提供できる workload では host monitor を利用可能にする。未対応 stream では `Audio: timing-only` と明示し、無音を実機の無音と解釈させない。

host monitor では underrun / overrun / dropped buffer を観測し、発生時は `Audio: degraded` を表示する。preview 由来の underrun、host DAC、OS mixer、speaker の音を firmware bug や実機音質の証拠にしてはならない。

host volume / mute を提供する場合、それは monitor gain のみを変更し、emulated PWM duty や firmware-visible volume state を変更しない。

## 9. screenshot の意味

F12 等で得る preview screenshot は **UX 用の便宜的 capture** であり、conformance artifact ではない。

- P0 が Firmware backend と同一 BIN / device path を使っていても、preview screenshot の pixel hash が golden image と一致することを仕様上保証しない。
- repaint coalescing、capture timing、window scaling、host presentation を golden comparison に混ぜない。
- raw framebuffer snapshot が偶然または実装上同一でも、authoritative comparison は Firmware backend の scenario / report 側で行う。
- P2 で source-level / host-assisted optimization を導入した場合、preview screenshot と golden image の一致をさらに期待してはならない。

## 10. preview で保持するもの / 外してよいもの

### 保持するもの

- wall-clock pacing と実測 ratio
- firmware / app delay
- LCD framebuffer の時系列状態
- keyboard down / held / up
- reset / reboot
- emulated audio timing
- UX に現れる SD wait の virtual-time 進行
- realtime miss / presentation drop / audio underrun の可視化

### preview から外してよいもの

- deterministic scenario assertion
- UART marker による合否判定
- pixel / region hash assertion
- trace の完全採取
- evidence package 生成
- CI 用 fail-closed verdict
- backend promotion 判定
- hardware correlation 記録
- exhaustive diagnostics

ただし「外す」ことで画面、入力、virtual time、audio producer の意味が変わる場合は採用しない。

## 11. 実装方針

### Phase P0: thin realtime frontend + performance baseline

既存 `picoem-picocalc` の RP2040 / PicoCalc device path、MachineSession、wall-clock pacer を使い、GUI、keyboard、host audio monitor、status overlay、計測を追加する。

P0 では新 core を作らず、semantic shortcut を導入しない。

P0 baseline は少なくとも次の二種類を含める。

- 現在の登録済み interactive reference workload（例: active な PicoTetris target）
- LCD 連続更新、keyboard、audio、multicore / DMA を同時に使う **NES-class workload**

NES-class workload が再現可能な validated target / fixture として準備できていない場合、軽い workload だけで realtime 能力を合格扱いにせず、P0 realtime qualification は未完了とする。

各代表 workload は **10 分以上の連続 interactive session** を crash なしで実行し、session ratio、rolling ratio、pacer backlog / overrun、presentation drop、audio underrun / overrun を保存する。10 分は安定性・熱的 host fluctuation・入力反復を観測する最低 duration であり、realtime 許容幅そのものではない。

### Phase P1: validation receipt gate

`tools/picocalc.py` に、成功した schema 8 report から receipt を派生生成し、preview 起動時に report / target registry / disk artifact / backend / source identity を再検証する gate を追加する。

receipt の手書き値だけでは起動できないことを unit / integration test で固定する。

### Phase P2: 必要な場合だけ最適化

P0 baseline で core / device path が 1× を維持できない場合のみ profiler で bottleneck を特定する。

```text
既存 core で測定
  -> 1× を満たす: 新しい簡略 core は作らない
  -> 未達: bottleneck を測定
  -> host presentation 負荷を除去
  -> なお未達: UX semantics を変えない optimization のみ検討
```

CPU / PIO / DMA / IRQ / device event を飛ばすなど、UX timing 自体を改変する shortcut は「preview の 1× 達成」のためには採用しない。もし将来その種の source-level / host-assisted mode を導入するなら、別 capability として明示し、同一の realtime fidelity を自動的に主張しない。

## 12. 受け入れ条件

P0 / P1 の最初の完成条件を次とする。

1. Firmware backend PASS がない source / artifact では preview を起動できない。
2. receipt を手編集しても、参照 schema 8 report、target registry、disk artifact、backend identity の再検証を突破できない。
3. PASS 後に source / build-control file / artifact / backend が変更されると preview gate が拒否する。
4. representative workload で LCD を連続表示でき、key down / held / up、reset、reload を対話操作できる。
5. supported audio workload では emulated audio timing を保持し、host monitor の mute / underrun / degradation 状態を UI で区別できる。
6. active PicoTetris 系 target と NES-class workload を各 10 分以上連続実行し、crash せず、wall-clock ratio、rolling ratio、pacer backlog / overrun、presentation drop、audio underrun / overrun を記録できる。NES-class workload が未整備ならこの項目は未完了とする。
7. realtime 許容幅が未固定の間は `Timing: UNCALIBRATED` を表示でき、core が追従できない session では `REALTIME NOT MET` を隠さない。
8. 1× 未達を隠すために CPU cycle、emulated frame、IRQ、PIO、DMA、device event、virtual audio event を skip しない。
9. scenario / trace / evidence を要求せずに UX session を開始できる。
10. preview の観測から hardware compatibility の PASS / FAIL を生成しない。
11. preview screenshot を conformance / golden artifact として扱わない。
12. Firmware backend の既存 schema 8 verdict、target registry、promotion policy、machine API schema 1 の決定性契約を変更しない。
13. realtime PASS の数値 threshold は P0 baseline の記録をレビューした後に別の設計記録で固定する。それまでは「計測できたこと」と「1× 合格」を分離する。

## 13. 非目標

- preview 単体による実機互換性保証
- preview 固有の異常を実機 bug と断定すること
- preview で異常が無かったことを実機保証にすること
- Firmware backend の置換
- `ExecutionModel::Serial` の正確性基準変更
- machine API v1 を wall-clock API へ変更すること
- arbitrary UF2 direct boot
- USB BOOTSEL / MSC 再現
- speaker / enclosure / physical volume を含む実音響再現
- 物理 key feel、LCD の物理色・残像・視野角の再現
- preview を CI authoritative verdict にすること

## 14. 開発ループの最終形

```text
AI / developer edits source
        |
        v
host test
        |
        v
build
        |
        v
Firmware backend authoritative validation
        |
        | PASS
        v
validation receipt generated by tools
        |
        | launch-time revalidation
        v
Validated Realtime Preview
        |
        | 1× qualified -> timing / UX inspection
        | 1× not met   -> timing judgement invalid, functional observation only
        v
human / AI-assisted UX inspection
        |
        v
必要なら hardware final check
```

この提案の核心は、**preview が Firmware backend の後にしか来ないこと**と、**1× を達成できないときに嘘をつかないこと**である。

Firmware backend は「この source / build / artifact を登録された PicoCalc hardware model 上で受け入れてよいか」を判定する。Validated Realtime Preview は、その検証済み対象を wall-clock で触ったときの UX を観測する。ただし realtime 条件を満たせない session は明示的に timing-unqualified とし、preview 自身は hardware correctness の権限を持たない。
