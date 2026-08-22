# SD-GEN-1 汎用 SD protocol 一般化計画

作成日: 2026-08-23  
対象: `picocalc_emu` / `picoem-picocalc`  
状態: **P3完了（local validation pass、通常runtime未昇格）。次はP4 representative runtime/app regression**

## 1. 目的

U6の固定版`uf2loader`受入とM-NESCO拡張で確認したSD経路を、特定loaderのtraceだけに
依存しない汎用block-deviceモデルへ段階的に広げる。目的は、PicoCalcアプリが利用する
single／multi-block read/writeを、SPIのwire順序・CS境界・token・CRC・busy遷移まで
決定的に検証できるようにすることである。

この計画は「未観測commandを推測で追加する」計画ではない。最初に一次traceと明示的な
synthetic protocol契約を固定し、その契約に対応する最小実装だけを追加する。

## 2. 維持する境界

- U6の固定版`uf2loader-e2e` target、report、trace、capabilityは変更しない。
- 通常のdirect boot、`--sd-image`、`--sd-dir`、RAW pack/extractの入口を壊さない。
- USB BOOTSEL/MSC、カード抜去、write-protect、電源断時のアナログ破損は対象外。
- FAT16/FAT32のfilesystem検証は既存のhost tool・FatFs回帰を通して行うが、filesystem
  実装とSD wire protocol実装を混同しない。
- productionで未対応のcommandは、既存方針どおり可視化されたfail-closedにする。
- 変更は小さなfeature-gated単位で行い、U6のversioned validationを新しいrecordなしに
  書き換えない。

## 3. 実施順序

### SD-GEN-1-P0: 現状棚卸しとtrace採取

production codeを変更せず、次を固定する。

1. 現行SD state machine、CMD初期化、CMD17/CMD24、CRC/token、CS high時の状態破棄、
   busy応答をソースとunit testから一覧化する。
2. clean backendで、既存U6 `uf2loader`、M-NESCO、利用可能なFatFs代表経路を各3回
   traceする。traceはrunner reportとは別artifactにし、command、response、token、
   block長、CRC、CS区間、未知commandを記録する。
3. traceに現れない経路は、production実装の根拠にしない。必要な経路は次のP1で
   synthetic契約として明示する。

### SD-GEN-1-P1: wire契約と受入マトリクス（完了 2026-08-23）

コマンドを「既存回帰」「実traceで必要」「synthetic契約で追加」「対象外」に分類する。
最低限、次の境界を個別に定義する。

- single-block read/write: CMD17/CMD24
- multi-block read/write: CMD18/CMD25、停止CMD12、事前消去CMD23
- read data token、write token、busy期間、CS deselect、block間隔
- command/data CRC、CRC無効設定時の扱い、CRC不一致のエラー応答
- byte address／block address、512-byte境界、範囲外アクセス
- unknown command、不正token、途中CS解除、途中エラーのfail-closed

各項目に、wire列、期待response、model state、trace digest、negative mutationを持たせる。
「コマンドを実装した」だけでは受入にしない。

P1の固定結果は[`SD_GEN1_P1_WIRE_CONTRACT_20260823.md`](SD_GEN1_P1_WIRE_CONTRACT_20260823.md)と
[`../firmware-validation/contracts/sd-gen1-p1-wire-v1.json`](../firmware-validation/contracts/sd-gen1-p1-wire-v1.json)に保存した。
P0 traceで観測したCMD0/CMD8/CMD55/ACMD41/CMD58/CMD17、source/unit testだけで確認した
CMD16/CMD24、未観測・未実装のCMD18/CMD25/CMD12/CMD23を分離している。P1ではproduction
SD codeを変更していない。multi-blockのproduction追加は、P2でbyte-level synthetic vector、
negative mutation、CS／busy境界を固定した後に判断する。

### SD-GEN-1-P2: 最小state machine実装（完了 2026-08-23、feature-gated）

P1で必要性が確定した範囲だけを、既存single-block回帰を保ったまま実装する。

- command受付、data token、block payload、CRC、busy、CS境界を明示的なstateとして扱う。
- multi-blockは`count * 512`の一括返却にせず、blockごとのtoken／payload／CRCを再現する。
- CMD12などの停止処理は、実traceまたはP1契約にある場合だけ追加する。
- writeはSDの既存COW overlay／atomic export境界を再利用し、未変更sectorのbyte一致を
  維持する。
- 既存`CMD17`の応答順序を変更しない。U6固定経路をfeatureなしでビルドできる状態を保つ。

P2の実装は[`SD_GEN1_P2_IMPLEMENTATION_20260823.md`](SD_GEN1_P2_IMPLEMENTATION_20260823.md)と
[`../firmware-validation/contracts/sd-gen1-p2-vectors-v1.json`](../firmware-validation/contracts/sd-gen1-p2-vectors-v1.json)に固定した。
`sd-gen1-multiblock` feature付きboard unit testでCMD18/CMD12/CMD23/CMD25のsynthetic vector、
誤token、範囲外、途中CS、既存single-block readbackを検証した。default featureでは従来経路を維持し、
通常runner／uf2loader capabilityには接続していない。

### SD-GEN-1-P3: unit／trace replay／negative report統合／既存回帰（完了 2026-08-23）

