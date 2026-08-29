# Validated Realtime Preview 実装計画

Status: **Current implementation plan / VRP-0〜VRP-4 formal evidence complete; VRP-5 reusable backend-pin preflight complete; VRP-LOAD-0 prototype and 120-second vertical slice complete as the repository-owned 1x workload; load admission/preparation and VRP-5 qualification remain**
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
7. 正式な1倍判定で必要なのはNESの意味論ではなく、全画面描画・音声・CPU・virtual timeを
   継続させる負荷特性である。したがって外部`Picocalc_NESco`はVRP-5の必須依存にせず、
   repository-ownedな`VRP-LOAD-0`負荷プロファイルを正式workloadとして別途準備する。
   既存の`VRP-NES-0` fixture／evidenceは歴史資料として保持し、資格判定には使用しない。
8. preview IPC schema 1はVRP-0の最初の成果物として、具体的なwire fixtureとともに凍結する。
   magic、version、endian、field幅、message kind、payload上限、異常系を未定義のままproduction
   codeへ進まない。

9. VRP-0で固定したtargetのbackend pinと、preview APIを実装した現在のbackendは同一とは限らない。
   既存のvalidation record／target revisionを上書きせず、VRP-2のregistered-target gateへ入る前に、
   現行backendで再検証した新しいversioned target revision、validation record、receiptを作る。
   旧revisionの実機相関・batch証拠は歴史的な証拠として保持し、preview用の再検証結果と混同しない。
10. VRP-2-eで固定した`c1c20d7d86a3006569375bc333cf72494e95eb46`は、証拠の一部としては変更せず保持するが、
    2026-08-29時点の`picoem-picocalc`のbranch／tagから到達できない。したがって、このcommitを
    VRP-5の再現可能な測定pinとして再利用しない。VRP-5前に、到達可能なclean backendで新しい
    versioned target、validation record、receiptを作る。これはVRP-0〜VRP-4の実装・証拠を取り消す条件ではない。
11. `picoem-picocalc`に既存の未コミット差分がある間は、backend identityを「clean」と記録しない。
    差分はpreview変更へ混ぜず、意味のある変更か整形だけかを確認したうえで、別commitとして固定するか、
    所有者の判断で作業ツリーから取り除く。VRP-LOAD-0のsource／fixture設計とprototypeは並行できるが、
    その正式target受入とVRP-5のqualification測定は、このclean reachable-pin gate後に行う。

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

### 4.3 VRP-5前提: 到達可能なbackend pinとclean worktree

VRP-2-eのlocal gateは、当時のclean checkoutで得た不変の歴史証拠として保持する。しかし、後続の
qualificationが同じbackendを再現できることは別の条件である。次の確認を、VRP-5の測定開始前に行う。

1. `git branch -a --contains <accepted-commit>`と`git tag --contains <accepted-commit>`で、target registryが
   指すbackend commitが現在のbranchまたはtagから到達できることを確認する。objectが存在するだけでは
   再現可能なpinとみなさない。
2. 到達不能な`c1c20d7d86a3006569375bc333cf72494e95eb46`を固定する
   `picotetris-opt1b-vrp2f` revision 8／`picoedit-r1-vrp2f` revision 4は、既存recordを改変せず、
   VRP-5の入力としては保留する。
3. 現行の到達可能なbackend（2026-08-29時点の`main`は`65c795e87321e79b960ac8a7495a205de6a24ec0`）を
   clean checkoutで固定し、同じBIN／runner／device projectionを新しいversioned targetとして再検証する。
   `picotetris-opt1b`の論理workloadを使う場合も、baseline revision 5と新しいlaunch target id／revisionを
   混同しない。
4. backend作業ツリーにある未コミット差分は、preview実装commitへ混ぜない。cargo fmt由来に見える場合でも、
   実際の差分を確認し、別commitのidentityへ含めるか、clean checkoutへ戻すかを先に決める。
5. 新targetのvalidation record、backend executable SHA、receipt、admitted descriptorを作り、旧revisionの
   evidence／SHA／実機記録は変更しない。ここまでを`VRP-5 reusable backend pin gate`の完了とする。

**Gate result (2026-08-29):** `picotetris-opt1b-vrp5` revision 10を追加し、到達可能な
`picoem-picocalc@65c795e87321e79b960ac8a7495a205de6a24ec0`のclean checkoutで、同じsource／BIN／scenario／
device projectionを再検証した。2つのclean source cloneでBIN／UF2が一致し、firmware report、validation
record、receipt、admitted descriptor、headless preview consumerが合格した。recordとartifactは
[`VRP5_BACKEND_PIN_PREFLIGHT_20260829.md`](validated-realtime-preview/VRP5_BACKEND_PIN_PREFLIGHT_20260829.md)
および`firmware-validation/records/vrp5-pin-picotetris-20260829-01/`に固定した。これはreusable
backend pin gateの完了であり、`VRP-LOAD-0`のcompletion、threshold decision、VRP-5 qualification、
`realtime-1x-qualified`を意味しない。

