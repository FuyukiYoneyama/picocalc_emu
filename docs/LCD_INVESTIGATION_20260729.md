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

## 追加調査（BSP 0.1.4）

BSP `0.1.3`でリセット解除後200msを追加してもRAMRDが全ゼロだったため、待機時間は
原因ではないと判定した。次の実働コード比較では、読み出し経路の構造は一致していたが、
Canonical BSPのログがMISO状態、コントローラ応答、生RAMRDバイト列を記録していなかった。

BSP `0.1.4`では、`picocalc-life`／`Picocalc_Clock`のRAMRD手順と、`Picocalc_NESco`の
読み出し診断方針を反映し、`RDDID (0x04)`、`RDDST (0x09)`、MISOアイドル、RAMRDダミー
バイト、各ピクセルの生バイト列を記録する。次回実機ログで、MISOが常時Lowなのか、
コントローラが応答しているのか、RGB565の読み出し位置だけがずれているのかを区別する。

## 追加調査（BSP 0.1.5）

BSP `0.1.4`ではRAMRDのCS Low区間中に`printf()`を実行していたため、実働プロジェクト
との差分を解消し、生バイトを配列へ保存してCS解除後に出力するよう変更した。また、
`pico_skyace`で実機確認済みのI2C1／アドレス`0x1f`／レジスタ`0x05`／書き込みマスク
`0x80`／輝度`220`／50ms間隔5回リトライによるバックライト強制点灯を追加した。

## 検証用UF2ビルド記録

このスレッドの会話記録上、今回の検証用UF2は**9回目に生成したUF2**である。
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
| 1 | 最初のBSP `0.1.0`ビルド（提示画像で確認） | `d37f7875032dfafcc116a4d5f27ff1cb9c7f19edf5c29ad6a9dee1cb81c35272` |
| 2 | 初期BSPビルド | `54acdbc0a518f3f3b158866df9dd2b3e5d7570e2178b6c66dc8dae2896babde` |
| 3 | LCD読み出し追加後 | `50c58eff35adad802ca6d4821f720d731013e1e002de1afd5d96253696f89f3c` |
| 4 | 版番号・ビルド時刻表示修正後 | `babdb44f1ec08142d5389ea84f1d129960e6a9aaa4e53321686bc35969c69ea1` |
| 5 | ビルド履歴機能の初回ビルド | `43c6266389a610a332478e363b4e71a54e411fc76f5449cb86241f9937a37872` |
| 6 | 同一版の2回目ビルド | `2038780b5af2faf609ac3b6a34dc3d6abfd8f0850a3a696c1a9fdcb9fecfeffd` |
| 7 | 履歴保存先変更後のビルド | `b4acd30d6702769ef2df9b12521d69954753d04417672b792dc719219295fdfa` |
| 8 | リセットタイミング修正後の直接CMakeビルド | 未記録 |
| 9 | リセットタイミング修正後の正式ビルド | `783ac18d9360c6b6907c67f7185370a237c055a8986781cb3d097ef990abb8d4` |
| 10 | BSP 0.1.4、生読み出し診断追加後 | `8ca3003f7807b6a175e2cc221dd39aed299f2d3cd8c188b34d46dccdb3ea7158` |
| 11 | BSP 0.1.5、読み出しログ位置修正・バックライト強制点灯後 | `ba96d318cd3b501a26fa15645b1fbc04a0262e10e27e129f5eb100ae5ef541e3` |
| 12 | BSP 0.1.6、LCD初期化クリアを赤`0xf800`へ変更後 | `65ea0e8684b730822cf6ad649af5fd93d6d88115801ebf47fb4b93a77d8331bc` |
| 13 | BSP 0.1.7、表示ON後の赤クリアを3秒保持 | `270412c88da27c5a8a854c5689c444c02dde7576f5c8446fb6ebaf8c1761e3ff` |
| 14 | BSP 0.1.8、実働多数派のリセット波形へ修正 | `598db1845e60a3b687fc998d45b83392b914564cda4807109ff9a75ccaf5da06` |
| 15 | BSP 0.1.9、LCD単独モードへ変更 | `ab1e7664416d0d30b3191b8537a75fc6df3942d8747b201e5700a3cc186ac035` |
| 16 | BSP 0.1.10、LCD初期化を停止しバックライトのみON | `4458f3bf1634b76093319f95c2e90c16ee1d37ba6d3a072d7d497ee9254215b8` |
| 17 | BSP 0.1.11、uf2loader準拠LCD初期化・RGB888転送へ修正 | `60e41039660448d3f06d809feaa2e54d4d14baf1748349f914a980b31807696b` |

