# M-NESCO 拡張受入 preflight

作成日: 2026-08-22
対象: `picocalc_emu` / `picoem-picocalc` / `nes2/Picocalc_NESco`
状態: **実装前の準備・受入契約。production code、target registry、capability、実行証拠は未変更**

この文書は、[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](../../UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)
の M-NESCO-S1 を拡張するための契約と実行結果である。U5-B watchdog warm reset完了後に実装・受入した。
この段階では `uf2loader supported` へ昇格しない。USB BOOTSEL/MSC、実 `uf2loader` end-to-end、
NESco のmapper互換性全般を宣言するものでもない。

## 1. 目的と境界

M-NESCO-S1 で確認済みなのは、1種類のNESco実行について、FAT32 RAW SDからROMを選び、
大きなROMをflashへerase/programし、XIPから実行し、flashをexportできることである。
拡張受入では、次の主張を**同一入力、同一BIN、同一clean backend**で再現可能にする。

1. 複数mapperを通したROM実行。
2. 小・中・大容量ROMを通したRAM／flash staging境界の確認。
3. PRG／CHRの先頭・中間・末尾を決めたサンプル読み出し。
4. CPU instruction fetch、CPU data read、core 1、DMAの各読み出し経路。
5. run A のflash exportをrun Bの初期flashへ再attachして同じROMを起動。
6. 独立run間でのflash SHA-256一致。
7. SD sourceのROM file SHA-256と、firmwareが読み実行したROMのSHA-256一致。

「画面が出た」「menuから起動できた」だけでは合格にしない。要求した読み出し経路を実際に
通った marker／counter／digest が無い場合は `cannot_judge` または FAIL とし、成功扱いにしない。

## 2. 実装前に確認済みの事実

### 2.1 NESco source

2026-08-22 の調査時点で `nes2/Picocalc_NESco` は次の状態だった。

| 項目 | 値 |
|---|---|
| source HEAD | `7e5c89bbc985626d4ff87aa110119284fa379f23` |
| worktree | clean |
| version banner | `1.2.4` |
| active emulator | `infones` static library（旧 `core/` はactive target外） |
| mapper table | `InfoNES_Mapper.cpp` に多数のmapper entry（139 entryを確認） |
| ROM loading | `sd:/`、または `flash:` XIP。小さいROMはRAM、大きいROMはXIP staging |
| XIP staging offset | `0x00080000`（metadata sectorを含む） |
| XIP data offset | `XIP_ROM_OFFSET + FLASH_SECTOR_SIZE` |
| XIP size limit | `PICO_FLASH_SIZE_BYTES - XIP_ROM_DATA_OFFSET` |

現在の `[ROM_START]` log は mapper、PRG 16-KiB page数、CHR 8-KiB page数、battery、trainerを出すが、
ROM file SHA-256、NES 2.0 submapper、各境界sample digestは出さない。また、flash metadataは
file name、source path、file size、mapperを保持するが、ROM SHA-256を保持しない。したがって、
拡張受入の前に、test-only oracle／diagnostic markerまたはrunner側のmanifest照合を追加する必要がある。
この不足を補わずに「SD sourceとROM SHAが一致した」と記録してはならない。

### 2.2 現在の経路の意味

- NES CPUのPRG fetch/data readは、`InfoNES_ReadRom()`が設定する `ROM`／`ROMBANK` を通る。
- CHR readはPPU／mapperの `VROM`／CHR-RAM 経路を通る。CHR-RAM（headerのCHR page数が0）の場合は
  CHR-ROM境界readを適用できないため、`not_applicable` を明示する。
- NEScoのcore 1 workerは主にkeyboard/LCDを処理し、LCD DMAはpixel bufferをPIOへ送る。
  現在のproduction codeからは「core 1またはDMAがNES ROM bytesを直接読む」ことは確認できない。
  よって、これらを合格項目にするには、XIP上の既知領域を読む test fixture／diagnostic probe を
  明示的に実行し、その経路をUART/reportへ記録する。NEScoの通常画面更新をROM readの証拠にしない。

## 3. 入力fixtureとサイズ分類

ROMは公開repositoryへ同梱しない。利用許諾のあるROM、または自作の最小fixtureだけを使用し、
recordにはsource／生成方法／SHA-256を残す。外部 `nes2/mapper_check` の成果物は、そのmanifestと
source provenanceを確認してから個別入力に採用する。ファイルが無い、SHAが一致しない、出所が不明な
場合はそのcaseを実行せず `input_missing` とする。

