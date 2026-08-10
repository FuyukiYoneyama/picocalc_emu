# picocalc_emu

PicoCalc向けアプリを、AIや自動試験がPC上で観測・検証できる開発基盤です。
実機で確認済みのCanonical BSP、host backend、RP2040 firmware backend、scenario runner、
headless machine API、同一artifact実機相関の証拠を一つの流れとして管理します。

本リポジトリの対象は、RP2040（Pico 1）を搭載したClockworkPi PicoCalcです。

## 現在の状態

- 現行BSP source: **0.9.0**
- 標準BSP機能の実機相関baseline: **0.8.8**
- 推奨LCD: `pio-rgb565`（PIO0、RGB565、LCD DMAなし）
- SD: **FAT32が既定**、FAT16は明示的な互換profile
- 通常のfirmware回帰backend: OPT1-B promoted commitをtargetごとに固定
- R0〜R6、NEXT-1〜NEXT-4: **完了**
- OPT2／OPT3: 正確性を確認したうえで性能条件未達として終了。候補はrevert済み
- 現在定義済みの作業パッケージ: **すべて完了または正式終了**
- 新しい番号付き作業: **未定義**

正確な状態は[実装状況](docs/IMPLEMENTATION_STATUS.md)、計画の完了表は
[Milestones](docs/MILESTONES.md)、機械可読な対応範囲は
[`capability.json`](firmware-validation/capability.json)を参照してください。

## 最初に読むもの

- 人間向け入口: このREADME
- AIがアプリを作る: [AI_START_HERE.md](AI_START_HERE.md)
- 文書全体の案内: [docs/README.md](docs/README.md)
- 現在できること／できないこと: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- BSPの公開APIと固定ハードウェア契約: [bsp/README.md](bsp/README.md)

過去の経緯、却下実験、詳細記録は[`docs/history/`](docs/history/README.md)へ分離しています。
検証器が読む凍結R/NEXT契約は`docs/`直下に残します。歴史資料や凍結契約の「次は〜」は
当時の判断であり、現在の作業指示ではありません。

## 5分で始める

必要条件はPython 3.9以降です。portable検証とプロジェクト生成にはPico SDKは不要です。

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
- NEXT-2Bの凍結48 kHz DMA-paced digital audio sink契約
- PWM5_CCからの決定的な音量統計、非正規化raw WAV、および「低音量／極端なrail使用」を分ける
  project-level品質契約
- NEXT-3のSD CMD8 CRC negative conformance
- NEXT-4 JSONL headless machine API

限定または未対応:

- Threaded executionを正確性基準として使うこと
- 両coreからの同時device access、core 1 relaunchなど、NEXT-2A外の一般multicore
- 任意codec／sample rate／DMA layoutの音声一般化
- bootromの実行、USB MSC boot
- SDのmulti-block、removal、write-protect、raw image persistence、directory-backed storage
- scenarioのloop／branch、任意report fieldの直接assert
- 実機の見え方・聞こえ方・物理操作品質

対応範囲を推測で広げず、[`capability.json`](firmware-validation/capability.json)の
具体的なtargetとlimitationを確認してください。

## リポジトリ構成

- `picocalc_emu`: Canonical BSP、CLI、target registry、scenario、証拠、文書
- `picoem-picocalc`: RP2040/PicoCalc firmware backendとmachine API
- `picotetris`: 正式回帰・実機相関に使うアプリ

backend sourceを本リポジトリへコピーせず、targetごとに正確なcommitを固定します。

## CIについて

検証の主体はローカル環境です。GitHub Actionsを通常の開発・デバッグ・試行錯誤に使いません。
workflowの追加・変更、pushによるCI発生、re-runは、必要性と使用量を確認してから行います。

## ライセンス

本リポジトリのコードは各ファイルと[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)の
記載に従います。派生backendは独立リポジトリで`MIT OR Apache-2.0`を維持します。
