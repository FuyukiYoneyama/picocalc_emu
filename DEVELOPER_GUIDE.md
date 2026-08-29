# PicoCalc emulator developer guide

この文書は、`picocalc_emu`をフォークして改造する人とAIのための実行入口です。
通常のPicoCalcアプリを作るだけなら[`USER_GUIDE/README.md`](USER_GUIDE/README.md)を使い、
エミュレーター本体、firmware backend、検証target、証拠、optional hardware profileを変更する場合だけ、
この文書を先に読んでください。

## 1. 文書の優先順位

現在の判断に使う順序は次です。

1. この`DEVELOPER_GUIDE.md` — 改造時の入口と実行手順
2. [`AI_START_HERE.md`](AI_START_HERE.md) — AIの責任境界、実機依頼、CI節約規則
3. [`README.md`](README.md) — 公開範囲と5分の概要
4. [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)、[`docs/MILESTONES.md`](docs/MILESTONES.md)、[`firmware-validation/capability.json`](firmware-validation/capability.json) — 現在の対応範囲
5. [`reference-projects/firmware-targets.json`](reference-projects/firmware-targets.json) — targetのsource／BIN／backend／scenario pin
6. `docs/history/`、`firmware-validation/records/`、`hardware-validation/records/` — 書き換えない時点証拠

履歴文書にある「次に行う」は当時の判断です。現在の作業を決めるときは、必ず上位の現在文書と
machine-readable capabilityを確認します。文書とsourceのどちらかが矛盾している場合、推測で進めず、
実装・target registry・evidenceを読んでから現在文書を直します。

## 2. リポジトリの責任範囲

| repository／場所 | 役割 | 通常の変更先 |
|---|---|---|
| `picocalc_emu` | Python CLI、Canonical BSP、target registry、schema、evidence、利用文書 | このrepoの`tools/`、`bsp/`、`reference-projects/`、`firmware-validation/`、docs |
| `picoem-picocalc` | RP2040 core、PicoCalc device model、firmware runner、machine API | 隣接repoのRust source／tests／docs |
| `picocalc_emu_ext/` | PicoTetris、PicoEdit、実機probe、speaker校正など任意の外部入力 | 各アプリの独立repo。通常runtimeの依存ではない |
| `RTC/`などの一次資料 | 個人hardwareや公式firmwareの参照source | emulationの都合で直接変更しない |

`picoem-picocalc`のsourceをこのrepoへvendorしません。targetが受け入れるbackend commitは
必ずtarget registryに固定し、working treeがdirtyのまま正式なvalidationを作りません。

現在のbackendの役割は次の通りです。

- 一般のpromoted target: `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- I2C-EXT E5/E6を含む現在のlocal development main: `f810d059958773d1b42a1c6d03cc15183cdc1a4f`
- OPT4時点の`d96f73b`や`a67e81c9`は凍結した過去の測定値であり、現在のHEADではありません

## 3. 最小セットアップ

通常の生成・portable検証は、このrepoだけで実行できます。firmware検証にはbackendが必要です。

```sh
git clone https://github.com/FuyukiYoneyama/picocalc_emu.git
cd picocalc_emu
python3 tools/picocalc.py verify
git clone --recursive https://github.com/FuyukiYoneyama/picoem-picocalc.git ../picoem-picocalc
```

必要条件はPython 3.9以降です。RP2040のBINを再ビルドする場合だけPico SDKを用意し、
`PICO_SDK_PATH`を設定します。Rust backendを変更する場合は、repositoryが要求するstable toolchainと
`Cargo.lock`を使い、`--locked`を付けます。

外部アプリを再ビルドしない新規開発では、`picocalc_emu_ext`、PicoTetris、PicoEdit、speaker校正
workspaceは不要です。既存targetのsourceから再生成したり、過去の実機相関を再現する場合だけ、
[`docs/EXTERNAL_WORKSPACE.md`](docs/EXTERNAL_WORKSPACE.md)の入力を取得します。

参照repoを厳密に取得する必要がある場合は、次を使います。取得先は新規ディレクトリにし、既存の
共有workspaceを上書きしません。

```sh
python3 tools/picocalc.py fetch-references --output /absolute/path/to/references
python3 tools/picocalc.py verify --references --strict-commit \
  --reference-root /absolute/path/to/references
