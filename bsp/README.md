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
* audio: GP26/27、`Picocalc_ment`からコピーした固定1 kHz/-6 dBFSの48 kHz PWM/DMA参照試験。PWM wrap 255、128 sample DMA half、512 sample ring
* PSRAM: 8 MiB ESP-PSRAM64H、PIO1、CS/SCK/MOSI/MISOはGP20/21/2/3。Aの参照試験は`pico_rescue`の候補順（fudge=trueのclkdiv 1/1.5/2/3/4、続いてfudge=falseの同じ候補）をそのまま使う
* PSRAM: transferは24 byte以下へ分割し、起動時にID読出しとread/write一致検証を行う。失敗時は利用不可として報告し、SRAMとして扱わない

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。

実機試験ではA/Bを同時に扱わず、一度に一方だけを同じ
`build/picocalc_app.uf2`へ生成する。Aの合否にかかわらずBも独立して検証し、
両方の`variant`と`[PICOCALC][LCD][VERIFY] app_status=pass`を確認する。
A/BのUF2を別名保存しない。

0.5.0-Aでは、まず動作実績コードのコピペ経路を実機で検証する。音声は
`Picocalc_ment`の固定サイン試験を`init()`から即時開始し、PSRAMは`pico_rescue`の
初期化・候補順・24 byte以下のread/write検証を使う。これらの実機合格前にPCM生成や
汎用APIへの改造を行わない。既存の0.4.0 LCD/SD/keyboard記録は遡って書き換えない。

実機合格記録は、Aが`hardware-validation/records/bsp-0.4.0-20260730-02.json`（LCD/SD/keyboard
pass）、Bが`hardware-validation/records/bsp-0.4.0-20260730-01.json`（LCD/SD pass、keyboard
未試験）である。

ピン定義と周波数は`profiles/picocalc-rp2040.json`を唯一の入力源とし、
`tools/generate_board_header.py`が`include/picocalc/board_generated.h`を生成する。
`board_generated.h`は直接編集しない。`board.h`には契約を守る`static_assert`だけを
置く。

LCD Aの初期化・転送列は`vendor/lcd_hwspi_rgb888.cpp`にあり、`src/display.cpp`は
公開APIとRGB565/RGB888変換だけを担当する。LCD Bは`src/display_pio_rgb565.cpp`
と`src/lcd_spi_min.pio`に独立して保持し、Aのprotocol helperを参照しない。
