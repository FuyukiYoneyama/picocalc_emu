# Validated Realtime Preview 実装計画

Status: **Current implementation plan / VRP-0〜VRP-4 formal evidence complete; VRP-NES-0 local preparation complete with owner-controlled external-artifact revalidation pending; VRP-5 onward remain**
Date: 2026-08-28 (updated 2026-08-29)
Proposal: [VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md](VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md)
Firmware input: [VALIDATED_REALTIME_PREVIEW_BIN_INPUT.md](VALIDATED_REALTIME_PREVIEW_BIN_INPUT.md)

## 1. 判定

提案の目的と安全境界は妥当であり、**以下の補正を含む本計画に従えば実装を開始できる**。

1. GUIへemulatorを再実装しない。validationで実際に使ったbyte-identicalな
   `picocalc-run`を子processとして起動し、frontendとはversioned preview IPCで接続する。
2. 提案のP0はreceiptを要求する一方、receipt生成をP1としている。本計画では依存関係を直し、
   **receipt/admissionをGUIより先に実装する**。
3. 現行target report schema 8にはtarget ID/revisionそのものは入らない。receiptはreportだけから
   targetを推測せず、registryのtarget ID/revision、target contract SHA-256、validation record SHA-256を
   結び直す。
4. 提案が固定するdevice 6項目は現行の標準targetには使用できるが、optional I2C profile等を
   暗黙に無視してはならない。初版は未知のsemantics-affecting optionをfail-closedで拒否する。
5. 既存promoted PicoTetris記録は実時間比14.636593%であり、仮想1秒にwall約6.83秒を要した。
   現行backendを再測定するまでは参考値だが、GUIを付けるだけで1倍になるとは見込まない。
   初回成果を「正直な計測付きpreview」、1倍到達を別のqualification gateとして扱う。
6. VRP-0の既存workloadは、曖昧な「active PicoTetris」ではなく、現在のpromoted target
   **`picotetris-opt1b`（revision 5）**と、性質の異なる再現可能な
   **`picoedit-r1`（revision 1）**に固定する。`picocalc-audio-r1`はVRP-4のaudio検証用fixtureとして扱う。
7. registryには現在NES-class targetが存在しない。NES-classはVRP-0の開始を塞ぐ暗黙の前提にせず、
   `VRP-NES-0`として別途target/fixtureを作成する。これは正式な`realtime-1x-qualified`昇格の
   前提だが、previewのreceipt・GUI・UART実装は既存2 targetで先に進められる。
8. preview IPC schema 1はVRP-0の最初の成果物として、具体的なwire fixtureとともに凍結する。
   magic、version、endian、field幅、message kind、payload上限、異常系を未定義のままproduction
   codeへ進まない。

9. VRP-0で固定したtargetのbackend pinと、preview APIを実装した現在のbackendは同一とは限らない。
   既存のvalidation record／target revisionを上書きせず、VRP-2のregistered-target gateへ入る前に、
   現行backendで再検証した新しいversioned target revision、validation record、receiptを作る。
   旧revisionの実機相関・batch証拠は歴史的な証拠として保持し、preview用の再検証結果と混同しない。

既存の権威あるFirmware backendの履歴、schema 8、既存targetのvalidation record／revision、machine API
schema 1は変更しない。VRP-2ではtarget registryのversioning規則に従った新revisionまたはpreview専用
targetを追加できるが、既存entryを上書きしてはならない。previewはhardware PASS/FAILを生成しない。

## 2. 確認した現状

| 項目 | 現状 | 実装への影響 |
|---|---|---|
| `MachineSession` | `picocalc-harness/src/session.rs`のcrate内共有型 | batch scenario、machine API、preview APIが同じsessionとstep境界を共有する |
| 既存TUI | 独自の簡易LCD/GPIO経路 | PicoCalc previewのdevice modelとして流用しない |
| wall-clock pacer | `picoem-common::Pacer`として実装済み | core semanticsを変えず再利用する |
| pacer metric | cycle、wall、emulation、spin、behind count | rolling ratioとlagはcold pathで導出・追加する |
| framebuffer | PicoCalc LCD modelからRGB565 snapshotを取得可能 | presentation cadenceでのみcopyする |
| keyboard | `MachineSession`のpressed/held/released入力が存在 | OS auto-repeatだけfrontendで抑止する |
| audio | run終了時captureに加え、VRP-4でbounded preview PCM tapを実装 | host monitorはpresentation専用。emulated sink／exactness digestは独立 |
| validation wrapper | BIN、backend commit、reportをfail-closed検査 | 実runner bytesとreceiptの固定を追加する |
| GUI/audio dependency | workspaceには専用GUI/audio stackなし | 最初にWSLg build/runとlicenseを小規模確認する |

## 3. 採用する構成

```text
picocalc.py preview (admission supervisor)
  |
  | verify report / target / validation / BIN / runner / device projection
  v
picocalc-preview (thin GUI, no emulator core)
  |
  | versioned local IPC; input, RGB565, PCM, status
  v
the exact validated picocalc-run --preview-api
  |
  v
MachineSession -> RP2040 + PicoCalc device models
```

### 3.1 process境界を採る理由

- GUI executableがemulatorを直接linkすると、validationで使った`picocalc-run`とbyte-identicalにできない。
- 子process方式なら、receiptが固定した実runner executableをそのまま実行できる。
- frontendのwindow/audio障害をauthoritative runnerやmachine APIへ混入させない。
- framebuffer/audio transportをdropしても、emulated CPU/PIO/DMA/device eventは子process内で進み続ける。

### 3.2 launch / reload

`picocalc.py preview`を長寿命supervisorとする。

```text
launch: admission -> GUI/backend start
F5:     admitted bytesからMachineSessionだけ再生成。frontend sticky stateは保持
Ctrl+R: GUI/backend停止 -> supervisorが同じadmissionを再実行 -> 成功時だけ再起動
```

