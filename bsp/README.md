# Canonical PicoCalc BSP

現在版は `VERSION` の `0.8.8` です。このBSPはAIが通常編集する場所ではありません。
アプリは `picocalc/bsp.h` 以下の公開APIを使い、LCD・SD・キーボード・PSRAMの
初期化を再実装しません。

キーボードのprotocol producerについては、ClockworkPi公式
[`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)
（このworkspaceでは`/home/fuyuki/pico_dvl/codex/PicoCalc/Code/picocalc_keyboard`）の
STM32F103R8T6 firmwareを一次リファレンスとする。
`picocalc-life`はRP2040側consumerの実機確認済みLCD/keyboard/SD実装、
`pico_skyace`はLCD bring-up記録、`Picocalc_ment`は音声の実機基準として使う。

固定する重要条件（LCDは二つの独立BSPから選び、Bを推奨デフォルトとする）:

* LCD共通: SCK/MOSI/MISO GP10/11/12、CS GP13、DC GP14、RESET GP15
* LCD A `hwspi-rgb888`（互換・診断）: `bsp/vendor/lcd_hwspi_rgb888.cpp`、uf2loader互換初期化、125 MHz、SPI1 25 MHz、`COLMOD 0x66`、RGB666をR/G/B各1バイトの3-byte containerで送信、CASET/RASET/RAMWRから画素列までRAMWRウィンドウ中CS保持
* LCD B `pio-rgb565`（推奨デフォルト）: 250 MHz、`general/lcd`/`pico_skyace`互換PIO0 blocking送信（LCD DMA OFF、clkdiv 2.0、約62.5 MHz）、`COLMOD 0x65`、RGB565を2 bytes/pixelで送信、PIO停止後SIOでRAMRD
* LCD: 公開APIはRGB565。A/Bの送信・初期化・読出し実装は混ぜず、CMakeの`PICOCALC_LCD_VARIANT`で一方だけをリンクする。AはSPI1 blocking/RGB666の3 bytes/pixel、BはPIO0 blocking/RGB565の2 bytes/pixelで、LCD DMAは使わない
* LCD: `verify_pixels()`は選択したBSPのRAMRD形式をRGB565へそろえ、最大16 pixelを比較する診断API
* keyboard controller: 公式STM32 firmwareが7×8 matrix＋12 buttonsを走査し、I2C target `0x1f`、status `0x04`、FIFO `0x09`、最大31 eventsを提供する
* keyboard RP2040 consumer: I2C1、SDA GP6、SCL GP7、400 kHz、repeated-start。起動時はバックライトの既定状態を変更しない
* SD: SPI0、MISO GP16、CS GP17、SCK GP18、MOSI GP19、detect GP22
* SD: 初期化 400 kHz、ready 後 12 MHz
* audio: GP26/27、`Picocalc_ment`からコピーした固定1 kHz/-6 dBFS参照試験と、同じPWM/DMAの48 kHz PCM stream API。PWM wrap 255、128 sample DMA half、512 sample SPSC ring
* PSRAM: 8 MiB（64 Mbit SPI PSRAM。ESP-PSRAM64H相当と記録しているが、実機の
  刻印による確認は未実施。APS6404L系も同一コマンドセットで互換のため、BSPは型番では
  なくコマンド契約に依存する）、PIO1、CS/SCK/MOSI/MISOはGP20/21/2/3。通常起動の候補は250 MHzでは`2.0/false → 3.0/false → 1.5/true`、125 MHzでは`1.0/false → 1.5/false → 2.0/false → 3.0/false → 4.0/false`。全候補スイープは共存検証モードだけで行う
* PSRAM: transferは24 byte以下へ分割し、起動時にID読出しとread/write一致検証を行う。失敗時は利用不可として報告し、SRAMとして扱わない

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。

音声経路の版ごとの変更理由（0.8.4のSPSCリング会計、0.8.5の量子化器クランプとdrain、
0.8.6のdrain順序、0.8.7のDMA IRQ source再開、0.8.8の等価乗算）は
[`CHANGELOG.md`](CHANGELOG.md)に記録する。いずれもPWMピン、DMA形式、音声
フォーマットは変更していない。

## Read-only filesystem API

`picocalc/filesystem.h` は、音楽アプリなどの長寿命 read-only 利用向けに、次の
opaque API を公開する。`FATFS`、`FIL`、`DIR`、`FRESULT` は app の include 面へ出ない。

- `mount()` / `unmount()` / `mounted()`
- `open_read()` / `read()` / `seek()` / `tell()` / `size()` / `close()`
- `open_dir()` / `next_dir()` / `close_dir()`

BSP 内では `FATFS` を1個だけ所有し、read file と directory は同時に開けない。
directory 列挙を再生開始前に完了してから、file handle を開く。`smoke_test()`も同じ
mountを再利用するため、app側で別の `FATFS` を mount しない。

実機試験ではA/Bを同時に扱わず、一度に一方だけを同じ
`build/picocalc_app.uf2`へ生成する。Aの合否にかかわらずBも独立して検証し、
両方の`variant`と`[PICOCALC][LCD][VERIFY] app_status=pass`を確認する。
A/BのUF2を別名保存しない。

## 現在のAI向け契約

`display`の画素形式は常にRGB565である。wire形式の違いは選択したLCD BSP内部に
閉じ込める。`display::verify_pixels()`の`app_status=pass`は、GRAM readbackと
期待値の一致まで確認したことを表す。

PSRAM通常起動の250 MHz第一候補は`clkdiv=2.0/fudge=false`（62.5 MHz）である。
`max_transfer_chunk_bytes`は24であり、これを超える転送をBSP外で直接発行しない。
高速候補の追加は、共存検証と実機根拠を伴うBSP変更である。

音声の既定参照経路は`PICOCALC_AUDIO_REFERENCE_TONE=ON`で固定1 kHz音を開始する。
標準テンプレートはLCD検証完了後に`audio::stop()`を呼ぶ。PCMアプリは`OFF`を選び、
`audio::init()`、サンプル投入、`audio::start()`、終了時`audio::stop()`の順に使う。

## 版ごとの変更履歴

過去の版でどこを、なぜ変えたかは[`CHANGELOG.md`](CHANGELOG.md)へ分離した。
本書には現行0.8.8の契約だけを置く。0.1.x〜0.2.xのLCD不動作調査の全経緯は
[`../docs/LCD_INVESTIGATION_20260729.md`](../docs/LCD_INVESTIGATION_20260729.md)にある。

過去の台帳記録は、Aが`hardware-validation/records/bsp-0.4.0-20260730-02.json`（LCD/SD/keyboard
pass）、Bが`hardware-validation/records/bsp-0.4.0-20260730-01.json`（LCD/SD pass、keyboard
未試験）である。最新の標準Bの実機確認結果は、起動ログの`git`と`app_status`を基準にする。

## 生成ファイルの規約

ピン定義と周波数は`profiles/picocalc-rp2040.json`を唯一の入力源とし、
`tools/generate_board_header.py`が`include/picocalc/board_generated.h`を生成する。
`board_generated.h`は直接編集しない。`board.h`には契約を守る`static_assert`だけを
置く。

LCD Aの初期化・転送列は`vendor/lcd_hwspi_rgb888.cpp`にあり、`src/display.cpp`は
公開APIとRGB565/RGB888変換だけを担当する。LCD Bは`src/display_pio_rgb565.cpp`
と`src/lcd_spi_min.pio`に独立して保持し、Aのprotocol helperを参照しない。
