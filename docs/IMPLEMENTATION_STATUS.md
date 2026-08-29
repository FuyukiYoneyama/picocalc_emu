# 現在の実装状況

この文書は現在値だけを示します。実装経緯や当時の「次の作業」は
[`history/`](history/README.md)へ分離しています。

更新日: 2026-08-29

## 版とbackend

| 項目 | 現在値 |
|---|---|
| Canonical BSP source | 0.9.0 |
| 標準機能の実機相関baseline | 0.8.8 |
| template app版 | `0.8.4-*`（BSP版と独立） |
| 推奨LCD | `pio-rgb565` |
| SD既定 | FAT32。FAT16は明示profile |
| 正確性基準 | Firmware backend `ExecutionModel::Serial` |
| 通常promoted backend | `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`（OPT1-B） |
| 実機相関済みR5 backend | `612b48510452d4012e4ac6639960ca3983b48f66`（不変証拠） |
| backend開発main | transientなbranch headであり、正確性の権威ではない。各targetの固定commitを使用 |

targetはそれぞれ正確なbackend commitを固定します。branch headやローカルmainを自動採用しません。

## 利用できる経路

### Canonical BSP

- 実機確認済みのLCD A/B、keyboard、SD/FatFs、PSRAM、audio API
- 通常アプリの変更範囲を`app/`へ限定
- source fingerprint、board profile、reference evidenceの検査
- FAT32/FAT16共有filesystem API。PicoEditでFAT32同一artifact相関済み
- 音声DMA channel/timer枯渇をpanicにせず`init()==false`で返し、部分claimをrollback
- 生成projectのBSP tree provenanceをCLI buildと直接CMakeの両方で照合

### Host backend

- framebuffer、keyboard FIFO、PSRAM、RAM-backed SD
- deviceと同じfilesystem sourceをネイティブ実行
- 仮想時刻と決定的な繰り返し検査
- hardware-freeなアプリロジックの高速試験

### Firmware backend

- Pico SDK BINのdirect boot、XIP、UART0、exception、unsupported MMIO
- A/B LCD、PIO、DMA、PSRAM、keyboard controller、SPI SD
- scenario、途中snapshot、fail-closed schema 8 verdict
- exact idle fast-forwardとOPT1-B fast path
- target registryとversioned validation
- 外部project用quality gateで、audio観測とoracle評価を`not_evaluated/pass/fail`へ分離
- schema 8を維持した独立audio解析artifact、非正規化raw WAV、schema 3 project契約により、
  控えめな区間音量をadvisory、極端なPWM rail張り付きをFAILとして分離
- 複数firmware run用のstderr heartbeat（`picocalc-run`の明示pair、`picocalc.py test --mode firmware`
  の既定10秒、run ID、finish exit、artifact分離手順）。heartbeatはreport／verdict／hashへ入らない

### Validated Realtime Preview（VRP-0〜VRP-4実装完了、formal gate／VRP-5以降未完了）

