# UF2Loader U6 end-to-end preflight

作成日: 2026-08-22
対象: `picocalc_emu` / `picoem-picocalc` / 外部 `uf2loader`
状態: **U6 Gate合格（2026-08-22）。実行証拠を固定済み。限定されたuf2loader経路をcapabilityへ反映済み。**

この文書は、[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](../../UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)
の最終ゲート U6 について、入力artifact、実行順序、判定条件、失敗時の停止点を固定するものである。
U5-B watchdog warm resetをcleanなbackend commitで閉じた後、M-NESCO拡張とは独立した固定LCD fixtureで
実行した。M-NESCO拡張の実装・受入はこのrecordに含めない。USB BOOTSEL/MSCは対象に含めない。証拠は
[`firmware-validation/evidence/uf2loader-u6-20260822-01/`](../../../firmware-validation/evidence/uf2loader-u6-20260822-01/)
へ固定している。

U6-P0として `tools/uf2_image.py` と `python3 tools/picocalc.py uf2 inspect/assemble` を追加し、
UF2のstrict validationと2 MiB (既定) raw XIP flash assemblyを実装した。さらに
`python3 tools/picocalc.py uf2 e2e`を追加し、cleanな外部loader source／artifactとclean backendを
固定して、同一入力を3回実行するU6 Gateを実装した。GateはUF2 block、loader／boot2保護領域、
NOR erase/programモデル、watchdog epoch、SD trace、UART、report、framebuffer、flash SHA、
再attachを機械判定する。

## 1. 目的と境界

U6で証明する経路は次の一続きである。

```text
boot2
  -> stage3
  -> SD上のBOOT2040.UF2をSRAMへ読み込み
  -> uf2loader UI起動
  -> SD上のアプリUF2を選択
  -> UF2検証、flash erase/program
  -> watchdog warm reset
  -> boot2 -> stage3
  -> 書込み済みアプリをXIPから起動
  -> UART / framebuffer / 終了条件を判定
```

ここでいう「実uf2loader」は、外部repositoryのcleanなRP2040 buildを使うことを意味する。
エミュレーター側で同等のsynthetic loaderを作って代用しない。逆に、実機のUSB BOOTSEL/MSCや
Down/F3によるBOOTSEL分岐はU6の成功条件ではない。通常のPicoCalc転送はuf2loader経由であり、
U6はそのSD・flash・reset経路をエミュレーター内で検証するためのものである。

### 1.1 U6でまだ宣言しないこと

- 全UF2形式・全family IDの互換性
- 全mapper／全ROMのNESco互換性（これはM-NESCO拡張の範囲）
- USB BOOTSEL/MSCの再現
- 任意のwatchdog delay、電源断、brown-outの再現
- 人間がUIを操作した場合の視認性やキーの物理的感触

## 2. 前提となる完了条件

U6のproduction実装へ進む前に、次をcleanなcommitとローカル証拠で閉じる。M-NESCO拡張は別の受入項目であり、
U6の固定LCD fixture Gateの前提には含めない。

| 前提 | 必須状態 | U6での役割 |
|---|---|---|
| U3-A/U3-B | host directory ↔ deterministic RAW snapshot | SD入力を同一内容で再生成する |
| U4-P2 | clean loader traceに基づくCMD17判断 | 未観測のmulti-block commandを推測実装しない |
| U5-A | `--boot-mode boot2`でboot2→stage3 entry | 初期flashの先頭から実boot2へ入る |
| U5-B | flash/SDを保持したwarm reset | UF2 program後にstage3へ再入場する |
| M-NESCO-S1 | 既存direct-boot SD/flash debug | U6導入前のSD/flash/XIP回帰を保つ。拡張受入は別項目 |

外部 `uf2loader` はpinされたsource commit、Pico SDK、compiler、CMake、Ninjaを記録し、
worktree cleanを確認する。外部checkoutに残る作業中の変更や未追跡build directoryを証拠へ使わない。
既知のpinはU4 traceで使用した `5c44a4b64749062b0200507ceeff3ef2b475e288` だが、
実際に採用するcommitはU6開始時にsource、toolchain、build manifestと一緒に再固定する。

## 3. 入力artifactの役割を混同しない

現行runnerの `--bin` は**rawなXIP flash image**を受け取る。UF2コンテナをそのまま
`--bin`へ渡してはならない。U6では最低限、次の3種類を別々に管理する。

