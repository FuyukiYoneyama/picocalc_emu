# picocalc_emu

PicoCalc向けアプリを、AIや自動試験がPC上で観測・検証できる開発基盤です。
実機で確認済みのCanonical BSP、host backend、RP2040 firmware backend、scenario runner、
headless machine API、同一artifact実機相関の証拠を一つの流れとして管理します。

本リポジトリの対象は、RP2040（Pico 1）を搭載したClockworkPi PicoCalcです。

> **使い始める人とAIは、まず [`USER_GUIDE/`](USER_GUIDE/README.md) だけを読んでください。**
> 生成、ビルド、host／firmware検証、scenario、複数runの手順を一つの入口に集めています。
> `docs/`直下の凍結契約や`docs/history/`は、通常利用では読む必要がありません。

## 現在の状態

- 現行BSP source: **0.9.0**
- 標準BSP機能の実機相関baseline: **0.8.8**
- 推奨LCD: `pio-rgb565`（PIO0、RGB565、LCD DMAなし）
- SD: **FAT32が既定**、FAT16は明示的な互換profile
- SD RAWの標準pack／extract: [`USER_GUIDE/SD_IMAGES.md`](USER_GUIDE/SD_IMAGES.md)
- 対話型preview GUI（PicoCalc skin／LCD／UART0／入力）: [`docs/validated-realtime-preview/VRP3_GUI_20260829.md`](docs/validated-realtime-preview/VRP3_GUI_20260829.md)
- bounded host audio monitor（可変rate／drop診断／非同期transport）: [`docs/validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md`](docs/validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md)
- 1倍UX qualification workload: [`docs/validated-realtime-preview/VRP_LOAD0_SUSTAINED_LOAD_20260829.md`](docs/validated-realtime-preview/VRP_LOAD0_SUSTAINED_LOAD_20260829.md)。`VRP-LOAD-0`はrepository-ownedな320x320 RGB565全画面、48 kHz DMA音声、継続CPU負荷、clean clone再現性を固定するr1 prototypeを実装済みで、固定条件BIN／UF2再現性と1秒／2秒のruntime／input smoke（公式scenarioを含む）を確認済みです。1〜2 virtual分のvertical slice、admission／receipt、10 virtual分以上の準備run、VRP-5 formal qualificationは未完了です
- 通常のfirmware回帰backend: OPT1-B promoted commitをtargetごとに固定
- R0〜R6、NEXT-1〜NEXT-4: **完了**
- OPT2／OPT3: 正確性を確認したうえで性能条件未達として終了。候補はrevert済み
- 現在定義済みのR/NEXT作業パッケージ: **すべて完了または正式終了**
- UF2Loader統合: **U0・U1・U2・M-NESCO-S1・U3-A・U3-B・U4-P2・U5-A・U5-B・U6完了**。M-NESCO拡張受入（計画mapper 0/2/4/30、追加mapper 1、small/medium/large、SD→flash→再attach、CPU/PPU/core 1/DMA観測）も完了しました。U6はcleanな外部uf2loader source/buildで3回deterministic Gateに合格し、限定されたSD→flash→watchdog→再起動経路をcapabilityへ反映済み
- U6証拠: [`firmware-validation/evidence/uf2loader-u6-20260822-01/`](firmware-validation/evidence/uf2loader-u6-20260822-01/)。USB BOOTSEL/MSC、全UF2 family、任意loader forkは対象外
- SD-GEN-1-P0〜P5: **完了（P5 bounded capability accepted）**。P4でmulti-blockをdefault runtimeへ接続し、CMD18→2 block→CS保持中CMD12、CMD23/CMD25→1 block write→CMD17 readbackの実SPI0 synthetic firmware E2E、RAW export byte一致、既存U6・M-NESCO・FAT16/FAT32凍結trace再play、legacy no-default差分を確認しました。P5でversioned validation contractと限定範囲の`sd-multi-block` capabilityを追加しました。versioned targetと固定版`uf2loader-e2e`は変更していません。詳細計画は[`docs/SD_GEN1_IMPLEMENTATION_PLAN_20260823.md`](docs/SD_GEN1_IMPLEMENTATION_PLAN_20260823.md)、P5証拠は[`firmware-validation/evidence/sd-gen1-p5-20260823-01/`](firmware-validation/evidence/sd-gen1-p5-20260823-01/)です
- I2C-EXT: **E0〜E6完了**。DS3231／AT24C32／AHT20／BMP280を既定構成へ入れず、明示的なprofileでのみ接続するoptional capabilityを同一UF2実機相関まで固定しました。詳細は[`docs/I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](docs/I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)と[`firmware-validation/capability.json`](firmware-validation/capability.json)です
- Validated Realtime Preview: **VRP-0／VRP-1／VRP-2-a〜e／VRP-3／VRP-4完了（VRP-4 formal gate 2026-08-29）**。`picocalc.py preview`は権威あるfirmware PASS済みの同一BIN・同一runnerを再検証し、admitted descriptorを出力します。`preview-digest-gate`はclean backend `c1c20d7d86a3006569375bc333cf72494e95eb46`、runner SHA `f1a79384d0f90fafea1fbe9db249dc9c54327ef12bed0445c1e4bef23e3a050c`で、`picotetris-opt1b-vrp2f` revision 8と`picoedit-r1-vrp2f` revision 4のbatch／machine API／preview API／registered report四者projection digest、timeline、終端cycle、report checksを完全一致させました。`preview-gui`は同じadmitted descriptorからTk薄型frontendを起動し、PicoCalc skinへ320x320 RGB565 LCDを合成、UART0 consoleを自動起動、key down/held/up・auto-repeat抑止、reset/reload、sticky UX-invalid、F12 screenshotを提供します。VRP-4はbounded backend tap／非同期writer／frontend・host queue、可変source rate resampling、drop／underrun／epoch statusを追加し、host player障害をemulation verdictから分離します。同一`picotetris-opt1b-vrp4` revision 9のmonitor off／on／forced-dropを比較するformal evidenceを[`firmware-validation/records/vrp4-picotetris-20260829-01/`](firmware-validation/records/vrp4-picotetris-20260829-01/)に保存しています。これは実機相関、hardware-audio fidelity、または`realtime-1x-qualified`を意味しません。`VRP-LOAD-0`のrepository-owned sustained-load計画をVRP-5の正式qualification前提として追加し、既存VRP-NES-0のfixture／target／evidenceは歴史資料として保持します。詳細は[`docs/validated-realtime-preview/`](docs/validated-realtime-preview/)と[`docs/VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md`](docs/VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md)を参照してください

VRP-2-eの`c1c20d7d86a3006569375bc333cf72494e95eb46`は当時の不変evidenceに残しますが、現在のbackendのbranch／tagから到達できないため、VRP-5の再現可能なpinとしては使いません。到達可能なclean backendでの新しいversioned target／validation／receiptがVRP-5の前提です。`VRP-LOAD-0`のsource／fixture prototypeはこれと並行できます。

既存VRP-NES-0のsynthetic NROM fixture、target、validation、3回local evidenceは`historical / non-qualifying`
として保持します。`Picocalc_NESco`は独立プロジェクトであり、`picocalc_emu`はbranchを作成・改造・公開・pushせず、
NES固有の適合性を将来確認する場合だけ、所有者提供の未改変公開clean refまたは再現可能なartifactをoptional conformanceとして扱います。

正確な状態は[実装状況](docs/IMPLEMENTATION_STATUS.md)、計画の完了表は
[Milestones](docs/MILESTONES.md)、機械可読な対応範囲は
[`capability.json`](firmware-validation/capability.json)を参照してください。
M-NESCO-S1の実行証拠は
[`firmware-validation/evidence/m-nesco-20260813-01/`](firmware-validation/evidence/m-nesco-20260813-01/)にあります。
M-NESCO拡張の契約と実行証拠は
[`docs/history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md`](docs/history/uf2loader/UF2LOADER_M_NESCO_EXT_PREFLIGHT_20260822.md)にあります。
実行証拠は[`firmware-validation/evidence/m-nesco-ext-20260822-01/`](firmware-validation/evidence/m-nesco-ext-20260822-01/)です。
U6実uf2loader end-to-endの実装前契約は
[`docs/history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md`](docs/history/uf2loader/UF2LOADER_U6_PREFLIGHT_20260822.md)にあります。
実際の限定U6 Gate結果は
[`firmware-validation/evidence/uf2loader-u6-20260822-01/`](firmware-validation/evidence/uf2loader-u6-20260822-01/)にあります。
公開前の依存境界・ライセンス・ローカルゲートは
[`docs/PUBLIC_RELEASE.md`](docs/PUBLIC_RELEASE.md)を参照してください。
利用者向けの安定版、タグ、2リポジトリの対応付けは
[`docs/VERSIONING.md`](docs/VERSIONING.md)を正典とします。

## 最初に読むもの

- 通常利用の入口: [`USER_GUIDE/README.md`](USER_GUIDE/README.md)
- 人間向け入口: このREADME
- 通常利用とAIの実行手順: [USER_GUIDE/](USER_GUIDE/README.md)
- 高度なAI監督・実機依頼の規則: [AI_START_HERE.md](AI_START_HERE.md)
- 改造・backend変更・新しい検証targetを追加するAI／開発者: [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- 文書全体の案内: [docs/README.md](docs/README.md)
- 現在できること／できないこと: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- 複数firmware runの監視: [docs/CONCURRENT_RUNS.md](docs/CONCURRENT_RUNS.md)
- 公開版の選び方とバージョン運用: [docs/VERSIONING.md](docs/VERSIONING.md)
- BSPの公開APIと固定ハードウェア契約: [bsp/README.md](bsp/README.md)
- SD directory ↔ RAW image のデバッグ往復: [`USER_GUIDE/SD_IMAGES.md`](USER_GUIDE/SD_IMAGES.md)
- 検証対象アプリ・校正ツールの外部workspace: [外部workspaceの説明](docs/EXTERNAL_WORKSPACE.md)

検証対象の独立アプリとspeaker校正ツールは、Git境界を保つため本リポジトリの外側にある
任意の`picocalc_emu_ext/`へまとめられます。この外部workspaceは通常のアプリ生成・ビルド・
host検証・firmware backendの直接実行には必要ありません。target IDや`repository_directory`は
論理識別子として変更せず、物理配置と再現手順だけを外部workspace側で管理します。
一方、既存のPicoTetris／PicoEdit／NEXT-2 targetを再ビルドし、回帰・実機相関系列を
フォークへ継承する場合は、該当アプリsourceまたは同等source bundleが必要です。詳細は
[外部workspaceの説明](docs/EXTERNAL_WORKSPACE.md)の開発プロファイルを参照してください。

過去の経緯、却下実験、詳細記録は[`docs/history/`](docs/history/README.md)へ分離しています。
リポジトリを改造・拡張する場合の実行可能な手順は、まず[`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md)を読みます。
検証器が読む凍結R/NEXT契約は`docs/`直下に残します。歴史資料や凍結契約の「次は〜」は
当時の判断であり、現在の作業指示ではありません。

