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
| SDのdirectoryとRAW imageを往復する | [`SD_IMAGES.md`](SD_IMAGES.md) |
| 次期SD／flash／UF2Loader計画を確認する | [`../docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](../docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)、[`U5-A boot2 実装・受入`](../docs/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md)、[`U4 preflight`](../docs/UF2LOADER_U4_PREFLIGHT_20260822.md) |
| U5-B watchdog warm resetの実装前契約を確認する | [`U5-B preflight`](../docs/UF2LOADER_U5B_WATCHDOG_PREFLIGHT_20260822.md) |
| M-NESCO拡張受入の契約・結果を確認する | [`M-NESCO拡張 evidence`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)、[`preflight契約`](../docs/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md) |
| SD-GEN-1の実装計画を確認する | [`SD-GEN-1 plan`](../docs/SD_GEN1_IMPLEMENTATION_PLAN_20260823.md) |
| SD-GEN-1-P0の現状棚卸しを確認する | [`SD-GEN-1-P0 inventory`](../docs/SD_GEN1_P0_INVENTORY_20260823.md) |
| 実uf2loader end-to-endの実装前契約を確認する | [`U6 preflight`](../docs/UF2LOADER_U6_PREFLIGHT_20260822.md) |

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
- SDの事前／事後処理には、このrepositoryの`tools/picocalc.py sd pack/extract`を使います。
- `picocalc_emu_ext/`やPicoTetris等の外部アプリは、通常の新規アプリ開発には不要です。

## 現在の標準

- LCD: `pio-rgb565`
- SD: FAT32が既定、FAT16は明示指定
- 通常の正確性基準: firmware backendのSerial execution
- firmware runnerの入力: raw BIN（UF2／ELFの直接実行ではありません）
- 実機へ渡すときの通常経路: PicoCalcの`uf2loader`
- エミュレーターでRAW SD／flash mutationを検査する場合: firmware backendの明示的な診断CLI

SD RAW imageの標準的な作成・取り出し手順は[`SD_IMAGES.md`](SD_IMAGES.md)にあります。

対応範囲と未対応範囲を確認する必要がある場合だけ、機械可読の
[`capability.json`](../firmware-validation/capability.json)を参照してください。

## 通常利用で読まなくてよい場所

- [`../docs/history/`](../docs/history/README.md): 過去の経緯・却下実験・時点記録
- `../docs/NEXT*.md`、`../docs/R2_TEMPLATE_B_REPRODUCTION.md`: 検証器が読む凍結契約
- `../firmware-validation/records/`、`../hardware-validation/records/`: 不変の証拠

現在の状態だけを確認したい場合は[`IMPLEMENTATION_STATUS.md`](../docs/IMPLEMENTATION_STATUS.md)、
公開版の選択は[`VERSIONING.md`](../docs/VERSIONING.md)を参照します。

UF2Loader計画ではU0（provenance）、U1（RAW SD）、U2（flash erase/program）、
M-NESCO-S1（`Picocalc_NESco`のdirect-boot SD/flash debug開始）まで完了しています。
host側のU3-A（directory ↔ RAW pack/extract）とU3-B（runner-integrated directory snapshot）も完了しています。
M-NESCO-S1は、`--sd-image`と`--flash-image-out`を使うbackend診断経路を提供し、U3-Bでは
`picocalc.py test --mode firmware --sd-dir`を追加しました。`--sd-dir`は起動時の一回限りの
FAT32 snapshotであり、boot2、watchdog、実`uf2loader` end-to-endを意味しません。実施順序と証拠は
[`../docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](../docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)を参照してください。
U4-P2では`picocalc-run --sd-trace <path>`によるdiagnostic-only SD traceをclean loaderで3回取得し、
CMD17のみ（CMD18／CMD12／CMD23／CMD24／CMD25は未観測）と判定しました。CMD17のR1順序だけを修正しました。
SD-GEN-1-P4でmulti-block production codeをdefault runtimeへ接続し、CMD18/CMD12 read、CMD23/CMD25 write、CMD17 readbackの実SPI0 synthetic
E2Eを追加しています。U5-B watchdog warm reset、U6実uf2loader end-to-end
Gateまで完了しています。M-NESCO拡張受入も計画4ケース＋追加mapper 1のローカルA/B deterministic gateを完了しています。
trace取得条件と実装判断表は[`../docs/UF2LOADER_U4_PREFLIGHT_20260822.md`](../docs/UF2LOADER_U4_PREFLIGHT_20260822.md)、
boot2の実装境界は[`../docs/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md`](../docs/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md)にあります。
U5-Bの受入後に行う、複数mapper／ROM容量、PRG／CHR境界、CPU／core 1／DMA read、flash export後の再attachの
M-NESCO拡張受入の契約と結果は
[`../docs/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md`](../docs/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md)です。
実行証拠は[`../firmware-validation/evidence/m-nesco-ext-20260822-01/`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)です。
このgateは`uf2loader-e2e`へ昇格するものではありません。U6は固定LCD fixtureで先に
Gateを閉じています。
M-NESCO拡張受入後のSD-GEN-1（uf2loader以外のアプリも対象にした汎用SD protocol）は、複数ブロック、
CRC／token／CS境界、read/write、unknown/errorのfail-closed、代表アプリ回帰まで実装・回帰済みです。
実装順序と受入条件は[`../docs/SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](../docs/SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)を正典とし、
P0〜P4は完了、次はP5のversioned validationとcapability判断です。
U6の実装前契約は[`../docs/UF2LOADER_U6_PREFLIGHT_20260822.md`](../docs/UF2LOADER_U6_PREFLIGHT_20260822.md)です。
U6-P0の標準 `picocalc.py uf2 inspect/assemble` は実装済みで、UF2からraw XIP flash imageを
決定的に生成できます。U6 Gateは`python3 tools/picocalc.py uf2 e2e`で実行し、cleanなexternal
uf2loader source／artifactとbackendを明示して同一入力を3回検証します。UF2 strict検査、loader／boot2
保護領域、erase/program readback、watchdog reset、SD trace、UART、report、framebuffer、flash SHA、
再attachを合格させた証拠は[`../firmware-validation/evidence/uf2loader-u6-20260822-01/`](../firmware-validation/evidence/uf2loader-u6-20260822-01/)にあります。
これは固定source／artifactの限定経路であり、USB BOOTSEL/MSCや任意UF2互換を意味しません。
実装状況は常に[`capability.json`](../firmware-validation/capability.json)を優先します。