## 追加調査（BSP 0.1.11）

`/home/fuyuki/pico_dvl/uf2loader/common/lcdspi/lcdspi.c` とヘッダーを直接比較した。
Canonical BSPは初期化コマンド列、`COLMOD`、および1ピクセルあたりの転送長がuf2loaderと一致していなかった。
uf2loaderの実働列へ合わせ、`COLMOD=0x66`、ILI9488のRGB888（3バイト/ピクセル）転送、
RGB888からRGB565へ戻す読み出し変換を実装する。

## 追加調査（BSP 0.1.10）

LCDコントローラ初期化、画面クリア、LCD RAM読み書き検証をすべて停止し、
PicoCalc側STM32のバックライト設定（I2C1、アドレス`0x1f`、レジスタ`0x05`、値`220`）だけを実行する。
この状態でランダムな表示が見えるかを確認し、LCD初期化経路とバックライト経路を分離判定する。

## 追加調査（BSP 0.1.9）

`tt260729191435.log`でもLCDは黒いままだったため、LCD以外の初期化・検証を全て停止する
LCD単独モードへ変更した。BSP起動ではLCDだけを初期化し、Appでは赤クリアと4ピクセルの
書き込み・読み出し検証だけを実行し、その後停止する。キーボードI2C、バックライト設定、
SD検出・初期化・FatFS、キー入力処理は実行しない。

## 追加調査（BSP 0.1.8）

`tt260729190949.log`では赤クリア転送は実行され、バックライト設定も成功していたが、
画面は黒いままだった。全実働プロジェクトを再確認した結果、Canonical BSPのリセット
波形だけが、実働多数派の`High 10ms → Low 10ms → High保持200ms`ではなく、
`High 1ms → Low 10ms → High 10ms → 待機200ms`になっていた。BSP `0.1.8`では、
実働`Picocalc_Clock`／`ClockCalc`／`ment`／`BVWCVolleyball`に合わせた。

## 運用版の復帰（2026-07-29）

uf2loaderのメニュー画面が残った状態に最も近かった初期BSP系列へ戻す要望により、
LCD/BSP/テンプレートの実行ソースを基準コミット`095e768`へ復帰した。

## BSP 0.2.0 の再構成（2026-07-29）

上記の復帰版は、後から追加された生成器・検証器・文書と整合せず、さらに実働
`uf2loader`との比較で判明したLCD契約（`COLMOD=0x66`、RGB888）も実行ソースへ
反映されていなかった。このため、過去の版番号を「実機で表示できた版」として
再利用せず、BSP 0.2.0を新しい検証対象として切り出した。

0.2.0では、次の条件を一つの契約へ統一した。

* LCDはSPI1、GP10/11/12、CS/DC/RSTはGP13/14/15、25 MHz
* `uf2loader`と同じ初期化列、`COLMOD=0x66`、MADCTL `0x48`
* アプリのRGB565 APIは維持し、LCDへはRGB888へ変換して送る
* リセットはHigh 10 ms → Low 10 ms → High保持200 ms
* 起動時に100 ms待機し、バックライトの明るさは変更しない

host transaction testとRP2040向けUF2ビルドは合格した。

