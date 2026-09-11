# DMA音声バッファ先行確保の限定検証（2026-09-11）

これは性能退行復旧計画§0.2の単一候補検証である。G0〜G7再構築、dynamic quantum、
1倍速qualificationは再開せず、既存targetのaccepted backendも変更しない。

## 固定した比較点

- baseline: `f32eba1878aeabc6dfc8954b363230ef1e4c2b52`（未変更の開発main）
- candidate: `e83759f68e4d6ee58731fc98e26e84838a8170bd`（上記からの単一commit）
- 変更: `AudioSink::default()`の三つの確保を遅延する。先頭8語は最初の実サンプルで、
  preview用queue／current bufferはpreview有効化時に確保する。時刻、転送、サンプル、キュー上限は不変。
- Rust: `rustc 1.97.1 (8bab26f4f 2026-07-14)`、両者とも同じ`Cargo.lock`とdefault features。
- build: `cargo build --locked --release -p picocalc-harness --bin picocalc-run`
- release: opt-level 3、fat LTO、panic abort、rp2040-emu codegen-units 1。
  repository `.cargo/config.toml`のx86_64 `-C target-feature=+fma`も両者で同一。
- 作業場所: `/tmp/picocalc-audio-alloc.7bZyGH`。共有mainに診断codeを追加していない。

候補commitは`backend-candidate.bundle`にも保存した。baselineを持つbackend repositoryで
`git bundle verify <bundle>`に合格している。候補branchを恒久保存する必要はない。
`0001-perf-defer-DMA-audio-sink-buffer-allocations.patch`は同commitのレビュー／再適用用である。

## Tetris入力の復元

既存外部workspace `picocalc_emu_ext/picotetris`のmainを変更せず、source
`fed84f358d7dcadb1457752e687355ddb1875c48`のdetached worktreeを作成した。
SDK `/home/fuyuki/pico/pico-sdk`はclean commit
`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`（2.2.0）、tinyusbは
`86ad6e56c1700e85f1c5678607a762cfe3aa2f47`。
ARM GCC 13.2.1、CMake 3.28.3、Ninja 1.11.1で、次の既存toolを実行した。

```sh
python3 tools/picocalc.py build \
  --project /tmp/picocalc-audio-alloc.7bZyGH/tetris-source \
  --sdk /home/fuyuki/pico/pico-sdk \
  --picotool-dir /usr/local/lib/cmake/picotool \
  --lcd-variant pio-rgb565 --jobs 2 \
  --build-timestamp 2026-08-06T00:00:00Z --generator Ninja
```

BIN `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`、
UF2 `44ec62270175aac16add07ca8d7c99abb0942bcff341c4c36c0d884fc857e274`に一致した。
source worktreeはbuild後もclean。UF2の生成にpicotoolを使ったが、USB実機操作は行っていない。

## 事前テスト

- 新規integration testは未修正sourceで1,000 DMA更新の確保／解放`(3000, 3000)`を検出し失敗した。
  これは期待したredであり、テストが退行を検出できることを確認した。
- 候補では同じtestが合格し、direct DMA更新とperipheral更新の両方で確保／解放`(0, 0)`。
- 音声sinkのrelease unit tests 10件が合格。先頭8語の通常観測、previewの遅延確保、
  再有効化でのqueue／partial block維持、既存のPCM／音量／可変rate／drop検証を含む。
- 両runnerで同一1,000-cycle起動preflightを実施し、compile-time commit一致、dirty=false、
  `cycle_limit`判定passを確認した。この短いpreflightを全体性能結果には使わない。

## 全体比較方法

`run_comparison.py`は既存`tools/benchmark_rp2040_cpu_candidate.py`のtarget argv builderと
runnerの`--host-timing`を利用する、このevidence専用の実行scriptである。
`picotetris-opt1b`の固定BIN／scenario、PIO RGB565、PSRAM、keyboard、SD FAT32、Serial、
quantum 1、1e9-cycle上限、CPU affinity 11、1 run 300秒上限を固定した。
順序はAB／BA／ABの3組。測定中はbuild／別の負荷試験を実行しない。

