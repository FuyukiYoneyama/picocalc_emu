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
加えて、8 MiB PSRAMのread/write自己検証と音声経路を起動します。既定値では
`Picocalc_ment`からコピーした固定1 kHz/-6 dBFS PWM/DMA参照試験です。
`-DPICOCALC_AUDIO_REFERENCE_TONE=OFF`にすると、PCMを投入して開始する汎用stream経路を
使います。どちらもログの先頭行と`[PICOCALC][AUDIO][VERIFY] mode=`で識別できます。

推奨表示デフォルトはLCD B（`pio-rgb565`）です。アプリ／LCDラッパーはRGB565、
LCDバスは2 bytes/pixel、転送はPIO0 blockingで、LCD DMAは使用しません。
LCD A（`hwspi-rgb888`）は互換・診断用として明示指定できます。

SD 成功時は LCD 中央下部が緑、失敗時は赤になります。UART/USB CDC には
`[PICOCALC]` で始まる機械可読ログを出力します。検証用ログには LCD の期待色・領域、
SD の実行シーケンスと失敗段階、キーボードイベントの通番が含まれます。

LCD A（`hwspi-rgb888`）はloader-style SPI1/RGB666 3-byte containerの専用vendorドライバ、LCD B
（`pio-rgb565`）は実機動作済みPIO/RGB565ドライバを使用します。選択した版はログ先頭の
`variant`、`app`、`git`で識別します。
PSRAMは`pico_rescue`の候補順（`fudge=true`のclkdiv 1/1.5/2/3/4、続いて
`fudge=false`の同じ候補）をそのまま使用します。起動ログの
`reference=pico_rescue`、`[PICOCALC][PSRAM][VERIFY]`、`[PICOCALC][PSRAM][PROBE]`
を確認してください。

個別機能の最小コピペ例は`examples/`にあります。LCD、キーボード、SD、PSRAM Buffer、
PCM音声をそれぞれ単独でアプリへ追加できます。例は既定ターゲットへ自動リンクせず、
テンプレートのスモークテストを壊さないようにしています。

## 開発規約

- 原則として変更するのは `app/` のみです。
- GPIO、LCD 初期化、LCD転送形式、SD初期化手順を変更しないでください。
- BSP 更新が必要な場合は、先に `python3 tools/verify_environment.py` 相当の
  契約検査を通し、実機成功根拠を追加します。
