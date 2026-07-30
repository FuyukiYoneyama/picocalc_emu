# Canonical BSP実機検証台帳

ここには、参照プロジェクトではなく、このリポジトリからビルドしたCanonical BSP
自身の実機結果を保存する。

## UF2と版の扱い

PicoCalcではUF2をSDカードへコピーして使うため、UF2のファイル名は常に
`build/picocalc_app.uf2`とする。ブランチや特別な試験でも名前を変えない。
UF2ファイルは保存せず、試験対象のソースコミットから必要なときに再生成する。

版の識別には、ブランチ、ソースコミット、BSP版、アプリ版またはビルドサブコメント、
UF2 SHA-256を使う。対象UF2を起動したら、ログの1行目にある
`[PICOCALC][BOOT] bsp=... app=... git=... build=... compile=...`を最初に確認し、
その後のLCD・SD・keyboardの結果と結び付ける。検証版の識別情報を変更する場合は、
先にソースをコミットしてからUF2を作る。

## 検証セッションの作成

1. `template.json`を`records/<bsp-version>-<YYYYMMDD>-<sequence>.json`へコピーする。
2. 対象コミット、PicoCalc revision、toolchain、SDカード情報を記入する。
3. UF2をビルドし、`sha256sum build/picocalc_app.uf2`を記録する。
4. UART/USB CDCログ、LCD写真、必要なら動画やlogic analyzer traceを
   `records/<validation_id>/`へ保存する。
5. LCD、SD、keyboardを個別判定する。
6. 3項目がすべて成功し、証拠ファイルと装置情報を登録した場合だけ
   `overall_status`を`pass`にする。装置情報が未確定なら、個別テストの`pass`を保持した
   まま`overall_status`は`pending`にする。
7. `python3 tools/verify_environment.py`で台帳を検査する。

## 必須判定

- LCD: 320x320表示、向き、RGB色、白黒領域、表示崩れの有無、solid fillとGRAM readback一致
- LCDログ: `[PICOCALC][LCD][VERIFY] app_status=pass`、`RAMRD`の生バイト列、mismatch `0`
- SD: `mount/write/sync/read/compare/remove`の全段階
- keyboard: 複数キーについてpress/releaseイベントとUARTログ
- PSRAM: `[PICOCALC][PSRAM][POLICY]`、安全な`[PSRAM][PROBE]`、`[PSRAM][VERIFY] status=pass`、
  8 MiB範囲のread/write利用可否。250 MHzではfudge=trueのclkdiv 1.0/1.2を試していないこと、
  125 MHz側ではfudge=falseを使ったこと
- audio: `[PICOCALC][AUDIO][VERIFY] mode=... status=ok`、48 kHz、PWM wrap 255、carrier、
  DMA half/ring、underrunを確認する。reference-fixed-sineでは連続1 kHz音、streamでは
  PCM投入後の出力を別途記録する

実機試験はA（`hwspi-rgb888`）とB（`pio-rgb565`）を同じ標準UF2名で一つずつ行う。
片方の不合格はもう片方を廃棄する理由にならない。両方が`app_status=pass`になったため、
Canonical BSPのLCD検証は完了している。現在はBのキーボード試験と、両セッションの基板
revision／SDカード識別情報が未記入である。

BSP 0.6.0の音声とPSRAMは、ソース検査とA/BのRP2040ビルドを先に確認する。
実機記録はその後に作成し、Aの実機検証を行った後、同じ標準UF2名でBを検証する。
`pending`テンプレートは成功証拠ではない。`records/`に追加した記録だけが
Canonical BSP自身の証拠となる。記録形式は`schema.json`で定義する。
`build_log`と`evidence_files`はリポジトリルートからの相対パスで記入し、
検証器はファイルの存在とリポジトリ外へのpath traversalを検査する。

環境情報は次のコマンドで取得できる。

```sh
git rev-parse HEAD
arm-none-eabi-g++ --version
cmake --version
sha256sum build/picocalc_app.uf2
```
