# NEXT-3 negative conformance

**状態:** NEXT3-0の契約・KPI schema、NEXT3-1の旧LCD 0.3.1 artifact監査、および
NEXT3-2の明示的fault版の再現可能buildまで完了した。旧候補は再現性と同一artifact実機証拠を
満たさずnegative母数へ採用しない。fault版も、同一UF2の実機FAILを確認するまではnegative母数へ
入れず、契約どおりエミュレーター初回実行を保留する。

## 目的

positive conformanceは「エミュレーターPASS、同一artifact実機PASS」を確認する。NEXT-3は逆向きの
判別能力、すなわち「実機で既知の理由によりFAILする同一artifactを、エミュレーターも同じ理由で
FAILにする」を検査する。単にエミュレーターが何らかの理由で停止しただけでは合格にしない。

正典となる機械可読ファイルは次である。

- 契約: `firmware-validation/contracts/next3-negative-conformance-v1.json`
- case schema: `firmware-validation/negative-conformance-case.schema.json`
- KPI schema: `firmware-validation/negative-conformance-kpi.schema.json`
- NEXT3-0開始時点: `firmware-validation/records/next3-0-20260810-01/kpi.json`
- 0.3.1監査後: `firmware-validation/records/next3-1-20260810-01/kpi.json`
- 明示的fault build: `firmware-validation/records/next3-lcd-cs-fault-v1-20260810-01/record.json`
- fault build後KPI: `firmware-validation/records/next3-fault-build-20260810-01/kpi.json`
- fault source bundle: `provenance/picocalc-next3-lcd-fault-v1.bundle`

## 分類

| 分類 | 条件 | negative母数 | 正検出 |
|---|---|---:|---:|
| `correct_negative_detection` | 実機FAIL、emulator FAIL、理由一致 | +1 | +1 |
| `false_accept` | 実機FAIL、emulator PASS | +1 | 0 |
| `wrong_reason_failure` | 両方FAILだがemulatorの理由がoracleと無関係 | +1 | 0 |
| `artifact_not_reproducible` | source/toolchain/BIN/UF2を固定できない | 0 | 0 |
| `inconclusive` | 証拠不足で上記を判定できない | 0 | 0 |

`wrong_reason_failure`は見かけ上FAILでも検出成功ではない。unsupported MMIO、exception、cycle limit、
UART採取漏れなど、凍結oracleと無関係な理由だけでFAILした場合はここへ分類する。

## KPIの分母

negativeの分母は`hardware_confirmed_negative_cases`だけである。候補を見つけただけ、古い文書にFAILと
書かれているだけ、emulatorだけでFAILしただけでは分母へ入れない。

開始時点と0.3.1監査後のいずれも、hardware-confirmed negative caseは0件である。したがって
`detection_rate`と`false_accept_rate`はともに`null`、状態は`no_negative_denominator`とする。
これを「検出率0%」「false-acceptance率0%」とは表現しない。

positive側では`hardware_correlation_completed=true`の系列を5件固定した。R5、NEXT-1、
NEXT-2 audio、NEXT-2 multicoreの4件は直接実機相関、OPT1-Bは不変R5 recordへの全event同値性による
推移的相関である。この5件で`emulator PASS -> hardware FAIL`は0件だが、negative検出率とは別の指標である。

## caseの必須順序

1. 正常版についてemulatorと実機のPASSを固定する。
2. fault版のsource、SDK commit、toolchain、build timestamp、BIN/UF2 SHAを固定する。
3. emulator実行前に、期待する実機症状と除外する無関係FAILをoracleへ固定する。
4. 同一buildのUF2を実機で実行し、oracleどおりのFAILを確認する。
5. 同じbuildのBINを凍結backendで一度実行し、PASSでもFAILでも初回結果を保存する。
6. 両結果の理由を比較して分類する。
7. 欠陥だけを直した版についてemulatorと実機のPASSを固定する。

## NEXT3-1: LCD 0.3.1監査結果

最初の候補はA系統`hwspi-rgb888`のCS保持欠陥だった。文書にはsource
`51380fa836e58373d1747904d46b28307ac65fa2`、UF2 SHA-256
`ae182a6947e46ee9f927e5dfc1b539a448b45f846cd5935eb69c9782dd802c4f`が残る。
しかし監査の結果、この組合せをnegative caseとして採用できないことが分かった。

