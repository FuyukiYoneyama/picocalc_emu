# SD-GEN-1-P1 wire 契約と受入マトリクス

作成日: 2026-08-23  
状態: **完了（P2実装へ進める契約を固定）**  
対象: `picoem-picocalc/crates/picocalc-board/src/sdcard.rs` / `sd_wire.rs`

この文書は、SD-GEN-1-P0で採取したclean traceと、現行backendのsource/unit testから
SPI SD wireの境界を固定する。P1ではproduction codeを変更していない。CMD18/CMD25/CMD12/
CMD23のmulti-block実装を「対応済み」とは扱わず、下表のsynthetic契約をP2の実装・検証対象
として明示する。

machine-readable正典は
[`firmware-validation/contracts/sd-gen1-p1-wire-v1.json`](../../../firmware-validation/contracts/sd-gen1-p1-wire-v1.json)、
P0の実測証拠は
[`firmware-validation/evidence/sd-gen1-p0-20260823-02/`](../../../firmware-validation/evidence/sd-gen1-p0-20260823-02/)にある。

## 1. 証拠の境界

| 分類 | command | 根拠 | P1での扱い |
|---|---|---|---|
| 実traceで観測 | CMD0, CMD8, CMD55, ACMD41, CMD58, CMD17 | U6、M-NESCO、FAT16/FAT32の各3回clean trace | 現行挙動を不変条件として固定 |
| source/unit testのみ | CMD16, CMD24 | backendのwire unit testとstate machine | runtime互換性を主張しない。既存single-block回帰を保持 |
| 未観測・未実装 | CMD18, CMD25, CMD12, CMD23 | P0 manifestの`not_observed` | P2のsynthetic vectorで初めて実装可否を判断 |
| 未対応 | card removal、write-protect、USB BOOTSEL/MSC | 現行scope | SD-GEN-1の対象外 |

P0で実traceに現れなかったcommandを、uf2loaderやM-NESCOが発行したと推測してはならない。
一方、汎用化のために必要なmulti-blockのwire列は、実アプリの一次traceが得られるまで
synthetic vectorとして隔離しておく。

## 2. 共通wire契約

### 2.1 command frame

- SPI 8-bit frameを6 byte送る: `0x40 | command_index`、argumentのbig-endian 4 byte、CRC byte。
- `0x40`以外の先頭byteはcommand frameを開始しない。
- command responseの前には、cardがMISOを`0xFF`に保つ期間があり得る。hostはbit7=0のR1をpollする。
- SDHCモデルのargumentはbyte addressではなく512-byte block addressである。
- block境界は常に512 byte。`CMD16`は受理してもblock長を変更しない。

### 2.2 CRC

- CMD0とCMD8のCRC7は必須検査対象。現行の既知値はCMD0=`0x95`、CMD8(`0x000001AA`)=`0x87`。
- CMD0/CMD8のCRC不一致はR1の`COM_CRC_ERROR`（bit 3）を返し、R7等の拡張response、
  command side effect、pending APP_CMD消費を発生させない。
- その他のcommand CRCは現行モデルでは一般CRC検査を有効にせず、wire値をtraceへ記録する。
  P2で一般CRCを有効化する場合は、別の契約revisionとnegative vectorを作る。
- read/write data CRC16はtraceへ記録する。現行モデルはhost提供値を検証せず、payloadの
  長さ・token・block境界を検証する。

### 2.3 CSとstate

- CS lowの開始ごとにtraceの`cs_epoch`を増やし、transfer counterを0から始める。
- CS highではcommand／reply／write payloadの途中状態を破棄し、次のCS lowで新しいframeを受ける。
- cardの初期化済み状態はCS pulseで失われない。初期化前後のR1はsourceの状態機械に従う。
- trace eventはcommand境界、block data、deselectを含み、sequence／epoch／transfer数を持つ。
- traceは診断専用であり、trace on/offでreply、counter、backing、UART、framebufferを変えてはならない。

### 2.4 backingと範囲

- block read/writeがcard容量外なら、データtokenを捏造してはならない。
- RAW backingへのwriteはCOW overlayへ記録し、入力RAWをrun中に変更しない。
- exportはatomic temporary file + renameで、未変更sectorのbyte列を保持する。

## 3. command受入マトリクス

### 3.1 現行回帰で固定するcommand

