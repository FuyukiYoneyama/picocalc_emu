# G5-C（SD protocol：bounded multiblock）記録

## 状態

**candidate-pass / 未統合**。

高速地点から積み直している候補へ、現在の公開SD利用経路で必要な bounded な
CMD18/CMD12 read と CMD23/CMD25 write を戻した。候補は backend `main`、target registry、
既存record、外部project、remote branch、hardwareへ変更を加えていない。

## マクロな位置づけ

これは性能退行復旧・再構築計画R2のG5（保存領域・起動経路）の最後のサブグループである。
G5-A（保存領域基盤）、G5-B（loader起動：boot2・watchdog warm reset）の後に、loader以外の
通常アプリでも使うSDプロトコル境界を復元した。目的は1倍速や性能値を判定することではなく、
高速地点から失われた公開機能を限定的に戻し、既存のUF2Loader U6経路を壊していないことを
確認することだ。

G5-Cが通過しても、backend `main`への統合、target登録、速度改善、1倍速qualificationは
まだ行わない。統合はG5全体のcandidate差分と、次の機能群を確認した後に計画R3/R4で行う。

## 候補で戻した契約

1. feature `sd-gen1-multiblock` を追加し、board/harnessの通常featureで有効化する。
2. CMD18（multi-block read）とCMD12（read stop）を、boundedなblock数・容量・応答状態で処理する。
3. CMD23（pre-erase block count）とCMD25（multi-block write）を、CMD17 readbackと組み合わせて
   処理する。未登録・範囲外・状態外の操作は黙って成功させず、protocol errorとしてfail closedにする。
4. SD command、block、CS境界を構造化traceへ記録し、runner reportへprotocol errorを出す。
5. feature有効時のCLI E2Eで、2-block read、stop、2-block write、readbackを3回再生し、report・trace・
   exported imageの決定性を確認する。

この候補は既存のsingle-block経路を無条件に置き換えるものではない。`--no-default-features`
で従来経路のunit testも実行し、後方のfeature境界を確認した。

## 起点とprovenance

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前G5-B candidate: `a5fa765cf308c35a750557c68fd3d68ede7ff35b`
- G5-C candidate: `bba2153d8de7d4503f0e7aff1a5b088bbd146da8`
- source差分: `g5c-source-diff.patch`（直前candidateから6 files、888 insertions、10 deletions）
- source差分SHA-256: `1258064178202eb06fbbf1bbd6d324068f1fbdab2112cf7de0c8d08a2815410b`
- candidate worktree: `/tmp`の一時worktree、detached、remote branchなし、clean
- runner release SHA-256: `eca0cf600ec9fae34071641a5e5bb9c59e2673b9a1e0913542248b81c9fc4867`
- execution model: `Serial`
- U6 step quantum: `16`
- Tetris screening step quantum: `1`
- bootrom SHA-256: `9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81`
- Tetris（軽ゲーム実装）firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- uf2loader source commit: `5c44a4b64749062b0200507ceeff3ef2b475e288`、clean temporary checkout
- loader UF2 SHA-256: `01c0bf6e6b49ef8468380ca7bcbac3f7bc758b07fa7e86e53e822f9abcba6e0b`
- app UF2 SHA-256: `95efae84fddd9c5ff0cb64b20641418a4c9036b1217c78b578cc0cb9740dcbd6`
- bootloader UF2 SHA-256: `d8e51bd8e2ab5dfd6071cbd0cb8cbdc3537811ac2e3084accf207976c008aee5`

rawの64 MiB SD image、2 MiB flash、UF2実体はこのrecordへ保存していない。入力の識別情報と、
report／trace／UART／snapshot／候補差分を保存している。機械判定の正典は[`u6-gate.json`](u6-gate.json)である。

## ローカル実装検証

clean candidateで次を確認した。