reload失敗時は旧sessionも停止し、`VALIDATION LOST — RELOAD REFUSED`を表示して終了する。
frontendへ渡すlaunch descriptorは一時artifactとして原子的に作り、BIN/runnerの期待SHAを含める。
frontendはspawn直前にも両bytesを再hashする。初版の脅威modelは悪意あるlocal userへの耐タンパー性ではなく、
buildやfile置換による**偶発的・不整合な迂回をfail-closedに検出すること**である。

VRP-2でdescriptorを実際のrunner起動へ接続する際は、descriptorからrunnerのargv（または同等の
versioned launch-contract snapshot）を復元できなければならない。frontendがmutableなtarget registryを
再解釈して引数を組み立てるだけの設計は採用しない。descriptorのlaunch contractを拡張する場合は、
descriptor schemaの必須field、正規化規則、SHA、拒否条件を同じ変更単位で固定し、descriptorの再検証なしに
runnerをspawnしない。

### 3.3 preview IPC

既存machine API schema 1を拡張しない。`--preview-api`は相互排他的な別modeとし、stdin/stdout上の
length-prefixed framingを使う。

- 固定magic、protocol version、message kind、payload length
- JSON control/status message
- raw RGB565 frame message
- interleaved signed PCM message
- key down/up、reset、quit command
- PicoCalc UART0のTX（firmware -> console）とRX（console -> firmware）を方向付きmessageで運ぶ
- UART consoleはrunnerのstderr/stdoutやhost shellではなく、PicoCalc UART0 peripheralの仮想TX/RX wireを表示・操作する
- maximum payload length、unknown kind、truncated frameをfail-closedで拒否
- protocol stdoutに通常logを混ぜず、診断logはstderrへ出す

ここで列挙した項目は概念上の要件ではなく、**VRP-0で具体値を決定してschema 1 fixtureへ凍結する**。
fixtureには少なくともhello/status、RGB565 frame、key/reset/quit、UART TX/RX、PCM、unknown kind、
truncated frameの代表バイト列を含める。magic値、整数のendian、各fieldのbyte幅、message kindの
番号、payload最大値、version不一致とEOFの扱いをfixtureのREADMEへ明記し、fixtureのレビューが終わる
までpreview production codeを追加しない。

VRP-0で凍結した正典は[`docs/validated-realtime-preview/preview-ipc-schema-v1.json`](validated-realtime-preview/preview-ipc-schema-v1.json)
と[`docs/validated-realtime-preview/preview-ipc-fixture-v1.json`](validated-realtime-preview/preview-ipc-fixture-v1.json)である。
receiptの正典は[`receipt-schema-v1.json`](validated-realtime-preview/receipt-schema-v1.json)と、2つの
fixture（`picotetris-opt1b` rev.5／`picoedit-r1` rev.1）である。fixtureは大きなBINを同梱しない
schema-only例であり、`<fresh-dir>`等のplaceholder pathを実際のlaunch入力として扱ってはならない。

IPCはlocal process間だけを対象とし、network APIやremote controlは初版へ入れない。

### 3.4 初版host範囲

最初のqualified hostは、現在の主要開発環境である **Ubuntu 24.04 on WSL2/WSLg x86_64** とする。
VRP-3のGUIはRust GUI dependencyを追加せず、Python標準ライブラリのTkで実装する。これにより
receiptが指定するRust runnerのbyte identityと、frontendのwindow障害を分離する。audio候補の
`cpal`はVRP-4までproduction pathへ固定しない。他OSは「動く可能性」と「qualified」を区別する。

### 3.5 PicoCalc本体スキン

提示された`IMG_20260828_0002a.jpg`のような本体写真は、emulator modelやconformance artifactではなく、
previewのpresentation assetとして扱う。実装時には共有workspaceの`log/`を実行時依存にせず、次の条件を満たす
repository assetへ取り込む。

- `assets/preview/picocalc-device-skin.png`（または同等の明示的なasset path）として固定する
- EXIF、撮影日時、機種情報などの不要なmetadataを除去し、asset SHA-256と由来・利用許諾を記録する
- VRP-0で画像の表示向き、LCD開口部4点のnormalized座標、必要な透視変換を校正する
- backendの320x320 RGB565 framebufferを、校正済みのLCD開口部へ合成する。写真のキーボードや本体を
  framebufferで描き直さない
- skinのscale、補間、window resizeはpresentationだけに作用し、emulated framebuffer、cycle、UART、audio、
  report hashを変更しない
- assetが無い、SHAが違う、開口部校正が無い場合は、`skin unavailable`をUIへ明示する。暗黙に別画像へ
  切り替えない。P0ではskinをqualified previewの既定assetとして同梱できない限り、skin表示を合格扱いにしない
- plain LCD presentationを診断用fallbackとして許可しても、それを「本体スキン表示」とは呼ばない

写真assetの公開許諾が確認できない間は、assetを公開repositoryへ入れず、local-only skin fixtureとして扱う。
この場合もpreview本体のruntime依存にはしない。

## 4. validation receipt schema 1

receiptは`picocalc.py test --mode firmware`が全契約を合格した後だけ原子的に生成する。
永続reportが必要なため、`--receipt-out`は既存の`--json <report-path>`との併用を必須とする。

最低field:

```text
schema_version
target.id / target.revision / target_contract_sha256
target_validation_record.path / sha256
firmware.path / sha256
backend.accepted_commit
backend.executable.path / sha256
report.path / sha256 / schema_version
device.board / lcd_variant / psram / keyboard / sd.attached / sd.format
provenance references
```

生成条件:

- wrapper、runner、reportの判定がすべてPASS
- runner exitと`verdict.status`が一致
- runner executableとBINを実行前・実行後にhashし、途中変更がない
- backend checkout commitとreportの`backend_build.commit`がaccepted commitに一致
- backend tracked worktreeがvalidation時にclean
- target contractとvalidation recordがregistryのSHAに一致
- outputはtemporary file + atomic replace
- 失敗・cannot judge時は古いreceiptを上書きせず、新receiptを生成しない

preview admissionはreceiptのcopy値を信用せず、参照先を毎回再読して同じ関係を検査する。

### 4.1 device projectionの初版境界