このgateと`VRP-LOAD-0`のsource／fixture prototypeは並行してよい。ただし、`VRP-LOAD-0`の正式target
recordとVRP-5 qualificationは、到達可能なbackend pin、clean worktree、再現可能なartifactが揃うまで開始しない。

## 5. 作業パッケージ

### VRP-0: contract・host spike・baseline preflight（4〜8時間）

変更前に次を固定する。

1. receipt schema 1と、VRP-0で具体値を凍結したpreview IPC schema 1のfixture（UART0のTX/RX双方を含む）。正典は[`docs/validated-realtime-preview/`](validated-realtime-preview/)
2. supported hostのWSLg GUI/audio capability。GUI/audio Rust crateはまだproduction dependencyへ追加せず、候補crateのbuild/license確認は実際に依存を追加するVRP-2/VRP-3のlockfile変更前に行う
3. `picotetris-opt1b`（revision 5）と`picoedit-r1`（revision 1）のtarget/validation record、provenance、
   それぞれのbaseline手順
4. 現行accepted backendでのGUIなし速度baseline
5. performance測定中は並列runを行わない条件

`VRP-LOAD-0`はこのgateでは要求しない。VRP-0は既存2 targetでreceipt、admission、GUI、UART、
audioの実装を先行できる。正式な1倍qualified判定に必要な継続負荷fixtureは、下記の
`VRP-LOAD-0`で別途準備する。負荷fixture、source、license、生成手順、hashはすべて
repository-ownedまたは再配布可能な入力として固定する。

**完了gate:** WSLg capability probeがwindowとsilent playback deviceの開閉を確認し、IPC schema 1
fixtureの具体値と、上記2 workloadのprovenance・baseline手順が記録される。VRP-0ではproduction
codeとRust GUI/audio dependencyを変更しない。VRP-1でも依存追加は行わず、候補crateのversion/build/license選定は
VRP-2/VRP-3で最初にlockfileを変更する前に別記録する。実測結果は[`VRP0_HOST_SPIKE_20260828.md`](validated-realtime-preview/VRP0_HOST_SPIKE_20260828.md)、
基準値は[`VRP0_BASELINE_20260828.json`](validated-realtime-preview/VRP0_BASELINE_20260828.json)を参照する。

### VRP-LOAD-0: repository-owned sustained-load target/fixture（10〜20時間、正式qualificationの前提）

VRP-5が必要とするのはNES-classの意味論ではなく、1倍UXを判定できる継続負荷である。
`VRP-LOAD-0`は外部プロジェクトの機能を借りるのではなく、`picocalc_emu`が所有・公開できる
source、fixture、生成手順から構成する。

最低限、次の負荷特性を固定する。

1. 320x320 RGB565の全画面を固定レートで連続更新する。
2. 48 kHzのDMA-paced audioを同時に連続ストリーミングする。
3. CPUを継続的に負荷し、idle fast-forwardやsemantic shortcutが効かない状態にする。
4. 固定入力・固定seed・固定device profileで10 virtual分以上連続実行する。
5. clean cloneからsource、fixture、BIN、runner、backend、toolchainを再現できるようにする。

上記は負荷の目的を定める要求であり、同じ実装と同じ判定を再現するには、firmwareのsourceを
書き始める前に次の実装契約を1つのmachine-readableまたはversioned recordへ固定する。r1では
この契約を[`VRP_LOAD0_PROFILE_R1.md`](validated-realtime-preview/VRP_LOAD0_PROFILE_R1.md)へ固定してから
source codingを開始した。以後のsource／scenario変更は、既存recordを黙って書き換えずrevisionを上げる。

- **所有権とidentity:** source directory、license、target id／revision、BINの生成元、許諾された
  fixtureの一覧とSHA-256。`picotetris-opt1b` revision 5は比較用の論理workload identityであり、
  実際のVRP-5 launchには到達可能なbackend pinを持つversioned targetを使用する。旧`vrp2f` r8を
  自動的に現行targetとみなさない。
- **display contract:** 320x320 RGB565全画面更新の具体的な更新レート、frame生成アルゴリズム、seed、
  LCD/PicoCalc device profile、frame/event marker。単に「画面が動く」だけでは合格条件にしない。
