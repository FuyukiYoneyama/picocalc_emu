# picocalc_emu AI 開発環境 要求仕様

> **文書の役割:** 本書は要求の背景と不変原則を定義します。§7の優先順位は初期計画です。
> 現在の実装状態は[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)、完了した
> 作業パッケージは[`docs/MILESTONES.md`](docs/MILESTONES.md)を優先してください。

> **文書の位置付け:** これは将来のエミュレーターを含む要求仕様です。現在実装済み
> なのは、Canonical BSP、RP2040アプリテンプレート、実機ログ付きスモークテスト、
> portable検証器です。PC上でUF2/ELFを動かす機能はまだ実装されていません。

## 0. 対象機器と目的（一文）

対象機器は [ClockworkPi PicoCalc](https://www.clockworkpi.com/picocalc)
（[ソース](https://github.com/clockworkpi/PicoCalc)）である。Raspberry Pi Pico
シリーズを差し替え可能なメインボードとして搭載し、4インチ 320×320 IPS、I²C 接続の
67 キー QWERTY、SD カード、8 MB PSRAM、PWM スピーカー 2 基を備えた、18650 電池で
駆動するスタンドアロン携帯マイコンである。本仕様の対象は RP2040（Pico 1）構成とする。

**本プロジェクトの目的は、PicoCalc 向けのプログラム開発を AI に依頼したときに、
人間が行う実機検証の回数を最小にし、できれば実機検証なしでプログラムを完成させ
られる開発の枠組み（エミュレーターを含む）を提供することである。**

削減対象は人間の作業である。AI は実機を操作できない。UF2 を SD カードへコピーし、
PicoCalc へ挿し、電源を入れ、画面を見て、写真を撮り、UART ログを回収する工程は
すべて人間が行う。AI が推測を 1 回外すたびに、人間がこの往復を 1 回払う。
以降の要求はすべて、この往復回数を減らすための手段として読むこと。

## 1. 背景

PicoCalc 向けプログラムを AI に開発させる際、すでに LCD 表示や SD カード読み書きに成功している複数の実働プロジェクトを提示しても、新規プロジェクトでは次の問題が繰り返し発生している。

* LCD に何も表示されない
* LCD コントローラー、色形式、回転、座標、SPI 設定が一致しない
* SD カードを認識または mount できない
* SD の初期化クロック、ピン、カード検出、FatFS 設定が一致しない
* 10 回以上の実機デバッグを行っても原因を特定できない
* AI は実機画面、SPI/I²C 通信、SD カード状態を直接観測できず、推測による修正を繰り返す

問題は参照資料の不足だけではない。複数の実働プロジェクトには、異なるドライバのコピー、ピン設定、I²C 速度、ライブラリ、ビルド構成が含まれる。AI がそれらを部分的に組み合わせると、各部分が正しくても全体として動かない構成になり得る。

## 2. 目的

AI が PicoCalc 向けプログラムを、動作確認済みのハードウェア基盤から開始し、PC 上でビルド、起動、画面確認、キー入力、SD 読み書き、失敗原因の確認、修正を反復できる環境を提供する。

反復のうち人間の手を必要とする回数をゼロへ近づけることが最終目標であり、
上記の「PC 上で」はそのための手段である。

目標は次の通りである。

* 新規プロジェクト作成直後から LCD が表示される
* 新規プロジェクト作成直後から SD の mount、read、write、sync が成功する
* AI はアプリケーション実装へ集中し、LCD/SD 初期化を毎回書き直さない
* 失敗時は「動かない」ではなく、正常な実働プロジェクトとの差分が構造化されて返る
* AI が人間を介さずに、自分の変更の合否と失敗箇所を判定できる
* 通常 10 回程度必要な人間の実機検証を、最終確認の 1〜2 回へ削減する
* 最終的には、実機検証なしで完成へ到達できる範囲を機能ごとに拡大する

最後の目標には限界がある。エミュレーターの予測が実機と乖離した機能は、
§3.5 に従って `hardware_required` へ戻す。実機検証ゼロは、精度を犠牲にして
達成してよい目標ではない。

## 3. 最上位原則

### 3.1 動作済み構成から開始する

新規プロジェクトを空のディレクトリから生成しない。必ず実機確認済みの PicoCalc Board Support Package（BSP）、CMake 設定、リンカ設定、起動処理を含むテンプレートから生成する。

### 3.2 実働プロジェクトを正解データにする

実働プロジェクトを単なる参考資料として扱わない。そこからビルド条件、画面、UART ログ、SPI/I²C トレース、SD 操作結果を採取し、golden artifact と conformance test の正解にする。

### 3.3 AI にハードウェア層を再実装させない

通常のアプリ開発では、AI が LCD、SD、キーボードの初期化コードやピン設定を新しく作らない。アプリは安定した公開 API を利用する。

ハードウェア層を変更する場合は通常のアプリ変更と区別し、protocol test と実機相関テストを必須にする。

### 3.4 失敗を観測可能にする

AI に、少なくとも次の情報を機械可読形式で返す。

* 起動状態と停止理由
* LCD 初期化状態、最初のフレーム時刻、スクリーンショット
* SPI コマンド列と golden trace との差分
* SD 初期化の進行状況、失敗したコマンド、クロック、応答
* mount/read/write/sync の各結果
* キーボード I²C 状態
* UART/stdio
* 未対応 MMIO とアクセス元

### 3.5 エミュレーターの予測精度を実機で校正する

エミュレーターで合格したプログラムが実機でも合格することを継続的に確認する。実機との不一致が許容値を超えた機能は、モデルが修正されるまで `hardware_required` とする。

## 4. 必須成果物

### 4.1 Canonical PicoCalc BSP

実働プロジェクトから正常動作する実装を選定し、一つの正式なハードウェア層へ統合する。

```text
picocalc_bsp/
  include/
    picocalc.h
    picocalc_board.h
    picocalc_lcd.h
    picocalc_sd.h
    picocalc_keyboard.h
  src/
    board.c
    lcd_st7365p.c
    sd_card.c
    keyboard_i2c.c
  profiles/
    picocalc_v2_rp2040.h
    picocalc_v2_rp2350.h
```

BSP は次を保証する。

* LCD の reset、初期化、表示開始、描画
* SD のカード検出、低速初期化、通常速度移行、mount
* ファイルの read、write、sync、close
* キーボードの I²C 初期化、FIFO 読み出し
* ボードごとのピン、SPI/I²C instance、速度
* エラーコードと診断ログ

### 4.2 動作保証済みプロジェクトテンプレート

次のコマンドで新規プロジェクトを生成できること。

```text
picocalc new <project-name> --board rp2040
```

生成直後のプロジェクトは、変更なしで次を満たす。

1. ビルドに成功する
2. LCD に起動画面を表示する
3. SD を mount する
4. SD に自己テストファイルを書き、読み戻し、削除する
5. キーボード入力を取得する
6. host test と firmware test に合格する

AI が通常変更する範囲は `app/` と `assets/` に限定する。BSP、board profile、CMake 基盤、リンカ設定の変更は検出し、変更理由と追加検証を要求する。

### 4.3 Reference Project Catalog

既存の実働プロジェクトごとに manifest を作成する。

```yaml
id: picocalc-lvgl-demo-rp2040
board: picocalc-v2-rp2040
pico_sdk: "<commit-or-version>"
build_command: "<reproducible-command>"
firmware: "<artifact>"
features:
  lcd: verified
  keyboard: verified
  sd: not-used
artifacts:
  uart: "<path>"
  lcd_frame: "<path>"
  spi_trace: "<path>"
hardware_verified_at: "<date>"
```

カタログには、成功したプロジェクトだけでなく、各機能が実際に検証済みかを明記する。「ソースが存在する」ことを「動作確認済み」と同一視しない。

### 4.4 Conformance Test

新しいアプリまたは BSP 変更を、実働プロジェクトの正常動作と比較する。

LCD では少なくとも次を比較する。

* reset と sleep-out の順序
* `COLMOD`、`MADCTL`、`CASET`、`PASET`、`RAMWR`
* SPI mode、速度、CS/DC
* 320x480 GRAM と 320x320 viewport
* 最初の非空フレームまでの時間
* 代表画面の pixel/hash 差分

SD では少なくとも次を確認する。

* SD_DET
* 初期化中の SPI 速度
* CMD0、CMD8、ACMD41、CMD58 と応答
* 通常速度への移行時点
* partition と FAT mount
* read、write、sync、close
* 再起動後の永続性
* カード抜去、timeout、容量不足、破損

### 4.5 Interactive Emulator

二つの実行経路を提供する。

* Host App mode: アプリロジックを PC ネイティブ実行し、高速な画面・入力・ファイルテストを行う
* Firmware mode: Rust製`picoem-picocalc`を主基盤として実際のUF2/ELF/BINを実行し、RP2040のMMIOとPicoCalc固有デバイスを接続する

Firmware mode の接続は次を初期目標とする。

```text
picoem-picocalc (ExecutionModel::Serialを正しさの基準とする)
  PIO0 / GPIO 10-15  -> ST7365P board model（標準B: RGB565, blocking）
  SPI1 / GPIO 10-15  -> 同modelのILI9488 command subset（互換A: RGB666 container）
  SPI0 / GPIO 16-19  -> SD block-device model
  I2C1 / GPIO 6-7    -> keyboard STM32 register model
  GPIO 22            -> SD_DET
  PIO1 / GPIO 20,21,2,3 -> PSRAM model（後続段階）
```

Keyboard modelの一次リファレンスはClockworkPi公式
[`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)
（ローカル配置`<PicoCalc checkout>/Code/picocalc_keyboard`、
STM32F103R8T6 firmware）とする。RP2040側の
`picocalc-life`およびCanonical BSPは、公式controller protocolを利用するconsumer実装と
実機証拠であり、protocol producerの定義を置き換えない。

SD modelはSPI block protocolとvolume provisioningを分離する。購入時付属の32 GBカードに
合わせてFAT32をデフォルトとし、FAT16は互換・診断用の明示profileとする。
firmware/host両backendでFAT32とFAT16を選択でき、同じ
mount/write/sync/read/compare/remove試験に合格することを要求する。既存FAT16回帰を
維持したまま、FAT32 profile、形式を記録するstructured report、target固定を追加する。

`picoem-picocalc`は別リポジトリで保守し、固定commitを使用する。デュアルコア、
SSI/flash write、PIO、DMAの対応状況をcapability manifestに記録し、未対応機能を
無視せず明示的に停止または`hardware_required`と判定する。`rp2040js`はRP2040の
動作と実装方法を比較する参考として利用し、主バックエンドとはしない。

## 5. AI の標準開発フロー

```text
1. picocalc new でプロジェクト生成
2. 生成直後の baseline test を実行
3. AI は app/ を実装
4. host test を実行
5. UF2 をビルド
6. firmware test を実行
7. LCD、SD、キー、UART、trace の結果を確認
8. 失敗原因を修正
9. 全テスト合格後に実機で最終確認
```

標準コマンドは次を想定する。

```text
picocalc new calculator --board rp2040
picocalc test --mode host
picocalc build
picocalc test --mode firmware
picocalc doctor --compare-reference
picocalc test --mode hardware
```

## 6. 診断出力

成功時の例:

```json
{
  "result": "pass",
  "boot": "pass",
  "lcd": {
    "initialized": true,
    "first_frame_ms": 183,
    "non_black_pixels": 4281,
    "screenshot": "artifacts/frame.png"
  },
  "sd": {
    "initialized": true,
    "mounted": true,
    "read": "pass",
    "write": "pass",
    "sync": "pass"
  },
  "keyboard": {
    "detected": true
  }
}
```

LCD 失敗時の例:

```text
LCD initialization mismatch
expected: COLMOD 0x66
actual:   COLMOD 0x55
expected: DISPON before first RAMWR
actual:   DISPON was not observed
```

SD 失敗時の例:

```text
SD initialization failed at ACMD41
CMD0: pass
CMD8: pass
ACMD41: timeout
SPI clock: 25000000 Hz
required during initialization: <= 400000 Hz
```

## 7. 実装優先順位

> **実行順序の正典は[`docs/MILESTONES.md`](docs/MILESTONES.md)です。** 以下の番号は
> 要求を洗い出した順であり、実行順序ではありません。両者の対応表は
> `MILESTONES.md`の「他文書との対応」にあります。項目1〜4はMilestone 0として
> 完了済み、5はMilestone 4、6はMilestone 2〜3、7〜9はMilestone 1に対応します。

1. 実働プロジェクトの棚卸しと再現ビルド
2. LCD、SD、キーボードの正常実装と設定の選定
3. Canonical PicoCalc BSP
4. 動作保証済みプロジェクトテンプレート
5. 実機から golden frame、UART、SPI/I²C、SD artifact を採取
6. Host App mode と conformance test
7. `picoem-picocalc`のSerial実行モデル、回帰テスト、固定commitの確定
8. `picoem-picocalc`とPicoCalc LCD/keyboard/SD modelの接続（`rp2040js`も比較参考に使う）
9. UF2 を使った Firmware mode
10. デュアルコア、PIO、PSRAM、PicoMite への拡張

完全な RP2040 エミュレーターの完成を待たず、BSP とテンプレートの完成時点から新規開発の失敗率を下げる。

## 8. 受け入れ条件

環境全体は次を満たしたとき、最初の目的を達成したと判断する。

1. テンプレートから生成した未変更プロジェクトが、host、firmware、実機の三つで LCD/SD/keyboard smoke test に合格する
2. AI が `app/` だけを変更して代表アプリを完成できる
3. LCD 初期化を意図的に壊すと、コマンドまたは設定の差分が報告される
4. SD 初期化クロックを意図的に壊すと、失敗コマンドと速度違反が報告される
5. エミュレーター合格・実機不合格となった重大障害が 0 件である
6. 通常の開発セッションにおける実機検証回数が基準値から 80% 以上減少する
7. 代表的な変更で実機確認が 1〜2 回以内に収まる
8. host/firmware両backendがFAT16とFAT32のSD profileで同一filesystem smoke testに合格し、実行した形式をreportに記録する

この環境の価値は、AI にハードウェア初期化を毎回推測させることではない。実機確認済みのハードウェア層を再利用し、PC 上で結果を観測し、正常系との差分を使って修正できる状態を提供することにある。
