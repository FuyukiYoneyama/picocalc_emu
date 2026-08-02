# PicoCalc Verified BSP & Emulator Development Kit

[![CI](https://github.com/FuyukiYoneyama/picocalc_emu/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/FuyukiYoneyama/picocalc_emu/actions/workflows/ci.yml)

PicoCalc向けソフトをAIと開発するとき、LCD・SD・キーボード・音声・PSRAMの
初期化を毎回作り直さないための開発基盤です。

現在は **Canonical BSP 0.8.2** です。実機動作済みプロジェクトから
抽出したBSP、アプリテンプレート、プロジェクト生成器、証拠台帳、検証ツールを
利用できます。PC上でPicoCalcファームウェアを実行するエミュレーターは
まだ実装されていません。

AIがアプリを作る場合は、まず [AI向け開始手順](AI_START_HERE.md) を読みます。
本書は全体説明、`AI_START_HERE.md`は変更範囲・A/B選択・ログ判定を含む正規手順です。

## 現在できること

- 実機で動作したLCD・キーボード・SD/FatFS実装を固定して再利用する
- AIの通常の変更範囲を生成プロジェクトの`app/`へ限定する
- LCD初期化とCS分割をhost SPI fakeで実トランザクション検査する
- JSON board profileからC++定数を一方向生成し、差分をCI検査する
- SD、keyboard、audio pinのsource fingerprintを検査する
- SDのmount/write/sync/read/compare/removeスモークテストを実機で実行する
- LCDのsolid fillとRAMRDによるGRAM readback一致検証を実機で実行する
- Picocalc_ment実績ベースの48 kHz PWM/DMA音声ストリームと固定サイン参照試験を提供する
- PicoCalc V2の8 MiB PSRAMをPIO1で初期化し、read/write APIと範囲管理付きBufferを提供する
- LCD・キーボード・SD・PSRAM・音声を個別にコピーできる最小例を提供する
- 基準プロジェクトのcommitと証拠ファイルSHA-256を完全照合する
- Canonical BSP自身の実機結果を構造化台帳へ記録する
- RP2040用ELF/BIN/UF2を生成する

## 現在できないこと

- PC上でUF2/ELFを実行する
- LCD framebufferをPNGとして取得する
- キーシナリオを再生する
- 仮想SDカードやSPI/I2C故障を注入する
- host合格と実機結果の相関を自動集計する

これらは[Milestones](docs/MILESTONES.md)に従って段階的に実装します。

## Firmware backendの開発方針

RP2040の同一ファームウェアをPC上で実行するFirmware backendには、
[`FuyukiYoneyama/picoem-picocalc`](https://github.com/FuyukiYoneyama/picoem-picocalc)を
第一候補として使用します。これは`0x4D44/picoem`の履歴と
`MIT OR Apache-2.0`ライセンスを維持した独立派生リポジトリです。

`picoem-picocalc`は`picocalc_emu`へソースをコピーせず別リポジトリで保守し、
正確なcommitを固定して利用します。初期段階では単一ホストスレッドの
`ExecutionModel::Serial`を正しさの基準とし、PIO0 LCD、I2C1 keyboard、SPI0 SD、
PIO1 PSRAM、PWM/DMA audio、multicoreを段階的に接続します。

Firmware backendは高速なHost device modelの代替ではありません。通常のUI・入力・
ファイル処理はHost backendで検証し、同一バイナリやRP2040固有動作の確認が必要な場合に
Firmware backendを使用します。詳細は
[主Firmware backend方針](docs/FIRMWARE_BACKEND.md)を参照してください。

## 30秒で試す

必要条件はPython 3.8以降とC++17 host compilerです。clone単体で動くportable
検証にはPico SDKは不要です。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
```

生成後、通常編集するファイルは`../MyApp/app/main.cpp`です。

ビルドにはPico SDKを明示します。

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
```

生成物は`../MyApp/build/picocalc_app.uf2`です。引数を省略した推奨表示デフォルトは
`pio-rgb565`（RGB565、PIO blocking、LCD DMAなし）です。

LCDは実績のある二種類を別BSPとして選択できます。ファイル名はどちらも同じです。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
python3 tools/picocalc.py build --project ../MyApp --lcd-variant hwspi-rgb888
```

前者は推奨デフォルトのPIO0/RGB565、後者は互換・診断用のSPI1/
`COLMOD=0x66`です。AのLCDバスはRGB666をR/G/B各1バイトの3-byte containerで送るため、
既存variant名は`hwspi-rgb888`のまま維持します。選択した版はUF2の名前ではなく、
起動ログ先頭行の`variant`とソースコミットで識別します。

PSRAMとLCDの共存クロックを実機で測る場合は、標準UF2名のまま専用モードを
ビルドします。B（PIO/RGB565）でLCDを動かしながら、PSRAMの候補clkdivを全て
検証し、ログの`[PICOCALC][PSRAM][COEX]`を比較します。

```sh
python3 tools/picocalc.py build --project ../MyApp \
  --lcd-variant pio-rgb565 --psram-lcd-coexist-test
```

このモードの起動ログ先頭は`app=0.8.2-b-pio-rgb565-psram-lcd-coexist`です。

### UF2と版管理の運用規約

PicoCalcではUF2をSDカードへコピーして使うため、同じプロジェクト内でUF2の
ファイル名を変更しない。生成物の名前は常に`build/picocalc_app.uf2`とし、
検証版・分岐版でもこの名前を維持する。UF2自体はリポジトリやプロジェクトの
成果物として保存せず、必要なときに対象コミットから同じ名前で再生成する。

版の識別はファイル名ではなく、次の組み合わせで行う。

- 対象ブランチとソースコミット（`git rev-parse HEAD`）
- BSP版番号
- アプリ版番号またはビルドサブコメント（例：`0.2.1-sd-validation`）
- UF2のSHA-256

起動ログの1行目は必ず次の`[PICOCALC][BOOT]`行とし、BSP版、ソースコミット、
ビルド時刻、コンパイル時刻を出力する。実機検証ではこの1行を読んでから、画面・
SD・キーボードの動作を判定する。特別な検証を行う場合は版番号またはビルド
サブコメントをソースへ反映してコミットし、そのコミットからUF2を作る。

`tools/picocalc.py build`はビルド開始時刻を毎回UTCでUF2へ埋め込み、生成したUF2の
SHA-256をプロジェクト直下の`.picocalc-build-history.json`へ記録します。同じBSP版と
アプリ版で過去に成功したビルドがある場合は警告しますが、再ビルドは禁止しません。
同じ版を意図的に使う場合はそのまま続行できます。新しいリリースや実機検証対象を
区別する場合だけ、テンプレートの版番号またはビルドサブコメントを更新し、先に
コミットしてください。

ビルドログには次の識別情報が出ます。

```text
[PICOCALC][BOOT] bsp=... app=... variant=... git=... build=... compile=...
[PICOCALC][APP] version=... compile=...
```

`build`はビルド開始時刻、`compile`はソースのコンパイル時刻です。UF2を実機へ
書き込む前に、コマンドが出力するSHA-256と実機ログの版・時刻を記録してください。

## 検証レベル

### Portable

cloneしたこのリポジトリだけで実行します。生成board header、LCD
transaction、BSP source fingerprint、実機台帳、テンプレートを検査します。

```sh
python3 tools/picocalc.py verify
```

### Reference evidence

実働プロジェクトをcatalog指定のcommitで用意し、証拠ファイルを完全照合します。
既定ではこのリポジトリの親ディレクトリを検索します。

```sh
python3 tools/picocalc.py verify --references --strict-commit
```

別の配置なら次のように指定できます。

```sh
python3 tools/picocalc.py verify \
  --references \
  --strict-commit \
  --reference-root /path/to/reference-workspace
```

取得元URL、commit、証拠SHA-256は
[reference-projects/catalog.json](reference-projects/catalog.json)にあります。
参照プロジェクトがまだ手元にない場合は、空の出力ディレクトリ名を指定して固定commitを
自動取得できます。

```sh
python3 tools/picocalc.py fetch-references --output /path/to/references
python3 tools/picocalc.py verify \
  --references \
  --strict-commit \
  --reference-root /path/to/references
```

## Canonical hardware contract

| 機能 | 実機基準 | 重要条件 |
|---|---|---|
| LCD A（互換・診断） | `bsp/vendor/lcd_hwspi_rgb888.cpp` | SPI1 GP10–15、25 MHz、COLMOD `0x66`、RGB666を3-byte RGB888 containerで送信、MADCTL `0x48`、window transaction中CS保持 |
| LCD B（推奨デフォルト） | `bsp/vendor/lcd_rgb565_pio.cpp` | PIO0 blocking、LCD DMAなし、clkdiv `2.0`、COLMOD `0x65`、RGB565を2 bytes/pixelで送信、RAMRD時はSIOへ切替 |
| Keyboard | `picocalc-life` | I2C1、GP6/7、400 kHz、address `0x1f`、repeated-start |
| SD/FatFS | `picocalc-life` | SPI0 GP16–19、detect GP22、400 kHz init、12 MHz run |
| Audio evidence | `Picocalc_ment` | GP26/27、48 kHz PWM/DMA、wrap 255、固定サインとPCM ring producer |
| PSRAM | `pico_rescue` | 8 MiB、PIO1、CS20/SCK21/MOSI2/MISO3、24-byte以下のread/write、250 MHz通常候補は2/0→3/0→1.5/1、125 MHz通常候補は1/0→1.5/0→2/0→3/0→4/0 |

通常のアプリ開発では`bsp/`を変更しません。BSP変更にはsource fingerprint更新、
reference evidence照合、実機相関確認が必要です。

## Canonical BSP自身の実機記録

参照プロジェクトの証拠と、抽出後BSP自身の証拠は分離しています。実機検証時は
[hardware-validation](hardware-validation/README.md)のテンプレートへPicoCalc
revision、toolchain、SDカード、UF2 SHA-256、ログ・写真を記録します。

**A（`hwspi-rgb888`）とB（`pio-rgb565`）のLCD転送は、BSP 0.4.0で実機合格しました。**
2026-07-30、Aはcommit `e2d53ad55afa`、Bはcommit `f763b91eae95`のUF2で、既知パターンの
表示とRAMRDによる全色一致（`app_status=pass`）を確認しています。AはさらにSDスモークと
キーボード148イベント（pressed/released各74）も合格しています。記録は
[Aの台帳](hardware-validation/records/bsp-0.4.0-20260730-02.json)と
[Bの台帳](hardware-validation/records/bsp-0.4.0-20260730-01.json)です。

この台帳は過去のA/B分離検証記録であり、Bのキーボードと装置識別情報が未記入のため
`overall_status=pending`を保持しています。最新の標準B（BSP/template 0.8.2、commit
`2360487f70ee`）は、別途取得した実機ログでLCD/GRAM readback、SD、キーボード、
LCD検証後の音声停止まで確認済みです。実機では一度に一方だけを
`build/picocalc_app.uf2`へ生成して検証します。UF2は保存せず、各ソースコミットから再生成します。

## 変更履歴の要点（過去の経緯。現在の利用手順ではない）

BSP 0.6.0では、動作済みプロジェクトを先にコピーした参照経路と、AIが利用する
汎用経路を分離しました。`PICOCALC_AUDIO_REFERENCE_TONE=ON`（既定値）は
`Picocalc_ment`の固定サイン、`OFF`はPCM stream APIを使います。PSRAMには
`picocalc::psram::Buffer`を追加しました。いずれもソースとA/Bのビルドを確認し、
この版の実機合否は最後にA/Bを個別に確認します。

BSP 0.7.0では、アプリ／LCDラッパーの標準画素形式をRGB565と明記し、引数なしの
推奨表示デフォルトをB（`pio-rgb565`、PIO blocking、DMA OFF）へ変更しました。
A（`hwspi-rgb888`）は公式互換・bring-up・診断経路として削除せず、明示指定で利用できます。

BSP 0.8.0では、BのLCD更新とPSRAM PIO1アクセスを交互に実行する共存クロック
検証モードを追加しました。LCD DMAは引き続き使用せず、PSRAM側はPIO＋DMA
blocking APIを使用します。

BSP 0.8.1では、83.3 MHz候補が通常スモーク起動で1 byte不一致になった実機結果を
反映し、250 MHz通常起動の第一候補を62.5 MHz（`clkdiv=2.0/fudge=false`）へ変更しました。
83.3 MHzは共存検証で合格した候補としてフォールバックに残します。

BSP 0.4.0では、B（`pio-rgb565`）の転送処理を書き写すのをやめ、実機動作が記録されている
`general/lcd/src/lcd_rgb565_pio.cpp`の**無改変コピー**を`bsp/vendor/`へ置いて呼ぶだけに
しました。`bsp/src/display_pio_rgb565.cpp`は`game/pico_skyace`と同じ呼び出し粒度
（160×160のウィンドウごとに`set_window`1回、画素は160ピクセル単位）に徹する薄い
アダプタです。`verify`は`vendor-lcd-pio-unmodified`でコピーのSHA-256を照合し、
アダプタ側に転送処理が戻っていないことも検査します。経緯は
[LCD調査記録](docs/LCD_INVESTIGATION_20260729.md)にあります。

RAMRDはこの実機で正常に動作します（`life`のスクリーンショット取得ビルドが同じ手順で
正しい画像を出力しています）。BのRAMRDは`life`の手順をそのまま使い、読み値が期待と
違う場合はパネルではなく書き込み経路を疑います。

## 文書

- [現在の実装状況](docs/IMPLEMENTATION_STATUS.md)
- [Milestones](docs/MILESTONES.md)
- [Firmware backend開発方針](docs/FIRMWARE_BACKEND.md)
- [将来のエミュレーター設計](docs/DESIGN.md)
- [要求仕様](REQUIREMENTS.md)
- [Canonical BSP](bsp/README.md)
- [実機検証台帳](hardware-validation/README.md)

## プロジェクトの位置付け

現時点では「PicoCalcエミュレーター完成品」ではなく、
**PicoCalc向け検証済みBSPスターターキット兼エミュレーター開発基盤**です。
現在使える主経路はRP2040実機向けBSP/templateです。将来のPC実行経路は、
高速なHost device modelと、`picoem-picocalc`を利用するRP2040 Firmware backendの
二本立てで開発します。