## BSP 0.2.0 実機確認（2026-07-29）

実機試験には次のUF2を使用した。

* ログ: `/home/fuyuki/pico_dvl/codex/log/pico20260729_215722.log`
* BSP/App: `0.2.0`
* UF2 SHA-256: `fac9fc39e4733cf1bd36b7dcd6ae314f57ff22819be85d9c493f75b25102919d`

ログでは2回の起動とも、次の段階まで到達している。

* LCD: hardware SPI1、25 MHz、`COLMOD=0x66`、`init status=ok`
* SD: detect、初期化、mount/write/read smoke test が成功
* keyboard: `[PICOCALC][READY] keyboard=waiting`

実機観察では、uf2loaderから起動した場合はメニュー表示が残り、その後に電源を
OFF/ONするとノイズ画面になった。これは今回の試験で確認した意図した挙動として
記録する。

一方、バックライトはBSPが設定した値220で明るすぎた。BSP 0.2.1ではバックライト
レジスタへ固定輝度を書き込まず、起動時の既定状態をそのまま使うよう変更した。
0.2.1ではこのバックライト動作だけを変更し、LCD/SD/keyboardの初期化契約は維持する。

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

## 追加再構成（general/mcp資料を基準にした未実機確認版）

`pico20260729_225401.log`では、アプリ版`2d78418`が起動し、SDとキーボード処理も
完了したが、画面はuf2loaderメニューのままだった。したがって、UF2取り違えやCPU停止
ではなく、LCD書込み経路がパネルへ有効に届いていない。

`/home/fuyuki/pico_dvl/codex/general/01_DISPLAY_LCD.md`、
`general/lcd/src/main_hwspi_rgb888_probe.cpp`、`mcp`の索引結果、uf2loaderの実装を
突き合わせた結果、これまでのBSPには実機表示が記録された`general/lcd`の最小プローブに
対して次の相違があった。

- `spi_init(spi1, 25MHz)`より前にSPI機能へ切り替えていた
- `DISPON`前にBSPの`clear()`を実行していた
- RAMWRの1ウィンドウ全体をCS保持する資料実装に対し、画素列の途中でCSを再同期していた
- 既存の動作コードを無改変で移植せず、uf2loaderとの部分比較から独自の送信状態機械を作っていた

再構成版では、`general/lcd`のloader-style実装に合わせ、GPIO初期化、SPI初期化順序、
LCD初期化末尾、`CASET/RASET/RAMWR`の独立トランザクション、RGB888転送、160×160
タイル分割を採用した。RAMWRの各ウィンドウではCSを保持し、160ピクセルは変換バッファ
分割だけに使う。これは資料と動作実績に基づく再構成で
あり、実機での表示成功はまだ確認していない。成功判定は、起動ログの版と画面写真、
`[PICOCALC][LCD][VERIFY]`の結果を同時に確認して行う。

## `pico20260729_230811.log` の判定とRAMRD経路の修正

実機ログの先頭は、UF2が意図したコミットから生成されたことを示している。
`bsp=0.2.1`、`app=0.2.1-loader-rgb888`、`git=4ad2251`であり、UF2取り違えや
CPU停止ではない。SDのmount/write/read/compareも成功し、問題はLCD検証へ限定できる。

ただし、次の結果からLCDのGRAM読み出しは成立していない。

* `RDDID=0xffffff`、`RDDST=0x19920000`で、コントローラ応答として不自然
* `RAMRD`の全ピクセルが`0x202020`で、書き込んだ色と一致しない
* solid fill 5色とpattern readbackがすべてfailし、`app_status=fail`

また、アプリの`[PICOCALC][SMOKE] lcd=ok`はLCD検証結果を参照せず、SD結果だけで
表示していたため、`lcd=fail`を正しく出すよう修正した。