### 3.1 必須caseの最小集合

最低4 caseを用意する。mapper番号は例ではなく、実際に採用するfixtureのiNES/NES 2.0 headerから
確定し、manifestへ固定する。

| case | 役割 | mapperの選定方針 | サイズ経路 |
|---|---|---|---|
| `mnesco-m0-small` | 非banked基準 | NROM／mapper 0 | RAM pathの上限内 |
| `mnesco-m2-medium` | PRG bank切替 | UNROM系（例 mapper 2） | flash staging開始後 |
| `mnesco-m4-large` | PRG/CHR bank・IRQ | MMC3系（例 mapper 4） | 大容量XIP staging |
| `mnesco-m30-large` | NEScoで既に実機確認したbanked系 | mapper 30、または同等の既存fixture | flash/XIP・banked read |

上記の番号を実行可能なROMが無い場合、別mapperへ勝手に置き換えない。`candidate` として保留し、
合法なfixtureが固定できてから実行する。mapper全種類の互換性をこのgateへ持ち込まない。

### 3.2 サイズの定義

サイズはROMファイル全体（iNES/NES 2.0 header、trainer、PRG、CHRを含む）で分類する。

- **small**: `<= 16 + 512 + 32 KiB + 8 KiB`。現行 `Mapper 0` RAM pathの上限（`MAPPER0_ROM_IMAGE_MAX_SIZE`）内。
- **medium**: smallより大きく、`512 KiB`以下。SDからflash stagingへ移る境界を通す。
- **large**: `512 KiB`より大きく、`XIP_ROM_MAX_BYTES`以下。実buildの
  `PICO_FLASH_SIZE_BYTES` と `XIP_ROM_DATA_OFFSET` をmanifestへ記録する。

`XIP_ROM_MAX_BYTES`を超えるROMは、このgateでは「大容量の合格」ではなく、明示的な容量FAILとする。
容量上限を変えるためにfirmware layoutを同時変更しない。

## 4. ROM境界sampleと読み出し経路

各caseのmanifestに、headerから計算した次のoffsetを保存する。

```text
file_header = 16
trainer      = (flags & 0x04) ? 512 : 0
prg_start    = file_header + trainer
prg_size     = prg16 * 16 KiB
chr_start    = prg_start + prg_size
chr_size     = chr8 * 8 KiB
```

`first`、`middle = floor((size - 1) / 2)`、`last = size - 1` の3点を、PRG／CHRそれぞれで
sampleする。sampleの値そのものと、順序付きのSHA-256をUART/reportへ出す。bank切替mapperでは、
bank切替前後の同じCPU/PPU論理addressについて、選択bankと戻り値も記録する。

各caseは次の経路表を満たす。

| 経路 | 必須証拠 |
|---|---|
| CPU instruction fetch | PRG上のfixture codeを実行したfetch count／digest |
| CPU data read | PRGのfirst/middle/lastをoperandまたは明示readで取得した値 |
| PPU/CHR read | CHR first/middle/last、またはCHR-RAMなら明示 `not_applicable` |
| core 1 XIP probe | core 1から既知XIP範囲を読むmarker／digest |
| DMA XIP probe | DMA sourceをXIPへ設定し、既知範囲の転送結果を読むmarker／digest |

core 1／DMA probeがNESco production codeに無い間は、test-only fixtureを用いる。LCD DMAの
framebuffer転送や、CPUがflash上の命令を実行した事実だけを、DMA／core 1 XIP readの代用にしない。

## 5. provenance manifest

各caseは次の情報を1つのJSON manifestへ固定する。hostの絶対pathは記録せず、basenameとSHAだけを残す。