提案の6項目をschema 1のprojectionとする。ただし現在のtargetに次があれば初版previewは拒否する。

- `runner.i2c`が存在する
- 将来schemaへ追加された、preview semanticsを変える未知のrunner field
- 初期media内容を別artifactで要求するが、そのSHAをreceiptが固定できないtarget
- preview backendが対応しないboot/image mutation profile

`cycles`、fixed `keys`、scenario、expected stop reason、audio oracleはvalidation専用なのでprojectionへ入れない。
optional I2C等へ対応するときはprojection schema revisionを上げ、fixture SHAも明示的に追加する。

### 4.2 VRP-2 current-backend revalidation

VRP-0の固定targetは、作成時点のaccepted backendを保持する。2026-08-28時点では
`picotetris-opt1b` revision 5と`picoedit-r1` revision 1が`e985a9d7…`を固定している一方、
preview APIを含む開発backendは`e78d11e…`である。したがって、既存receiptをそのままpreview APIの
実行証拠として使ってはならない。

VRP-2のregistered-target gateは次の手順で閉じる。

1. 旧target revision、validation record、receipt、実機証拠を変更せず保存する。
2. 現行backendのclean checkoutとrunner SHAを固定し、同じsource/BIN/device projectionで2 workloadを再実行する。
3. report、runner、BIN、contract、backend commitを含む新しいvalidation recordとtarget revision（または
   明示的なpreview専用target）を作る。挙動差がある場合は旧revisionへ遡及修正せず、新revisionの差分として記録する。
4. 新revisionからreceiptを生成し、descriptor admissionと後述のheadless launch consumerで再検証する。

この工程が完了するまで、synthetic fixtureの三者比較をregistered targetの合格結果へ昇格しない。

## 5. 作業パッケージ

### VRP-0: contract・host spike・baseline preflight（4〜8時間）

変更前に次を固定する。

1. receipt schema 1と、VRP-0で具体値を凍結したpreview IPC schema 1のfixture（UART0のTX/RX双方を含む）。正典は[`docs/validated-realtime-preview/`](validated-realtime-preview/)
2. supported hostのWSLg GUI/audio capability。GUI/audio Rust crateはまだproduction dependencyへ追加せず、候補crateのbuild/license確認は実際に依存を追加するVRP-2/VRP-3のlockfile変更前に行う
3. `picotetris-opt1b`（revision 5）と`picoedit-r1`（revision 1）のtarget/validation record、provenance、
   それぞれのbaseline手順
4. 現行accepted backendでのGUIなし速度baseline
5. performance測定中は並列runを行わない条件

NES-class workloadはこのgateでは要求しない。正式な1倍qualified判定に必要なfixtureは、下記の
`VRP-NES-0`で別途準備する。実cartridge ROMや再配布条件不明のdataは使わず、適切なhomebrewまたは
synthetic ROMを使い、そのsource/license/hashを固定する。

**完了gate:** WSLg capability probeがwindowとsilent playback deviceの開閉を確認し、IPC schema 1
fixtureの具体値と、上記2 workloadのprovenance・baseline手順が記録される。VRP-0ではproduction
codeとRust GUI/audio dependencyを変更しない。VRP-1でも依存追加は行わず、候補crateのversion/build/license選定は
VRP-2/VRP-3で最初にlockfileを変更する前に別記録する。実測結果は[`VRP0_HOST_SPIKE_20260828.md`](validated-realtime-preview/VRP0_HOST_SPIKE_20260828.md)、
基準値は[`VRP0_BASELINE_20260828.json`](validated-realtime-preview/VRP0_BASELINE_20260828.json)を参照する。

### VRP-NES-0: NES-class target/fixture preparation（10〜20時間、正式qualificationの前提）

registryには現在NES-class targetがないため、これを既存targetの別名として扱わない。再配布可能な
homebrewまたはsynthetic ROMを選定し、source、license、生成手順、BIN SHA、validation record、
target contract、registry entryを独立した証拠として固定する。real cartridge ROMや再配布条件が不明な
外部data、個人所有物をfixtureへ含めない。

**実施結果（2026-08-29）:** repository-ownedのsynthetic NROM-256（trainer付き、mapper 0、
41,488 bytes）と標準ライブラリだけの決定的generatorを追加した。NESco診断BINをclean backendで
3回実行し、SD FAT32入力、flash staging、XIP、core 1、DMA、UART、framebuffer、report、SD trace、
flash exportがすべてbyte-identicalになることを確認した。証拠は
[`VRP_NES0_NES_CLASS_FIXTURE_20260829.md`](validated-realtime-preview/VRP_NES0_NES_CLASS_FIXTURE_20260829.md)
と[`vrp-nes0-synthetic-nrom-20260829-01`](../firmware-validation/evidence/vrp-nes0-synthetic-nrom-20260829-01/)
に固定し、target entryとvalidation attestationも作成した。

ただし使用したNESco診断commit
`7f3fa05971930e03653694117cbf6a435ec1dd4e`は、現在の公開remoteに到達可能なrefがない。
そのため`vrp-nes0-synthetic-nrom`は`pending-revalidation`に留め、source commitがclean cloneから
取得可能になるまで`active`へ昇格しない。これはfixtureまたはbackendの不合格ではなく、外部source
provenanceが未提供であるためである。`Picocalc_NESco`は独立プロジェクトであり、`picocalc_emu`は
その計画・改造・ブランチ公開・pushを行わない。正式な`realtime-1x-qualified` capabilityの前提は
未完了のままとする。

#### 外部NEScoの責任境界（2026-08-29時点の状態）

この記録で扱う診断変更は、NEScoのローカルcheckoutにある
`codex/mnesco-extension`（commit `7f3fa05971930e03653694117cbf6a435ec1dd4e`）だけである。
そのcheckoutはcleanで、GitHubの`Picocalc_NESco` remoteにはこのbranchは存在しない。確認できる
remote refは`main`（`acf605358b0808052b87bc3e64aabf413d2d22b7`）と、今回の作業で作成していない
既存の`perf/bg-tile-share-log`（`c2430c0bcf536ccf7aec18039bb6dfb81eb9ad13`）である。
このため、NEScoを公開remoteで`main`へ統合したり、診断branchを新たに公開したりすることは
`picocalc_emu`の作業範囲に含めない。

