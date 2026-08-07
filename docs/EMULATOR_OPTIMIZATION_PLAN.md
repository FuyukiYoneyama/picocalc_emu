# Firmware emulator高速化計画

**状態:** 計画確定、OPT0-A semantic profile・部分cost計測済み（full horizon/event costは未完）
**基準日:** 2026-08-06  
**対象:** `picoem-picocalc`のRP2040 Serial実行と、`picocalc_emu`のfirmware regression  
**性能基準:** [`R5_REALTIME_PERFORMANCE.md`](R5_REALTIME_PERFORMANCE.md)

## 1. 目的

この高速化の目的は、エミュレーターを実時間の100%で動かすことではない。実機と同じBINに
対して、実機と同じ動作・同じ結果を担保できる範囲を維持したまま、firmware regressionの
wall timeを短縮し、開発全体のターンアラウンドを改善することである。

優先順位は常に次の順とする。

1. 実機との意味的・時間的な正確性
2. 同一入力に対する決定性
3. fail-closedな検証契約
4. wall timeの短縮

最終UARTや最終framebufferが一致するだけでは正確性を満たさない。cycle、IRQ、PIO/GPIO edge、
PSRAM、timer、DMA、PWMなど、ファームウェアから観測可能な途中状態が変わる最適化は採用しない。

## 2. 非目標

- 100% real timeの達成を合格条件にしない。
- workloadの試験範囲、scenario step、device modelを減らして速く見せない。
- `step_quantum`を大きくしただけの近似実行を正規経路へ入れない。
- Host backendの高速性をFirmware backendの正確性の代用にしない。
- 現在のエミュレーター出力だけを実機の真値とみなさない。
- RP2040 Serialの正確性が確立する前にthreaded modelを高速化の主経路にしない。

## 3. 固定baseline

R5実機相関前の登録済みbaselineは次のとおりである。

| 項目 | 固定値 |
|---|---|
| target | `picotetris-r4` revision 2 |
| BIN SHA-256 | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| backend | `3bc6bbd7833e45fbf94d640eb7fbe056dd9fbd81`、release、Serial |
| scenario | `tetris-line-clear`、85/85 steps |
| quantum | `1` |
| emulated cycles | `927,528,660` |
| virtual time | `3.715000 s` |
| WSL wall time中央値 | `63.247008 s` |
| 実時間比中央値 | `5.873808%` |
| slowdown中央値 | `17.024767倍` |

同一条件10 runのreport、UART、PNGはbyte-identicalである。この値は性能比較の起点であり、
R5実機合格の証拠ではない。

## 4. 既知の診断結果

以下は高速化候補の方向を決める診断値であり、targetの正式な受入記録ではない。

| 診断 | 概算throughput | 読み取れること |
|---|---:|---|
| CPU-only、Serial、quantum 1 | 29.9 Mcycle/s | CPU実行だけでも100% real timeには届かない |
| CPU＋PIO、Serial、quantum 1 | 15.0 Mcycle/s | per-cycle統合でthroughputがおよそ半減する |
| CPU＋PIO、quantum 64 | 30.0 Mcycle/s | dispatch償却の余地は大きいが、正確性は別途必要 |
| PIO direct、1 SM | 94〜102 Mcycle/s | PIO interpreter単体だけが全コストではない |
| PIO direct、2 SM | 55〜59 Mcycle/s | SM数に応じたcost増加がある |
| PIO direct、4 SM | 31〜34 Mcycle/s | per-cycle orchestrationも主要候補になる |

`picotetris-r4`を非正規に`quantum=2`で実行した試験では、wall timeは約40.45秒、実時間比は
約9.18%まで改善した。UARTと最終framebufferは一致したが、次が一致しなかった。

- 到達cycle: baselineより15 cycle増加
- PSRAM `tick_count`: baselineより1,070,641減少
- timeline digest: 不一致

したがってこの候補は不採用である。この結果は、最終画面とUARTだけを合否契約にすると
誤った最適化を通すことを実証している。

## 5. 用語

