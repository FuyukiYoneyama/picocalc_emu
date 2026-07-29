# LCD不動作調査記録（2026-07-29）

## 対象

対象ログ：`/home/fuyuki/pico_dvl/log/tt260729173036.log`

対象UF2はBSP `0.1.2`、App `0.1.1-readback`。ログ上、GPIO、PIO、LCD初期化コマンド、
LCDへのピクセル転送処理は最後まで実行された。しかし、`RAMRD (0x2e)`による読み出しは
4ピクセルすべて`0x0000`で、LCD書き込み成功は証明できなかった。

## 全実働プロジェクトとの比較

| プロジェクト | リセット解除後の待機 | 備考 |
|---|---:|---|
| `picocalc-life` | 10ms | メイン側でLCD初期化前に100ms待機 |
| `Picocalc_Clock` | 200ms | `picocalc_lcd_hw_baseline.cpp` |
| `Picocalc_ClockCalc` | 200ms | `picocalc_lcd_hw_baseline.cpp` |
| `Picocalc_ment` | 200ms | `picocalc_display.cpp` |
| `Picocalc_BVWCVolleyball` | 200ms | `picocalc_display.cpp` |
| `pico_skyace` | 10ms | メイン側でLCD初期化前に100ms待機 |
| `pico_rescue` | 別実装 | 共通BSPの直接根拠からは除外 |

`picocalc_emu`はLCD初期化前に200ms待機していたが、LCDリセット解除後は10msのままだった。
これは、解除後200msを採用して実機成功している4プロジェクトとの明確な差分である。

## 修正

`bsp/src/display.cpp`の`reset_panel()`に、リセット解除後の200ms待機を追加した。
版番号をBSP `0.1.3`、App `0.1.2-lcd-reset-timing`へ更新した。

## 判定

この修正後のUF2を実機へ書き込み、LCD画面と`[PICOCALC][LCD][VERIFY]`を再確認する。
`app_status=pass`になるまでBSP完成とは判定しない。

## 検証用UF2ビルド記録

このスレッドの会話記録上、今回の検証用UF2は**8回目に生成したUF2**である。
これは実機ログの本数ではなく、私がこのスレッド内で実行したUF2生成ビルドの回数である。

| 項目 | 値 |
|---|---|
| ビルド日時（UTC） | `2026-07-29T08:37:12Z` |
| BSP | `0.1.3` |
| App | `0.1.2-lcd-reset-timing` |
| UF2 SHA-256 | `783ac18d9360c6b6907c67f7185370a237c055a8986781cb3d097ef990abb8d4` |
| 履歴ファイル | `templates/rp2040-basic/.picocalc-build-history.json` |

### スレッド内のUF2生成ビルド通番

| 回数 | 内容 | UF2 SHA-256（確認できるもの） |
|---:|---|---|
| 1 | 初期BSPビルド | `54acdbc0a518f3f3b158866df9fdd2b3e5d7570e2178b6c66dc8dae2896babde` |
| 2 | LCD読み出し追加後 | `50c58eff35adad802ca6d4821f720d731013e1e002de1afd5d96253696f89f3c` |
| 3 | 版番号・ビルド時刻表示修正後 | `babdb44f1ec08142d5389ea84f1d129960e6a9aaa4e53321686bc35969c69ea1` |
| 4 | ビルド履歴機能の初回ビルド | `43c6266389a610a332478e363b4e71a54e411fc76f5449cb86241f9937a37872` |
| 5 | 同一版の2回目ビルド | `2038780b5af2faf609ac3b6a34dc3d6abfd8f0850a3a696c1a9fdcb9fecfeffd` |
| 6 | 履歴保存先変更後のビルド | `b4acd30d6702769ef2df9b12521d69954753d04417672b792dc719219295fdfa` |
| 7 | リセットタイミング修正後の直接CMakeビルド | 未記録 |
| 8 | リセットタイミング修正後の正式ビルド | `783ac18d9360c6b6907c67f7185370a237c055a8986781cb3d097ef990abb8d4` |

### 実機検証ログの通番

| 回数 | ログ | 判定・識別情報 |
|---:|---|---|
| 1 | `tt260729163011.log` | 初期BSP、LCDログ未詳細 |
| 2 | `tt260729164457.log` | 初期BSP、LCDログ未詳細 |
| 3 | `tt260729165556.log` | 初期BSP、LCDログ未詳細 |
| 4 | `tt260729170656.log` | BSP `0.1.1`、LCDログ詳細化前 |
| 5 | `tt260729171221.log` | BSP `0.1.1`、LCD読み出し検証失敗 |
| 6 | `tt260729173036.log` | BSP `0.1.2`、LCD読み出し検証失敗 |
| 7 | `tt260729173939.log` | BSP `0.1.3`、リセット解除後200ms版 |
