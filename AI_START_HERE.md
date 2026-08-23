# AI向け開始手順

通常のアプリ生成・ビルド・検証を行うAIは、まずリポジトリ直下の
[`USER_GUIDE/README.md`](USER_GUIDE/README.md)を読みます。この文書は、監督・分担・実機依頼などの
高度な運用が必要な場合に追加で読むものです。過去の調査記録や完了済みの
R/OPT/NEXT文書は、この現在手順を上書きしません。

## 最上位原則

> 推測でハードウェア層を再実装しない。動作実績のあるBSP APIを、実績のある条件で使う。

実機操作は人間が行います。AIの推測が外れるたびに、UF2転送、起動、キー操作、写真、
UART回収の往復が発生します。まずhost／firmware backendで観測し、人間に依頼する操作を
最後の必要最小限へ絞ってください。

## 現在地

- Canonical BSP source current: **0.9.0**
- 標準機能の実機相関baseline: **0.8.8**
- 推奨LCD: `pio-rgb565`
- SD: FAT32既定、FAT16明示
- R0〜R6、NEXT-1〜NEXT-4: 完了
- OPT1-B: promoted
- OPT2／OPT3: 性能gate不合格として終了、候補はrevert済み
- 現行計画の番号付き作業: すべて完了または正式終了
- UF2Loader U0〜U6、M-NESCO拡張受入、SD-GEN-1 P0〜P5: 完了
- SD-GEN-1 P5: boundedな`sd-multi-block` capabilityをversioned validationとして受入
- OPT4 micro-opt bank: 現行mainのcycle差によりhold。promoted targetはOPT1-Bのまま
- I2C-EXT: E0〜E3完了。DS3231/AT24C32/AHT20/BMP280 modelと、任意の picocalc-rtc-v1／picocalc-rtc-env-v1 profile接続を実装。E4詳細sidecar/target接続、実機相関、capability昇格は未実施

