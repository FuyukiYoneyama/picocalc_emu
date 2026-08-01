# Canonical PicoCalc BSP

この BSP は、`picocalc-life` の実機確認済み LCD/keyboard/SD 実装と、
`pico_skyace` の LCD bring-up 記録を基準にしている。音声機能の実機基準は
`Picocalc_ment` とする。

固定する重要条件（LCDは二つの独立BSPから選び、Bを推奨デフォルトとする）:

* LCD共通: SCK/MOSI/MISO GP10/11/12、CS GP13、DC GP14、RESET GP15
* LCD A `hwspi-rgb888`（互換・診断）: `bsp/vendor/lcd_hwspi_rgb888.cpp`、uf2loader互換初期化、125 MHz、SPI1 25 MHz、`COLMOD 0x66`、RGB666をR/G/B各1バイトの3-byte containerで送信、CASET/RASET/RAMWRから画素列までRAMWRウィンドウ中CS保持
* LCD B `pio-rgb565`（推奨デフォルト）: 250 MHz、`general/lcd`/`pico_skyace`互換PIO0 blocking送信（LCD DMA OFF、clkdiv 2.0、約62.5 MHz）、`COLMOD 0x65`、RGB565を2 bytes/pixelで送信、PIO停止後SIOでRAMRD
* LCD: 公開APIはRGB565。A/Bの送信・初期化・読出し実装は混ぜず、CMakeの`PICOCALC_LCD_VARIANT`で一方だけをリンクする
* LCD: `verify_pixels()`は選択したBSPのRAMRD形式をRGB565へそろえ、最大16 pixelを比較する診断API
* keyboard: I2C1、SDA GP6、SCL GP7、400 kHz、address `0x1f`。起動時はバックライトの既定状態を変更しない
* SD: SPI0、MISO GP16、CS GP17、SCK GP18、MOSI GP19、detect GP22
* SD: 初期化 400 kHz、ready 後 12 MHz
* audio: GP26/27、`Picocalc_ment`からコピーした固定1 kHz/-6 dBFS参照試験と、同じPWM/DMAの48 kHz PCM stream API。PWM wrap 255、128 sample DMA half、512 sample ring
* PSRAM: 8 MiB ESP-PSRAM64H、PIO1、CS/SCK/MOSI/MISOはGP20/21/2/3。`pico_rescue`の候補順（fudge=trueのclkdiv 1/1.5/2/3/4、続いてfudge=falseの同じ候補）をそのまま使う
* PSRAM: transferは24 byte以下へ分割し、起動時にID読出しとread/write一致検証を行う。失敗時は利用不可として報告し、SRAMとして扱わない

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。

実機試験ではA/Bを同時に扱わず、一度に一方だけを同じ
`build/picocalc_app.uf2`へ生成する。Aの合否にかかわらずBも独立して検証し、
両方の`variant`と`[PICOCALC][LCD][VERIFY] app_status=pass`を確認する。
A/BのUF2を別名保存しない。

0.6.0では、動作実績コードをコピーした参照経路を残したまま、AIが使う汎用経路も
用意した。音声は`PICOCALC_AUDIO_REFERENCE_TONE=ON`で固定サイン、`OFF`で
`audio::init()`→`write_sample()`→`start()`のPCM経路になる。PSRAMは生APIに加えて
`psram::Buffer`でアドレス範囲を管理できる。個別のコピペ例は
`templates/rp2040-basic/examples/`に置く。実機検証はこの準備が終わった最後に行う。

0.7.0では、公開APIのRGB565をプロジェクト標準画素形式とし、CMakeとビルドCLIの
引数なしデフォルトをBへ変更した。A/Bのドライバは引き続き独立しており、Aを削除・統合しない。

0.8.0では、BのLCD更新中にPSRAMの候補clkdivを順番に切り替え、各候補で
24-byte write/readを120フレーム実行する`probe_lcd_coexistence()`を追加した。
検証後は最初に共存合格した候補をそのまま有効にする。

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
