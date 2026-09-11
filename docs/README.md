# 文書案内 — PicoCalc開発の流れに沿って読む

このプロジェクトは、エミュレーターを使ってPicoCalcアプリを開発・検証する環境です。
全体の目的と構成は[PROJECT_OVERVIEW](PROJECT_OVERVIEW.md)、現在の対応範囲は
[IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)を参照します。

## アプリを作る・動かす・調べる

| 作業 | 文書 |
|---|---|
| 最初の生成とビルド | [利用ガイド](../USER_GUIDE/README.md)、[QUICKSTART](../USER_GUIDE/QUICKSTART.md) |
| ロジック確認とRP2040 BIN実行 | [TESTING](../USER_GUIDE/TESTING.md)、[host](HOST_BACKEND.md)、[firmware](FIRMWARE_BACKEND.md) |
| 再現する入力・画面・UART判定 | [SCENARIOS](../USER_GUIDE/SCENARIOS.md)、[runner契約](SCENARIO_RUNNER.md) |
| SD imageの準備と取り出し | [SD_IMAGES](../USER_GUIDE/SD_IMAGES.md) |
| 対応版での対話操作 | [PREVIEW_GUI](../USER_GUIDE/PREVIEW_GUI.md)、[machine API](HEADLESS_MACHINE_API.md) |
| 複数runの分離と監視 | [CONCURRENT_RUNS](../USER_GUIDE/CONCURRENT_RUNS.md) |
| 実機で補完する確認 | [HIL](HARDWARE_IN_THE_LOOP.md)、[実機記録](../hardware-validation/README.md) |
| BSP API | [BSP](../bsp/README.md) |

追加機能の説明は、その機能のtargetが固定するbackend版を前提とします。
過去の機能受入を公開main全体の対応表として読まないでください。

## エミュレーター・検証基盤を保守する

- [DEVELOPER_GUIDE](../DEVELOPER_GUIDE.md)、[AI_START_HERE](../AI_START_HERE.md)、[運用](DEVELOPMENT_WORKFLOW.md)
- [要求仕様](../REQUIREMENTS.md)、[版管理](VERSIONING.md)、[公開手順](PUBLIC_RELEASE.md)、[release checklist](RELEASE_CHECKLIST.md)
- [target registry](../reference-projects/firmware-targets.json)、[versioned validation](VERSIONED_VALIDATION.md)、[capability registry](../firmware-validation/capability.json)
- [外部project品質](EXTERNAL_PROJECT_QUALITY.md)、[外部workspace](EXTERNAL_WORKSPACE.md)
- [keyboard](KEYBOARD_CONFORMANCE.md)、[multicore](NEXT2_MULTICORE_CONFORMANCE.md)、[audio](NEXT2_AUDIO_CONFORMANCE.md)
- [音量評価](AUDIO_LEVEL_QUALITY.md)、[speaker校正](SPEAKER_CALIBRATION.md)、[聴感確認](SPEAKER_LISTENING_ACCEPTANCE.md)

## 固定契約・証拠

firmware-validationとhardware-validationのrecords／evidence、provenance、registry、
凍結契約のpath・ID・SHAは保持します。過去の記録を現在値へ書き換えません。
NEXT1_PICOEDIT_BLIND_CONTRACT、NEXT-3の契約など、検証器の参照対象も元の場所を維持します。

[preview契約資料](validated-realtime-preview/README.md)は固定schemaと対応版の実装記録です。
1倍速への適格性判定は未達で終了しています。
[UF2Loader](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)、
[SD-GEN-1](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)、
[I2C-EXT](I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)は過去の受入範囲と固定版を調べる資料です。

## プロジェクト履歴

- [作業パッケージの台帳](MILESTONES.md)
- [高速化・UX 1倍速プロジェクト：失敗・終了の総括](history/performance/README.md)
- [全履歴の索引](history/README.md)

旧計画の「次は」「現行」「再開条件」は当時の記述です。現在の作業指示として扱いません。
