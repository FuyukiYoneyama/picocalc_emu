# OPT2-B running event-horizon profiler evidence

**Date:** 2026-08-08  
**Target input:** `picotetris-opt1b` revision 5  
**Profiler backend:** `ac0c3052e6c28fcf235a33f98f3a96470d2966f1`

## Purpose and scope

CPUがrunningの区間について、どのdispatchがCPU可視・device可視の境界で終わるか、現在の
保守的event horizonが何cycle先を示すか、境界なしに連続した区間がどれだけあるかを測った。
profilerは`event-horizon-profiler` featureでのみコンパイルされ、通常・性能測定binaryには入らない。
計装runは`instrumented=true`、`valid_for_wall_time=false`であり、wall timeの評価には使わない。

`observed_inter_boundary_*`と`observed_candidate_*`は実行後に観測した分布である。将来の境界を
予測する安全証明ではないため、artifactにも`observed_gaps_are_safe_windows=false`を固定した。
candidateは「そのdispatchで観測境界がなく、dispatch前の保守的horizonが消費cycleより遠い」
場合だけ数える。

## Reproduction

PicoTetris source commit `fed84f358d7dcadb1457752e687355ddb1875c48`をfresh checkoutし、
Pico SDK 2.2.0、Ninja、timestamp `2026-08-06T00:00:00Z`で生成した登録済みBINを使う。

```bash
cd /home/fuyuki/pico_dvl/codex/picoem-picocalc
cargo clean
cargo build --locked --release -p picocalc-harness \
  --features event-horizon-profiler --bin picocalc-run

target/release/picocalc-run \
  --bin <fresh-picotetris>/build/PicoTetris.bin \
  --bootrom roms/rp2040/bootrom-rp2040-b2.bin \
  --cycles 8000000000 --board picocalc --quantum 1 \
  --psram --keyboard --sd --sd-format fat32 \
  --scenario <picocalc_emu>/scenarios/tetris-line-clear.json \
  --snapshot-dir <tmp>/opt2b-snapshots \
  --expect-stop scenario_done \
  --expect-uart '[TETRIS] start' \
  --expect-uart '[TETRIS] cleared=' \
  --expect-uart 'score=1400 lines=13' \
  --json run-report.json \
  --event-horizon-profile running-event-horizon-profile.json
```

`cargo clean`は証拠runの前に必要である。Cargoの既存build-script cacheを残したままHEADだけを
更新すると、runnerへ埋め込むcommit/dirty provenanceが以前のbuild値を保持し得るためである。
本recordは`backend_build.commit=ac0c305...`、`dirty=false`を確認してから保存した。

## Exactness

- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- stop: `scenario_done`
- cycle / virtual time: `927,528,660` / `3,715,000 us`
- scenario: 85/85 pass
- UART SHA-256: `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- framebuffer RGB565 SHA-256: `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`
- behavior SHA-256: `79dedc1525bc4f04057b36f3e395845f9dae16d484d9122c61518f3be6e2dfc8`
- event stream: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`、
  173,498,680 events、全9 domain一致

すべて`picotetris-opt1b`の登録値と一致した。profilerは状態を観測・集計するだけでexecution orderを
変更していない。normal buildではfeatureごとコードが除外される。
backend CI run `31258130408`ではdefault buildに加え、OPT2-B featureのtest、fmt、Clippyも合格した。

## Result

| metric | value | interpretation |
|---|---:|---|
| total cycles | 927,528,660 | 全run |
| running cycles | 308,932,816 (33.3071%) | OPT2の対象母数 |
| running dispatches | 172,715,307 | Serial running step |
| boundary steps | 94,014,038 (54.4330%) | 複数sourceは重複計数 |
| candidate dispatches | 28,608,173 (16.5638%) | post-hoc候補 |
| candidate cycles | 46,411,891 (runningの15.0233%) | post-hoc候補cycle mass |
| candidate intervals | 2,388,571 | 平均11.977 dispatch、19.431 cycle |
| 2 dispatch以上のcandidate mass | 46,191,140 cycle | 全run virtual cycleの4.9800% |

主な観測境界はPIO/device 85,620,520、CPU MMIO 46,442,648、FIFO/DREQ 13,484,531、
timer/SysTick/PWM 1,090,337だった。現在のhorizonを1 cycleへ制限したsource別cycleはPIO
217,027,394、UART 40,197,601、DMA 5,320,143であり、今後candidate範囲を広げる場合の主対象を
明確にした。

4.9800%はvirtual cycle massの割合であってwall-time上限ではない。blocked fast-forward後は
running pathとblocked pathの1 cycle当たりcostが異なり、batch後もCPU decode/executeは残る。
したがって、この値から「5%未満だから不採用」または「5%改善できる」とは判断しない。

## Decision and next step

OPT2-B profilerは完了とする。production最適化はまだ追加しておらず、active targetも変更しない。
分布は機会がゼロでない一方、候補がrunning cycleの15.02%に限られ、区間も平均19.43 cycleと短い。
次はOPT2-Cとして、現在の保守的horizon内かつCPUがMMIOを行わない区間だけを対象にした小規模な
exact batching prototypeを一変更単位で作る。まずcandidate区間で省けるper-dispatch orchestration
costを実測し、正確性gateの後にtrace OFF A/Bで5%採用目安を判定する。PIO/UART/DMAのdeadline
promotionは、この限定prototypeの利得が不足した場合にだけ別候補として設計する。

## Artifact integrity

- `running-event-horizon-profile.json`: `27d462fd6acc98bcfd42de8ace12b43bccff168b47a624285ab1d42213ac6a80`
- `run-report.json`: `75867be9188dc020941fcbe35fd8f9761191ac4e4b910346c78f564c9c1ab042`
- `behavior-trace.json`: `a7fc839a4f9381525018b2d21b0b425cb8e9b721d29e80cf1bf3390370585835`
