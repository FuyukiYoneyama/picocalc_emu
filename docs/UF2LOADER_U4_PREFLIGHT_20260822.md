# U4 preflight: 実 `uf2loader` の SD protocol gap

作成日: 2026-08-22

状態: **U4-P2完了。diagnostic-only trace入口、clean loader trace 3回、protocol判断を完了。CMD18/CMD12のproduction追加は不要。U6 clean GateでもSD trace一致を再確認した。**

この文書は、[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)
のU4-P1準備からU4-P2判定までを記録する。U4では、一般的なSD仕様や外部loaderのソースだけを根拠に
CMD18/CMD12を追加しない。**cleanな実`uf2loader`がエミュレーター上で実際に発行したtrace**を
一次証拠とし、観測された最小のprotocolだけを実装する。

## 1. 現時点の判定

U4-P2では、既存のカード応答を変えないdiagnostic-only trace入口でcleanな実loaderを3回実行した。
traceはCMD17だけを観測し、CMD18/CMD12/CMD23/CMD24/CMD25は一度も現れなかった。なお、最初の実行で
既存SD modelの「CMD17のR1がdata tokenより後ろにキューされる」不具合を検出したため、R1→token→payloadの
wire順序を修正し、同じclean loaderを再実行した。これはmulti-block protocolの追加ではない既存single-block
応答のcorrectness修正である。現状について確認できたことは次のとおりである。

| 項目 | 結果 |
|---|---|
| uf2loader source pin | `5c44a4b64749062b0200507ceeff3ef2b475e288` |
| SDK pin | `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` |
| toolchain | CMake 3.28.3 / Ninja 1.11.1 / arm-none-eabi-gcc 13.2.1 (20231009) |
| U0 evidence | source・SDK・artifact provenanceとdirect-bootのfirst failureのみ |
| U0に保存されたSD command trace | **なし** |
| U4 clean trace | 3回とも event 787 / digest `2f98c14d0b45c85c...`、CMD17 379回 |
| 現行SD model | 初期化、CMD17、CMD24、既知CRC、未知command可視化。CMD17のR1順序を修正 |
| CMD18 / CMD12 / CMD23 | **未実装・未観測** |
| U5-A boot2 entry | backendにproduction実装済み。U6 clean Gateのboot2→stage3経路で再確認 |
| U4-P2の扱い | `--sd-trace`、clean trace反復、traceなし一致、protocol必要性判定を完了。multi-block追加なし |

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

2026-08-22に、固定commitのdetached clean cloneとSDK pinから`stage3`をビルドできることを確認した。
U4で使う全artifactは、次の形式で改めてclean buildし、source／SDK／toolchain／picotool／生成物を
同じrecordへ固定する。

```sh
git clone --no-local /home/fuyuki/pico_dvl/uf2loader "$U4_SRC"
git -C "$U4_SRC" checkout --detach 5c44a4b64749062b0200507ceeff3ef2b475e288
git -C "$U4_SRC" submodule update --init --recursive
PICO_SDK_PATH=/home/fuyuki/pico_dvl/codex/pico-sdk \
  cmake -S "$U4_SRC" -B "$U4_BUILD" -DPICO_BOARD=pico -DCMAKE_BUILD_TYPE=Release
cmake --build "$U4_BUILD" -j2
```

必要なRP2040生成物は`$U4_BUILD/stage3/bootloader_pico.bin`と、SDへ置くUIの
`$U4_BUILD/../output/BOOT2040.uf2`である（外部sourceの`CMAKE_BINARY_DIR/../output`）。既存U0の`bootloader_pico.bin`／`BOOT2040.bin`とSHA-256が
一致しない場合でも、それは直ちにprotocol差ではない。U0の時点証拠は書き換えず、U4用recordへ
完全なconfigure command、build-date等の再現条件、生成物SHAを追加してprovenance gapを閉じる。

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

## 4. trace取得の前提（U4-P2）

実loaderのtraceを取るには、次の前提をすべて満たす必要がある。

1. clean uf2loader source、SDK、toolchain、picotoolを固定する。
2. build-date等の再現条件を完全なcommand列としてrecordする。
3. loaderのinitial flash、`BOOT2040.UF2`、選択するapp UF2、SD tree/imageのSHAを固定する。
4. RP2040のboot2→stage3→SRAM UIへ入る経路を実行する。
5. SD modelに、既定動作を変えないdiagnostic-only traceを明示オプションで有効化する。
6. traceはcommand index、argument、CS low/high区間、response、data token、block index、
   data length、CRC bytes、stop／deselect理由を順序付きで保存する。
7. traceを有効にしたrunでも、trace以外のreport（cycle、UART、LCD、flash、SD read結果）が
   traceなしrunと一致することを確認する。