- command FSM、CRC、token、busy、CS、block境界をfeature-enabled hardware-free
  unit testで検証した（board 90、harness 67 main tests、全てpass）。既定featureも
  board 85、harness 66 main testsでpassした。
- `tools/sd_trace_replay.py`を追加し、P0の完全preview traceから`SdTraceState`の
  canonical streaming digestを再計算する。sequence、CS epoch、command、token、
  512-byte data、CRC、preview truncationを検査し、反復trace比較も行う。
- digest mutationはexit 1／`status=fail`で拒否し、feature-enabled runnerの
  `protocol_errors`は`sd_protocol_error`としてjudged failureへ統合した。既定featureでは
  report schemaとverdictを変更しない。
- U6、M-NESCO SD／flash、FAT16、FAT32の凍結clean traceをreplayし、3回反復可能な
  経路はevent countとdigestが一致した。結果は[`sd-gen1-p3-20260823-01/`](../firmware-validation/evidence/sd-gen1-p3-20260823-01/)
  と[`sd-gen1-p3-validation-v1.json`](../firmware-validation/contracts/sd-gen1-p3-validation-v1.json)へ固定した。
- 速度比較はこの段階では行わない。既存runtimeの速度・挙動を変更するpromotionではなく、
  feature-gated診断と凍結trace replayである。CIは使わず全検証をローカルで行った。

### SD-GEN-1-P4: representative runtime／アプリ回帰（未着手）

次の順で回帰する。

1. U6固定`uf2loader`（既存recordを変更せず、同じverdictを確認）。
2. M-NESCOの計画4ケース＋追加mapper 1（SD source、flash export、再attach、XIP）。
3. FatFsのFAT16／FAT32 pack、read、write、extract。
4. P1で追加したmulti-blockを**既定で有効化した**代表アプリまたはsynthetic firmware。

各段階で、unknown command、mutation error、flash SHA、SD image SHA、UART/reportの
一致を確認する。失敗した段階より先へ進めない。

P3で完了したU6／M-NESCO／FAT回帰は、既存の固定版runtimeのtrace replayであり、P2の
multi-block featureを通常runnerへ昇格したことを意味しない。P4ではproduction runtimeへ
接続した場合の新しいrecordを作り、既存U6／M-NESCO／FATの全契約を壊さないことを改めて
実行確認する。

### SD-GEN-1-P5: versioned validationとcapability判断

P4の全ゲートが通った場合だけ、新しいschema／recordを作成する。既存U6 recordを
上書きせず、SD protocol世代と対応command集合をregistryへ明記する。

`capability.json`の汎用SD項目は、次を全て満たした後に限定範囲で更新する。

- wire契約、unit test、trace replay、negative mutationが揃っている。
- U6、M-NESCO、FAT16/FAT32回帰が全てpassしている。
- 3回以上のdeterministic再実行でdigest／SHAが一致する。
- 未対応範囲（USB BOOTSEL/MSC、card removal等）が明記されている。

## 4. 受入条件

SD-GEN-1の完了条件は次の全てである。

- single／multi-block read/writeの対象範囲が文書とmachine-readable recordで一致する。
- command、response、token、CRC、CS、busy、block境界のtrace digestが決定的である。
- 正常経路は3回以上一致し、mutationはfail-closedである。
- U6固定targetとM-NESCO拡張の既存結果を壊さない。
- FAT16/FAT32のpack／extractとSD COW／atomic exportが回帰する。
- 速度退行が既存OPT手順で測定され、採用判断が記録されている。
- 実装・record・capability・利用者文書の対象範囲に齟齬がない。

## 5. 見積りと開始条件

| 段階 | 目安 | 主な成果物 |
|---|---:|---|
| P0 棚卸し／trace | 4〜6時間 | clean trace、現状一覧 |
| P1 wire契約 | 6〜8時間 | command/state受入マトリクス（完了） |
| P2 state machine | 10〜16時間 | feature-gated production実装（完了） |
| P3 test／mutation／凍結回帰 | 8〜12時間 | unit、replay、negative record、既存trace回帰（完了） |
| P4 runtime／アプリ回帰 | 8〜12時間 | feature昇格後のU6／M-NESCO／FAT再実行 |
| P5 record／docs | 4〜6時間 | versioned validation、capability判断 |
| **合計** | **40〜60時間** | 実装範囲確定後に再見積り |

開始条件はP0のtraceとP1の契約が完了すること。P0で必要なcommandが見つからない
場合は、production codeを増やさず「未観測・未対応」として計画を縮小する。

P0、P1、P2、P3は完了した。P3で`sd-gen1-multiblock`のrunner診断接続、trace replay、negative
report判定、既存U6／M-NESCO／FATの凍結trace回帰を行った。P2のmulti-blockはなおfeature-gatedで、
通常runtime／capabilityへの昇格はしていない。次に着手できるのは**SD-GEN-1-P4 representative
runtime／アプリ回帰**である。
P0の記録は[`firmware-validation/evidence/sd-gen1-p0-20260823-02/`](../firmware-validation/evidence/sd-gen1-p0-20260823-02/)へ、
P1のwire契約は[`SD_GEN1_P1_WIRE_CONTRACT_20260823.md`](SD_GEN1_P1_WIRE_CONTRACT_20260823.md)へ固定した。
