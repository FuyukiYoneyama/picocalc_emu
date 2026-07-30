# Validation records

実機検証後、`../template.json`を基にしたJSON記録と、その記録から参照するログ・
写真・動画・traceをここへ保存する。

2026-07-30時点では、A（`hwspi-rgb888`）のLCD/SD/keyboard、B（`pio-rgb565`）のLCD/SDが
個別に実機合格している。台帳の`overall_status=pending`は、未試験項目または基板revision・
SDカード識別情報が未記入であることを表し、個別テストの`pass`を取り消すものではない。