- **blocked episode**: 両coreがhaltedまたはWFE待機で、CPU instructionが進まない連続区間。
- **blocked upper bound**: blocked episodeの全cycle。安全に飛ばせる量の上界であり、
  fast-forward可能量そのものではない。
- **proven-safe episode**: CPU停止中に動作する全自律機構を考慮しても、次の観測可能イベント
  まで一括前進できることを証明できた区間。
- **event horizon**: timer、PIO、DMA、PWM、IRQ、外部入力などのうち、最も早い次イベントcycle。
- **boundary event**: 比較一致、IRQ assert/delivery、pin transition、FIFO/DREQ変化など、
  そのcycleを越えてまとめてはならないイベント。
- **candidate optimization**: 自動回帰は通るが、R5実機相関をまだ通していない暫定候補。
- **promoted optimization**: 正確性回帰、性能条件、R5実機相関をすべて通した正式採用。

## 6. OPT0: 観測契約とprofiler

OPT0では挙動を変えない計測・契約だけを追加する。診断機能を有効にした実行と、性能測定を
同一runに混ぜない。

### 6.1 二つの実行モード

1. **correctness mode / trace ON**
   - cycle付きeventを逐次hashへ畳み込む。
   - 巨大なevent配列や927 Mcycle分のtraceをメモリへ保持しない。
   - wall timeは採用判定に使わない。
2. **performance mode / trace OFF**
   - baselineと同じ観測だけでwall timeを測る。
   - profiler、trace、詳細ログによる測定歪みを入れない。

両modeは同じBIN、target revision、scenario、backend candidateから実行し、modeの違いをreportへ
記録する。

### 6.2 `behavior_sha256`

`normalized_report_sha256`はbackend commitなどprovenanceも含むため、backendを変更すれば挙動が
同じでも変化する。これを置き換えず、挙動だけを比較する`behavior_sha256`を追加する。

`behavior_sha256`はreportから項目を削るdeny-list方式ではなく、次の観測項目を明示した
canonical projectionのhashとする。

- stop reason、exception、unsupported MMIO、scenario verdict
- master/core cycle、virtual elapsed time、clock transition
- UART byte列またはそのhash
- framebuffer、PNG、LCD transaction/edge digest
- keyboard delivery/drop、SD、PSRAM、audio、device別結果とcounter
- IRQ assert/delivery、PIO/GPIO、DMA/DREQ、timer/PWM等のevent digest
- targetが要求するmarker、step、最終状態

backend commit、host path、wall-clock timestamp、実行機名などprovenance-only fieldは含めない。
一方で、BIN、device設定、scenario、quantumなど挙動を変え得る入力条件はhash対象または外側の
厳密な同一性検査対象とする。`normalized_report_sha256`は完全reportとprovenanceの証拠として
引き続き保持する。

### 6.3 streaming event digest

少なくとも次を`(domain, source, cycle, payload)`のcanonical byte表現で逐次hashする。

- IRQ source assert、NVIC pending、core delivery、exception entry/return
- PIO state-machine stepの観測可能なpin transition
- PSRAM CS/SCK/MOSI/MISO transitionとtransaction境界
- LCD control/data transitionとtransaction境界
- DMA transfer、DREQ変化、completion/chain
- timer alarm match、SysTick、PWM wrap/compare
- UART/SPI/I2CのFIFO・shift完了などtargetが観測するイベント
- scenarioによるkeyboard、GPIOその他外部入力

event数自体もdomain別に記録し、hashの偶然一致だけに依存しない。trace実装はbackendの
通常実行順序を変更してはならない。

### 6.4 blocked/safe区間の計測

次を64-bit counterとして記録する。

- total master cycles
- coreごとのrunning、halted、WFE waiting cycles
- both-blocked cyclesとepisode数
- proven-safe cyclesとepisode数
- event horizonまでの距離
- fast-forwardを禁止したsource別cycle数・episode数
- PIO、DMA、PWM、SysTick、UART、SPI、I2C、ADC、pending IRQ、外部入力の状態

区間長の平均だけでなく、次を累積分布として保持する。

```text
S(K) = 長さK以上のepisodeに含まれるcycle総数
K    = 1, 2, 4, 8, ... 2^n
```