| artifact | 役割 | 配置・入力 |
|---|---|---|
| `bootloader_pico.uf2` | boot2、stage3、proginfoを含む初期flashの材料 | hostでUF2 blockをraw flashへ決定的に展開し、`--bin`へ渡す |
| `BOOT2040.UF2` | SD rootからstage3がSRAMへ読み込むloader UI | SD imageのroot `/BOOT2040.UF2` |
| `TEST.UF2` | loader UIが選択してflashへ書き込む検証用アプリ | SD `/pico1-apps/TEST.UF2` |

`bootloader_pico.uf2`と`BOOT2040.UF2`は同じものではない。初期flashを作るhost-side
UF2 assembler（または同じ仕様の決定的な既存tool）をU6-P0で固定し、2 MiB flash imageの
サイズ、書込みblock、未使用領域の初期値、target address範囲を記録する。UF2 assemblerを
実装する場合も、loader本体へUF2の曖昧な解釈を持ち込まず、入力・出力SHAと範囲検査を持つ
小さなhost toolとして分離する。

SD側はU3-Bの `--sd-dir` から作る一回限りの決定的FAT32 snapshot、または同じ内容のRAW imageを
使う。SD treeは少なくとも次を含む。

```text
BOOT2040.UF2
pico1-apps/TEST.UF2
```

ファイル名のcase、8.3変換、ディレクトリ順、paddingをmanifestへ記録し、同じtreeを2回packした
SHA-256が一致することを先に確認する。入力UF2、raw initial flash、SD image、生成appのsource
commitはすべて公開可能なprovenanceまたは合法な自作fixtureでなければならない。

## 4. 実行シナリオ

### 4.1 主シナリオ（起動前キー不要）

初期flashは、既存アプリの有効なproginfoを持たないbootloader-only状態にする。この状態では
stage3が既存アプリを起動できず、SDから `BOOT2040.UF2` を読み込んでloader UIへ進むため、
scenario開始前の0.5秒boot menuへUp/F1/F5を注入する必要がない。これは現在のrunnerの入力時刻
制約を隠さずに、要求されたU6経路を再現する最小の主シナリオである。

1. `bootloader_pico.uf2`から決定的にinitial raw flashを作る。
2. initial raw flashを `--bin` でattachし、`--boot-mode boot2`を明示する。
3. SD snapshotをattachする。SD rootに`BOOT2040.UF2`、`pico1-apps/TEST.UF2`があることを確認する。
4. boot2がstage3へ渡り、stage3がSDをmountする。
5. stage3が`BOOT2040.UF2`を読み込み、SRAM上のloader UIへ制御を渡す。
6. loader UIで`pico1-apps/TEST.UF2`を選択する。アプリが1件だけなら、directory UIの初期選択とEnterを
   raw `key_events`で明示する。
7. UF2 magic、family、block順、block数、target addressを検査し、flash erase/programを行う。
8. loaderがproginfoを更新して`watchdog_reboot(0,0,0)`相当を発行する。
9. warm reset後、flashとSDを保持したままboot2→stage3へ再入場する。
10. stage3が更新されたproginfoを読み、XIPのアプリentryを起動する。
11. test appのUART marker、framebuffer、終了理由、必要なreport fieldを判定する。
12. `--flash-image-out`でfinal flashをexportし、UF2 payloadとflash範囲を比較する。

### 4.2 起動前キー経路（追加coverage、主Gate外）

外部loaderは既存アプリがある場合、boot時のUp/F1/F5（`0xb5`/`0x81`/`0x85`）でSD loaderを選ぶ。
一方、現行scenarioのkey injectionはfirmware実行loop開始後に投入されるため、stage3の最初の
0.5秒windowへ確実に届くとは限らない。したがって、U6実装時にこの経路を「通るはず」と仮定しない。

次のどちらかを別途明示して選ぶ。

- 最小実装: 主シナリオをbootloader-onlyに固定し、既存アプリ＋起動前キーはU6-P1の追加coverageへ送る。
- 必要性が証明された場合だけ: preboot key eventをscenarioへ最小拡張し、Up/F1/F5のboot menu選択を
  独立fixtureとして追加する。一般的なbranch/loopやUI自動化言語は作らない。

この決定を記録しないまま、通常scenarioのEnterをboot menuキーの代わりに扱ってはならない。

## 5. 観測と受入artifact

U6 runは通常のstdout JSON reportとstderr heartbeatを分離し、UART、framebuffer、SD trace、flash exportを
別artifactとして保存する。最低限、次のmanifestを1 runごとに残す。

### 5.1 provenance

- `picocalc_emu` commit、`picoem-picocalc` commit、dirty=false
- uf2loader source commit、worktree clean、SDK/toolchain/CMake/Ninja版
- test app source commit、BSP commit、LCD variant
- `bootloader_pico.uf2` SHA-256
- `BOOT2040.UF2` SHA-256
- `TEST.UF2` SHA-256、UF2 family ID、block count、payload address range
- initial raw flash SHA-256、SD tree manifest SHA-256、SD image SHA-256

