# SD RAW image の作成と取り出し

PicoCalc の firmware backend は、SD を 512-byte sector の RAW image として受け取ります。
アプリのデバッグ前後に毎回 Python を書かなくて済むよう、`picocalc_emu` は決定的な FAT16／FAT32
pack／extract ツールを標準提供します。

## 基本の往復

通常は FAT32（既定、PicoCalc 付属 32 GB カードとの整合を優先）を使います。
次のコマンドは外部の `mkfs.fat`、`mcopy`、FAT ライブラリを必要としません。

```sh
cd /path/to/picocalc_emu

# directory tree -> input.img
python3 tools/picocalc.py sd pack ./sd-tree ./input.img \
  --format fat32 --size-mib 64 --json ./input.sd.json

# firmware backend を実行する（backend 側の既存 CLI）
cd /path/to/picoem-picocalc
target/release/picocalc-run ... \
  --sd-image /path/to/picocalc_emu/input.img \
  --sd-image-out /path/to/picocalc_emu/output.img

# output.img -> directory tree
cd /path/to/picocalc_emu
python3 tools/picocalc.py sd extract ./output.img ./sd-tree-after \
  --json ./output.sd.json
```

`input.img` は runner が読み取り専用で開き、firmware の書込みは COW overlay に保持します。
`output.img` は run 完了時に atomic export された完全な RAW image です。最後に `extract` して
ファイル単位の差分を確認します。入力と出力を同じ path にすることはできません。

このツールは既存の `picocalc.py` に統合されています。直接使う場合は同じ引数で
`python3 tools/sd_image.py sd pack ...`／`sd extract ...`も利用できます。

## UF2 を初期 flash image に変換する（U6-P0）

firmware runner の `--bin` は UF2 コンテナではなく、XIP address を 0 offset に写した
raw flash image を受け取ります。U6 の実 `uf2loader` 検証では、初期 flash を作る処理を
毎回個別スクリプトで書かず、標準の `uf2` tool を使います。

```sh
cd /path/to/picocalc_emu

# UF2 の magic、RP2040 family、block 順、address 範囲を検査する
python3 tools/picocalc.py uf2 inspect /path/to/bootloader_pico.uf2 \
  --json ./bootloader.uf2.json

# 2 MiB の blank flash (0xff) に UF2 payload を XIP address で配置する
python3 tools/picocalc.py uf2 assemble /path/to/bootloader_pico.uf2 \
  ./initial.bin --flash-size-mib 2 --json ./initial.flash.json
```

既定では RP2040 family ID (`0xe48bff56`) と family flag を必須にし、payload の重複、
範囲外、`NOT_MAIN_FLASH`、不連続な block 番号を拒否します。既存の出力は明示的に
`--force`を指定しない限り上書きしません。生成された `initial.bin` を、既存の runner の
`--bin` に渡します。

この tool は UF2 を実行したり、SD の `BOOT2040.UF2` を自動的に配置したりしません。
SD 側の loader artifact は U3-B の `sd pack`／`--sd-dir` で別途 snapshot に含めます。
family 検査を緩める `--family-id none --allow-missing-family` は、U6 の正式検証では
使用しないでください。inspect／assemble の JSON には入力・payload・出力の SHA-256 が
含まれるため、provenance manifest の材料として保存できます。

## pack の契約

- `--format fat32` が既定です。FAT16 は `--format fat16` を明示します。
- `--size-mib` の既定値は 64 MiB です。論理 image 全体を作るため、必要な容量を先に確保します。
- image は MBR を持たない **super-floppy** 形式で、sector 0 が FAT BPB です。
- entry は名前順に並べ、固定 timestamp、固定 volume ID、固定 label で生成するため、同じ tree は
  常に同じ image SHA-256 になります。
- 長い名前・Unicode 名は VFAT LFN と決定的な 8.3 alias に変換します。
- symlink、device、socket、FATで表現できない名前、case-insensitive な同名、容量超過は拒否します。
- 出力 image がすでに存在する場合は上書きしません。失敗時も一時ファイルを公開しません。