```json
{
  "schema": 1,
  "case_id": "mnesco-m2-medium",
  "nesco": {"commit": "<40-hex>", "dirty": false, "version": "1.2.4"},
  "firmware": {"bin_sha256": "<64-hex>", "uf2_sha256": "<64-hex>"},
  "backend": {"commit": "<40-hex>", "dirty": false},
  "sdk": {"path_identity": "<commit-or-tree>", "toolchain": "<record>"},
  "rom": {
    "file": "TEST.NES",
    "sha256": "<64-hex>",
    "bytes": 0,
    "format": "ines1|nes20",
    "mapper": 0,
    "submapper": 0,
    "prg_bytes": 0,
    "chr_bytes": 0,
    "trainer": false,
    "samples": {"prg": {}, "chr": {}}
  },
  "sd": {
    "format": "fat32",
    "tree_sha256": "<64-hex>",
    "image_sha256": "<64-hex>",
    "rom_manifest_path": "<relative-path>"
  },
  "flash": {
    "capacity_bytes": 0,
    "before_sha256": "<64-hex>",
    "after_a_sha256": "<64-hex>",
    "after_b_sha256": "<64-hex>"
  }
}
```

`rom.sha256` はSD directory manifestの該当file SHAとfirmware側markerの両方に照合する。
`sd.image_sha256`だけではROM fileの同一性を証明できないため、SD image全体SHAをROM SHAの代用にしない。

## 6. 実行手順（run A / B / repeat）

### 6.1 Run A: SD sourceからstaging

各caseについて、同一のclean firmware BIN、FAT32 RAW image、scenario、clean backendで実行する。
典型的なrunner経路は次のとおりである（実装時にtarget contractの引数へ固定する）。

```sh
picocalc-run \
  --bin Picocalc_NESco.bin \
  --boot-mode app \
  --board picocalc --lcd-variant pio-rgb565 --psram --keyboard \
  --sd-image case-a.img \
  --flash-image-out case-a.flash.bin \
  --scenario case-a.json --json case-a.report.json --uart case-a.uart
```

Run Aで必須なのは、ROM menu選択、ROM SHA marker、PRG/CHR境界sample、CPU/core 1/DMA probe、
flash erase/program、scenario終了、unknown/exception 0件である。

### 6.2 Run B: export後の再attach

現行runnerは`--bin`をXIP初期imageとして読み込む。したがってRun Aの**全量2 MiB flash export**を
Run Bの`--bin`へ指定し、同じSD RAW imageをread-only attachする。`--bin`と`--flash-image-out`は
同一pathにしない。

```sh
picocalc-run \
  --bin case-a.flash.bin \
  --boot-mode app \
  --board picocalc --lcd-variant pio-rgb565 --psram --keyboard \
  --sd-image case-a.img \
  --flash-image-out case-b.flash.bin \
  --scenario case-b-reattach.json --json case-b.report.json --uart case-b.uart
```

Run Bは、flash metadataから復元された`flash:/` entryまたは明示した同一ROMを起動し、Run Aと
同じROM SHA、同じ境界sample、同じpath digestを得なければならない。Run B終了後の
`case-b.flash.bin`は`case-a.flash.bin`とbyte完全一致しなければならない。

### 6.3 独立repeat

同じRun A入力を新しい出力pathで最低2回実行し、次を比較する。

- flash before／after SHA-256
- SD image source SHA-256とROM file SHA-256
- ROM metadata、boundary sample、mapper bank digest
- report checks、UART marker、scenario timeline

比較用の出力pathを共有しない。run間でbackend、BIN、SDK、scenario、SD imageのいずれかが変わった
場合はdeterminism比較を成立させず、先にprovenance mismatchとして停止する。

## 7. 受入条件とfail-closed

### 必須合格条件

- 各必須caseが入力manifestのmapper／size classと一致する。
- backend `commit` が固定値と一致し、`dirty=false`。
- firmware BIN／UF2、NESco source、SDK／toolchain、SD tree／image、ROM file SHAが一致する。
- PRG／CHRのfirst/middle/last sampleが期待値・digestと一致する。
- CPU fetch、CPU data、PPU/CHR、core 1、DMAの要求経路がそれぞれ観測済みである。
- Run Aのflash exportをRun Bへ再attachできる。
- Run A repeat、Run Bのfinal flash SHAが要求どおりbyte一致する。
- scenario、UART、exception、unknown MMIO、SD unknown command、flash mutation errorが合格する。
- flash export／SD input／manifestのpath混同や同時書込みがない。

### 即時FAILまたはcannot_judge

