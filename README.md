# PicoCalc Verified BSP & Emulator Development Kit

[![CI](https://github.com/FuyukiYoneyama/picocalc_emu/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/FuyukiYoneyama/picocalc_emu/actions/workflows/ci.yml)

PicoCalc向けソフトをAIと開発するとき、LCD・SD・キーボードの初期化を毎回
作り直さないための開発基盤です。

現在は **Milestone 0: Canonical BSP** です。実機動作済みプロジェクトから
抽出したBSP、アプリテンプレート、プロジェクト生成器、証拠台帳、検証ツールを
利用できます。PC上でPicoCalcファームウェアを実行するエミュレーターは
まだ実装されていません。

## 現在できること

- 実機で動作したLCD・キーボード・SD/FatFS実装を固定して再利用する
- AIの通常の変更範囲を生成プロジェクトの`app/`へ限定する
- LCD初期化とCS分割をhost SPI fakeで実トランザクション検査する
- JSON board profileからC++定数を一方向生成し、差分をCI検査する
- SD、keyboard、audio pinのsource fingerprintを検査する
- SDのmount/write/sync/read/compare/removeスモークテストを実機で実行する
- LCDのsolid fillとRAMRDによるGRAM readback一致検証を実機で実行する
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

生成物は`../MyApp/build/picocalc_app.uf2`です。

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
[PICOCALC][BOOT] bsp=... app=... git=... build=... compile=...
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
| LCD | `uf2loader/common/lcdspi` | SPI1 GP10–15、25 MHz、COLMOD `0x66`、RGB888、MADCTL `0x48` |
| Keyboard | `picocalc-life` | I2C1、GP6/7、400 kHz、address `0x1f`、repeated-start |
| SD/FatFS | `picocalc-life` | SPI0 GP16–19、detect GP22、400 kHz init、12 MHz run |
| Audio evidence | `Picocalc_ment` | GP26/27、48 kHz PWM/DMA、wrap 255 |

通常のアプリ開発では`bsp/`を変更しません。BSP変更にはsource fingerprint更新、
reference evidence照合、実機相関確認が必要です。

## Canonical BSP自身の実機記録

参照プロジェクトの証拠と、抽出後BSP自身の証拠は分離しています。実機検証時は
[hardware-validation](hardware-validation/README.md)のテンプレートへPicoCalc
revision、toolchain、SDカード、UF2 SHA-256、ログ・写真を記録します。

現時点のテンプレートは`pending`であり、BSP 0.2.1の実機成功を主張しません。

## 文書

- [現在の実装状況](docs/IMPLEMENTATION_STATUS.md)
- [Milestones](docs/MILESTONES.md)
- [将来のエミュレーター設計](docs/DESIGN.md)
- [要求仕様](REQUIREMENTS.md)
- [Canonical BSP](bsp/README.md)
- [実機検証台帳](hardware-validation/README.md)

## プロジェクトの位置付け

現時点では「PicoCalcエミュレーター完成品」ではなく、
**PicoCalc向け検証済みBSPスターターキット兼エミュレーター開発基盤**です。
Host device modelを主経路とし、RP2040JSによるfirmware backendは、
同一バイナリ確認が必要な範囲に限定します。
