# 実装状況と利用手順

## 現在利用できるもの（BSP/template MVP 0.4.0、LCD A/Bを独立vendor化）

この段階では「空のプロジェクトから AI にハードウェア初期化を書かせない」ための
土台を実装している。PC 上の完全な RP2040/PicoCalc エミュレーターはまだ未実装で
あり、現在の検証範囲はビルド、既知の実機契約、起動時スモークテストである。

- `bsp/`: 実働プロジェクトを基準にした LCD二系統・キーボード・SD/FatFS BSP。Aはloader-style SPI/RGB888転送を専用vendorドライバへ固定し、BはPIO/RGB565の無改変vendorコピーを使う
- `templates/rp2040-basic/`: BSP を利用する最小アプリと CMake
- `tools/picocalc.py`: 新規プロジェクト生成、ビルド、検証
- `tools/verify_environment.py`: portable fingerprint と基準証拠の段階別検査
- `profiles/picocalc-rp2040.json`: 機械可読なboard contract
- `bsp/include/picocalc/board_generated.h`: profileから生成したC++定数
- `tests/lcd_protocol_test.cpp`: SPI fakeによるLCD transaction検査
- `reference-projects/catalog.json`: 実機成功根拠と SHA-256
- `hardware-validation/`: Canonical BSP自身の実機検証schemaと台帳
- `tests/test_tools.py`: 検証器と生成器の回帰テスト

既存の実働プロジェクトは変更せず、次を Canonical BSP の根拠にしている。

| 機能 | 基準 | 固定した成功条件 |
|---|---|---|
| LCD A | `general/lcd/src/main_hwspi_rgb888_probe.cpp` + `PicoCalc/Code/picocalc_helloworld/lcdspi` | `bsp/vendor/lcd_hwspi_rgb888.cpp`、SPI1 GP10〜15、25 MHz、COLMOD `0x66`、RGB888、CASET/RASET/RAMWRから画素列までCS保持、RAMRDは6 MHz |
| LCD B | `general/lcd` / `pico_skyace` / `life` | 転送は`bsp/vendor/lcd_rgb565_pio.cpp`（無改変コピー、PIO0 blocking、clkdiv `2.0`、COLMOD `0x65`、RGB565）。アダプタ側の契約はウィンドウ160×160以下・画素160ピクセル単位、RAMRDは`life`のキャプチャ手順 |
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