現行`picocalc-run`は`direct_boot_from_flash(0x100)`が既定で、`--bootrom`はロードするだけで
実行しない。U5-Aで追加した`--boot-mode boot2`を明示した場合だけ、clean loader artifactのflash
先頭boot2からstage3へ入る。従って、`BOOT2040.uf2`やstage3をdirect bootした結果を「実loader trace」
と呼んではならない。U5-Aのclean artifact受入証拠を先に固定し、その入口を使ってU4 traceを採取する。

traceは通常のtarget artifactへ混入させず、featureまたは明示的diagnostic outputに限定する。
trace有効runは性能測定・promoted target判定には使わない。

### 4.1 診断traceの実装境界（U4-P1）

追加したのはSD protocolの機能ではなく、既存の挙動を変えない観測だけである。

- 観測点は`SdCard`／`SdCardWire`のカード側境界に限定し、SPI controller全体の汎用ログは使わない。
- 既定では無効とし、明示的なdiagnostic optionまたはfeatureでだけ有効にする。
- command frame、R1/R3/R7応答、data token、block payload長、CRC bytes、CS risingによるdeselect、
  unknown commandを順序付きstructured eventへ畳み込む。
- trace有効時も、cardのreply、block counter、overlay、unknown commandの通常処理は同じコードを
  通り、traceを理由に応答待ちやbusy時間を変更しない。
- イベント列はメモリへ無制限に蓄積せず、streaming digestと上限付きpreviewを使う。完全列が必要な
  U4 runだけ、明示的なtrace pathへatomicに書き出す。
- trace schema、digest、previewはrunner reportの既存判定値から分離し、traceなし／traceありで
  cycle、UART、LCD、flash、SD結果が一致することを回帰で固定する。

runnerの利用例（通常の`--json` reportとは別のartifactを出力する）。

```sh
cargo run --locked --release -p picocalc-harness --bin picocalc-run -- \
  --bin app.bin --bootrom roms/rp2040/bootrom-rp2040-b2.bin \
  --sd-image input.img --sd-trace sd-trace.json --cycles 1000000
```

`--sd-trace`は`--sd`または`--sd-image`と併用したときだけ有効で、`--machine-api`とは併用できない。
出力schema 1は`trace_kind: "sd-spi-structured-v1"`、全イベントのstreaming SHA-256、イベント数、
上限付きpreviewを持つ。previewが切れた場合もdigestとevent_countは全イベントを対象とする。
通常のrunner reportのschema／verdictにはtraceを混入させない。

この診断trace入口のローカル回帰は完了している。clean loaderでの反復結果は次節に固定し、
`sdcard.rs`へCMD18／CMD12やmulti-block stateは追加しない。

### 4.2 clean loader traceの結果（U4-P2）

2026-08-22、外部checkoutを固定commitのdetached clean cloneとして作り、SDK pinから生成した
`stage3/bootloader_pico.bin`を`--boot-mode boot2`で起動した。SD protocolだけを観測するため、
LCD modelは付けず、uf2loaderが実際に使う`--keyboard`とFAT32 RAW imageを接続した。これは
`BOOT2040.UF2`をstage3がSRAMへ読み込む経路を省略していない。最終的なapp選択・flash書込み・watchdog
resetはU6の範囲であり、ここでは行っていない。

再現時のrunner形は次のとおりである（`--sd-trace`を外せばtraceなし比較runになる）。

```sh
picocalc-run \
  --bin "$U4_BUILD/stage3/bootloader_pico.bin" \
  --bootrom roms/rp2040/bootrom-rp2040-b2.bin \
  --boot-mode boot2 --keyboard \
  --sd-image "$U4_SD_IMAGE" --sd-trace "$U4_TRACE" \
  --json "$U4_REPORT" --uart "$U4_UART" --cycles 500000000
```

| 入力／結果 | 値 |
|---|---|
| uf2loader source | `5c44a4b64749062b0200507ceeff3ef2b475e288`（clean） |
| SDK | `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` |
| `bootloader_pico.bin` | `a0c995c138db6773726980b8af448ed86a435f4aac754210250187f6d932787e` |
| `BOOT2040.UF2` | `3f1a096937d38de98f7b4eed2b1ceae1c34c789d8fcb1e3f529a1ee9fab5a25c` |
| FAT32 SD image | `b5887857d76864d7b5e5ac91ebb28f1efd2e620aa624cc43519e8f5db1fba1a5` |
| cycle budget | `500000000`（各3回） |
| trace event count | `787`（各3回） |
| trace digest | `2f98c14d0b45c85cd7a4beabdf447dc5623ee0819e4b65c17001ca6dd6f33282`（各3回） |
| report／UART | traceあり・なしでbyte一致。UARTは空（SHA-256は空列） |
| loader到達点 | `pc=0x200027f6`（SRAM上のUI実行域） |
| unknown SD command | 0 |

