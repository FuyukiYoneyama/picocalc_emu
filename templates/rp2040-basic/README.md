# PicoCalc RP2040 application template

このテンプレートは、実機で動作した LCD・SD・キーボード処理を
`bsp/` に固定し、通常のアプリ開発を `app/` 内に限定するためのものです。

## Build

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
cmake -S . -B build -DPICO_BOARD=pico
cmake --build build -j
```

書き込み対象は `build/picocalc_app.uf2` です。起動すると LCD テストパターン、
SD の mount/write/sync/read/compare/remove、キーボード待受を順に実行します。
加えて、8 MiB PSRAMの安全クロックprobe/read/write自己検証と、48 kHz PWM/DMA音声
ストリームの初期化を行います。音声は初期化時には発音せず、PCMを投入してから
`picocalc::audio::start()`を呼びます。

SD 成功時は LCD 中央下部が緑、失敗時は赤になります。UART/USB CDC には
`[PICOCALC]` で始まる機械可読ログを出力します。検証用ログには LCD の期待色・領域、
SD の実行シーケンスと失敗段階、キーボードイベントの通番が含まれます。

LCD A（`hwspi-rgb888`）はloader-style SPI1/RGB888の専用vendorドライバ、LCD B
（`pio-rgb565`）は実機動作済みPIO/RGB565ドライバを使用します。選択した版はログ先頭の
`variant`、`app`、`git`で識別します。
PSRAMの安全方針は、250 MHz時にclkdiv 1.5/2/3/4のみを試し、既知のREAD8失敗条件である
1.0/1.2を試さないことです。起動ログの`[PICOCALC][PSRAM][POLICY]`、
`[PICOCALC][PSRAM][VERIFY]`、`[PICOCALC][PSRAM][PROBE]`を確認してください。

## 開発規約

- 原則として変更するのは `app/` のみです。
- GPIO、LCD 初期化、LCD転送形式、SD初期化手順を変更しないでください。
- BSP 更新が必要な場合は、先に `python3 tools/verify_environment.py` 相当の
  契約検査を通し、実機成功根拠を追加します。
