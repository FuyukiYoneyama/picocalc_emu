# Validation records

実機検証後、`../template.json`を基にしたJSON記録と、その記録から参照するログ・
写真・動画・traceをここへ保存する。

2026-07-30時点では、A（`hwspi-rgb888`）のLCD/SD/keyboard、B（`pio-rgb565`）のLCD/SDが
個別に実機合格している。台帳の`overall_status=pending`は、未試験項目または基板revision・
SDカード識別情報が未記入であることを表し、個別テストの`pass`を取り消すものではない。

2026-08-01には、BのLCD更新中にPSRAM候補速度を検証した記録
`bsp-0.8.0-20260801-psram-coexist.json`を追加した。これは共存専用アプリの記録であり、
LCD/PSRAMの判定はpassだが、SD・keyboardを実行していないため`overall_status=pending`である。

同日の標準BSPスモーク結果は`bsp-0.8.0-20260801-standard-b.json`に記録した。
LCD・SD・keyboardはpass、PSRAMは83.3 MHzから62.5 MHzへフォールバックしてpassである。