このU4-P2測定時点ではbackendにU4/U5-Aの未コミット変更が残っているため、runner reportの
`backend_build.dirty`は`true`である。したがって上表はprotocol判断の再現可能な作業記録であり、
正式なversioned validation evidenceではない。backendをclean commitへ固定した後、同じ入力で再取得した
trace/reportを正式recordとして保存する。外部uf2loader checkout自体はcleanであり、そこを汚染していない。

3回のcommand内訳は、CMD0×2、CMD8×2、CMD55×4、ACMD41×4、CMD58×2、CMD17×379である。
CMD17の各readは`0x00`(R1) → `0xFE`(data token) → 512 byte → 2 CRC byteの順序で観測された。
CMD18、CMD12、CMD23、CMD24、CMD25は0回だった。trace digestとstructured reportは3回とも一致し、
traceを無効にした同一入力のreport／UARTも一致した。

最初の試行ではCMD17の応答順序の既存バグによりblock 0の再試行が発生した。この差分をunit test
`single_block_read_returns_r1_before_data_token`で固定し、R1をdata tokenより前に返す修正後に上記の
3回結果を取得した。これはCMD18/CMD12を先回り実装する根拠ではなく、既存single-block契約の修正である。

## 5. 観測結果による最小実装表

| clean traceで観測したもの | U4で行うこと |
|---|---|
| CMD17のみ（初期化commandを除く） | 既存single-blockのR1→token順序だけを修正済み。U4を「追加protocol変更不要」としてrecordし、CMD18/CMD12は未対応のまま保持 |
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

CMD18/CMD12が一度も観測されず、CMD17だけでclean loaderがSRAM UIへ到達した場合、U4のproduction codeへ
multi-block機能は追加しない。今回のU4 traceはこの条件を満たした。`uf2loader` sourceがCMD18を選択できる
ことだけでは実装根拠にならない。single-block R1順序の修正と「clean traceでCMD18/CMD12未観測、追加変更なし」
をU4 recordへ記録し、capabilityのmulti-block limitationも維持する。app選択、flash書込み、watchdog resetの
end-to-end判定はU6へ残す。

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

## 8. protocol追加を再開する条件

今回のclean traceでは追加gapが見つからなかったため、`sdcard.rs`へCMD18/CMD12のproduction codeは
追加しない。将来別のclean loader／workloadでprotocol追加を再開する場合だけ、次の条件をすべて満たす。

- U4用clean artifact recordがあり、source／SDK／toolchain／入力SHAが固定されている。
- boot2経路または同等のtrace入口が、別テストで合格している。
- traceに実際のCMD18またはCMD12（あるいは別の不足command）が現れている。
- そのcommandの最小state／token／CS／error仕様をtraceから書ける。
- 既存CMD17のR1→token→payload順序と、traceなし／traceあり一致を維持する。

U4-P2の完了条件は次のとおりである。

- [x] U5-Aの`--boot-mode boot2`入口と既定app経路の分離を確認した。
- [x] 固定uf2loader source／SDK／toolchainのclean clone build手順を再現した。
- [x] 外部汚染された`/home/fuyuki/pico_dvl/uf2loader`を証拠に使わない境界を固定した。
- [x] clean artifact、`BOOT2040.uf2`、選択app UF2、SD imageの入力SHAをrecordする形式を固定した。
- [x] trace有効／無効の既存report一致をU4受入条件へ追加した。
- [x] 診断trace入口をbackendへ実装し、unit testでtraceなしの挙動不変を確認する。
- [x] clean artifactで実loaderを起動し、traceを3回取得してdigest一致を確認する。
- [x] traceなし／traceありでreportとUARTがbyte一致することを確認する。
- [x] CMD18／CMD12／CMD23／CMD24／CMD25が未観測であることを確認し、multi-block production追加を見送る。
- [x] CMD17のR1→data token順序をunit test付きで修正する。

これによりU4のSD protocol判断は完了した。U5-BとU6 end-to-endは後続Gateとして完了し、
U6のclean証拠は`firmware-validation/evidence/uf2loader-u6-20260822-01/`へ保存した。
M-NESCO拡張（複数mapper／ROMサイズ／read path／再attachの受入）は別項目として完了しており、
U6の固定LCD fixture証拠とは分離したNESco-specific evidenceへ固定している。CMD18/CMD12等のproduction追加は行わず、限定されたU6 capabilityだけを有効化している。

この順序により、SD仕様の一般論やsource上の未使用分岐を先回り実装せず、実loaderが必要とする
範囲だけを正確に追加できる。
