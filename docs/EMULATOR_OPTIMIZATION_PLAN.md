# Firmware emulator高速化計画

**状態:** OPT1-A・OPT1-B promoted、R5 PicoCalc実機相関完了。OPT2-G UART exact scheduler laneは正確性合格・性能不採用（中央値8.681%退行）・revert済み。OPT2は性能条件未達のまま追加promotionなしで終了し、次はOPT3 CPU/decode/execute block cache
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

backend `763595fedefa08886b41298be79bff69324ac51f`でこの契約をfeature分離して実装した。
PicoTetris全走行2回の`behavior_sha256`は
`3ee0dff39b10b5863aa28326189f70ba553e714c1e9ada403db1ad4622a1daf3`、event streamは
`448b0a00575b6748445906a5863c508f2fb86910fba73137605d66147bd191d9`で一致した。
trace OFF production binaryのnormal reportもtrace ON時とbyte-identicalである。schema、CLI、
domain mapping、受入結果は[`OPT0_B_BEHAVIOR_CONTRACT.md`](OPT0_B_BEHAVIOR_CONTRACT.md)に固定した。

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

最初のOPT1-B変更はbackend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`で実装した。
PIO idleを最初に評価し、activeなら結果を変えない残りのread-only predicateを短絡する。また、
`all_peripherals_idle()`に含まれるDMAの重複判定を除いた。tick、edge、IRQ、event horizonの順序は
変更していない。

PicoTetrisはbaselineとbehavior SHA、173,498,680 event、全9 domain、cycle、timeline、UART、
framebufferが一致した。trace OFF 10 runのwall中央値は27.122874秒から25.381594秒へ
6.419972%短縮した。Template Bの3 run中央値退行は1.357247%で3%上限内、公式Helloは95億cycleと
8 MiB PSRAM全域照合を合格した。R5相関firmwareでも既存preflightと同じ観測契約を再現し、
既存hardware evidenceへの同値性を確認したためpromotedとする。詳細は
[`OPT1_B_SERIAL_FAST_PATH.md`](OPT1_B_SERIAL_FAST_PATH.md)にある。

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

### 9.1 dispatcher-only候補（不採用）

最初の候補`d43693cf26f7f947b389ea9f673995a686fda602`では、hardware quantumを1のまま維持し、
runnerからbackendへの外側dispatchだけを最大64回まとめた。各substepは従来のperipheral、PIO、
GPIO、IRQ処理を省かない保守的な候補だった。

開発途中では、`clk_sys`変更後もbatchを継続したため、runnerの`VirtualClock` rebaseが遅れた。
その結果、最初のscenario観測が1,397 cycle早まり、総cycleは`927,527,264`、event数は
`173,498,675`となってbaselineからずれた。最終UARTとframebufferだけは一致していたため、
behavior/event契約がこの誤りを検出した。`sys_clk_hz`変更を明示境界に追加した後は、総cycle、
85-step timeline、behavior SHA、`173,498,680` event、全9 domain、UART、framebufferが
OPT1-Bと完全一致した。

しかし同時条件3組のtrace OFF A/Bでは、OPT1-B中央値`26.16 s`に対して候補は`26.54 s`で、
約1.45%遅かった。5%改善目安を満たさず、単純性の利点も性能退行を正当化しないため、
`9a7387c9aca50aba6434323d2d5e24566a6e9436`でrevertした。これはOPT2完了を意味しない。
次候補は、外側callの集約ではなく、CPUが観測可能な境界とdevice event horizonの間で実際の
per-cycle orchestrationを削減できる範囲を測定してから設計する。詳細は
[`opt2-dispatcher-20260808-01`](../firmware-validation/records/opt2-dispatcher-20260808-01/notes.md)に残す。

### 9.2 OPT2-B running event-horizon profiler（完了）

backend `ac0c3052e6c28fcf235a33f98f3a96470d2966f1`に、通常buildから完全に分離した
`event-horizon-profiler` featureを追加した。CPU MMIO、SIO `GPIO_IN`、FIFO/DREQ、IRQ/exception、
PIO/device、DMA、timer/SysTick/PWM、serial、clock、runner所有external boundaryを重複を許して
数え、境界間dispatch/cycleと保守的horizon距離を`2^n`累積分布へ記録する。

同一PicoTetris BINの計装runは85/85、927,528,660 cycle、virtual time、UART、framebufferが
登録済みOPT1-B値と一致した。runningは308,932,816 cycle、172,715,307 dispatchで、post-hoc
candidateは28,608,173 dispatch、46,411,891 cycle、2,388,571 intervalだった。candidateは
running cycleの15.0233%、平均11.977 dispatch / 19.431 cycleである。PIO 217,027,394 cycle、
UART 40,197,601 cycle、DMA 5,320,143 cycleが1-cycle fallbackに制限された。

観測したgapは予測可能なsafe windowではないため、artifactは
`observed_gaps_are_safe_windows=false`とする。また、candidateの全run virtual cycle比5.0038%を
wall-time上限へ読み替えない。blockedとrunningでは1 cycle当たりcostが異なり、batch後もCPU
decode/executeが残るためである。次のOPT2-Cでは、現在の保守的horizon内かつCPU MMIOなしの
区間だけを対象に小規模prototypeを作り、per-dispatch costとtrace OFF A/Bを測る。PIO/UART/DMA
deadlineの拡張は限定prototypeの結果後に別変更単位で判断する。証拠は
[`opt2-b-running-horizon-20260808-01`](../firmware-validation/records/opt2-b-running-horizon-20260808-01/notes.md)
に固定した。

### 9.3 OPT2-C 限定exact prototype（完了、不採用）

事前証明可能な最小subsetとして、core 1停止、pending IRQなし、完全horizon内、decode-cache hit済みの
逐次・bus-free・fault-free・1-cycle Thumb-16命令だけを最大64 cycleまとめた。PicoTetrisのcycle、
85-step、behavior SHA、173,498,680 event、全9 domain、UART、framebuffer、PSRAM counterはOPT1-Bと
一致した。

しかし成立したのは8,420 batch、23,176 cycle、14,756 dispatch省略、最大13 cycleで、全runの
0.002498%だけだった。Trace OFF 3 paired screeningはbaseline中央値51.38秒、candidate 57.49秒で
11.89%退行し、全pairが遅かった。5%改善基準から遠いため10 run promotion測定を早期停止し、
candidate `815ef5d`を`c44c87f`でrevertした。次はPIO/UART/DMA deadline promotionとCPU/decode
block workを別々に測り、優先順位を決める。詳細は
[`OPT2_C_EXACT_BATCHING.md`](OPT2_C_EXACT_BATCHING.md)に固定した。

### 9.4 OPT2-D 候補レバー比較（完了）

backend `e482172565fc3073ba0960eb5e2642968a65ae52`でprofiler schemaを2へ上げ、PIO/UART/DMAの
one-cycle fallback重複signatureと、core別decode hit/miss・動的sequential hit run分布を同じ
PicoTetrisで採取した。計装runは85/85、cycle、UART、framebufferに一致し、別trace runも
behavior SHA、173,498,680 event、全9 domainに一致した。

one-cycle fallback unionはrunningの83.2696%で、PIO-onlyが217,025,266 cycle、runningの
70.2500%を占めた。UART-onlyは34,901,586 cycle、DMA-onlyは22,000 cycleだった。decode cacheは
99.8279% hitだが、動的sequential hit runは平均4.563命令で、16命令以上に属するhit massは
13.5240%だった。

どちらもsafe windowやwall speedup予測ではない。その制限をartifactへ明記したうえで、次candidateは
PIO exact event horizon / bulk advanceを選ぶ。UARTはその次、CPU/decode block cacheはOPT3へ残す。
詳細は[`OPT2_D_LEVER_COMPARISON.md`](OPT2_D_LEVER_COMPARISON.md)に固定した。

### 9.5 OPT2-E PIO pull-stall bulk prototype（完了、不採用）

一般PIO schedulerの前に、全enabled SMが空TX FIFOへの`PULL`で停止している最小subsetを試作した。
同一`step_n_with_pins(n)`内ではCPU/DMAがFIFOを補充できないため、命令実行、pin、FIFO、DREQ、IRQ
eventは起きず、divider phaseとstall診断値だけを閉形式で更新できる。active/mixed stall、`WAIT`、
RX-full、TX refillは従来tickへfallbackし、GPIO/PSRAM/LCD観測と外側dispatchは省略しなかった。

clean candidate `a7ac9020b9861c1c4803187b7092512b65f60835`は85/85、927,528,660 cycle、
behavior SHA、173,498,680 event、全9 domain、UART、framebuffer、PSRAM tickをOPT1-Bと完全一致させた。
しかし受理した371,982,564 call / system cycleはすべて1 cycleで、対応PIO tickは185,895,678だった。
外側が各PIO tick直後にpin/deviceを観測するため、内部bulkへ複数cycleを渡せなかった。

trace OFFのclean 3 paired screeningはbaseline中央値25.70秒、candidate 25.64秒、改善0.233463%で、
5%採用基準未達だった。候補は`a7939e5`でrevertし、active targetとpinは変更していない。次のPIO
調査は、constant-pin区間に対するPSRAM/LCDのexact bulk observation契約を設計した後、外側の
`tick_pio + update_gpio`を同じ静止証明下でまとめる。UART deadline promotionは独立した次点、
CPU/decode block cacheはOPT3に残す。詳細は
[`OPT2_E_PIO_PULL_STALL_PROTOTYPE.md`](OPT2_E_PIO_PULL_STALL_PROTOTYPE.md)に固定した。

### 9.6 OPT2-F stationary pin-device bulk prototype（完了、不採用）

OPT2-Eの静止PIO証明に、PSRAM、PIO LCD、SPI side-band deviceの明示opt-in契約を加え、同一pin
sampleの最初だけを通常処理し、残りを閉形式でまとめた。未知device、active/mixed stall、`WAIT`、
FIFO refillは従来per-cycle経路へfail-closedでfallbackした。

clean candidate `9ec1988ec4c5c4fa240a1f409ac9524364e017de`はcycle、85/85、behavior SHA、
173,498,680 event、全9 domain、UART、framebuffer、PSRAM tickをOPT1-Bと完全一致させた。
23,199,887 outer callで37,012,745回の重複`update_gpio`を削減したが、CPU 0固定clean 3 pairedの
中央値はbaseline 26.18秒、candidate 26.00秒、短縮0.687547746%で5%条件未達だった。

候補は`cdb7584`、前提PIO reapplyは`2671d04`でrevertし、active targetとpinは変更していない。
次はOPT2-Dで次点だったUART deadline promotionを試す。CPU/decode block cacheはOPT3に残す。
詳細は[`OPT2_F_STATIONARY_PIN_DEVICE_BULK.md`](OPT2_F_STATIONARY_PIN_DEVICE_BULK.md)に固定した。

### 9.7 OPT2-G UART exact scheduler lane（完了、不採用）

UART TXのTXRIS、FIFO pop、DREQ境界を扱うfeature-gated・fail-closedのUART-only laneを試作した。
実際のrunning fast-forwardはCPU MMIO、clock変更、DMA orderingを事前証明できないため実装せず、
非UART peripheralがidleである場合だけ通常のUART orderingを保つlaneとした。candidate
`593e6d78541722920e1fa903e682d49912eae825`はcycle、85/85、behavior SHA、全9 domain、UART、
framebuffer、PSRAM tickをreferenceと完全一致させた。

CPU 0固定clean A/B/A/B/A/Bのbaseline中央値は25.92秒、candidateは28.17秒で、改善率は
`-8.6805555556%`（8.681%退行）。5%条件未達のためexactnessは合格、性能は不採用とする。
candidateは`335ecdd7f01cbc5d4f63e18403033bd629efbe77`でrevertし、最終内容がbaselineと一致した。
backend CI run `31287315634`も成功した。active targetとvalidation attestationは変更しない。証拠は
[`OPT2_G_UART_EXACT_LANE.md`](OPT2_G_UART_EXACT_LANE.md)と
[`opt2-g-uart-deadline-20260809-01/`](../firmware-validation/records/opt2-g-uart-deadline-20260809-01/)に固定した。
OPT2は性能条件未達のまま追加promotionなしで終了し、次はOPT3 CPU/decode/execute block cacheである。

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

R5では`picotetris-r5`の同一BIN/UF2 SHAを使う。firmwareはLCD、PSRAM、SD、audio、line clear、
game-over、restartを自動検査した後、公式keyboard firmware由来67キーを確認する。`CAPS`以外の
66キーは任意順・個別retry・SD progress resumeとし、`CAPS`は途中で押さず`66/67`の後に
最後に押す。別の診断BIN、ゲーム途中の写真、連続入力成功は要求しない。
エミュレーターpreflightは完了しており、実機のUART全文、参照音確認、安定した最終PASS写真1枚と
一致範囲を記録して初めて**promoted optimization**とする。操作契約は
[`R5_HARDWARE_CORRELATION.md`](R5_HARDWARE_CORRELATION.md)を正典とする。

2026-08-08の実機runは同一UF2でLCD、PSRAM、FAT32、audio、PicoTetris、keyboard 67/67を合格し、
`io_errors=0 progress=saved overall=pass`となった。UART、最終写真、参照音、SD進捗は
`firmware-validation/records/r5-hardware-20260808-01/`へ固定したため、OPT1-Aをpromotedとする。

OPT2以降は原則として最初のR5相関後に行う。R5で基準modelのずれが判明した場合は、速度より先に
正確性を修正してbaselineとversioned validationを更新する。

## 14. 実施順序と状態

| 順序 | 作業 | 状態 | 完了条件 |
|---:|---|---|---|
| 0 | R4 CIとR5前性能baseline | **完了** | 3 repo CI合格、10 run baseline固定 |
| 1 | OPT0-A blocked/safe profiler | **完了** | schema 3 full horizon、boundary分布、production costを固定 |
| 2 | OPT0-B behavior/streaming trace契約 | **完了** | trace ONで全digest、trace OFFで無歪み測定が可能 |
| 3 | コストモデルによるOPT1優先順位決定 | **完了** | OPT1-A exact idle fast-forwardを第一候補に選択 |
| 4 | OPT1-A第一候補 | **promoted完了** | 正確性・性能gateとR5同一artifact実機相関に合格 |
| 5 | R5実機相関 | **完了** | `r5-hardware-20260808-01`に67/67、UART、音、最終写真、進捗を固定 |
| 6 | OPT1-B serial fast-path gate | **promoted完了** | 全digest一致、主workload 6.42%短縮、追加workload合格、R5既存実機相関との同値性 |
| 7 | OPT2 exact event batching | **終了（性能条件未達）**。OPT2-G UART laneまでexact候補を検証し、追加promotionなし | 全boundary eventのcycle/order一致＋有意な性能改善 |
| 8 | OPT3 CPU/decode | R5後 | cache invalidationを含む完全回帰＋有意な性能改善 |

依存関係は次のとおりである。

```text
R4 + baseline
      |
      v