`picocalc_emu`が保持するのは、repository-owned synthetic ROM、提供されたBIN/UF2、SHA-256、
runner report、trace、validation recordなどの**入力識別情報と検証記録**だけである。SHA-256は
同一バイト列の確認には使えるが、NEScoのソース再構成、ライセンス判断、動作の一般的保証を意味しない。
将来このtargetを再検証する場合は、NESco側の所有者が独立に公開refまたは再現可能なartifactを
提供し、その入力をエミュレーターが検査する。提供がない限り、targetは`pending-revalidation`の
ままとし、エミュレーター側でNEScoソースを取り込んだり改造したりしない。

この作業はpreviewのreceipt・IPC・GUI実装を開始するための必須条件ではないが、正式な
`realtime-1x-qualified` capabilityを宣言する前には必須である。targetを作成できない場合は、
previewを`validated-preview-admission`または`realtime candidate`として提供できるが、1倍qualifiedへ
昇格してはならない。

### VRP-1: receipt生成と共通admission（12〜20時間）

`picocalc_emu`側へ次を追加する。

使用例は既存の`--json`を維持し、新しいreceiptだけを`--receipt-out`で指定する。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target <target-id> --firmware /absolute/path/to/app.bin \
  --json /absolute/path/to/validation-report.json \
  --receipt-out /absolute/path/to/validation-receipt.json \
  --backend-dir /absolute/path/to/picoem-picocalc
