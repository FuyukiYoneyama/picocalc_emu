# Validated Realtime Preview 実装計画

Status: **Current implementation plan / implementation not started**
Date: 2026-08-28
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

既存の権威あるFirmware backend、schema 8、target registry、machine API schema 1は変更しない。
previewはhardware PASS/FAILを生成しない。

## 2. 確認した現状

| 項目 | 現状 | 実装への影響 |
|---|---|---|
| `MachineSession` | `picocalc-harness/src/main.rs`内の非公開型 | 共通session moduleへ機械的に分離してからpreview APIを接続する |
| 既存TUI | 独自の簡易LCD/GPIO経路 | PicoCalc previewのdevice modelとして流用しない |
| wall-clock pacer | `picoem-common::Pacer`として実装済み | core semanticsを変えず再利用する |
| pacer metric | cycle、wall、emulation、spin、behind count | rolling ratioとlagはcold pathで導出・追加する |
| framebuffer | PicoCalc LCD modelからRGB565 snapshotを取得可能 | presentation cadenceでのみcopyする |
| keyboard | `MachineSession`のpressed/held/released入力が存在 | OS auto-repeatだけfrontendで抑止する |
| audio | 現在はrun終了時に全PCMを回収する診断capture | bounded streaming tapが必要。emulated sinkは止めない |
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

IPCはlocal process間だけを対象とし、network APIやremote controlは初版へ入れない。

### 3.4 初版host範囲

最初のqualified hostは、現在の主要開発環境である **Ubuntu 24.04 on WSL2/WSLg x86_64** とする。
GUI候補は`winit` + software framebuffer presentation、audio候補は`cpal`とする。VRP-0で
build/runtime/license/WSLg audioを確認し、合格するまでdependencyをproduction pathへ固定しない。
他OSは「動く可能性」と「qualified」を区別する。

### 3.5 PicoCalc本体スキン

提示された`IMG_20260828_0002a.jpg`のような本体写真は、emulator modelやconformance artifactではなく、
previewのpresentation assetとして扱う。実装時には共有workspaceの`log/`を実行時依存にせず、次の条件を満たす
repository assetへ取り込む。

- `assets/preview/picocalc-device-skin.jpg`（または同等の明示的なasset path）として固定する
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

## 5. 作業パッケージ

### VRP-0: contract・host spike・baseline preflight（4〜8時間）

変更前に次を固定する。

1. receipt schema 1とpreview IPC schema 1のfixture（UART0のTX/RX双方を含む）
2. supported host、GUI/audio dependency、third-party license
3. active PicoTetris targetと、再配布可能なNES-class target/fixture
4. 現行accepted backendでのGUIなし速度baseline
5. performance測定中は並列runを行わない条件

NES-class fixtureにはreal cartridge ROMや再配布条件不明のdataを入れない。適切なhomebrewまたは
synthetic ROMを使い、そのsource/license/hashを固定する。

**完了gate:** dependency spikeがWSLgで本体window、UART0 console、input/audio deviceを開閉でき、2 workloadの
provenanceとbaseline手順が記録される。production codeはまだ変更しない。

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

### VRP-2: shared session coreとpreview backend API（24〜40時間）

`picoem-picocalc`側で、現在`main.rs`にあるMachineSession、board handle、boot/session factoryを
共通moduleへ分離する。batch scenarioとmachine APIを先に同じmoduleへ戻し、report bytes、cycle、
UART、framebuffer、device observationの既存回帰が変わらないことを確認してから`--preview-api`を足す。

preview loopは既存`Pacer`を用い、clock変更時も`update_sys_clk_hz()`を呼ぶ。追加metricは
session/rolling `virtual_time / wall_time`、lag、behind count、presentation/audio queue状態で、
emulation hot pathの決定性へ入れない。

F5は起動時に読んだadmitted BINとinitial device fixtureから新MachineSessionを作る。
disk上のBINを再読しない。watchdog resetとは別の、preview operatorによるfull machine resetである。

#### PicoCalc UART0 console

現在のUART modelはfirmware TXの観測を持つ一方、外部RX stimulusをまだ提供していない。UARTウィンドウを
「ログ表示」として実装して済ませず、VRP-2で次を追加する。

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
- repaint coalescing/drop count。backend frame/device eventはskipしない
- unsupported/truncated MMIOのsticky UX-invalid state
- sticky stateはF5で保持、admission済みreloadだけでclear

screenshotは表示用PNGとし、conformance hashへ使わない。スキンを含むscreenshotは本体写真の
presentationを含むため、raw framebufferのgolden imageとは別物である。

**完了gate:** 本体スキンの校正済み開口部へframebufferが合成され、key down/hold/up、auto-repeat抑止、
UART consoleの自動起動とTX/RX双方の表示・入力、reset、成功reload、拒否reload、sticky coverageを自動testし、
人間のWSLg smokeで本体windowとUART windowを確認する。

