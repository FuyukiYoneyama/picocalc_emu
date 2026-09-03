# G5-A（保存領域基盤：RAW SD・NOR flash mutation）記録

## 状態

**candidate-pass / 未統合**。

高速地点 `e985a9d...` からG1〜G4を戻した一時candidateへ、現在の公開利用経路に必要な
RAW SD backing、NOR flash erase/program、XIP readback、SD mandatory command CRCを戻した。
候補はbackend `main`へ統合していない。target registry、既存record、外部project、remote
branch、hardwareは変更していない。

## マクロな位置づけ

これは性能退行復旧・再構築計画R2のG5-Aである。目的は、保存領域機能を一括で復元して
1倍速を判定することではなく、現在の利用者が必要とする保存領域の最小契約を高速地点へ
戻し、次のloader起動（G5-B）へ進めるかを確認することだ。1倍速、LOAD-0（最大級の
継続負荷性能テスト0番）、特定倍率のqualification、平均値の作成は行っていない。

G5-Aの対象は次のとおり。

1. RAW SD入力をregular fileとして開き、書き込みをsector単位のcopy-on-write overlayへ
   置き、atomicに別ファイルへexportする。
2. NOR flashのWREN、page program、sector/block/chip eraseをSSIで受け、物理的な
   1→0書き込みとerase後のXIP readbackへ反映する。範囲、ページ境界、WREN違反、
   0→1要求は診断エラーとして保持する。
3. boot helperが使うQSPI SS境界、known command、CMD0/CMD8のmandatory CRCを扱う。
4. harnessのRAW SD／flash exportとpath-free reportを提供する。

USB BOOTSEL/MSC、実RP2040 bootrom全体、任意UF2、loaderのwarm reset、bounded SD
multiblockはG5-Aの対象外であり、それぞれG5-B/G5-Cまたは既存recordの契約で扱う。

## 起点と候補

- 高速起点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 直前G4 candidate: `f2d4d52711af70cd7f4e1c74ffda667966df15cb`
- G5-A candidate: `70533db18830e5935ac7bdc6b659ad01a22236c9`
- candidate commit: `recovery: restore flash and raw SD storage`
- source差分: `g5a-source-diff.patch`（G4から8 files、1,149 insertions、140 deletions）
- source差分SHA-256: `1c43d56105a8704ec83b92308ab92fe19064d5a7924c3d4e459c59b95d74ab93`
- candidate worktree: `/tmp`の一時worktree、detached、remote branchなし
- runner release SHA-256: `64c6163895b273da93ceefa609792e7faf694eb303a22ac1073bb08ad17787de`

G5-Aのcandidateはcommit後にcleanで再buildした。runner reportの
`backend_build.dirty`は`false`で、compile-time backend identityは候補commitと一致する。

## 対象testとbuild

clean candidate worktreeで次を実行し、すべてpassした。

- `cargo test --locked -p picocalc-board`: library 81、doctest 1
- `cargo test --locked -p rp2040-emu`: library 1,239、firmware 9、multicore 9、PSRAM edge 4、
  smoke 6、WFE IRQ wake 5、doctest 0
- `cargo test --locked -p picocalc-harness`: opt0 2、runner 62
- `cargo fmt --package picocalc-board -- --check`
- `cargo fmt --package picocalc-harness -- --check`
- `cargo build --locked --release -p picocalc-harness`

実行ログは[`tests/`](tests/)に保存した。workspace全体のformat checkは既存のformat driftを
含むためG5-A gateには採用していない。

## RAW SD（保存領域の実行入口）

`uart_hello.bin`へ10,000-cycleの短いcycle-limit runを行い、2-block（1,024 byte）の
RAW imageをattachし、実行後に別ファイルへexportした。

- report: [`raw/report.json`](raw/report.json)
- input: [`raw/input.img`](raw/input.img)
- exported output: [`raw/output.img`](raw/output.img)
- input/output SHA-256: `5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef`
- report SHA-256: `df33ffa4ac97636700fced759fdf822c7ca00b7d1eacd44aa908010841a01ea1`
- report verdict: `pass`、stop reason `cycle_limit`
- report `sd.raw_image`: 1,024 bytes、2 blocks、dirty blocks 0、source SHAはinputと一致
- report `flash.errors`: 空