- ROM file SHAがmanifest、SD tree、firmware markerのいずれかで不一致。
- mapper／submapper／PRG／CHRサイズがheaderとmanifestで不一致。
- boundary sampleの一つでも未観測、欠落、または順序が不明。
- core 1／DMAを単なるframebuffer転送で代用している。
- Run BがRun Aのexportを初期flashとして実際には読んでいない。
- flash final SHAが不一致、または比較対象のprovenanceが一致しない。
- cycle limit、exception、unknown command／MMIO、scenario failure、backend dirty。
- 容量上限超過、CHR-RAMをCHR-ROM合格として扱う、入力ROMの出所不明。

これらは「別の画面が出たが動いた」として救済しない。原因を修正して同じcaseを再実行する。

## 8. 証拠の保存場所と昇格境界

実装後の証拠は、次のようなcase単位のディレクトリへ保存する。

```text
firmware-validation/evidence/m-nesco-ext-YYYYMMDD-01/
  README.md
  manifest.json
  mnesco-m0-small/
    run-a.report.json  run-a.uart  run-a.flash.bin.sha256
    run-b.report.json  run-b.uart  run-b.flash.bin.sha256
  mnesco-m2-medium/
  ...
```

ROM、RAW image、BIN、UF2の大きな実体は原則Gitへ入れず、SHAと再生成／取得手順を保存する。
`records/*/report.json`へ登録する場合は、既存のschema／gate／milestone契約を満たすrecord設計を
先に行う。今回のpreflightではrecordやregistryを追加しない。

M-NESCO拡張の合格は、`Picocalc_NESco`をこの限定された複数caseでSD/flash debugに使えるという
意味だけである。現時点ではproduction code、fixture、実行証拠がなく未完了である。別fixtureで完了した
U6の`uf2loader-e2e` capabilityは、このM-NESCO拡張の代替でも、mapper全般の互換性宣言でもない。

## 9. 実装順序と工数見積り

U5-Bのclean受入後、次の順序でproduction codeを変更する。

1. **P0 入力manifest／ROM header parser** — mapper、submapper、PRG/CHR、size class、ROM file SHAを固定。
2. **P1 観測fixture／marker** — ROM SHA、boundary sample、CPU/PPU/core 1/DMA経路のdigestを追加。
3. **P2 case scenario** — 最小4 mapper/size caseとRun A/B、repeatを定義。
4. **P3 export／reattach harness** — full flash imageをRun Bへ渡し、SHA比較をfail-closed化。
5. **P4 local実行・証拠化** — clean backendで全caseを再生成し、report／UART／manifestを保存。
6. **P5 independent review** — source／ROM／SD／flash／path coverageの照合。合格後もU6へ昇格しない。

概算は **28〜46時間**（fixtureの出所確認、NESco側のdiagnostic marker追加、4 caseの複数run、
独立再検証を含む）。合法なROM fixtureが不足する場合、その調達・生成待ち時間は別である。
CI、GitHub Actions、実機操作はこのpreflightの検証手段にしない。通常はローカルで全て実行し、
実機相関が必要になった場合だけ別途承認を得る。

## 10. 実装・受入結果

M-NESCO拡張は**完了（2026-08-22、ローカル検証）**した。診断oracleとhost runnerを実装し、
計画caseのmapper 0／2／4／30（small／medium／large、mapper 4はPRG+CHR大容量）に加え、
mapper 1の追加caseを実行した。
各caseでRun Aを3回、XIP caseではA exportを初期flashへ再attachしたRun Bを3回実行し、
report、UART、SD trace、flash SHA、ROM identity、PRG／CHR境界sample、CPU／PPU／core 1／DMA
観測digestの決定性を確認した。詳細なmanifestとsanitized case recordは
[`../../../firmware-validation/evidence/m-nesco-ext-20260822-01/`](../../../firmware-validation/evidence/m-nesco-ext-20260822-01/)に固定している。

NESco診断変更はcommit `7f3fa05971930e03653694117cbf6a435ec1dd4e`へ固定し、clean sourceから
再buildしたBIN SHA-256は実行artifactと一致した。backendはcommit
`d1360cbb13fd807661474b49a1b5516b12567d00`でclean。GitHub Actionsは使用していない。

このPASSは固定した計画4ケース＋追加mapper 1のdirect-boot SD／flash／XIP debug範囲だけを示す。mapper全般、任意ROM、
USB BOOTSEL/MSC、`uf2loader supported`への昇格は宣言しない。次段階のSD-GEN-1（uf2loader以外も対象にした
汎用SD protocol一般化）は、別の計画・versioned validationとして固定してから着手する。
