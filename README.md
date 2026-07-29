# PicoCalc Verified BSP & Emulator Development Kit

PicoCalc向けソフトをAIと開発するとき、LCD・SD・キーボードの初期化を毎回
作り直さないための開発基盤です。

現在は **Milestone 0: Canonical BSP** です。実機動作済みプロジェクトから
抽出したBSP、アプリテンプレート、プロジェクト生成器、証拠台帳、検証ツールを
利用できます。PC上でPicoCalcファームウェアを実行するエミュレーターは
まだ実装されていません。

## 現在できること

- 実機で動作したLCD・キーボード・SD/FatFS実装を固定して再利用する
- AIの通常の変更範囲を生成プロジェクトの`app/`へ限定する
- LCD、SD、keyboard、audio pinのsource fingerprintを検査する
- SDのmount/write/sync/read/compare/removeスモークテストを実機で実行する
- 基準プロジェクトのcommitと証拠ファイルSHA-256を完全照合する
- RP2040用ELF/BIN/UF2を生成する

## 現在できないこと

- PC上でUF2/ELFを実行する
- LCD framebufferをPNGとして取得する
- キーシナリオを再生する
- 仮想SDカードやSPI/I2C故障を注入する
- host合格と実機結果の相関を自動集計する

これらは[Milestones](docs/MILESTONES.md)に従って段階的に実装します。

## 30秒で試す

必要条件はPython 3.8以降です。clone単体で動くportable検証にはPico SDKは
不要です。

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

生成物は`../MyApp/build/picocalc_app.uf2`です。

## 検証レベル

### Portable

cloneしたこのリポジトリだけで実行します。構造化board profile、BSP source
fingerprint、テンプレート、メタデータを検査します。

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
参照プロジェクトがまだない場合は、空の出力ディレクトリ名を指定して固定commitを
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
| LCD | `picocalc-life`, `pico_skyace` | GP10–15、COLMOD `0x65`、MADCTL `0x48`、最大160 pixels/CS |
| Keyboard | `picocalc-life` | I2C1、GP6/7、400 kHz、address `0x1f`、repeated-start |
| SD/FatFS | `picocalc-life` | SPI0 GP16–19、detect GP22、400 kHz init、12 MHz run |
| Audio evidence | `Picocalc_ment` | GP26/27、48 kHz PWM/DMA、wrap 255 |

通常のアプリ開発では`bsp/`を変更しません。BSP変更にはsource fingerprint更新、
reference evidence照合、実機相関確認が必要です。

## 文書

- [現在の実装状況](docs/IMPLEMENTATION_STATUS.md)
- [Milestones](docs/MILESTONES.md)
- [将来のエミュレーター設計](docs/DESIGN.md)
- [要求仕様](REQUIREMENTS.md)
- [Canonical BSP](bsp/README.md)

## プロジェクトの位置付け

現時点では「PicoCalcエミュレーター完成品」ではなく、
**PicoCalc向け検証済みBSPスターターキット兼エミュレーター開発基盤**です。
Host device modelを主経路とし、RP2040JSによるfirmware backendは、
同一バイナリ確認が必要な範囲に限定します。
