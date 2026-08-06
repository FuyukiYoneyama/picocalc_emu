# R5実機相関前のエミュレーター実時間性能

この文書は、R5の実機相関へ入る前に、登録済みPicoTetris workloadが実時間に対して
どの速度で進むかを固定した性能baselineである。実機合否の証拠ではなく、R5 hardware
correlation自体はまだ完了していない。

## 指標

本書の「実時間比」は次で定義する。

```text
real_time_percent = emulated_seconds / wall_seconds * 100
slowdown          = wall_seconds / emulated_seconds
```

100%なら実機と同じ時間で進み、50%なら実機の半速、5%なら実機の20分の1の速度である。
CPU使用率や「1秒あたりの描画frame数」ではない。仮想時間はrunner reportの`elapsed_us`を
使う。これは起動時のclockからfirmwareが設定した`clk_sys`へ切り替わるたびにrebaseされるため、
全cycleを一律250 MHzで割った近似値ではない。

## 固定workload

| 項目 | 固定値 |
|---|---|
| target | `picotetris-r4` revision 2 |
| BIN SHA-256 | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` |
| backend | `3bc6bbd7833e45fbf94d640eb7fbe056dd9fbd81`、release build、Serial |
| scenario | `tetris-line-clear`、85/85 steps |
| device | PIO0/RGB565 LCD、PSRAM、keyboard、FAT32 SD |
| quantum | `1`（PSRAMのPIO edgeを各sysclkで観測する正しさの条件） |
| 到達cycle | `927,528,660` |
| 仮想時間 | `3.715000 s` |

build時間、backend/targetの事前検査時間は測定から除外した。release runner processの起動、
BIN/bootrom load、device生成、scenario、report/UART/PNG書き出しは含めた。1回のwarm-upを
集計から除外し、同じ論理CPUへ固定して10回測定した。全runのreport、UART、PNGは
byte-identicalである。今回の記録はrunnerの前後を`date +%s%N`で挟んだnanosecond wall-clock
timestampの差で採取した。再測定ツールは時刻調整の影響を受けない`time.perf_counter_ns()`を使う。

## 理論値

このworkloadの仮想平均clockは次になる。

```text
927,528,660 cycles / 3.715000 s = 249,671,240.915 cycles/s
```

したがって100% real timeの必要条件は、wall time `3.715000 s`以内に約249.671 Mcycle/sを
処理することである。`quantum=1`なので、master-clock dispatchもほぼ同じ頻度で必要になる。

測定したWSLが報告するhost clockは3,693.098 MHzである。仮に1 dispatchをhost CPUの
1 clockだけで処理できるという実現不能な下限を置くと、理論上限は1,479.184%となる。
100%を達成するために使える予算は1 dispatchあたり14.792 host clocksしかない。

これは**上限であって予測値ではない**。実際のdispatchはThumb decode/execute、二つのcore、
PIO、DMA、GPIO edge、LCD、PSRAM、SD、scenario pollなどを処理し、cache・branch・OS/WSL
schedulingも受ける。したがってソースだけから一意な実行時間を導くことはできない。

## WSL実測値（2026-08-06）

環境はWindows上のWSL2 Ubuntu 24.04.4 LTS、kernel
`6.18.33.2-microsoft-standard-WSL2`、AMD Ryzen 5 5600X、12 logical CPUsである。
runnerはlogical CPU 0へ固定し、測定中の1分load averageは0.50〜1.06だった。

| run | wall秒 | 実時間比 | 実機比の遅さ |
|---:|---:|---:|---:|
| 1 | 64.267121 | 5.780561% | 17.299360倍 |
| 2 | 61.003966 | 6.089768% | 16.420987倍 |
| 3 | 62.560364 | 5.938265% | 16.839936倍 |
| 4 | 63.157131 | 5.882154% | 17.000574倍 |
| 5 | 62.895334 | 5.906638% | 16.930103倍 |
| 6 | 63.982774 | 5.806250% | 17.222819倍 |
| 7 | 62.167212 | 5.975819% | 16.734108倍 |
| 8 | 68.340057 | 5.436051% | 18.395708倍 |
| 9 | 63.336885 | 5.865461% | 17.048960倍 |
| 10 | 63.744329 | 5.827969% | 17.158635倍 |

| 統計量 | wall秒 | 実時間比 | emulated cycle/s | 遅さ |
|---|---:|---:|---:|---:|
| 平均 | 63.545517 | 5.850894% | 14.607999 M | 17.105119倍 |
| 中央値 | 63.247008 | 5.873808% | 14.665208 M | 17.024767倍 |
| 標本標準偏差 | 1.934651 | 0.171321 point | 0.427739 M | 0.520768倍 |
| 最小〜最大 | 61.003966〜68.340057 | 5.436051〜6.089768% | 13.572255〜15.204399 M | 16.420987〜18.395708倍 |
| 平均の95% CI（t, df=9） | 62.161551〜64.929483 | 5.728338〜5.973449% | 14.302012〜14.913985 M | 16.732584〜17.477654倍 |

代表値は外れ値に強い中央値を使い、**このWSL・このR5 workloadでは実時間の5.874%、
約17.025倍遅い**とする。報告されたhost clockで換算すると、中央値は1 emulated cycleあたり
約251.827 host clocksに相当する。

この値はエミュレーター全般の定数ではない。PSRAMを外せるtargetはquantum 16または64で
dispatch overheadを償却できるため速くなる可能性がある。R5との対応を優先し、ここでは
正しさを変える高速化設定を混ぜない。

## 再測定

固定BINとaccepted backendのrelease runnerを用意し、次を実行する。

```sh
python3 tools/benchmark_firmware_realtime.py \
  --target picotetris-r4 \
  --firmware /path/to/PicoTetris.bin \
  --backend-dir /path/to/picoem-picocalc \
  --cpu 0 --warmup 1 --runs 10 \
  --json /tmp/picocalc-realtime.json
```

CPU型、電源設定、WSL/OS、host負荷が変わればwall timeも変わるため、別環境の値はこの記録を
上書きせず別recordにする。機械可読な今回の値は
`firmware-validation/records/r5-preflight-20260806-01/realtime-performance.json`にある。
