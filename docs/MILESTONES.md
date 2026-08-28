# 現行計画の完了状態

**この文書が番号付き作業計画の正典です。** R0〜NEXT-4は完了または正式終了しています。
性能改善については、旧OPT3終了後の現行計画としてOPT4 micro-opt bankを定義しています。
直近の完了済み機能計画だった任意I2C外部moduleを扱うI2C-EXTは、E0〜E6まで完了しています。E5では同一UF2を通常のuf2loader経路で実機起動し、E6ではその証拠をversioned validationとbounded capabilityへ固定しました。現在の未実装計画はValidated Realtime Preview（VRP-0〜VRP-7）です。提案の安全境界をソース監査で補正した実施順序は[`VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md`](VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md)を正典とします。

## 状態

| 順序 | 作業パッケージ | 最終状態 |
|---|---|---|
| R0 | 基準点・生成契約・provenance | 完了 2026-08-05 |
| R1 | verdict/report、FAT32既定、公式keyboard conformance | 完了 2026-08-05 |
| R2 | Firmware CLI・target registry | 完了 2026-08-06 |
| R3 | PicoTetris正式回帰 | 完了 2026-08-06 |
| R4 | 3リポジトリ品質ゲート | 完了 2026-08-06 |
| R5 | 同一artifact PicoCalc実機相関 | 完了 2026-08-08 |
| R6 | 文書・配布状態確定 | 完了 2026-08-08 |
| R6-M | backend role／回帰境界の分離 | 完了 2026-08-09 |
| OPT1-B | Serial fast-path gate | promoted完了 2026-08-08 |
| OPT2 | exact event batching | 性能条件未達。追加promotionなしで終了 2026-08-09 |
| OPT3 | CPU/decode高速化 | OPT3-Cまで評価。5%条件未達でrevert、終了 2026-08-09 |
| OPT4 | micro-opt bank | **Aのempty-sentinel／DMA・audio／priority低レベル／CLI E2E／firmware回帰を完了。現行mainで3 targetにcycle差が残るため暫定分類のうえhold。B〜Eは採用なし、bank復帰とpromotionは保留、promoted targetはOPT1-Bを維持。詳細は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)** |
| NEXT-1 | 新規blind app（PicoEdit） | 完了 2026-08-09 |
| NEXT-2 | bounded multicore／audio | NEXT-2A・2B完了 2026-08-09 |
| NEXT-3 | negative conformance | 完了 2026-08-10 |
| NEXT-4 | 安定headless machine API | 完了 2026-08-10 |
| I2C-EXT | 任意I2C外部module（RTC/EEPROM/AHT20/BMP280） | **E0〜E6完了。E5は同一BIN 3回のemulator回帰と、同一UF2の実機startup probe（RTC／EEPROM／keyboard／AHT20／BMP280）を合格。E6はactive target、versioned validation、`i2c-external-rtc-env-v1` bounded capabilityを固定。** private hardwareを既定構成へ入れず、run単位profileとしてattach/detachする。固定証拠は[`i2c-ext-e5-20260823-01`](../firmware-validation/evidence/i2c-ext-e5-20260823-01/)、詳細は[`I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)。backend commitsは`60ac700`、`f1ae8dc`、`5802b2e`、`0481474`、`f810d05`** |
| VRP | Validated Realtime Preview | **提案レビュー・実装計画完了、実装未着手。** VRP-0〜VRP-6を順に実施し、VRP-7は1倍未達時だけ開始する。preview機能完成と1倍qualified完成を分離し、現時点ではcapabilityへ昇格しない |

R0〜NEXT-4の15項目には最終処置があります。OPT2とOPT3は正確性を優先する性能gateにより
正式終了しました。不採用candidateはactive targetへ混入していません。OPT4はその後に定義した
現行の実験計画であり、OPT4-Aはsentinel回帰、DMA／audio／priority低レベル回帰、CLI E2E、
firmware再回帰まで完了しています。現行mainの3 targetにcycle差があるため、差分を暫定分類し、
bank復帰とpromotionを保留しています。隔離candidateの測定記録は保持しますが、現行mainの
cycle差をexactness合格へ丸める根拠には流用しません。OPT4-Bは速度改善未確認、OPT4-Cは
中央値退行、OPT4-Dは正式SD/FAT32条件でも正の改善未確認、OPT4-Eは正式性能測定未完了かつ短縮screeningで正の信号なしのため、いずれもpromoted targetへは採用していません。OPT4-C/D/Eの
実装・exactness・A/B結果は[`history/opt4/OPT4_C_DECODED_OP_8BYTE.md`](history/opt4/OPT4_C_DECODED_OP_8BYTE.md)／
[`history/opt4/OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md`](history/opt4/OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md)／
[`history/opt4/OPT4_E_COMPACT_DISPATCH_KEY.md`](history/opt4/OPT4_E_COMPACT_DISPATCH_KEY.md)に記録しています。

## 現在の品質境界

検証は次の三層を分離します。

1. host unit test — hardware-freeなロジックを高速に保護
2. firmware scenario — 同一RP2040 BINとPicoCalc device modelの権威ある自動判定
3. hardware correlation — 同一artifactを実機で確認する最終相関

Host backendの合格だけでハードウェア挙動を合格にしません。runnerの終了コード0だけでも
合格にせず、targetが固定したBIN、backend、scenario、stop reason、UART、report、snapshotを照合します。

## 現在の正式計画

R/NEXTの機能作業は完了しています。UF2Loader U0〜U6、M-NESCO拡張受入、SD-GEN-1 P0〜P5は完了しています。SD-GEN-1 P5で
boundedな`sd-multi-block` capabilityをversioned validationとして受け入れました。現行作業は、性能面では
[`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md)、機能面では番号付き作業とは別に固定した
**UF2Loader SD／flash統合（U0〜U6）**とM-NESCO拡張受入は完了し、U6の限定capabilityを有効化しました。U4はCMD18/CMD12追加なしと判定済みです。通常direct boot debugは従来どおりで、
USB BOOTSEL/MSCや全UF2互換は未対応です。
OPT4／backend側は、性能測定を再開する前に
[`picoem-picocalc/docs/BACKEND_CHANGE_VALIDATION_PLAN.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/BACKEND_CHANGE_VALIDATION_PLAN.md)
の修正・低レベルtest・CLI E2E・既存firmware再回帰をこの順序で完了しました。現行mainの
cycle差は暫定分類として記録し、差分targetはhold、旧pinとpromoted targetは維持しています。
新たなversioned validationや実機相関はこの記録から開始しません。
詳細は[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)を参照してください。
`history/`に残る古い「次はNEXT-*」「次はOPT*」を再開指示として扱いません。新しい正式計画を
開始する場合は、目的、受入条件、対象リポジトリ、実機操作、ローカル検証、CI予算を計画書で再確認します。
直近の完了済み正式計画として、I2C-EXTのE0〜E6を
[`I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)に固定した。
実装はE0（source/provenanceとwire contract）、E1（controller/mux/shared virtual-time）、E2の
DS3231/AT24C32/AHT20/BMP280 modelとpicocalc-rtc-v1／picocalc-rtc-env-v1 profile接続、schema 2 sidecar、target contract接続、E5同一UF2実機probe、E6 active target／versioned validation／bounded capabilityまで完了した。
U0のprovenance固定は完了しており、現在はproduction codeを変更できる状態です。