```

- 既存の`--json <report-path>`と併用する`--receipt-out <receipt-path>`付きauthoritative validation
- receipt JSON schemaとvalidator
- `picocalc.py preview --firmware ... --receipt ... --backend-dir ...`
- launch/reloadで共有する単一admission関数
- target contract SHA、validation record SHA、runner/BIN/report SHAの再検証
- preview-ineligible targetの明示的な拒否理由

mutation testは少なくともreport欠落/改変、schema違い、verdict fail、target revision違い、
target contract違い、validation record違い、BIN違い、backend commit違い、runner bytes違い、
device projection違い、optional I2C targetを含む。

**完了gate:** 手編集したreceiptだけではいずれの不一致も通らず、正しいreceiptだけがimmutableな
launch descriptorを生成する。まだGUIは起動しない。

**実装結果（2026-08-28）:** `tools/picocalc.py test --mode firmware`へ
`--receipt-out`を追加し、PASS済みreportからschema 1 receiptを原子的に生成する。
`picocalc.py preview`はreceipt、registry、validation record、BIN、report、backend HEAD／clean状態、
runner bytes、device projectionを再検証し、GUIを起動せず`status=admitted`のlaunch descriptorだけを
原子的に出力する。schema-only fixture、改変SHA、未知のsemantics-affecting runner fieldは拒否する。
旧accepted backendのようにheartbeat optionを持たないrunnerは、既定のheartbeat引数を自動的に省略して
互換実行し、明示的なheartbeat要求は`cannot judge`とする。実際の`picotetris-opt1b` clean build／run／
admission結果とSHAは[`validated-realtime-preview/VRP1_RECEIPT_ADMISSION_20260828.md`](validated-realtime-preview/VRP1_RECEIPT_ADMISSION_20260828.md)に固定した。
VRP-1ではGUI、preview IPC本体、capability昇格は行わない。

### VRP-2: shared session coreとpreview backend API（24〜40時間）

`picoem-picocalc`側で、現在`main.rs`にあるMachineSession、board handle、boot/session factoryを
共通moduleへ分離する。batch scenarioとmachine APIを先に同じmoduleへ戻し、report bytes、cycle、
UART、framebuffer、device observationの既存回帰が変わらないことを確認してから`--preview-api`を足す。

VRP-2は、初期API実装とregistered-target受入を混同しないよう、当初は次の4つの作業へ分けた。
以下の完了記録が示すとおり、VRP-2-a〜eはすべて完了している。

#### VRP-2-a: current-backend versioned target

上記§4.2の手順で、現行backendを固定した新revision／validation record／receiptを作る。旧revisionの
report SHAや実機相関証拠を書き換えず、previewで実行するtargetのsource、BIN、runner、device projection、
backend commitを一組のprovenanceとして保存する。

**完了記録（2026-08-28）:** `picotetris-opt1b-vrp2` revision 6 と
`picoedit-r1-vrp2` revision 2 を追加した。両方をbackend
`d3767c901921811b5744925832956661fd344457`／runner SHA
`f436d7dc4965b433a65ee7355014b1d93148dbb433e251927cbd9064e019a6d7`で
clean revalidationし、UART・RGB565 framebuffer・scenario timelineは旧revisionと
一致、cycle差はそれぞれ -1／-4 と記録した。validation record、target contract、
receipt生成、`preview` admissionまでローカルでPASSした。旧revisionの実機証拠は変更して
いない。詳細は[`validated-realtime-preview/VRP2A_CURRENT_BACKEND_20260828.md`](validated-realtime-preview/VRP2A_CURRENT_BACKEND_20260828.md)を参照する。

#### VRP-2-b: admitted descriptor consumer

`picocalc.py preview`が出力したdescriptorを入力として、GUIなしでrunnerをspawnするheadless consumer／
smoke gateを追加する。consumerはdescriptorのlaunch contract、BIN／runner SHA、backend HEAD／clean状態を
再検証し、PCRP hello→status→quitまでを実行する。手書きargvやmutable registryからの暗黙補完で起動した
場合は合格にしない。

**完了記録（2026-08-29）:** `preview-headless`を追加した。admitted descriptorへ埋め込んだ
schema-1 launch contract（argv、cwd、bootrom、contract SHA）を再検証し、runnerの全PCRP出力を
schema-1のpayload／sequence／canonical JSON規則で検査する。hello→status後にquitを送信し、goodbyeと
exit 0を要求する。descriptor mutation、timeout、EOF、unknown/direction-invalid kind、sequence不連続、
JSON／binary payload不正はfail-closedで拒否する。実際のVRP-2-a 2 target descriptorとfake-runner
unit testでローカルPASSした。詳細は[`validated-realtime-preview/VRP2B_DESCRIPTOR_CONSUMER_20260829.md`](validated-realtime-preview/VRP2B_DESCRIPTOR_CONSUMER_20260829.md)。

#### VRP-2-c: machine API schema-1 compatibility

既存machine APIの`run`、`step`、`run_until`、`input`、`observe`、`subscribe`、`snapshot`を代表する
golden JSONL transcriptを固定し、preview実装前後で既存domainの応答が不変であることをローカルで確認する。
新しい`observe domains=["preview"]`は追加domainとして扱い、既存domainの出力変更を許可しない。

**完了記録（2026-08-29）:** `picoem-picocalc`の
`crates/picocalc-harness/tests/fixtures/machine-api-schema1-golden.jsonl`へ、既存schema 1の
`observe`／`step`／`subscribe`／`run`／`input`／`run_until`／`snapshot`を含む8交換のgolden transcriptを固定した。
`machine_api_schema1_golden.rs`は実runnerへ同じJSON Linesを順に送り、応答JSONをbyteではなく構造化値として
完全一致比較し、snapshot生成も確認する。`cargo test -p picocalc-harness --test machine_api_schema1_golden --locked`
がローカルで合格し、preview専用`observe` domainを既存transcriptへ混入させない境界もテストコメントで固定した。

#### VRP-2-d: UART RX positive/overflow evidence

RXを有効にした小さなrepository-owned firmware fixtureを追加し、previewからのaccepted RX、guest側の
echo／応答、FIFO full／overrun、方向付きcounterを確認する。RX無効時の拒否だけではVRP-2のUART gateを
閉じない。

**完了記録（2026-08-29）:** `preview_api_e2e`へrepository-ownedの決定的Thumb raw-flash fixtureを追加し、
previewのUART RXへ16バイトを連続投入してguest側のecho順序とaccepted counterを確認した。17バイト目は
bounded FIFOのoverrunとして方向付きerror／counterへ入り、RX disabled時の拒否経路も既存テストで保持する。
テストはfixtureを一時生成して終了時に削除し、`cargo test -p picocalc-harness --test preview_api_e2e --locked`
と`cargo clippy -p picocalc-harness --tests --locked -- -D warnings`をローカルで合格させた。これはUART
wire／queue semanticsの証拠であり、実機音声やhardware qualificationを主張するものではない。

#### VRP-2-e: registered-target complete digest gate

`tools/picocalc.py preview-digest-gate`を追加し、VRP-2-aのadmitted
descriptorを入力として、登録targetの同一BIN・同一scenarioをbatch、machine API、preview APIの
三経路へ渡し、descriptorが参照するregistered reportを含む**四者**のobservation projection／
canonical digest、scenario timeline、終端virtual cycle、target report checksを比較する。
projectionはRust backendのpreview observation schema 1と同じく、schema-8の`audio_sink`にある
DMA-to-PWM観測面（write/error、PCM／edge／due-cycle、block/gap、service-latency）を完全に含み、
RGB565 framebuffer、UART、unsupported-MMIOも含む。`--audio-analysis`のhost側loudness/rail統計は
別artifactであり、VRP-2のexactness projectionへ推測混入しない。観測値が欠ける古いreportへaudioを
推測補完せず、完全digest gateを拒否する。音声分析値を受入入力にする場合はVRP-4で別のversioned
monitor contractを定義する。

実装はfake registered-targetでdescriptor admissionからevidence原子書込みまでローカルテスト済みであり、
2026-08-29に実targetでも受入した。clean backend `c1c20d7d86a3006569375bc333cf72494e95eb46`と
runner SHA `f1a79384d0f90fafea1fbe9db249dc9c54327ef12bed0445c1e4bef23e3a050c`を固定し、
実BIN、`--audio-analysis`付きfresh schema-8 report、versioned validation／receipt／descriptorを
新revisionへ接続した。`picotetris-opt1b-vrp2f` revision 8と`picoedit-r1-vrp2f` revision 4の
両方で、batch／machine API／preview API／registered reportの四者projection digest、timeline、
終端virtual cycle、target report checksが一致し、gateはexit 0となった。各targetの証拠は
[`firmware-validation/records/vrp2-f-picotetris-20260829-01/`](../firmware-validation/records/vrp2-f-picotetris-20260829-01/)
と[`firmware-validation/records/vrp2-f-picoedit-20260829-01/`](../firmware-validation/records/vrp2-f-picoedit-20260829-01/)
に保存する。旧revision・旧validation・旧実機証拠は変更していない。

```sh
python3 tools/picocalc.py preview-digest-gate \
  --descriptor /absolute/path/to/admitted-descriptor.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --evidence-out /absolute/path/to/vrp2-complete-digest.json
