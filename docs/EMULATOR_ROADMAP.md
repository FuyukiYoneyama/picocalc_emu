# PicoCalc emulator implementation roadmap

## 1. 目的

`picocalc_emu`の次の開発目標は、ClockworkPi PicoCalcリポジトリにある
`Code/picocalc_helloworld`を、ファームウェア側へエミュレーター専用の変更を加えず、
Rust製`picoem-picocalc`の`ExecutionModel::Serial`上で実行することである。

単にRP2040の命令を実行できたことやLCDへ何かが表示されたことだけを「動作」とは
判定しない。最初の可視化到達点と、公式サンプル全体の合格を分けて管理する。

`picocalc_helloworld`の対象ソース、ビルド設定、Pico SDK、toolchain、ELF/BINの
SHA-256、`picoem-picocalc`のcommitを実行結果へ記録する。調査時点で対象ディレクトリに
ローカル変更はなく、このディレクトリを最後に変更したPicoCalc側commitは
`e403bc04d8f1f1ee6617bf1484250731db319fa3`である。実装開始時には、実際にビルドへ
使用するリポジトリ全体のcommitを改めて固定する。

## 2. 対象ファームウェアの契約

`picocalc_helloworld`は一つのアプリケーション内で、次を順に使用する。

| 機能 | 公式サンプルの使用条件 |
|---|---|
| system clock | 133 MHz |
| UART | UART0、115200、8-N-1、USB stdioなし |
| LCD | SPI1、GP10〜15、25 MHz書き込み、`COLMOD=0x66`、320×320、RGB666を3 bytes/pixelで転送 |
| keyboard等 | I2C1、GP6/7、10 kHz、address `0x1f` |
| PSRAM | 8 MiB、PIO1、GP20/21/2/3、DMAを含む8/16/32/128-bit全域試験 |
| LED | GP25 |
| PWM | GP26/27を初期化するが、`main()`は音声データの再生を開始しない |
| SD | 使用しない |
| core1 | libraryはlinkするが、`main()`から起動しない |

したがって、この最初の対象ではSDカード、実音声出力、core1を先に実装しない。
対応していない周辺機能を成功として無視せず、対象ファームウェアが実際に使用した機能を
段階ごとのcapabilityと受入条件にする。

## 3. 合格段階

### HELLO-VISIBLE: 最初の可視化成功

公式ソースから生成した無改変のELF/BINを起動し、次を満たす。

1. Flash/XIPから`main()`へ到達する。
2. UART0ログを取得できる。
3. clock、GPIO、SPI1、I2C1の初期化で未対応MMIO、Bus fault、panicを起こさない。
4. LCDのRESET、CS、DCとSPI1転送を外部LCD modelへ渡す。
5. LCD初期化、画面消去、`Hello World PicoCalc`描画を解釈する。
6. 320×320 framebufferをPNGまたはhashとして決定的に取得する。
7. 同一入力を繰り返したとき、UART、framebuffer、停止理由が一致する。

HELLO-VISIBLEは最初の可視化到達点であり、`picocalc_helloworld`全体の合格ではない。
ファームウェアへテスト専用の早期returnやエミュレーター判定を追加せず、runner側の
framebuffer条件、symbol/PC、UART、cycle timeoutで到達点を判定する。

### HELLO-FULL: `picocalc_helloworld`完全合格

HELLO-VISIBLEと同じ無改変成果物を継続実行し、次を満たす。

1. PIO1、DMA、GP20/21/2/3へ8 MiB PSRAM modelを接続する。
2. サンプルに含まれる8/16/32/128-bitの全域write/read試験を省略せず完走する。
3. UARTまたはLCD上のPSRAM完了結果を取得し、不一致が0である。
4. I2C address `0x1f`のkeyboard controller modelでbatteryとbacklight registerを扱う。
5. シナリオから投入したキーがFIFOを通り、LCDへechoされる。
6. PWM初期化を観測できる。サンプルが再生を開始しないため、可聴音は要求しない。
7. 未対応MMIO、Bus fault、panic、黙ったperipheral dropがない。
8. UART log、framebuffer、キー結果、PSRAM結果、backend/source commit、成果物SHA-256を
   構造化artifactへ保存し、複数回実行で同一結果を得る。

HELLO-FULLを満たした時点で初めて、「公式`picocalc_helloworld`がエミュレーター上で動く」と
判定する。

## 4. 実装順序

### Gate 0: 基準の固定

- PicoCalc source commit、Pico SDK、toolchain、CMake optionを固定する。
- 無改変のELF/BINをビルドし、SHA-256、map、主要symbolを記録する。
- `picoem-picocalc`の継承済みSerial testを基準化する。

### Gate 1: headless firmware runner

