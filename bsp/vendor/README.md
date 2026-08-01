# Vendored LCD drivers (do not edit)

LCDの転送本体は、実機動作が記録されている参照プロジェクトの契約を保つため、
BSPアダプタから分離する。新しいLCD転送を`bsp/src/display*.cpp`へ書き戻してはならない。

## A: `hwspi-rgb888`

`lcd_hwspi_rgb888.cpp/.h`は、`general/lcd/src/main_hwspi_rgb888_probe.cpp`のloader-style
初期化と、実機動作している`PicoCalc/Code/picocalc_helloworld/lcdspi/lcdspi.c`の
ウィンドウ／RAMRD契約をBSPから直接呼べる形へ固定したドライバである。

- SPI1、25 MHz、`COLMOD=0x66`、RGB888 3 bytes/pixel
- リセット解除後200 ms、`0x11`/`0x29`前後の120 ms待機
- `CASET`、`RASET`、`RAMWR`、画素列を一つのCS Low区間で送信
- RAMRDはSPI1を6 MHzへ落とし、RGB888 3 bytes/pixelを読み、終了後25 MHzへ復帰
- `bsp/src/display.cpp`はRGB565公開API、変換、比較ログだけを担当

参照元はstandalone probeと実働プロジェクトに分かれているため、Bのような単一ファイルの
バイト単位コピーではなく、両者の転送契約を専用vendorドライバへ固定している。

`pio-rgb565`（LCD BSP B）の転送処理は、実機動作が記録されている実装の**無改変コピー**を
使う。ここにあるファイルは書き写し・再実装ではなく、バイト単位の複製である。

| ファイル | 取得元 | 取得元commit | SHA-256 |
|---|---|---|---|
| `lcd_rgb565_pio.cpp` | `general/lcd/src/lcd_rgb565_pio.cpp` | `f5517829f1bc` | `d4013f26f7a49350a354d716e825ac516e952857e2f3578cd414ac50c1e88920` |
| `lcd_rgb565_pio.h` | `general/lcd/src/lcd_rgb565_pio.h` | `f5517829f1bc` | `350aafa3ffb28ac8a31b6e1adcdef551e0177428ee67f9896978c1714e0978f9` |
| `lcd_spi_min.pio` | `general/lcd/src/lcd_spi_min.pio` | `f5517829f1bc` | `618d4be87efb71a24422aa74d156d13db32e027cbfd5679cef21aa6d14b82fac` |

この3ファイルは`game/pico_skyace`が2026-07-04に無改変移植して実機動作した組み合わせと
同一である。`general/01_DISPLAY_LCD.md`§0と§8.1は、独自実装ではなくこのファイルを
そのまま使うことを指示している。

## Audio: `audio_picoment`

`audio_picoment/platform/picocalc_audio_pwm.cpp/.h`は、実機で音声出力を確認した
`synth/Picocalc_ment/src/platform/`のPWM/DMA経路をBSP向けに固定したものを基にした、
0.8.4でリング会計だけを修正したBSPドライバである。PRA32-Uなどの音源生成は含めず、
PCMを受け取る出力経路だけを提供する。

- GP26/27、sysclk 250 MHz基準、PWM wrap 255、約976 kHz carrier
- 48 kHz、DMA timer、128 sample half-buffer、512 sample SPSC ring
- 16-bit PCMからPWMへの量子化誤差拡散100%、DMA IRQのunderrun/drop統計
- 初期化時は発音せずPWM midpoint。アプリが`write_sample()`して`start()`する

0.8.4の変更理由は、core1 producerから`write_sample()`を呼ぶとcore0のDMA IRQに対する
`save_and_disable_interrupts()`が無効で、共有`g_ring_count`の非アトミックRMWが破損する
ためである。`g_ring_write`はproducer、`g_ring_read`はDMA IRQだけが書き、公開前後に
`__dmb()`を置いた。変更対象はリング会計のみで、取得元のPWM/DMA契約は変更していない。

0.8.5では、誤差拡散状態をPWM入力範囲へクランプして正当なint16 PCMをclipとして
数えないようにし、`request_drain()` / `drain_complete()`を追加した。後者は曲末の
短いDMA tailをcenter-duty silenceで完了させる。いずれもcore1 decoderとcore0 DMA
producer/consumer構成で必要な差分であり、取得元との差分として記録する。

## PSRAM: `rp2040-psram`

`rp2040-psram/`は`PicoCalc/Code/picocalc_helloworld/rp2040-psram/`のPIO SPIドライバを
固定したもの（MIT License）。`game/pico_rescue`でも同じドライバが使われている。
ヘッダの仕様どおりCS/CLKは連続GPIOが必要なため、PicoCalc V2ではCS20/SCK21、MOSI2、
MISO3を固定する。read/writeはDMA blocking APIを使い、`fudge`は実測済み候補だけで選ぶ。

クロック制約はドライバの一般的な上限ではなく、PicoCalc実機の記録を優先する。
250 MHz通常起動時は実機合格済みの`fudge=true, clkdiv=1.5`、続いて
`fudge=false, clkdiv=2/3`だけをread/write自己検証する。125 MHz側は
`fudge=false`の1/1.5/2/3/4を使う。共存検証モードだけは全候補を測定する。
PSRAMは揮発性なので永続ログや
セーブ領域には使わない。

2026-08-01のLCD共存実機検証では、250 MHz system clockで`fudge=true, clkdiv=1.5`
（約83.3 MHz）、`fudge=false, clkdiv=2.0/3.0`が合格した。その後の標準スモーク起動で
83.3 MHzに1 byte不一致が出たため、通常起動は`fudge=false, clkdiv=2.0/3.0`を優先し、
`1.5/true`をフォールバックとする。実際の候補選択は起動時のwrite/read検証結果に従う。

## 規約

- LCDの無改変コピーは**このディレクトリのファイルを編集しない**。修正が必要なら取得元を直し、
  コピーを取り直して上記のSHA-256とcommitを更新する。`audio_picoment`だけは0.8.4で
  上記のcore1/DMA IRQ競合を解消するためのBSP差分を許可された例外として記録する。
- `bsp/src/display_pio_rgb565.cpp`は薄いアダプタに徹する。転送・初期化・タイミングを
  アダプタ側で作り直さない。
- `tools/picocalc.py verify`が`vendor-lcd-pio-unmodified`でSHA-256を照合する。

## 上位で守る呼び出し規約

`game/pico_skyace/src/platform/picocalc_display.cpp`と同じ粒度で呼ぶ。

- `lcd_rgb565_pio_set_window()`は160×160以下の矩形につき1回
- 画素は`lcd_rgb565_pio_write_blocking()`を160ピクセル単位で呼んで送る
- ウィンドウを再送せず、GRAMアドレスの自動インクリメントに任せる