FAT16 は互換性用の明示 profile です。FAT16 の cluster は 32 KiB 以下に制限しており、サイズや
entry 数によっては FAT32 を選ぶ必要があります。

## extract の契約

- 入力は FAT16 または FAT32 の妥当な super-floppy RAW image です。
- 出力 directory は存在しないことが基本です。空の既存 directory を置き換える場合だけ
  `--force` を指定できます。非空 directory、symlink 経由の path、破損した BPB/FAT/LFN/chain は
  変更せずに拒否します。
- FAT copy の不一致、cluster chain の loop／共有／サイズ不一致、path traversal は fail-closed です。
- JSON report には operation、format、image／tree SHA-256、entry manifest が含まれます。

## runnerへdirectory snapshotを渡す（U3-B）

通常のfirmware targetでhost directoryをSDの入力にしたい場合は、wrapperを使います。
`--sd-dir`は常に固定profile（FAT32、64 MiB、volume label `PICOCALC`）で一度だけsnapshotを作り、
backendの既存`--sd-image`へ渡します。host directoryをrun中にmountしたり、run中のfirmware書込みを
directoryへlive同期したりはしません。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target <fat32-target> \
  --firmware /absolute/path/to/app.bin \
  --sd-dir ./sd-tree \
  --sd-manifest ./sd-snapshot.json \
  --sd-image-out ./sd-after.img \
  --json ./run-report.json
```

`--sd-dir`は登録targetがattached FAT32を要求するときだけ使用できます。`--sd`、`--sd-format`
との併用は拒否されます。`--sd-manifest`にはtree/imageのSHA-256とentry一覧が出力され、runner
reportの`sd.raw_image.source_sha256`／`bytes`とも照合されます。`--sd-image-out`はbackendのCOW
exportであり、必要な場合だけ指定します。

## U6実uf2loader Gate（限定conformance）

外部`uf2loader`を使う最終経路を再現する場合は、個別のPython scriptを作らず、次のGateを使います。
入力UF2、SD tree、cleanなuf2loader source、clean backend commitを明示し、同じ入力を3回実行します。

```sh
python3 tools/picocalc.py uf2 e2e \
  --runner /path/to/picoem-picocalc/target/release/picocalc-run \
  --backend-dir /path/to/picoem-picocalc \
  --backend-commit <clean-backend-commit> \
  --loader-source-dir /path/to/uf2loader/src \
  --loader-source-commit <clean-uf2loader-commit> \
  --bootloader-uf2 /path/to/bootloader_pico.uf2 \
  --loader-uf2 /path/to/BOOT2040.UF2 \
  --app-uf2 /path/to/app.uf2 \
  --sd-dir ./u6-sd-tree \
  --scenario scenarios/uf2loader-u6-e2e.json \
  --reattach-scenario scenarios/uf2loader-u6-reattach.json \
  --output ./u6-gate-output \
  --repetitions 3
```

GateはUF2 block欠落／重複／family／範囲、boot2／loader保護領域、flash erase/program readback、
SD command trace、watchdog warm reset、UART／report／framebuffer／flash SHA、再attachをfail-closedで
判定します。成功証拠は[`../firmware-validation/evidence/uf2loader-u6-20260822-01/`](../firmware-validation/evidence/uf2loader-u6-20260822-01/)にあります。
これは固定source／artifactの限定経路であり、USB BOOTSEL/MSCや任意UF2互換を意味しません。

## 現在の範囲

`sd pack/extract`はhost側の明示的な前処理・後処理です。U3-Bの`picocalc.py test --sd-dir`も
同じpack実装を起動時に使うだけで、runnerがdirectoryを直接mountする機能ではありません。
`uf2 pack/extract`やdirectory snapshotの存在だけで、一般的な`uf2loader supported`を宣言しません。
U6の限定conformanceは上記`uf2 e2e` Gateと機械可読capabilityの記載を正典とします。

通常のアプリ debug では、SD image を使わない従来の host／firmware 実行もそのまま利用できます。
