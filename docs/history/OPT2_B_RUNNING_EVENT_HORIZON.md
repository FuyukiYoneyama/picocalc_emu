# OPT2-B running event-horizon profiler

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


**状態:** 完了（2026-08-08）  
**backend:** `ac0c3052e6c28fcf235a33f98f3a96470d2966f1`  
**evidence:** [`opt2-b-running-horizon-20260808-01`](../../firmware-validation/records/opt2-b-running-horizon-20260808-01/notes.md)

## 目的

OPT1-Aは両core blocked区間を正確にfast-forwardした。OPT2はCPU running中のper-cycle
orchestrationをまとめるが、CPUまたはdeviceが観測できるeventを越えてはならない。
OPT2-Bは最適化を実装せず、次の限定prototypeを設計するための分布だけを取得する。

## 実装境界

`event-horizon-profiler` featureは`idle-profiler`の保守的horizonと`behavior-trace`のobservable
projectionを再利用する。通常buildにはprofiler state、MMIO latch、集計branchを含めない。
runnerの`--event-horizon-profile <path>`はidle profile、behavior traceと同時指定できない。
出力は必ず次を宣言する。

```json
{
  "instrumented": true,
  "valid_for_wall_time": false,
  "observed_gaps_are_safe_windows": false
}
```

計装runのwall timeを性能値として扱わない。profile ONは境界ごとのprojection比較とcounter更新を
行うため、performance modeを意図的に歪める。

## Boundary分類

各running dispatchの前後で、次のbitを重複を許して記録する。

- `cpu_mmio`: CPUによるperipheral/SIO/PPB MMIO read/write
- `gpio_in`: CPUによるSIO `GPIO_IN` read（`cpu_mmio`にも含む）
- `fifo_dreq`: FIFO/DREQに関係するCPU-visible MMIO（`cpu_mmio`にも含む）
- `irq_exception`: IRQ pending/deliveryまたはexception状態変化
- `pio_device`: GPIO input、PIO output/OE、PSRAM transaction状態変化
- `dma_dreq`: DMA transfer counter変化
- `timer_systick_pwm`: timer alarm stateまたはPWM enable/top/wrap境界
- `serial`: UART/SPI/I2C/ADC observable state変化
- `clock`: `clk_sys`、`clk_ref`、`clk_peri`変化
- `external`: runnerが渡したscenario poll/input/snapshot/stop horizonへの着地

boundary countは重複するため、全categoryの和を`boundary_steps`と比較しない。

## Histogramの意味

全histogramは閾値`K = 1, 2, 4, ...`に対して累積である。

- `episodes_ge[K]`: 長さがK以上のinterval数
- `cycle_mass_ge[K]`: そのinterval群に含まれるcycle総数

`observed_inter_boundary_dispatches`はdispatch数でintervalを分類し、cycle massを保持する。
`observed_inter_boundary_cycles`はcycle長で分類する。`observed_candidate_*`は、各dispatchで
観測boundaryがなく、dispatch前の保守的horizon distanceが消費cycleより大きかった連続区間だけを
同じ二軸で集計する。`candidate_dispatches`と`candidate_cycles`は全candidate intervalの直接合計である。

このcandidate判定はpost-hoc filterであり、未来のCPU MMIOを予測する機構ではない。したがって
実装時はpure instruction/MMIO分類とpre-dispatch event horizonを別途安全条件にしなければならない。

## PicoTetris結果

| item | result |
|---|---:|
| total cycle | 927,528,660 |
| running cycle | 308,932,816 |
| running dispatch | 172,715,307 |
| candidate cycle | 46,411,891 (runningの15.0233%) |
| candidate dispatch | 28,608,173 (running dispatchの16.5638%) |
| candidate interval | 2,388,571 |
| average candidate length | 19.431 cycle / 11.977 dispatch |

PIO/deviceとCPU MMIOが最も多い観測境界だった。保守的horizonを1 cycleへ制限したmassはPIO
217,027,394 cycle、UART 40,197,601 cycle、DMA 5,320,143 cycleである。

candidate cycleが全run virtual cycleの5.0038%であることをwall-time上限と解釈しない。
OPT1-A後はblocked cycleとrunning cycleのhost costが同一でなく、batchしてもCPU decode/executeは
消えない。採否は限定prototypeのtrace OFF A/Bでのみ決める。

## 次の変更単位

OPT2-Cでは、現在の保守的horizon内、かつCPUがMMIOを実行しないと事前に分類できる区間だけを
batchする。次の順序を守る。

1. candidate区間でper-dispatch orchestration costを測る。
2. 小規模prototypeをfeatureまたは独立commitで実装する。
3. cycle/order、behavior全domain、timeline、UART、framebufferをone-cycle referenceと比較する。
4. exactness合格後だけtrace OFF A/Bを10 run行う。
5. 5%改善目安に届かない場合はrevertし、PIO/UART/DMA deadline promotionかOPT3へ進む。
