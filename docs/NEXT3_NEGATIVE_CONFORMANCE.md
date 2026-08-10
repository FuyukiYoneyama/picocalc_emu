# NEXT-3 negative conformance

**状態:** NEXT3-0の契約・KPI schema、NEXT3-1の旧LCD 0.3.1 artifact監査、および
NEXT3-2の明示的fault版buildとuf2loader経由の実機試験まで完了した。旧候補はartifact再現不能、
明示的fault v1は実機FAILしたものの凍結oracleと症状不一致のため、いずれもnegative母数へ採用しない。
エミュレーター初回実行は行わず、hardware-confirmed negative caseは引き続き0件である。原因分析では、
v1が旧write-side CS defectを再現する一方、旧症状を測ったSIO bitbang RAMRD observerではなく6 MHz
hardware SPI observerを使っていたことを主要な未制御変数として確認した。observerを固定するv2事前設計と
A1 baseline実装、clean clone再現、エミュレーターPASS、同一UF2のuf2loader実機PASSを完了した。
positive control gate後、fault Bを許可されたwriter CS境界とidentityだけの差分として実装し、
clean cloneで一致するBIN/UF2/source bundleとoracleを固定した。uf2loader実機先行結果はv1と同じ
rotated-bit症状となり、solid 3色とpattern mismatch数が凍結oracleに一致しなかった。Fault Bも
`inconclusive`、negative母数増分0とし、エミュレーター初回runは行わない。observer差は不一致の
十分条件ではなかった。実機後source gap分析では、旧160x160 tiling、runtime初期化順とactive audio IRQ、
回収不能な旧toolchainを残差として順位付けした。複数の未固定変数を重ねた再試行はせずv2を閉じた。
決定的なSD CMD8 bad-CRC negative候補の実装前契約とA1正常対照を固定した。A1は2 clean buildと
凍結backendのemulator runに合格し、次は同一UF2のuf2loader実機確認である。

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
- uf2loader実機試験: `firmware-validation/records/next3-lcd-cs-fault-v1-hardware-attempt-20260810-01/record.json`
- 実機試験後KPI: `firmware-validation/records/next3-hardware-attempt-20260810-01/kpi.json`
- fault source bundle: `provenance/picocalc-next3-lcd-fault-v1.bundle`
- v2事前契約: `firmware-validation/contracts/next3-lcd-cs-fault-v2.json`
- v2原因分析・設計: `docs/NEXT3_V2_CANDIDATE_DESIGN.md`
- v2 A1 baseline: `firmware-validation/records/next3-v2-a1-20260810-01/record.json`
- v2 A1実機相関: `firmware-validation/records/next3-v2-a1-hardware-20260810-01/record.json`
- v2 Fault B artifact: `firmware-validation/records/next3-v2-b-20260810-01/record.json`
- v2 Fault B source bundle: `provenance/picocalc-next3-lcd-fault-v2-b.bundle`
- v2 Fault B実機結果: `firmware-validation/records/next3-v2-b-hardware-attempt-20260810-01/record.json`
- v2 Fault B実機後KPI: `firmware-validation/records/next3-v2-b-hardware-attempt-20260810-01/kpi.json`
- v2実機後source gap分析: `firmware-validation/records/next3-v2-gap-analysis-20260810-01/record.json`
- SD CMD8 CRC事前契約: `firmware-validation/contracts/next3-sd-cmd8-crc-v1.json`
- SD CMD8 CRC設計: `docs/NEXT3_SD_CMD8_CRC_CANDIDATE.md`
- SD CMD8 CRC A1: `firmware-validation/records/next3-sd-cmd8-crc-a1-20260810-01/record.json`

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

開始時点、0.3.1監査後、明示的fault v1実機試験後のいずれも、hardware-confirmed negative caseは
0件である。したがって
`detection_rate`と`false_accept_rate`はともに`null`、状態は`no_negative_denominator`とする。
これを「検出率0%」「false-acceptance率0%」とは表現しない。

positive側では`hardware_correlation_completed=true`の系列を7件固定した。R5、NEXT-1、
NEXT-2 audio、NEXT-2 multicore、NEXT3 LCD v2 A1、NEXT3 SD CRC A1の6件は直接実機相関、OPT1-Bは
不変R5 recordへの全event同値性による推移的相関である。この7件で
`emulator PASS -> hardware FAIL`は0件だが、negative検出率とは別の指標である。

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

