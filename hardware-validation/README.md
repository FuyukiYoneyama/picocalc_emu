# Canonical BSP実機検証台帳

ここには、参照プロジェクトではなく、このリポジトリからビルドしたCanonical BSP
自身の実機結果を保存する。

## 検証セッションの作成

1. `template.json`を`records/bsp-0.1.0-YYYYMMDD-01.json`へコピーする。
2. 対象コミット、PicoCalc revision、toolchain、SDカード情報を記入する。
3. UF2をビルドし、`sha256sum build/picocalc_app.uf2`を記録する。
4. UART/USB CDCログ、LCD写真、必要なら動画やlogic analyzer traceを
   `records/<validation_id>/`へ保存する。
5. LCD、SD、keyboardを個別判定する。
6. 3項目がすべて成功し、証拠ファイルを登録した場合だけ
   `overall_status`を`pass`にする。
7. `python3 tools/verify_environment.py`で台帳を検査する。

## 必須判定

- LCD: 320x320表示、向き、RGB色、白黒領域、表示崩れの有無
- SD: `mount/write/sync/read/compare/remove`の全段階
- keyboard: 複数キーについてpress/releaseイベントとUARTログ

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
