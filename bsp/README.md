# Canonical PicoCalc BSP

現在版は `VERSION` の `0.8.8` です。このBSPはAIが通常編集する場所ではありません。
アプリは `picocalc/bsp.h` 以下の公開APIを使い、LCD・SD・キーボード・PSRAMの
初期化を再実装しません。

この BSP は、`picocalc-life` の実機確認済み LCD/keyboard/SD 実装と、
`pico_skyace` の LCD bring-up 記録を基準にしている。音声機能の実機基準は
`Picocalc_ment` とする。

固定する重要条件（LCDは二つの独立BSPから選び、Bを推奨デフォルトとする）:

* LCD共通: SCK/MOSI/MISO GP10/11/12、CS GP13、DC GP14、RESET GP15
* LCD A `hwspi-rgb888`（互換・診断）: `bsp/vendor/lcd_hwspi_rgb888.cpp`、uf2loader互換初期化、125 MHz、SPI1 25 MHz、`COLMOD 0x66`、RGB666をR/G/B各1バイトの3-byte containerで送信、CASET/RASET/RAMWRから画素列までRAMWRウィンドウ中CS保持
* LCD B `pio-rgb565`（推奨デフォルト）: 250 MHz、`general/lcd`/`pico_skyace`互換PIO0 blocking送信（LCD DMA OFF、clkdiv 2.0、約62.5 MHz）、`COLMOD 0x65`、RGB565を2 bytes/pixelで送信、PIO停止後SIOでRAMRD
* LCD: 公開APIはRGB565。A/Bの送信・初期化・読出し実装は混ぜず、CMakeの`PICOCALC_LCD_VARIANT`で一方だけをリンクする。AはSPI1 blocking/RGB666の3 bytes/pixel、BはPIO0 blocking/RGB565の2 bytes/pixelで、LCD DMAは使わない
* LCD: `verify_pixels()`は選択したBSPのRAMRD形式をRGB565へそろえ、最大16 pixelを比較する診断API
* keyboard: I2C1、SDA GP6、SCL GP7、400 kHz、address `0x1f`。起動時はバックライトの既定状態を変更しない
* SD: SPI0、MISO GP16、CS GP17、SCK GP18、MOSI GP19、detect GP22
* SD: 初期化 400 kHz、ready 後 12 MHz
* audio: GP26/27、`Picocalc_ment`からコピーした固定1 kHz/-6 dBFS参照試験と、同じPWM/DMAの48 kHz PCM stream API。PWM wrap 255、128 sample DMA half、512 sample SPSC ring
* PSRAM: 8 MiB ESP-PSRAM64H、PIO1、CS/SCK/MOSI/MISOはGP20/21/2/3。通常起動の候補は250 MHzでは`2.0/false → 3.0/false → 1.5/true`、125 MHzでは`1.0/false → 1.5/false → 2.0/false → 3.0/false → 4.0/false`。全候補スイープは共存検証モードだけで行う
* PSRAM: transferは24 byte以下へ分割し、起動時にID読出しとread/write一致検証を行う。失敗時は利用不可として報告し、SRAMとして扱わない

通常のアプリはこのディレクトリを変更せず、`picocalc/bsp.h` の API を使う。

## 0.8.4 audio ring change

`vendor/audio_picoment/platform/picocalc_audio_pwm.cpp` は、`synth/Picocalc_ment`
からのPWM/DMA出力経路を元にしたBSP内の意図的な修正版である。従来の共有
`g_ring_count`を廃止し、512サンプルの2冪リングをproducer-owned
`g_ring_write`／DMA IRQ-owned `g_ring_read`のSPSC会計へ変更した。
core1から`write_sample()`を呼ぶ場合、core0のDMA IRQに対する割り込み禁止は効かないため、
この変更が必要である。producer publishとconsumer releaseの境界には`__dmb()`を置く。
変更範囲はこのリング会計だけで、PWMピン、DMA、量子化、音声フォーマットは変更していない。

## 0.8.5 audio quantizer correction

誤差拡散の内部値がint16入力の表現範囲を一時的に超えた場合、PWM量子化前に
`[0, 65535]`へクランプする。これは入力音声のclipではなく、量子化器の状態補正である。
これにより、正当なint16 PCMの再生で`clip_count`が誤って増加しない。PWMピン、DMA、
リング会計、音声フォーマットは変更していない。

同版では、曲末に残るソフトウェアリングと2つのDMA half-bufferを
`request_drain()` / `drain_complete()`で意図的なcenter-duty silenceとして排出する。
EOFの通常終了をDMA underrunとして数えず、既に投入済みのPCMを捨てないためのAPIである。

## 0.8.6 audio drain sequencing

最後に補充したDMA halfを、反対側のhalfの完了後に実際に開始してから停止する。
これにより曲末の1〜128サンプルを捨てず、停止時にはPWM出力をcenter dutyへ戻す。

## 0.8.7 audio DMA restart

EOF drainの停止IRQで無効化したDMAチャネルIRQ sourceを、`start_output()`のたびに
再有効化する。NVICのIRQ lineだけを戻してもDMAチャネルから割り込みが上がらないため、
複数曲の自動再生と停止後の再生を成立させるための修正である。PWM、DMA format、
リング会計、量子化、drainのサンプル順序は変更していない。

## 0.8.8 exact 8-bit PWM reconstruction

PWM wrap 255では、誤差拡散用の再構成値
`(duty * 65535 + 127) / 255`が全duty 0..255について厳密に`duty * 257`と等しい。
左右各サンプルで発生していた除算をこの等価な乗算へ置き換えた。量子化結果、誤差拡散状態、
PWM duty、音声フォーマットは変わらない。Host試験は全256入力を旧式と突合する。

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

## 変更履歴（現在の契約ではない）

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

2026-08-01のPicoCalc実機（250 MHz）では、LCD更新を止めずに共存できたPSRAM設定は
`clkdiv=1.5/fudge=true`（約83.3 MHz）、`clkdiv=2.0/fudge=false`（62.5 MHz）、
`clkdiv=3.0/fudge=false`（約41.7 MHz）だった。共存スイープ上の最高速度は前者で、
検証記録は`hardware-validation/records/bsp-0.8.0-20260801-psram-coexist.json`に置く。

その後の標準BSPスモーク起動では83.3 MHzで1 byte不一致が発生し、62.5 MHzへ
フォールバックした。したがって通常運用の推奨は`clkdiv=2.0/fudge=false`とし、
83.3 MHzは自動フォールバック候補に残す。

過去の台帳記録は、Aが`hardware-validation/records/bsp-0.4.0-20260730-02.json`（LCD/SD/keyboard
pass）、Bが`hardware-validation/records/bsp-0.4.0-20260730-01.json`（LCD/SD pass、keyboard
未試験）である。最新の標準Bの実機確認結果は、起動ログの`git`と`app_status`を基準にする。

ピン定義と周波数は`profiles/picocalc-rp2040.json`を唯一の入力源とし、
`tools/generate_board_header.py`が`include/picocalc/board_generated.h`を生成する。
`board_generated.h`は直接編集しない。`board.h`には契約を守る`static_assert`だけを
置く。

LCD Aの初期化・転送列は`vendor/lcd_hwspi_rgb888.cpp`にあり、`src/display.cpp`は
公開APIとRGB565/RGB888変換だけを担当する。LCD Bは`src/display_pio_rgb565.cpp`
と`src/lcd_spi_min.pio`に独立して保持し、Aのprotocol helperを参照しない。
