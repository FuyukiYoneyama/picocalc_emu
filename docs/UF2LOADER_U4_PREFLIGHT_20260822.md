# U4 preflight: 実 `uf2loader` の SD protocol gap

作成日: 2026-08-22

状態: **実装未着手。trace取得条件と判定規則を固定した段階。**

この文書は、[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)
のU4に着手する前の準備記録である。U4では、一般的なSD仕様や外部loaderのソースだけを根拠に
CMD18/CMD12を追加しない。**cleanな実`uf2loader`がエミュレーター上で実際に発行したtrace**を
一次証拠とし、観測された最小のprotocolだけを実装する。

## 1. 現時点の判定

U4のproduction codeはまだ変更していない。現状について確認できたことは次のとおりである。

| 項目 | 結果 |
|---|---|
| uf2loader source pin | `5c44a4b64749062b0200507ceeff3ef2b475e288` |
| SDK pin | `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` |
| toolchain | CMake 3.28.3 / Ninja 1.11.1 / arm-none-eabi-gcc 13.2.1 (20231009) |
| U0 evidence | source・SDK・artifact provenanceとdirect-bootのfirst failureのみ |
| U0に保存されたSD command trace | **なし** |
| 現行SD model | 初期化、CMD17、CMD24、既知CRC、未知command可視化 |
| CMD18 / CMD12 | **未実装・未観測** |
| U4の扱い | trace取得までproduction codeを変更しない |

`firmware-validation/evidence/uf2loader-u0-20260813-01/first-run.md`の内容は、無効なBPBを
受けたdirect-bootのSD mount停止と、その修正後にROM menuへ到達した記録である。これはU4の
protocol traceではない。したがって、U0の完了を理由にCMD18/CMD12を実装済みとは扱わない。

## 2. 外部checkoutとartifactの境界

一次sourceは`/home/fuyuki/pico_dvl/uf2loader`（upstream `pelrun/uf2loader`）である。ただし、
このcheckoutは調査時点で次の未追跡・未コミット状態を含む。

```text
M  ui/text_directory_ui.c
?? build_pico/
```

この状態のsourceや生成物はU4の証拠に使わない。U4では、上記commitのdetached clean cloneを
一時workspaceへ作り、submodule・source diff・生成物を別々に確認する。GPL sourceと生成UF2を
`picocalc_emu`へvendorしない。

2026-08-22に同じpinとSDKでclean cloneをビルドできることは確認したが、U0に記録された
`bootloader_pico.bin`／`BOOT2040.bin`のSHA-256とは一致しなかった。通常のbuildではPico SDKの
program build date（今回のbuildでは`Aug 22 2026`）がバイナリへ入る。U0 READMEには、完全な
configure command、`CFLAGS`/`CXXFLAGS`、build-date制御、picotoolのidentityが記録されていない。
この差はprotocolの結果ではなく、**U4 traceを採取する前に新しいclean artifact recordで閉じるべき
provenance gap**である。U0の時点証拠は書き換えず、U4用recordへ完全なコマンド列と生成物SHAを
追加する。

## 3. sourceから分かること／分からないこと

clean sourceのSD経路は次のとおりである。

```text
ui/main.c
  -> f_mount / f_opendir / f_open / f_read (FatFs)
  -> disk_read(..., count)
  -> MMC_disk_read(..., count) (ui/lib/sdmmc/sdmmc.c)
```

`MMC_disk_read`は`count == 1`ならCMD17、`count > 1`ならCMD23の後にCMD18を選ぶ構造を持つ。
一方、UF2本体の`load_application_from_uf2`は`sizeof(struct uf2_block)`（512 byte）ずつ
`f_read`する。FatFsのdirectory・FAT操作もsector単位の読み出しを含む。このsource-levelの
呼出し関係は「CMD17だけになり得る」ことを示すが、**実行時のcount、CS境界、token列を証明する
ものではない**。

現在のloader sourceにはCMD12の定義と、CMD12を特別扱いするresponse処理があるが、
`MMC_disk_read`の通常のread完了経路でCMD12を送ることはsourceから確認できない。これも
「未観測だから実装しない」というU4規則に従う。

## 4. trace取得の前提（U4-P0）

実loaderのtraceを取るには、次の前提をすべて満たす必要がある。

1. clean uf2loader source、SDK、toolchain、picotoolを固定する。
2. build-date等の再現条件を完全なcommand列としてrecordする。
3. loaderのinitial flash、`BOOT2040.UF2`、選択するapp UF2、SD tree/imageのSHAを固定する。
4. RP2040のboot2→stage3→SRAM UIへ入る経路を実行する。
5. SD modelに、既定動作を変えないdiagnostic-only traceを一時的に追加する。
6. traceはcommand index、argument、CS low/high区間、response、data token、block index、
   data length、CRC bytes、stop／deselect理由を順序付きで保存する。