次に開始する新規機能計画はValidated Realtime Previewです。実装順序は、VRP-0 contract/host
spike、VRP-1 receipt/admission、VRP-2 shared session/preview API、VRP-3 GUI/input、VRP-4 audio、
VRP-5 qualification、VRP-6 capability/docsです。VRP-7 exact optimizationはVRP-5で1倍未達を
確認した場合だけ開始します。詳細と各gateは
[`VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md`](VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md)
を正典とし、提案書だけからproduction実装の順序を推測しません。

### UF2Loader計画の実施順序と中間マイルストーン

| 順序 | 計画段階 | 状態 |
|---:|---|---|
| 1 | U0 provenance／fixture／first-run trace | **完了 2026-08-13** |
| 2 | U1 SD RAW image | **完了 2026-08-13** |
| 3 | U2 flash erase/program | **完了 2026-08-13** |
| 4 | **M-NESCO-S1** — `Picocalc_NESco`を既存direct bootでSD/flash debug開始 | **完了 2026-08-13** |
| 5a | U3-A host directory ↔ RAW pack／extract tool | **完了 2026-08-13** |
| 5b | U3-B runner-integrated directory snapshot import | **完了 2026-08-22** |
| 6 | U5-A boot2 entry | **完了。`--boot-mode boot2` production実装・local evidence 2026-08-22** |
| 7 | U4 実loaderで判明したSD protocol gap | **完了。clean trace 3回、CMD18/CMD12未観測、multi-block追加なし 2026-08-22** |
| 8 | U5-B watchdog warm reset | **完了。flash／SD保持とboot2再入場をlocal regressionで固定 2026-08-22** |
| 8.5 | **M-NESCO拡張受入** — 複数mapper／サイズ、ROM境界、CPU／PPU／core 1／DMA、flash再attach | **完了。4計画case（mapper 0/2/4/30）＋mapper 1追加、A/B各3回、2026-08-22** |
| 9 | U6 実`uf2loader` end-to-end | **完了（独立fixture）。clean source/backendの3回Gate、readback・保護領域・trace・SHA・再attach合格 2026-08-22** |
| 10 | **SD-GEN-1 汎用SD protocol generalization** — uf2loader以外のアプリを含む汎用SD経路 | **P5完了（P0 trace／P1 wire契約／P2 state machine／P3 replay・negative・U6／M-NESCO／FAT凍結回帰／P4 default runtime代表E2E／P5 bounded capability）。詳細は[`SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)、[`P5 decision evidence`](../firmware-validation/evidence/sd-gen1-p5-20260823-01/)** |

M-NESCO-S1は番号付きR/NEXTの追加ではなく、U1とU2のGateが閉じた時点で
`Picocalc_NESco`のdirect-boot SD/flash debugを解禁する中間マイルストーンです。
FAT32 RAWからROMを選択し、erase/programとXIP反映を同一runで確認した証拠を
`firmware-validation/evidence/m-nesco-20260813-01/`へ保存しています。この時点では
複数size/mapperの網羅、run-to-run再attach比較、directory import、boot2、watchdog、
`uf2loader-e2e`の限定capabilityとは区別します。全UF2互換やUSB BOOTSEL/MSCは宣言しません。

M-NESCO拡張受入は、U5-B watchdog warm resetの受入後に実施した独立gateです。計画caseのmapper 0/2/4/30と追加mapper 1、small／medium／large
ROM、PRG／CHRの先頭・中間・末尾read、CPU fetch／data、core 1／DMAのXIP read、flash export後の再attach、
run間のflash SHA、SD sourceとROM file SHAの一致を、同一provenanceで確認しました。計画4ケース＋追加mapper 1の実行証拠は
[`history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md)にあり、
[`../firmware-validation/evidence/m-nesco-ext-20260822-01/`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)に固定しています。このgate単独では`uf2loader-e2e`へ昇格しません。U6のclean Gateは別途完了済みです。

