# NEXT-1 PicoEdit実機相関メモ

2026-08-09に、`picoedit-r1`でエミュレーター合格したBINと同じbuildから生成したUF2を
ClockworkPi PicoCalcへ書き込み、FAT32 SDカード上で実行した。

実機はBSP 0.9.0、PSRAM、SD初期化、61-byte seedのload、検索、編集、64-byte outputの
save/readbackをすべて合格した。UARTには同じ内容のSAVE PASSが3回記録されている。SDカードでは
`OUTPUT.TXT`と`OUTPUT.BAK`が期待値とバイト一致し、`OUTPUT.TMP`は残っていなかった。

操作中には検索欄の誤入力と編集文字の誤入力があり、どちらもBackspaceで修正して合格へ到達した。
したがって、この試験は長い連続キー列を無誤入力で完遂することを要求せず、手順書の回復経路が
実際に機能することも示した。

`final.jpg`は提出された`IMG_8947.JPG`の画素を変更せず、位置情報を含むEXIF/XMPだけを除去した
リポジトリ格納版である。原本はリポジトリへ格納していない。原本と格納版のdecoded RGB SHA-256は
ともに`23d4b70922b8f7ea0bd50da6fd3a1bd480b7acbdc94c42c8ed0e2b4496d751b9`である。

この相関結果はPicoEdit v1と今回観測した経路についての
`emulator PASS -> hardware PASS`を示す。未知の全workloadについて一般的なfalse-accept率0を
主張するものではない。