`blocked_upper_bound`と`proven_safe`を別々に集計する。両者の差は「停止しているCPU以外の
どの機構がfast-forwardを妨げたか」を示す。phase別の比較が必要な場合は、backendへ
PicoTetris固有のUART文字列をhard-codeせず、scenario/record側のcycle markerで区切る。

### 6.5 音声に関する計測上の注意

PicoTetrisの参照音声は48 kHzのDMA pacingを使用するため、250 MHzでは平均約5,208.33 cycle
ごとにDMA event候補がある。一方、PWM wrapは255なのでcarrierは約976.5625 kHz、wrapは
256 cycleごとであり、同じ時刻系ではない。

`audio::stop()`は現在DMAをabortして中央levelへ戻すが、PWM sliceを明示disableしない。
したがって「音声停止後はPWMも停止」「描画外はPIOも停止」と仮定せず、実際のenable、stall、
IRQ、FIFO、pin観測状態からproven-safeを判定する。

## 7. コストモデルと優先順位判定

約68 ns/cycleの全体平均をblocked pathの損益分岐へ直接使わない。同じrelease build、同じhost
固定CPU上で次を個別に測る。

- `Cblocked`: 現行blocked branchが1 cycle進むcost
- `Chorizon`: 有効な全event sourceから最小horizonを求めるcost
- `Cadvance(L)`: L cycle分の状態を閉形式またはchunkで更新するcost
- `Cevent`: horizon上のeventを発火・routeするcost

長さLのepisodeを飛ばす候補の推定節約時間は次とする。

```text
saving(L) = L * Cblocked - Chorizon - Cadvance(L) - Cevent
```

全episodeについて正の`saving(L)`を合計し、既知のhot-path改善余地と比較する。

```text
ideal_ceiling = total_cycles / (total_cycles - proven_safe_cycles)
```

この式はjump処理が無料だった場合の理想上限であり、性能予測には使わない。算術モデルは
実装優先順位を選ぶscreeningであって、実装後の実測を省略する根拠ではない。差が十分大きい
候補を先に実装し、近い場合だけ小規模prototypeを比較する。

## 8. OPT1: 低リスク高速化

OPT0の結果により、OPT1-AとOPT1-Bの順序を決める。いずれも一変更単位ずつ実装し、各変更で
正確性gateと性能gateを通す。

### 8.1 OPT1-A: exact idle fast-forward

両core blocked時に、次のevent horizonまでmaster clockと全関連状態を等価に進める。

event horizonは少なくとも次の最小値である。

- timer alarm match
- SysTickその他core-local timer event
- PIO instruction/pin/IRQ/FIFO event
- DMA DREQ、transfer、completion、chain event
- PWM wrap/compare/IRQ event
- UART/SPI/I2C/ADCの完了またはIRQ event
- 外部pin/deviceからの変化
- scenario input、poll、snapshot、停止条件

単調counterは、閉形式更新が1-cycle実行とbit-identicalになる場合だけbulk incrementする。
比較一致イベントは越えず、その本来のcycleへ着地してassert、route、wakeを通常順序で処理する。
複数eventが同一cycleにある場合の優先順も現行1-cycle実行と一致させる。

現在のboth-blocked branchがtimer deadlineだけを見ていることを、全deviceに対する安全性の証拠と
みなさない。まず全自律機構がquiescentな保守的経路を実装し、sourceごとのnext-event計算は
正確性試験を追加しながら段階的に広げる。

### 8.2 OPT1-B: 既存hot pathの低リスク整理

- 不変な状態判定、pin mapping、maskの再計算を避ける。
- PIO/device/GPIO統合で同一cycle内に重複する読取・lock・mergeを減らす。
- inactive SM/deviceのdispatchを省く。
- framebuffer/device lockは観測順序を変えない範囲で回数を減らす。
- allocation、formatting、診断分岐をperformance modeのinner loopから除く。

PIO、PSRAM、LCDのedge順序を変えるまとめ処理はOPT1-Bへ混ぜず、OPT2で扱う。

## 9. OPT2: exact event batching