## 5分で始める

この節は概要です。実際にコマンドを選ぶときは、リポジトリ直下の
[`USER_GUIDE/`](USER_GUIDE/README.md)を正本として使ってください。既存の`docs/`リンクは
詳細仕様・凍結契約への参照であり、通常利用の代替入口ではありません。

必要条件はPython 3.9以降です。portable検証とプロジェクト生成にはPico SDKは不要です。
provenance付きの`verify-project`まで行う公開利用者は、GitHubのDownload ZIPではなく
`git clone`で取得してください。ZIPはGit metadataを含まないため、検証を安全側に倒して
`cannot judge`になります。

利用者はGitHub Releasesの具体的なタグ（例: `v0.1.0`）を使ってください。`main`は
開発中の先端であり、安定版の目印ではありません。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
```

通常編集するのは生成先の`app/`です。LCD、SD、keyboard、PSRAMのdriverをアプリへコピーして
再実装しないでください。

RP2040向けにビルドするときだけPico SDKを指定します。

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
python3 tools/picocalc.py verify-project --project ../MyApp
```

生成物は次です。

```text
../MyApp/build/picocalc_app.bin
../MyApp/build/picocalc_app.uf2
```

通常表示は`pio-rgb565`です。互換・診断用のSPI1/RGB666経路を使う場合だけ
`--lcd-variant hwspi-rgb888`を指定します。

