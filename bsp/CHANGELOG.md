# Canonical PicoCalc BSP 変更履歴

> **この文書は履歴です。現在の契約ではありません。**
> 現在守るべき契約は[`bsp/README.md`](README.md)にあります。過去の版の記述を
> 現行仕様として実装・検証に使わないでください。

現行版は `VERSION` の `0.9.0` です。

## 0.9.0 public filesystem mutation API

アプリが`ff.h`へ依存せず安全保存を実装できるよう、device/host共通の公開filesystem APIへ
create/truncate write、write結果、sync、stat、remove、renameを追加した。not-foundと各I/O失敗を
区別し、BSPが所有する単一fileとdirectory列挙が競合する操作は`Busy`でfail-closedにする。
FAT32既定imageと明示FAT16 imageの両方で、write/sync/readback/rename/removeと負例を検査する。
LCD、keyboard、PSRAM、audioの実装と既存0.8.8実機相関済み経路は変更していない。

## 0.8.8 exact 8-bit PWM reconstruction

PWM wrap 255では、誤差拡散用の再構成値
`(duty * 65535 + 127) / 255`が全duty 0..255について厳密に`duty * 257`と等しい。
左右各サンプルで発生していた除算をこの等価な乗算へ置き換えた。量子化結果、誤差拡散状態、
PWM duty、音声フォーマットは変わらない。Host試験は全256入力を旧式と突合する。

## 0.8.7 audio DMA restart

EOF drainの停止IRQで無効化したDMAチャネルIRQ sourceを、`start_output()`のたびに
再有効化する。NVICのIRQ lineだけを戻してもDMAチャネルから割り込みが上がらないため、
複数曲の自動再生と停止後の再生を成立させるための修正である。PWM、DMA format、
リング会計、量子化、drainのサンプル順序は変更していない。

## 0.8.6 audio drain sequencing

最後に補充したDMA halfを、反対側のhalfの完了後に実際に開始してから停止する。
これにより曲末の1〜128サンプルを捨てず、停止時にはPWM出力をcenter dutyへ戻す。

## 0.8.5 audio quantizer correction

誤差拡散の内部値がint16入力の表現範囲を一時的に超えた場合、PWM量子化前に
`[0, 65535]`へクランプする。これは入力音声のclipではなく、量子化器の状態補正である。
これにより、正当なint16 PCMの再生で`clip_count`が誤って増加しない。PWMピン、DMA、
リング会計、音声フォーマットは変更していない。

同版では、曲末に残るソフトウェアリングと2つのDMA half-bufferを
`request_drain()` / `drain_complete()`で意図的なcenter-duty silenceとして排出する。
EOFの通常終了をDMA underrunとして数えず、既に投入済みのPCMを捨てないためのAPIである。

## 0.8.4 audio ring change

`vendor/audio_picoment/platform/picocalc_audio_pwm.cpp` は、`synth/Picocalc_ment`
からのPWM/DMA出力経路を元にしたBSP内の意図的な修正版である。従来の共有
`g_ring_count`を廃止し、512サンプルの2冪リングをproducer-owned
`g_ring_write`／DMA IRQ-owned `g_ring_read`のSPSC会計へ変更した。
core1から`write_sample()`を呼ぶ場合、core0のDMA IRQに対する割り込み禁止は効かないため、
この変更が必要である。producer publishとconsumer releaseの境界には`__dmb()`を置く。
変更範囲はこのリング会計だけで、PWMピン、DMA、量子化、音声フォーマットは変更していない。

## 0.8.1 PSRAM通常起動の第一候補を変更

83.3 MHz候補が通常スモーク起動で1 byte不一致になった実機結果を反映し、250 MHz通常起動の
第一候補を62.5 MHz（`clkdiv=2.0/fudge=false`）へ変更した。83.3 MHzは共存検証で合格した
候補としてフォールバックに残す。

## 0.8.0 PSRAM/LCD共存クロック検証モード

