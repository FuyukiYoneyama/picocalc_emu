# OPT1-B serial fast-path gate

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


**状態:** 正確性・性能gate合格。R5既存実機相関との同値性確認後にpromoted

**backend candidate:** `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`

**target:** `picotetris-opt1b` revision 5

## 目的と変更範囲

OPT1-Bは、1-cycle実行、PIO/GPIO edge、peripheral更新、IRQ配送の順序を変えず、Serial実行の
fast-path可否判定だけを整理する低リスク最適化である。

変更は次の2点に限定した。

1. `pio_all_idle()`を最初に評価し、PIOがactiveなら残るread-only predicateを評価しない。
2. `all_peripherals_idle()`に既に含まれるDMAの重複`is_idle()`を削除する。

PicoCalc workloadではPIO SMが長時間activeであり、その時点でslow pathが必須になる。したがって
後続のIRQ、SysTick、UART/SPI/I2C/ADC/PWM/DMA判定を省いても分岐結果は変わらない。PIOがidleの
場合は従来と同じ全条件を評価する。peripheral tick、event horizon、state更新自体には変更がない。

## 正確性

登録済みPicoTetris BINと`tetris-line-clear` scenarioを、OPT1-A/R5 backend
`612b48510452d4012e4ac6639960ca3983b48f66`と候補backendで比較した。

| 観測 | 一致値 |
|---|---|
| cycle / virtual time | `927,528,660` / `3.715000 s` |
| scenario | 85/85、timeline `50eb1f6c...e2dd1` |
| UART | `bff1f245...e9266c` |
| framebuffer RGB565 | `f63b598f...54e4a2` |
| behavior SHA-256 | `79dedc15...e2dfc8` |
| event stream schema 2 | `2ead2041...4a789`、173,498,680 events |

9 domainすべてでevent数とstreaming SHA-256が一致した。candidate固有のnormalized report SHA-256は
`6c63ab48729684f8391498ff1e1b6486c3a3e19db62c191f0b6637ee29d2d917`である。

追加workloadも次のとおり合格した。

- Template B: 登録BIN `1e6abac...2a3d`、3 runずつ。verdict、UART、framebufferは一致。
- 公式PicoCalc Hello: 登録BIN `925d4a97...4086`、95億cycleを完走。8 MiB PSRAMは
  `8,388,608 / 8,388,608` byte一致、不一致0。UART、framebuffer、keyboard結果も合格。
- R5相関firmware: candidate backendで既存preflightのcycle、timeline、UART、framebuffer、
  device verdictが一致することを確認する。既存の実機recordは変更しない。

unit test、feature別test、CIと同じClippy構成も合格した。trace ONは正確性確認専用で、性能値には
使用していない。

## 性能

主workloadはWSL2、AMD Ryzen 5 5600X、logical CPU 0固定、release、trace OFF、warm-up 1回除外、
10回で測定した。

| 指標 | OPT1-A | OPT1-B | 差 |
|---|---:|---:|---:|
| wall中央値 | 27.122874 s | 25.381594 s | **6.419972%短縮** |
| 実時間比中央値 | 13.696960% | 14.636593% | 6.860156%向上 |
| throughput中央値 | 34.197 Mcycle/s | 36.543 Mcycle/s | 1.068604倍 |

candidate wall平均は25.536005秒、95% CIは`[25.153603, 25.918407]`である。主workloadの5%条件を
満たした。

Template Bはbaseline `[20.48, 20.63, 20.83]`秒、candidate
`[20.78, 20.91, 21.20]`秒で、中央値退行は1.357247%だった。3%上限内である。公式Helloの
622.51秒は全域PSRAMを含む正確性runであり、正式な性能比較には使用しない。

## 採用判断

この変更は挙動を近似せず、read-onlyなAND条件の短絡評価だけを行う。正確性gate、主性能gate、
追加workload非退行gateをすべて満たした。R5診断firmwareでも、すでに実機相関済みのbackendと
同じ観測契約を再現した場合、既存hardware evidenceとの推移的同値性によりpromotedとする。
新しい物理キー操作や写真は要求せず、過去のR5 recordは不変に保つ。

証拠は`firmware-validation/records/opt1-b-20260808-01/`、target attestationは
`firmware-validation/validations/picotetris-opt1b-r5.json`に固定する。