OPT0 profiler + exactness contract
      |
      v
cost model -> OPT1-A -> R5 hardware correlation
                            |
                            v
                         OPT1-B -> OPT2 -> OPT3
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
dispatchの上限比であり、wall-time speedup予測ではない。この時点ではfull horizon、
boundary/event、IRQ/wake costが未測定だった。

同じhost・CPU固定で取得した部分costは
[`firmware-validation/records/opt0-a-20260806-02/notes.md`](../firmware-validation/records/opt0-a-20260806-02/notes.md)
に保存した。現行blocked stepは52.647255 ns、現在の保守的probeは10.771746 ns、quiescentな
`tick_peripherals(L)`はL=1〜1,048,576で37.108583〜37.825914 nsだった。ただしfull horizon、
clock更新、boundary event、IRQ route、wake checkを含まないため、この履歴値だけでは優先順位を
決めなかった。

OPT0-Aの完了記録は
[`firmware-validation/records/opt0-a-20260808-04/notes.md`](../firmware-validation/records/opt0-a-20260808-04/notes.md)
に保存した。現行modelの全sourceを覆う保守的horizonは、TIMER alarm、PWM wrap、caller所有の
外部境界にexact deadlineを使い、長いdeadlineをまだ証明していないsourceには1 cycle fallbackを
使う。PicoTetrisの618,595,844 safe cycleは2,064,042 event-bounded segmentへ分かれ、
2,063,903件がPWM、138件がTIMER境界だった。production featureを含まない別binaryで測った
`Cblocked=48.621175 ns`に対し、`Chorizon=30.388395 ns`、`Cadvance(1)=39.412803 ns`、
TIMER event/route/wake増分`7.122434 ns`で、損益分岐は2 cycleだった。既存baselineへ適用した
33.329秒・実時間比11.146%はscreening用の算術投影であり、最適化実測ではない。この差により
OPT1-A exact idle fast-forwardをOPT1-Bより先に実装する。実装前にOPT0-Bを完了し、OPT1-Aでは
runner所有のscenario/input horizonも必ず境界へ接続する。

