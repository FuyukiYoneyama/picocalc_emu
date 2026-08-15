# 文書案内

このページが`docs/`の入口です。現行仕様と歴史資料を混同しないよう、読む目的で分けています。

通常の利用者・AIは、リポジトリ直下の
[`USER_GUIDE/`](../USER_GUIDE/README.md)から開始してください。このページは全資料の索引であり、
通常利用の手順を最初から読むための入口ではありません。

## まず読む

| 目的 | 文書 |
|---|---|
| プロジェクトの入口と最短手順 | [`../README.md`](../README.md) |
| 通常利用とAIの実行手順 | [`../USER_GUIDE/`](../USER_GUIDE/README.md) |
| 高度なAI監督・実機依頼の規則 | [`../AI_START_HERE.md`](../AI_START_HERE.md) |
| 現在できること／できないこと | [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) |
| 現行計画の完了状態 | [`MILESTONES.md`](MILESTONES.md) |
| 性能micro-optの現行計画 | [`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md) |
| OPT4-A試作・A/B記録 | [`OPT4_A_UNCONDITIONAL_CACHE_LOOKUP.md`](OPT4_A_UNCONDITIONAL_CACHE_LOOKUP.md) |
| OPT4-B試作・A/B記録 | [`OPT4_B_NVIC_BITMAP_SCAN.md`](OPT4_B_NVIC_BITMAP_SCAN.md) |
| OPT4-C試作・A/B記録 | [`OPT4_C_DECODED_OP_8BYTE.md`](OPT4_C_DECODED_OP_8BYTE.md) |
| 公開版の目印とバージョン運用 | [`VERSIONING.md`](VERSIONING.md) |
| BSPの公開APIとhardware契約 | [`../bsp/README.md`](../bsp/README.md) |
| エミュレーター関連の外部project workspace（任意） | [`EXTERNAL_WORKSPACE.md`](EXTERNAL_WORKSPACE.md) |

## 通常利用

| 作業 | 文書 |
|---|---|
| Host backendで高速にロジックを検査 | [`HOST_BACKEND.md`](HOST_BACKEND.md) |
| RP2040 BINをfirmware backendで検査 | [`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md) |
| 複数firmware runのheartbeat監視 | [`CONCURRENT_RUNS.md`](CONCURRENT_RUNS.md) |
| 画面／UART条件に応じてキーを投入 | [`SCENARIO_RUNNER.md`](SCENARIO_RUNNER.md) |
| JSONLで長寿命sessionを操作 | [`HEADLESS_MACHINE_API.md`](HEADLESS_MACHINE_API.md) |
| 外部projectのBSP由来と音声合否を固定 | [`EXTERNAL_PROJECT_QUALITY.md`](EXTERNAL_PROJECT_QUALITY.md) |
| 音量advisoryと極端なrail張り付きを分離 | [`AUDIO_LEVEL_QUALITY.md`](AUDIO_LEVEL_QUALITY.md) |
| 内蔵speakerの破綻境界を動画から校正 | [`SPEAKER_CALIBRATION.md`](SPEAKER_CALIBRATION.md) |
| 内蔵speakerを人間が判定する2問と通過基準 | [`SPEAKER_LISTENING_ACCEPTANCE.md`](SPEAKER_LISTENING_ACCEPTANCE.md) |
| 実機証拠を記録 | [`../hardware-validation/README.md`](../hardware-validation/README.md) |

## 契約・保守

| 対象 | 文書または機械可読正典 |
|---|---|
| target revisionと不変record | [`VERSIONED_VALIDATION.md`](VERSIONED_VALIDATION.md) |
| keyboard protocol | [`KEYBOARD_CONFORMANCE.md`](KEYBOARD_CONFORMANCE.md) |
| Sol／Lunaの責任境界 | [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) |
| release前の確認 | [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) |
| 公開リリース手順と依存境界 | [`PUBLIC_RELEASE.md`](PUBLIC_RELEASE.md) |
| 要求仕様 | [`../REQUIREMENTS.md`](../REQUIREMENTS.md) |
| 対応・未対応範囲 | [`../firmware-validation/capability.json`](../firmware-validation/capability.json) |
| firmware target registry | [`../reference-projects/firmware-targets.json`](../reference-projects/firmware-targets.json) |

## 現行の次期実装計画

SDのRAW image、flash erase/program、`M-NESCO-S1`（`Picocalc_NESco`のdirect-boot SD/flash debug開始）、
host directory snapshot、boot2／warm resetをこの順序で段階的に実装し、最後に外部`uf2loader`の
end-to-end conformanceへ進む計画は
[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)が正典です。
U0（clean provenance・fixture・first-failure trace）、U1（RAW SD）、U2（flash erase/program）、
**M-NESCO-S1（`Picocalc_NESco`のdirect-boot SD/flash debug開始）**、U3-A（host directory ↔ RAW
pack/extract）は完了しました。現在はU3-B（runner-integrated directory snapshot）前です。M-NESCO-S1の証拠は
`../firmware-validation/evidence/m-nesco-20260813-01/`にあります。通常のdirect bootによる
アプリdebugは、この計画の前後で変わりません。

`NEXT1_PICOEDIT_BLIND_CONTRACT.md`とNEXT-3の3文書は、検証器がSHA-256を含めて読む凍結契約です。
作成時点の状態や「次は」が残っていても現在計画ではなく、改変して現在値へ合わせません。
NEXT-3の最終状態は`IMPLEMENTATION_STATUS.md`と`MILESTONES.md`、詳細な最終結果は
`NEXT3_SD_CMD8_CRC_CANDIDATE.md`を参照してください。

keyboard controllerのprotocol producer一次リファレンスはClockworkPi公式
[`Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)です。
利用者の環境では、公式repositoryを任意の場所へcheckoutして参照します。

## 歴史資料

R0〜R6、OPT0〜OPT3、NEXT-1〜NEXT-3、初期設計、性能実験、実機調査の長文は
[`history/README.md`](history/README.md)から参照します。

完了済みの実装計画、機能追加要求など、現在の運用手順ではない時点文書は
`history/`へ集約しています。代表例はheartbeat計画と、UF2Loader計画に統合された旧SD／flash要求です。
これらは当時の判断と要件を残すための資料であり、現行機能の有効化手順ではありません。

歴史資料に残る「次は〜」「未着手」は、その文書が作成された時点の判断です。現在の状態は
`IMPLEMENTATION_STATUS.md`、現在計画は`MILESTONES.md`を優先します。
歴史資料に現れる`~/pico_dvl/codex/build/...`は当時の一時生成先で、現在は退役しています。
現行の再生成先は、外部workspaceを用意した場合だけ、そのworkspaceのREADMEに従います。
外部workspaceが無い利用者は、上記の通常利用手順だけでアプリ生成・ビルド・検証を完了できます。

`firmware-validation/records/`、`hardware-validation/records/`、provenance、registryは
不変証拠または機械検証対象なので、文書整理を理由に移動しません。

これらのrecordに含まれる`notes.md`や`PROCEDURE.md`も、recordのSHA-256契約に含まれる場合は
作成時の内容を保持します。そのため古いproject-relativeな`build/`表記が残ることがあります。
現在のcheckout場所と再生成先は、外部workspaceを使う場合に限り、同workspaceのREADMEを正とします。
外部workspaceは歴史的なアプリ・校正ツールの再現用であり、`picocalc_emu`の実行時依存ではありません。