原因候補を一般化した独自SPI読み出しから、資料に記録された実働コードへ戻した。
書き込みは従来どおりhardware SPI1の25 MHzを使い、読み出し時だけ次の手順にする。

1. SPI1を停止する。
2. SCK/MOSI/MISOをGPIO SIOへ切り替え、SCK/MOSIを出力、MISOを入力にする。
3. CSを保持したままCASET、PASET、RAMRDをビットバンで送る。
4. falling側のサンプリングでダミー1バイトとRGB888の3バイト/ピクセルを読む。
5. 読み出し後にSPI1とSPI機能を復元する。

この経路は`general/01_DISPLAY_LCD.md`および`life`／`Picocalc_Clock`の実装に基づく。
修正後の実機ログで、`transport=bitbang_sio`、色ごとのreadback `pass`、
`[PICOCALC][LCD][VERIFY] app_status=pass`を確認するまで、LCD表示成功とは判定しない。

## 追加修正（BSP 0.2.2）

`pico20260729_231558.log`では、読み出し方式をbitbangへ変更しても
`RDDID=0xffffff`、`RAMRD=0x202020`が変化しなかった。これは読み出しだけでなく、
検証前のRAMWR書き込みが成立していない可能性を残す。

直前版の`send_solid_pixels()`と`write_pixels()`は、RAMWRデータ列の160ピクセルごとに
CSを解除していた。これはPIO系の長時間転送対策をhardware SPIへ誤って適用したもので、
`general/lcd/src/main_hwspi_rgb888_probe.cpp`の実装（RAMWR開始後、矩形全体をCS保持）と
異なる。BSP `0.2.2-loader-rgb888-held-cs`では、CSをRAMWRウィンドウ全体で保持し、
160ピクセルはRGB888変換バッファの分割に限定した。

## 追加修正（BSP 0.2.3）

`pico20260729_232111.log`でも、BSP `0.2.1`／App `0.2.2-loader-rgb888-held-cs`の
`cs=held_per_window`は確認できたが、`RDDID`、`RDDST`、RAMRDの値は前回と完全に同じで、
全色のreadbackがfailした。

公式`lcdspi.c`および`general/lcd/src/main_hwspi_rgb888_probe.cpp`を信号順序まで比較した
結果、`lcd_protocol.h`のhardware-SPI取引がDCをCS Lowの後で設定していた。公式実装は
DCを先に設定し、その後CSをLowにしてSPI送信する。BSP `0.2.3`ではこの順序を修正し、
host transaction testもこの電気的な順序を検査するよう変更した。さらに公式GPIO初期化に
合わせ、SPI機能設定前にSCK/MOSIを出力へ設定する。

## LCD BSPを二系統へ分離（BSP 0.3.0）

0.2.xでは、hardware SPI1/RGB888の送信と、PIO系資料の考え方を一つの実装へ混ぜて
しまっていた。そのため、どの既知動作コードを実機へ移植したUF2なのかを固定できず、
LCD書込みが成立しない版を重ねる結果になった。

0.3.0では、LCD実装を次の二つの独立BSPへ分離した。

* A `hwspi-rgb888`: `general/lcd/src/main_hwspi_rgb888_probe.cpp`／uf2loader系。SPI1、
  25 MHz、`COLMOD=0x66`、RGB888、RAMWRの各ウィンドウでCS保持。既存のhost transaction
  検査とRGB888 RAMRD診断をこのファイルだけが使う。
* B `pio-rgb565`: `general/lcd/src/lcd_rgb565_pio.cpp`のPIO0 blocking送信と、`life`の
  RAMRD手順。`COLMOD=0x65`、RGB565、`lcd_spi_min.pio`、読出し時だけPIOを停止してSIOへ
  切り替える。Aの`lcd_protocol.h`やhardware SPI送信処理は参照しない。

