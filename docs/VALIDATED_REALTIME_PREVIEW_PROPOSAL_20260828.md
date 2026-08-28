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
- **Validated Realtime Preview**: Firmware backend を通過済みの build artifact だけを、wall-clock 1× を目標に対話実行する UX 確認層。以下 **preview** と略す。
- **validation receipt**: Firmware backend の PASS と、そのとき使用した firmware artifact / backend executable / report を参照する preview 用索引。receipt 自体は信頼の起点ではない。
- **validation provenance**: source、BSP、SDK、toolchain、build option 等、「その validated artifact がどう作られたか」を説明・再現する情報。P0/P1 の preview 起動時 gate とは区別する。

「確実版」「簡略版」は会話上の説明語としてのみ使い、仕様上の正式名称にはしない。

## 1. 目的

`picocalc_emu` に、**Firmware backend で合格した同一 build artifact だけを対象に、実時間 1× を目標として人間または AI が画面・入力・音・待ち時間を確認する Validated Realtime Preview** を追加する。

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
build
  |
  v
Firmware backend authoritative validation
  |
  | PASS
  v
validated firmware artifact + validated backend executable
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

preview は「検証済み artifact の UX 観測器」であり、正負どちらの方向にも hardware verdict を生成しない。

### 2.2 preview は検証器ではない

