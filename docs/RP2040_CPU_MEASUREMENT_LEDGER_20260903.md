# RP2040 CPU 性能値台帳

更新日: 2026-09-03

この台帳を、RP2040 CPU 高速化プロジェクトで使う数値の正典とする。CPU単体の
ホストスループット、実アプリのCPU-time差分、PicoCalc全体の実時間比は別の指標であり、
同じ「速度」として足し合わせない。

## 現在、直接測定できているCPU単体値

P1-Aの経路を実際に通るCPU-only `self-invalidate` workloadを、同一ホスト・同一条件で
baselineとcandidateの10 pair比較した。PicoCalcの周辺装置と実アプリfirmwareは含めていない。

| 状態 | 中央値（MHz相当） | 条件 |
|---|---:|---|
| baseline（index-only invalidation） | **124.963556** | backend `d8f5bb22fae221a7a31ae45c953b64b375eeb316` |
| P1-A（full-tag guard） | **142.810288** | backend `58e73010636bb1b60fdb1ccace40db29b5bb96cc` |

- workload: `self-invalidate`、single-core / Serial、CPU 11、unpaced
- 1 run = 1,000,000,000 emulated cycles、10 pair、全pair保持
- paired point estimate: **+15.324225%**
- paired median: **+14.289532%**
- 95% CI: **+12.471306%〜+18.249511%**
- 証拠: [`rp2040-cpu-p1-a-cpu-only-direct-20260903-01`](../firmware-validation/evidence/rp2040-cpu-p1-a-cpu-only-direct-20260903-01/)

ここでの「MHz相当」は、ホスト上でflat-out実行したemulated cycle throughputをMHz表記したもの
であり、RP2040実機のクロックを変更した値ではない。したがって、現在のCPU単体値をこの測定範囲で
一つ答えるなら **P1-A後は142.810288 MHz相当** となる。

250 MHzを分母にした機械的な参考換算は baseline **49.985422%**、P1-A **57.124115%** だが、
これは上記synthetic workloadの補助表示にすぎない。PicoCalc全体の実時間比や、別workloadの
CPU天井を表す値ではない。

## 別スコープの確定値

| 指標 | 値 | 意味 |
|---|---:|---|
| P1-A実アプリ combined raw CPU-time | **+1.218973%** | PicoTetris r10 / PicoEdit r4の等重みA/B。CPU単体MHzとは別 |
| PicoCalc全体の既存実時間比 | **14.636593%** | 周辺装置を含むpromoted workloadの実時間比 |

P1-Aの採用判断は実アプリ combined rawがマイナスでなかったことに基づく。詳細は
[`RP2040_CPU_P1_A_ADOPTION_DECISION_20260903.md`](RP2040_CPU_P1_A_ADOPTION_DECISION_20260903.md)を参照する。

## 111.7 MHz（資料上の旧値）の出典訂正

これまで一部資料に現れた数値は **117 MHzではなく111.7 MHz** である。調査時点で確認できたのは、
2026-08-30作成の分析ノートにある次の記述だけだった。

- `CPU_HOTPATH_MEASUREMENT_20260830.md`: `33.63 host cycles / emulated cycle ≒111.7 MHz`
- `UX_MODE_CONCEPT_20260830.md`: `111.7 / 250 = 44.7%`
- `VRP_DUAL_BUILD_CORRECTION_ADVICE_20260830.md`: CPU単体111.7 MHz、周辺装置ゼロ時44.7%

この111.7 MHzについて、測定コマンド、ホスト識別情報、測定日時、backend/source SHA、raw log、
集計ファイルを特定できなかった。したがって、これは再現可能な実測値でも、RP2040の仕様値でも、
P0で確定した基準値でもない。

ここでいう「歴史的」とは、過去の資料に引用された参考記載という意味である。正式な意味は
**出典未確定の過去記載値**であり、現行の性能比較には使わない。44.680%も、この111.7 MHzを
250 MHzで割った派生値にすぎず、確定済みのCPU基準値ではない。

P0が確定したのは、共通baselineへのadmission、correctness、CPU-time測定経路、null-controlなどの
測定基盤である。P0は111.7 MHzや44.680%を確定していない。

## 今後の表記規則

1. CPU単体を述べるときは、workload名・条件・`MHz相当`を必ず併記する。
2. 実アプリの候補効果はCPU-timeの符号付き%で示し、CPU単体MHzと混ぜない。
3. PicoCalc全体の1倍評価は実時間比で示し、CPU単体の参考換算をその代用にしない。
4. raw logとprovenanceがない旧値は「出典未確定」と明記し、現在値・基準値として再利用しない。