- bootromとBINをロードし、Pico SDK imageをFlash offset `0x100`からdirect bootする。
- cycle上限、UART capture、PC、例外、未対応MMIO、終了理由を取得する。
- 最初は既知の小さいPico SDK firmwareでrunnerを検証し、その後
  `picocalc_helloworld`が`main()`とUART初期化へ到達することを確認する。

現在の対話TUIだけを受入runnerとして使用しない。bootromが未実装のSSI/QSPI経路から
UF2待ちへ進む状態と、対象ファームウェアを実行できた状態を混同しない。

### Gate 2: SPI1 LCD vertical slice

- RP2040側SPIへ外部device transaction interfaceを追加する。
- PicoCalc board adapterでSPI1とGP13/14/15のCS/DC/RESETをLCD modelへ接続する。
- ILI9488/ST7365P互換の対象command subsetとして、少なくともreset、sleep/display state、
  MADCTL、COLMOD、CASET、RASET、RAMWRを実装する。
- 3-byte RGB666 wire dataをdecodeし、共通のRGB565 framebufferへ正規化する。
- HELLO-VISIBLEの画面、UART、決定性を検収する。

### Gate 3: PIO1/DMA PSRAM

- 公式サンプルのPIO program、pin、DMA transactionをそのまま通す。
- まず正確さをSerial modelで確立し、全域試験のhost実行時間を計測する。
- 高速化が必要な場合も、ファームウェアの試験範囲を減らして合格扱いにせず、
  transactionと結果が等価と検証できるbackend側の最適化だけを追加する。

### Gate 4: I2C keyboard controller

- 固定ACKや固定`0xff`応答ではなく、外部I2C device interfaceを用意する。
- address `0x1f`のFIFO、battery、backlight registerを実装する。
- シナリオ入力をFIFOへ投入し、ファームウェアのLCD echoまで検証する。

### Gate 5: full application acceptance

- HELLO-FULLの全条件を一つのscenarioで実行する。
- UART、PNG、trace、PSRAM、keyboard、capability、commit、SHA-256を保存する。
- 少なくとも3回連続で決定的に合格することを確認する。

### Gate 6: `picocalc_emu` integration

- `picoem-picocalc`をソースコピーせず、検証済みcommitで接続する。
- runnerとboard modelを`picocalc_emu`のscenario/artifact interfaceへ接続する。
- 公開版がprivate dependencyを要求しないという公開条件を維持する。

### Gate 7: Canonical BSP B

`picocalc_helloworld`合格後、Canonical BSPの推奨デフォルトBを対象にする。

- PIO0 blocking
- RGB565、2 bytes/pixel
- LCD DMA OFF
- 320×320 framebuffer
- GRAM readbackを含む既存BSP診断

AとBは別々のbus adapterとして実装し、転送電文を統合しない。LCD controller stateと
framebufferは共有できるが、AのSPI1/RGB666とBのPIO0/RGB565を同じ転送処理へ
押し込まない。

## 5. A/BとBSP既定値の関係

`picocalc_helloworld`を最初に選ぶのは、実在する公式ファームウェアを端から端まで動かす
最初の観測可能な目標に適しているためである。このサンプルはLCD Aに相当する。

これは、Canonical BSPの推奨表示デフォルトをBからAへ変更するという意味ではない。

- 最初のFirmware縦断試験: A、SPI1、RGB666 3-byte、`picocalc_helloworld`
- Canonical BSP推奨デフォルト: B、PIO0、RGB565 2-byte、LCD DMA OFF
- A合格後の次のFirmware conformance: B、Canonical BSP診断

## 6. 実装境界

- `picoem-picocalc`: RP2040命令・周辺機能、direct boot、外部SPI/I2C device hook、
  Serial correctness、低レベルtraceを担当する。
- PicoCalc board/device layer: pin配線、LCD、keyboard controller、PSRAM等の
  PicoCalc固有モデルを担当し、汎用RP2040 coreへPicoCalc条件を埋め込まない。
- `picocalc_emu`: scenario実行、入力、UART/PNG/JSON等のartifact収集、比較、利用者向け
  interfaceを担当する。
- `rp2040js`: 周辺機能の挙動、テスト構成、実装方法の比較参考に限定する。

配置の詳細は最初の実装タスクで確定してよいが、この責任境界は維持する。

## 7. Sol / Luna運用

各Gateについて、Solが対象firmware、受入条件、変更可能範囲、禁止事項、検証方法を
先に定義する。Lunaはrunner、SPI hook、LCD model、PSRAM、I2C model、定型テスト等の
境界を限定した実装を一件ずつ行う。

Solは差分と一次資料を照合し、独立テストを実行してから受け入れる。各Gateは合格後に
独立したcommitとして残し、途中の資産を破棄しない。Lunaの自己判定、画面だけの観察、
一度だけの成功を、Gate合格やプロジェクト完了の代わりにしない。
