# OPT2-D 候補レバー比較

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


## 結論

OPT2-Dの計測は完了した。次のproduction prototypeには
**PIO exact event horizon / bulk advance**を選ぶ。CPU/decode block cacheは有望性を残すが、
動的な連続hit列が平均4.563命令と短いため、計画どおりOPT3へ残す。UARTはPIOの次、DMA単独は
優先しない。

この結論はwall timeの予測ではない。profileは計装runであり、次の値を明示している。

- `valid_for_wall_time=false`
- `fallback_occupancy_is_safe_window=false`
- `decode_hit_runs_are_speedup_prediction=false`

## 比較したもの

同一のPicoTetris runから、互いに意味の異なる二系統を採った。

1. PIO/UART/DMAが保守的event horizonを1 cycleに固定した占有量。重複を失わない16 signatureで
   `PIO`, `UART`, `DMA`, `any_other`を記録する。
2. core別decode-cache hit/missと、動的に連続するsequential cache-hit列の`2^n`累積分布。

前者はevent scheduler側の候補量、後者はCPU block側の候補量である。両者のcycle massを足したり、
そのまま短縮秒数へ変換してはならない。

## 固定入力

| 項目 | 値 |
|---|---|
| backend | `e482172565fc3073ba0960eb5e2642968a65ae52`、clean |
| target | `picotetris-opt1b` revision 5 |
| firmware BIN | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| scenario | `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208` |
| execution | Serial、quantum 1、PIO RGB565、PSRAM、keyboard、FAT32 SD |
| profiler | `event-horizon-profiler`、schema 2 |

runnerはbackendで次のようにclean buildする。

```bash
cargo clean
cargo build --locked --release -p picocalc-harness \
  --features event-horizon-profiler --bin picocalc-run
```

firmwareはtarget registry記載のPicoTetris source commit、SDK 2.2.0、Ninja、固定timestampから
再生成し、BIN SHAを照合する。実行形は次である。

```bash
target/release/picocalc-run \
  --bin /absolute/path/to/PicoTetris.bin \
  --bootrom roms/rp2040/bootrom-rp2040-b2.bin \
  --cycles 8000000000 --quantum 1 \
  --board picocalc --lcd-variant pio-rgb565 \
  --psram --keyboard --sd --sd-format fat32 \
  --scenario /absolute/path/to/picocalc_emu/scenarios/tetris-line-clear.json \
  --snapshot-dir /absolute/path/to/output/snapshots \
  --expect-stop scenario_done \
  --expect-uart '[TETRIS] start' \
  --expect-uart '[TETRIS] cleared=' \
  --expect-uart 'score=1400 lines=13' \
  --json /absolute/path/to/output/run-report.json \
  --event-horizon-profile /absolute/path/to/output/running-event-horizon-profile.json
```

behavior exactnessは`cargo clean`後に`behavior-trace` featureで別runnerを作り、同じ引数から
`--event-horizon-profile`を外して`--behavior-trace`を指定する。同一runで性能とtraceを兼用しない。

## exactness

85/85、927,528,660 cycle、3,715,000 virtual us、UART、framebuffer、behavior SHA、
173,498,680 event、全9 domainが登録済みOPT1-B値と一致した。計装を入れたbackend commitで
挙動差はない。

## peripheral horizon結果

runningは308,932,816 cycleである。one-cycle fallback signatureのunionは257,246,995 cycle、
runningの83.2696%、全runの27.7347%だった。

| signature | cycle mass | running比 |
|---|---:|---:|
| PIO only | 217,025,266 | 70.2500% |
| UART only | 34,901,586 | 11.2975% |
| DMA only | 22,000 | 0.0071% |
| PIO + DMA | 2,128 | 0.0007% |
| UART + DMA | 5,296,015 | 1.7143% |

PIO-onlyは全run cycleの23.3982%でもある。ただしpin transitionやLCD/PSRAM応答を含むので、
このcycleを捨ててよいという意味ではない。PIOをexactにまとめて進められなければ、UART/DMAだけを
改善しても最大のhorizonは開かない、という優先順位を示す。

## CPU/decode結果

core 0のcacheable hitは172,417,748、missは297,282で、hit率は99.8279%だった。core 1は
実行しなかった。sequential hit runは37,786,899本、平均4.563命令である。

| 最小run長 | hit命令mass | 全hit命令比 |
|---:|---:|---:|
| 4 | 86,811,548 | 50.3495% |
| 8 | 47,058,537 | 27.2933% |
| 16 | 23,317,771 | 13.5240% |
| 32 | 942,517 | 0.5466% |
| 64 | 18,085 | 0.0105% |

hit率は十分高いが、長い直線列は少ない。CPU block cacheはdecode lookupやRust dispatchを減らす
可能性がある一方、code write invalidation、branch、MMIO、exception、dual-core可視性を保つ必要が
ある。event schedulingより先に混ぜず、OPT3の独立変更単位とする。

## 優先順位と次gate

1. PIO exact event horizon / bulk advance
2. UART exact deadline promotion
3. CPU decode/execute block cache（OPT3）
4. standalone DMA deadline promotion

次prototypeはまず限定PIO状態についてone-cycle referenceと以下を完全一致させる。

- PIO state machineの全状態とFIFO/DREQ
- pin transitionのcycleと順序
- LCD/PSRAMを含むdevice応答
- IRQ assertion、NVIC delivery、exception entry
- CPUから観測できるMMIO/GPIO値

このexactness gateを通った後だけtrace-OFF A/Bを行い、5%改善基準で採否を決める。

完全なartifactは
[`opt2-d-lever-comparison-20260809-01`](../../firmware-validation/records/opt2-d-lever-comparison-20260809-01/notes.md)
に固定する。