- **audio contract:** 48 kHzのchannel数、sample format、DMA timer／block／buffer条件、決定的な生成
  pattern／seed、期待するsource／sink observation、audio event digest。`48 kHz`だけではfixtureを
  一意に再現できない。
- **CPU／multicore contract:** 継続負荷の処理内容、core 0／core 1の役割、停止・待機を許す箇所、
  `step_until`のexact idle fast-forwardを許すかどうか。許す場合は意味論が同一であることと、負荷中に
  timing pressureを隠していないことをreportへ記録する。
- **input／scenario contract:** key down／held／upまたはUART入力の列、入力cycle、seed、virtual duration、
  cycle limit、終了marker、期待するauthoritative observation digest。host wall clockをguestの入力源に
  しない。
- **execution／evidence contract:** clean cloneからのbuild command、SDK／BSP／compiler／CMake／Ninja、
  backend commitとexecutable SHA、headless qualificationの実行経路、preview API／GUIのUX smoke経路、
  出力manifestと全artifact SHA。既存のrelease runner timerだけでGUI UXを測ったことにしない。
- **UX timing contract:** 1倍のthroughputを測るmetricと、入力から画面反映までの応答を測るmetricを分離し、
  後者を測らない場合は「1倍UX」ではなく「継続負荷timing qualification」と表示する。

このrecordを作ること自体はVRP-LOAD-0の実装完了ではない。r1ではまず1 virtual秒のpre-gate smokeを
clean cloneからbuild → runし、画面、音声、core 0／1、入力、終端UART recordが観測可能であることを確認した。
このsmokeは1〜2 virtual分のvertical sliceではない。次に1〜2 virtual分のvertical sliceをclean cloneから
build → run → report／receipt → existing admission／preview pathまで通し、上記契約の各値を収集できることを
確認する。その後に10 virtual分以上の準備runへ進む。vertical sliceでsource、target、scenario、metricの
いずれかが未定義なら、formal completion・qualificationを開始したと扱わない。

なお、現在のbackendの`step_until`は、両core停止中の安全なevent boundaryまでexactに進めることがある。
これはcycleを捨てる不正なshortcutとは限らないため、「idle fast-forward禁止」は実装者の印象で判定せず、
許可範囲と観測証拠を上記CPU／multicore contractへ明記する。

準備gateでは同じ入力を少なくとも3回実行し、source／fixture／artifactのSHA、wall-clock ratio、
rolling ratio、pacer backlog／overrun、presentation drop、audio underrun／overrun、
authoritative observation digestを保存する。1倍の許容幅とlag上限は、測定結果を見た後に変更
できないよう、VRP-5 qualificationの前に別decision recordで固定する。

このdecision recordは、qualification結果を通すための後付け閾値になってはならない。drop／underrun／
digest不一致などの絶対条件、ratio／lagの統計方法、run数、許容値の選択根拠、`REALTIME OK`／
`REALTIME NOT MET`の機械的判定式を記載し、準備baselineの閲覧後かつqualification run開始前に凍結する。
baselineを見て決めてよいのは、事前に定めた選択規則の範囲に限る。各runの結果を見て閾値や対象runを
変更してはならない。

**状態（2026-08-29）:** repository-owned fixtureのprototype実装、2つのclean cloneによる固定条件build再現性、
1秒／2秒のruntime／input smoke（公式scenarioを含む）までは完了。1〜2 virtual分のvertical slice、admission／receipt、10 virtual分以上の
準備run、threshold decision、VRP-5 qualificationは未完了である。これはVRP-0〜VRP-4の完了を取り消さず、
VRP-5へ進むための新しいrepository-owned workload preparationである。実装時に外部sourceの取得、改変branchの作成、
外部projectへの公開・pushを必要条件にしてはならない。詳細なprofileは
[`VRP_LOAD0_SUSTAINED_LOAD_20260829.md`](validated-realtime-preview/VRP_LOAD0_SUSTAINED_LOAD_20260829.md)
に固定する。

#### VRP-NES-0／NEScoの歴史資料としての扱い

既存のrepository-owned synthetic NROM、NESco診断BIN、target entry、validation、実行evidenceは
削除せず、`historical / non-qualifying`として保持する。これらはSD→flash→XIP、core 1、DMA、
UART、framebufferの当時のlocal結果を示すが、VRP-5の1倍資格、NEScoの一般的互換性、公開sourceの
再現性を示さない。

`vrp-nes0-synthetic-nrom`の`pending-revalidation`状態も歴史的な再検証可能性の記録として残すが、
VRP-5のblockerとはしない。将来NES固有の適合性を確認する場合だけ、NESco所有者が提供する
未改変の公開clean refまたは再現可能なartifactを、別のoptional conformanceとして扱う。
`codex/mnesco-extension`のような診断branchは正式証拠・資格判定・公開成果物に使用しない。

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