UF2LoaderのSD／flash統合、M-NESCO拡張、SD-GEN-1汎用SD protocolは完了しています。
現在の境界と証拠は[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)、
[`docs/MILESTONES.md`](docs/MILESTONES.md)、
[`firmware-validation/capability.json`](firmware-validation/capability.json)を正典とします。
統合計画の全履歴と最終状態は
[`docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)
にあります。これらの完了済み計画を再開せず、次の機能作業はI2C-EXTのE4/E5/E6から継続します。

現在の正式計画は、共有I2C1上の外付けRTC/EEPROM/環境sensorを任意profileとして扱う
[`I2C-EXT`](docs/I2C_EXTERNAL_MODULE_EMULATION_PLAN_20260823.md)です。実module/profileの
E0のsource/provenanceとwire contract固定、E1のcontroller/mux/shared virtual-time基盤、
DS3231/AT24C32/AHT20/BMP280 model core、picocalc-rtc-v1／picocalc-rtc-env-v1 profileのfixture検証・I2C1 attachは完了しています。
E4の詳細sidecar/target接続、実機相関、capability昇格は未実施です。RTC directoryの
sourceを直接変更してemulatorの動作へ合わせてはいけません。E0の固定証拠は
[`firmware-validation/evidence/i2c-ext-e0-20260823-01/`](firmware-validation/evidence/i2c-ext-e0-20260823-01/)
を参照します。

NEXT-2Aで固定したSerial multicore範囲と、NEXT-2Bで固定した48 kHz DMA-paced audio範囲は
対応済みです。ただしThreaded、両core同時device access、core relaunch、任意の音声構成は
対応済みとはみなしません。正確な境界は
[`firmware-validation/capability.json`](firmware-validation/capability.json)を確認します。

音声を出すアプリは、転送count/hashだけで完成扱いにしません。PicoCalcの物理ボリュームを前提に
デジタルレンジを十分使い、短い飽和は許容しつつ、小さすぎる区間音量と極端なrail張り付きを
[`音量品質手順`](docs/AUDIO_LEVEL_QUALITY.md)で検査します。

## 監督と分担

Solが要件、設計、受入、統合、commit／push、CI・実機結果の最終判断を担当します。
LunaはSolが限定した明確・反復的・大量の作業を行い、差分と検証結果を提出します。
workerの報告はSolの検収を置き換えません。詳細は
[開発運用](docs/DEVELOPMENT_WORKFLOW.md)を参照してください。

指定されたworker構成が使えない場合、別構成で強行せず、原因を特定してから再開します。

## 通常のアプリ開発

このリポジトリは、生成物のBSP由来を固定するためGit metadataを使います。完全なprovenance検証を
行う場合はGitHubのDownload ZIPではなく`git clone`したcheckoutから開始してください。ZIPでも
portableなコード参照はできますが、`verify-project`は`cannot judge`になります。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
```

通常変更する場所:

```text
../MyApp/app/main.cpp
../MyApp/assets/       # 必要な場合だけ
```

通常変更しない場所:

```text
../MyApp/bsp/
../MyApp/generated/
```

LCD GPIO、初期化列、transfer粒度、SD SPI、keyboard I2C、PSRAM clockを`app/`へコピーして
書き直してはいけません。BSPの公開APIを使用します。

生成物:

```text
../MyApp/build/picocalc_app.bin
../MyApp/build/picocalc_app.uf2
```

## 検証順序

1. アプリ固有のhardware-free unit test
2. `python3 tools/picocalc.py test --mode host`
3. 固定targetによるfirmware scenario
4. report、UART、snapshot、SHAの照合
5. エミュレーターで判定できない項目だけ実機へ依頼

SDのdirectoryをfixtureとして渡す場合は、毎回独自スクリプトを作らず、
`picocalc.py test --mode firmware --sd-dir <directory>`を使います。wrapperが起動時に
決定的FAT32 RAW snapshotを作り、backendの既存`--sd-image`経路へ渡します。変更を保存する場合は
`--sd-image-out`、入力manifestを保存する場合は`--sd-manifest`を追加します。FAT16や手動の
往復が必要な場合だけ[`USER_GUIDE/SD_IMAGES.md`](USER_GUIDE/SD_IMAGES.md)の`sd pack` → runner
`--sd-image`／`--sd-image-out` → `sd extract`を使います。host directoryをrun中にlive mountする
機能ではありません。

Host backendは高速ですがハードウェアモデルではありません。PIO、DMA、I2C、割り込み、
multicore、LCD wire形式を判断するときはfirmware backendを使います。

私的I2C moduleを明示的に付ける場合だけ、picocalc-runへ
--i2c-profile picocalc-rtc-v1 --i2c-report <path>、または環境sensorを含める場合は --i2c-profile picocalc-rtc-env-v1 --i2c-report <path> を渡します。
fixtureを使う場合は --i2c-fixture <fixture.json> も指定します。profileを省略した通常runには
DS3231/AT24C32/AHT20/BMP280は接続されません。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target <target-id> \
  --firmware /absolute/path/to/app.bin \
  --snapshot-dir /tmp/picocalc-snapshots
```

firmware modeでは長時間実行を監視する stderr heartbeat が既定で有効です。複数runを同時に動かす場合は、
runごとに別の出力directoryを用意し、必要なら`--run-id <id>`を指定します。既定のheartbeatを止める
場合だけ`--no-progress`を使います。`finish`の有無を最初に確認し、WSLで外側の終了コードが0に見えても
`finish.exit`とreportを優先してください。詳細は[複数runの運用](docs/CONCURRENT_RUNS.md)を参照します。

登録targetと異なるBIN、scenario、backend、device optionをoverrideして通してはいけません。

## AI実行時の注意

`wsl.exe`経由でシェルを起動する実行環境では、`$?`やパイプ後の終了コードが失われ、常に0として
読めることがある。判定は`$?`ではなく、ツールが出力する`RESULT mode=... status=...`行、または
実行ツール自体が返す`Exit code N`のような表示で行う。

scenario JSONやcommit messageのような複数行contentは、シェルのheredocで組み立てるとクォートが
崩れやすい。ファイルを書き込むツールで生成してからコマンドへ渡す。

低レベルrunnerをheartbeatなしで直接呼ぶ場合、サイクル数の大きいfirmware実行（soak、full検証など）は
完了まで中間出力がない。正規の`picocalc.py test --mode firmware`はheartbeatを既定で出すが、数分以上
かかる実行ではなおバックグラウンドで開始し、`finish`とreportをポーリングで確認する。

## 状態を見て入力する

画面やUARTを待ってから入力する場合は[Scenario runner](docs/SCENARIO_RUNNER.md)を使います。
対話的な長寿命sessionが必要なら[Headless machine API](docs/HEADLESS_MACHINE_API.md)を使います。
machine APIは操作面であり、target registryの合否判定を置き換えません。

## 実機依頼

通常の転送経路はPicoCalcの**uf2loader**です。BOOTSELを使うのは、それでしか検証できない
明示的理由がある場合だけです。

人間へ依頼する前に次を提示します。

- UF2の絶対pathとSHA-256
- 起動時に照合するBSP/app/variant/build
- 操作を一度に一つずつ
- 誤入力、反応しないキー、中断、再起動からの回復方法
- 必要なUARTログ、写真、SDファイル
- 終了条件

タイミング依存の長いキー列や途中写真を当然の前提にしません。機械化できる操作はscenarioへ
移し、人間には最終的な見え方、聞こえ方、物理操作だけを依頼します。

## 版と証拠

UF2を実機へ渡す前にsource commit、BSP/app版、build timestamp、BIN/UF2 SHA-256を固定します。
UF2のファイル名だけで版を識別しません。起動ログの`[PICOCALC][BOOT]`行を先に確認します。

履歴recordは時点証拠です。後から現在値に書き換えず、新しいrevision／validation／recordを
追加します。詳細は[Versioned validation](docs/VERSIONED_VALIDATION.md)を参照してください。

## 文書の入口

- 現在の状態: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)
- 計画の完了表: [docs/MILESTONES.md](docs/MILESTONES.md)
- 文書分類: [docs/README.md](docs/README.md)
- BSP API: [bsp/README.md](bsp/README.md)
- Firmware backend: [docs/FIRMWARE_BACKEND.md](docs/FIRMWARE_BACKEND.md)
- Host backend: [docs/HOST_BACKEND.md](docs/HOST_BACKEND.md)
- Scenario: [docs/SCENARIO_RUNNER.md](docs/SCENARIO_RUNNER.md)
- 複数run heartbeat: [docs/CONCURRENT_RUNS.md](docs/CONCURRENT_RUNS.md)
- Machine API: [docs/HEADLESS_MACHINE_API.md](docs/HEADLESS_MACHINE_API.md)
- 過去の経緯・却下実験: [docs/history/README.md](docs/history/README.md)