`verify-project`は生成時に固定したBSP tree SHA-256を検査します。通常のGit statusとは別に、
アプリrepositoryのcommitをBSP由来として誤継承していないことも保証します。直接CMakeを使う場合と
音声を必須能力として判定する外部project契約は
[外部project品質ゲート](docs/EXTERNAL_PROJECT_QUALITY.md)を参照してください。

## 検証する

### Portable検証

生成物、source fingerprint、board profile、schemaをローカルで検査します。

```sh
python3 tools/picocalc.py verify
```

参照リポジトリまで固定commitで照合する場合:

```sh
python3 tools/picocalc.py verify --references --strict-commit
```

### Host backend

アプリロジックをネイティブ実行する高速経路です。

```sh
python3 tools/picocalc.py test --mode host
```

Host backendにはPIO、DMA、I2C transaction、割り込み、multicore、LCD wire形式はありません。
ハードウェア挙動についてはfirmware backendが権威です。詳細は
[Host backend](docs/HOST_BACKEND.md)を参照してください。

### Firmware backend

登録targetが固定したBIN、backend commit、device構成、scenario、期待reportをまとめて検査します。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target picocalc-template-b \
  --firmware /absolute/path/to/picocalc_app.bin \
  --backend-dir /absolute/path/to/picoem-at-0d434d789ed2