- `cargo test --locked -p picocalc-board`: feature有効 87 tests、doctest 1、pass
- `cargo test --locked -p picocalc-harness`: feature有効 opt0 2、runner 63、SD E2E 1、pass
- `cargo test --locked -p picocalc-board --no-default-features`: 82 tests、doctest 1、pass
- `cargo test --locked -p picocalc-harness --no-default-features`: opt0 2、runner 62、pass
- `cargo fmt --package picocalc-board --package picocalc-harness -- --check`: pass
- `git diff --check`: pass
- `cargo build --locked --release -p picocalc-harness --bin picocalc-run`: pass
- release版 `cli_sd_multiblock_e2e`: 1 test、3 repetitions、pass

strict全体Clippyは、G5-Bで記録済みの既存警告（`ssi_flash.rs`の`manual_is_multiple_of`と
`tests.rs`の`identity_op`）を含むため、G5-Cの合否には使っていない。同じ原因の全体strict
Clippyを無変更で再実行していない。

## Tetris（軽ゲーム実装）短screening

G5-AのTetris短screeningと同じfirmware、scenario、PicoCalc board、PIO RGB565、PSRAM、keyboard、
memory-backed SD、Serial、quantum=1で1回実行した。

- report: [`tetris/report.json`](tetris/report.json)
- scenario: [`tetris/r0-scenario-probe.json`](tetris/r0-scenario-probe.json)
- verdict: **pass**、stop reason `scenario_done`
- guest cycles: `187,528,659`
- guest elapsed: `755,000 µs`
- UART: 1,387 bytes、SHA-256 `db430d62e3e6164709d30ff7ebaac033408ef36f8261a4f313b478e3f8e8155a`
- framebuffer RGB565 SHA-256: `21738024c789675f1d2a7299004618dc648cc1d5af6f4971c33e392c2bac0162`
- PSRAM: CS falling 7、bytes written 24、bytes read 34
- SD: attached、FAT32、protocol errors 0、unknown commands 0

`candidate-normalized.json`と`g4-control-normalized.json`は、G5-Cで追加された空の
`sd.protocol_errors`を比較対象から外した正確性投影であり、SHA-256はともに
`fe658ee07415b6d55799e250c09e6997fe9ac98dcd43140efb452fcb4bed4da5`で一致する。
これはSD protocol復元によるTetrisのguest-visible退行がこのprobeでないことを示すが、
速度改善の主張ではない。

## U6候補回帰

G5-Bで使用した固定U6入力を、G5-C candidateのrelease runnerで3回再生し、run-01のfinal
flashをreattachした。U6のraw入力は保存していないため、既存U6 recordのbyte-identicalな
再実行とは称さない。clean source、入力hash、scenario、traceと受入条件を照合した新しい
candidate evidenceである。

- gate: **U6 pass**
- 3 run: `scenario_done`、verdict pass、全runのreport／UART／framebuffer／flash／SD／trace digest一致
- watchdog warm reset: 各run 1回
- flash: loader model readback exact、protected loader region unchanged、mutation error なし
- SD: FAT32、484 commands、470 block reads、protocol error なし、unknown command なし
- SD trace: 970 events、digest `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3`
- final flash SHA-256: `0fbbb894b2123b60f1ceff205e81e764c12460681d88f5f863d6276015cfe308`
- reattach: flash／SD SHA-256保持、application snapshot pass

各runのreport、trace、UART、loader/application snapshotと、機械判定`u6-gate.json`を保存した。

## 判定と次の作業

G5-Cは、bounded SD multiblockのunit／CLI E2E、feature無効の後方経路、Tetris短screening、
U6 3回回帰、final-image reattachを通過したため**candidate-pass**とする。ただしこれは
performance improvement、1倍速、formal qualification、production integrationを意味しない。

G5-A／G5-B／G5-Cの差分確認が完了したため、次は計画R2のG6（外部I2C module：RTC／EEPROM／AHT20／BMP280）
の必要性と、既存I2C-EXT受入との差分を棚卸しする。G6の移植前には、TetrisでinactiveなI2C
経路を通常hot pathへ混ぜないことを確認する。

旧`uf2loader` projectのbranch・公開・改変は行っていない。
