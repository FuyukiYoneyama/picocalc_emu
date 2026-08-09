# NEXT-2A実機証拠採取 attempt 1

2026-08-09に、`picocalc-multicore-r1`と同じbuildから生成した固定UF2をClockworkPi
PicoCalcへ書き込んだ。提出写真では`NEXT2 MULTICORE`の最終画面に
`LAUNCH`、`FIFO`、`WFE SEV`、`IRQ1`、`OVERALL`の5項目がすべて緑の`PASS`として表示された。
固定アプリでは各表示が対応する固定word、4 vector、WFE前後stage、IRQ回数と受信wordの完全一致から
導出されるため、実機の機能観測はpassである。

一方、2回のserial captureはともに0 byteだった。v1アプリは各markerを一度だけ出し、エミュレーター
測定では起動後615 msで最終markerまで完了し、その後は画面を保持して出力しない。さらに
`stdio_init_all()`が使う`pico_stdio_usb`の既定
`PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS`は0で、CDC接続を待たない。したがってUSB CDCの列挙とmonitor
openが出力後なら、実機が正常でも全文が失われる。この設計は人間に起動前captureを要求した手順と、
PicoCalc USB Type-Cのnative USB CDC列挙を同一視した証拠採取上の欠陥だった。

凍結したv1契約はUART全文と最終写真の両方を要求するため、写真だけを根拠に契約を書き換えず、正式な
hardware correlationは未完了として残す。機能FAILや`emulator PASS -> hardware FAIL`には分類しない。
後続v2はphase、固定値、初回marker、最終画面を変更せず、最終判定後に同じ完全なmarker blockを周期
再送する。これによりUSB CDCを後から開いても、キー入力や接続タイミング合わせなしで証拠を取得する。

`final.jpg`は提出された`IMG_8948.JPG`の画素を変更せず、EXIF、GPS、XMP、maker notes、MPFを除去した
格納版である。ICC profileは保持し、原本と格納版のdecoded RGB SHA-256はともに
`0e02149b88ef10e8061561696601a949b81d757b78d874884137e3dd1efca089`である。