共通化したのは公開API、物理ピン、SD/keyboard、版管理だけである。CMakeの
`PICOCALC_LCD_VARIANT=hwspi-rgb888|pio-rgb565`で一方のソースだけをリンクする。
どちらをビルドしても生成物は同じ`build/picocalc_app.uf2`であり、実機ログの先頭行の
`variant`、`app`、`git`で識別する。UF2を別名保存して管理しない。

この時点で確認できたのは、両バリアントのRP2040コンパイルとportable検証である。
A/Bのどちらがこの個体のLCDを実機で駆動できるかは、各UF2を一度ずつ実機へ書き込み、
画面写真と`[PICOCALC][LCD][VERIFY] app_status=pass`をログで確認して確定する。

## `pico20260729_234804.log` の再判定（BSP 0.3.1）

0.3.0 A/Bを同一実機で比較した結果、識別ログは正しく、CPU・SD・keyboardは両方とも
動作した。しかしLCDは両方とも不合格だった。

* Aは`RDDID=0xffffff`、`RAMRD=0x202020`が従来どおりで、LCD応答が成立していない。
* Bは黒の初回読出しだけがpassし、白・赤・緑・青は全て`0x0000`のままだった。

資料との再比較で、0.3.0には二つの実装差分が残っていた。Aは実機表示済みのloader
probeが`set_sys_clock_khz(125000, true)`なのにBSP全体を250MHzで動かしていた。Bは
`main_pio_blocking_rgb565.cpp`の160×160象限分割を取り込まず、320×320を一つのPIO/CS
連続転送にしていた。

0.3.1では、Aを125MHz、Bを160×160以下のタイル転送へ修正した。これはA/Bを再び一つへ
混ぜる変更ではなく、各参照実装の実機条件をそれぞれのBSPへ戻す修正である。

## Aを先に実機検証する運用（2026-07-29）

実機では同時に二つのUF2を管理できないため、0.3.1の検証順を固定した。最初はA
`hwspi-rgb888`だけを作成し、標準の`build/picocalc_app.uf2`としてSDカードへコピーする。
Aのログ先頭で`variant=hwspi-rgb888`を確認し、LCDの
`[PICOCALC][LCD][VERIFY] app_status=pass`と画面写真を取得するまで、BのUF2は
作成・提示しない。Aが合格した後に、同じ場所・同じファイル名へBを生成する。

今回Aの実機試験用に生成したUF2は、ソースコミット`51380fa`
（BSP/App `0.3.1-hwspi-rgb888`）から作成した。UF2は保存・コミットせず、必要なら
このコミットから再生成する。

| 項目 | 値 |
|---|---|
| UF2 | `build/picocalc_app.uf2` |
| variant | `hwspi-rgb888` |
| source commit | `51380fa` |
| UF2 SHA-256 | `ae182a6947e46ee9f927e5dfc1b539a448b45f846cd5935eb69c9782dd802c4f` |
| 実機判定 | 未確認（次回Aを試験） |

## B（`pio-rgb565`）の電気的契約を実働2件へ戻す（BSP 0.3.2、2026-07-30）

実機報告は「Aはある程度表示する、Bは全く表示しない」。この非対称性を、ソースを
実働プロジェクトへ突き合わせて説明できる差分に限定した。BのHEAD（`8a3c344`）には、
どの実働実装にも存在しない条件が三つ残っていた。

### 差分1: リセット解除後の待機が10ms（最有力）

| 実装 | 解除後の待機 | 実機表示 |
|---|---:|---|
| `life/src/platform/picocalc_display.cpp` | 200ms | あり |
| `RTC/Picocalc_Clock`、`synth/Picocalc_ment`、`game/porting/Picocalc_BVWCVolleyball` | 200ms | あり |
| `bsp/src/display.cpp`（A） | 200ms | 部分的にあり |
| `bsp/src/display_pio_rgb565.cpp`（B、修正前） | 10ms | なし |

