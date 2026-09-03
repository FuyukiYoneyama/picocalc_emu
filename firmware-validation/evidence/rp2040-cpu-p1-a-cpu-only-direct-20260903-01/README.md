# RP2040 CPU単体 P1-A 直接計測

- 測定日: 2026-09-03
- candidate: `58e73010636bb1b60fdb1ccace40db29b5bb96cc` (`decode-invalidation-tag-guard` default-on)
- baseline: `d8f5bb22fae221a7a31ae45c953b64b375eeb316` (index-only invalidation)
- 目的: PicoCalc周辺装置を含めず、P1-Aの decode-cache invalidation guard が CPU hot path に与える速度差を直接測る。

## 公式測定

`official-1b/` に measured raw log 20本、warmup raw log 2本、metadata、完了時刻を保存した。

- workload: `self-invalidate`
- single-core / Serial、`taskset -c 11`
- 1 run = 1,000,000,000 emulated cycles、process内 warmup 1 + measured 1
- 10 paired runs（奇数 pair は baseline→candidate、偶数 pair は candidate→baseline）
- arm間 cooldown 1秒
- primary: `host_cycles_per_emu` の paired log ratio `log(baseline / candidate)`
- 解析: 全10 pairを保持、事後除外なし、df=9 の両側95% t区間（t=2.2621571627）

結果（`summary.json` と同じ値）:

| 指標 | baseline | candidate |
|---|---:|---:|
| median executed MHz | 124.963556 | 142.810288 |
| median host cycles / emulated cycle | 31.715413 | 27.730372 |

- paired point estimate: **+15.324225%**
- paired median: **+14.289532%**
- 95% CI: **+12.471306% ～ +18.249511%**
- pairごとの速度差: **全10 pairでcandidateがプラス**（+10.278423% ～ +22.797550%）

`executed MHz` はこのホスト上での flat-out throughput であり、RP2040実機のクロックを変更した値ではない。採否の根拠はこの CPU単体値だけでなく、実アプリA/Bの combined raw **+1.218973%** と併せて扱う。後者の記録は `firmware-validation/records/rp2040-cpu-p1-a-production-v3-20260902-03/` にある。

## workloadがP1-A経路を通ることの確認

loopは `0x2000_0000` のThumb codeを実行し、毎回 `0x2000_4004` へ SRAM word storeする。`0x4000` byte差で store先は hot code と同じ direct-mapped slot（8192 entries）に衝突するが、物理SRAMアドレスは異なる。従来baselineはその slotを無条件clearし、P1-Aはfull tag不一致を検出して保持する。

`diagnostic/` は `cpu-application-profiler` を有効にした確認用ログであり、速度値には使っていない。250M-cycle runで両armとも 83,333,396 invalidation requestを生成した。baselineは decode miss 83,333,399、candidateは5で、candidateの tag guard が無関係なslotのevictionを抑止していることを確認した。profiler自体の計測オーバーヘッドがあるため、これは経路確認用である。

## 補助データ

- `pilot-250m/`: 同じ workloadの 250M-cycle × 20 pair。短時間のためホスト遅延1件が混入しており、公式値には使わず全rawを保存した。
- `scope-invalid-basic-250m/`: `basic` loopの初回試行。SRAM storeがなくP1-Aを通らないため、効果測定の採否資料から除外した（失敗ではなくスコープ不適合の記録）。
- `pilot-self-invalidate-50m/`: 50M-cycle短時間pilot。benchmarkの1秒monitor待ちの影響を含むため、公式値には使わない。
- `baseline-harness.diff` / `candidate-harness.diff`: scratch worktreeで追加した診断 workload と精度表示の差分。production backend sourceの変更ではない。
- `binary-sha256.txt`、`environment.txt`: 実行バイナリと環境のprovenance。
- `feature-tree-baseline.txt` / `feature-tree-candidate.txt`: baseline/candidateの実効Cargo feature。
- `valid_matrix_long.sh`: 公式20-runの固定実行script（scratchで使用したもの）。

機械可読な集計値と全pairの数値は [`summary.json`](summary.json) を参照する。