OPT1とR5の相関後、CPUがrunningの区間にもevent horizon方式を広げる。batchは次の境界で必ず
分割する。

- CPUのPIO/GPIO MMIO read/write
- CPUによるSIO `GPIO_IN`その他pin入力の読み出し
- FIFO/DREQの状態がCPUまたはDMAから観測可能になるcycle
- IRQ assert、NVIC delivery、exception entry
- PIO pin transitionと外部device応答
- timer、SysTick、PWM、DMAの比較一致
- scenario input、snapshot、停止条件

batch内部のstate更新は、1-cycle referenceと同じ最終値だけでなく、全観測可能eventのcycleと
順序を一致させる。`quantum=2`試験で発生したtimelineとPSRAM counterのずれを許容しない。

## 10. OPT3: CPU/decode高速化

event schedulingを安定させた後に、CPU側を最適化する。

- Thumb decode cacheのhit率、無効化cost、self-modifying code境界を計測する。
- immutable flash/XIPとmutable RAMでcache policyを分離する。
- MMIO、exception、barrier、code write時の無効化を保つ。
- dual-coreの可視性と既存cache invalidation契約を変えない。

JITや大規模なthreaded再設計は、OPT3までの実測で必要性が示された場合だけ別計画にする。

## 11. 正確性gate

候補は次をすべて満たさなければ破棄する。

1. backendのunit test、fmt、Clippyが合格する。
2. `picocalc_emu`のportable、Python、schema、host、firmware regressionが合格する。
3. 登録済みBIN、scenario、device設定を変更しない。
4. stop reason、exception、unsupported MMIO、scenario stepが一致する。
5. master/core cycle、virtual time、timeline、device counterが完全一致する。
6. UART、framebuffer、PNG、SD、PSRAM、keyboard結果が一致する。
7. `behavior_sha256`とdomain別streaming event digestが一致する。
8. 複数runで結果が決定的に一致する。
9. PicoTetrisだけでなく、Template Bと公式hello系など異なるdevice構成でも退行しない。

最適化により既存エミュレーターの誤りが見つかった場合は、旧hashへ合わせて誤りを温存しない。
hardware evidenceと仕様を根拠にmodelを修正し、新しいversioned validation recordを作る。
旧recordは時点証拠として書き換えない。

## 12. 性能gate

正確性gate合格後、trace OFFのperformance modeで測る。

- 同一host、同一logical CPUへ固定する。
- release、`--locked`、同一BIN/target/scenarioを使う。
- warm-upを除外し、原則10 run以上を採る。
- wall time、cycle/s、実時間比、中央値、分散、95% CIを保存する。
- 主workloadはwall time中央値5%以上の改善を採用目安とする。
- 他の代表workloadで3%を超える中央値退行があれば、理由を特定するまで採用しない。
- 小さい差は測定noiseと区別できるまでrun数を増やす。

5%は正確性を緩める閾値ではない。正確性gateは改善率にかかわらず必須である。5%未満でも
後続最適化の前提になる単純化は、複雑性を増やさず退行がない場合に限り個別判断する。

## 13. R5との関係

OPT0と最初のOPT1候補は、R5実機相関を豊かにする観測契約を先に用意するため、R5前に実施できる。
ただしR5前の合格は**candidate optimization**であり、現在のエミュレーター内部の一致を示すだけである。

R5では同一BIN SHAを使い、既存のLCD、keyboard、line clear、game-over、restart、PSRAM、SD、
audio条件に加えて、取得可能なtimer、IRQ、PIO/GPIO、PSRAM transactionの相関を行う。実機と一致した
範囲を明示して初めて**promoted optimization**とする。

OPT2以降は原則として最初のR5相関後に行う。R5で基準modelのずれが判明した場合は、速度より先に
正確性を修正してbaselineとversioned validationを更新する。

## 14. 実施順序と状態

