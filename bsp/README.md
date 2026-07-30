# Canonical PicoCalc BSP

この BSP は、`picocalc-life` の実機確認済み LCD/keyboard/SD 実装と、
`pico_skyace` の LCD bring-up 記録を基準にしている。音声機能の実機基準は
`Picocalc_ment` とする。

固定する重要条件（LCDは二つの独立BSPから選ぶ）:

* LCD共通: SCK/MOSI/MISO GP10/11/12、CS GP13、DC GP14、RESET GP15
* LCD A `hwspi-rgb888`: `bsp/vendor/lcd_hwspi_rgb888.cpp`、uf2loader互換初期化、125 MHz、SPI1 25 MHz、`COLMOD 0x66`、RGB888、CASET/RASET/RAMWRから画素列までRAMWRウィンドウ中CS保持
* LCD B `pio-rgb565`: 250 MHz、`general/lcd`/`pico_skyace`互換PIO0 blocking送信（clkdiv 2.0、約62.5 MHz）、`COLMOD 0x65`、RGB565、PIO停止後SIOでRAMRD
* LCD: 公開APIはRGB565。A/Bの送信・初期化・読出し実装は混ぜず、CMakeの`PICOCALC_LCD_VARIANT`で一方だけをリンクする
* LCD: `verify_pixels()`は選択したBSPのRAMRD形式をRGB565へそろえ、最大16 pixelを比較する診断API
* keyboard: I2C1、SDA GP6、SCL GP7、400 kHz、address `0x1f`。起動時はバックライトの既定状態を変更しない
* SD: SPI0、MISO GP16、CS GP17、SCK GP18、MOSI GP19、detect GP22
* SD: 初期化 400 kHz、ready 後 12 MHz
* audio: GP26/27（48 kHz PWM/DMA stream API は次版で取り込む）

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。

実機試験ではA/Bを同時に扱わず、一度に一方だけを同じ
`build/picocalc_app.uf2`へ生成する。Aの合否にかかわらずBも独立して検証し、
両方の`variant`と`[PICOCALC][LCD][VERIFY] app_status=pass`を確認する。
A/BのUF2を別名保存しない。

ピン定義と周波数は`profiles/picocalc-rp2040.json`を唯一の入力源とし、
`tools/generate_board_header.py`が`include/picocalc/board_generated.h`を生成する。
`board_generated.h`は直接編集しない。`board.h`には契約を守る`static_assert`だけを
置く。

LCD Aの初期化・転送列は`vendor/lcd_hwspi_rgb888.cpp`にあり、`src/display.cpp`は
公開APIとRGB565/RGB888変換だけを担当する。LCD Bは`src/display_pio_rgb565.cpp`
と`src/lcd_spi_min.pio`に独立して保持し、Aのprotocol helperを参照しない。
