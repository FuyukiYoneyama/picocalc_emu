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
| 次の任意I2C外部module計画（RTC/環境sensor） | [`I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md) |
| M-NESCO拡張の実行証拠・完了記録 | [`M-NESCO evidence`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)、[`完了済み契約`](history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md) |
| SD-GEN-1汎用SD protocol計画・P5判断 | [`SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)、[`P5 validation contract`](../firmware-validation/contracts/sd-gen1-p5-validation-v1.json)、[`P5 decision evidence`](../firmware-validation/evidence/sd-gen1-p5-20260823-01/) |
| SD-GEN-1-P0 初回autostart trace（履歴） | [`historical trace`](../firmware-validation/evidence/sd-gen1-p0-20260823-01/) |
| SD-GEN-1-P0 完了record（M-NESCO A/B・FAT16/FAT32） | [`P0 completed evidence`](../firmware-validation/evidence/sd-gen1-p0-20260823-02/) |
| SD-GEN-1のP0〜P2詳細記録 | [`history/sd-gen1/`](history/sd-gen1/)、[`machine-readable contracts`](../firmware-validation/contracts/) |
| SD-GEN-1-P3 replay／negative／既存回帰 | [`P3 evidence`](../firmware-validation/evidence/sd-gen1-p3-20260823-01/)、[`validation contract`](../firmware-validation/contracts/sd-gen1-p3-validation-v1.json) |
| SD-GEN-1-P4 default runtime／代表E2E回帰 | [`P4 evidence`](../firmware-validation/evidence/sd-gen1-p4-20260823-01/) |
| U6実uf2loader end-to-endの契約・実測結果 | [`U6 evidence`](../firmware-validation/evidence/uf2loader-u6-20260822-01/)、[`完了済み契約`](history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md) |
| 性能micro-optの現行計画 | [`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md) |
| 現行backend変更の修正・検証順序 | [`picoem-picocalc/docs/BACKEND_CHANGE_VALIDATION_PLAN.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/BACKEND_CHANGE_VALIDATION_PLAN.md) |
| OPT4候補の試作・A/B記録 | [`history/opt4/`](history/opt4/) |
| OPT4 bank判定・残件 | [`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md) |
| 完了済み計画・実験記録の一覧 | [`history/README.md`](history/README.md) |
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

## 現行計画（U0〜U6／M-NESCO拡張／SD-GEN-1 P0〜P5完了）

SDのRAW image、flash erase/program、`M-NESCO-S1`（`Picocalc_NESco`のdirect-boot SD/flash debug開始）、
host directory snapshot、boot2／SD trace／warm resetを依存関係に沿って段階的に実装し、最後に外部`uf2loader`の
end-to-end conformanceへ進む計画は
[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)が正典です。
U0（clean provenance・fixture・first-failure trace）、U1（RAW SD）、U2（flash erase/program）、
**M-NESCO-S1（`Picocalc_NESco`のdirect-boot SD/flash debug開始）**、U3-A（host directory ↔ RAW
pack/extract）とU3-B（runner-integrated directory snapshot）は完了しました。U4-P2では`--sd-trace`による
diagnostic-only SD protocol traceをclean loaderで3回採取し、CMD17のみ（CMD18/CMD12等は未観測）と判定しました。
CMD17のR1順序だけを修正しました。固定版uf2loaderのU4受入ではmulti-block production codeを追加していませんが、
SD-GEN-1 P4で別のbounded multi-block surfaceをdefault runtimeへ接続しました。U5-A boot2 entry、U5-B
watchdog warm reset、U6の実uf2loader end-to-end Gate、M-NESCO拡張受入まで完了しています。U6の契約と
実測結果は[`U6 evidence`](../firmware-validation/evidence/uf2loader-u6-20260822-01/)に固定し、完了済みの契約記録は
[`history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md)に、機械可読な
証拠は`../firmware-validation/evidence/uf2loader-u6-20260822-01/`に保存しています。
U4の実装判断は[`history/uf2loader/UF2LOADER_U4_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U4_PREFLIGHT_20260822.md)、U5-Aの実装・受入境界は
[`history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md)、U5-Bの実装前契約は
[`history/uf2loader/UF2LOADER_U5B_WATCHDOG_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U5B_WATCHDOG_PREFLIGHT_20260822.md)に固定しています。M-NESCO-S1の証拠は
`../firmware-validation/evidence/m-nesco-20260813-01/`にあります。通常のdirect bootによる
アプリdebugは、この計画の前後で変わりません。

U5-Bの受入後に行った、複数mapper・ROM容量・PRG／CHR境界read・CPU／core 1／DMA経路・flash再attachの
**M-NESCO拡張受入**は完了しています。契約とfixture／provenance／fail-closed条件は
[`history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md)に固定しています。
実行証拠は[`../firmware-validation/evidence/m-nesco-ext-20260822-01/`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)にあります。このgateは`uf2loader-e2e`へ昇格せず、U6とは独立した固定LCD fixtureの受入です。
U6は、boot2→stage3→SD上の`BOOT2040.UF2`→アプリUF2のerase/program→watchdog warm reset→
書込み後app起動を同一artifactで通す最終gateです。固定source／artifactに限定した`uf2loader-e2e`
capabilityを有効化し、USB BOOTSEL/MSCと任意UF2互換は未対応のままです。

M-NESCO拡張の計画4ケース＋追加1ケースを越える汎用化として進めた
SD-GEN-1（uf2loader以外のアプリも対象にした汎用SD protocol一般化）は、P0〜P5まで完了しています。
複数ブロック、CRC／token／CS境界、read/write、unknown/errorのfail-closed、代表アプリ回帰を確認し、
P5でversioned validation contractと限定範囲の`sd-multi-block` capabilityを受け入れました。
詳細計画は[`SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)に固定し、P0のtrace棚卸し、
P1のwire契約・受入マトリクス、P2のfeature-gated最小state machine、P3のtrace replay／negative report統合／凍結回帰、
P4のdefault runtime接続と代表E2E回帰、P5のversioned validation／capability判断を完了しています。
P1のmachine-readable契約は
[`sd-gen1-p1-wire-v1.json`](../firmware-validation/contracts/sd-gen1-p1-wire-v1.json)、P2のvectorは
[`sd-gen1-p2-vectors-v1.json`](../firmware-validation/contracts/sd-gen1-p2-vectors-v1.json)です。P2の詳細作業記録は
[`history/sd-gen1/`](history/sd-gen1/)へ移し、P2実装時点では通常runtime／runnerへ接続していませんでしたが、
P4でdefault runtimeへ昇格しました。P4の代表E2EはCMD18→2 block→CMD12、CMD23/CMD25→1 block write→CMD17 readbackを実SPI0経路で実行し、RAW exportのbyte一致も確認しています。同じclean backendで3回再実行し、安定report項目・trace・exported imageが一致しました。既存U6／M-NESCO／FAT16／FAT32の凍結clean traceも再playしています。
versioned targetと固定版`uf2loader-e2e`は変更していません。次の作業は、新しい正式計画が立つまで保留です。

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
