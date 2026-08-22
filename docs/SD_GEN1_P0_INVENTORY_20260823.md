# SD-GEN-1-P0 現状棚卸し

実施日: 2026-08-23  
状態: **部分完了（source inventoryとU6 clean traceを固定。代表アプリtraceは未完）**

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
export／再attach、CPU／PPU／core 1／DMA XIPを固定している。ただし現在のrunner-manifestは
SD wire traceを保存していない。したがって、M-NESCOのSD command使用範囲はP0の未完項目として
扱い、既存のM-NESCO PASSをSD-GEN-1のtrace証拠へ流用しない。

### FAT16／FAT32代表経路

hostのpack／extractとSD image unit testは既存回帰で保護されている。しかし、FatFs firmware
のclean wire traceをSD-GEN-1用に固定したrecordはまだない。FAT filesystemの回帰と、SD
wire protocolの回帰を混同しない。

## 3. P0で残る採取項目

1. M-NESCO診断BINをclean backendで起動し、SD traceを3回取得する（ROMの絶対pathは記録しない）。
2. FAT16／FAT32を読む代表firmwareまたは既存sampleをclean backendで起動し、各3回取得する。
3. 各traceについて、command集合、token、CRC、CS epoch、block境界、unknown/errorを集計する。
4. P1のwire契約に移す候補と、未観測のため保留する候補を分ける。

代表firmwareが用意できない場合は、無理にproduction codeを追加せず、synthetic protocol契約を
先に作成する。その場合も「実アプリで観測済み」とは記録しない。

## 4. P0完了条件

- 現行source inventoryがレビュー済みである。
- U6 clean traceのcommand集合とdigestが再計算できる。
- M-NESCOとFAT16/FAT32について、trace取得済みまたは「入力不足」と理由付きで保留されている。
- P1へ渡すcommand/state候補と、未対応のまま残す範囲が一覧化されている。

P0完了後に初めて、P1のwire契約とsynthetic test vectorを固定する。P0の途中ではCMD18／CMD12／
CMD23／CMD25のproduction実装を開始しない。