| 順序 | 作業 | 状態 | 完了条件 |
|---:|---|---|---|
| 0 | R4 CIとR5前性能baseline | **完了** | 3 repo CI合格、10 run baseline固定 |
| 1 | OPT0-A blocked/safe profiler | **進行中** | schema 2 semantic profileと部分cost完了。full horizon・event/routing costが残る |
| 2 | OPT0-B behavior/streaming trace契約 | 未着手 | trace ONで全digest、trace OFFで無歪み測定が可能 |
| 3 | コストモデルによるOPT1優先順位決定 | 未着手 | idle fast-forwardとhot pathの期待値を同一尺度で比較する |
| 4 | OPT1-AまたはOPT1-Bの第一候補 | 未着手 | 正確性gate＋性能gate合格、candidateとしてrecord化 |
| 5 | R5実機相関 | 実機着手前 | 同一BINと追加観測値で相関し、候補を正式採用または棄却する |
| 6 | 残るOPT1候補 | R5後 | 独立変更単位で正確性・性能gate合格 |
| 7 | OPT2 exact event batching | R5後 | 全boundary eventのcycle/order一致 |
| 8 | OPT3 CPU/decode | R5後 | cache invalidationを含む完全回帰＋有意な性能改善 |

依存関係は次のとおりである。

```text
R4 + baseline
      |
      v
OPT0 profiler + exactness contract
      |
      v
cost model -> OPT1 first candidate -> R5 hardware correlation
                                      |
                                      v
                         remaining OPT1 -> OPT2 -> OPT3
```

## 15. 記録と変更単位

- profiler/contract、各最適化、record更新を別commitにする。
- 一つのcommitで複数の独立最適化を混ぜない。
- candidateごとに変更前後のwall time、hash、event count、テスト結果を保存する。
- backend commitを更新するときはschema 3の新target revisionとvalidation attestationを作る。
- R3/R4/R5以前のrecordは書き換えない。
- 性能結果はhost、OS/WSL、CPU affinity、toolchain、run数を必ず伴う。
- 不採用候補も、理由と検出した不一致を記録し、同じ誤りを再試行しない。

OPT0-Aの初回PicoTetris profileは
[`firmware-validation/records/opt0-a-20260806-01/notes.md`](../firmware-validation/records/opt0-a-20260806-01/notes.md)
に保存した。両core停止は全cycleの66.692909%だったが、active sourceを考慮した現在の
保守的なproven-safe下限は0 cycleだった。このschema 1結果はproduction用`is_idle()`が静的な
FIFO/IRQ stateまでblockerとした診断であり、不変証拠として保持する。

計測専用predicateをtemporal/wake blocker、stationary state、existing exact-bulk workへ分離した
schema 2再計測は
[`firmware-validation/records/opt0-a-20260807-03/notes.md`](../firmware-validation/records/opt0-a-20260807-03/notes.md)
に保存した。同一PicoTetrisの全618,595,844 blocked cycleが観測境界上proven-safeで、85/85、
cycle、UART、framebufferも一致した。全blocked cycleを除去した場合の3.002364倍はvirtual-cycle
dispatchの上限比であり、wall-time speedup予測ではない。残るfull horizon、boundary/event、
IRQ/wake costを同一尺度で測ってからOPT1の優先順位を決める。

同じhost・CPU固定で取得した部分costは
[`firmware-validation/records/opt0-a-20260806-02/notes.md`](../firmware-validation/records/opt0-a-20260806-02/notes.md)
に保存した。現行blocked stepは52.647255 ns、現在の保守的probeは10.771746 ns、quiescentな
`tick_peripherals(L)`はL=1〜1,048,576で37.108583〜37.825914 nsだった。ただしfull horizon、
clock更新、boundary event、IRQ route、wake checkを含まないため、まだ優先順位決定には使わない。

## 16. 最終判断規則

高速化候補は、次の順に一つでも失敗した時点で不採用とする。

```text
source/target contract
        -> correctness gate
        -> determinism gate
        -> performance gate
        -> R5 hardware correlation
        -> promotion
```

速度向上は正確性の代償として受け入れない。逆に、正確性を維持した有意な改善は100% real timeに
届かなくても価値がある。評価対象は「どこまで実時間へ近づいたか」だけでなく、同じ実機相当結果を
得るための開発待ち時間をどれだけ安全に削減できたかである。
