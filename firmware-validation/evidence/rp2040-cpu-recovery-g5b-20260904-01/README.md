# G5-B（loader起動：boot2・watchdog warm reset）記録

## 状態

**candidate-pass / 未統合**。

高速地点から保存領域を戻したG5-A candidateへ、通常のTetris（軽ゲーム実装）起動へ影響を
広げず、明示したloader conformance経路だけに必要なboot2 entry、watchdog warm reset、
flash/SD保持、構造化SD traceを追加した。候補はbackend `main`、target registry、既存U6
record、外部uf2loader、remote branch、hardwareへ変更を加えていない。

## マクロな位置づけ

これは性能退行復旧・再構築計画R2のG5-Bである。目的は1倍速や性能値を判定することではなく、
高速地点から失われた「uf2loaderをboot2から起動し、watchdog reset後にアプリへ引き渡す」
利用経路を、対象を限定して戻せるか確認することだ。G5-Aの保存領域基盤の次に、loader起動の
実動作と再attach後の保存結果を確認した。次のG5-C（SD protocol／bounded multiblock）は
まだ開始していない。

## 候補で戻した契約

1. `--boot-mode boot2`でflash先頭のboot2へ明示的に入る。実RP2040 bootromのUSB MSC経路を
   模倣したとは扱わず、boot2へ渡す初期SP/LR/PCを検査可能なhelperで設定する。
2. WATCHDOGのCTRL/TRIGGER、REASON、SCRATCH0..7をモデル化し、triggerを命令完了境界で
   warm resetへ渡す。flash、SD backing、scratch、reset reason、外部GPIO入力を保持し、
   reset eventのepoch／cycle／core／PC／reasonをreportへ記録する。
3. PicoCalcのSD card-detectで使うGPIO入力overrideを反映する。
4. SD SPIのcommand／block data／CS epochを構造化traceへ記録する。traceは任意の診断artifactで、
   通常reportや性能指標へ混ぜない。

## 起点とprovenance

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- G5-A candidate: `70533db18830e5935ac7bdc6b659ad01a22236c9`
- G5-B candidate: `a5fa765cf308c35a750557c68fd3d68ede7ff35b`
- G5-B source差分: [`g5b-source-diff.patch`](g5b-source-diff.patch)、9 files、1,088 insertions、55 deletions
- source差分SHA-256: `329376b7d87d9cd315f86145ea6fedf7081e05a72741f2eb080ae7a81a4f60f6`
- candidate runner SHA-256: `7b884d74d5cc90124f14bc653e6a0d1e4724d1faa537f4afcc9978ec21f7dcdc`
- backend worktree: clean、detached temporary candidate、remote branchなし
- uf2loader source commit: `5c44a4b64749062b0200507ceeff3ef2b475e288`、clean temporary checkout
- bootrom SHA-256: `9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81`
- scenario: `scenarios/uf2loader-u6-e2e.json`、SHA-256 `603fccde1b86eae06bf1cd778000683560787ffa9d6fc92329f02184ea91f115`
- reattach scenario: `scenarios/uf2loader-u6-reattach.json`

`u6-gate.json`がこの候補実行の機械判定の正典である。64 MiB SD imageと2 MiB flashのraw入力・
出力は保存せず、manifest、report、trace、UART、snapshotと各SHA-256を保存した。

既存の`uf2loader-u6-20260822-01`は書き換えていない。旧recordで保存されていないbootloader
UF2／BOOT2040.UF2の実体は、この再実行では再取得できないため、今回のclean source buildの
入力SHAは旧recordと異なる（今回のbootloader `d8e51bd8...`、BOOT2040 `01c0bf6e...`）。
一方、外部source commit、scenario、選択app UF2（`95efae84...`）は同じで、SD trace digestは
旧recordと同じになった。このため本recordは「旧U6のbyte-identical再実行」とは称さず、旧U6の
受入条件・traceを照合した新しいG5-B candidate evidenceとして扱う。

## ローカルU6候補回帰

既存の`tools/uf2_e2e.py`を使い、同一入力を3回実行した後、run-01のfinal flashを再attachした。
runnerは各runで`--boot-mode boot2`を受け取っている。

- 3 run: pass、`stop_reason=scenario_done`、verdict pass
- watchdog warm reset: 各run 1回、epoch 1
- flash: UF2 loader modelとのreadback exact、erase 6、program 88、protected boot2／top 16 KiB不変
- flash／SD mutation error: なし、unknown command: なし、SD dirty blocks: 0
- SD: 484 commands、470 block reads、blocks written 0
- SD trace: 970 events、digest `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3`
- 3 runのreport／UART／framebuffer／flash／SD／trace digest: すべて一致
- final flash再attach: flash SHAとSD SHAを保持し、アプリsnapshot pass

保存した主artifact:

- [`u6-gate.json`](u6-gate.json): U6機械判定と全runの入力・出力digest
- `run-01`〜`run-03`: report、SD trace、loader/app snapshot、UART capture
- `reattach`: report、SD trace、app snapshot、UART capture

## unit test・format・build

clean candidateで次を実行し、すべてpassした。

- `cargo test --locked -p picocalc-board`: library 82、doctest 1
- `cargo test --locked -p rp2040-emu`: library 1,243、firmware 9、multicore 9、PSRAM edge 4、smoke 8、WFE IRQ wake 5、doctest 0
- `cargo test --locked -p picocalc-harness`: opt0 2、runner 62
- `cargo fmt --package picocalc-board -- --check`
- `cargo fmt --package picocalc-harness -- --check`
- `cargo build --locked --release -p picocalc-harness --bin picocalc-run`

実行ログは[`tests/`](tests/)に保存した。

## 判定と次の作業

G5-Bは、boot2専用entry、watchdog warm resetの命令境界、保存領域保持、SD trace、3回のU6
候補回帰、再attachを通過したため**candidate-pass**とする。これは性能改善、1倍速、正式target
登録、backend `main`への統合を意味しない。

次はG5-C（SD protocol：bounded multiblock）だが、G5-AとG5-Bのcandidate差分を確認してから
着手する。旧uf2loader projectをbranch・公開・改変する作業は行わない。
