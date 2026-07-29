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

SD 成功時は LCD 中央下部が緑、失敗時は赤になります。UART/USB CDC には
`[PICOCALC]` で始まる機械可読ログを出力します。検証用ログには LCD の期待色・領域、
SD の実行シーケンスと失敗段階、キーボードイベントの通番が含まれます。

## 開発規約

- 原則として変更するのは `app/` のみです。
- GPIO、LCD 初期化、LCD転送形式、SD初期化手順を変更しないでください。
- BSP 更新が必要な場合は、先に `python3 tools/verify_environment.py` 相当の
  契約検査を通し、実機成功根拠を追加します。