```

参照repoが無い環境で`--references --strict-commit`が失敗するのは、入力不足を安全側に判定した結果です。
runtimeの故障と解釈してコードを変更しません。

## 4. ローカル品質ゲート

GitHub Actionsは通常の開発・debug・試行錯誤には使いません。まず変更対象に応じた最小のローカル検査を行い、
最後に関連ゲートをまとめて実行します。

### `picocalc_emu`の変更

```sh
python3 tools/picocalc.py verify
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

### `picoem-picocalc`のRust変更

```sh
cd ../picoem-picocalc
cargo test --locked --release -p rp2040-emu -p picocalc-board -p picocalc-harness
cargo fmt -p picocalc-board -p picocalc-harness --check
cargo clippy --locked --release \
  -p picocalc-board -p picocalc-harness --all-targets -- -D warnings
git diff --check
```

### Validated Realtime Preview frontend (VRP-3)

`tools/picocalc_preview.py`は、admitted descriptorのlaunch contractを再検証して
`picocalc-run --preview-api`を子process起動する薄型Tk frontendです。GUIへemulator coreを
再実装したり、registryからmutableなargvを再構成したりしません。PCRPのwire変更は
`docs/validated-realtime-preview/preview-ipc-schema-v1.json`とfixtureをversion更新し、
backend／consumer／negative testを同じ変更単位で更新します。

VRP-3の表示処理（skin、RGB565変換、screenshot）はpresentation専用です。古いframeの描画を
coalesceしてpresentation dropとして数えることは許可しますが、backendが発行したdevice event、
status、UART、cycle、error、report digestを落としたり変更したりしてはいけません。UART consoleはPicoCalc UART0の仮想TX/RX wireであり、host
stdin/stdoutやkeyboard入力と混同しません。F5 resetはsticky UX-invalidを保持し、Ctrl+Rは
admission成功時だけ新childを起動します。`audio=not_streamed`をhost音声再生済みと説明せず、
音声transportはVRP-4へ分離します。

frontend変更の最小ローカルゲートは次です。

```sh
python3 -m unittest -q tests.test_preview_gui
python3 -m unittest -q tests.test_tools
python3 tools/picocalc.py preview-headless --descriptor /absolute/path/to/admitted-descriptor.json
python3 tools/picocalc.py preview-gui --descriptor /absolute/path/to/admitted-descriptor.json --smoke-seconds 2
git diff --check
```

WSLgのwindow確認はCIの代替ではなく、ローカルのpresentation smokeです。skin assetを変更する
場合はEXIF等のmetadataを除去し、由来・許諾・SHA・開口部校正を
`assets/preview/README.md`へ更新します。descriptor、target、validation record、backend
runnerの不変証拠を改変してGUIの都合に合わせてはいけません。

実機相関・target更新が無いdocs-only変更でfirmwareを長時間実行する必要はありません。
逆にdevice model、runner、BSP、schema、target contractを変更した場合は、関連unit testだけで済ませず、
既存の受入targetを固定backendで再実行します。CIの結果をローカル検証の代わりにしません。

## 5. 変更から受入までの標準手順

1. `git status --short`と現在文書、`capability.json`、対象targetを読む。
2. 変更の責任repoと、既定profileを変えるのかopt-in profileを追加するのかを決める。
3. 最小のsource／unit test／fixture変更を行う。履歴証拠や既存targetを上書きしない。
4. `verify`、unit test、必要ならbackendのfmt／clippy／testをローカルで実行する。
5. firmwareの挙動が変わるときは、clean backend、固定BIN、scenario、report、UART、framebuffer、SHAを確認する。
6. 既存targetと異なるsource、backend、profile、fixture、acceptanceを使う場合は、既存IDを編集せず新しいtarget revision、validation、evidenceを追加する。
7. 同一UF2を実機へ渡す必要がある場合だけ、人間向けの実機手順を作り、emulator結果とhardware evidenceを分離して保存する。
8. `IMPLEMENTATION_STATUS.md`、`MILESTONES.md`、READMEなど現行文書とmachine-readable capabilityを更新する。
9. `git diff --check`、リンク、JSON、`git status --short`、一時出力の掃除を再確認してからcommitする。

