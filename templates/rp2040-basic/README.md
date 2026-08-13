# PicoCalc RP2040 application template

このテンプレートは、実機で動作した LCD・SD・キーボード処理を
`bsp/` に固定し、通常のアプリ開発を `app/` 内に限定するためのものです。
リポジトリ全体から使い始めるAIは、リポジトリrootの`USER_GUIDE/README.md`を先に
読んでください。監督・実機依頼など高度な運用が必要な場合だけ、rootの
`AI_START_HERE.md`を追加で読みます。生成後のプロジェクトへコピーされたこのREADMEからrootへの相対
リンクは作らず、生成先でも壊れない説明にしています。

## Build

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
cmake -S . -B build -DPICO_BOARD=pico -DPICOCALC_LCD_VARIANT=pio-rgb565
cmake --build build -j
```

直接CMakeでも、`.picocalc-project.json`に固定されたBSP生成元commitと`bsp/`全体SHA-256を
読みます。外側のアプリGit commitを`bsp_git`として継承しません。release buildで変更済みBSPを
拒否する場合はconfigureへ`-DPICOCALC_REQUIRE_CLEAN_BSP_PROVENANCE=ON`を追加します。

生成元リポジトリのtoolが利用できる場合は、build前に明示的にも検査できます。

```sh
python3 /path/to/picocalc_emu/tools/picocalc.py verify-project --project .
```

リポジトリのrootから生成・ビルドするときは、次のラッパーが版情報とUF2 SHA-256を
記録します。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
```

`tools/picocalc.py new` は template 作業ツリーの `build/` と
`.picocalc-build-history.json` を生成先へコピーしません。生成先の build cache と
UF2履歴は、新規プロジェクト自身のものだけを記録します。

LCD variantを省略して推測しません。Aを使うときだけ`hwspi-rgb888`を明示します。

書き込み対象は `build/picocalc_app.uf2` です。起動すると LCD テストパターン、
SD の mount/write/sync/read/compare/remove、キーボード待受を順に実行します。
加えて、8 MiB PSRAMのread/write自己検証と音声経路を起動します。既定値では
`Picocalc_ment`からコピーした固定1 kHz/-6 dBFS PWM/DMA参照試験です。
`-DPICOCALC_AUDIO_REFERENCE_TONE=OFF`にすると、PCMを投入して開始する汎用stream経路を
使います。どちらもログの先頭行と`[PICOCALC][AUDIO][VERIFY] mode=`で識別できます。
LCDの塗りつぶし・パターン・GRAM readback検証が完了すると音声を停止し、SD検証と
キーボード待受では発音しません。停止ログは
`[PICOCALC][AUDIO] status=stopped reason=lcd_verify_complete`です。

推奨表示デフォルトはLCD B（`pio-rgb565`）です。アプリ／LCDラッパーはRGB565、
LCDバスは2 bytes/pixel、転送はPIO0 blockingで、LCD DMAは使用しません。
LCD A（`hwspi-rgb888`）は互換・診断用として明示指定できます。

PSRAMとLCDの共存クロックを実機検証する専用モードは、次でビルドします。

```sh
python3 tools/picocalc.py build --project . \
  --lcd-variant pio-rgb565 --psram-lcd-coexist-test
```

このモードはLCD上で移動矩形を更新しながら、PSRAMの各候補clkdivで24-byteの
write/readを120回実行します。`[PICOCALC][PSRAM][COEX]`の各candidate行で
`display_failures=0`かつ`psram_failures=0`の候補が共存合格です。

SD 成功時は LCD 中央下部が緑、失敗時は赤になります。UART/USB CDC には
`[PICOCALC]` で始まる機械可読ログを出力します。検証用ログには LCD の期待色・領域、
SD の実行シーケンスと失敗段階、キーボードイベントの通番が含まれます。

LCD A（`hwspi-rgb888`）はloader-style SPI1/RGB666 3-byte containerの専用vendorドライバ、LCD B
（`pio-rgb565`）は実機動作済みPIO/RGB565ドライバを使用します。選択した版はログ先頭の
`variant`、`app`、`bsp_git`、`app_git`で識別します。
PSRAMは実機検証済みの通常候補を使用します。250 MHzでは`clkdiv=2.0/fudge=false`
→`3.0/false`→`1.5/true`、125 MHzでは`1.0/false`→`1.5/false`→`2.0/false`
→`3.0/false`→`4.0/false`の順です。起動ログの
`reference=pico_rescue`、`[PICOCALC][PSRAM][VERIFY]`、`[PICOCALC][PSRAM][PROBE]`
を確認してください。

個別機能の最小コピペ例は`examples/`にあります。LCD、キーボード、SD、PSRAM Buffer、
PCM音声をそれぞれ単独でアプリへ追加できます。例は既定ターゲットへ自動リンクせず、
テンプレートのスモークテストを壊さないようにしています。

通常のアプリ変更では`bsp/`、`profiles/`、`CMakeLists.txt`の版選択を変更しません。
変更が必要なら、BSP変更として検証・コミットしてからUF2を生成します。

## 開発規約

- 原則として変更するのは `app/` のみです。
- GPIO、LCD 初期化、LCD転送形式、SD初期化手順を変更しないでください。
- BSP 更新が必要な場合は、先に `python3 tools/verify_environment.py` 相当の
  契約検査を通し、実機成功根拠を追加します。