7. traceを有効にしたrunでも、trace以外のreport（cycle、UART、LCD、flash、SD read結果）が
   traceなしrunと一致することを確認する。

現行`picocalc-run`は`direct_boot_from_flash(0x100)`が既定で、`--bootrom`はロードするだけで
実行しない。従って、現時点で`BOOT2040.bin`やstage3をdirect bootした結果を「実loader trace」と
呼んではならない。U5のboot2 entryを先に実装するか、U4-P0専用の同等なboot2 trace入口を用意し、
その入口自体を別の回帰として検証する。

traceは通常のtarget artifactへ混入させず、featureまたは明示的diagnostic outputに限定する。
trace有効runは性能測定・promoted target判定には使わない。

## 5. 観測結果による最小実装表

| clean traceで観測したもの | U4で行うこと |
|---|---|
| CMD17のみ（初期化commandを除く） | SD model変更なし。U4を「追加protocol変更不要」としてrecordし、CMD18/CMD12は未対応のまま保持 |
| CMD23 + CMD18、複数data token | CMD23の必要な引数形式、CMD18、各blockの`0xFE` token・512 byte・CRC・block incrementだけを実装 |
| CMD12 | CMD12のresponse前stuff byte、stop後のCS/state遷移を観測どおりに実装。観測されない用途へ一般化しない |
| CMD18中のCS high／deselect終了だけ | CS highでのread state破棄を実装。CMD12を代替として推測追加しない |
| read data CRC/error応答 | traceで現れたエラー経路だけを実装し、正常readのCRCを勝手に検証する範囲を広げない |
| CMD25、multi-block write、未観測command | U4には追加しない。別のclean traceと計画判断が必要 |

特に、CMD18を実装する場合は単に`count * 512`を一度に返さない。SPI multi-block readでは
各blockごとにdata token、512 byte、CRCが繰り返されるため、traceで確認した境界をstate machine
として表現する。CMD12も観測されない限り追加しない。

## 6. U4受入条件

### trace取得前の必須条件

- dirty external checkoutを使っていない。
- source／SDK／toolchain／build flags／picotool／artifact SHAがrecordされている。
- boot2経路をdirect bootと混同していない。
- trace有効／無効の同一入力で、trace以外の既存reportが一致している。

### protocol実装後の条件（CMD18等が観測された場合のみ）

- 既存CMD17初期化・read・write unit testが全て合格する。
- clean loaderが`BOOT2040.UF2`と選択app UF2を欠落・重複なく読み切る。
- 各blockのtoken／CRC／CS境界がtrace digestと一致する。
- block count、範囲外、早期CS、途中stop、壊れたtokenはvisible failureとなり、黙ってPASSしない。
- 同じsource／artifact／SD入力の3回でtrace digestとstructured reportが一致する。
- 既存target、M-NESCO-S1、U3-Bのreportとcapabilityを変更しない。

### protocol追加が不要だった場合

CMD18/CMD12が一度も観測されず、CMD17だけでclean loaderが完走した場合、U4のproduction codeは
変更しない。`uf2loader` sourceがCMD18を選択できることだけでは実装根拠にならない。U4 recordに
「clean traceで未観測、追加変更なし」と記録し、capabilityのmulti-block limitationも維持する。

## 7. 予定する証拠と工数

trace取得後の証拠は、次の新しいrecordへ保存する（空のrecord directoryは先に作らない）。

```text
firmware-validation/evidence/uf2loader-u4-YYYYMMDD-01/
  README.md
  source-manifest.json
  trace.json
  report.json
  SHA256SUMS
```

外部source・UF2・SD image本体はrepositoryへコピーしない。READMEには再現コマンド、入力SHA、
backend commit、trace schema、判定（追加実装／変更不要）を記す。

概算は、trace入口とclean artifactの再固定が4〜10時間、trace取得・解析が4〜8時間、
protocol追加が必要な場合の最小実装と回帰が8〜20時間である。CMD18/CMD12が未観測なら、
追加実装は0時間で、証拠整理とU4 closeだけを行う。

## 8. 実装開始条件

次のすべてが揃うまで、`sdcard.rs`へCMD18/CMD12のproduction codeを追加しない。

- U4用clean artifact recordがあり、U0の未記録build条件を補完している。
- boot2経路または同等のtrace入口が、別テストで合格している。
- traceに実際のCMD18またはCMD12（あるいは別の不足command）が現れている。
- そのcommandの最小state／token／CS／error仕様をtraceから書ける。

この順序により、SD仕様の一般論やsource上の未使用分岐を先回り実装せず、実loaderが必要とする
範囲だけを正確に追加できる。
