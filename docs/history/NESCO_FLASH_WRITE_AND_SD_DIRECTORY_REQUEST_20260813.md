# flash program/erase と SD ディレクトリマウントの機能追加依頼

作成日: 2026-08-13
起票: Codex（`Picocalc_NESco` 側の検証計画から）
対象: `picocalc_emu` host / firmware backend
状態: **依頼のみ。** 実装・変更は未実施。

## 1. 要旨

2 つの機能を依頼する。

| capability | 現状 | 依頼 |
|---|---|---|
| `flash-chip-commands` | erase / program は deliberately absent | **実装してほしい** |
| `sd-card` | raw-image persistence / directory-backed storage とも無し | **指定ディレクトリを SD カードとしてマウントできるようにしてほしい** |

両方とも `firmware-validation/capability.json` に限定事項として記録されている。**ただし、限定事項として記録されていることは要件が満たされていることを意味しない。** 本書は、その限定を置いた判断の前提が現在は成立していないこと、および要件が実在することを報告する。

## 2. 消費者

`Picocalc_NESco`（`nes2/Picocalc_NESco`）。PicoCalc 上の NES エミュレーターで、`picocalc_emu` を検証環境として使っている。Mapper 4 / 7 / 9 の検証をこの環境で完了し、現在 Mapper 19 と Mapper 30 の検証を進めている。

## 3. flash program / erase

### 3.1 限定の根拠が成立していない

```
id         : flash-chip-commands
limitation : Erase and program are deliberately absent: nothing in the conformance
             track writes flash, and a half-modelled program path would corrupt the
             XIP image rather than fail visibly.
```

根拠の前半「**nothing in the conformance track writes flash**」は、conformance track の選択によって成り立っている記述であり、flash 書き込みを必要とする消費者が存在しないことの証拠ではない。実際に存在する。

`nes2/Picocalc_NESco/platform/rom_image.c`:

```c
#include "hardware/flash.h"                                   // 49 行
flash_range_erase(flash_offs, count);                         // 821 行
flash_range_program(flash_offs, data, count);                 // 829 行
rom_flash_range_program_locked(XIP_ROM_OFFSET + written, page_buf, FLASH_PAGE_SIZE);  // 798 行
```

**SD から選んだ ROM を内蔵 flash の XIP 領域へ書き込む経路**であり、実機ではこれが通常の ROM 投入手段である。

### 3.2 現在の回避策とその代償

検証はこの経路を回避し、ROM を raw flash image として事前に埋め込んでいる。firmware から見ると「最初からそこにある」状態を作っている。

その結果、

- ROM メニューから ROM を選ぶ
- flash へ erase / program する
- 書き込んだ ROM で起動する

という**実機の主要動線が、エミュレーターで一度も実行されていない。** これは検証されていない範囲として無期限に残り、実機でしか触れられない。回避策は検証の代わりにならない。

### 3.3 実装方針についての依頼側の考え

限定事項が挙げる「a half-modelled program path would corrupt the XIP image rather than fail visibly」という懸念は妥当である。**ただしこれは実装方法の制約であって、実装しない理由にはならない。** 依頼側としては次で構わない。

- 未対応のアドレス範囲・アライメント・セクタ境界違反は、**黙って壊さず明示的に error として報告する**
- 段階導入でよい。まず `flash_range_erase` と `flash_range_program` の 2 つ
- 導入初期は opt-in でよい。ただし**最終的には既定で有効な機能**として扱ってほしい

silent corruption を避けるという設計判断には全面的に同意する。visible failure であれば要件を満たす。

## 4. SD カードのディレクトリマウント

### 4.1 現状

```
id         : sd-card
limitation : There is no multi-block transfer, CSD/CID beyond bring-up, removal,
             write-protect, raw-image persistence or directory-backed storage, ...
```

`bsp/host/src/sdcard.cpp` は `std::vector<uint8_t> g_sectors` のメモリ内実装で、`format_sd(SdFormat)` が毎回まっさらに再フォーマットする。公開 API は `sd_sector_count()` / `sd_sectors_read()` / `sd_sectors_written()` / `format_sd()` のみ。CLI は `--sd --sd-format <fat32|fat16>` のみ。