| command | response / data列 | state effect | acceptance |
|---|---|---|---|
| CMD0 (0) | R1 `0x01`（有効CRC時） | idleを報告 | P0 trace、CRC known vector、bad-CRC negative |
| CMD8 (8) | R7: R1 + `00 00 01 AA`（argument `0x1AA`） | voltage/check patternを返す | P0 trace、CRC known vector、bad-CRC negative |
| CMD55 (55) | 初期化前R1 `0x01`、初期化後R1 `0x00` | 次のaccepted commandをACMDとして扱う | P0 trace、ACMD41 unit test |
| ACMD41 (CMD55後, index 41) | まずR1 `0x01`、最終的にR1 `0x00` | initialized=true | P0 trace、busy poll回帰 |
| CMD58 (58) | R3: R1 + OCR `C0 FF 80 00` | high-capacity/block addressingを示す | P0 trace |
| CMD17 (17) | R1 `0x00` → `0xFE` → 512 byte → CRC16 2 byte | blocks_read++ | P0 trace、R1/token順序、範囲外no-token |

### 3.2 source/unit testでのみ固定するsingle-block command

| command | 現状 | P2以降の境界 |
|---|---|---|
| CMD16 (16) | R1 readyを返すが、512 byte固定 | block長変更を許可しない。実traceが得られるまでは追加意味を持たせない |
| CMD24 (24) | R1 ready → `0xFE` → 512 byte → CRC16 → data response `0x05`。COWへcommit | runtime traceで未観測。既存unit testとRAW export回帰を保持し、multi-blockの根拠にはしない |

### 3.3 syntheticで保留するmulti-block command

以下は**P1で実装済みではない**。P2では、まず記載したvectorをbyte列としてfixture化し、
state遷移・停止・範囲外・mutationを定義した後にproduction codeを変更する。

| command | synthetic vector | 必須wire項目 | 現在の判定 |
|---|---|---|---|
| CMD18 (18) | start block 3から2 blocks read | R1、各blockの`0xFE`/512/CRC、block間のCS保持、終了境界 | 未対応・P2候補 |
| CMD12 (12) | CMD18の2 block目後にstop | stop command frame、data stream停止、R1、CS epoch／transfer順序 | 未対応・P2候補 |
| CMD23 (23) | pre-erase count=2、続くCMD25へ | R1、countの次commandへの結合、不要時の失効 | 未対応・P2候補 |
| CMD25 (25) | start block 3へ2 blocks write | 各blockのwrite token、512/CRC、data response、busy、stop token | 未対応・P2候補 |

P2のfixtureでは、CMD12のstuff byte、CMD25のstop token（通常`0xFD`）とbusy解除の具体的な
transfer数を明示する。実アプリのtraceが先に得られた場合は、synthetic vectorより一次traceを
優先し、契約revisionを更新する。

## 4. negative mutation契約

P2/P3で、次のmutationは正常passとして通してはならない。未対応commandを受信しただけで
「汎用互換」と判定せず、unknown opcodeと原因をreport／traceへ残す。

| mutation | 期待する観測 |
|---|---|
| CMD0/CMD8 CRCを1 bit変更 | R1 `COM_CRC_ERROR`、拡張responseなし、state side effectなし |
| read tokenを`0xFE`以外に変更 | block payloadを正常readとして受理しない |
| payloadを511/513 byteに変更 | block boundary errorとしてfail-closed |
| CMD17/CMD24の範囲外block | token／commitを捏造せず、原因を記録 |
| block途中でCS high | in-flight stateを破棄し、次epochへ移行 |
| 未実装CMD18/25/12/23 | unknown／unsupportedとして可視化し、正常multi-block passを返さない |
| trace on/off | protocol以外のreport／UART／framebufferに差を作らない |

## 5. P2開始条件と受入ゲート

P2は次の順で進める。ここでproduction codeを追加するのは、fixtureとunit testの失敗理由が
固定された後だけである。

1. 上表のCMD18/CMD25/CMD12/CMD23をbyte列fixtureへ落とし、期待response・token・CRC・CS epoch・busyを固定する。
2. normal／out-of-range／CRC／token／途中CSのunit testを先に追加する。
3. feature-gated state machineを実装し、既存CMD0/8/55/41/58/17/24回帰を再実行する。
4. trace replayとmutationで、正常vectorは3回一致、異常vectorはfail-closedになることを確認する。
5. trace on/offの挙動一致と逐次10-run性能測定を行う。GitHub Actionsは使用しない。
6. U6固定target、M-NESCO、FAT16/FAT32を壊していないことをローカルで確認してからP3へ進む。

P1完了時点の結論は、**CMD18/CMD25/CMD12/CMD23を実装することではなく、実装前に何を一致させるかを固定したこと**である。
P2のsynthetic vectorまたは新しい一次traceがない限り、現行production modelの未対応範囲は変更しない。