reportから除外するのは`backend_build`と`backend_commit`だけで、出力先は同じ相対basenameを使用する。
guest cycles、step quantum、PSRAM tick count、audio expectationを含む他の全field、
UART raw、framebuffer PNG、scenario snapshot PNGを全6 runで厳密比較する。
CPU時間短縮率の組ごとの中央値20%以上かつ全組改善を、追加回帰へ進む条件として事前登録した。
14%の復旧gateは変更せず、このscriptの成功だけでmain統合や正式target受入を承認しない。

```sh
python3 firmware-validation/evidence/dma-audio-allocation-20260911-01/run_comparison.py \
  --validation /home/fuyuki/pico_dvl/codex/picocalc_emu \
  --baseline /tmp/picocalc-audio-alloc.7bZyGH/baseline \
  --candidate /tmp/picocalc-audio-alloc.7bZyGH/candidate \
  --target picotetris-opt1b \
  --firmware /tmp/picocalc-audio-alloc.7bZyGH/tetris-source/build/PicoTetris.bin \
  --output /tmp/picocalc-audio-alloc.7bZyGH/tetris-comparison --pairs 3
```

## 結果・判定

**限定検証完了・今回の候補は不採用。backend mainへの統合なし。**

| 組／順序 | baseline CPU秒 | candidate CPU秒 | CPU時間短縮率 |
|---|---:|---:|---:|
| 1 / AB | 200.832424163 | 205.060303548 | -2.105178% |
| 2 / BA | 199.030480175 | 179.319772373 | +9.903361% |
| 3 / AB | 195.378851014 | 176.130427272 | +9.851846% |

組ごとの短縮率中央値は**9.851846%**。2組では約10%の改善を観測したが、1組目は逆転し、
事前登録した「全3組改善かつ中央値20%以上」を満たさなかった。信頼区間や安定した10%改善を
実証したとは記録しない。今回の単一差分だけで大きな性能退行を解消したとも言えない。

| 指標（各3 runの中央値） | baseline | candidate |
|---|---:|---:|
| process CPU秒 | 199.030480175 | 179.319772373 |
| run-loop wall秒 | 194.441687972 | 175.220125745 |
| real-time比率 | 1.910598513% | 2.120190237% |

全6 runは`scenario_done`、`927528659 cycles`、`3715000 us`で一致した。
backend provenanceを除く全report、UART raw、framebuffer PNG、scenario snapshot PNGが一致した。
ただし、このTetris契約は音声の正式oracleを要求しない。音声unit testsの合格やTetrisの一致を、
未実施の固定音声firmware／PicoEdit／multicore回帰の合格へ読み替えない。

candidateのreal-time比率は1.853171371〜2.159381310%で、14%の復旧gateにも届かなかった。
追加回帰、別の最適化候補、G0〜G7再構築、1倍速計画には進まず、ここで限定検証を終了する。
不要な確保の存在・除去は実証できたが、その回数をTetris全体の支配的な費用とみなす根拠は得られなかった。

生データと集計は[`tetris/manifest.json`](tetris/manifest.json)、
[`tetris/summary.json`](tetris/summary.json)、各`pair-*` directoryに保存した。
採否は[`decision.json`](decision.json)、局所テストとLunaレビューは
[`tests-and-review.md`](tests-and-review.md)を参照する。

候補commitは上記bundle／patchで再現可能にしたうえで、今回の一時worktreeを削除した。
恒久的な作業branchやdefault-off候補codeをbackend mainへ残していない。
固定BINは確認済みの手順で再生成できるため、firmware本体をvalidation repositoryへ同梱していない。
実行command中の`/tmp` pathは当時の作業場所であり、再現時には新しい単一の一時作業領域へ置き換える。

## Validation repositoryの既存gate不整合

終了時のportable verifyは85 pass／1 fail、Python testsは242件中239 pass／3 failuresだった。
未変更`c7e7975`でも同じ失敗を確認し、既存recovery evidenceのUART `.bin`等13 pathと
release-layout検査の不整合へ切り分けた。今回の候補の失敗と混同せず、全体gate合格とも記録しない。
既存evidenceやvalidatorは変更していない。詳細と対照実行は
[`validation-checks/README.md`](validation-checks/README.md)を参照する。
