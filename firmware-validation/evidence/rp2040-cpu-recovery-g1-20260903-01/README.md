# G1（CPU・マルチコア・割込み正確性）記録

## 状態

**candidate-pass / 未統合**。

R2（高速地点からの段階再構築）の最初の機能群として、現行のマルチコア受入targetが必要とする
CPU・割込み経路だけを、e985の一時worktreeへ戻した。候補はbackend `main`へ統合していない。
validation target registry、既存record、外部アプリprojectも変更していない。

## マクロな位置づけ

この記録は、約14%で動作していた高速なSerial起点から、現在必要な機能を一群ずつ取り戻す
手戻り計画のG1である。1倍速、LOAD-0（最大級の継続負荷性能テスト0番）、新しい最終倍率の
qualificationではない。G1の性能値は「高速化達成率」ではなく、機能を戻したときの追加コストを
次の判断へ渡すためのscreening値である。

## 起点と候補

- 起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 候補commit: `e785e02596eab17f50ba55a72cda2e7e7741b499`
- 候補commitの意味: `38683d6`由来のcore-aware fatal exception／core-local SIO FIFO IRQ routingと、
  `c184d6c`由来のstale active level IRQ抑制を、必要部分だけ直接移植したもの
- 差分: `g1-source-diff.patch`（6 source files、180 insertions、27 deletions）
- firmware source: `picocalc-multicore` commit `e9e99f0bfde7b2706fbe7f5a2a92331eed141c98`
- candidate firmware artifact SHA-256: `d8e67255952c64e246469176656bd46d3e61797b48e26a267ff61afff84942a9`

candidate firmwareはsource checkoutから再ビルドした未登録artifactであり、既存の受入registry artifactを
置き換えない。UARTのprovenance行はbuild日時とsource checkout状態が異なるが、provenance行以降の
UART本文は既存受入runと一致した。

## 実装内容

1. harnessがcore 0だけでなくcore 1のNMI／HardFaultもfatalとして停止するようにした。
2. SIO FIFOのlevel-sensitive IRQを、受信側coreのNVICだけへ投影し、FIFO／WOF／ROEの状態変化後に
   再assertするようにした。
3. shared level IRQのpending投影で、同じcoreが実行中の同じexceptionを重複再pendingしないようにした。
   sourceがreturn後もassertedなら、次のpollで再びpendingになる。
4. 上記のcore 1 fatal、SIO FIFO routing／reassert、active level IRQのunit testを追加した。

## 正確性結果

### Tetris（軽ゲーム実装）短screening

measurement-only host timing sidecarを一時適用した1回の診断で、scenarioは完了し、例外・未対応MMIOは
なかった。

| 構成 | cycles | CPU秒 | wall秒 | 結果 |
|---|---:|---:|---:|---|
| e985（sidecar、38683なし／c184なし） | 187,528,660 | 4.954540759 | 4.900088587 | pass |
| e985 + 38683相当 | 187,528,660 | — | — | pass |
| e985 + c184相当 | 187,528,656 | 5.108380735 | 5.137696754 | pass |
| e985 + G1（38683+c184） | 187,528,656 | 4.906316751 | 4.959809758 | pass |

CPU／wallの各値は各1回のsidecar診断であり、平均値や改善率の主張には使わない。`c184d6c`で4 cycle
変化することは分離できたが、これはactive level IRQ正確性の変更であり、性能向上とは分類しない。

### マルチコア実アプリ

G1候補を、`next2-multicore-v1` scenario、Serial、quantum 1、PicoCalc board、PSRAM／keyboard／SD有効で
実行した。

- verdict: **pass**、停止理由: `scenario_done`
- 全5 UART marker（LAUNCH、FIFO、WFE_SEV、IRQ_PROC1、VERDICT）: **検出**
- IRQ_PROC1: `count=1 word=0x13579bdf`
- framebuffer: 320×320、RGB565 SHA-256 `7a8c4e73b96d34e87b8c1629c17e105351c69ad01cc92a71b81e0966ee9e49ff`
- PSRAM: CS falling 7、write 24 byte、read 34 byte、unknown command 0
- unsupported MMIO: **0件**
- candidate cycles: 152,548,108、elapsed 615,000 µs

既存受入run（backend `38683d6`）のcyclesは152,548,092で、candidateとは16 cycle異なる。このrunでは
firmware artifactも既存registry artifactと異なるため、cycle一致とは記録しない。guest-visibleなUART本文
（provenance行を除く）とframebufferは一致しており、差分を性能改善として解釈しない。

比較のため、同じcandidate firmwareをG1なしのe985で実行したrunは1,000,000,000 cycle limitで停止し、
`IRQ_PROC1`と総合PASS markerを出せなかった。これはG1が現行マルチコア契約に必要なことを示す失敗記録で
あり、性能比較値には使わない。

## test結果

- `cargo test --locked -p rp2040-emu`: library 1232、firmware 9、multicore 9、PSRAM／PIO edge 4、
  smoke 6、WFE IRQ wake 5、doctest 0が全てpass
- `cargo test --locked -p picocalc-harness`: `opt0_blocked_baseline` 2、runner unit 39が全てpass
- G1候補worktreeはclean。候補commitは一時worktreeにのみ存在し、backend `main`は変更していない。

## 判定と次の作業

G1は、必要な正確性機能を戻すcandidateとしてpassとする。まだproduction採用・最終性能baseline更新は
しない。次はG2（LCD・PIO・PSRAM正確性）について、同じ短screening、対象test、性能内訳の順に確認する。
G2で説明できないhost costまたはguest-visible差が出た場合は、G2を止めて再設計する。