`VRP-5 reusable backend pin gate`と`VRP-LOAD-0`のcompletion gateを先に閉じる。初期のpreview candidate
測定は`picotetris-opt1b`と`picoedit-r1`をそれぞれ単独実行する。正式な1倍qualification測定は、
`VRP-LOAD-0`完了後に、`picotetris-opt1b`の論理workloadを表す到達可能なversioned launch targetと
`VRP-LOAD-0`をそれぞれ単独実行する。`picotetris-opt1b` revision 5、旧`picotetris-opt1b-vrp2f` r8、
現行`picotetris-opt1b-vrp4` r9は同じものとして扱わず、実際に使ったtarget id／revisionをrecordへ固定する。
いずれも次を保存する。

- host/OS/CPU、backend/BIN/receipt SHA
- session ratioとrolling ratio
- lag/backlog、behind count
- presentation drop
- audio underrun/overrun/drop
- unsupported/truncated MMIO
- CPU使用率と最大RSS（補助値）

測定経路を2つに分ける。coreのthroughput／timingは、既存release runnerまたは同じ境界を持つpreview
APIのheadless経路で測定し、正確なcommand、timer範囲、virtual boundary、出力manifestをrecordする。
GUIを起動した事実だけをcore timingの証拠にしない。UX確認は同じadmitted descriptor／同じBINでpreview
API／GUIを別途実行し、固定入力に対するkey down／held／upから画面反映までの応答観測を保存する。
応答観測を実装できない場合、結果の表示名は`1倍UX`ではなく`継続負荷timing`に限定する。

screeningは各workload 10 wall分以上でよい。qualificationは既存baselineが定めた逐次10-run／95% CI
手順を維持し、各workload **10 virtual分以上を各runで要求する**。並列runは行わない。run数、統計方法、
ratio／lag／drop／underrunの合格条件は、qualification開始前にdecision recordへ凍結する。
`VRP-LOAD-0`またはreusable backend pinが未整備の場合、existing workloadの測定を完了しても正式な
1倍qualificationは未完了とする。1倍未達なら`REALTIME NOT MET`を正式結果として記録し、機能preview、
realtime candidate、realtime-qualifiedを混同しない。

baseline reviewでrealtime許容幅とlag上限を別decision recordへ固定し、その同じ条件でqualificationを
実行する。baselineを参照してよいのは、あらかじめ記載した選択規則に従う場合だけであり、測定値を
見てから都合よく各runの閾値、対象run、target revision、測定経路を変更しない。

**完了gate:** preview candidateについては`picotetris-opt1b`と`picoedit-r1`の2 workload recordがあり、
`UNCALIBRATED`または`REALTIME NOT MET`の根拠が機械可読に残る。正式な
`REALTIME OK`／`realtime-1x-qualified`には、これに加えて、到達可能なbackend pinを持つ`picotetris-opt1b`
launch target、`VRP-LOAD-0`のrepository-owned workload record、凍結済みdecision record、逐次10-runの
qualification evidenceが必要である。GUIの入力応答観測を行わない場合は、`realtime-1x-qualified`を
「1倍UX」の意味で表示しない。

### VRP-6: versioning・capability・利用文書（6〜10時間）

- `USER_GUIDE`にvalidation→receipt→previewの最短手順
- `DEVELOPER_GUIDE`にprocess/IPC/admission拡張規則
- capabilityは`validated-preview-admission`と`realtime-1x-qualified`を分離
- 1倍未達なら後者をsupportedへしない
- supported host、known limitation、audio fidelity、hardware verdictなしを明記
- receipt/IPC schemaをversioned contractとして固定
- 利用者向けには、`機能preview`、`継続負荷timing`、`1倍UX`、`hardware correlation`を別の状態として
  最短の起動手順とともに表示し、ratio／lag／behind／drop／`timing-only`／`degraded`の意味を平易に説明する

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
| 6a | VRP-5 reusable backend pin preflight | **完了 2026-08-29。到達可能な`65c795e...`のclean backendで`picotetris-opt1b-vrp5` r10を新規作成し、2 clean cloneのBIN／UF2一致、firmware report、validation record、receipt、admission、headless preview consumerを確認。旧c1c20d7-pinned evidenceは不変のまま保持** |
| 6b | VRP-LOAD-0 repository-owned sustained-load target/fixture（VRP-5正式qualification前に完了） | **進行中。repository-owned r1 fixtureを`40a9e07`で実装し、2 clean cloneの固定条件BIN／UF2一致、quantum 1の1秒／2秒runtime／input smoke、120秒vertical slice（公式scenario）とnon-formal completion recordを確認。load側admission／receipt、3回determinism、10 virtual分以上の準備runは未完了** |
| 7 | VRP-5 baseline/threshold/qualification | **未着手。6aのreusable pin gateと6bのcompletion gate後に開始** |
| 8 | VRP-6 capability/docs/versioning | 未着手 |
| 9 | VRP-7 exact optimization | 条件付き。VRP-5判断前は着手しない |

