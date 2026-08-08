# OPT1-A exact idle fast-forward

**状態:** candidate完了、R5実機相関待ち

**backend:** `picoem-picocalc` `c68c58f6c37fb31eb9313566c8b16883db9063b6`

**target:** `picotetris-opt1a` revision 3
**証拠:** [`firmware-validation/records/opt1-a-20260808-01/`](../firmware-validation/records/opt1-a-20260808-01/)

## 目的と採用境界

OPT1-Aは、両coreがhaltまたはWFEで停止している区間だけを、次の観測可能eventへ等価に進める。
CPU実行、PIO/DMA等の未証明な自律処理、wake可能なpending IRQを高速化対象へ混ぜない。

PicoCalc runnerは次のscenario pollまたはcycle limitを外部境界として`step_until()`へ渡す。
内部horizonはTIMER alarm、PWM wrap、外部境界の最小値である。長距離のexact horizonをまだ
持たないactive sourceは1 cycle fallbackとなる。長いjumpを許すのは全sourceがquiescent、静的、
または既存のbulk tickでexactと証明された場合だけである。

境界での処理順は、master clock更新、peripheral bulk tick、IRQ route、wake checkを維持する。
通常の`Emulator::step()`契約は変えず、最適化は明示的な`step_until()`利用時だけ有効になる。

## behavior trace schema 2

初回比較で、schema 1のUART eventがguestの挙動ではなく、host harnessによる256 stepごとの
diagnostic log回収に依存していることが判明した。fast-forwardはstep call数を減らすため、同じ
UART byte列でも回収batchの分割が変わっていた。

schema 2はUARTDRへ受理された各byteを独立したbehavior tapへ記録し、host diagnostic drainから
分離する。PWMがbulk advanceでちょうど一周して同じcounter値へ戻る場合も、到達したwrap境界を
明示してeventを失わない。旧schema 1 recordは時点証拠として変更しない。

one-cycle referenceと候補の全走行比較では、behavior projection、全9 domainのevent件数/hash、
総合stream hashが一致した。

| 項目 | schema 2結果 |
|---|---:|
| behavior SHA-256 | `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8` |
| event stream SHA-256 | `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789` |
| event数 | 173,498,680 |
| reference/candidate | 全domain一致 |

## 正確性と性能

PicoTetrisは従来と同じBIN/scenarioで85/85、927,528,660 cycle、3,715,000 us、UART、画面、
timelineが一致した。trace OFFの10 runはreport/UART/PNGがすべて決定的に一致した。

同一WSL host、CPU 0、release、warm-up 1回除外、10 runの測定結果は次のとおり。

| metric | R5 preflight baseline | OPT1-A | 改善 |
|---|---:|---:|---:|
| wall time中央値 | 63.2470 s | 27.1229 s | 57.116%短縮 |
| 実時間比中央値 | 5.8738% | 13.6970% | 2.3319倍 |
| emulated cycle/s中央値 | 14.665 M | 34.197 M | 2.3319倍 |

これはcandidate gateの合格である。実機と同じ結果であることの正式なpromotionはR5相関後に行う。

## 再現

```bash
python3 tools/picocalc.py test --mode firmware \
  --target picotetris-opt1a \
  --firmware /path/to/PicoTetris.bin \
  --backend-dir /path/to/picoem-picocalc

python3 tools/benchmark_firmware_realtime.py \
  --target picotetris-opt1a \
  --firmware /path/to/PicoTetris.bin \
  --backend-dir /path/to/picoem-picocalc \
  --cpu 0 --warmup 1 --runs 10 \
  --json /tmp/opt1a-realtime.json
```
