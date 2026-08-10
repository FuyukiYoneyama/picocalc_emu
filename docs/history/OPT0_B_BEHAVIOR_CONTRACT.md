# OPT0-B behavior / streaming event契約

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


**状態:** 完了  
**実装backend:** `picoem-picocalc` `763595fedefa08886b41298be79bff69324ac51f`  
**証拠:** [`firmware-validation/records/opt0-b-20260808-01/`](../../firmware-validation/records/opt0-b-20260808-01/)

## 目的

backend commitや出力pathが変わっても、同じBIN・scenario・device設定で観測可能な挙動が同じかを
比較できるようにする。既存のschema 8 normal reportと`normalized_report_sha256`はprovenanceを
含む完全証拠として維持し、OPT0-Bは別のdiagnostic artifactを追加する。

## 実行モード

correctness modeはfeatureを明示してbuildし、`--behavior-trace`でartifactを指定する。

```bash
cargo build --locked --release -p picocalc-harness --features behavior-trace
target/release/picocalc-run \
  --bin /path/to/PicoTetris.bin \
  --board picocalc --lcd-variant pio-rgb565 --quantum 1 \
  --cycles 8000000000 --psram --keyboard --sd --sd-format fat32 \
  --scenario /path/to/scenarios/tetris-line-clear.json \
  --snapshot-dir /tmp/opt0-b-snapshots \
  --expect-stop scenario_done \
  --expect-uart '[TETRIS] start' \
  --expect-uart '[TETRIS] cleared=' \
  --expect-uart 'score=1400 lines=13' \
  --json /tmp/opt0-b-report.json \
  --behavior-trace /tmp/opt0-b-behavior.json
```

performance modeは`behavior-trace` featureを付けずにbuildし、`--behavior-trace`も渡さない。
featureが無いbuildにはhash stateもhot-path branchも存在しない。trace artifactは
`mode=correctness_trace_on`、`valid_for_wall_time=false`を必ず記録し、性能値として利用しない。

## canonical event framing

各eventは次のbyte列をSHA-256へ逐次投入する。event配列は保存せず、全体とdomain別のhash state、
64-bit event countだけを保持する。

```text
"PICOEM-EVENT\0"
|| schema_version:u32(be)
|| domain:u8
|| source:u16(be)
|| cycle:u64(be)
|| payload_length:u32(be)
|| payload
```

schema 1のdomainは`clock`、`irq_exception`、`pio_gpio`、`psram`、`lcd`、`dma_dreq`、
`timer_pwm`、`serial_bus`、`scenario_input`である。PicoCalc harnessはboard wiringを宣言し、
PIO0 edgeをLCD、PIO1 edgeとGPIO input edgeをPSRAMへ振り分ける。汎用RP2040 coreには
PicoCalc固有のpin配置をhard-codeしない。

- clock: sys/ref/peri clock transition
- irq_exception: bus/NVIC pendingと両core exception stateの遷移
- pio_gpio: deviceへ割り当てていないPIO/GPIO edge
- psram: PIO/GPIO wire edge、CS/byte/transaction counter遷移
- lcd: PIO wire edge、終了時のpath-free panel/framebuffer snapshot
- dma_dreq: channel transfer counter遷移
- timer_pwm: alarm arm/fire期限、pending、PWM enable/top/wrap境界
- serial_bus: UART byte/FIFO、SPI FIFO/shift、I2C transaction/state遷移
- scenario_input: scenario poll/input適用cycleと最終status

IRQのlevel信号を毎cycle新規assertとして数えない。NVIC/exception stateの遷移とsource domainの
boundaryを組み合わせる。時間とともに増えるPSRAM tickやserial divider accumulatorもevent条件に
せず、pin、FIFO、transaction、比較一致など観測可能な境界だけを記録する。

## `behavior_sha256`

artifact schema 1はnormal reportから明示allow-listでcanonical projectionを作り、sorted JSON bytesを
SHA-256へ入力する。projectionにはBIN/bootrom SHA、execution/device設定、quantum、stop/cycle、
verdict、unsupported MMIO、UART、framebuffer、LCD、PSRAM、SD、keyboard、PWM、PIO、scenarioの
path-free結果、event traceを含める。

backend commit・dirty state、host path、firmware/bootrom/scenarioのbasename、snapshot PNG名、
wall-clock値は含めない。backend provenanceはartifact外側の`backend_build`へ記録する。
scenario内容はbasenameではなくfile SHA-256で入力契約に含める。provenanceだけを変更して
projectionが不変であること、cycleまたはscenario SHAを変えるとprojectionが変わることをunit testで
固定している。

## PicoTetris受入結果

clean backend `763595f...`と登録済みPicoTetris BIN/scenarioを2回実行し、normal report、behavior
artifact、UARTがそれぞれbyte-identicalだった。trace OFF production binaryのnormal reportもtrace
ON時とbyte-identicalだった。

| 項目 | 結果 |
|---|---|
| verdict / scenario | `pass`、85/85 |
| cycle / virtual time | `927,528,660` / `3,715,000 us` |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer SHA-256 | `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2` |
| `behavior_sha256` | `3ee0dff39b10b5863aa28326189f70ba553e714c1e9ada403db1ad4622a1daf3` |
| event stream SHA-256 | `448b0a00575b6748445906a5863c508f2fb86910fba73137605d66147bd191d9` |
| total events | `173,498,252` |

このartifactは現在の正確性baselineを固定するものであり、実機相関の代用ではない。OPT1-A候補は
このbehavior/domain契約と従来のnormal report契約をすべて維持して初めてR5へ進める。

## 後継schema

この文書とrecordはschema 1の時点証拠として変更しない。OPT1-Aの比較でUART source 1がhost側の
diagnostic drain cadenceに依存することが判明したため、backend `c68c58f...`は各UARTDR writeを
独立eventにするschema 2へ更新した。理由、one-cycle referenceとの全domain一致、新しいhashは
[`OPT1_A_EXACT_IDLE_FAST_FORWARD.md`](OPT1_A_EXACT_IDLE_FAST_FORWARD.md)に記録している。
