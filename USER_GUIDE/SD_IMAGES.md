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

## 現在の範囲

これは host 側の前処理・後処理ツールです。`picocalc test --mode firmware --sd-dir` のように
runner が directory を直接 mount する機能ではありません。runner の既存 `--sd-image`／
`--sd-image-out` と組み合わせて使います。directory snapshot の runner 統合（U3-B）は別の受入条件で
行い、完了するまでは本ツールの存在を `uf2loader supported` の宣言とは解釈しません。

通常のアプリ debug では、SD image を使わない従来の host／firmware 実行もそのまま利用できます。
