# 実装状況と利用手順

## 現在利用できるもの（BSP/template MVP 0.1.0）

この段階では「空のプロジェクトから AI にハードウェア初期化を書かせない」ための
土台を実装している。PC 上の完全な RP2040/PicoCalc エミュレーターはまだ未実装で
あり、現在の検証範囲はビルド、既知の実機契約、起動時スモークテストである。

- `bsp/`: 実働プロジェクトを基準にした LCD・キーボード・SD/FatFS BSP
- `templates/rp2040-basic/`: BSP を利用する最小アプリと CMake
- `tools/picocalc.py`: 新規プロジェクト生成、ビルド、検証
- `tools/verify_environment.py`: portable fingerprint と基準証拠の段階別検査
- `profiles/picocalc-rp2040.json`: 機械可読なboard contract
- `reference-projects/catalog.json`: 実機成功根拠と SHA-256
- `tests/test_tools.py`: 検証器と生成器の回帰テスト

既存の実働プロジェクトは変更せず、次を Canonical BSP の根拠にしている。

| 機能 | 基準 | 固定した成功条件 |
|---|---|---|
| LCD | `picocalc-life`, `pico_skyace` | GP10〜15、PIO0、COLMOD `0x65`、MADCTL `0x48`、最大160 pixelごとにCSを解放 |
| Keyboard | `picocalc-life` | I2C1、GP6/7、400 kHz、address `0x1f`、register `0x04`/FIFO `0x09`、repeated-start |
| SD/FatFS | `picocalc-life` | SPI0 GP16〜19、CS GP17、detect GP22、400 kHz初期化、12 MHz運用、CMD0/8/55/ACMD41/58 |
| Audio | `Picocalc_ment` | GP26/27 PWM、48 kHz、wrap 255、DMA timer、128 sample二重buffer、512 sample ring、error diffusion 100% |

## 新規プロジェクト

`picocalc_emu` で次を実行する。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
python3 tools/picocalc.py build --project ../MyApp --sdk /path/to/pico-sdk
```

生成後に AI が通常変更する場所は `MyApp/app/` だけである。`MyApp/bsp/` は
生成時点の既知動作版を固定したコピーであり、アプリ都合で初期化コードを
作り直さない。

Pico SDK は `--sdk` または `PICO_SDK_PATH` で明示する。picotool は
`--picotool-dir`、`PICOTOOL_DIR`、または `PATH` 上の実行ファイルから探索する。
作者固有の絶対パスには依存しない。

## 起動時スモークテスト

生成した `picocalc_app.uf2` は、起動時に次を行う。

1. 250 MHz、PSRAM CS inactive、LCD、キーボードを初期化する
2. LCD に黒・白・RGB の既知パターンを描画する
3. SD を mount し、`PICOTEST.TXT` を write/sync/close/read/compare する
4. テストファイルを削除する
5. 成功時は画面のステータス領域を緑、失敗時は赤にする
6. キーボード FIFO をポーリングし、キーイベントを UART/USB CDC に記録する

主要ログは次の形式なので、人だけでなく AI も失敗段階を判定できる。

```text
[PICOCALC][SD] component=init status=ok detail=1
[PICOCALC][SMOKE] lcd=ok sd=ok stage=ok detail=0
[PICOCALC][READY] keyboard=waiting
```

SD エラーは `mount`, `open_write`, `write`, `sync`, `open_read`, `read`,
`compare`, `remove` のどこで発生したかを出力する。

## 検証済み範囲

- Canonical BSP とテンプレートは `arm-none-eabi-gcc 9.2.1`、
  Pico SDK 2.0.0 でコンパイル済み
- `picocalc_app.elf`、`.bin`、`.uf2` の生成を確認済み
- clone単体のportable検証7件が合格
- 基準プロジェクト3件と証拠ファイル13件を含む完全検証23件が合格
- 生成器・検証器・異常系のPython回帰テスト11件が合格
- GitHub Actionsでportable検証、Pythonテスト、RP2040 template compileを実行

実機で新しい BSP 0.1.0 の LCD/SD/keyboard スモークを確認した時点で、
この BSP 自体を新しい基準実装として記録する。

## まだ実機確認が必要な点

PC ビルド合格は電気的な動作を証明しないため、BSP 0.1.0 の最初の1回は実機確認が
必要である。特に LCD の色・向き、SD カード個体差、USB CDC 初期化待ちを確認する。

また、次の機能は今後のエミュレーター段階である。

- RP2040JS 上での同一 UF2/ELF 実行
- SPI/I2C デバイスモデルと LCD framebuffer/PNG
- FAT イメージを使う仮想 SD と故障注入
- キーシナリオ再生、画面差分、JUnit/JSON 成果物
- PIO/DMA、multicore、PSRAM を使う既存アプリ

音声については `Picocalc_ment` を実機基準として証拠台帳へ登録済みだが、
共通BSPの音声APIとホスト音声モデルはまだ未実装である。実装時には音源合成器
そのものと出力経路を分離し、固定1 kHz診断、ring underrun、sample pacing、
GP26/27 PWM出力を別々に検証する。

したがって現時点の価値は、LCD と SD を毎回 AI が再実装する問題を止めること、
および最初の実機試験で「どこが失敗したか」を一度で観測可能にすることである。