Firmware backendでPASSした同一raw BINと、validationで実際に使ったbyte-identicalな
`picocalc-run`だけをwall-clock 1倍目標で対話観測する提案があります。2026-08-29時点では
VRP-0のcontract／fixture、WSLg host capability probe、2 workloadのprovenance／GUIなしbaselineに加え、
VRP-1のreceipt生成と共通admission（参照artifactの再hash、registry／validation record／backend clean
pinの再検証、admitted descriptor出力）が固定済みです。backend側には`--preview-api`の固定PCRP
IPC、UART0 TX/RX、RGB565 frame、reset/quit、pacer status、fail-closed入力、`src/session.rs`への
MachineSession共有分離、UART／framebuffer／unsupported-MMIO／audio-sinkのversioned observation
projectionとcanonical digestが実装されています。board-backed synthetic UART fixtureのbatch／machine／preview三者を
同一cycleで比較するreport-compatible observation digest smoke gate（初期RGB565 LCD frameを含む）に加え、
VRP-2-aでは現行backendを固定した`picotetris-opt1b-vrp2` revision 6と`picoedit-r1-vrp2` revision 2を
追加し、両targetのreceipt生成・registered target admissionまでローカルで確認しました。VRP-2-bでは
admitted descriptorのlaunch contractを再検証して、同じrunnerをspawnするheadless consumerの
hello／status／quit smoke gateを追加しました。VRP-2-cでは既存machine API 7 operationを含む8交換のgolden JSONL transcriptを実runnerで再生し、応答とsnapshotを完全一致させました。VRP-2-dではrepository-ownedのUART echo fixtureでRX accepted 16 byte、17 byte目のFIFO overrun、方向付きcounter、RX disabled拒否を確認しました。`preview-digest-gate`の実装とfake-target検査に加え、2026-08-29にclean backend・実BIN・fresh complete audio reportを用いたVRP-2-e実target gateを2つのversioned targetで完了しました。四者projection digest、timeline、終端cycle、report checksが一致し、証拠は[`validated-realtime-preview/VRP2E_REGISTERED_DIGEST_GATE_20260829.md`](validated-realtime-preview/VRP2E_REGISTERED_DIGEST_GATE_20260829.md)と`firmware-validation/records/vrp2-f-*/`にあります。
VRP-3では、admitted descriptorを再検証して同一runnerを子process起動するTk薄型GUI、提示画像から作った
PicoCalc skin、320x320 RGB565 LCD合成、自動UART0 console、UART text/raw RX、キーdown/held/upとOS
auto-repeat抑止、F5 reset、Ctrl+Rの再admission reload、F12 screenshot、sticky UX-invalid表示を実装し、
WSLgで本体window／UART windowの起動とclean shutdownを確認しました。VRP-4ではbounded PCM tap、非同期
runner output、bounded frontend／host queue、可変source rateのstateful resampling、player／queue／IPC／ingress
dropの分離counter、`stream_epoch`付きresetを追加しました。host playerが無い場合は`timing-only`、transport
が破綻した場合は`degraded`として表示し、emulated audio sink／cycle／UART／framebuffer／validation digestから
分離しています。詳細な実装記録は
 [`validated-realtime-preview/VRP3_GUI_20260829.md`](validated-realtime-preview/VRP3_GUI_20260829.md)と
 [`validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md`](validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md)、
skinの由来・SHA・校正は[`../assets/preview/README.md`](../assets/preview/README.md)を参照してください。
VRP-4のlocal実装は完了していますが、同一registered targetでmonitor off/on/forced-dropの3条件を比較した
versioned evidenceとformal audio-monitor qualificationは未完了です。1倍qualificationも未実装です。したがって
現行capabilityにpreviewやrealtime 1倍を追加せず、既存machine APIをrealtime previewと呼び替えません。VRP-1の旧backend heartbeat互換を含む実装記録は
[`validated-realtime-preview/VRP1_RECEIPT_ADMISSION_20260828.md`](validated-realtime-preview/VRP1_RECEIPT_ADMISSION_20260828.md)、実施順序と安全gateは
[`VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md`](VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md)
を正典とします。VRP-2-c/dの証拠は[`validated-realtime-preview/VRP2CD_MACHINE_UART_20260829.md`](validated-realtime-preview/VRP2CD_MACHINE_UART_20260829.md)に、VRP-2-eの境界は[`validated-realtime-preview/VRP2E_REGISTERED_DIGEST_GATE_20260829.md`](validated-realtime-preview/VRP2E_REGISTERED_DIGEST_GATE_20260829.md)に固定しました。previewの初期workloadは`picotetris-opt1b`（baseline revision 5）と`picoedit-r1`（baseline revision 1）で、VRP-2-eの受入descriptorはそれぞれrevision 8／4へversionedされています。
正式な`realtime-1x-qualified`昇格には、別途作成する再配布可能なNES-class target（VRP-NES-0）が必要です。
VRP-0の正典fixtureは[`docs/validated-realtime-preview/`](validated-realtime-preview/)にあり、VRP-3 GUIは
Python標準ライブラリTkで実装したため`winit`／`cpal`はproduction dependencyへ追加していません。

### 範囲を固定して対応済み

- NEXT-2A: core 1 launch、双方向SIO FIFO、WFE/SEV、core-local SIO IRQ
- NEXT-2B: 48 kHz stereo、固定DMA timer／PWM sliceの凍結digital sample sink。加えて同じPWM5_CC経路では、
  可変timer分数とDMA block長を診断目的で観測し、実効rateの解析artifact／WAVを出力できる
- NEXT-3: CMD8 mandatory CRC7 errorの実機・emulator negative conformance
- NEXT-4: JSONL schema 1の`run`／`step`／`run_until`／`input`／`observe`／
  `subscribe`／`snapshot`