### 5.2 実行経路

- boot modeとboot epoch（初回boot2、warm reset後の2回目boot2）
- boot2 vector／stage3 entry marker
- `BOOT2040.UF2`のSD read開始・完了、UI entry marker
- 選択された相対pathが`/pico1-apps/TEST.UF2`と一致したこと
- UF2 block validation結果、erase sector数、program page数、program bytes
- WEL、page boundary、0→1禁止、範囲・alignment違反のエラー数
- watchdog reset発行、scratch command、reset後のscratch消費
- 更新後appのUART marker、framebuffer digest、scenario stop reason

### 5.3 内容保持

- warm reset前後のSD backing SHAが一致
- 書込み対象外のflash範囲が一致
- boot2とloader保護領域（top 16 KiB）のSHAが一致
- final flashのapp payloadが`TEST.UF2`のpayloadと一致
- exportしたflashを再attachして同じapp markerへ到達

U6のfinal flash比較は、UF2 blockのpayloadをtarget addressへ配置した範囲だけでなく、
書込み対象外領域と保護領域の不変性も別fieldで判定する。単に最終画面が同じことを成功条件にしない。

## 6. fail-closed条件

次のいずれかが起きたrunはPASSにしない。

- initial flashをUF2から決定的に組み立てられない、または`--bin`へUF2を直接渡している
- source/toolchain/backendがpinと一致しない、worktreeがdirty、入力SHAがmanifestと不一致
- boot2、stage3、loader UI、selected app、warm reset、second boot epochのいずれかのmarkerが欠落
- `BOOT2040.UF2`が読めない、UIが起動しない、選択pathが期待値と違う
- UF2 magic/family/block順/block数/address範囲の検査を通っていない
- erase/programが要求された回数・範囲・bytesと一致しない
- WELなし、page跨ぎ、0→1、alignment、範囲違反を見逃す
- watchdog reset後にSDまたはflashの保持条件が破られる
- final appのUART/framebuffer/終了条件が欠落する、またはcycle limitで終了する
- final flashとUF2 payload、保護領域、再attach結果のいずれかが不一致
- 未対応MMIO、unknown SD command、exception、key drop、`reset_usb_boot`到達が残る

判定不能なrunは、成功へ丸めず `cannot_judge` として停止する。USB BOOTSEL/MSCへ落ちた場合もU6成功とは
扱わず、安定した理由付きのunsupported verdictを残す。

## 7. negative input guard

U6の受入では、実loaderを壊れたfixtureで何度も実行するのではなく、host-side strict UF2／flash
model boundaryで、壊れた入力がPASSへ丸められないことを確認する。runtime device faultの網羅は
U6 capabilityの範囲外であり、必要になった場合は別のnegative-conformance recordとして追加する。

- UF2欠落／空、CRC／magic破損、wrong family、重複／欠落block番号、範囲外address
- payload overlap、NOT_MAIN_FLASH、family flag欠落、不正payload長
- app payloadがboot2、stage3、proginfo、loader保護領域へ重なる
- loaderモデルのNOR 0→1、page跨ぎ、WEL／alignment／範囲エラーを見逃さないこと
- export先競合、途中失敗、再attach時のSHA不一致を成功へ丸めないこと

`reset_usb_boot`やSD電気的faultはUSB／device-fault経路の未対応を示すため、U6 positive Gateの一部には
数えない。

## 8. 実装順序と停止点

U6は、次の小さな実装単位で進める。各段階でlocal testとartifact reviewを行い、失敗した段階の外側を
先に実装しない。

| step | 内容 | 完了条件 |
|---|---|---|
| U6-P0 | UF2→raw initial flash assembler、SD tree、provenance manifest | **完了。strict parser／assembler／unit testをlocal確認** |
| U6-P1 | boot2→stage3→BOOT2040 UI到達 | **完了。clean loader source/buildで主scenarioのloader snapshotを取得** |
| U6-P2 | UI選択→UF2 validation→erase/program | **完了。UF2 block、erase/program、NOR readback、proginfo mutationが一致** |
| U6-P3 | watchdog warm reset→stage3→app launch | **完了。各run epoch 1、SD／flash保持、app snapshot PASS** |
| U6-P4 | final export/re-attach、3回determinism、negative input guard | **完了。3回のUART/report/framebuffer/flash/SD trace SHA一致、再attach PASS。strict UF2／loader-model negative unit testも合格** |
| U6-P5 | evidence review、versioned validation、capability判断 | **完了。evidence recordを固定し、限定されたuf2loader経路をcapabilityへ反映** |