- 当時の文書自身が、このUF2の実機判定を「未確認」としている。
- UF2本体、BIN SHA、完全build logは保存されていない。
- CIはPico SDK branch `2.0.0`を使ったが、SDK commitを記録していない。
- aptで入れたcompiler/binutils/CMakeの版、CMake generatorを記録していない。
- 当時のbuild toolは現在UTC時刻をfirmwareへ埋め込み、その値を記録していない。
- solid-fill PASS、4色pattern FAILを示す既存ログのboot identityは`5b12a7c`であり、
  文書化された`51380fa` artifactと同一ではない。

したがって`51380fa`候補は`artifact_not_reproducible`、negative分母への増分0とした。監査recordは
`firmware-validation/records/next3-lcd-031-audit-20260810-01/record.json`にある。古いFAILログを
無理に同一artifact証拠として扱わない。

## NEXT3-2: 明示的fault版

現行の実機PASS済みLCD版をbaselineとし、loader-style transactionのうち
「CASET/RASET/RAMWRから画素payloadまでCS Lowを保持する」条件だけを壊す。fault版は通常buildへ
混入しない独立Git repository `picocalc-next3-lcd-fault`へ分離した。baseline commit
`5e5e7e998cabea9861676700ec16d412ddfec8eb`に対し、fault source commitは
`d7f0668db17e74dfa94d10458487e627a880c4bc`である。変更はfirmware identity、USB CDCへ1秒ごとに
再掲する証拠marker、および`lcd_hwspi_rgb888`の`begin_window` CS framingに限定する。

実装前oracleは次である。

- 5色solid-fill readbackはすべてPASSする。
- red/green/blue/whiteの4 pixel patternはred/red/red/redとして読まれる。
- pattern mismatchは3、`app_status=fail`となる。
- exception、unsupported MMIO、cycle limit、UART不足は0である。

この厳密な症状を実機で再現できなければ、fault版はnegative母数へ採用しない。別のFAILへ期待値を
合わせることもしない。

### 固定build

build入力を次へ固定した。

- generator/source: `picocalc_emu` commit `6bd826e7dcaf7b62f9633dc02552c032e65d9cee`
- Pico SDK: 2.2.0 commit `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`
- toolchain: arm-none-eabi-gcc 13.2.1、CMake 3.28.3、Ninja 1.11.1
- CMake generator: Ninja
- build timestamp: `2026-08-10T00:00:00Z`
- LCD variant: `hwspi-rgb888`

repository本体と別のclean cloneで同じコマンドを実行し、BINとUF2が一致した。

```sh
python3 ../picocalc_emu/tools/picocalc.py build \
  --project . \
  --sdk ../pico-sdk \
  --picotool-dir /usr/local/lib/cmake/picotool \
  --lcd-variant hwspi-rgb888 \
  --jobs 2 \
  --build-timestamp 2026-08-10T00:00:00Z \
  --generator Ninja
```

固定artifactは次である。

- BIN SHA-256: `7ffc6335b3d65276f173954244c8eb481201c9805c6904f192b7b62ea87a5f0f`
- UF2 SHA-256: `74aa594d86666103f947b1905dafb25fd57cd6c49bf3397a9fb340d577c1d6c0`
- source bundle SHA-256: `8824baed4577441da7d58b3a52502c8a7392e029e2bfb53cbfddd4912b7b4ad6`

### 実機確認の境界

次に行うのは同一UF2の実機確認だけである。キー操作は不要で、USB CDCは起動後に接続してもよい。
最終証拠markerを1秒ごとに再掲するため、接続が遅れてboot logを失っても同じ起動を再実行する必要はない。
次のmarkerを含むUART logと最終画面写真を保存する。

```text
[NEXT3][LCD_CS_FAULT][EVIDENCE] ... solid=pass pattern=fail mismatches=3 app=fail sd=pass
```

別の結果が出た場合は結果を保存し、oracleを結果へ合わせて変更しない。実機でoracleどおりFAILした後に
限って、同一buildのBINを凍結backendで初回実行する。

## CI運用

NEXT-3のbuild、schema検証、emulator runはローカルで行う。通常の試行錯誤にGitHub Actionsを
使わず、中間pushもしない。workflowの変更やCI実行が必要になった場合は、実行前に理由と見込使用量を
説明して許可を得る。