```

詳細な受入境界とnon-claimは[`validated-realtime-preview/VRP2E_REGISTERED_DIGEST_GATE_20260829.md`](validated-realtime-preview/VRP2E_REGISTERED_DIGEST_GATE_20260829.md)に固定する。

VRP-2-c／dの互換性・UART RX証拠と、VRP-2-eのregistered-target完全digest受入は完了した。
この完了記録は、VRP-2-aで作成したversioned registered targetのlaunch contractに対する
同一virtual cycleのprojection digest、receipt／admission接続までを含む。これはpreviewをsupported、
またはhardware qualification済みと扱うことを意味しない。

preview loopは既存`Pacer`を用い、clock変更時も`update_sys_clk_hz()`を呼ぶ。追加metricは
session/rolling `virtual_time / wall_time`、lag、behind count、presentation/audio queue状態で、
emulation hot pathの決定性へ入れない。

F5は起動時に読んだadmitted BINとinitial device fixtureから新MachineSessionを作る。
disk上のBINを再読しない。watchdog resetとは別の、preview operatorによるfull machine resetである。

#### PicoCalc UART0 console

現在のUART modelはfirmware TXの観測に加え、VRP-2-dで外部RX stimulusと方向付きcounterを提供する。
UARTウィンドウを「ログ表示」として実装して済ませず、次の境界を維持する。

- UART0 TX byteをvirtual cycle付きでpreviewへ逐次送る
- previewからUART0 RXへ投入するbounded queueと、UART FIFO full/overrunの既存semanticsを使用する
- RX入力の投入境界をIPC contractへ固定する（host arrival時刻を直接emulated cycleへ混ぜない）
- text入力とraw byte入力を区別し、改行・NUL・非UTF-8を失わない
- TX/RX、virtual cycle、drop/overrunを方向付きでstatusへ示す
- UARTのhost側入力はemulated UART0 RX FIFOへ投入し、PicoCalc keyboard入力やprocess stdinとは混同しない
- UART入力を使わないworkloadでは、TX/RX tapの有効/無効が既存report、cycle、framebuffer、audio digestへ
  影響しないことを回帰する

**完了gate:** 同じBINを同じvirtual cycleまで動かしたbatch/machine API/preview APIのUART、
framebuffer、unsupported MMIO、audio digestが一致し、machine API schema 1の出力が不変。

このgateは、board-backed synthetic fixtureのsmokeだけでは完了としない。VRP-2完了には、VRP-2-aの
versioned target／receipt、VRP-2-bのdescriptor consumer、VRP-2-cのschema-1 transcript、VRP-2-dの
UART RX正常系・overrun証拠、VRP-2-eのregistered-target完全digestをすべて同じbackend revisionで通す
ことを追加で要求する。

**実装進捗（2026-08-29）:** backend側に`--preview-api`の初期実装を追加し、`MachineSession`を
`src/session.rs`へ分離した。固定PCRP
schema 1のframe reader/writer、sequence・direction・payloadのfail-closed検証、UART0のTX/RX
wire、key/reset/quit入力、RGB565初期・差分frame、pacer status、bounded input queueを実装し、
未知messageのexit 2と正常quitをrunner process E2Eで確認した。さらに同じsession境界から
UART、framebuffer、unsupported-MMIO、audio-sinkを含むversioned observation projectionと
canonical digestをpreview status／machine APIの`preview`観測domainへ追加した。既存batch／
machine APIのreport生成経路は変更していない。現在はpreviewとbatch/machineを同じvirtual
cycleで走らせるbackend／machine／previewの三者比較を、board-backed synthetic UART fixtureの
report-compatible observation digest smoke gate（初期RGB565 LCD frameを含む）として追加した。
これはregistered target admissionへ接続した完全なdigest gateとは別の、初期実装時点のsmokeである。
PCMは`audio.state=not_streamed`として明示し、host側のbounded monitorはVRP-4で実装済みである。
backend側の利用・制約は
[`picoem-picocalc/docs/VALIDATED_REALTIME_PREVIEW_BACKEND.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/VALIDATED_REALTIME_PREVIEW_BACKEND.md)
を参照する。

VRP-2-c／dの互換性・UART RX証拠、VRP-2-eのgate実装・fake-target検査、実targetのcomplete digest
受入は完了した。VRP-2-eの実target記録は上記のversioned revisionと証拠ディレクトリを参照する。
ただしこれはGUI、host audio qualification、実機hardware correlation、または`realtime-1x-qualified`
を意味しない。次はVRP-5 qualification、VRP-6 capability/docsであり、VRP-7 exact optimizationは
VRP-5で1倍未達を確認した場合だけ開始する。

### VRP-3: GUI・本体スキン・LCD・keyboard・UART・reset/reload（24〜36時間）

新しい`picocalc-preview`はemulator coreをlinkせず、preview IPC clientに限定する。

- 320x320 RGB565 window、integer scale優先
- `picocalc-device-skin`を既定で読み込み、校正済みLCD開口部へframebufferをはめ込む
- 本体スキンとは別のUART0 console windowをpreview起動時に自動で開く
- UART consoleはTX/RXを明確に分け、text/raw bytes、virtual cycle、overrun/dropを表示する
- UART console windowのcloseは「console closed」と明示し、firmware UARTを無音・未接続へ黙って変更しない
- key mappingとdown/up。OS auto-repeat key-downを重複投入しない
- F5 reset、Ctrl+R reload request、F12 screenshot、Esc quit
- validation identity、target/measured speed、timing、coverage、audio、hardware verdict banner
- repaint coalescing/drop count。表示側の古いframe描画だけはcoalesceできるが、backendが発行した
  device event、status、UART、error、cycle、observationはskip／再解釈しない
- unsupported/truncated MMIOのsticky UX-invalid state
- sticky stateはF5で保持、admission済みreloadだけでclear

screenshotは表示用PNGとし、conformance hashへ使わない。スキンを含むscreenshotは本体写真の
presentationを含むため、raw framebufferのgolden imageとは別物である。

**完了gate:** 本体スキンの校正済み開口部へframebufferが合成され、key down/hold/up、auto-repeat抑止、
UART consoleの自動起動とTX/RX双方の表示・入力、reset、成功reload、拒否reload、sticky coverageを自動testし、
人間のWSLg smokeで本体windowとUART windowを確認する。

**実装結果（2026-08-29）:** `tools/picocalc_preview.py`を追加し、`preview-gui`サブコマンドから
admitted descriptorを再検証して、descriptorの完全なlaunch contractに記録されたrunnerだけをTkの
子processとして起動する。Rust GUI/audio依存やemulator coreの再実装は行っていない。提示された
PicoCalc写真はEXIFを除去した`assets/preview/picocalc-device-skin.png`（607x1026、SHA-256をREADMEへ固定）
としてpresentation asset化し、校正済み開口部へ320x320 RGB565を表示する。アセットのSHA／サイズ異常は
`skin unavailable`として明示し、`--skin none`では整数倍率のLCDへfallbackする。

