# picocalc_emu — エミュレーターを使ったPicoCalc開発環境

ClockworkPi PicoCalc（RP2040／Pico 1）向けアプリを、PC上で作成・ビルド・実行・観測・検証し、
必要な実機確認へつなぐプロジェクトです。人間とAIが、画面、キー入力、UART、SDなどの挙動を
確認しながらアプリを修正できる開発環境を提供します。

## PicoCalcアプリを開発する

1. [クイックスタート](USER_GUIDE/QUICKSTART.md)でアプリを生成し、Canonical BSPを使って実装する。
2. [host検証](USER_GUIDE/TESTING.md)でアプリロジックを確認する。
3. Pico SDKでBIN／UF2をビルドし、RP2040エミュレーターでBINを実行する。
4. [scenario](USER_GUIDE/SCENARIOS.md)で画面・UARTを観測し、キー入力と期待結果を再現する。
5. report、UART、画像、実行条件を保存して修正前後を比較し、必要な項目を[実機で確認](docs/HARDWARE_IN_THE_LOOP.md)する。

通常の入口は **[USER_GUIDE](USER_GUIDE/README.md)** です。
エミュレーター本体や検証基盤を変更する場合は[DEVELOPER_GUIDE](DEVELOPER_GUIDE.md)を使います。

## 構成と責任範囲

| 構成 | 開発での役割 |
|---|---|
| このrepoのBSP・templates・Python CLI | 動作実績のある構成からアプリを作り、ビルドと検証を行う |
| host backend | アプリロジックをPC上で確認する。RP2040周辺回路の検証とは区別する |
| 別repo [picoem-picocalc](https://github.com/FuyukiYoneyama/picoem-picocalc) | RP2040命令とPicoCalcデバイスをエミュレートし、raw BINを実行する |
| scenario・target registry・検証記録 | 入力、期待結果、使用版、バイナリを固定して回帰を判定する |
| 実機相関・HIL | 実シリコン、画面の見え方、聴感、物理操作などを補完確認する |

アプリ固有の実装は生成先のappへ置きます。LCD／SD／keyboard／PSRAMの初期化を
アプリごとにコピーし直さず、[BSP公開API](bsp/README.md)を使います。
[外部workspace](docs/EXTERNAL_WORKSPACE.md)は既存アプリや過去の実機試験の再現用で、
通常の新規アプリ開発には不要です。

## 開始例

Python 3.9以降を使用します。provenance検証にはGit metadataが必要なためgit cloneで取得します。
生成とportable検証にはPico SDKは不要で、RP2040向けビルド時に指定します。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output /absolute/path/to/MyApp
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project /absolute/path/to/MyApp
python3 tools/picocalc.py verify-project --project /absolute/path/to/MyApp
```

生成したBINの診断実行と登録targetの正式回帰は[検証手順](USER_GUIDE/TESTING.md)に従います。
登録targetには指定されたbackend commitが必要です。同じtreeでもcommit pinを省略できません。

## 現在使う版と対応範囲

- BSP sourceは0.9.0、標準機能の実機相関baselineは0.8.8。
- 標準LCDはPIO RGB565、SDはFAT32、firmware検証の基準はSerial実行。
- 公開backend mainは2026-09-11時点で32d27ff（旧e985a9dと同一tree）。
- machine API、preview、追加音声解析、外部I2C、loader等の過去の受入は、それぞれの固定backendに対応します。公開mainで全部が使えるという意味ではありません。
- 対応機能は[現在の実装状況](docs/IMPLEMENTATION_STATUS.md)とtargetの固定版で確認します。

[対話preview](USER_GUIDE/PREVIEW_GUI.md)は対応する固定backendとreceiptが必要な追加経路です。
基本の開発はBIN実行、scenario、UART、snapshotで行えます。実時間1倍速は保証していません。

## 文書と証拠

| 目的 | 入口 |
|---|---|
| アプリを作り、実行・検証する | [USER_GUIDE](USER_GUIDE/README.md) |
| プロジェクトの目的・構成・完了の考え方 | [プロジェクト体系](docs/PROJECT_OVERVIEW.md) |
| 現在の対応範囲と版を確認する | [実装状況](docs/IMPLEMENTATION_STATUS.md)、[版管理](docs/VERSIONING.md) |
| エミュレーターや検証基盤を保守する | [開発者ガイド](DEVELOPER_GUIDE.md)、[AI運用](AI_START_HERE.md) |
| 契約と再現可能な証拠を調べる | [文書案内](docs/README.md)、[target registry](reference-projects/firmware-targets.json) |
| 終了した取り組みを調べる | [履歴](docs/history/README.md)、[作業台帳](docs/MILESTONES.md) |

UX 1倍速・高速化・性能復旧の取り組みは、目標未達により**失敗したプロジェクトとして終了**しました。
[失敗総括と履歴](docs/history/performance/README.md)に経緯・旧計画・証拠をまとめています。
公開版の旧状態への復旧は原状回復です。この開発環境の目的や現行作業を、高速化計画で定義しません。
