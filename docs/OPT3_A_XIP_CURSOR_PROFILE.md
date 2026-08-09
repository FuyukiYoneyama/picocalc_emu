# OPT3-A immutable-XIP decode cursor profile

## 結論

OPT3-Aの計測は完了した。次は**短いimmutable-XIP decode cursor**のfeature-gated試作
（OPT3-B）へ進む。長いbasic blockをまとめて実行する設計は選ばない。

PicoTetrisではimmutable XIPのdecode-cache hit率は99.8287%だったが、hit-only直線runは平均
4.563命令である。hit命令massの50.3433%は長さ4以上、27.2919%は8以上だが、32以上は
0.5468%しかない。終了37,776,562件のうち37,756,069件はpost-execute PC redirectだった。

この分布はcursor再利用の機会を示すだけで、wall-time短縮率や安全な命令batchを意味しない。

## 固定入力と実行

| 項目 | 値 |
|---|---|
| backend | `0b99b2eabe23205b3c6ac194dcdf016a53de554d`、clean |
| target | `picotetris-opt1b` revision 5 |
| firmware BIN | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| scenario | `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208` |
| execution | Serial、quantum 1、PIO RGB565、PSRAM、keyboard、FAT32 SD |
| profiler | `event-horizon-profiler`、schema 3 |

schema 3は既存のrunning/event-horizon値を保持したまま、次を追加する。

- core別PC領域lookup hit/miss（ROM、immutable XIP、XIP-SRAM、SRAM、other）
- narrow/wide hit数
- immutable XIP hit-only sequential runの`2^n`累積分布
- redirect、XIP miss、region exit、fetch前exception、同期faultによる終了数
- entry-address、region、bulk、all decode-cache invalidation観測

実行時のimmutable XIPは`0x10000000..0x14000000`の半開区間だけである。XIP-SRAM
`0x15000000..0x15004000`は明示的に別領域とし、候補から除外する。

profileは計装runなので`valid_for_wall_time=false`である。behavior traceは別runner・別runで
取得し、同一runを性能値と正確性証拠に兼用しない。

## exactness

profile runと独立behavior runは、どちらも85/85、927,528,660 cycle、3,715,000 virtual usで
合格した。UART、framebuffer、PSRAM tick、behavior SHA、173,498,680 event、全9 domain digestは
登録済みOPT1-B値と一致した。

| 観測 | 値 |
|---|---|
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer RGB565 SHA-256 | `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2` |
| PSRAM tick | `305747113` |
| behavior SHA-256 | `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8` |
| event stream SHA-256 | `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789` |

## 計測結果

core 0のimmutable-XIP hitは172,373,954、missは295,794だった。core 1は実行していない。

| 最小run長 | hit命令mass | immutable-XIP hit比 |
|---:|---:|---:|
| 2 | 172,338,762 | 99.9796% |
| 4 | 86,778,680 | 50.3433% |
| 8 | 47,044,211 | 27.2919% |
| 16 | 23,313,232 | 13.5248% |
| 32 | 942,483 | 0.5468% |
| 64 | 18,085 | 0.0105% |

計測区間のinvalidation addressは9,243,286件で、すべてSRAMだった。XIP、ROM、bulk、allは0で
ある。これは今回のworkloadと現行SSI modelでXIPが不変だった証拠であり、将来flash program/
eraseを実装しても無効化不要という意味ではない。

## OPT3-Bの境界

最初の試作は次へ限定する。

1. Serial core 0、実XIP flashだけを対象にする。
2. scheduler quantumは1命令のままにし、per-instruction exception/IRQ/peripheral順序を変えない。
3. 現在のdecoded-op cacheの次entry再利用だけを小さく試す。
4. redirect、miss、exception、fault、region exitで直ちにcursorを破棄する。
5. SRAM、XIP-SRAM、Threaded、dual-core共有codeをfail-closedで除外する。
6. behavior/event全digestが一致した候補だけtrace-OFF A/Bへ進め、5%基準未達ならrevertする。

完全なartifactは
[`opt3-a-xip-cursor-profile-20260809-01`](../firmware-validation/records/opt3-a-xip-cursor-profile-20260809-01/notes.md)
に固定する。