**イメージの投入も、run をまたぐ保持も、ファイル単位の準備も、いずれもできない。**

### 4.2 依頼内容

**ホスト上の指定ディレクトリを SD カードとしてマウントできるようにしてほしい。**

```
--sd-dir <path>
```

- 起動時、そのディレクトリの内容が SD カード上に見える
- run 中に firmware が書いたファイルが、run 終了後にそのディレクトリで**通常のファイルとして読める**
- 中間形式（raw image）を経由しない

raw image の入出力は、これに比べて中途半端である。イメージを組み立てる道具と、走らせた後にイメージから FAT を解析してファイルを取り出す道具が、依頼側と依頼先の双方に必要になる。**検証のたびにその往復が発生するなら、機能として成立していない。**

### 4.3 既存設計との整合について

`bsp/host/src/sdcard.cpp` の冒頭コメントは、SD をブロックデバイスとして実装することで `src/filesystem.cpp` と `src/fatfs_diskio.cpp` を経由させ、**実際のファイルシステム層を検証対象に含める**意図を述べている。これは正しい設計であり、崩すべきではない。

したがって依頼は「FatFs を迂回してホスト FS へ直結する」ことではない。**入口と出口だけをディレクトリにし、内部は現在どおりブロックデバイスと Chan FatFs を通す**形を想定している。起動時にディレクトリから FAT ボリュームを構成し、終了時に書き戻す実装であれば、ファイルシステム層の検証価値を保ったまま要件を満たす。

実装方法は依頼先の判断に委ねる。要件は「ディレクトリで入れて、ディレクトリで出る」ことである。

### 4.4 現在の要件

`Picocalc_NESco` はセーブデータを SD へ書く（`platform/sram_store.cpp`、Chan FatFs 経由）。

- 通常のバッテリーセーブ: `*.srm`
- Mapper 30 の PRG flash overlay: `*.m30`

| 必要な操作 | 現状 | 影響を受けている工程 |
|---|---|---|
| 既存のセーブファイルを置いた状態で起動する | **不可** | Mapper 19 Phase 7「既存 8192 byte `.srm` を読み、内容が変わらない」 |
| 書き込んだ内容が次の run に残る | **不可** | Mapper 19 Phase 7「保存・再起動・復元」、Mapper 30 P4「`.m30` の保存・再起動・復元」 |
| 書き込まれたファイルを直接検査する | **不可** | 上記すべての結果確認 |

**両検証計画に、現状では実行できない合格条件が入っている。**

なお同一 run 内であれば ROM 切替（A → B → A）で flush と restore の経路を通せる。`sram_store.cpp` は `[M30] flush path=… slots=…` / `[M30] restore path=… slots=…` を出すため、ファイル形式の往復は観測できる。**これは代替手段であって、要件の充足ではない。**

## 5. 優先度

**4（SD ディレクトリマウント）を優先してほしい。** 2 つの検証計画の合格条件を直接不可能にしている。3（flash）は実機動線が未検証のまま残る問題で、現在の工程を止めてはいないが、放置すれば恒久的な未検証範囲になる。

いずれも入らない場合、依頼側は合格条件を縮小し、該当範囲を「エミュレーターでは検証不能・実機のみ」として両計画へ記録する。**ただしこれは要件が消えたのではなく、検証されない範囲が増えたという記録である。**

## 6. 参考

- `nes2/Picocalc_NESco/platform/rom_image.c`（flash program/erase の使用箇所）
- `nes2/Picocalc_NESco/platform/sram_store.cpp`（`.srm` / `.m30` の SD 書き込み）
- `nes2/mapper_check/mapper19_validation/IMPLEMENTATION_PLAN_20260812.md` Phase 7
- `nes2/mapper_check/mapper30_validation/GAP_AND_PLAN_20260813.md` P4
- `nes2/Picocalc_NESco/docs/design/OBSERVABILITY_INFRASTRUCTURE_PLAN_20260813.md`（同時に起票した `Picocalc_NESco` 側の観測基盤依頼。本書とは別件）