### uf2loader経由の実機結果

一般ユーザーと同じ経路を主試験にするため、同一UF2をSDカードの`pico1-apps`へ置き、uf2loaderの
application menuから起動した。BOOTSELは使用していない。fault版は標準Pico SDK UF2でRP2040 flashを
書き換える処理を持たず、uf2loaderの予約領域にも達しないため、BOOTSEL限定の技術的理由はない。

実機はFAILしたが、保存された結果は凍結oracleと一致しなかった。

- black、whiteのsolid fillはPASS。
- red、green、blueのsolid fillはそれぞれ4 mismatchでFAIL。
- 4 pixel patternは全sampleが`0x7c00`となり、3ではなく4 mismatch。
- `app_status=fail`、SD smokeはPASS。
- 最終markerは20回反復して同一だった。

```text
[NEXT3][LCD_CS_FAULT][EVIDENCE] app_git=d7f0668db17e bsp_git=6bd826e7dcaf-dirty solid=fail pattern=fail mismatches=4 app=fail sd=pass
```

oracleを実測結果へ合わせて変更せず、このattemptを`inconclusive`、negative分母増分0とした。
必須順序のstep 4を満たさないため、同一BINのエミュレーター初回実行は保留する。写真のrepository copyは
GPSを含むEXIF/XMPを削除し、decoded RGB SHAが元画像と一致することを確認した。

## NEXT3-3: v2候補の原因分析と事前設計

旧`5b12a7c`とv1をsource比較した結果、両者のfaulty writerはいずれもCASET、RASET、RAMWR、pixel payloadを
別々のCS Lowで送っていた。一方、旧症状は約500 kHzのSIO bitbang RAMRDで測定され、v1は6 MHzの
hardware SPI RAMRDで測定された。v1はwrite defectだけでなくobserverまで含めた旧測定系の再現には
なっていなかった。この差は確認済みだが、v2実測まではoracle不一致の単独原因とはしない。

v2では正しいwriter＋旧observerをA1、旧faulty writer＋同じ旧observerをB、writerだけを戻したものを
A2とする。変更する独立変数はwrite-side CS framingだけである。旧ログのsolid 5色PASS、pattern
red/red/red/red、3 mismatchを実装前oracleとして固定した。詳細と停止条件は
[`NEXT3_V2_CANDIDATE_DESIGN.md`](NEXT3_V2_CANDIDATE_DESIGN.md)にある。

## NEXT3-4: v2 A1 baseline

独立repository `picocalc-next3-lcd-fault` commit `168a65d9f8206d2767641c589f21f359c1ce7b1b`で、
正しいsingle-CS writerと旧`5b12a7c` SIO bitbang observerを組み合わせた。build timestampは
`2026-08-10T06:00:00Z`、SDKは2.2.0 commit `a1438dff...`、GCC 13.2.1、CMake 3.28.3、
Ninja 1.11.1である。別clean cloneとのBIN/UF2一致を確認した。

- BIN SHA-256: `28c42956d63b162fa6a0487ba82cfcdb1e63fc62b13ce0672c0344cdaf7f5f6c`
- UF2 SHA-256: `ce15219188b35ef54edebfcb6b6df09ec8632145d8e1ce28ea750f2444742c99`

promoted backend `e985a9d`の初回実行はRAMRD count 0でFAILした。これはLCD modelの判定ではなく、
variant AがSPI1 FIFO transferだけをpanelへ届け、SPI deinit後のSIO SCK/MOSI/MISOを接続していなかった
capability gapである。backend `fc4a622`でvariant Aへpin observerを接続し、`4a90864`でbit-level選択中だけ
dummy timingを切り替えてdeselect時にSPI timingを復元し、旧実機証拠どおりRGB666 RAMRDをR,G,B順へ
修正した。既存variant BはRGB565であり、その独立firmware回帰もPASSした。promoted roleは変更していない。

clean backend `4a90864816ef58286f2b292df0e7fe44fbcd4809`のA1 runは700,000,000 cycle、
RAMRD 6回、solid 5色PASS、pattern PASS/mismatch 0、SD PASS、exceptionなし、unsupported MMIO 0で
verdict PASSとなった。recordは`firmware-validation/records/next3-v2-a1-20260810-01/record.json`にある。

