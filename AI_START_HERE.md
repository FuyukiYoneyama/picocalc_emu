# AI向け開始手順

このファイルを最初に読みます。ここに書かれている内容が、PicoCalc上で動く
アプリを作るときの短い正規手順です。過去の調査経緯や将来のエミュレーター設計は
この手順を上書きしません。

## このリポジトリの現在の目的

これは完成したPCエミュレーターではありません。実機で動作確認したRP2040用BSPと
アプリテンプレートを提供し、AIがLCD・SD・キーボード・音声・PSRAMの初期化を
推測で書かなくて済むようにするプロジェクトです。

現在のCanonical版はBSP `0.8.4`です。template の既存アプリ版名とは別に、実機で使用する対象は、ログ先頭の
`[PICOCALC][BOOT]`に出る`bsp`、`app`、`variant`、`git`で識別します。

## AIが行う正規手順

リポジトリのルートで実行します。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
```

生成物は常に次です。

```text
../MyApp/build/picocalc_app.uf2
```

PicoCalcのSDカード上でファイル名を管理するため、UF2名と場所を変更しません。
実機へコピーする前に、ビルドが出力するSHA-256と実機ログ1行目を記録します。

## AIが変更してよい場所

通常のアプリ開発で変更するのは、生成されたプロジェクトの次だけです。

```text
MyApp/app/main.cpp
MyApp/assets/       （必要な場合だけ）
```

LCDのGPIO、LCD初期化、転送形式、SD初期化、キーボードI2C、PSRAMクロックを
`app/`へコピーして書き直してはいけません。公開ヘッダーのAPIを呼びます。
生成された`MyApp/bsp/`は、そのプロジェクトが使用するBSPの固定コピーです。
`board_generated.h`はJSON profileから生成されるため直接編集しません。

BSPやprofileを変更する作業は通常のアプリ作業ではありません。変更する場合は、
変更理由、source fingerprint、host test、実機検証を同じコミットに記録します。

## LCDはA/Bから一つだけ選ぶ

AとBは同じドライバに統合しません。個体や目的に応じてビルド時に一つを選びます。

| variant | 用途 | 実際の転送 |
|---|---|---|
| `pio-rgb565`（B、推奨） | 通常のアプリ | PIO0 blocking、RGB565、2 bytes/pixel、LCD DMA OFF、clkdiv 2.0 |
| `hwspi-rgb888`（A） | 互換・bring-up・診断 | SPI1 blocking、RGB666 wire、3 bytes/pixel、25 MHz |

アプリの公開画素形式は常にRGB565です。Aの3-byte転送をBへ持ち込んだり、Bの
PIO転送をAへ持ち込んだりしません。選択例は次です。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
python3 tools/picocalc.py build --project ../MyApp --lcd-variant hwspi-rgb888
```

実機検証は同時に二つ行わず、一つずつ同じ
`../MyApp/build/picocalc_app.uf2`を生成します。A/Bの判定はUF2名ではなく、
ログ先頭の`variant`と`app_status`で行います。

## PSRAMの制約

PSRAMは8 MiB、PIO1、CS/SCK/MOSI/MISOはGP20/21/2/3です。250 MHz通常起動の
推奨候補は、最初に`clkdiv=2.0/fudge=false`（62.5 MHz）を使い、失敗時だけ
`3.0/false`、`1.5/true`へ進みます。高速候補を通常設定へ勝手に追加しません。

公開APIのread/writeはBSP内部で最大24 byteへ分割されます。PSRAMは任意機能で、
起動ログが`status=unavailable`ならSRAMとして扱わず、アプリ側で代替動作を選びます。
LCD更新との共存速度を測るときだけ、B専用の次のモードを使います。

```sh
python3 tools/picocalc.py build --project ../MyApp \
  --lcd-variant pio-rgb565 --psram-lcd-coexist-test
```

## 音声の扱い

既定の`PICOCALC_AUDIO_REFERENCE_TONE=ON`は、実機動作確認済みの固定1 kHz音を
`picocalc::init()`中に開始します。標準テンプレートはLCDのGRAM検証が終わった直後に
`picocalc::audio::stop()`を呼び、次のログを出します。

```text
[PICOCALC][AUDIO] status=stopped reason=lcd_verify_complete
```

PCMを使うアプリは、`PICOCALC_AUDIO_REFERENCE_TONE=OFF`でビルドし、
`audio::init()` → `audio::write_sample()` → `audio::start()`の順に使います。
不要になったら必ず`audio::stop()`を呼びます。最小例は
`templates/rp2040-basic/examples/audio_stream.cpp`です。

## 実機ログの合格判定

画面だけで合否を判断しません。最低限、次を順番に確認します。

1. 最初の行が`[PICOCALC][BOOT]`で、意図した`bsp/app/variant/git`である
2. LCD各色の`[PICOCALC][LCD][VERIFY] ... status=pass`が出る
3. `[PICOCALC][LCD][VERIFY] app_status=pass`が出る
4. BではRAMRDの`format=rgb565`と期待値が一致する
5. LCD検証直後に音声停止ログが出る
6. SDの`[PICOCALC][SD][SMOKE] stage=end status=ok`が出る
7. キーボードを操作し、Pressed/Releasedイベントが記録される

LCDの`app_status=pass`は、塗りつぶしと既知パターンをGRAMから読み戻し、公開APIの
RGB565値と一致したという意味です。`stage=end status=drawn`だけではreadback合格を
意味しません。

## 版管理

実機に渡す版は、版番号またはサブコメントをソースへ反映してからコミットし、その
コミットからUF2を生成します。UF2自体は保存・コミットせず、同じ名前で再生成します。
ブランチを統合するときも、資産を捨てず、必要なソース・文書・検証をすべて統合します。

## 参照先の読み方

- `README.md`: プロジェクト全体の入口と現在の状態
- `templates/rp2040-basic/README.md`: 生成後のビルドと起動時スモーク
- `bsp/README.md`: 固定ハードウェア契約
- `docs/IMPLEMENTATION_STATUS.md`: 実装済み範囲と実機確認状況
- `REQUIREMENTS.md`: 将来のエミュレーターを含む要求仕様
- `docs/DESIGN.md`: 未実装エミュレーターの将来設計
- `docs/LCD_INVESTIGATION_20260729.md`: LCD問題の過去の調査記録。手順の根拠ではあるが、
  古いUF2やコミットを現在版として再利用しない