UART0は本体とは別のconsole windowを起動時に自動作成し、TXのvirtual cycle付きhex/text表示、UTF-8／
raw-hex RX入力、accepted／overrunのbackend counterを表示する。TkのOS auto-repeat `KeyPress`は重複
`down`へ変換せず、初回`down`・UI timerの`held`・`up`へ分離する。F5 resetはsticky UX-invalidを保持し、
Ctrl+Rはadmissionを再実行して成功時だけsticky stateをclear、変更／欠落時は
`VALIDATION LOST — RELOAD REFUSED`を表示する。F12はpresentation screenshot、Escはpreview quitへ予約する。
backendのerror、coverage停止、unsupported/truncated attribution、IPC読取失敗はsticky UX-invalidとして
表示し、GUIは終了コード2を返す。`audio=not_streamed`はauthoritative digestのlegacy fieldとして維持し、
host PCM再生は別の`audio_monitor` statusでVRP-4が扱う。

headlessな`tests/test_preview_gui.py`でPCRP input fixture、方向／payload fail-closed、RGB565変換、
key down/held/up、OS repeat抑止、UART entry focus、reset／成功・拒否reload、sticky stateを検査した。
実Tk／backendを必要とする画面合成・UART console自動起動・実runner TX/RXの確認は、別のWSLg local
smokeとして行う。WSLg実行では登録済み`picoedit-r1-vrp2f`の
descriptorを使い、本体window・自動UART0 window・初期frame・clean child shutdownを確認した。詳細と
実行境界は[`validated-realtime-preview/VRP3_GUI_20260829.md`](validated-realtime-preview/VRP3_GUI_20260829.md)
に固定する。これはGUI機能の完了であり、host audio playbackの正式gate、hardware verdict、
`realtime-1x-qualified`昇格を意味しない。

### VRP-4: bounded host audio monitor（16〜28時間）

既存のrun全体`Vec<i16>` captureとは別に、preview専用のbounded PCM tapとhost presentationを実装した。
これは音声の聴感・実機speaker品質を判定するoracleではなく、emulated PWM/DMA/audio sinkを止めずに
PCMを観測するための補助経路である。

- backend tapは最大8 block、各blockは最大128 source frame。tap満杯時はhost向けblockだけをdropし、
  authoritative sink／cycle／report digestには影響させない
- runner出力は最大256 framed messageの非同期bounded writer、frontend ingressは512 eventのbounded queue。
  audio／frame／statusだけをlossyとし、UART／error／hello／goodbye等はfail-closedで保持する
- host queueは`--audio-queue-blocks`で上限を指定し、player停止・queue満杯・IPC／ingress dropを個別counterへ記録する
- source blockは128 frame上限、source rate/channelsを保持する。frontendは22,050／48,000 Hz等を
  bounded stateful linear resamplerで`--audio-host-rate`へ変換し、resampled blockは4096 frameを上限とする
- `--audio off`はhost再生だけを無効化し、`audio.state=not_streamed`を含むauthoritative observationを変えない
- playerなしは`timing-only`、player／queue／payload／transport失敗は`degraded`として表示する。gain、mute、
  smoothing、EQ、compressor、enhancementをemulated pathへ入れない
- F5／Ctrl+RはPCM queueとresamplerを破棄して`stream_epoch`を進める。drop／underrun等の診断counterは
  GUI process内で累積し、epochでrun境界を区別する

実装詳細・status定義・局所的な受入境界は
[`validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md`](validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md)に固定した。

**実装結果（2026-08-29、local）:** backend／frontendのunit・E2E、可変rate／block、bounded resampling、
player終了、host／ingress／IPC drop、reset epoch、authoritative tap isolationを確認した。非同期output
writerのforced-drop testも追加し、emulation threadが遅いhost sinkを待たないことを検査した。

**完了gate（2026-08-29、local）:** `picotetris-opt1b-vrp4` revision 9を同じ
registered target／clean backend／BINで`off`／`on`／`forced-drop`の3条件実行し、同じvirtual boundaryの
audio event digest、cycle、UART、framebuffer、message sequenceを確認した。`on`ではPCM 1,000 frameを
受信・送信しhost drop 0、`forced-drop`では決定的に8 blockをdropして`degraded`を示しつつ、
authoritative projectionは不変だった。証拠は`firmware-validation/records/vrp4-picotetris-20260829-01/`
に固定した。VRP-4 formal evidenceは完了したが、これは`realtime-1x-qualified`やhardware-audio capabilityへの
昇格を意味しない。

### VRP-5: baseline・threshold決定・qualification（10〜18時間 + 実測時間）

まずthresholdを決めずに測る。初期のpreview candidate測定は`picotetris-opt1b`と`picoedit-r1`を
それぞれ単独実行する。正式な1倍qualification測定は、`VRP-NES-0`完了後に
`picotetris-opt1b`とNES-class targetをそれぞれ単独実行する。いずれも次を保存する。

- host/OS/CPU、backend/BIN/receipt SHA
- session ratioとrolling ratio
- lag/backlog、behind count
- presentation drop
- audio underrun/overrun/drop
- unsupported/truncated MMIO
- CPU使用率と最大RSS（補助値）

screeningは各workload 10 wall分以上でよいが、1倍qualificationは各workload **10 virtual分以上**を
要求する。NES-classが未整備の場合、existing workloadの測定を完了しても正式な1倍qualificationは
未完了とする。1倍未達なら`REALTIME NOT MET`を正式結果として記録し、機能preview、realtime candidate、
realtime-qualifiedを混同しない。

baseline reviewでrealtime許容幅とlag上限を別decision recordへ固定し、その同じ条件でqualificationを
再実行する。測定値を見てから都合よく各runの閾値を変更しない。

**完了gate:** preview candidateについては`picotetris-opt1b`と`picoedit-r1`の2 workload recordがあり、
`UNCALIBRATED`または`REALTIME NOT MET`の根拠が機械可読に残る。正式な
`REALTIME OK`／`realtime-1x-qualified`には、これに加えて`VRP-NES-0`のNES-class recordが必要である。

### VRP-6: versioning・capability・利用文書（6〜10時間）

