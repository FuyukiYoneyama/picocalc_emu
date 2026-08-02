# Canonical BSP実機検証台帳

ここには、参照プロジェクトではなく、このリポジトリからビルドしたCanonical BSP
自身の実機結果を保存する。

## UF2と版の扱い

PicoCalcではUF2をSDカードへコピーして使うため、標準アプリのUF2名は常に
`build/picocalc_app.uf2`とする。ブランチや特別な試験でも名前を変えない。
UF2ファイルは保存せず、試験対象のソースコミットから必要なときに再生成する。
専用HV-1診断は別プロジェクトの固定名
`diagnostics/bsp-quality/build/PicoCalc_BSP_Diagnostic.uf2`を使う。どちらの
プロジェクトも、同じプロジェクト内で版ごとにUF2名を変えない。

版の識別には、ブランチ、ソースコミット、BSP版、アプリ版またはビルドサブコメント、
UF2 SHA-256を使う。対象UF2を起動したら、ログの1行目にある
`[PICOCALC][BOOT] bsp=... app=... variant=... bsp_git=... app_git=... build=...`を最初に確認し、
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
  8 MiB範囲のread/write利用可否。通常起動では250 MHzの実測合格候補だけを使い、
  共存検証モードだけが全候補を意図的に試験する。125 MHz側ではfudge=falseを使うこと
- audio: `[PICOCALC][AUDIO][VERIFY] mode=... status=ok`、48 kHz、PWM wrap 255、carrier、
  DMA half/ring、underrunを確認する。reference-fixed-sineでは連続1 kHz音、streamでは
  PCM投入後の出力を別途記録する

実機試験はA（`hwspi-rgb888`）とB（`pio-rgb565`）を同じ標準UF2名で一つずつ行う。
片方の不合格はもう片方を廃棄する理由にならない。過去のA/B表示はどちらも
合格済みであるが、0.8.3のBでRAMRDが3回中1回間欠失敗したため、現行0.8.8の
LCDとkeyboardは専用HV-1診断で再確認する。

BSP 0.8.8の推奨表示デフォルトはB（`pio-rgb565`、PIO blocking、LCD DMA OFF）である。
音声とPSRAMは、ソース検査とA/BのRP2040ビルドを先に確認する。
実機記録はその後に作成し、まずBの推奨デフォルトを検証した後、同じ標準UF2名で
Aの互換・診断経路を検証する。
PSRAMとLCDの共存確認では、先に`--psram-lcd-coexist-test`のUF2を実機へ書き込み、
各`[PSRAM][COEX]` candidate行を記録してから、通常のB標準ビルドへ戻す。
`pending`テンプレートは成功証拠ではない。`records/`に追加した記録だけが
Canonical BSP自身の証拠となる。記録形式は`schema.json`で定義する。

### HV-1: LCD/keyboard専用診断

`diagnostics/bsp-quality`は0.8.8台帳でpendingのLCDとkeyboardだけを検査する。
SDはmount/writeせず、audioも開始しない。LCD GRAM write/readbackを100回繰り返し、
Up/Down/Enter/EscapeのPressed/Hold/Releasedを誘導し、最後の
`[BSP_DIAG_VERDICT]`で合否を判定する。

```sh
python3 tools/picocalc.py build \
  --project diagnostics/bsp-quality \
  --lcd-variant pio-rgb565 \
  --build-timestamp YYYY-MM-DDTHH:MM:SSZ
sha256sum diagnostics/bsp-quality/build/PicoCalc_BSP_Diagnostic.uf2
```

`app=0.8.8-hv1-lcd-keyboard`、`variant=pio-rgb565`、`bsp_git`、`app_git`を
ログ先頭で照合する。

2026-08-01の共存検証では、LCD更新中のPSRAM合格設定を次のように確定した。

- 共存スイープ上の最高速度: `clkdiv=1.5 / fudge=true`、約83.3 MHz
- 通常運用の推奨: `clkdiv=2.0 / fudge=false`、62.5 MHz
- 合格: `clkdiv=2.0 / fudge=false`、62.5 MHz
- 合格: `clkdiv=3.0 / fudge=false`、約41.7 MHz
- 不合格: その他7候補

全候補で`display_failures=0`だったため、このセッションでの制約はLCDではなく
PSRAM転送条件である。詳細は`records/bsp-0.8.0-20260801-psram-coexist.json`を参照する。
標準BSPの通常起動では83.3 MHzで1 byte不一致が発生し、62.5 MHzへフォールバックした。
`build_log`と`evidence_files`はリポジトリルートからの相対パスで記入し、
検証器はファイルの存在とリポジトリ外へのpath traversalを検査する。

環境情報は次のコマンドで取得できる。

```sh
git rev-parse HEAD
arm-none-eabi-g++ --version
cmake --version
sha256sum build/picocalc_app.uf2
```