targetの正式な判定は、単にrunnerがexit 0になったことではありません。targetが固定したBIN、backend、
device options、scenario、stop reason、UART、report checks、sidecar checksをすべて満たす必要があります。
契約の詳細は[`docs/VERSIONED_VALIDATION.md`](docs/VERSIONED_VALIDATION.md)を正典とします。

新しい機能を始める場合は、最初に目的、対象repo、既定経路への影響、受入条件、ローカル検証、
実機操作、CI予算を`docs/`直下の計画書へ書きます。作業中の計画は`docs/`直下とREADME／MILESTONESから
参照できる状態に保ち、完了後にだけ`docs/history/`へ移して完了証拠とリンクを残します。`history/`に
未完了の計画を置いて、次のAIから見えなくしてはいけません。

新規アプリの最小ループは次です。

```sh
python3 tools/picocalc.py new MyApp --output ../MyApp
# repository host-model smoke (the generated firmware is checked below)
python3 tools/picocalc.py test --mode host
export PICO_SDK_PATH=/absolute/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
python3 tools/picocalc.py verify-project --project ../MyApp
```

firmwareを使う場合は、target registryに既にある固定BIN／scenarioなら登録targetを指定します。
まだ登録していないBINの直接実行は診断であり、正式な受入判定ではありません。

## 6. I2C optional moduleを追加する場合

I2C-EXTは個人hardware向けの任意接続点です。DS3231／AT24C32／AHT20／BMP280は、profileを指定したrunに
だけattachされ、profileを省略した標準runの挙動を変えません。実装・受入の正典は
[`docs/I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md`](docs/I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)です。

新しいmoduleを追加するときは次の順序を守ります。

1. 実hardware sourceとwire protocolを固定し、既存moduleの推測コピーをしない。
2. `picoem-picocalc`のexternal-device接続点、address routing、data-NACK、STOP、RESTART、virtual-timeの
   unit testを追加する。
3. profile／fixture／sidecar schemaとCLIをopt-inで追加する。default device構成へ入れない。
4. unknown address、duplicate address、protocol error、profileなしのnegative testを追加する。
5. firmware backendで同一BINを複数回実行し、report・sidecar・UART・framebufferを比較する。
6. 同一UF2を実機で相関し、versioned validationを作成する。
7. その範囲だけを`capability.json`へ追加する。実機相関前に「supported」へ昇格しない。

`RTC/`の一次sourceや個人hardwareの仕様を、emulatorが通るように改変してはいけません。新しい利用者が
独自hardwareを追加できるよう、child modelと接続stubを独立させ、profileなしの既定経路を保ちます。

## 7. SD／flash／UF2の境界

標準ツールは`tools/picocalc.py sd pack/extract`と`uf2 inspect/assemble`です。firmware runでは
`--sd-dir`が起動時に決定的なFAT32 snapshotを作り、run中のlive directory mountはしません。
`--sd-image-out`でcopy-on-write結果をexportし、必要な場合だけ`sd extract`でhost directoryへ戻します。

SD-GEN-1の`sd-multi-block`はbounded capabilityであり、任意のSDカード機能全般を意味しません。
UF2Loader U6も固定source／artifactの限定end-to-endです。USB BOOTSEL/MSC、任意loader fork、全UF2 familyを
対応済みと書きません。範囲を広げる場合は、観測したtrace、negative mutation、代表アプリ回帰を先に追加します。

## 8. AIが迷ったときの停止条件

- 文書とsourceの状態が違う場合、推測で埋めず、source・registry・evidenceを読み直して止まる。
- profile、target、backend、fixtureが曖昧なまま「既定値」で進めない。
- dirty backend、未固定BIN、未記録の実機結果を正式証拠として扱わない。
- CIをデバッグ目的で起動しない。push、tag、release、実機書き込みは、依頼範囲と必要性を確認する。
- 一時worktree、build、ログ、外部workspaceを作ったら、用途終了後に所有repoまたは`picocalc_emu_ext`へ
  移すか削除し、共有workspace直下に放置しない。

作業終了時の最小報告は、変更したrepo、commit、ローカルコマンドと結果、未解決の入力不足、
CI／push／実機操作を行ったかどうかです。これで、次のAIは過去の経緯を全件読むことなく、現在の
契約に沿って安全に作業を再開できます。
