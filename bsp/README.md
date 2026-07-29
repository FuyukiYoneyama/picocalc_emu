# Canonical PicoCalc BSP

この BSP は、`picocalc-life` の実機確認済み LCD/keyboard/SD 実装と、
`pico_skyace` の LCD bring-up 記録を基準にしている。音声機能の実機基準は
`Picocalc_ment` とする。

固定する重要条件:

* LCD: PIO0、GP10/11、CS GP13、DC GP14、RESET GP15
* LCD: ST7365P/ILI9488 互換初期化、`COLMOD 0x65`、RGB565
* LCD: 一回の CS Low で最大 160 pixels（320 bytes）
* keyboard: I2C1、SDA GP6、SCL GP7、400 kHz、address `0x1f`
* SD: SPI0、MISO GP16、CS GP17、SCK GP18、MOSI GP19、detect GP22
* SD: 初期化 400 kHz、ready 後 12 MHz
* audio: GP26/27（48 kHz PWM/DMA stream API は次版で取り込む）

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。