これらは凍結targetで証明した範囲です。似たworkload全般へ自動的に一般化しません。

## I2C-EXT（E0〜E6完了、optional profileをbounded capabilityとして昇格）

任意の外付けI2C moduleをfirmware backendへ接続する計画として、
[`I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)
を固定した。初期対象はPicoCalcの共有I2C1（GP6/GP7）にあるDS3231、AT24C32、AHT20、BMP280で、
既存keyboard controllerとの共存を必須にする。

環境sensorのemulation capabilityは`i2c-external-rtc-env-v1`として昇格済みである。ただしこれは
明示的に選択したoptional profileに限るbounded capabilityであり、標準PicoCalcへ無条件には適用しない。
profileなしの通常runを変えず、E0でsource/provenanceと
wire contractを固定し、E1ではcontroller address-phase契約、mux、data-NACK伝播、共有
virtual-time抽出を実装し、DS3231/AT24C32/AHT20/BMP280の独立model coreと、任意の
picocalc-rtc-v1／picocalc-rtc-env-v1 profileのfixture検証・I2C1 attachを追加した。E4ではschema 2の
詳細sidecar（transaction digest、device state、protocol error）と`picocalc.py` target contract接続を追加した。
E0の証拠は
[`firmware-validation/evidence/i2c-ext-e0-20260823-01/`](../firmware-validation/evidence/i2c-ext-e0-20260823-01/)。

E5 emulator回帰は、cleanな`RTC/Picocalc_Clock` source（commit `f04982cf1d1bf24e3020d992a5f63961c6c8536c`）から
生成した同一BIN/UF2、fixture `i2c-ext-e5-env-v1`、backend `f810d059958773d1b42a1c6d03cc15183cdc1a4f`で
3回実行し、primary report、I2C schema 2 sidecar、UART、framebufferがすべてbyte一致した。
E6のversioned validation `picocalc-clock-i2c-env-e5-r1` は active target
`picocalc-clock-i2c-env-e5` として固定済みである。E5の同一UF2実機UART証拠は
[`firmware-validation/evidence/i2c-ext-e5-20260823-01/hardware-uart.log`](../firmware-validation/evidence/i2c-ext-e5-20260823-01/hardware-uart.log)
に保存し、startup probe、AHT20、BMP280の成功を確認した。

## 完了済み計画（U0〜U6／M-NESCO拡張／SD-GEN-1 P0〜P5）

SD RAW image、flash erase/program、`M-NESCO-S1`（`Picocalc_NESco`のdirect-boot debug開始）を完了した。
host側の標準SD pack／extract（U3-A）とrunnerへのdirectory snapshot import（U3-B）は完了した。
U5-A boot2 entry、U4-P2 clean trace／protocol判断、U5-B watchdog warm reset、外部`uf2loader`の
U6 end-to-end GateとM-NESCO拡張受入まで完了した。U4ではCMD17のsingle-block応答順序だけを修正し、
固定版uf2loaderのU4受入経路にはCMD18/CMD12等のmulti-block production codeを追加していない。別計画の
SD-GEN-1 P4ではboundedなmulti-block経路をdefault runtimeへ接続した。U6はcleanな外部loader source/buildと
clean backendで同一入力を3回実行し、UF2 strict検査、flash readback、loader領域保護、SD trace、UART、
report、framebuffer、watchdog warm reset、再attachを合格させた。
計画書は[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)です。
`firmware-validation/evidence/m-nesco-20260813-01/`にM-NESCO-S1のreport、scenario、UART、画面証拠を置いた。
U4-P2とU5-Aの実装判断、U5-Bの受入、U6の正式evidenceはclean commitへ固定済みです。M-NESCO拡張の
diagnostic oracle、計画4ケース＋追加mapper 1のA/B反復、clean source再build、証拠manifestも固定済みです。
U6 Gateの証拠は`firmware-validation/evidence/uf2loader-u6-20260822-01/`にあります。`capability.json`には
全UF2互換ではなく、clean uf2loader sourceの限定されたSD→flash→watchdog→再起動経路を示す
`uf2loader-e2e`を追加しています。
U4-P2では、`picocalc-run --sd-trace <path>`によるSDカード側の診断traceをclean loaderで3回取得しました。
traceはrunner reportとは別のschema 1 JSON artifactで、command／response／data token／block長／CRC／CS区間を
streaming digestと上限付きpreviewへ記録します。3回ともCMD17のみ（CMD18/CMD12/CMD23/CMD24/CMD25は未観測）で、
trace digestとtraceなし／traceありのreport・UARTが一致しました。従ってmulti-block production codeは追加せず、
CMD17のR1→data token順序バグはunit test付きで修正済みです。
U4-P2の初期測定はdirty working treeの作業記録だったが、U6ではbackend commit
`d1360cbb13fd807661474b49a1b5516b12567d00`をclean固定して再実行した。
準備の判定表は完了済み履歴の[`history/uf2loader/UF2LOADER_U4_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U4_PREFLIGHT_20260822.md)と
[`history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md)です。U5-Bの実装前契約・受入条件は
[`history/uf2loader/UF2LOADER_U5B_WATCHDOG_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U5B_WATCHDOG_PREFLIGHT_20260822.md)を参照してください。
M-NESCO拡張の契約・fixture・provenance・受入結果は
[`history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md)を参照してください。
U6の実装前契約、UF2/raw flashのartifact境界、loader選択、watchdog後の再起動、determinism、negative条件は
[`history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md)を参照してください。U6-P0の
`tools/picocalc.py uf2 inspect/assemble`とunit testは実装済みで、外部loaderを使ったU6-P1到達smokeも
localで確認した。U6 Gateの正式結果は[`../firmware-validation/evidence/uf2loader-u6-20260822-01/`](../firmware-validation/evidence/uf2loader-u6-20260822-01/)に固定した。
通常のdirect bootアプリdebugと既存target回帰は変更しない。U6の標準入口は
`python3 tools/picocalc.py uf2 e2e`であり、入力UF2、SD tree、外部loader source、backend commitを
明示して実行する。
SD-GEN-1汎用SD protocol一般化はP0〜P5まで完了した。詳細計画は
[`SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)であり、
P0（現状棚卸しとclean trace採取）、P1（wire契約・受入マトリクス）、P2（feature-gated最小state
machine）、P3（trace replay、negative report統合、既存U6／M-NESCO／FATの凍結trace回帰）、P4（default runtime代表E2E）、
P5（versioned validationとbounded capability判断）を完了した。
P3では`sd-gen1-multiblock`を明示したboard／harness testと診断reportだけを有効化し、P4で同featureを
board／harnessのdefault runtimeへ接続し、SPI0のCMD18→2 block→CS保持中CMD12、CMD23/CMD25→1 block write→CMD17 readbackを送るrepository-owned
synthetic firmware E2Eを追加した。RAW exportのreadback byte一致も含め、default board 90件、legacy no-default 85件、default harness 67件、
legacy harness 66件、clippy default／legacyをlocalでpassさせ、既存U6／M-NESCO／FAT16／FAT32の凍結trace
も再playした。synthetic E2Eは3回実行し、reportの安定項目、trace、exported RAW imageが一致した。P4のreport／trace／SHAは[`sd-gen1-p4-20260823-01/`](../firmware-validation/evidence/sd-gen1-p4-20260823-01/)へ固定した。
既存versioned targetとU6／uf2loader capabilityは変更していない。P5でversioned validation contractを追加し、
対象commandと未対応境界を限定した`sd-multi-block` capabilityだけをbounded supportとして昇格した。P5のdecision evidenceは
[`../firmware-validation/evidence/sd-gen1-p5-20260823-01/`](../firmware-validation/evidence/sd-gen1-p5-20260823-01/)へ固定した。
P0のsource inventoryとU6 clean trace確認は[`history/sd-gen1/SD_GEN1_P0_INVENTORY_20260823.md`](history/sd-gen1/SD_GEN1_P0_INVENTORY_20260823.md)に記録し、
M-NESCO通常menu A/B、FAT16、FAT32の代表wire traceを各3回deterministicで採取した完了recordを
[`../firmware-validation/evidence/sd-gen1-p0-20260823-02/`](../firmware-validation/evidence/sd-gen1-p0-20260823-02/)へ固定した。
P1のwire契約は[`history/sd-gen1/SD_GEN1_P1_WIRE_CONTRACT_20260823.md`](history/sd-gen1/SD_GEN1_P1_WIRE_CONTRACT_20260823.md)と
[`../firmware-validation/contracts/sd-gen1-p1-wire-v1.json`](../firmware-validation/contracts/sd-gen1-p1-wire-v1.json)に固定した。
P2のfeature実装・local test結果は[`history/sd-gen1/SD_GEN1_P2_IMPLEMENTATION_20260823.md`](history/sd-gen1/SD_GEN1_P2_IMPLEMENTATION_20260823.md)と
[`../firmware-validation/contracts/sd-gen1-p2-vectors-v1.json`](../firmware-validation/contracts/sd-gen1-p2-vectors-v1.json)に固定した。
これはU6の固定LCD fixture evidenceとは別のNESco-specific gateであり、計画4ケース＋追加mapper 1の証拠は
[`../firmware-validation/evidence/m-nesco-ext-20260822-01/`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)に固定している。
P3のreplay tool、negative verdict、U6／M-NESCO／FAT16／FAT32回帰結果は
[`../firmware-validation/evidence/sd-gen1-p3-20260823-01/`](../firmware-validation/evidence/sd-gen1-p3-20260823-01/)と
[`../firmware-validation/contracts/sd-gen1-p3-validation-v1.json`](../firmware-validation/contracts/sd-gen1-p3-validation-v1.json)に固定した。

U3-Aの実行入口は[`USER_GUIDE/SD_IMAGES.md`](../USER_GUIDE/SD_IMAGES.md)であり、U3-Bのwrapper入口は
`python3 tools/picocalc.py test --mode firmware --sd-dir <directory>`である。どちらも決定的RAW
snapshotを使い、runnerへhost directoryを直接mountするものではない。

## 性能

正式promoted値はPicoTetrisでwall中央値**25.381594秒**、実時間比**14.636593%**です。
R5前baseline 63.247秒から約2.492倍高速化しています。

OPT2候補は追加promotionなし、OPT3-Bは退行、OPT3-Cは当時のbaselineに対して4.1542%改善でしたが
5%採用基準未達でrevertしました。OPT4 micro-opt bankをfeature-gated候補として評価しましたが、
現行backend mainのOPT4-A featureでempty sentinelとfaulting PCの誤一致をunit testが検出しましたが、
backend `37c50e6`で修正し、default／unconditional／8-byte／compactのfeature matrixを合格させました。
DMA／audio低レベル回帰はbackend `6a675b1`でquantum-invariance 5/5、HIGH_PRIORITY／timer競合は`00b05f5`で5/5、board-less audio／WAV／UART marker CLI E2Eは`e0eda1c`で合格させました。現行firmware再回帰、証拠固定、cycle差の暫定分類、差分targetをholdする受入判断まで完了したため、bank復帰は保留します。隔離candidateで得た過去のexactness／性能値は
履歴証拠として保持しますが、cycle差のある現行mainをexactness合格へ丸める根拠には流用しません。OPT4-Bはexactness passだが速度改善未確認、OPT4-Cはexactness passだが
10-run A/Bで中央値1.9094%退行、OPT4-Dは正式SD/FAT32条件で再測定しても分散が大きく、OPT4-Eは正式シナリオ10-run A/B未完了かつ短縮screeningで正の信号なしのため、いずれもpromotionしていません。
正式Template Bはremoteから復元して再測定でき、公式Helloは9.5B-cycleの**registry受入項目**を正式target条件で
合格しました。これらは隔離candidateおよび現行main回帰の記録です。現行mainの回帰修正、
DMA／audio test拡張、CLI E2E、既存firmware再回帰、証拠固定、cycle差の暫定分類、受入判断は
完了しています。ただし3 targetのcycle差をexactness合格へ丸めないため、micro-opt bank全体の
採否とpromotionは保留します。
2026-08-16時点のbackend main checkpoint (`a67e81c9…`) に対するfirmware再回帰は実行完了した。
PicoTetrisは`-1` cycle、multicoreは`+5` cycle、PicoEditは`-4` cycleの差を確認し、
UART／framebuffer／scenario等は一致した。audio targetはcycle／PCMとも一致した。公式Helloも
registry条件（`hwspi-rgb888`、keyboard `HI`、PSRAM verify、9.5B cycles）でexit 0、required
marker 3件、PSRAM `8388608/0`、unknown MMIO 0、exception 0に合格した。したがって、Helloの
registry受入項目の未完了は解消したが、full-report byte equalityを主張せず、3 targetのcycle差を
**当時のmain checkpointのexactness合格へ丸めず**、OPT4-Aのbank
復帰とpromotionを保留している。差分は`94818f8` probeと`00b05f5` checkpointでdefault runtime
更新帯に暫定的に境界づけられ、後続feature-gated候補では変化しない。このcheckpoint後にSD-GEN-1
P0〜P5の実装・回帰がbackend mainへ追加されており、現在のlocal development mainは
[`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md)と`firmware-validation/capability.json`に記録した
`f810d059…`である。`d96f73b…`はSD-GEN-1 P4/P5時点の旧local checkpointである。以下の`a67e81c9…`の数値はOPT4時点の凍結証拠であり、現在のbackend HEADを
示すものではない。検証reportと境界probeは
[`opt4-current-main-20260816-01`](../firmware-validation/evidence/opt4-current-main-20260816-01/)へ固定した。
詳細なコマンド、差分、判定は
[`picoem-picocalc/docs/BACKEND_CHANGE_VALIDATION_PLAN.md`](../../picoem-picocalc/docs/BACKEND_CHANGE_VALIDATION_PLAN.md)
と[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)を参照する。
OPT4-C/D/Eの詳細は[`history/opt4/OPT4_C_DECODED_OP_8BYTE.md`](history/opt4/OPT4_C_DECODED_OP_8BYTE.md)／
[`history/opt4/OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md`](history/opt4/OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md)／
[`history/opt4/OPT4_E_COMPACT_DISPATCH_KEY.md`](history/opt4/OPT4_E_COMPACT_DISPATCH_KEY.md)に記録しています。正式promoted targetは変更していません。
候補ごとの採否条件は[`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md)を参照してください。

## 実機相関とnegative conformance

- R5 PicoTetris: 同一artifact合格
- NEXT-1 PicoEdit: 同一artifact合格
- NEXT-2A multicore: 凍結v2同一artifact合格
- NEXT-2B audio: 凍結v3同一artifact合格
- OPT1-B: R5 observation contractとのexact equivalenceによりpromoted
- NEXT-3 SD CRC: hardware-confirmed negative母数1

NEXT-3の初回凍結backendはFault BINを誤ってacceptし、修正後backendは実機と同じR1 CRC error理由で
rejectしました。母数1なので一般的なfalse-acceptance率へ外挿しません。

## 未対応または限定事項

- Threaded executionを正確性基準にすること
- NEXT-2A外の同時device access、spinlock timing、core 1 relaunch
- 任意codec、別PWM slice／DMA destination／TREQ、mixing、speaker response。PWM5_CC診断sinkは
  timer分数とDMA block長の可変化を受け入れるが、任意の音声経路の一般化や実機相関を保証しない。
  level解析はdigital境界だけで、実際の音圧やspeaker responseは含まない
- bootrom execution、USB MSC boot
- SD removal、write protect、host directoryへのlive同期
- 任意のUF2 family／任意loader fork／USB BOOTSEL・MSC。`uf2loader-e2e`は固定source・固定artifactの
  限定経路のみであり、一般的なUF2書込み互換ではない
- raw imageのCOW読み出し・atomic exportは実装済み。M-NESCOの計画4ケース＋追加mapper 1で複数runの再attach比較を完了したが、任意ROM／任意mapperの一般互換性は保証しない
- backendのRAW exportはatomicでデータ破損を防ぐが、未作成出力の相対／絶対表記違いによるsame-path
  拒否に既知の検査抜けがある。次回backend変更時にcanonical path比較と別表記テストを追加する
- host backendのPIO、DMA、I2C transaction、interrupt、multicore、LCD wire形式
- scenarioのloop／branch、任意report fieldの直接assert
- machine APIとのheartbeat併用。初版は長時間CLI／wrapperの監視に限定
- 実機の色、向き、可読性、キーの物理反応品質。聴感は自動モデルではなく、固定された2問式の
  実機speaker受入記録で判定

完全な機械可読一覧は
[`firmware-validation/capability.json`](../firmware-validation/capability.json)を優先します。

## リポジトリ状態

working treeやpush済みかどうかは一時状態なので本書には固定せず、作業開始・終了時に各repositoryで
`git status --short --branch`を確認します。GitHub Actions節約方針により、通常開発ではCIを起動せず
ローカル検証を主体とし、push／CI実行は別途判断します。

## 詳細履歴

2026-08-10までの詳細な実装記録は
[`history/IMPLEMENTATION_STATUS_DETAIL_20260810.md`](history/IMPLEMENTATION_STATUS_DETAIL_20260810.md)に
保存しています。