board unit testでは、RAWの読み出し、sector COW、input非変更、atomic export、空/unaligned
input拒否、同一path・`.` alias・symlink alias・memory-backed cardのexport拒否も確認した。

同じrunでflashの最終2 MiB imageもexportした。

- flash output: [`raw/flash-output.bin`](raw/flash-output.bin)
- SHA-256: `28d1b234ad6b6ce79f2c2149fd79ec81397ca6951a17e028299a8f1449e814f0`
- `erase_count=0`、`program_count=0`、`errors=[]`

## Tetris（軽ゲーム実装）短screening

G4 controlと同じfirmware、B2 bootrom、PicoCalc board、PIO RGB565、PSRAM、keyboard、
memory-backed SD、quantum=1、R0短scenarioで1回実行した。

- report: [`tetris/report.json`](tetris/report.json)
- scenario: [`tetris/r0-scenario-probe.json`](tetris/r0-scenario-probe.json)
- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- bootrom SHA-256: `9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81`
- scenario SHA-256: `49740dab5069cd3f056ab4c9e0a46323d5b18e1f7ff21e4e6a0ce58aa6f8a7f3`
- report SHA-256: `7c2b4f8ecfc8a16dca3fe0873d92798801eff1a596d7658355be0d1aa932459f`
- verdict: **pass**、stop reason `scenario_done`
- guest cycles: `187,528,659`
- guest elapsed: `755,000 µs`
- UART bytes: `1,387`、SHA-256 `db430d62e3e6164709d30ff7ebaac033408ef36f8261a4f313b478e3f8e8155a`
- framebuffer RGB565 SHA-256: `21738024c789675f1d2a7299004618dc648cc1d5af6f4971c33e392c2bac0162`
- PSRAM: CS falling 7、bytes written 24、bytes read 34
- flash: erase 0、program 0、unknown commandなし、errorsなし

G4 controlとの比較対象を[`tetris/candidate-normalized.json`](tetris/candidate-normalized.json)と
[`tetris/g4-control-normalized.json`](tetris/g4-control-normalized.json)に保存した。両方の
SHA-256は `fe658ee07415b6d55799e250c09e6997fe9ac98dcd43140efb452fcb4bed4da5`で一致する。
これはG5-A追加によるguest-visible退行がないことを示す短い確認であり、速度改善の主張ではない。

## 判定と次の作業

G5-Aは、必要なRAW SD／NOR flash mutation／mandatory CRCをcandidateへ戻し、対象unit test、
clean release build、RAW実行入口、Tetris（軽ゲーム実装）短screeningを通過した段階として
**pass**とする。

次はG5-B（loader起動：boot2・watchdog warm reset）の必要部分である。boot2は通常app起動へ
追加せず、明示 `--boot-mode boot2` の固定loader conformance経路だけを対象にする。既存の
`uf2loader-u6-20260822-01` recordと外部sourceは書き換えない。G5-Bのcandidateが、boot2専用
unit test、固定U6 trace、再attach後のflash/SD結果を通過するまで、G5-Cや正式target更新へ
進まない。

## 再現に使った入口

RAW SD短run:

```text
picocalc-run --backend-commit 70533db18830e5935ac7bdc6b659ad01a22236c9 \
  --bin uart_hello.bin --bootrom bootrom.bin --cycles 10000 \
  --sd-image input.img --sd-image-out output.img \
  --flash-image-out flash-output.bin --json report.json \
  --expect-stop cycle_limit
```

Tetris（軽ゲーム実装）短screening:

```text
taskset -c 11 picocalc-run --backend-commit 70533db18830e5935ac7bdc6b659ad01a22236c9 \
  --bin PicoTetris.bin --bootrom bootrom-rp2040-b2.bin \
  --board picocalc --lcd-variant pio-rgb565 --psram --keyboard --sd \
  --scenario r0-scenario-probe.json --quantum 1 \
  --expect-stop scenario_done --expect-uart '[TETRIS] start'
```

実行時には各artifactの絶対pathを指定し、reportのbackend、firmware、bootrom SHA-256を
照合する。
