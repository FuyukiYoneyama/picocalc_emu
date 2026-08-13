# PicoCalc エミュレーター利用ガイド

このディレクトリが、`picocalc_emu`を使ってPicoCalcアプリを作る人とAIの入口です。
通常のアプリ開発では、まずこのディレクトリの文書だけを読めば足ります。

実装の経緯、却下した最適化、実機相関の時点記録、検証器が読む凍結契約は、通常利用の前提では
ありません。必要な場合だけ、本文のリンクから個別に参照してください。

## 目的別に読む順番

| やりたいこと | 読む文書 |
|---|---|
| 初めてアプリを作る | [`QUICKSTART.md`](QUICKSTART.md) |
| host／firmwareで検証する | [`TESTING.md`](TESTING.md) |
| 画面やUARTを待ってキーを入れる | [`SCENARIOS.md`](SCENARIOS.md) |
| 複数の実行を同時に監視する | [`CONCURRENT_RUNS.md`](CONCURRENT_RUNS.md) |
| 次期SD／flash／UF2Loader計画を確認する | [`../docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](../docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md) |

## AIの実行ルール

AIは次の順序を変えません。

1. この`USER_GUIDE/README.md`を読む。
2. 新規アプリなら[`QUICKSTART.md`](QUICKSTART.md)で生成し、`app/`だけを変更する。
3. まずhostを実行し、hardware固有の確認が必要なときだけ[`TESTING.md`](TESTING.md)へ進む。
4. **登録済みtarget**と**新規BINの診断実行**を混同しない。正式な回帰判定は登録targetだけで行う。
5. LCD、SD、keyboard、PSRAM、audio APIを使うときは、下の最小API表に従う。BSP内部をコピーしない。
6. 通常の検証でGitHub Actionsを使わない。build／test／validationはローカルで行う。

### どの実行を選ぶか

| 状況 | 実行するもの | 結果の扱い |
|---|---|---|
| 生成直後・ロジック確認 | `picocalc.py test --mode host` | 高速なロジック確認 |
| 既存registry targetの再現 | `picocalc.py test --mode firmware --target ...` | pin付き正式回帰判定 |
| まだregistryにない新規BIN | backendの`picocalc-run` | 診断。正式target合格とは扱わない |

### BSP APIの最小表

アプリは`#include "picocalc/bsp.h"`を使い、最初に`picocalc::init()`を1回呼びます。

| 用途 | 公開APIの入口 |
|---|---|
| LCD | `picocalc::display::init/clear/fill_rect/set_window/write_pixels` |
| keyboard | `picocalc::keyboard::init/read_event` |
| SDのsector | `picocalc::sdcard::init/read_sectors/write_sectors` |
| FAT filesystem | `picocalc::filesystem::mount/open_read/open_write_truncate/read/write/...` |
| PSRAM | `picocalc::psram::init/read/write`、必要なら`psram::Buffer` |
| audio | `picocalc::audio::init/start/stop/write_sample` |

関数の引数・戻り値がこの表だけで足りない場合に限り、対応する公開headerまたは
[`../bsp/README.md`](../bsp/README.md)を参照します。`bsp/src/`、`bsp/vendor/`、生成headerを
アプリへコピーしたり直接編集したりしません。

## 最小の前提

- 対象はClockworkPi PicoCalcのRP2040構成です。
- `git clone`したcheckoutを使います。Download ZIPではprovenance検証が`cannot judge`になります。
- Python 3.9以降が必要です。生成・portable検証だけならPico SDKは不要です。
- RP2040へビルドするときだけPico SDKを指定します。
- firmware backendを使うときだけ、別repositoryの`picoem-picocalc`が必要です。
- `picocalc_emu_ext/`やPicoTetris等の外部アプリは、通常の新規アプリ開発には不要です。

## 現在の標準

- LCD: `pio-rgb565`
- SD: FAT32が既定、FAT16は明示指定
- 通常の正確性基準: firmware backendのSerial execution
- firmware runnerの入力: raw BIN（UF2／ELFの直接実行ではありません）
- 実機へ渡すときの通常経路: PicoCalcの`uf2loader`

対応範囲と未対応範囲を確認する必要がある場合だけ、機械可読の
[`capability.json`](../firmware-validation/capability.json)を参照してください。

## 通常利用で読まなくてよい場所

- [`../docs/history/`](../docs/history/README.md): 過去の経緯・却下実験・時点記録
- `../docs/NEXT*.md`、`../docs/R2_TEMPLATE_B_REPRODUCTION.md`: 検証器が読む凍結契約
- `../firmware-validation/records/`、`../hardware-validation/records/`: 不変の証拠

現在の状態だけを確認したい場合は[`IMPLEMENTATION_STATUS.md`](../docs/IMPLEMENTATION_STATUS.md)、
公開版の選択は[`VERSIONING.md`](../docs/VERSIONING.md)を参照します。

UF2Loader計画は**未着手の設計計画**です。実施順序はU0 → U1（SD RAW） → U2（flash） →
M-NESCO（`Picocalc_NESco`のdirect-boot debug開始） → U3（directory snapshot） → U4 → U5 → U6です。
計画書が`docs/`直下にあることは、現在のCLIで
`--sd-image`、`--sd-dir`、flash erase/program、boot2起動が使えることを意味しません。
実装状況は常に[`capability.json`](../firmware-validation/capability.json)を優先します。
