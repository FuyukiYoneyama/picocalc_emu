# G2（LCD・PIO・PSRAM正確性）記録

## 状態

**candidate-pass / 未統合**。

約14%で動作していたbackend `e985a9d...`からG1（CPU・マルチコア・割込み正確性）を戻した
candidateへ、現行のLCD readback契約に必要なG2だけを移植した。候補はbackend `main`へ統合していない。
validation target registry、既存record、外部アプリprojectも変更していない。

## マクロな位置づけ

この記録は、性能退行復旧・再構築計画R2のG2である。目的は、必要なLCD・PIO・PSRAMのguest-visible
正確性を一群だけ戻し、そのときの性能コストを次の判断へ渡すことである。1倍速、LOAD-0（最大級の
継続負荷性能テスト0番）、新しい最終倍率のqualificationではない。短probeのCPU時間は性能改善を
主張するためではなく、次の機能群へ進む前に明確な退行がないかを見るscreening値である。

## 起点と候補

- 起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前G1: `e785e02596eab17f50ba55a72cda2e7e7741b499`
- G2候補commit: `aa9c868576f02c7bc6e3e450f5224143f09b93a6`
- 由来を確認した履歴: `fc4a62272fff2a7ebbc5bd77a4677c2c4ed7bf87`、
  `4a90864816ef58286f2b292df0e7fe44fbcd4809`
- 差分: `g2-source-diff.patch`（3 source files、123 insertions、33 deletions）
- 候補worktree: `/tmp/picocalc-performance-recovery.QMNRcP/rebuild-e985`

G2は履歴commit全体を機械的にcherry-pickせず、LCD PIO wireのtransport切替、ST7365P RAMRDの
RGB666 wire order、Variant AのSIO pin observer接続という必要部分だけを直接移植した。

## 実装内容

1. `LcdPioWire`は、CS assertだけでなく実際のpad-level SCK edgeを見てbit-level transportを有効化する。
   Variant Aの通常SPI frameとSIO bitbang readbackでRAMRD dummy timingを混同しない。
2. SIO readback終了時のCS deselectで、通常SPI経路の明示的RAMRD dummy timingへ戻す。
3. ST7365PのRGB666 RAMRDを、hardware-observedなR、G、B順に固定する。
4. Variant Aへframe-level SPI wireとSIO pin wireを併設し、通常SPI frameを二重に数えない。
5. SIO RAMRDのRGB orderとSPI dummy復帰をboard unit testで固定する。

## 正確性結果

### Tetris（軽ゲーム実装）短screening

固定artifact（BIN SHA-256 `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`）と
R0固定の3配置scenarioを、同じCPU affinity（logical CPU 11）、Serial、PicoCalc board、PIO RGB565、
PSRAM／keyboard／SD有効で実行した。measurement-only host timing sidecarは一時適用し、candidate source
commitとは別に記録した。

| 構成 | cycles | CPU秒 | wall秒 | 結果 |
|---|---:|---:|---:|---|
| G1 control (`e785e02`、sidecar) | 187,528,656 | 4.954513817 | 4.951456021 | pass |
| G2 candidate (`aa9c868`、sidecar) | 187,528,656 | 4.958608351 | 4.962682779 | pass |

両runのschema-8 reportとUARTはbyte-identicalで、report内のguest-visible fields（LCD、framebuffer、
PSRAM、SD、keyboard、PIO、scenario、UARTを含む）も一致した。G2候補のCPU時間はこの1回ではG1 control
より約0.08%長いが、これは性能改善・退行の確定値ではない。追加平均runは行っていない。

### NEXT-3 A1（LCD readback・SD・PSRAM positive-control）

外部project `picocalc-next3-lcd-fault`のsourceは変更せず、commit
`168a65d9f8206d2767641c589f21f359c1ce7b1b`をclean temporary sourceとしてbuildした。fresh BINは
`d3b8ae7244d8374149fe29e6ffb8939d814a42bfa4cb8b5c1b3ebcd7d1f2d99d`であり、既存registry artifactを
置き換えていない。

G2 clean runner（backend `aa9c868576f02c7bc6e3e450f5224143f09b93a6`、runner SHA-256
`461a2b1f9f60069c5401b49282d558437da296c4574e1b46daf03a11e783fbbe`）で、700,000,000 cycle limitを
明示的に許可して実行した。

- verdict: **pass**、stop reason: `cycle_limit`
- LCD: `ramrd=6`、solid／pattern PASS、mismatches 0、pixels dropped 0
- framebuffer: 320×320、RGB565 SHA-256 `fad83ca09aa4d5956b84776d7a778916df24b22d6a6eba43641431b319a71dc8`
- PSRAM: CS falling 6、write 24 byte、read 34 byte、unknown command 0
- SD: FAT32、28 commands、9 blocks read、10 blocks written、unknown command 0
- keyboard: delivered 2、dropped 0
- exception: なし、unsupported MMIO: 0件

UARTの受入markerは、新規buildが実際に出した
`app_git=untracked bsp_git=168a65d9f820`を要求値に使った。既存artifactのdirty markerは流用していない。

## test結果

- `cargo test --locked -p picocalc-board`: 74 tests＋doctest 1が全てpass
- `cargo test --locked -p rp2040-emu`: library 1232、firmware 9、multicore 9、PSRAM／PIO edge 4、
  smoke 6、WFE IRQ wake 5、doctest 0が全てpass
- `cargo test --locked -p picocalc-harness`: `opt0_blocked_baseline` 2、runner unit 39が全てpass

## 判定と次の作業

G2は、現行LCD readback契約を戻すcandidateとしてpassとする。ただし、まだproduction採用・最終性能
baseline更新はしない。次はG3（DMA・audio正確性）の最小移植であり、G2候補commitから一群だけを対象に、
対象test、必要targetの正確性、短いTetris性能screeningの順で確認する。