どのstepでも、backendや入力のpinを変更して結果を合わせることを禁止する。外部loader側の修正が必要な
場合は、loaderのsource commitを新しいprovenanceとして固定し、U6-P0から再開する。

## 9. Gate U6

U6の正式受入は、同じclean inputを異なる出力ディレクトリで**3回**実行し、次をすべて満たすこととする。

1. 3 runのboot epoch、SD trace digest、erase/program counts、UART、framebuffer、final flash SHAが一致する。
2. boot2、stage3、loader UI、UF2選択、erase/program、watchdog、second boot、app launchの全markerがある。
3. UF2 payloadとfinal flashの書込み範囲が一致し、保護領域とSD backingが不変である。
4. final flash exportを初期flashへ再attachしたrunが同じapp markerへ到達する。
5. strict UF2／loader-model negative guardが壊れた入力をPASSへ丸めない。runtime device-faultのnegative conformanceは別recordとする。
6. 既存U0〜M-NESCOのlocal regression、default direct boot、既存targetの意味が変わらない。

このGateの合格後、`capability.json`へ「限定された実uf2loader SD→flash→warm-reset経路」を追加した。
これは全UF2、USB BOOTSEL/MSC、任意のloader forkを支持する宣言ではない。主Gateのpositive経路と
host-side strict UF2 negative unit testを保持し、今後のloader変更は新しいsource／artifact provenanceで
再実行する。

## 10. 工数見積りと実装しない範囲

U5-Bがcleanに完了していることを前提に、U6の実装・local検証・証拠整理を**20〜36時間**と見積もる。

| 作業 | 見積り |
|---|---:|
| UF2 assembler、fixture、provenance | 4〜6時間 |
| boot2／stage3／UI到達と入力境界 | 4〜8時間 |
| UF2選択、flash erase/program、warm reset統合 | 4〜8時間 |
| 3回determinism、re-attach、negative、evidence | 8〜14時間 |
| **合計** | **20〜36時間** |

外部uf2loaderのclean build、合法なtest app／fixtureの準備、既存U5-B／M-NESCOのやり直しは別見積りとする。
これらの前提が満たせない場合はU6を成功扱いにせず、不足している入力またはgateを明示して停止する。

## 11. 実装着手時の運用規則

- production codeを変更する前に、U6-P0の入力SHAとtoolchainを固定する。
- 通常のbuild、test、trace、negative、determinismはすべてlocalで行う。
- GitHub Actions workflowを追加・変更・debug目的で実行しない。必要性が出た場合は先に承認を得る。
- 1つのstepをlocalで閉じてから関連変更をまとめ、未検証の中間commitを共有branchへpushしない。
- `picocalc_emu_ext/`や外部uf2loader checkoutは入力workspaceであり、picocalc_emuのruntime依存にしない。
- 証拠は実行後に`firmware-validation/evidence/`へ凍結し、生成途中の`/tmp`や外部build directoryを正典にしない。

## 12. U6 Gate実測結果

2026-08-22、cleanなuf2loader source `5c44a4b64749062b0200507ceeff3ef2b475e288`と、cleanな
backend `d1360cbb13fd807661474b49a1b5516b12567d00`を使い、同じFAT32 snapshotと同じapp UF2を
3回実行した。3回とも次を満たした。

- report SHA `fa83ee1935728abab2543896c412491b1fa6e9ae512ec1e0f569d107199e0de9`
- UART SHA `1a1ff8de54237fae11773825e29d627dfd90a5473c5a6db4c924610e1089448b`
- framebuffer SHA `db449bc298f72dbd0a14ea9d482cf719622ac93782c17580a3ad6774f6f28c45`
- final flash SHA `853b9d711fe82364b88a59c756b43dfb3456eddc4328640d660c5912df434d0c`
- SD trace digest `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3`（970 events）
- unknown SD／flash command、flash mutation error、SD write、keyboard dropは0
- boot2／loader top 16 KiBは不変、watchdog resetは各run 1回、再attachはPASS

証拠の機械可読manifestは[`../../../firmware-validation/evidence/uf2loader-u6-20260822-01/u6-gate.json`](../../../firmware-validation/evidence/uf2loader-u6-20260822-01/u6-gate.json)
である。

U6 Gateは完了している。今後M-NESCO拡張を実装する場合は、このU6 evidenceをNESco互換の根拠へ流用せず、
M-NESCO preflightのfixture／marker／SHA契約を別途閉じる。
