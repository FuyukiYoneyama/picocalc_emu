# 文書案内

このページが`docs/`の入口です。現行仕様と歴史資料を混同しないよう、読む目的で分けています。

## まず読む

| 目的 | 文書 |
|---|---|
| プロジェクトの入口と最短手順 | [`../README.md`](../README.md) |
| AIがアプリを作るときの規則 | [`../AI_START_HERE.md`](../AI_START_HERE.md) |
| 現在できること／できないこと | [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) |
| 現行計画の完了状態 | [`MILESTONES.md`](MILESTONES.md) |
| BSPの公開APIとhardware契約 | [`../bsp/README.md`](../bsp/README.md) |

## 通常利用

| 作業 | 文書 |
|---|---|
| Host backendで高速にロジックを検査 | [`HOST_BACKEND.md`](HOST_BACKEND.md) |
| RP2040 BINをfirmware backendで検査 | [`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md) |
| 画面／UART条件に応じてキーを投入 | [`SCENARIO_RUNNER.md`](SCENARIO_RUNNER.md) |
| JSONLで長寿命sessionを操作 | [`HEADLESS_MACHINE_API.md`](HEADLESS_MACHINE_API.md) |
| 実機証拠を記録 | [`../hardware-validation/README.md`](../hardware-validation/README.md) |

## 契約・保守

| 対象 | 文書または機械可読正典 |
|---|---|
| target revisionと不変record | [`VERSIONED_VALIDATION.md`](VERSIONED_VALIDATION.md) |
| keyboard protocol | [`KEYBOARD_CONFORMANCE.md`](KEYBOARD_CONFORMANCE.md) |
| Sol／Lunaの責任境界 | [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) |
| release前の確認 | [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) |
| 要求仕様 | [`../REQUIREMENTS.md`](../REQUIREMENTS.md) |
| 対応・未対応範囲 | [`../firmware-validation/capability.json`](../firmware-validation/capability.json) |
| firmware target registry | [`../reference-projects/firmware-targets.json`](../reference-projects/firmware-targets.json) |

`NEXT1_PICOEDIT_BLIND_CONTRACT.md`とNEXT-3の3文書は、検証器がSHA-256を含めて読む凍結契約です。
作成時点の状態や「次は」が残っていても現在計画ではなく、改変して現在値へ合わせません。
NEXT-3の最終状態は`IMPLEMENTATION_STATUS.md`と`MILESTONES.md`、詳細な最終結果は
`NEXT3_SD_CMD8_CRC_CANDIDATE.md`を参照してください。

keyboard controllerのprotocol producer一次リファレンスはClockworkPi公式
[`Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)です。
このworkspaceでは`/home/fuyuki/pico_dvl/codex/PicoCalc/Code/picocalc_keyboard`にあります。

## 歴史資料

R0〜R6、OPT0〜OPT3、NEXT-1〜NEXT-3、初期設計、性能実験、実機調査の長文は
[`history/README.md`](history/README.md)から参照します。

歴史資料に残る「次は〜」「未着手」は、その文書が作成された時点の判断です。現在の状態は
`IMPLEMENTATION_STATUS.md`、現在計画は`MILESTONES.md`を優先します。

`firmware-validation/records/`、`hardware-validation/records/`、provenance、registryは
不変証拠または機械検証対象なので、文書整理を理由に移動しません。
