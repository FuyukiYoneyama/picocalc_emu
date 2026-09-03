# 作業計画の完了状態

**この文書は完了・終了した作業の台帳です。** R0〜NEXT-4は完了または正式終了しています。
現在の性能退行復旧の目的、実施順序、採否条件は
[`PICOCALC_EMULATOR_PERFORMANCE_RECOVERY_PLAN_20260903.md`](PICOCALC_EMULATOR_PERFORMANCE_RECOVERY_PLAN_20260903.md)
を正典とします。
表示名として、`VRP-LOAD-0`は **LOAD-0（最大級の継続負荷性能テスト0番）**、
`picotetris-opt1b`は **Tetris（軽ゲーム実装）** と記載します。内部IDと証拠のパスは変更しません。
LOAD-0は数値の基準値や高速化gateではなく、保存済みの人工stress fixtureです。120秒sliceの
測定値はLOAD-0固有の歴史的観測値であり、現行エミュレーター全体の性能値ではありません。
OPT4 micro-opt bankは完了・保留履歴であり、現行計画ではありません。
I2C-EXTはE0〜E6まで完了しています。Validated Realtime PreviewはVRP-0〜VRP-4とVRP-5 reusable backend-pin preflightまで完了し、LOAD-0 r1のpreview-only経路も確認済みです。これらは完了・中断履歴であり、未完了のVRP-5〜VRP-7、正式qualification、capability昇格は現行作業ではありません。
1倍速UXプロジェクトは、LOAD-0 r1の120秒non-formal vertical sliceを停止点として中断しています。
未完了項目は現行高速化へ持ち越さず、追加の長時間runやVRP-5 qualificationを開始しません。判断は
[`validated-realtime-preview/VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md`](validated-realtime-preview/VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md)
を参照してください。

## 状態

VRP-2-eの`c1c20d7d86a3006569375bc333cf72494e95eb46`は当時の不変evidenceとして保持する。
到達可能なclean backendでの新しいversioned target／validation／receiptも作成・受入済みだが、
1倍速中断により正式qualificationは開始しない。

### VRP-NES-0／NESco歴史資料の境界（2026-08-29時点）

VRP-NES-0で使用した診断NESco checkoutは、ローカルの
`codex/mnesco-extension`（`7f3fa05971930e03653694117cbf6a435ec1dd4e`）でcleanである。
このbranchはGitHubの`Picocalc_NESco` remoteには公開されていない。公開remoteに確認できるのは
`main`（`acf605358b0808052b87bc3e64aabf413d2d22b7`）と、今回の作業で作成していない既存の
`perf/bg-tile-share-log`（`c2430c0bcf536ccf7aec18039bb6dfb81eb9ad13`）である。

