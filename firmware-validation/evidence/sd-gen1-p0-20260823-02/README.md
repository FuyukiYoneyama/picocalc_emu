# SD-GEN-1-P0 clean wire traces

判定: **P0 trace採取 PASS（M-NESCO menu A/B、FAT16、FAT32）**

2026-08-23に、cleanなNESco source/backendとローカルrunnerだけを使って、SD-GEN-1の
代表wire traceを採取した。productionのSD protocol codeは変更していない。各traceは
同じ入力を3回実行し、event count、digest、保存JSONのSHA-256が一致した。

## 共通 provenance

- NESco source: commit `7f3fa05971930e03653694117cbf6a435ec1dd4e`, clean
- 診断BIN: SHA-256 `1b4c3277597030d8e0358be2aeb59fadc5c6289d2e47e337059e9c47aa92735f`
- build flags: `NESCO_MNESCO_EXT_ORACLE=ON`, `NESCO_RUNTIME_LOGS=ON`、autostart flagsはOFF
- backend: commit `d1360cbb13fd807661474b49a1b5516b12567d00`, clean
- runner: `picocalc-run` SHA-256 `919b84aedb4b0eb6dd92a4aa21200b343ab83c103144356803da9c868aedfcb5`
- trace保持tool: `tools/mnesco_ext.py` SHA-256 `395701f5f073b90efe7e6f52b9af5fe21d02d2163aee30f94110956a85446038`
- runner条件: `--board picocalc --keyboard --quantum 256 --cycles 2,000,000,000`

診断BINは検査用の一時buildであり、通常の製品targetや既存M-NESCO受入recordを置き換えない。
入力ROMの識別はbasename、iNES metadata、SHA-256だけを記録し、呼び出し側の絶対pathは保存していない。

## M-NESCO menu経路（mapper 2／中容量）

`mnesco-m2-menu/`にrunner manifest、case record、A/B各3回のtraceを保存した。

- ROM: `Makai_Mura_(Japan).nes`, 131088 bytes, mapper 2, ROM SHA-256
  `7421b53c43f5d4a1b8620f56696c827f1192ba3feeccde594e7e92af18a0ff53`
- FAT32 image SHA-256 `3cc402001ceea99523ea8968e71f8f5a8198e599da4f7b9d1da3bddb2fa564a7`
- Run A (`sd:/TEST.NES`): 3/3 pass、`event_count=2083`、trace digest
  `c3db672deded667f83e3daa4b6feedb8585aae709bf70850d287c649b6e87366`、trace JSON SHA-256
  `6bc190caff1095a079391b17a50cda3232d7a67d2774e8a4d10bdbbd6c549596`
- Run B (`flash:/TEST.NES`): A export後の再attachを3/3 pass、`event_count=29`、trace digest
  `ac242c6aec780fee8793ca99c2b010017e08b411a7968a723ec5490691c85f23`、trace JSON SHA-256
  `95bc731d23979cabc0aa3960a74b7bb0bc5350b2888bfed3174b9f043ae22d26`
- A/BでROM SHA、PRG境界sample、CPU/PPU観測、core 1/DMA XIP digest、flash SHAが一致
- unknown command: 0

Bはflash再attachのmenu選択経路なので、ROM本体をflashから読んだ後のSD traceは初期化と
最小metadata読出しだけになる。AとBのevent数が異なることは経路差であり、determinism違反ではない。

## FAT16／FAT32代表経路

同じROMを決定的packerでFAT16（32 MiB）とFAT32（64 MiB）へ格納し、通常menuから読む
Run Aを各3回実行した。各形式の`pack.json`にはtree/image/file SHAを保存している。

| format | image SHA-256 | repeats | event count | trace digest | trace JSON SHA-256 |
|---|---|---:|---:|---|---|
| FAT16 | `eb7c536e3921491b2c45ef38fd1116a0046b3a6c0af20aaffdf3574993cd482a` | 3/3 | 2081 | `e189b48cb6bcb9600697959cf5bff18b1544a32dfa56e3938b2935847d1dcf6c` | `20e194380f0ecc4941856e052ccc2f8969b12b2c10ed2a5ad65a5e9fdb7dd8bd` |
| FAT32 | `1842d0c458d32499ab219dcee1870be877a4c7559f768c8998127270eff67995` | 3/3 | 2083 | `c3db672deded667f83e3daa4b6feedb8585aae709bf70850d287c649b6e87366` | `6bc190caff1095a079391b17a50cda3232d7a67d2774e8a4d10bdbbd6c549596` |

両形式とも観測command集合は `CMD0`, `CMD8`, `CMD17`, `CMD55`, `ACMD41`, `CMD58`、
data tokenはread `0xFE`、block長は512 bytes、unknown commandは0件だった。FAT16とFAT32で
filesystem metadataに由来するsector列は異なるが、現行firmwareはsingle-block CMD17を
sector単位で発行しており、CMD18/CMD12/CMD23/CMD24/CMD25は発行していない。

## P0からP1へ渡す判断

- 実traceで必要性が確認できた範囲は、既存single-block read初期化・token・CRC・CS境界である。
- この代表経路からmulti-block commandを推測追加する根拠はない。CMD18/CMD12/CMD23/CMD25は
  P1でsynthetic契約または別アプリの一次traceが得られるまで未対応・可視化fail-closedのままにする。
- FAT filesystemのFAT16/FAT32対応と、SD wire protocolのmulti-block対応は別契約として扱う。
- P0完了後の次段階はP1 wire契約の固定であり、production実装はP1の受入matrix後に判断する。

## 再現手順の形

入力ROM、SDK、backend checkout、runnerは呼び出し側で用意する。以下は経路を示すための
プレースホルダー付きコマンドであり、privateなローカル絶対pathを証拠へ固定しない。

```sh
cmake -S <nesco-source> -B <build-dir> \
  -DPICO_SDK_PATH=<pico-sdk-2.2.0> -DPICO_BOARD=pico -DCMAKE_BUILD_TYPE=Release \
  -DNESCO_MNESCO_EXT_ORACLE=ON -DNESCO_RUNTIME_LOGS=ON \
  -DNESCO_MNESCO_AUTOSTART_SD=OFF -DNESCO_DIAGNOSTIC_AUTOSTART_BUILTIN=OFF
cmake --build <build-dir> -j2
python3 tools/picocalc.py sd pack <tree-with-TEST.NES> <fat16.img> --format fat16
python3 tools/picocalc.py sd pack <tree-with-TEST.NES> <fat32.img> --format fat32
picocalc-run --bin <Picocalc_NESco.bin> --board picocalc --keyboard --quantum 256 \
  --sd-image <input.img> --sd-trace <sd-trace.json> --scenario <mnesco-ext-sd.json> \
  --uart <uart.bin> --json <report.json> --cycles 1900000000 \
  --expect-stop scenario_done --backend-commit <clean-backend-commit>
```

M-NESCOのA/B再attachは`tools/mnesco_ext.py --retain-sd-traces <evidence-dir>`で同じ
trace保持契約を使う。P0で保存した実体は、このディレクトリの`manifest.json`と各trace JSONである。
