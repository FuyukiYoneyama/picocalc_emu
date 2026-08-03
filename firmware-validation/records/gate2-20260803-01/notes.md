# Gate 2 notes — 到達点の先にある3つの制限

**PSRAM未接続による停滞（Gate 3の範囲）.** HELLO-VISIBLEは約75.4Mサイクルで完了するが、その先の`psram_test`は`psram_write8`で停滞する。PIO1/DMAの8 MiB PSRAM modelが未接続で書き込み完了応答が返らないため。UARTは`Testing PSRAM...`で止まり、LCDにも同じ2行だけが残る。800Mサイクルまで回しても`stop_reason`は`cycle_limit`、`exception`は`null`、`unsupported_mmio`は空で、異常終了ではなく単なる待ちである。Gate 2の合否には影響しない。

**RAMRD未実装.** `0x2E`は計数のみで0を返す。公式ファームの読み出し経路`read_buffer_spi`は`scroll_lcd_spi`からしか呼ばれないため、画面26行を超える出力を伴うファームでは表示が壊れる。発火検知は`lcd.ramrd`が非0になること（本recordの全実行で0）。実装にはダミーバイト数とバイト順の実機確認が要る。Track AのRAMRD実機セッションを一次資料とする想定で、計画上もGate 2はその相関確認までは暫定合格の扱いである。

**MADCTL/INVON非適用の判断.** `0x48`(MX|BGR)とINVONは記録するがframebufferへは適用しない。いずれもパネル配線とガラスの補正だからである。MXは物理ガラスに対して列カウンタを反転させて実機で正立させるものなので、論理CASET/RASET座標で索く本framebufferに適用すると人間が見る像と左右が逆になる。BGRはR先頭のバイト列が赤として出るよう設定されているので、ワイヤ上のバイトは並び順どおり(R,G,B)として解釈する。INVONはPicoCalcのガラスが`BLACK`を黒として出すために必要なもので、反転を適用すると背景が白になり実機と逆になる。実機像と食い違った場合、変換はcommand decoderではなくframebuffer切り出し側に置く。