[`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md) が定義する Firmware backend は、PIO、DMA、GPIO、interrupt、multicore など binary / hardware 固有挙動を検証する正確性側の backend であり、`ExecutionModel::Serial` を正確性基準とする。

preview はこの責務を持たない。scenario assertion、target promotion、hardware correlation、authoritative verdict は Firmware backend 側に残す。

### 2.3 P0/P1 は「同一 BIN」を gate にする

P0/P1 の preview は Firmware backend が PASS した **同一 firmware BIN** を実行する。

したがって、validation 後に source tree、compiler、CMake、Ninja、Pico SDK 等の現在状態が変化しても、ディスク上の validated BIN 自体が byte-identical なら、その事実だけを理由に既存 artifact の preview を拒否しない。

一方、編集後に再ビルドして BIN が 1 byte でも変われば SHA-256 が変化するため preview gate は拒否する。新しい source の結果を見るには、その新 BIN を Firmware backend に通してから preview へ進む。

```text
source A -> BIN A -> firmware PASS -> preview BIN A OK
source A' (未build)                     -> preview BIN A OK
source A' -> BIN B                      -> preview BIN B REFUSED
source A' -> BIN B -> firmware PASS     -> preview BIN B OK
```

これは source provenance を不要にする意味ではない。provenance は validation の再現・監査のために保存するが、**同一 BIN を再実行する P0/P1 の runtime admission gate と混同しない**。

将来、P2 以降で source-level / host-assisted な別実行方式を追加する場合は、その mode では source/build snapshot identity を別途 gate に含める。

## 3. 現在の構成との整合

既存要求は Host backend と Firmware backend を分離している。Firmware backend は raw Pico SDK BIN を direct boot し、同一 build から作られる UF2 と payload identity を結び、schema 8 report、backend/source identity、artifact hash、device arguments、期待値を fail-closed で判定する。

また `picoem-picocalc` には wall-clock real-time pacing があり、MachineSession は scenario runner と headless machine API で共有されている。そのため preview は第三の core を作るのではなく、既存 session core に wall-clock / GUI / interactive input / host audio monitor を接続する層とする。

| 層 | 主目的 | hardware correctness の権限 | 時間特性 |
|---|---|---|---|
| Host backend | アプリロジック、UI、file 処理の高速反復 | なし | 最速 |
| Firmware backend | RP2040 / PicoCalc 固有挙動の合否判定 | **あり** | 任意 |
| Validated Realtime Preview | 検証済み artifact の UX 観測 | **なし** | wall-clock 1× target |

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

validation receipt は `tools/picocalc.py` が成功した Firmware backend run に対して生成する索引とする。Firmware backend の report schema 8 自体は変更しない。

概念例:

```json
{
  "schema": 1,
  "target": "<target-id/revision>",
  "firmware_bin_sha256": "<sha256>",
  "backend_commit": "<full sha>",
  "backend_executable_sha256": "<sha256>",
  "report": "<schema 8 report path>",
  "report_sha256": "<sha256>",
  "provenance": "<validation provenance reference>"
}
```

receipt 内の `status` や `verdict` のコピー値は trust root として使わない。

`backend_executable_sha256` は checkout の commit から推測せず、**Firmware validation で実際に起動した `picocalc-run` executable の bytes を SHA-256 して記録する**。古い build artifact、dirty tree から作った別 binary、別 optimization build を commit SHA だけで同一視しない。

### 5.2 validation provenance と runtime gate を分離する

validation 時には、既存 target registry / validation record の方針に従い、少なくとも次の provenance を保存する。

- アプリ source / exact commit / tree identity
- `CMakeLists.txt`、Makefile、toolchain file 等の build-control information
- Canonical BSP または参照 BSP の version / tree identity
- submodule / nested repository / external source の exact commit
- Pico SDK version / exact commit（固定対象の場合）
- compiler、CMake、Ninja / Make、picotool 等の toolchain identity
- CMake option、board / LCD variant、再現 build define 等の build parameter
- firmware BIN SHA-256
- target id / revision
- backend source commit / report schema / validation record

これらは「何をどう作って検証したか」の再現・監査情報である。

**P0/P1 preview launcher は、現在の host に入っている compiler / CMake / Ninja / picotool / SDK を起動時に再検査しない。** 同一 validated BIN を再ビルドせず実行するため、それらの現在値は runtime semantics を決めない。現在の toolchain が変わっただけで validated BIN を拒否してはならない。

### 5.3 P0/P1 起動時に必ず再検証するもの

preview launcher は receipt の値だけを信用せず、起動ごとに少なくとも次を再検証する。

1. 参照先 report が存在し、receipt が固定する report SHA-256 と一致すること
2. report が期待する schema 8 であること
3. report の `verdict.status` が `pass` であること
4. report / target registry が指す target id と revision が一致すること
5. ディスク上の firmware BIN を再 SHA-256 し、validation で固定された artifact hash と一致すること
6. target registry が固定する accepted backend commit と、validation 時の backend commit が一致すること
7. **実際に preview が起動しようとしている backend executable を再 SHA-256 し、validation 時に記録した `backend_executable_sha256` と一致すること**
8. Firmware validation と preview で、次の **preview semantics に必要な device configuration 6 項目だけ**が一致すること
   - `board`
   - `lcd_variant`
   - `psram`
   - `keyboard`
   - `sd.attached`
   - `sd.format`

項目 8 は target registry の `runner` block 全体一致を意味しない。次は preview の実行方式上、validation と一致しなくてよいため runtime gate に含めない。

- `cycles`: validation は bounded run、preview は長寿命の対話 session である
- `keys`: validation の固定入力列を preview の対話入力へ持ち込まない
- `scenario`: preview は authoritative scenario を実行しない
- `expected_stop_reason`: preview は `cycle_limit` / `scenario_done` 等の validation stop contract を持たない

上記6項目以外を device gate に追加する場合は、「preview semantics が変わるため一致が必要」という理由と field 名を本書または後続の versioned contract に明記してから追加する。「等」や `runner` 全体比較で gate 範囲を暗黙に拡張しない。

不一致は warning ではなく起動拒否とする。

P0/P1 の runtime gate では、現在の source working tree や現在インストールされている compiler / CMake / Ninja / SDK の再ハッシュ・version comparison を要求しない。新しい source を build すれば firmware BIN SHA-256 が変わり、項目 5 で確実に拒否される。

### 5.4 backend 更新時の失効

「より新しい backend」だから自動的に receipt を有効とはみなさない。

preview は validation に使った accepted backend commit に加え、**validation で実際に使用した backend executable と byte-identical な executable** で起動する。

次のいずれかが変われば、その validation receipt は新 backend に対して無効である。

- accepted backend commit
- 実際に起動する backend executable SHA-256
- preview semantics に必要な backend build configuration

backend source checkout の commit が同じでも executable hash が違えば拒否する。逆に working tree が dirty でも、preview が実際に起動する executable が validation 時と byte-identical なら、dirty tree だけを理由に P0/P1 の既存 artifact preview を拒否しない。

新しい backend executable を使う場合は、その executable で Firmware backend validation をやり直して新しい receipt を生成する。

これは [`VERSIONING.md`](VERSIONING.md) の exact target / backend pin 方針を runtime executable まで具体化するものである。

### 5.5 reload は起動時 gate を再実行する

`Ctrl+R` / reload は admission gate の例外ではない。

reload は、現在の process 内で単に firmware file を読み直してはならない。**起動時と同じ一つの revalidation 関数**を先に実行し、§5.3 の report / target / firmware BIN / backend executable / device configuration をすべて再確認する。

```text
Ctrl+R
  |
  v
same admission revalidation as launch
  | PASS
  v
stop old session -> create fresh preview session

  | mismatch
  v
RELOAD REFUSED -> stop current session
```

不一致の場合は新 artifact を一瞬でも実行せず、reload を拒否し、現在の session も停止する。UI は validated 表示を残さず、例えば次を表示する。

```text
VALIDATION LOST — RELOAD REFUSED
reason: firmware SHA-256 differs from validated artifact
next: run firmware validation again
```

これにより「build -> Ctrl+R」で gate を黙って迂回できない。

reset が in-memory の同一 firmware image を単に初期状態へ戻すだけなら再ハッシュは不要である。ただし reset / reload 実装がディスクから firmware または backend を読み直す場合は、その直前に同じ admission revalidation を必須とする。

## 6. preview 実行契約

### 6.1 UI で常時見せる状態

最低限、次を常時表示する。

```text
Validated Realtime Preview
Validation: artifact + backend executable verified
Target speed: 1.000x
Measured speed: 0.997x
Timing: UNCALIBRATED / REALTIME OK / REALTIME NOT MET
Model coverage: OK / UNSUPPORTED MMIO REACHED
Audio: monitor on / muted / degraded / timing-only
Hardware verdict: NOT PROVIDED BY THIS MODE
```

P0 baseline 中は realtime 許容幅が未固定なので `Timing: UNCALIBRATED` を許す。ただし明確に wall clock へ追従できず backlog が増加している場合は `REALTIME NOT MET` を優先表示する。

「Validated」は preview 自身が PASS を出したという意味ではなく、入口 artifact と backend executable が Firmware backend validation と同一であるという意味だけである。

### 6.2 1× の定義

`1×` は全電気的タイミングの再現ではない。virtual time の進行を wall clock に合わせ、少なくとも次の UX 時間を人間が比較できる状態を指す。

- firmware delay
- frame pacing
- menu wait
- animation interval
- key repeat / hold
- audio stream timing

速度変更は P0 に入れない。0.5×、2×、turbo は UX 判定を曖昧にするためである。

実測は少なくとも session 全体の `virtual_time / wall_time`、rolling ratio、pacer overrun / backlog、host presentation drop count、audio underrun / overrun を記録する。

### 6.3 1× 未達時の劣化ポリシー

preview は **1× に見せかけるために emulated semantics を捨てない**。

P0 の劣化順序を次に固定する。

1. authoritative validation 用の scenario assertion、evidence、trace、不要な診断出力を preview session では実行しない。
2. host audio playback が負荷要因なら、host 側の再生 buffer を drop / mute してよい。ただし emulated PWM / DMA / audio producer の virtual-time 進行は省略しない。UI に `Audio: degraded` または `muted` と underrun / drop count を表示する。
3. GUI repaint が負荷要因なら host window の repaint を coalesce / drop してよい。ただし emulated LCD command、framebuffer 更新、virtual frame timing は省略しない。UI に presentation drop count を表示する。
4. それでも emulator core / device path 自体が 1× に追従できない場合、P0 では CPU cycle、IRQ、PIO、DMA、device event、emulated frame、virtual audio event を飛ばして 1× を偽装しない。

4 に達した session はそのまま遅く実行を継続してもよいが、UI に **`REALTIME NOT MET — TIMING / AUDIO UX JUDGEMENT INVALID`** を常時表示する。その session は非時間的な診断観測には使えるが、実機のテンポ、入力 latency、audio quality の根拠には使わない。

密結合 workload では、host presentation を落としても core が追従できない可能性を正式に認める。その場合は「P0 の実速度が限界」であり、P2 の最適化が成立するまでは realtime UX preview 未達とする。

### 6.4 unsupported MMIO 到達時の UX 無効化

対話 preview は validation scenario が通っていない操作経路へ入れる。そのため、Firmware validation では到達しなかった unsupported / truncated MMIO に session 中に初めて到達する可能性がある。

preview はこれを hardware FAIL と判定しない一方、**その時点以降の UX を実機相当として見せ続けてはならない**。

既存 [`HEADLESS_MACHINE_API.md`](HEADLESS_MACHINE_API.md) の MachineSession が持つ `unsupported_mmio` observation / counter を利用し、新しい peripheral emulation を追加せずに状態を監視する。

unsupported MMIO entry の発生、または unsupported MMIO observation の truncation を検出した時点で、preview frontend 自身に sticky な UX-invalid state を立て、例えば次を常時表示する。

```text
UNSUPPORTED MMIO REACHED — UX JUDGEMENT INVALID FROM THIS POINT
Model coverage: INVALID
Hardware verdict: NOT PROVIDED BY THIS MODE
```

preview process は診断目的で実行を継続してもよいが、その時点以降の画面、音、入力 latency、timing、機能挙動を実機の根拠として扱わない。banner を隠して通常の `Validated` 状態へ戻してはならない。

**F5 reset は sticky UX-invalid state をクリアしない。** underlying MachineSession の reset によって `unsupported_mmio` counter / entries がゼロへ戻っても、preview frontend が保持する sticky state と banner は残す。F5 は同一 admitted session 内の firmware reset であり、新しい trust admission ではない。

sticky UX-invalid state をクリアできるのは、admission gate を通って新しい clean session を開始する経路だけとする。具体的には process の新規起動、または §5.5 の revalidation に PASS した `Ctrl+R` である。reload revalidation が失敗した場合は session 自体を停止するため banner を通常状態へ戻さない。

これは preview の verdict ではない。authoritative FAIL / PASS は引き続き Firmware backend の責務である。

### 6.5 realtime 許容幅

数値 threshold は測定前に決めない。

P0 は baseline を収集し、後続の設計記録で rolling / sustained ratio、許容 overrun、audio underrun 等の gate を固定する。threshold が固定されるまでは `REALTIME OK` を authoritative な受入表示には使わない。

## 7. 対話 UI、AI 操作、同時実行

### 7.1 最小 GUI

P0 の最小 UI:

- PicoCalc LCD 表示
- PC keyboard -> PicoCalc keyboard event
- key down / held / up
- reset（sticky UX-invalid state は維持）
- reload validated artifact（必ず §5.5 の再検証を通す）
- screenshot
- host audio monitor 状態
- realtime status / measured ratio / drop counters
- model coverage / unsupported MMIO status
- quit

概念 CLI:

```sh
python3 tools/picocalc.py preview \
  --receipt artifacts/validation-receipt.json \
  --backend-dir ../picoem-picocalc
```

ショートカット例:

```text
F5       reset in-memory validated session; keep sticky UX-invalid state
Ctrl+R   revalidate, then reload validated artifact
F12      screenshot
M        mute/unmute host audio monitor
Esc      quit
```

mute は host monitor sink だけに作用し、emulated audio device state や PWM / DMA の時間進行を変えない。

host OS / GUI toolkit の keyboard auto-repeat は firmware 側の repeat / hold と混同しない。物理 key の press について preview frontend は原則として最初の key-down を一度だけ投入し、OS が同じ key-down を自動反復しても追加の press event として投入しない。key-up は実際の release 時に一度投入し、hold / repeat の時間的挙動は PicoCalc keyboard model / firmware-visible semantics に委ねる。GUI framework が repeat flag を提供する場合はそれを抑止判定に使う。

### 7.2 headless machine API との関係

既存 [`HEADLESS_MACHINE_API.md`](HEADLESS_MACHINE_API.md) の `--machine-api` は仮想 cycle 境界で決定的に操作する API であり、wall-clock pacing を契約に含めない。したがって **machine API をそのまま realtime preview と呼び替えない**。

preview は同じ `MachineSession` の input / observe / snapshot primitive を再利用する別 frontend とする。AI-assisted UX inspection では、preview frontend が同じ semantic operation を使って programmatic input と framebuffer snapshot を行えるようにするが、既存 machine API schema 1 の決定性契約や authoritative verdict を変更しない。

`unsupported_mmio` も同じ MachineSession observation を読む。preview 専用の第二の MMIO counter や別判定ロジックを作らず、sticky UX-invalid state だけを frontend が保持する。

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

unsupported MMIO 到達後は、host audio monitor が正常に鳴っていても §6.4 に従い UX/audio judgement は無効である。

## 9. screenshot の意味

F12 等で得る preview screenshot は **UX 用の便宜的 capture** であり、conformance artifact ではない。

- P0 が Firmware backend と同一 BIN / device path を使っていても、preview screenshot の pixel hash が golden image と一致することを仕様上保証しない。
- repaint coalescing、capture timing、window scaling、host presentation を golden comparison に混ぜない。
- raw framebuffer snapshot が偶然または実装上同一でも、authoritative comparison は Firmware backend の scenario / report 側で行う。
- P2 で source-level / host-assisted optimization を導入した場合、preview screenshot と golden image の一致をさらに期待してはならない。
- unsupported MMIO 到達後の screenshot は `UX-invalid` 状態の診断 capture であり、実機期待画面には使わない。

## 10. preview で保持するもの / 外してよいもの

### 保持するもの

- launch / reload admission revalidation
- firmware BIN SHA-256 identity
- backend executable SHA-256 identity
- fixed device configuration 6 項目 (`board`, `lcd_variant`, `psram`, `keyboard`, `sd.attached`, `sd.format`)
- wall-clock pacing と実測 ratio
- firmware / app delay
- LCD framebuffer の時系列状態
- keyboard down / held / up（host OS auto-repeat は重複 press として投入しない）
- reset / reboot
- reset を跨いで維持する sticky UX-invalid state
- emulated audio timing
- UX に現れる SD wait の virtual-time 進行
- realtime miss / presentation drop / audio underrun の可視化
- **unsupported / truncated MMIO の既存 observation と UX-invalid banner**

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

unsupported MMIO の **authoritative verdict** は preview から外すが、unsupported MMIO に到達した事実の可視化まで外してはならない。

また「外す」ことで画面、入力、virtual time、audio producer の意味が変わる場合は採用しない。

## 11. 実装方針

### Phase P0: thin realtime frontend + same-artifact safety gate + baseline

既存 `picoem-picocalc` の RP2040 / PicoCalc device path、MachineSession、wall-clock pacer を使い、GUI、keyboard、host audio monitor、status overlay、計測を追加する。

P0 では新 core を作らず、semantic shortcut を導入しない。

安全上、P0 の時点で最低限次を実装する。

- schema 8 PASS / target identity の確認
- validated firmware BIN SHA-256 の起動時確認
- validation で実際に使った backend executable SHA-256 の記録と起動時確認
- fixed device configuration 6 項目の一致確認
- reload 時に起動時と同じ admission gate を再実行
- unsupported / truncated MMIO 到達時の sticky UX-invalid banner
- F5 reset を跨いだ sticky UX-invalid state の維持
- host OS / GUI toolkit の keyboard auto-repeat 抑止

P0 では **現在の source tree、compiler、CMake、Ninja、picotool、Pico SDK の再検査コードを書かない**。同一 validated BIN の runtime admission には不要であり、正しい artifact を環境差だけで拒否する false rejection を作らないためである。

P0 baseline は少なくとも次の二種類を含める。

- 現在の登録済み interactive reference workload（例: active な PicoTetris target）
- LCD 連続更新、keyboard、audio、multicore / DMA を同時に使う **NES-class workload**

NES-class workload が再現可能な validated target / fixture として準備できていない場合、軽い workload だけで realtime 能力を合格扱いにせず、P0 realtime qualification は未完了とする。

各代表 workload は **10 分以上の連続 interactive session** を crash なしで実行し、session ratio、rolling ratio、pacer backlog / overrun、presentation drop、audio underrun / overrun を保存する。10 分は安定性・host fluctuation・入力反復を観測する最低 duration であり、realtime 許容幅そのものではない。

### Phase P1: validation receipt の正式化

`tools/picocalc.py` に、成功した Firmware backend run とその実行 executable から receipt を生成する機能を追加する。

P1 の receipt は P0 で既に必要な gate 情報を索引化する。

- report path / SHA-256
- target id / revision
- validated firmware BIN SHA-256
- backend accepted commit
- **validation で実際に起動した backend executable SHA-256**
- validation provenance への参照

receipt の手書き値だけでは起動できないこと、reload が同じ gate を通ることを unit / integration test で固定する。

P1 でも compiler / CMake / Ninja / SDK の **現在値**を preview 起動条件へ追加しない。

### Phase P2: 必要な場合だけ最適化

P0 baseline で core / device path が 1× を維持できない場合のみ profiler で bottleneck を特定する。

```text
既存 core で測定
  -> 1× を満たす: 新しい簡略 core は作らない
  -> 未達: bottleneck を測定
  -> host presentation 負荷を除去
  -> なお未達: UX semantics を変えない optimization のみ検討
```

CPU / PIO / DMA / IRQ / device event を飛ばすなど、UX timing 自体を改変する shortcut は「preview の 1× 達成」のためには採用しない。

もし将来 source-level / host-assisted mode を導入するなら、それは P0/P1 の same-BIN preview とは別 capability とする。その mode では必要な source/build snapshot identity を新たに gate し、P0/P1 の単純な artifact gate を曖昧に拡張しない。

## 12. 受け入れ条件

P0 / P1 の最初の完成条件を次とする。

1. Firmware backend PASS がない artifact では preview を起動できない。
2. receipt を手編集しても、参照 schema 8 report、target registry、disk firmware artifact、backend executable identity の再検証を突破できない。
3. validated firmware BIN が変更されると launch / reload の両方で拒否する。
4. backend source commit が同じでも、実際に起動する backend executable SHA-256 が validation 時と異なれば launch / reload の両方で拒否する。
5. `Ctrl+R` は起動時と同じ admission revalidation を必ず先に実行し、不一致時は新 artifact を実行せず現在 session を停止して validated 表示を解除する。
6. 現在の compiler / CMake / Ninja / picotool / Pico SDK が validation 時から変わっていても、validated firmware BIN と validated backend executable が byte-identical なら、それだけを理由に P0/P1 preview を拒否しない。
7. 対話操作により unsupported / truncated MMIO に初めて到達した場合、既存 MachineSession observation から検出し、以後 `UX JUDGEMENT INVALID` を sticky 表示する。**F5 reset で underlying MMIO counter / entries が初期化されても sticky 状態と banner は維持され、admission gate を通った新規 process または revalidated reload でのみクリアできる。** preview 自身は hardware FAIL を生成しない。
8. runtime device gate は `board`、`lcd_variant`、`psram`、`keyboard`、`sd.attached`、`sd.format` の6項目を一致必須とし、`cycles`、`keys`、`scenario`、`expected_stop_reason` を一致条件にしない。
9. representative workload で LCD を連続表示でき、key down / held / up、reset、reload を対話操作できる。host OS / GUI toolkit の auto-repeat による重複 key-down を firmware press event として投入しない。
10. supported audio workload では emulated audio timing を保持し、host monitor の mute / underrun / degradation 状態を UI で区別できる。
11. active PicoTetris 系 target と NES-class workload を各 10 分以上連続実行し、crash せず、wall-clock ratio、rolling ratio、pacer backlog / overrun、presentation drop、audio underrun / overrun を記録できる。NES-class workload が未整備ならこの項目は未完了とする。
12. realtime 許容幅が未固定の間は `Timing: UNCALIBRATED` を表示でき、core が追従できない session では `REALTIME NOT MET` を隠さない。
13. 1× 未達を隠すために CPU cycle、emulated frame、IRQ、PIO、DMA、device event、virtual audio event を skip しない。
14. scenario / trace / evidence を要求せずに UX session を開始できる。
15. preview の観測から hardware compatibility の PASS / FAIL を生成しない。
16. preview screenshot を conformance / golden artifact として扱わない。
17. Firmware backend の既存 schema 8 verdict、target registry、promotion policy、machine API schema 1 の決定性契約を変更しない。
18. realtime PASS の数値 threshold は P0 baseline の記録をレビューした後に別の設計記録で固定する。それまでは「計測できたこと」と「1× 合格」を分離する。

## 13. 非目標

- preview 単体による実機互換性保証
- preview 固有の異常を実機 bug と断定すること
- preview で異常が無かったことを実機保証にすること
- Firmware backend の置換
- `ExecutionModel::Serial` の正確性基準変更
- machine API v1 を wall-clock API へ変更すること
- P0/P1 起動時に source/toolchain 全体を再検証すること
- validation runner の `cycles` / fixed `keys` / `scenario` / expected stop contract を preview へ強制すること
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
validated BIN + validated backend executable identity
        |
        | launch/reload admission revalidation
        v
Validated Realtime Preview
        |
        | unsupported MMIO -> sticky UX judgement invalid (survives F5 reset)
        | 1× qualified      -> timing / UX inspection
        | 1× not met        -> timing judgement invalid, diagnostic observation only
        v
human / AI-assisted UX inspection
        |
        v
必要なら hardware final check
```

この提案の核心は、**preview が Firmware backend の後にしか来ないこと**、**reload でも gate を迂回できないこと**、**F5 reset でも model-coverage 警告を消せないこと**、**実際に動かす firmware BIN と backend executable の bytes を pin すること**、そして **1× や model coverage を満たせないときに嘘をつかないこと**である。

Firmware backend は「この source / build / artifact を登録された PicoCalc hardware model 上で受け入れてよいか」を判定する。Validated Realtime Preview は、その検証済み artifact を同じ backend executable で wall-clock 実行したときの UX を観測する。

P0/P1 では source/toolchain provenance を保存しつつ、runtime gate は同一 BIN / backend executable と明示された6つの device configuration に絞る。新しい build を見たい場合は必ず Firmware backend へ戻る。preview 自身は hardware correctness の権限を持たない。
