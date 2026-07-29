# Canonical PicoCalc BSP

この BSP は、`picocalc-life` の実機確認済み LCD/keyboard/SD 実装と、
`pico_skyace` の LCD bring-up 記録を基準にしている。音声機能の実機基準は
`Picocalc_ment` とする。

固定する重要条件（LCDは二つの独立BSPから選ぶ）:

* LCD共通: SCK/MOSI/MISO GP10/11/12、CS GP13、DC GP14、RESET GP15
* LCD A `hwspi-rgb888`: uf2loader互換初期化、125 MHz、SPI1 25 MHz、`COLMOD 0x66`、RGB888、RAMWRウィンドウ中CS保持
* LCD B `pio-rgb565`: 250 MHz、`general/lcd`互換PIO0 blocking送信、160×160以下のタイル、`COLMOD 0x65`、RGB565、PIO停止後SIOでRAMRD
* LCD: 公開APIはRGB565。A/Bの送信・初期化・読出し実装は混ぜず、CMakeの`PICOCALC_LCD_VARIANT`で一方だけをリンクする
* LCD: `verify_pixels()`は選択したBSPのRAMRD形式をRGB565へそろえ、最大16 pixelを比較する診断API
* keyboard: I2C1、SDA GP6、SCL GP7、400 kHz、address `0x1f`。起動時はバックライトの既定状態を変更しない
* SD: SPI0、MISO GP16、CS GP17、SCK GP18、MOSI GP19、detect GP22
* SD: 初期化 400 kHz、ready 後 12 MHz
* audio: GP26/27（48 kHz PWM/DMA stream API は次版で取り込む）

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。

実機試験ではAを先に確認する。Aの`variant=hwspi-rgb888`と
`[PICOCALC][LCD][VERIFY] app_status=pass`を確認してから、同じ
`build/picocalc_app.uf2`へBを生成する。A/BのUF2を別名保存しない。

ピン定義と周波数は`profiles/picocalc-rp2040.json`を唯一の入力源とし、
`tools/generate_board_header.py`が`include/picocalc/board_generated.h`を生成する。
`board_generated.h`は直接編集しない。`board.h`には契約を守る`static_assert`だけを
置く。

LCD Aの初期化列は`include/picocalc/detail/lcd_protocol.h`にあり、実機hardware-SPI
transportとhost SPI fakeが同じ関数を実行する。LCD Bは`src/display_pio_rgb565.cpp`
と`src/lcd_spi_min.pio`に独立して保持し、Aのprotocol helperを参照しない。