```

BINやscenarioのSHA、backend commit、LCD variantが契約と違えば実行前に失敗します。
例の`picocalc-template-b`はbackend `0d434d789ed2...`を固定しており、通常のbackend `main`を
そのまま指定しても合格しません。各targetの`backend.accepted`に一致する専用checkout／worktreeを
`--backend-dir`へ指定してください。必要commitと再現条件は
[`firmware-targets.json`](reference-projects/firmware-targets.json)にあります。
終了コードは`0=pass`、`1=judged failure`、`2=cannot judge`です。詳細は
[Firmware backend](docs/FIRMWARE_BACKEND.md)と
[Versioned validation](docs/VERSIONED_VALIDATION.md)を参照してください。

`picocalc.py test --mode firmware` は、長い実行を監視できるよう stderr heartbeat を既定で有効にします。
各 run に別の出力ディレクトリを割り当て、必要なら`--run-id`で再試行をまたぐIDを指定してください。
無効化は`--no-progress`です。heartbeatのfield、`finish`優先の判定、並列実行時のartifact分離は
[複数runの運用](docs/CONCURRENT_RUNS.md)にまとめています。

## 画面を見ながら入力する

再現可能な合否判定には、固定文字列を起動前に積むだけの`--keys`ではなくJSON scenarioを使用します。
UART、pixel、region hashなどの条件を待ってからkeyboard eventを投入できます。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target <target-id> \
  --firmware /absolute/path/to/app.bin \
  --snapshot-dir /tmp/picocalc-snapshots
```

形式と制限は[Scenario runner](docs/SCENARIO_RUNNER.md)を参照してください。

## Headless machine API

外部AIが長寿命sessionを逐次操作する場合はmachine APIを使います。NEXT-4で、emulator sessionを
JSON Linesで操作するschema 1 APIを実装しました。
`run`、`step`、`run_until`、`input`、`observe`、`subscribe`、`snapshot`を提供します。

```sh
cd ../picoem-picocalc
cargo run --release -p picocalc-harness --bin picocalc-run -- \
  --machine-api \
  --bin /absolute/path/to/app.bin \
  --bootrom "$PWD/roms/rp2040/bootrom-rp2040-b2.bin" \
  --board picocalc --lcd-variant pio-rgb565 \
  --psram --sd --sd-format fat32 --keyboard \
  --snapshot-dir /tmp/picocalc-machine-snapshots
```

標準入力へ1行1requestを送ります。

```json
{"schema":1,"id":"r1","op":"observe","domains":["machine","uart"]}
```

このコマンドはbackend checkoutのrootで実行します。`cargo run`がrunnerをbuildするため、clean cloneに
存在しない`target/release/picocalc-run`を前提にしません。machine APIはsession操作面であり、
target registryのfail-closed合否判定を置き換えず、単独ではtarget verdictを生成しません。
完全な契約は[Headless machine API](docs/HEADLESS_MACHINE_API.md)を参照してください。