LCD BSPはA/Bを混ぜず、ビルド時に一方を選ぶ。生成物名は常に同じである。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant hwspi-rgb888
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
```

実機試験は同時に二つのUF2を扱わず、一度に一方だけを標準名
`build/picocalc_app.uf2`へ生成する。A（`hwspi-rgb888`）とB（`pio-rgb565`）は
どちらも独立した合格対象であり、Aの結果でBを廃棄しない。各ログ先頭の
`variant`と、LCDの`[PICOCALC][LCD][VERIFY] app_status=pass`および画面写真を
個別に確認する。

生成後に AI が通常変更する場所は `MyApp/app/` だけである。`MyApp/bsp/` は
生成時点の既知動作版を固定したコピーであり、アプリ都合で初期化コードを
作り直さない。

Pico SDK は `--sdk` または `PICO_SDK_PATH` で明示する。picotool は
`--picotool-dir`、`PICOTOOL_DIR`、または `PATH` 上の実行ファイルから探索する。
作者固有の絶対パスには依存しない。

## UF2と実機検証の版管理規約

PicoCalcのUF2はSDカードへコピーして使用するため、プロジェクト内のUF2名は
常に`build/picocalc_app.uf2`で固定する。検証版やブランチ版でもファイル名を
変更せず、UF2そのものは保存しない。

版を区別するときは、対象ブランチのソースコミット、BSP版、アプリ版または
ビルドサブコメント、UF2のSHA-256を記録する。特別な実機試験を行う場合も、
版番号／サブコメントをソースへ反映してコミットしてからUF2を生成する。
これにより、実機ログの先頭行に出る識別情報を使って対象を確定でき、必要なら
そのコミットへ戻って同じ`build/picocalc_app.uf2`を再生成できる。

起動時の最初の機械可読ログは次の形式でなければならない。

```text
[PICOCALC][BOOT] bsp=... app=... variant=... git=... build=... compile=...
```

この1行を実機ログの版判定に使う。UF2ファイル名を版識別に使ってはならない。

## 起動時スモークテスト

生成した `picocalc_app.uf2` は、起動時に次を行う。

1. 選択したBSPの基準クロック（A: 125 MHz、B: 250 MHz）、100 ms安定待ち、PSRAM CS inactive、キーボード、LCDを初期化する（バックライトの明るさは変更しない）
2. LCD を黒・白・赤・緑・青で塗りつぶし、2x2 sampleを`RAMRD (0x2e)`で読み戻して一致比較する
3. LCD に黒・白・RGB の既知パターンを描画し、2x2の書き込み／GRAM readback一致を確認する
4. SD を mount し、`PICOTEST.TXT` を write/sync/close/read/compare する
5. テストファイルを削除する
6. 成功時は画面のステータス領域を緑、失敗時は赤にする
7. キーボード FIFO をポーリングし、キーイベントを UART/USB CDC に記録する

主要ログは次の形式なので、人だけでなく AI も失敗段階を判定できる。

```text
[PICOCALC][LCD][VERIFY] stage=end status=drawn regions=top(0,0,320,24),bottom(0,296,320,24),white(16,48,288,224),inset(20,52,280,216),red(32,72,80,80),green(120,72,80,80),blue(208,72,80,80) colors=top:0x07e0,bottom:0x001f,white:0xffff,inset:0x0000,red:0xf800,green:0x07e0,blue:0x001f
[PICOCALC][LCD][READ] ramrd dummy=0x.. pixels=4 format=rgb888
[PICOCALC][LCD][VERIFY] status=pass pixels=4 mismatches=0
[PICOCALC][LCD][VERIFY] stage=pattern_readback status=pass pixels=4 mismatches=0
[PICOCALC][LCD][VERIFY] app_status=pass
[PICOCALC][SD][SMOKE] stage=begin path=0:/PICOTEST.TXT sequence=mount,write,sync,close_write,read,compare,close_read,remove
[PICOCALC][SD][SMOKE] stage=end status=ok result_stage=ok detail=0
[PICOCALC][SD] component=init status=ok detail=1
[PICOCALC][SMOKE] lcd=ok sd=ok stage=ok detail=0 status_region=green
[PICOCALC][KEY][VERIFY] stage=waiting requirement=multiple_press_release_events
[PICOCALC][KEY][VERIFY] stage=event count=1 state=pressed state_code=1 code=0x.. pressed_count=1 released_count=0
[PICOCALC][VERIFY] stage=ready lcd=ok sd=ok keyboard=waiting
[PICOCALC][READY] keyboard=waiting
```

LCDの`[LCD][VERIFY] app_status=pass`は、塗りつぶしとパターンの書き込み後に
GRAMを`RAMRD`で読み出し、RGB888からRGB565へ戻した値が一致したことを表す。
`[LCD][READ]`にはMISOアイドル、RDDID/RDDST、RAMRDダミー、各pixelの生バイト列を出す。
SD エラーは `mount`, `open_write`, `write`, `sync`, `open_read`, `read`,
`compare`, `remove` のどこで発生したかを出力する。

B（`pio-rgb565`）のRAMRDは`life`のスクリーンショット取得ビルドと同じ手順である。
PIOステートマシンを停止してSCK/MOSI/MISOをSIOへ移し、CS保持で`CASET`/`RASET`/`RAMRD`を
送り、ダミー1バイトの後に2バイト/ピクセルをfallingでサンプルし、ピンをPIOへ戻す。
`life`はこの手順で実機のスクリーンショットを正しく取得しているため、読み値が期待と
異なる場合はRAMRDではなく書き込み経路を疑う。

UF2は従来どおり `build/picocalc_app.uf2` として生成する。LCDの`stage=end`は
既知の色パターン描画呼び出し完了、SDの`result_stage`は失敗箇所、キーの`count`は
実機で取得したイベント数と押下／リリース数を表す。LCDの色・向き・ノイズの有無はログだけでは判定
できないため、画面写真と合わせて記録する。

## 検証済み範囲

- Canonical BSP とテンプレートは `arm-none-eabi-gcc 13.2.1`、
  Pico SDK 2.x 系でコンパイル可能
- `picocalc_app.elf`、`.bin`、`.uf2` の生成を確認済み
- clone単体のportable検証15件が合格
- 基準プロジェクト3件と証拠ファイル13件を含む完全検証26件が合格
- 生成器・検証器・異常系のPython回帰テスト19件が合格
- LCD初期化とCS分割は実行可能なhost transactionテストで検査
- `--json`は入力ファイル破損・不正引数でも構造化された失敗を返す
- GitHub Actionsでportable検証、Pythonテスト、RP2040 template compileを実行

実機で BSP 0.2.0 の LCD/SD/keyboard スモークを確認した。その後LCDを二系統へ分離し、
Bの転送を無改変コピー、Aの転送を専用vendorドライバへ固定した BSP 0.4.0 で、**A/B両方の
LCDが実機表示に成功した**（2026-07-30）。

- A（`hwspi-rgb888`）：commit `e2d53ad55afa`、LCD/SD/keyboard合格。キーボードは148イベント
  （pressed/released各74）。記録は`bsp-0.4.0-20260730-02.json`。
- B（`pio-rgb565`）：commit `f763b91eae95`、LCD/SD合格。記録は
  `bsp-0.4.0-20260730-01.json`。キーボードはこの記録では未試験。

両記録とも基板revisionとSDカード識別情報が未記入のため、台帳の`overall_status`は
`pending`にしている。LCD A/Bの実機合格自体は、各ログの`app_status=pass`、GRAM readback
全色一致、写真で個別に確定している。

## まだ実機確認が必要な点

B（`pio-rgb565`）はLCD/SDに合格したが、キーボードのイベント確認、基板revision、SDカード
識別が未記入である。A（`hwspi-rgb888`）はLCD/SD/keyboardに合格した。装置情報3点だけが
台帳上の未完了項目である。

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