Bだけが`High 1ms → Low 10ms → High 10ms`で、10ms後に初期化コマンド列を送っていた。
解除後200msはAと実働4件が共有する条件であり、Aだけが表示するという観察と一致する。
0.3.2ではBを`High 10ms → Low 10ms → High 200ms`へ変更した。

### 差分2: RAMWRデータのCS保持が長すぎた

`c65b6a7`で、160ピクセル単位のCSトグルと160×160のタイル分割を削除し、矩形全体を
1回の`select()`〜`deselect()`で送る実装に戻していた。`clear()`では204,800バイトを
CS下げっぱなしで送る。これは`general/01_DISPLAY_LCD.md`§0の禁止事項であり、
§8.1が「同じウィンドウサイズでもCSの下げ方だけで表示が壊れた」と記録した条件その
ものである。0.3.2では実機動作済みの`game/pico_skyace`／
`general/lcd/src/main_pio_blocking_rgb565.cpp`と同じ粒度へ戻した。

* `CASET`/`RASET`/`RAMWR`はウィンドウごとに1回だけ送る
* ウィンドウは160×160以下のタイルに分ける
* RAMWRデータは160ピクセル（320バイト）ごとにCSを解放する
* ウィンドウは再送せず、GRAMアドレスの自動インクリメントに任せる

`life`はCSを矩形全体で保持していても表示するが、`life`と同じ31.25MHzでも個体差の
余地がある。0.3.2は軸ごとに「実働実績のある側で、より保守的な値」を選び、新しい値は
導入していない（clkdivは`life`の4.0、リセットは実働4件の200ms、CS粒度と
ウィンドウ上限は`pico_skyace`の160）。

### 差分3: `send_solid_pixels()`の転送量が矩形と一致しない

修正前は「320ピクセル×(count/320)行」を送っていたため、面積が320の倍数でない矩形
（例: 288×224）では最大319ピクセル分が転送されず、ウィンドウが埋まりきらなかった。
0.3.2では常に`count`ピクセルを送る。また`write_pixels()`は`count`をそのまま640バイトの
行バッファへ展開していたため、320ピクセルを超える呼び出しでバッファ外書き込みになる。
0.3.2では160ピクセル単位に分割して展開する。

### 付随修正: RAMRD後のPIO復帰

読み出しはPIOステートマシンを停止してSCK/MOSIをSIOへ渡すため、復帰時に
`pio_sm_clear_fifos()`／`pio_sm_restart()`／`pio_sm_clkdiv_restart()`と
プログラム先頭への`jmp`を行い、シフトカウンタ途中からの再開でバイト境界がずれない
ようにした。

### 判定方法

起動ログの`[PICOCALC][LCD][PIO]`行に`reset_ms=10/10/200`、`window_max=160x160`、
`cs=released_per_160_pixels`が出ることを確認し、そのうえで画面を見る。この個体では
`RAMRD`がAで`0x202020`、Bで`0x0000`を返し続けており、`app_status`は表示成否の判定に
使えない。0.3.2のB判定は画面写真で行い、`app_status`は参考値として扱う。

期待する画面は`draw_test_pattern()`の結果である。上端24pxが緑、下端24pxが青、内側に
白枠、その中に赤・緑・青の80×80が横並び、最後にSDスモーク結果の帯（成功で緑、失敗で赤）。

### 0.3.2 B検証用UF2

| 項目 | 値 |
|---|---|
| UF2 | `templates/rp2040-basic/build/picocalc_app.uf2` |
| variant | `pio-rgb565` |
| BSP / App | `0.3.2` / `0.3.2-pio-rgb565-reset200ms-cs160` |
| source commit | `6b2718d055c1` |
| build（UTC） | `2026-07-30T12:52:44Z` |
| UF2 SHA-256 | `16ccb91178bac9f3b2d18b0a2e67cdef9e6cc94a299cf9a69e4c3dc9d302f0f4` |
| 実機判定 | 未確認（次回Bを試験） |