## 実機へ渡す

通常のPicoCalcユーザーと同じく、**uf2loader経由を標準経路**とします。BOOTSEL書込みは、
flash書込み経路そのものを検証する場合や、uf2loaderを利用できない明示的理由がある場合だけです。
これは実機への通常転送経路の説明です。エミュレーター内でも、外部uf2loaderの限定された
SD→flash→watchdog→再起動経路を`python3 tools/picocalc.py uf2 e2e`で検証できます。
USB BOOTSEL/MSCや任意UF2の一般互換を意味しません。

実機へ渡す前に、少なくとも次を固定します。

- source commit
- BSP版、app版、LCD variant
- BIN／UF2 SHA-256
- build timestampとPico SDK/toolchain
- 合否条件と必要なUART marker
- 人間に依頼する最小限の操作と回復手順

色、向き、可読性、物理キーの感触、実際の聞こえ方はエミュレーターでは判定できません。
同一artifact相関の記録方法は[hardware validation](hardware-validation/README.md)を参照してください。

## 対応範囲の要点

対応済み:

- A/B両LCD経路、RGB565 framebuffer、PNG snapshot、GRAM readback
- 8 MiB PSRAM、SPI0 SD（FAT32既定／FAT16明示）、公式firmware準拠keyboard model
- scenario runnerとfail-closed structured verdict
- exact idle fast-forwardとpromoted OPT1-B fast path
- NEXT-2Aの凍結Serial multicore契約
- NEXT-2Bの凍結48 kHz DMA-paced digital audio sink契約と、同じPWM5_CC経路の可変timer分数／DMA block長を
  観測する診断audio sink（観測rateの解析artifact／WAV）
- PWM5_CCからの決定的な音量統計、非正規化raw WAV、および「好みとしての音量／極端なrail使用」を
  分けるproject-level品質契約
- キー入力なしの既知刺激とphone動画解析による内蔵speaker校正（初回hardware profileは未相関）
- 全体音量とpercussion／破裂音を人間が判定する2問式の実機speaker通過基準
- NEXT-3のSD CMD8 CRC negative conformance
- NEXT-4 JSONL headless machine API
- `picocalc.py test --mode firmware --sd-dir` による決定的FAT32 directory snapshot import（必要なら`--sd-image-out`／`--sd-manifest`）

限定または未対応:

- Threaded executionを正確性基準として使うこと
- 両coreからの同時device access、core 1 relaunchなど、NEXT-2A外の一般multicore
- 任意codec、別PWM slice／DMA destination／TREQ、mixingの音声一般化。診断sinkが受け入れるのは
  同じPWM5_CC経路に限ったtimer分数とDMA block長の変化であり、任意の音声経路や実機相関を意味しない
- bootromの実行、USB MSC boot
- 任意／無制限のSD multi-block、removal、write-protect、host directoryへのlive同期（boundedな`sd-multi-block` profileは対応済み）
- scenarioのloop／branch、任意report fieldの直接assert
- 実機の見え方・聞こえ方・物理操作品質を機械だけで判定すること

対応範囲を推測で広げず、[`capability.json`](firmware-validation/capability.json)の
具体的なtargetとlimitationを確認してください。

## リポジトリ構成

- `picocalc_emu`: Canonical BSP、CLI、target registry、scenario、証拠、文書
- `picoem-picocalc`: RP2040/PicoCalc firmware backendとmachine API
- `picotetris`、`picoedit-picocalc`: 正式回帰・実機相関に使う任意の外部アプリworkspace

backend sourceを本リポジトリへコピーせず、targetごとに正確なcommitを固定します。

## CIについて

検証の主体はローカル環境です。GitHub Actionsを通常の開発・デバッグ・試行錯誤に使いません。
workflowの追加・変更、pushによるCI発生、re-runは、必要性と使用量を確認してから行います。

## ライセンス

本リポジトリのコードは各ファイルと[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)の
記載に従います。派生backendは独立リポジトリで`MIT OR Apache-2.0`を維持します。