OPT1-A candidateはbackend `c68c58f6c37fb31eb9313566c8b16883db9063b6`で完了した。
両core blocked時だけ全source horizonとrunner所有の外部境界までexact bulk advanceし、未証明
sourceは1 cycle fallbackする。PicoTetrisは85/85、cycle、UART、framebuffer、timelineを維持した。
behavior traceはhost UART drain cadence依存を除いたschema 2へversion upし、one-cycle referenceと
全9 domainで一致した。CPU固定10 runのwall中央値は63.247秒から27.123秒へ57.116%短縮し、
実時間比中央値は5.874%から13.697%へ向上した。詳細は
[`OPT1_A_EXACT_IDLE_FAST_FORWARD.md`](OPT1_A_EXACT_IDLE_FAST_FORWARD.md)と
[`firmware-validation/records/opt1-a-20260808-01/notes.md`](../firmware-validation/records/opt1-a-20260808-01/notes.md)
に固定した。R5 emulator preflightでは単一の`PicoTetris_R5` artifactを再現し、自動周辺機器・
ゲーム診断と67/67キーscenarioを合格させた。同一UF2のPicoCalc実機runも全項目pass、67/67、
`io_errors=0`で一致し、`r5-hardware-20260808-01`へ固定したため、OPT1-Aはpromotedとなった。

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