### VRP-4: bounded host audio monitor（16〜28時間）

既存のrun全体`Vec<i16>` captureとは別に、preview専用のbounded PCM tapを追加する。

- emulated PWM/DMA/audio sinkを常に進める
- transport ringが満杯ならhost向けblockだけをdropし、drop countを増やす
- host underrun/overrun/drop時は`Audio: degraded`
- unsupported streamは`timing-only`
- mute/gainはhost monitorだけに作用
- smoothing、EQ、compressor、enhancementを標準経路へ入れない
- sample rate変更時はtransport resamplingを明示し、元rate/timingをstatusへ残す

**完了gate:** monitor off/on/forced dropの3条件で、同じvirtual boundaryのaudio event digest、cycle、
UART、framebufferが一致する。host failureがemulator停止やfalse PASSへ変換されない。

### VRP-5: baseline・threshold決定・qualification（10〜18時間 + 実測時間）

まずthresholdを決めずに測る。PicoTetrisとNES-classをそれぞれ単独実行し、次を保存する。

- host/OS/CPU、backend/BIN/receipt SHA
- session ratioとrolling ratio
- lag/backlog、behind count
- presentation drop
- audio underrun/overrun/drop
- unsupported/truncated MMIO
- CPU使用率と最大RSS（補助値）

screeningは各workload 10 wall分以上でよいが、1倍qualificationは各workload **10 virtual分以上**を
要求する。1倍未達なら`REALTIME NOT MET`を正式結果として記録し、機能previewとrealtime-qualifiedを
混同しない。

baseline reviewでrealtime許容幅とlag上限を別decision recordへ固定し、その同じ条件でqualificationを
再実行する。測定値を見てから都合よく各runの閾値を変更しない。

**完了gate:** 2 workloadのrecordがあり、`UNCALIBRATED`、`REALTIME NOT MET`、または
`REALTIME OK`の根拠が機械可読に残る。

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
| 1 | VRP-0 contract/host spike/baseline preflight | 未着手 |
| 2 | VRP-1 receipt/admission | 未着手 |
| 3 | VRP-2 shared session/preview API | 未着手 |
| 4 | VRP-3 GUI/input/reset/reload | 未着手 |
| 5 | VRP-4 audio monitor | 未着手 |
| 6 | VRP-5 baseline/threshold/qualification | 未着手 |
| 7 | VRP-6 capability/docs/versioning | 未着手 |
| 8 | VRP-7 exact optimization | 条件付き。VRP-5判断前は着手しない |

VRP-0〜VRP-6の中心工数は**96〜160時間 + 実測時間**である（本体スキン校正とUART RX/TXを含む）。
VRP-7は結果依存で別枠とする。
GUIだけを先に作るとadmissionとbackend identityを後付けすることになるため、順序を入れ替えない。

## 7. commitと検証の単位

推奨commit単位:

1. contract/fixture/docsのみ
2. receipt schema/generator/negative tests
3. admission supervisor/negative tests
4. MachineSession機械的分離（挙動差ゼロ）
5. preview IPC/backend loop
6. frontend window/framebuffer
7. keyboard/reset/reload/sticky state
8. audio transport
9. baseline/decision record
10. capability/user/developer docs

各単位でローカルtestを完了してから次へ進む。通常の試行錯誤にGitHub Actionsを使わず、
workflow追加・trigger/job変更・CI実行増加は所有者の事前許可なしに行わない。pushをCIの代わりにしない。

## 8. 中止条件

次の場合は無理に先へ進まず、原因と再開条件を記録する。

- GUI/audio dependencyがqualified hostで再現可能にbuild/runできない
- same executable identityを維持できない構成変更が必要になった
- batch/machine API/preview API間で同じvirtual boundaryのstateが一致しない
- host presentationのdropがemulated eventを変える
- optional device設定を6項目だけで安全に識別できないtargetを起動しようとした
- baseline fixtureのsource/license/provenanceを固定できない
- 1倍未達を隠すsemantic shortcutが必要になった

## 9. 完成の定義

「preview機能完成」と「1倍完成」を分ける。

### 機能preview完成

- authoritative PASSからreceiptを生成し、same BIN/same runnerだけを起動できる
- GUI、input、reset/reload、coverage banner、audio statusが動く
- hardware verdictを出さず、timing未達を明示する
- 既存Firmware backendとmachine APIの契約が不変

### 1倍qualified完成

- 上記に加え、固定した2 workload/host/thresholdでVRP-5 qualificationに合格
- 10 virtual分以上の各runでratio/lag/presentation/audio metricを保存
- capabilityにqualified範囲だけを明示

前者だけが完成しても有用な対話viewerにはなるが、「1倍エミュレーター完成」とは表現しない。
