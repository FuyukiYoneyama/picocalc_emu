# UF2 Loader を目標とする SD / flash 統合実装計画

作成日: 2026-08-13
対象: `picocalc_emu` / `picoem-picocalc`
状態: **計画固定。実装未着手。**
目標アプリ: RP2040 PicoCalc 用 [`pelrun/uf2loader`](https://github.com/pelrun/uf2loader)

## 1. 結論

次の機能を、依存関係のある**1つの縦方向の機能追加**として実施する。

1. SDカードのRAW image入力
2. RP2040 flashのerase / program
3. `Picocalc_NESco`をdirect bootでdebugできる中間マイルストーン
4. ホストdirectoryからSD内容を読み込むsnapshot import
5. 実loaderで観測したSD protocol gap
6. boot2 entry、watchdog warm reset、実`uf2loader` end-to-end

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

### U0: 契約、fixture、protocol traceを固定

実装前に次を固定する。

- cleanなuf2loader source commit、submodule、SDK、compiler、CMake/Ninja version
- `bootloader_pico.uf2`と`BOOT2040.UF2`のSHA-256
- 外部配布物を含まない自作test app UF2
- SD directory manifest
- loaderが実際に発行するSD/SSI/watchdog access trace
- 「既存の何が不足して停止するか」を示すfirst-run record

初期flashは、2 MiBを`0xFF`で埋め、`bootloader_pico.uf2`のpayloadを適用して作る。objcopyのsparse gapが`0x00`になったBINを、そのままblank flashと誤認して使わない。

**Gate U0:** source/toolchain/artifact SHAが固定され、GPL artifactをrepositoryへ入れず再現できる。

### U1: SD RAW image

SDのsector storageをinterface化し、既存memory backingと新しいRAW backingを分離する。

- input sizeは非0かつ512 byteの倍数
- block indexの範囲外は明示error
- input fileはrun中に直接変更しない
- firmware writeはsector overlayへ記録
- 未変更runのexportはinputとbyte-for-byte一致
- 変更runは次回の`--sd-image`で再利用可能
- input/output SHA、block数、read/write数、dirty block数をreportへ記録

**Gate U1:** FAT32/FAT16の既存RAW imageをmount/readでき、1 sectorの変更をexportして次runで読める。異常size、範囲外、同一input/outputはfail-closed。

### U2: flash erase / program

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

**Gate U2:** erase、program、readback、WEL/WIP、cache invalidationがunit/integration testを通る。不正alignment、page crossing、範囲外、WELなし、0->1は黙って成功しない。

### M-NESCO: `Picocalc_NESco`デバッグ開始マイルストーン

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

**Gate M-NESCO:** RAW SD imageから選んだ複数size/mapperのROMについて、stage、全量verify、同一run実行、final flash再attach後の復元が決定的に合格する。このgate以降は`Picocalc_NESco`のdebugへ使用可能と明記できるが、directory import、boot2、watchdog、uf2loader conformanceはまだ未完了と表示する。

### U3: directory snapshot import

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

実装開始時に、外部commandへ依存しない方法を決める。第一候補はlicenseとmaintenance状態を確認したpinned permissive-licenseのRust FAT libraryである。適切なlibraryがなければ、小さなFAT32 packerを自作するが、その場合はU3の工数を再見積りする。`mkfs.fat`や`mcopy`がhostに偶然入っていることを前提にしない。

**Gate U3:** rootの`BOOT2040.UF2`と`pico1-apps/TEST.UF2`をloader相当のFatFs経路で列挙/open/readでき、同じtreeから毎回同じimage SHAを得る。

### U4: uf2loader実行で判明したSD protocol gap

実loaderのprotocol traceを一次証拠として、不足したcommand、data token列、CS解除またはstop commandによる終了、error/CRCの扱いを実装する。source上はCMD18を選択できる構造を持つが、対象のFAT readが実際に複数sector要求になるかはU0 traceで確定する。CMD18/CMD12が観測されなければ、実装したことにせず、U4は「追加変更不要」として閉じる。未観測のcommandを推測で広く追加しない。

**Gate U4:** single-blockの既存回帰を保ち、`BOOT2040.UF2`と選択したapp UF2を途中で欠落・重複せず読み切る。未知commandは従来どおりvisible failureとする。

### U5: boot2 entryとwatchdog warm reset

既存defaultの`direct_boot_from_flash(0x100)`は変えない。通常のアプリdebugは今後もこの経路を使う。`--boot-mode boot2`を明示したuf2loader conformance runだけが、flash先頭の実際のboot2へ入る。

full bootromやUSBを実行するのではなく、RP2040 reset後にboot2へ制御を渡す最小の起動modeとする。RP2040版uf2loaderでは、flash先頭の256-byte custom boot2がtop 16 KiB内のflash-resident stage3へ渡り、stage3が`BOOT2040.UF2`をSRAMへloadしてUIへ渡す。この実配置とhandoffを迂回せずに通す。

watchdogはまず、`watchdog_reboot(0,0,0)`が使う即時TRIGGERを実装する。warm resetでは、

- flash内容とSD backingを保持
- CPU、DMA、PIO、IRQ、timer等をreset stateへ戻す
- watchdog scratchのdatasheet上の保持条件を守る
- runner全体の単調なcycle/epochを保持し、scenario時刻を巻き戻さない
- 同じboot modeでboot2へ再入場

とする。任意delayのwatchdog timer完全再現は今回の対象外である。

起動時menu keyは、既存のpre-queued keyで0.5秒windowを再現できるかを先に試す。不足する場合だけ、scenario schemaへ最小の`preboot key event`を追加する。一般的なbranch/loop機能までは足さない。

**Gate U5:** menu選択boot、app既定boot、flash後watchdog resetの3経路を区別してreportでき、reset前後でflash/SDは保持される。

### U6: 実uf2loader end-to-end

clean buildした外部uf2loaderと、自作test appを使って次を1つのscenarioで通す。

1. `bootloader_pico.uf2`から作ったinitial flashをattach
2. directory importまたは同一内容のRAW SDをattach
3. 起動時にUp/F1/F5のいずれかを入力
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

**Gate U6:** 同一入力の3 runがdeterministicで、全契約に合格する。ここで初めて`uf2loader supported`へcapabilityを昇格する。

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
| U3 deterministic directory import | 16〜26時間 |
| U4 実traceで判明したSD gap（変更不要なら監査だけ） | 2〜12時間 |
| U5 boot2 entry + watchdog warm reset | 16〜28時間 |
| U6 実uf2loader scenario/negative/artifact | 16〜24時間 |
| 文書・全local回帰・公開境界監査 | 8〜12時間 |
| **合計** | **104〜176時間** |

目安は**実働13〜22日**である。directory importに適切なlibraryを使えない、実loaderが未観測のSD/SSI commandを要求する、warm resetが既存cycle契約へ広く影響する場合は上限を超える。その場合は問題を隠して範囲を縮めず、該当gateで停止して再見積りする。

42〜60時間程度で作れるsyntheticな「SDからUF2を読んで直接chain-loadするデモ」は、本計画の最終目標ではない。今回は**実際のuf2loader、実際のflash helper、実際のwatchdog reboot**を通すため、その差分を工数へ含めている。

## 11. 実施順序と分担

Solが契約、hardware semantics、gate判定、最終検収を担当する。Lunaには、明確なfixture生成、table/manifest作成、反復test追加、documentation cross-checkを委譲する。委譲結果はSolがsourceとartifactで再確認する。

実施順序は固定する。

```text
U0 契約固定
 -> U1 RAW
 -> U2 flash erase/program
 -> M-NESCO Picocalc_NEScoで実用開始判定
 -> U3 directory import
 -> U4 SD実loader gap（必要な場合だけ実装）
 -> U5 boot/reset
 -> U6 uf2loader end-to-end
 -> 文書/capability公開判定
```

次に着手する作業は**U0「clean provenance・fixture・first-run traceの固定」**である。U0が閉じるまでproduction codeは変更しない。
