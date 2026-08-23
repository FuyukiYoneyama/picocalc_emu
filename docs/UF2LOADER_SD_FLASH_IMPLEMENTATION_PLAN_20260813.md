# UF2 Loader を目標とする SD / flash 統合実装計画

作成日: 2026-08-13
対象: `picocalc_emu` / `picoem-picocalc`
状態: **U0・U1・U2・M-NESCO-S1・U3-A・U3-B・U4-P2・U5-A・U5-B・U6・M-NESCO拡張受入・SD-GEN-1 P0〜P5完了。U6はcleanな実uf2loader source/buildを使う3回deterministic Gateに合格し、固定LCD fixtureの限定されたSD→flash→watchdog→再起動経路をcapabilityへ反映済み。SD-GEN-1 P5ではdefault runtimeのbounded `sd-multi-block` capabilityをversioned validationとして受け入れた。USB BOOTSEL/MSCと全UF2互換性は対象外。**
目標アプリ: RP2040 PicoCalc 用 [`pelrun/uf2loader`](https://github.com/pelrun/uf2loader)

## 1. 結論

次の機能を、依存関係のある**1つの縦方向の機能追加**として実施する。

1. SDカードのRAW image入力
2. RP2040 flashのerase / program
3. `Picocalc_NESco`をdirect bootでdebugできる中間マイルストーン
4. ホストdirectoryからSD内容を読み込むsnapshot import
5. boot2 entry（U5-A）
6. 実loaderで観測したSD protocol gap（U4）
7. watchdog warm reset（U5-B）
8. M-NESCO拡張受入（複数mapper／容量／read経路／flash再attach）
9. 実`uf2loader` end-to-end

`uf2loader`は今後の標準起動方式ではない。通常のアプリ開発・debugは、現在と同じBINの`direct_boot_from_flash(0x100)`を既定のまま使う。`uf2loader`はSD、flash erase/program、変更後XIP read、resetを一度に通す**高精度conformance workload**として使う。

統合機能の最終受入条件は、実際の`uf2loader`が次の経路を完走することである。

```text
電源投入相当
  -> 起動時キーでUF2 Loader menuを選択
  -> SD rootのBOOT2040.UF2をSRAMへロード
  -> pico1-appsのUF2一覧を表示
  -> 選択したUF2を内蔵flashへerase/program
  -> watchdog reboot
  -> 書き込んだアプリを起動
  -> UART / framebuffer / flash内容を検証
```

SD RAWとflash read/writeまで完了した時点に、`M-NESCO`という正式な中間マイルストーンを置く。この時点から`Picocalc_NESco`を既存のdirect bootでdebugに利用してよい。directory import、boot2、watchdog、実`uf2loader`はこの後に続く。M-NESCOではまだ**`uf2loader supported`とは表示しない。** 上記のend-to-end受入が通って初めて、SD/flash/resetを統合した最終conformanceが完了したとする。

2026-08-13に、U0で固定したclean provenanceとU1/U2の実装を使ったM-NESCO-S1を完了した。M-NESCO-S1の範囲は、既存direct bootで`Picocalc_NESco`を起動し、FAT32 RAW image上のSD ROMを選択し、flash erase/programとXIP反映を同一runで確認し、structured reportとflash exportを得るところまでである。複数mapper・複数サイズの網羅、export後の再attach run、directory import、boot2、watchdog、実`uf2loader` end-to-endは、M-NESCOの拡張受入またはU3以降に残す。これにより、証拠のない「uf2loader対応済み」や「全NESco ROM対応済み」を宣言しない。

本書は[`NESCO_FLASH_WRITE_AND_SD_DIRECTORY_REQUEST_20260813.md`](history/NESCO_FLASH_WRITE_AND_SD_DIRECTORY_REQUEST_20260813.md)の要件を残したまま、今回指定された実行順序を優先する統合計画である。旧文書の「directoryを先にする」という優先順位は本書で置き換える。

## 2. 一次リファレンスとprovenance

実装前の調査では、ローカルの次を読み、実際の経路を確認した。

- source: `/home/fuyuki/pico_dvl/uf2loader`
- commit: `5c44a4b64749062b0200507ceeff3ef2b475e288`
- upstream: `https://github.com/pelrun/uf2loader.git`
- license: GPL-3.0

ただし現在のローカルcheckoutには`ui/text_directory_ui.c`の未コミット変更と`build_pico/`がある。これは調査用に限り、正式な受入証拠には使わない。受入時は同commitの**clean checkout**と、固定したSDK/toolchainから再ビルドする。

`uf2loader`本体、生成UF2、ゲームデータはMITの`picocalc_emu`へvendorしない。公開repositoryには自作の小さなfixture、プロトコルテスト、外部sourceのcommit/SHAと再現手順だけを置く。GPL成果物を必要とするend-to-end検証は、利用者が別途取得した外部checkoutを明示指定するoptional conformanceとする。

## 3. 現状と不足

| 領域 | 現在あるもの | uf2loader完走に不足するもの |
|---|---|---|
| SD | SPI bring-up、CMD17、CMD24、memory上の64 MiB FAT32/FAT16 | RAW backing、directory import、実loaderが使うmulti-block read |
| flash | XIP read、JEDEC/UID/status query | WEL/WIP、sector erase、page program、memory反映、cache無効化 |
| boot | SDK vector tableから`direct_boot_from_flash(0x100)` | boot2からstage3へ入る起動方式 |
| reset | watchdog tickとscratchの一部 | `watchdog_reboot(0,0,0)`によるwarm reset |
| input | 起動前queueとscenario input | 起動時0.5秒のmenu選択を再現できることの確認 |
| artifact | 初期BIN、report、UART、PNG | 最終flash imageとflash mutation report |

実物のloader UIのSD driverは複数sector要求時にCMD18を選べる構造を持ち、選択後は`flash_range_erase` / `flash_range_program`を使い、最後に`watchdog_reboot(0,0,0)`を呼ぶ。したがって、ユーザーが挙げた3機能だけを表面的に足しても完走しない。実traceで観測されたSD gap、boot2 entry、warm resetは、対象を広げる追加要求ではなく、**実際のuf2loaderを動かすための最小付帯条件**である。

## 4. 最小実装の境界

### 4.1 今回含める

- RP2040のみ
- 通常のアプリdebugは既存direct bootを維持し、uf2loader専用boot modeを明示指定したrunだけで使う
- FAT32を既定の検証形式とする。RAWはfilesystemを解釈せずFAT16もそのまま扱える
- RAW imageをfile-backedでreadし、run中の変更はcopy-on-write overlayへ保持
- host directoryから決定的なFAT32 imageを1回だけ構成するsnapshot import
- SD multi-block readについて、実loaderのtraceで観測した最小command/token/CS動作
- flash Write Enable、status、4 KiB sector erase、256-byte page program
- flash変更をXIP read/fetchへ反映し、両coreのdecode cacheを無効化
- boot2 entryと、flash/SDを保持するwatchdog warm reset
- 最終flash imageのatomic export
- 実loaderによるend-to-end scenarioとnegative tests

### 4.2 今回含めない

- RP2350
- USB BOOTSEL / USB Mass Storage / Picotool protocol
- SDのhost directoryへの双方向live同期
- firmwareがSDへ書いた内容をhost directoryへファイル単位で逆変換
- SD card removal、write protect pin、実時間のprogramming delay
- CMD25 multi-block write（実loader完走traceで必要と判明した場合だけ再判断）
- flash wear、電源断途中のanalogな破損、メーカー固有timing
- full RP2040 bootrom/QSPI pad emulation
- 既存direct bootをuf2loader起動へ置き換えること

USB BOOTSELは、loaderの初回インストール手段または失敗時fallbackである。今回検証するのは、一般利用者が日常的に使う**SD menuからアプリUF2を選んで起動する経路**であり、USB stackを実装する必要はない。

## 5. 外部インターフェース案

最終的なCLIは次を基本形とする。名称は実装段階のCLI reviewで確定する。

```text
--sd                         新規memory-backed SD（既存）
--sd-format fat32|fat16      --sdだけに有効（既存）
--sd-image INPUT.img         既存RAW imageをread-onlyでattach
--sd-dir DIRECTORY           directory snapshotをFAT32へimport
--sd-image-out OUTPUT.img    run後のSD imageをatomic export

--boot-mode app|boot2        appは既存direct boot、boot2は新経路
--flash-out OUTPUT.bin       run後の2 MiB flashをatomic export
```

規則:

- `--sd`、`--sd-image`、`--sd-dir`は相互排他
- `--sd-format`は`--sd`でのみ許可
- inputとoutputの同一pathは初期版では拒否する
- outputは一時fileへ書いた後にrenameし、失敗時に既存fileを半端に壊さない
- 絶対host pathはstructured reportへ入れず、basename、size、SHA-256だけを記録する
- 複数runではrunごとに別output pathを使う。同一pathへの同時書込みは保証しない
- 既存引数だけを使うrunのreport byte列とtarget契約は変更しない

### RAWを全量`Vec`へ読まない理由

PicoCalc付属SDは32 GBである。32 GB imageをrun開始時にRAMへ展開する設計は採用しない。入力fileをblock単位でreadし、変更sectorだけをmemory overlayに置く。これにより、64 MiBの検証imageにも32 GBのsparse/real imageにも同じinterfaceを使える。

`--sd-image-out`を指定した場合だけ、入力とoverlayを合成して完全なimageを出力する。32 GBの出力には相応のI/O時間と空き容量が必要であることを明記する。uf2loaderのread経路では通常outputを必要としない。

## 6. 実装段階

### U0: 契約、fixture、protocol traceを固定 — **完了 2026-08-13**

実装前に次を固定する。

- cleanなuf2loader source commit、submodule、SDK、compiler、CMake/Ninja version
- `bootloader_pico.uf2`と`BOOT2040.UF2`のSHA-256
- 外部配布物を含まない自作test app UF2
- SD directory manifest
- loaderが実際に発行するSD/SSI/watchdog access trace
- 「既存の何が不足して停止するか」を示すfirst-run record

初期flashは、2 MiBを`0xFF`で埋め、`bootloader_pico.uf2`のpayloadを適用して作る。objcopyのsparse gapが`0x00`になったBINを、そのままblank flashと誤認して使わない。

**Gate U0:** source/toolchain/artifact SHAが固定され、GPL artifactをrepositoryへ入れず再現できる。clean checkout・clean build・SHA確認を
`firmware-validation/evidence/uf2loader-u0-20260813-01/`に記録した。

### U1: SD RAW image — **完了 2026-08-13**

SDのsector storageをinterface化し、既存memory backingと新しいRAW backingを分離する。

- input sizeは非0かつ512 byteの倍数
- block indexの範囲外は明示error
- input fileはrun中に直接変更しない
- firmware writeはsector overlayへ記録
- 未変更runのexportはinputとbyte-for-byte一致
- 変更runは次回の`--sd-image`で再利用可能
- input/output SHA、block数、read/write数、dirty block数をreportへ記録

**Gate U1:** FAT32/FAT16の既存RAW imageをmount/readでき、1 sectorの変更をexportして次runで読める。異常size、範囲外、同一input/outputはfail-closed。file-backed RAW、512-byte lazy read、COW overlay、atomic export、source/dirty metadataとunit testを実装した。M-NESCO-S1では64 MiB FAT32 RAWを読み、341 command、332 block read、unknown command 0件を記録した。

### U2: flash erase / program — **完了 2026-08-13**

`SsiFlash`がvalidated mutation eventを生成し、`Bus`がXIP backingへtransaction境界で適用する構造を基本とする。

最低限の意味論:

- WREN (`0x06`)でWELをset
- program/eraseはWEL必須
- SDKの`flash_range_erase(offset, count)`が要求するsector/blockを`0xFF`にする
- page program (`0x02`)は最大256 byte、page跨ぎ禁止
- program結果は`old & new`。eraseなしの0->1要求はsilent correctionせずerror
- 正常完了後はWEL clear
- status read (`0x05`)でWEL/WIPを観測可能
- address範囲、alignment、command lengthを検査
- mutation後に両coreのXIP decode cacheとimmutable-XIP前提を無効化
- flash readbackは変更後の同じbackingを参照

SDK bootrom helperが実際に使うexit-XIP/read/status/erase commandはU0 traceで確定し、必要分だけ実装する。4 KiB eraseで一般的な`0x20`に加え、大きなNESco ROM範囲ではblock erase opcodeが選ばれる可能性がある。一般的なNOR opcode一覧を根拠にどちらかへ固定せず、clean traceに現れた経路を正確に実装する。

real flashにはtop 16 KiBの物理write protectionはないため、エミュレーター独自の保護を作らない。代わりにend-to-end契約でloader領域が不変であることを検査し、変更が起きればアプリ/loaderの失敗として落とす。

**Gate U2:** erase、program、readback、WEL/WIP、cache invalidationがunit/integration testを通る。不正alignment、page crossing、範囲外、WELなし、0->1は黙って成功しない。SPI-NORのWREN/status/sector・block erase/page program、QSPI CS境界、XIP backing更新、decode cache invalidation、flash mutation reportを実装した。実行証拠では12 erase、179 page program、45,824 program bytes、unknown command 0件、errors 0件だった。

### M-NESCO: `Picocalc_NESco`デバッグ開始マイルストーン — **M-NESCO-S1完了 2026-08-13**

U1〜U2が完了した時点で、boot2/watchdogを待たずに`Picocalc_NESco`を既存のdirect bootで検証する。これは仮のデモではなく、SDとflashの実装がNEScoのdebugに使えることを宣言する正式な中間マイルストーンである。

```text
Picocalc_NESco BINを従来どおりdirect boot
  -> RAW SD imageからROMを選択
  -> 大きなROMをflash XIP領域へerase/program
  -> firmware自身がflash内容を元SD fileと照合
  -> 同じrunでXIP上のROMを実行
  -> final flashをexport
  -> 次runの初期flashとして再利用し、metadata/ROMを復元
```

flash readについては、単に書いた直後の1回の`memcmp`だけでは合格にしない。少なくとも次を検証する。

- CPU instruction fetch、literal/dataの8/16/32-bit read
- ARM/RP2040モデルで定義するaligned/unaligned read semanticsとflash境界
- core 0/core 1およびDMAからのXIP read
- erase/program直後に古いdecode/data cacheが残らないこと
- runをまたいでexport/importしたflashのbyte完全一致
- `Picocalc_NESco`のmetadata、iNES header、PRG/CHR先頭・末尾・複数中間sample
- mapperが実行中に行うrandom/banked PRG readの結果
- SD sourceとの全file比較とSHA-256

`Picocalc_NESco`は`multicore_lockout_start_blocking()`、割込み禁止、`flash_range_erase/program()`、`flash_flush_cache()`を実際に使うため、その経路も迂回しない。

**Gate M-NESCO-S1（今回完了）:** 既存direct bootの`Picocalc_NESco` BINをclean backendで実行し、FAT32 RAW imageからSD ROMを選択、flash erase/program、XIP反映、scenario PASS、flash exportを1 runで決定的に確認する。実行証拠は
`firmware-validation/evidence/m-nesco-20260813-01/`に保存した。

実測値は、firmware source commit `ce67aa76e86dec700f086cd70214c247d6317da8`、BIN SHA-256
`ce865f2a26fecc55cfd033abfc71590c9918499c477fee81897f7ca5ababeb1c`、backend commit
`ae49c6c090dbd26c08c8360821cc6b2cc2c66dbe`（`dirty=false`）、1,316,021,684 cycles、scenario
exit 0である。SDは64 MiB FAT32、source SHA-256
`95fedb2fa5b83a08c8480bb1da654bd25a03f0005fc5471c6606d4180b2f65e0`。flashは2 MiB、12 erase、179
program、45,824 bytes、unknown command 0件、errors 0件だった。

M-NESCO-S1は「`Picocalc_NESco`をdirect bootでSD/flash debugへ使い始められる」ことを宣言する
中間gateであり、複数size/mapperの網羅、全量のrun-to-run再attach比較、directory import、boot2、
watchdog、実`uf2loader` end-to-endを完了したことを意味しない。これらはM-NESCO拡張受入またはU3以降で行う。

### M-NESCO拡張受入 — **実装・受入完了 2026-08-22**

U5-B watchdog warm resetの受入後、M-NESCO-S1を複数入力と複数観測経路へ拡張する。対象は
複数mapper、小・中・大容量ROM、PRG／CHRの先頭・中間・末尾read、CPU instruction fetch／data read、
core 1／DMAからのXIP read、flash export後の再attach、run間のflash SHA-256一致、SD sourceのROM
file SHA-256一致である。mapper全般やuf2loader全体の互換性はこのgateの主張に含めない。

ROM fixtureの合法なprovenance、iNES／NES 2.0 header、サイズ分類、境界sample、test-onlyのcore 1／DMA
probe、run A／B／repeatの入力とfail-closed判定を、専用の実装前契約
[`history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md)へ固定した。
診断oracle、host runner、計画4ケース＋追加mapper 1のA/B反復、clean source再build、evidence manifestを実装・固定した。
このgateを完了しても`uf2loader supported`へ昇格せず、U6 end-to-endの限定capabilityとは別に扱う。
実行証拠は[`firmware-validation/evidence/m-nesco-ext-20260822-01/`](../firmware-validation/evidence/m-nesco-ext-20260822-01/)に保存した。

### M-NESCO後の次段階: SD-GEN-1 汎用SD protocol一般化 — **P0〜P5完了**

M-NESCO拡張受入後に、SDプロトコルの一般化をP0〜P5の独立した段階として実施した。M-NESCO拡張は、
複数ROM・flash/XIP read経路・再attachを先に閉じるための前提受入ゲートであった。

その後のSD-GEN-1では、uf2loaderの固定版traceだけを基準にせず、PicoCalcアプリが利用する
汎用SD block-device経路を対象にする。対象は実際の利用要求と一次traceから段階的に固定し、
少なくとも次を個別の実装・unit test・trace契約として管理する。

- single／multi-block readと停止・busy遷移
- single／multi-block writeと事前消去指定
- CRC、data token、CS境界、エラー応答
- FAT16／FAT32を利用するFatFs経路の回帰
- unknown command／不正token／途中失敗のfail-closed
- uf2loader、NESco、その他の代表アプリごとのコマンド使用範囲

SD-GEN-1 P5では、`uf2loader-e2e` capabilityを汎用SD互換性の根拠に流用せず、P4のdefault-runtime
E2Eを親証拠とする新しいversioned validation contractを追加した。U6の固定版uf2loader受入は保持し、
一般化した範囲だけを`sd-multi-block`のbounded capabilityとして反映した。契約とdecision evidenceは
[`SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)および
[`firmware-validation/evidence/sd-gen1-p5-20260823-01/`](../firmware-validation/evidence/sd-gen1-p5-20260823-01/)に固定している。

### U3-A: host directory ↔ RAW image 標準ツール — **完了 2026-08-13**

runnerの前処理・後処理をAIごとの自作scriptにしないため、`picocalc_emu/tools/sd_image.py`を
stdlib-onlyの標準host toolとして追加し、`tools/picocalc.py sd pack/extract`へ統合した。
FAT32を既定、FAT16を明示profileとし、固定geometry／timestamp／volume parameter、名前順、VFAT
LFN、8.3 alias、atomic output、JSON manifestを提供する。symlink／special file／case collision、
破損BPB・FAT・LFN・chain、出力pathのsymlink、同時変更中の入力はfail-closedで拒否する。

このツールはrunnerの`--sd-image`／`--sd-image-out`と組み合わせて使う。手順と制約は
[`../USER_GUIDE/SD_IMAGES.md`](../USER_GUIDE/SD_IMAGES.md)に固定した。U3-A単体は`--sd-dir`の
実装でもhost directoryのlive mountでもない。U3-Bはこのpack処理をwrapperから一度だけ呼び出す。
packしたimageのsuper-floppy sector 0がFAT BPBとなる。

**Gate U3-A:** FAT32／FAT16のround-trip、同一treeのimage SHA一致、LFN／Unicode、symlink・collision・
malformed image・入力同時変更の拒否をlocal testで確認する（CIは実行しない）。

### U3-B: runner-integrated directory snapshot import — **完了 2026-08-22**

`--sd-dir`はhost filesystemをfirmwareへ直結しない。起動時に次の順でFAT32 imageを決定的に作り、既存SD SPI/FatFs経路へ渡す。

1. directory treeを安全に走査
2. entryをbyte順にsort
3. fixed timestampと固定volume parameterでFAT32へ格納
4. run中は通常のblock deviceとして扱う
5. 必要なら`--sd-image-out`でRAWを保存

拒否するもの:

- symlink、device、socket等のregular file/directory以外
- root外へのescape
- case-insensitiveな名前衝突
- FATで表現できない名前または容量超過
- 読取り不能file

directory側への書戻しは行わない。これにより、hostの予期しない削除・rename・上書きを避ける。

U3-Aでhost packerは確定したため、U3-Bはこのpack結果をrunner起動時に接続するCLI／contract／
artifact境界に限定する。公開入口は`tools/picocalc.py test --mode firmware --sd-dir`であり、
wrapperが一時RAWを作ってbackendの既存`--sd-image`へ渡す。`mkfs.fat`や`mcopy`がhostに偶然
入っていることを前提にしない。`--sd-manifest`はtree/image SHAとentry一覧をatomicに保存し、
runner reportの`sd.raw_image.bytes`／`source_sha256`を同じ生成物へfail-closedで照合する。

実装は`picocalc_emu`のwrapperと既存`sd_image.py`に限定し、`picoem-picocalc`のstandalone
`--sd-image`契約は変更しない。ただし、U3-Aで既知だった`export_raw`のsame-path判定をbackend側で
親directoryのcanonical pathまで比較し、symlink outputを拒否する回帰修正を同じ作業単位に含めた。
`--sd-dir`は登録targetがattached FAT32を要求する場合だけ許可し、FAT16、detached target、
`--sd`との併用は拒否する。これはlive host-directory mountや双方向同期ではなく、起動時の一回限り
のsnapshot importである。

**Gate U3-B:** rootの`BOOT2040.UF2`と`pico1-apps/TEST.UF2`をloader相当のFatFs経路で列挙/open/readでき、
同じtreeから毎回同じimage SHAを得て、`--sd-image-out`と同一のmanifest境界を保つ。
ローカルのCLI fixture、同時変更拒否、profile競合拒否、reportのsource SHA／bytes照合を完了した。

### U4: uf2loader実行で判明したSD protocol gap

実loaderのprotocol traceを一次証拠として、不足したcommand、data token列、CS解除またはstop commandによる終了、error/CRCの扱いを実装する。U4-P2ではclean loaderを3回実行し、CMD17のみ（CMD18/CMD12/CMD23/CMD24/CMD25は未観測）でSRAM UIへ到達した。traceなし／traceありのreportとUARTも一致したため、**固定版uf2loaderのU4/U6受入経路に限っては**multi-block protocolのproduction追加を行わない。これは汎用SD互換性の宣言ではない。途中で検出したCMD17のR1→data token順序バグだけをunit test付きで修正した。準備・測定・判定は完了済み履歴の[`history/uf2loader/UF2LOADER_U4_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U4_PREFLIGHT_20260822.md)へ、U5-Aの実装境界と検証結果は[`history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md)へ固定した。

CMD18/CMD12が観測されなければ、固定版uf2loaderのU4受入では「追加変更不要」として閉じる。これは「エミュレーター全体で不要」という意味ではない。M-NESCO拡張受入後のSD-GEN-1 P0〜P5で、uf2loader以外のアプリ向けにboundedなmulti-block command surfaceを一般化し、未対応コマンドは明示的にfail-closedした。未観測のcommandを現在のU4へ推測追加していない。

**Gate U4:** clean loader traceでsingle-blockの既存回帰を保ち、CMD18/CMD12等の追加gapがないことを確認する。今回のU4-P2では`BOOT2040.UF2`をSRAM UIへ読み込む経路までを確認し、multi-block追加なしと判定した。選択app UF2、flash書込み、watchdog resetを含むend-to-endはU6で受入する。未知commandは従来どおりvisible failureとする。

### U5-A: boot2 entry

既存defaultの`direct_boot_from_flash(0x100)`は変えない。通常のアプリdebugは今後もこの経路を使う。`--boot-mode boot2`を明示したuf2loader conformance runだけが、flash先頭の実際のboot2へ入る。実装境界、ローカル検証、正式受入条件は完了済み履歴の[`history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U5A_BOOT2_PREFLIGHT_20260822.md)に固定した。

full bootromやUSBを実行するのではなく、RP2040 reset後にboot2へ制御を渡す最小の起動modeとする。RP2040版uf2loaderでは、flash先頭の256-byte custom boot2がtop 16 KiB内のflash-resident stage3へ渡り、stage3が`BOOT2040.UF2`をSRAMへloadしてUIへ渡す。この実配置とhandoffを迂回せずに通す。U5-Aではboot2→stage3 entryまでを受入範囲とし、SD protocol変更、watchdog reset、UF2選択までは含めない。

**Gate U5-A:** `--boot-mode boot2`でclean uf2loader artifactを起動し、boot2からstage3 vector／entryへ到達する。既定app modeの既存reportと回帰は変えない。U5-A合格後にU4のclean SD protocol traceを取得する。

### U5-B: watchdog warm reset

watchdogはまず、`watchdog_reboot(0,0,0)`が使う即時TRIGGERを実装する。warm resetでは、

- flash内容とSD backingを保持
- CPU、DMA、PIO、IRQ、timer等をreset stateへ戻す
- watchdog scratchのdatasheet上の保持条件を守る
- runner全体の単調なcycle/epochを保持し、scenario時刻を巻き戻さない
- 同じboot modeでboot2へ再入場

とする。任意delayのwatchdog timer完全再現は今回の対象外である。

起動時menu keyは、既存のpre-queued keyで0.5秒windowを再現できるかを先に試す。不足する場合だけ、scenario schemaへ最小の`preboot key event`を追加する。一般的なbranch/loop機能までは足さない。

**Gate U5-B:** menu選択boot、app既定boot、flash後watchdog resetの3経路を区別してreportでき、reset前後でflash/SDは保持される。

### U6: 実uf2loader end-to-end

実装前のartifact、入力時刻、観測項目、fail-closed条件は
[`history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md`](history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md)に固定した。
clean buildした外部uf2loaderと、自作test appを使って次を1つのscenarioで通す。

U6-P0のhost tool（`python3 tools/picocalc.py uf2 inspect/assemble`）とsynthetic UF2 unit testを実装した。
さらに`python3 tools/picocalc.py uf2 e2e`を追加し、cleanな外部loader source／artifactとclean backendを
固定した3回Gateを実装した。U5-Bのclean commitを前提に、M-NESCO拡張とは独立した固定LCD fixtureでP1〜P4のboot2、SD loader UI、
UF2選択、erase/program、watchdog warm reset、再起動、再attach、determinismを一つの証拠manifestへ固定した。

1. `bootloader_pico.uf2`から作った**raw initial flash**をattach（UF2を`--bin`へ直接渡さない）
2. directory importまたは同一内容のRAW SDをattachし、rootに`BOOT2040.UF2`、`pico1-apps/TEST.UF2`を置く
3. boot2からstage3へ入り、既存appのproginfoが無い主シナリオでは起動前キーなしでloader UIへ進む
4. `BOOT2040.UF2` UIが起動
5. `pico1-apps/TEST.UF2`を選択
6. erase/program完了
7. watchdog reset
8. stage3が新appを起動
9. appのUART marker、framebuffer、終了条件を検証
10. final flashをexportしてUF2 payloadと比較

受入artifact:

- uf2loader/test app source commitとtoolchain identity
- initial flash、BOOT2040、test UF2、SD inputのSHA-256
- SD command count/trace digest
- flash erase/program sector/page count、before/after SHA-256
- reset回数とboot epoch
- final flash image SHA-256
- UART、framebuffer、scenario timeline、structured verdict
- loaderのtop 16 KiBと保存したboot2が不変である検査結果

既存appがある状態でUp/F1/F5を押してloaderへ入る起動前キー経路は、現在のscenario投入時刻が
stage3の0.5秒windowへ届くことを先に証明できた場合だけ追加coverageとする。主Gateはbootloader-only
initial flashで閉じ、preboot key eventの未実装を隠れた前提にしない。

**Gate U6:** 同一入力の3 runがdeterministicで、全契約に合格する。2026-08-22に合格し、
[`firmware-validation/evidence/uf2loader-u6-20260822-01/`](../firmware-validation/evidence/uf2loader-u6-20260822-01/)
へ凍結した。ここで初めて、全UF2互換を意味しない限定された`uf2loader-e2e` capabilityを有効化する。

## 7. negative tests

少なくとも次をfail-closedで確認する。

- RAW sizeが512の倍数でない、空、read不能
- directoryのsymlink、case衝突、容量超過
- `BOOT2040.UF2`欠落または壊れたUF2
- wrong family ID、block magic不正、block重複、範囲外target address
- CMD18中の不正token/中断
- WELなしerase/program
- erase/programの範囲・alignment違反
- page跨ぎと0->1 program
- flash mutation後に古いdecode結果を実行しないこと
- watchdog reset後にSD/flashが消えないこと
- output path競合、途中失敗で既存outputを壊さないこと

`reset_usb_boot`へ落ちた場合は「成功」と扱わない。今回USB BOOTSELはunsupportedなので、`unsupported_usb_boot_path`等の安定した理由付き`cannot_judge`または期待したnegative verdictとして明示する。

## 8. 回帰・品質条件

- 既存target、既存report schemaの意味、promoted backendを変更しない
- 新しいreport fieldは機能使用時だけ出すか、新schema revisionとして管理する
- 現行のSD FAT32/FAT16、PicoTetris、PicoEdit、multicore、audioのlocal regressionを維持
- 既存CLIのdefault boot modeがdirect bootのままであることを回帰testで固定する
- flash変更経路を使わないworkloadの性能を退行させない
- deterministic artifactを3回比較
- 実装、debug、lint、testはすべてlocalで行う
- GitHub Actionsをdebugに使わない。workflowは明示許可なしに変更しない
- 小変更ごとにpushせず、各gateをlocalで完了して関連変更をまとめる
- CIが必要になった場合は、localで代替できない理由と予想使用量を先に説明して許可を得る

## 9. 文書更新

実装と同じcommit群で次を更新する。

- `README.md`: RAW/directory/uf2loaderの利用例と非対応範囲
- `AI_START_HERE.md`: 外部workspaceを必須としない通常開発、optional external conformance
- `docs/FIRMWARE_BACKEND.md`: boot mode、SD backing、flash mutation/reset semantics
- `docs/IMPLEMENTATION_STATUS.md`: 各gateの完了状態
- `firmware-validation/capability.json`: 実装済みだけをsupportedへ移し、未完はlimitationに残す
- CLI `--help`と`tools/picocalc.py` forwarding tests
- 新しいend-to-end validation/record

本計画中は、既存の未コミット変更を混ぜずに作業単位を分離する。

## 10. 工数見積り

| 段階 | 見積り |
|---|---:|
| U0 契約・clean fixture・protocol trace | 6〜10時間 |
| U1 file-backed RAW + COW + export + report/tests | 12〜18時間 |
| U2 flash erase/program + cache coherence | 20〜32時間 |
| M-NESCO Picocalc_NESco direct-boot実用検証 | 8〜14時間 |
| U3-A host pack/extract標準ツール | **完了** |
| U3-B runner-integrated directory import | **完了** |
| U4 実traceで判明したSD gap（P2判断完了、正式record再取得を残す） | **完了。clean trace／unit test／追加production codeなし** |
| U5-A boot2 entry | **完了。production実装・clean evidence固定** |
| U5-B watchdog warm reset | **完了。flash／SD保持とboot2再入場をlocal regressionで固定** |
| M-NESCO拡張受入（fixture／probe／再attach／provenance） | **完了 2026-08-22** |
| U6 実uf2loader scenario/negative/artifact | **完了 2026-08-22** |
| 文書・全local回帰・公開境界監査 | **U0〜U6／M-NESCO拡張分を完了** |
| **SD-GEN-1 P5** | **完了。versioned validation contract、bounded capability、decision evidenceを固定** |

上表の初期工数は実装前の見積りを履歴として残したものであり、完了後の残作業見積りではない。U0〜U6、
M-NESCO拡張、SD-GEN-1 P0〜P5の実装・local回帰・証拠固定は完了した。次の作業は新しい正式計画が立つまで保留する。

42〜60時間程度で作れるsyntheticな「SDからUF2を読んで直接chain-loadするデモ」は、本計画の最終目標ではない。今回は**実際のuf2loader、実際のflash helper、実際のwatchdog reboot**を通すため、その差分を工数へ含めている。

## 11. 実施順序と分担

Solが契約、hardware semantics、gate判定、最終検収を担当する。Lunaには、明確なfixture生成、table/manifest作成、反復test追加、documentation cross-checkを委譲する。委譲結果はSolがsourceとartifactで再確認する。

実施順序は固定する。

```text
U0 契約固定
 -> U1 RAW
 -> U2 flash erase/program
 -> M-NESCO Picocalc_NEScoで実用開始判定
 -> U3-B directory import（完了）
 -> U5-A boot2 entry
 -> U4 SD実loader gap（必要な場合だけ実装）
 -> U5-B watchdog warm reset
 -> M-NESCO拡張受入（複数mapper／サイズ／read path／flash再attach）
 -> U6 uf2loader end-to-end
 -> SD-GEN-1 P0〜P5 汎用SD protocol／versioned validation／bounded capability
 -> 文書/capability公開判定
```

U4-P2のclean trace取得とprotocol判断、U5-B、U6 Gate、M-NESCO拡張受入は完了した。`picocalc-run --sd-trace <path>`はdiagnostic-onlyのまま保持し、CMD18／CMD12等のproduction codeは追加していない。U6とM-NESCOのevidenceはbackend/sourceをclean commitへ固定したうえで取得し、固定LCD fixture専用のcapabilityとNESco-specific evidenceを分離して保存した。通常のdirect boot debugは変更しない。

計画の実施順は、M-NESCO拡張をU6の固定LCD fixtureと独立したGateとして実施し、その後SD-GEN-1を
P0〜P5で完了した。U6とM-NESCO、SD-GEN-1は別々の証拠・capability境界を持つ。SD-GEN-1 P5で対象commandを
versioned contractへ固定し、未観測commandを追加で推測していない。次の作業は新しい正式計画が立つまで保留する。