同一UF2を一般利用経路のuf2loaderから実機起動した。boot identityはcanonical A1 commitと一致し、
solid 5色、pattern、PSRAM、SDはすべてPASS、最終markerは14回同値だった。写真でもRGB三色、白枠、
上下/status領域を確認した。原写真はGPS付きEXIFを含むため、repository copyだけmetadataを除去し、
decoded RGB SHA一致を確認した。

UART自体はuf2loader経路やUF2 SHAを出力しない。したがって経路はoperator procedure、artifact連続性は
事前UF2 hash、clean clone再現、embedded source/build identity、実行証拠の組合せによる。この限界を
in-band暗号証明とは表現しない。A1 positive control gateは完了した。

## NEXT3-5: v2 Fault B artifact freeze

A1 canonical treeからidentity、evidence marker、`begin_window()`のwrite-side CS framingだけを変更した。
canonical Fault B commitは`3a073fbf206b02993dd80a0a7158c1e3c865efff`であり、A1からのnet tree diffは
`CMakeLists.txt`、`app/main.cpp`、`bsp/vendor/lcd_hwspi_rgb888.cpp`の3 pathだけである。
SIO bitbang observer、test coordinates、expected colours、sample count、colour conversion、backendは
変更していない。

同じbuild timestamp `2026-08-10T06:00:00Z`でcanonical treeと別clean cloneをbuildし、次を固定した。

- BIN SHA-256: `f9f5a347c36b38fbcb93967cd6a6bcd7caafb8d19805d235e0bfc7a27c5a18a4`
- UF2 SHA-256: `8f45245d8b0c8f1d543d1f909368ca4c48438e898352b48c3afcdaa172cb291f`
- source bundle SHA-256: `876a1889897517d01a18ee813922a725f602c52df988627b8eccaf1b71534de0`

Fault Bはまだエミュレーターで実行していない。一般利用経路のuf2loaderで実機を先行し、solid 5色PASS、
pattern `red/red/red/red`・3 mismatch、`app=fail`、`sd=pass`の全fieldが一致した場合だけ、backend
`4a90864816ef58286f2b292df0e7fe44fbcd4809`で同一BINの初回runを解禁する。1 fieldでも違えば
`inconclusive`として保存し、oracleは変更せず、エミュレーターを実行しない。

## NEXT3-6: v2 Fault B hardware result

canonical Fault B UF2をuf2loaderから実機起動した。boot identityはcommit `3a073fb`、BSP
`6bd826e7dcaf-dirty`、build timestamp `2026-08-10T06:00:00Z`と一致し、最終markerも15回同値だった。
しかしLCD実測は凍結oracleへ一致しなかった。

- black、white solidはPASS。
- redはraw/value `7c8000`/`7c00`、greenは`007c80`/`03f0`、blueは`80007c`/`800f`で、各4 mismatch。
- patternは`7c8000`/`7c00`×4、4 mismatch。
- `app=fail`、`sd=pass`。

この値はv1実機結果と同じである。historical SIO observerへ固定してもv1症状が変わらなかったため、
observer差だけでは旧`5b12a7c` oracleとの差を説明できない。結果を後付けoracleにせず、v2 Bも
`inconclusive`、negative denominator増分0とした。negative候補監査は3件、artifact audit failure 1件、
inconclusive 2件、hardware-confirmed negative case 0件であり、率は引き続き`null`である。

Fault Bのエミュレーターrunは未実行で、今後もこの候補では実行しない。UARTに残った
`window_cs=held_from_caset_through_ramwr`はA1由来の古い説明で、canonical B sourceと矛盾するため
writer modeの証拠から除外した。source commitとA1→B diffが実際のCS-separated writerの正典である。

## NEXT3-7: v2実機後source gap分析と候補切替

旧`5b12a7c`と現行Fault Bを再比較し、次を確定した。

- v1 hardware-SPI observerとv2 historical-SIO observerは、現行runtimeで同一のrotated-bit値を返した。
  observer差は旧oracle不一致の十分条件ではない。
- 最大のsource差は、旧`fill_rect()`が最大160x160 tileごとにwindow/CS境界を作り、現行Bが矩形全体を
  1 windowにする点である。