BのLCD更新中にPSRAMの候補clkdivを順番に切り替え、各候補で
24-byte write/readを120フレーム実行する`probe_lcd_coexistence()`を追加した。
検証後は最初に共存合格した候補をそのまま有効にする。LCD DMAは引き続き使用せず、
PSRAM側はPIO＋DMA blocking APIを使用する。

2026-08-01のPicoCalc実機（250 MHz）では、LCD更新を止めずに共存できたPSRAM設定は
`clkdiv=1.5/fudge=true`（約83.3 MHz）、`clkdiv=2.0/fudge=false`（62.5 MHz）、
`clkdiv=3.0/fudge=false`（約41.7 MHz）だった。共存スイープ上の最高速度は前者で、
検証記録は`hardware-validation/records/bsp-0.8.0-20260801-psram-coexist.json`に置く。

その後の標準BSPスモーク起動では83.3 MHzで1 byte不一致が発生し、62.5 MHzへ
フォールバックした。したがって通常運用の推奨は`clkdiv=2.0/fudge=false`とし、
83.3 MHzは自動フォールバック候補に残す。

## 0.7.0 推奨デフォルトをBへ変更

公開APIのRGB565をプロジェクト標準画素形式とし、CMakeとビルドCLIの
引数なしデフォルトをB（`pio-rgb565`、PIO blocking、DMA OFF）へ変更した。
A（`hwspi-rgb888`）は公式互換・bring-up・診断経路として削除・統合しない。

## 0.6.0 参照経路と汎用経路の分離

動作実績コードをコピーした参照経路を残したまま、AIが使う汎用経路も
用意した。音声は`PICOCALC_AUDIO_REFERENCE_TONE=ON`で固定サイン、`OFF`で
`audio::init()`→`write_sample()`→`start()`のPCM経路になる。PSRAMは生APIに加えて
`psram::Buffer`でアドレス範囲を管理できる。個別のコピペ例は
`templates/rp2040-basic/examples/`に置く。

## 0.4.0 転送本体をvendorへ固定（LCD A/B実機合格）

Bの転送処理を書き写すのをやめ、実機動作が記録されている
`general/lcd/src/lcd_rgb565_pio.cpp`の**無改変コピー**を`bsp/vendor/`へ置いて呼ぶだけに
した。`bsp/src/display_pio_rgb565.cpp`は`game/pico_skyace`と同じ呼び出し粒度
（160×160のウィンドウごとに`set_window`1回、画素は160ピクセル単位）に徹する薄い
アダプタである。`verify`は`vendor-lcd-pio-unmodified`でコピーのSHA-256を照合し、
アダプタ側に転送処理が戻っていないことも検査する。

同じ方針をAへも適用し、両参照のloader-style SPI契約を
`bsp/vendor/lcd_hwspi_rgb888.cpp`へ固定した。

2026-07-30にA/B両方が実機表示に成功した。Aはcommit `e2d53ad55afa`、Bは
`f763b91eae95`。記録は`hardware-validation/records/bsp-0.4.0-20260730-02.json`（A、
LCD/SD/keyboard pass）と`bsp-0.4.0-20260730-01.json`（B、LCD/SD pass、keyboard未試験）。

## 0.3.0 LCDを二系統へ分離

0.2.xではhardware SPI1/RGB888の送信とPIO系資料の考え方を一つの実装へ混ぜてしまい、
どの既知動作コードを移植したUF2なのかを固定できなくなっていた。0.3.0でLCD実装を
A `hwspi-rgb888` と B `pio-rgb565` の二つの独立BSPへ分離し、CMakeの
`PICOCALC_LCD_VARIANT`で一方だけをリンクする構成にした。

## それ以前

0.1.x〜0.2.xのLCD不動作調査の全経緯は
[`docs/LCD_INVESTIGATION_20260729.md`](../docs/LCD_INVESTIGATION_20260729.md)と
[`docs/PROJECT_HISTORY_20260729.md`](../docs/PROJECT_HISTORY_20260729.md)にある。
これらの版のUF2・コミットを現在版として再利用しない。
