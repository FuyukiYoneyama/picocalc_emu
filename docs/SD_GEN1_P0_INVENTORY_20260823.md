# SD-GEN-1-P0 現状棚卸し

実施日: 2026-08-23  
状態: **完了（source inventory、U6 clean trace、M-NESCO A/B trace、FAT16/FAT32 traceを固定）**

この文書は、SD-GEN-1のproduction実装を承認する文書ではない。現行モデルで確認できる
範囲と、次に取得すべき一次traceを分離するための作業記録である。

## 1. 現行production model

対象: `picoem-picocalc/crates/picocalc-board/src/sdcard.rs`

| 項目 | 現状 |
|---|---|
| 初期化 | CMD0、CMD8、CMD55+ACMD41、CMD58 |
| single-block read | CMD17、R1→`0xFE` token→512 bytes→CRC16 |
| single-block write | CMD24、data token→512 bytes→CRC16→data response |
| block length | SDHCの512 bytes固定。CMD16は受理するだけ |
| command CRC | CMD0/CMD8を検査。その他はwire値をtraceへ記録 |
| storage | memoryまたはRAW file-backed。run中はCOW overlay、exportはatomic |
| CS | epochをtraceへ記録。deselectでCS状態を破棄 |
| busy | 初期化pollのbusyは再現する。write完了後の実時間busyは未実装 |
| multi-block | CMD18/CMD25/CMD12/CMD23は未実装 |
| removal／write-protect | 未実装 |

未知commandは`unknown_commands`へ記録し、正常な汎用互換性を装わず可視化する。P0時点で
このfail-closed方針は変更しない。

## 2. clean traceで確認済みの範囲

### U6固定版uf2loader

証拠: `firmware-validation/evidence/uf2loader-u6-20260822-01/run-01/sd-trace.json` 〜
`run-03/sd-trace.json`

- 3回とも`event_count=970`、digestは
  `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3`
- previewで観測されたcommandはCMD0、CMD8、CMD17、ACMD41、CMD55、CMD58のみ
- CMD17は470回。CMD18/CMD12/CMD23/CMD24/CMD25は観測されない
- traceあり／なしのU6 report・UARTは既存Gateで一致済み

この結果は固定版uf2loaderの受入範囲を示すだけで、汎用SD互換性の根拠にはしない。

### M-NESCO拡張

`firmware-validation/evidence/m-nesco-ext-20260822-01/`は、SD sourceとROM SHA、flash
export／再attach、CPU／PPU／core 1／DMA XIPを固定している。P0では通常menu buildを使って
mapper 2のRun A/B traceを各3回再採取し、`sd:/TEST.NES`→`flash:/TEST.NES`のpath契約を
閉じた。証拠は[`sd-gen1-p0-20260823-02`](../firmware-validation/evidence/sd-gen1-p0-20260823-02/)へ固定した。
旧autostart buildで採取したRun Aのみのrecord（`sd-gen1-p0-20260823-01`）は履歴として保持するが、
今回のP0完了判定は新しい通常menu recordを使う。既存のM-NESCO受入recordをwire traceの代替にはしない。

再採取時は`tools/mnesco_ext.py --retain-sd-traces <evidence-dir>`を使い、各runのtrace JSONを
一時ディレクトリの終了前に保存する。このオプションは既定OFFで、既存の受入結果やreportを変更しない。

ソース棚卸しでは、`Picocalc_NESco/drivers/sdcard.c`がCMD17をsectorごとに発行し、
CMD24をsectorごとのwriteに使い、CMD9でCSDを読むことを確認した。CMD18/CMD12/CMD23/
CMD25の呼び出しは見つからない。これは実traceの代替ではないが、M-NESCO側でmulti-block
を推測追加する根拠がないことを補強する。

### FAT16／FAT32代表経路

hostのpack／extractとSD image unit testは既存回帰で保護されている。P0では同じmapper 2 ROMを
決定的にpackしたFAT16／FAT32 imageを通常menu firmwareで各3回読み、clean wire traceを
[`sd-gen1-p0-20260823-02`](../firmware-validation/evidence/sd-gen1-p0-20260823-02/)へ固定した。
FAT filesystemの回帰と、SD wire protocolの回帰は引き続き別に扱う。

M-NESCOのFatFs diskioは`disk_read`／`disk_write`の`count`を受け取るが、下位の
`sdcard_read_sectors`／`sdcard_write_sectors`は現状1 sectorずつCMD17／CMD24を発行する。
P1では、`count > 1`が実際に渡る別アプリまたはsynthetic契約を対象にし、そのときのwire列を
現行single-block列と分けて受入matrixへ記載する。

## 3. P0で完了した採取項目

1. M-NESCO通常menuのA/Bをclean backendで各3回取得した（ROMの絶対pathは記録していない）。
2. FAT16／FAT32代表imageをclean backendで各3回取得した。
3. 各traceのcommand集合、token、CRC、CS epoch、block境界、unknown/errorを集計した。
4. P1へ移す候補と、未観測のため保留する候補を分けた。

P1で別アプリの代表firmwareが用意できない場合は、無理にproduction codeを追加せず、synthetic
protocol契約を先に作成する。その場合も「実アプリで観測済み」とは記録しない。

## 4. P0完了条件

- 現行source inventoryがレビュー済みである。
- U6 clean traceのcommand集合とdigestが再計算できる。
- M-NESCOとFAT16/FAT32について、3回deterministic traceを取得した。
- P1へ渡すcommand/state候補と、未対応のまま残す範囲が一覧化されている。

P0完了後に初めて、P1のwire契約とsynthetic test vectorを固定する。P0ではCMD18／CMD12／
CMD23／CMD25のproduction実装を開始していない。P1で別アプリの一次traceまたはsynthetic契約が
確定するまで、これらは未対応・可視化fail-closedのままとする。