- 旧runtimeにはPSRAM probeとaudio DMA/PWMがなくLCD init直後に検証した。現行runはaudio IRQが動作中である。
- 旧SDK commit、toolchain、BIN、UF2は回収不能であり、同一artifactとして追加変数を完全には固定できない。
- GPIO初期化の細部にも差はあるが、SIO setupと観測idle levelは一致し、優先度は低い。

この分析は原因候補を順位付けするが、歴史的artifactの同一性を新たに証明しない。tiling、runtime、toolchainを
重ねて旧症状へ合わせることはpost-hoc oracle fittingになるため行わない。v2は`inconclusive`で閉じ、Fault B
emulator runは禁止、oracle不変、negative母数0のままとする。

## NEXT3-8: SD CMD8 CRC候補の事前設計

タイミング依存のLCD観測を離れ、SD SPI CMD8 CRCを使う決定的なnegative caseの実装前契約を固定した。
CMD8はCRC検査が常時有効である一方、backend `4a908648`はCRC byteを捨てる。A1は正しい`0x87`、Bは
CRCだけを`0x85`へ変え、実機R1=`0x09`のCRC errorをhardware-firstで確認する。filesystemへはアクセスせず、
通常の実機操作はuf2loaderからA1とBを各1回起動する2回だけである。詳細は
[`NEXT3_SD_CMD8_CRC_CANDIDATE.md`](NEXT3_SD_CMD8_CRC_CANDIDATE.md)に固定した。

## NEXT3-9: SD CMD8 CRC A1正常対照

A1を独立repository `picocalc-next3-sd-crc-fault` commit `f942b8eb0008`へ実装した。applicationは
canonical CRC `0x87`で`sdcard::init()`だけを行い、filesystem、キー、audio、PSRAMを試験範囲へ入れない。
source本体と別clean cloneのBIN `0ae9eea0...fce1b`、UF2 `be9c0e8d...a9ffd`は完全一致し、source bundleも
`ed985de5...a05da`へ固定した。

凍結backend `4a908648`の同一BIN runはCMD0 R1=`0x01`、CMD8 arg=`000001aa`／CRC=`0x87`／
R1=`0x01`／R7=`000001aa`、init PASSとなった。SD block read/writeは0、exception、unsupported MMIOも0、
最終画面までPASSした。記録は`firmware-validation/records/next3-sd-cmd8-crc-a1-20260810-01/`にある。

同一UF2のuf2loader実機runもPASSした。boot identityはcanonical sourceと一致し、CMD0
arg=`00000000`／CRC=`0x95`／R1=`0x01`、CMD8 arg=`000001aa`／CRC=`0x87`／R1=`0x01`／
R7=`000001aa`、init、appがすべてPASSした。完全なEVIDENCE markerは39回同一で、最終写真もPASS表示に
一致した。実機記録は
`firmware-validation/records/next3-sd-cmd8-crc-a1-hardware-20260810-01/`にある。

positive相関は7系列、`emulator PASS -> hardware FAIL`は0のままである。A1はpositive controlなので
negative母数は0のまま、率は`null`である。Fault B source実装は解禁したが、そのBINのemulator runは
凍結hardware oracle一致まで禁止する。次はA1からidentity、EVIDENCE marker、CMD8 CRC `0x87 -> 0x85`
だけを変えたFault B artifactの固定である。

## NEXT3-10: SD CMD8 CRC Fault B artifact freeze

Fault Bをcommit `e78cabbe2041`へ実装した。A1からの実行差分はidentity、EVIDENCE namespace、送信CMD8
CRC `0x87 -> 0x85`、expected trace CRC identityだけである。expected trace側も変えるのは、applicationの
self-rejectionではなくbackendがbad CRCを受理するかを測るためである。その他のprotocol、filesystem、key、
backendは不変で、change-budget auditはPASSした。

source本体と独立clean cloneのBIN `6665ca51...9bd0`、UF2 `43ea1098...e958`は一致し、完全source bundle
`3e3fded8...739a`を固定した。Bはまだemulatorで実行していない。negative母数は0、positive相関7系列の
ままである。次は同一UF2をuf2loader実機で先行実行し、凍結oracleへ全field一致した場合だけ初回backend
runを解禁する。

## CI運用

NEXT-3のbuild、schema検証、emulator runはローカルで行う。通常の試行錯誤にGitHub Actionsを
使わず、中間pushもしない。workflowの変更やCI実行が必要になった場合は、実行前に理由と見込使用量を
説明して許可を得る。