- `USER_GUIDE`にvalidation→receipt→previewの最短手順
- `DEVELOPER_GUIDE`にprocess/IPC/admission拡張規則
- capabilityは`validated-preview-admission`と`realtime-1x-qualified`を分離
- 1倍未達なら後者をsupportedへしない
- supported host、known limitation、audio fidelity、hardware verdictなしを明記
- receipt/IPC schemaをversioned contractとして固定

release tagはこの計画だけでは作らない。commit/push/tagは所有者の個別指示に従う。

### VRP-7: 条件付きexact optimization（別見積り、24〜80時間以上）

VRP-5でcore/device pathが1倍未達の場合だけ開始する。

1. profilerでhost presentation、audio transport、CPU、PIO、DMA、deviceを分離
2. presentation/audio transport負荷を先に除去
3. exactness不変の候補だけfeature-gated・独立commitでA/B
4. cycle、UART、framebuffer、behavior/event digestを既存gateで照合
5. 小改善はmicro-opt bankとして総合評価

CPU cycle、IRQ、PIO、DMA、device event、virtual audio eventを飛ばして1倍を偽装しない。
VRP-7を実施しても1倍に届かなければ、previewは`REALTIME NOT MET`のまま提供できるが、
timing/audio UX判定には使わない。

## 6. 実施順序と進捗表

| 順序 | package | 状態 |
|---:|---|---|
| 1 | VRP-0 contract/host spike/baseline preflight（`picotetris-opt1b` + `picoedit-r1`） | **完了 2026-08-28**（Rust GUI/audio dependencyは未追加） |
| 2 | VRP-1 receipt/admission | **完了 2026-08-28** |
| 3 | VRP-2 shared session/preview API | **完了 2026-08-29。VRP-2-a〜d、VRP-2-eのgate実装・fake-target検査、clean backend・実BIN・fresh complete audio reportによるregistered-target四者digest受入を完了。受入targetは`picotetris-opt1b-vrp2f` r8／`picoedit-r1-vrp2f` r4** |
| 4 | VRP-3 GUI/skin/LCD/keyboard/UART/reset/reload | **完了 2026-08-29。Tk薄型frontend、PicoCalc skin、UART0 console、入力／reset／reload／sticky gateをローカル受入** |
| 5 | VRP-4 bounded host audio monitor | **完了 2026-08-29（local unit／E2E、registered-target off/on/forced-drop formal evidence）** |
| 6 | VRP-NES-0 NES-class target/fixture（VRP-5正式qualification前に完了） | **fixture・local run完了。NEScoは独立プロジェクトで診断commitはローカルのみ。targetは`pending-revalidation`（所有者提供のref/artifact待ち）** |
| 7 | VRP-5 baseline/threshold/qualification | 未着手 |
| 8 | VRP-6 capability/docs/versioning | 未着手 |
| 9 | VRP-7 exact optimization | 条件付き。VRP-5判断前は着手しない |

VRP-0〜VRP-6のpreview実装中心工数は、今回追加したregistered-target closureを含めて
**128〜220時間 + 実測時間**である（本体スキン校正、UART RX/TX、bounded host audio monitorを含む）。VRP-2の初期API、
versioned target、descriptor consumer、machine API transcript、UART RX正常系、registered-target digest
closure、VRP-3 GUI/input、VRP-4の実装・local test・formal evidenceは完了している。今後の工数はqualificationで見積もる。
正式な1倍qualificationまで行う場合は、これにVRP-NES-0の**10〜20時間**とその測定時間を加える。
VRP-7は結果依存で別枠とする。
GUIだけを先に作るとadmissionとbackend identityを後付けすることになるため、順序を入れ替えない。

## 7. commitと検証の単位

推奨commit単位:

1. contract/fixture/docsのみ
2. receipt schema/generator/negative tests
3. admission supervisor/negative tests
4. MachineSession機械的分離（挙動差ゼロ）
5. preview IPC/backend loop
6. current-backend versioned target／validation record／receipt
7. admitted descriptor consumer/headless launch smoke
8. machine API schema-1 compatibility transcript／UART RX fixture
9. frontend window/framebuffer
10. keyboard/reset/reload/sticky state
11. audio transport
12. baseline/decision record
13. capability/user/developer docs

各単位でローカルtestを完了してから次へ進む。通常の試行錯誤にGitHub Actionsを使わず、
workflow追加・trigger/job変更・CI実行増加は所有者の事前許可なしに行わない。pushをCIの代わりにしない。

## 8. 中止条件

次の場合は無理に先へ進まず、原因と再開条件を記録する。

- GUI/audio dependencyがqualified hostで再現可能にbuild/runできない
- same executable identityを維持できない構成変更が必要になった
- batch/machine API/preview API間で同じvirtual boundaryのstateが一致しない
- current backendを新しいversioned targetへ再検証できず、旧validation recordを書き換える必要が生じた
- descriptorからrunnerの完全なlaunch contractを再現できず、手動argvまたはmutable registry依存が必要になった
- machine API schema 1の既存domainまたはUART RX正常系の回帰証拠を固定できない
- host presentationのdropがemulated eventを変える
- optional device設定を6項目だけで安全に識別できないtargetを起動しようとした
- baseline fixtureのsource/license/provenanceを固定できない
- 1倍未達を隠すsemantic shortcutが必要になった

## 9. 完成の定義

「preview機能完成」と「1倍完成」を分ける。

### 機能preview完成

- authoritative PASSからreceiptを生成し、same BIN/same runnerだけを起動できる
- registered targetのversioned receiptから、同じlaunch contractをheadless consumerで再検証・起動できる
- GUI、input、reset/reload、coverage banner、audio statusが動く
- hardware verdictを出さず、timing未達を明示する
- 既存Firmware backendとmachine APIの契約が不変

### 1倍qualified完成

- 上記に加え、`picotetris-opt1b`と`VRP-NES-0`で固定したNES-class targetの2 workload/host/thresholdで
  VRP-5 qualificationに合格
- 10 virtual分以上の各runでratio/lag/presentation/audio metricを保存
- capabilityにqualified範囲だけを明示

前者だけが完成しても有用な対話viewerにはなるが、「1倍エミュレーター完成」とは表現しない。