VRP-0〜VRP-6のpreview実装中心工数は、今回追加したregistered-target closureを含めて
**128〜220時間 + 実測時間**である（本体スキン校正、UART RX/TX、bounded host audio monitorを含む）。VRP-2の初期API、
versioned target、descriptor consumer、machine API transcript、UART RX正常系、registered-target digest
closure、VRP-3 GUI/input、VRP-4の実装・local test・formal evidenceは完了している。今後の工数はqualificationで見積もる。
正式な1倍qualificationまで行う場合は、これにVRP-LOAD-0の**10〜20時間**とその測定時間を加える。
この10〜20時間はsource／fixtureのprototypeおよび初期integrationの見積りであり、target registry／
validation／receipt、到達可能なbackend pinの再受入、decision record、逐次qualification runの時間を
含まない。測定時間はhost性能と負荷profileで変動するため、完了予定時間として扱わない。
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

`picoem-picocalc`のclean checkout、到達可能なbackend pin、未コミット差分の扱いは、preview文書の
commitへ暗黙に含めない。backend側の整形差分を採用する場合も、対象範囲・理由・検証結果を別commitで
固定し、そのcommitを新targetのbackend identityへ明示的に記録する。

各単位でローカルtestを完了してから次へ進む。通常の試行錯誤にGitHub Actionsを使わず、
workflow追加・trigger/job変更・CI実行増加は所有者の事前許可なしに行わない。pushをCIの代わりにしない。

## 8. 中止条件

次の場合は無理に先へ進まず、原因と再開条件を記録する。

- VRP-5で使うbackend commitがbranch／tagから到達できない、またはbackend worktreeがcleanでない
- backend pinの再受入、target revision、decision record、qualification run数のいずれかを機械可読に固定できない
- GUI/audio dependencyがqualified hostで再現可能にbuild/runできない
- same executable identityを維持できない構成変更が必要になった
- batch/machine API/preview API間で同じvirtual boundaryのstateが一致しない
- current backendを新しいversioned targetへ再検証できず、旧validation recordを書き換える必要が生じた
- descriptorからrunnerの完全なlaunch contractを再現できず、手動argvまたはmutable registry依存が必要になった
- machine API schema 1の既存domainまたはUART RX正常系の回帰証拠を固定できない
- host presentationのdropがemulated eventを変える
- optional device設定を6項目だけで安全に識別できないtargetを起動しようとした
- baseline fixtureのsource/license/provenanceを固定できない
- VRP-LOAD-0の負荷特性、source、fixture、clean clone再現性を固定できない
- 外部プロジェクトの改変branchを資格判定または公開成果物の前提にしなければ負荷を再現できない
- 1倍未達を隠すsemantic shortcutが必要になった
- `1倍UX`を名乗るのに入力から画面反映までの応答を測定できない

## 9. 完成の定義

「preview機能完成」と「1倍完成」を分ける。

### 機能preview完成

- authoritative PASSからreceiptを生成し、same BIN/same runnerだけを起動できる
- registered targetのversioned receiptから、同じlaunch contractをheadless consumerで再検証・起動できる
- GUI、input、reset/reload、coverage banner、audio statusが動く
- hardware verdictを出さず、timing未達を明示する
- 既存Firmware backendとmachine APIの契約が不変

### 1倍qualified完成

- 上記に加え、到達可能なclean backend pinで再受入した`picotetris-opt1b` launch targetと、
  repository-owned `VRP-LOAD-0`の2 workload/host/thresholdでVRP-5 qualificationに合格
- 凍結済みdecision recordに従う逐次10-run／95% CIのqualification evidenceがあり、各runで10 virtual分以上の
  ratio／lag／presentation／audio metricを保存
- `1倍UX`と表示する場合は、同じadmitted BINを使うGUI経路で固定入力のinput-to-visible-response観測も保存する。
  それを行わない場合は、表示名を`継続負荷timing`に限定する
- capabilityにqualified範囲だけを明示

前者だけが完成しても有用な対話viewerにはなるが、「1倍エミュレーター完成」とは表現しない。