`Picocalc_NESco`は独立プロジェクトであり、`picocalc_emu`はNEScoの計画・改造・branch公開・pushを
行わない。`picocalc_emu`側で保持するのは提供されたBIN/UF2、SHA-256、report、trace、validation
recordなどの入力識別情報と検証記録だけである。SHA-256は同一バイト列の確認には使えるが、NESco
ソースの再構成、ライセンス判断、一般的な動作保証を意味しない。このtargetは
`historical / non-qualifying`であり、`pending-revalidation`状態は当時の外部source再現性を記録する
ために保持する。VRP-5のblockerにはしない。将来NES固有の適合性を再確認する場合だけ、NESco側の
所有者が提供する未改変の公開refまたは再現可能なartifactをoptional conformanceとして扱う。

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
| PERF | PicoCalc emulator高速化 | **PERF-Q3まで完了後、約7.4倍の性能退行判明により以後を停止。履歴として保持** |
| PERF-RECOVERY | 高速地点からの性能退行復旧 | **現行計画。R0・R1完了、G0クリーン検証完了、G1（CPU・multicore・割込み正確性）・G2（LCD・PIO・PSRAM正確性）candidate pass。G3（DMA・audio正確性）待ち** |
| OPT1-B | Serial fast-path gate | promoted完了 2026-08-08 |
| OPT2 | exact event batching | 性能条件未達。追加promotionなしで終了 2026-08-09 |
| OPT3 | CPU/decode高速化 | OPT3-Cまで評価。5%条件未達でrevert、終了 2026-08-09 |
| OPT4 | micro-opt bank | **Aのempty-sentinel／DMA・audio／priority低レベル／CLI E2E／firmware回帰を完了。現行mainで3 targetにcycle差が残るため暫定分類のうえhold。B〜Eは採用なし、bank復帰とpromotionは保留、promoted targetはOPT1-Bを維持。詳細は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)** |
| NEXT-1 | 新規blind app（PicoEdit） | 完了 2026-08-09 |
| NEXT-2 | bounded multicore／audio | NEXT-2A・2B完了 2026-08-09 |
| NEXT-3 | negative conformance | 完了 2026-08-10 |
| NEXT-4 | 安定headless machine API | 完了 2026-08-10 |
| I2C-EXT | 任意I2C外部module（RTC/EEPROM/AHT20/BMP280） | **E0〜E6完了。E5は同一BIN 3回のemulator回帰と、同一UF2の実機startup probe（RTC／EEPROM／keyboard／AHT20／BMP280）を合格。E6はactive target、versioned validation、`i2c-external-rtc-env-v1` bounded capabilityを固定。** private hardwareを既定構成へ入れず、run単位profileとしてattach/detachする。固定証拠は[`i2c-ext-e5-20260823-01`](../firmware-validation/evidence/i2c-ext-e5-20260823-01/)、詳細は[`I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)。backend commitsは`60ac700`、`f1ae8dc`、`5802b2e`、`0481474`、`f810d05`** |
| VRP | Validated Realtime Preview | **VRP-0〜VRP-4完了（VRP-4 formal evidence 2026-08-29）。** 固定PCRP IPC、UART0 TX/RX、RGB565 frame、reset/quit、pacer status、fail-closed入力、`src/session.rs`へのMachineSession共通module分離、UART／framebuffer／unsupported-MMIO／audio-sinkのversioned observation projection/digestを実装し、runner process E2Eをローカル確認済み。VRP-2-a〜eではversioned target／validation record／receipt、descriptor consumer、machine API／UART fixture、registered／batch／machine／preview四者digestを受入した。VRP-3ではTk薄型GUI、PicoCalc skin、320x320 RGB565 LCD合成、自動UART0 console、key down/held/up・auto-repeat抑止、reset/reload、sticky UX-invalidを追加し、WSLg smokeを確認した。VRP-4ではbounded backend tap／非同期writer／frontend・host queue、可変rate resampling、drop/underrun/epoch statusを実装し、同一registered targetのmonitor off／on／forced-drop formal evidenceを固定した。VRP-5 reusable backend pin preflightは完了（`picotetris-opt1b-vrp5` r10、到達可能なclean backend、receipt／admission／headless consumer）。VRP-5 qualification、VRP-6 capability/docs、条件付きVRP-7は未完了。`VRP-LOAD-0`はrepository-ownedな320x320 RGB565全画面・48 kHz DMA音声・継続CPU負荷・clean clone再現性を固定するr1 prototypeを実装し、2つのclean cloneによる固定条件BIN／UF2一致、1秒／2秒のruntime／input smoke、120秒のnon-formal vertical sliceを確認した。preview-only target `vrp-load0-r1-vslice` r1のwrapper report／receipt／admission／headless consumerまで受入したが、これはLOAD-0 completionや1倍速の判定ではない。3回determinism、10 virtual分以上の準備run、LOAD-0正式target completionは未完了。既存VRP-NES-0 fixture／target／evidenceは歴史資料として保持し、`realtime-1x-qualified`の前提にはしない。 |

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

現在の性能作業は
[`PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md`](PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md)
に従います。R/NEXTの機能作業、UF2Loader U0〜U6、M-NESCO拡張受入、SD-GEN-1 P0〜P5は完了しています。
SD-GEN-1 P5でboundedな`sd-multi-block` capabilityをversioned validationとして受け入れました。
機能面では番号付き作業とは別に固定した
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

Validated Realtime Previewは完了・中断状態を記録する履歴です。VRP-0 contract/host spike、VRP-1
receipt/admission、VRP-2-a current-backend versioned target revalidation、VRP-2-b descriptor consumer、VRP-2-c machine API schema-1 transcript、VRP-2-d UART RX、VRP-2-e registered-target digest gate実装と実target受入、VRP-3のTk GUI／PicoCalc skin／LCD／keyboard／UART0 console／reset-reload、VRP-4のbounded host audio monitorとregistered-target off／on／forced-drop formal evidence、VRP-5 reusable backend pin preflightは完了しています。shared sessionとversioned observation projection/digest、board-backed synthetic UART fixtureの三者report-compatible observation digest smoke gateも実装済みです。VRP-LOAD-0はrepository-ownedな320x320 RGB565全画面・48 kHz DMA音声・継続CPU負荷・clean clone再現性を固定するr1 prototypeを実装し、固定条件BIN／UF2再現性、1秒／2秒のruntime／input smoke（公式scenarioを含む）、120秒 vertical slice、preview-only targetのreceipt／admission／headless consumerまで確認済みです。3回determinism、10 virtual分以上の準備run、LOAD-0 completionは未完了です。既存VRP-NES-0のsynthetic NROM fixtureと3回local firmware evidenceは歴史資料として保持し、VRP-5の依存にはしません。VRP-7 exact optimizationはVRP-5で1倍未達を
確認した場合だけ開始する旧条件でしたが、現在はVRP-5以降とVRP-7を開始しません。詳細と当時の各gateは
[`VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md`](VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md)
に記録していますが、production実装の順序には使いません。

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
