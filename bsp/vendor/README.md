# Vendored LCD driver (do not edit)

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

## 規約

- **このディレクトリのファイルを編集しない。** 修正が必要なら取得元を直し、コピーを
  取り直して上記のSHA-256とcommitを更新する。
- `bsp/src/display_pio_rgb565.cpp`は薄いアダプタに徹する。転送・初期化・タイミングを
  アダプタ側で作り直さない。
- `tools/picocalc.py verify`が`vendor-lcd-pio-unmodified`でSHA-256を照合する。

## 上位で守る呼び出し規約

`game/pico_skyace/src/platform/picocalc_display.cpp`と同じ粒度で呼ぶ。

- `lcd_rgb565_pio_set_window()`は160×160以下の矩形につき1回
- 画素は`lcd_rgb565_pio_write_blocking()`を160ピクセル単位で呼んで送る
- ウィンドウを再送せず、GRAMアドレスの自動インクリメントに任せる