U6の契約と結果は[`history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md)に固定しています。
bootloader-only initial flashを起点に、boot2→stage3→`BOOT2040.UF2`→アプリUF2のerase/program→
watchdog warm reset→書込み後app起動を通し、3回determinism、strict UF2 negative unit test、
再attachを閉じました。これはM-NESCO拡張とは独立した固定LCD fixtureであり、限定された固定source／artifact経路だけを
`uf2loader-e2e` capabilityへ反映しています。

`SD-GEN-1`汎用SD protocol一般化のP0〜P5は完了しました。M-NESCO拡張のfixtureと証拠は完了済みです。
詳細計画を[`SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)へ固定し、P4でmulti-block featureを
既定runtimeへ接続した代表synthetic firmware E2E（CMD18/CMD12 read、CMD23/CMD25 write、CMD17 readback）と、既存U6／M-NESCO／FAT凍結trace再playを完了しました。P5でversioned validation contractとbounded
`sd-multi-block` capabilityを追加しました。
追加blind app、SD fault／persistence、machine APIのclient利便性は候補であり、SD-GEN-1とは別の正式計画ではありません。

## 詳細履歴

各作業の当時の受入条件、commit、SHA、測定値、判断経緯は
[`history/MILESTONES_DETAIL_20260810.md`](history/MILESTONES_DETAIL_20260810.md)と
[`history/README.md`](history/README.md)に保存しています。
