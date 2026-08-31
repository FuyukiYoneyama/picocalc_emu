# RP2040 CPU 実アプリ高速化 実装・効果測定計画

- Status: P0-A1 implemented — P0-0 passed — P0-A2 currently has six immutable invalid records (four completed v1 invalid batches, one aborted v2 preflight record, and one completed v2 model-invalid batch). Batch `rp2040-cpu-p0-null-v2-20260831-02` completed with CPU 11: 40 runs, 15 anchors, checksum, target-schema, and all raw/host-corrected null-effect checks passed, but the global log-linear anchor model gate was invalid (maximum residual 5.1743%; RMS 3.1993%; 2% limit) while every replicated-anchor dispersion gate passed. P0-A2 protocol v2 (replicated anchors with fixed median/MAD aggregation) is implemented and preserved as immutable invalid evidence. The v3 protocol (27 anchors at nine boundaries, piecewise log interpolation, deterministic leave-one-group-out local residual gate, and unchanged 2% dispersion/sensitivity/null thresholds) is now implemented in runner/schema/verifier/tests; CPU11 correctness for both workloads is complete in `rp2040-cpu-p0-null-v3-20260901-01`, and its real null-control measurement is pending — P0-B profiler implementation/profile/correctness complete — P1-A implementation/profile/correctness complete; its existing correctness record has no measurement CPU and must be regenerated with the A/B CPU, while its profile is diagnostic-only and is not an A/B admission gate — P2-A implementation (`ba93c1f`), feature tests, correctness record `rp2040-cpu-p2-a-correctness-20260831-01`, and diagnostic profile `rp2040-cpu-p2-a-profile-20260831-01` complete (both workload profiles valid; no-candidate reject 99.989%/99.943%; aggregate/core/source equations pass), but existing P2-A correctness/profile records use CPU 1/0 and cannot be pointer-gated to a CPU 11 A/B — P1-A/P2-A production A/B and performance acceptance pending a valid host-calibration null-control plus CPU-aligned correctness/profile records where the gate requires them
- Date: 2026-09-01
- Review completed: 2026-08-31
- Scope: `picocalc_emu` が使用する RP2040 CPU エミュレーションの正確性を維持した高速化
- Implementation repository: `picoem-picocalc`
- Validation and decision repository: `picocalc_emu`

## 0. レビュー結果と適用した修正

現行計画、登録 target、既存計測文書、`rp2040-emu`/`picocalc-harness` の実コードを照合し、Luna による二系統の読み取り専用レビューも行った。実装開始を妨げていた事項は、次のように解消した。

| レビュー指摘 | この版での解決 |
|---|---|
| 登録 target ごとに accepted backend が異なる | 登録記録を変更せず、候補比較用の共通 baseline を P0-0 で二つの実アプリに admission する |
| 既存 realtime benchmark は candidate backend、AB/BA、CPU専用統計を扱えない | 既存 script を変更せず、専用 `benchmark_rp2040_cpu_candidate.py` を新設する |
| P0 が将来候補の全 counter を一度に要求していた | P0-A1/A2 の runner/schema/null batch と P0-B の最小 profiler に分割し、候補固有 counter は各 phase へ遅延する |
| profile、A/B、decision の schema と保存名が未確定 | schema 名、record tree、必須ファイルを本書で固定した |
| 10 pair、CI、calibration の定義が曖昧 | 20 run/workload、5 AB+5 BA、log ratio の t 区間、実アプリ calibration anchor と residual gate を固定した |
| 正確性比較で executable identity まで一致させる矛盾があった | firmware/scenario は同一、backend/runner identity は別々に記録し、guest observation projection だけを一致させる |
| P1-A が両 core の同時 invalidation を要求し、現行 active-core drain と衝突していた | 配送先の意味論は変更せず、active core に対する full-tag 判定を実装し、core 0/1 を個別に試験する |
| P2 が最初から mutation-maintained summary を要求していた | まず既存状態を読む inline reject + cold arbitration の P2-A とし、summary は測定後の P2-B に分離した |
| 一時 worktree と raw data の置き場所が運用ルールと不整合だった | 一つの `/tmp/picocalc-rp2040-cpu-opt.*` だけを使用し、共有 root 直下へ新規 directory を作らない |
| 既存の合成 workload 測定が実アプリ採否に混ざり得た | 合成測定は仮説の方向付けだけとし、採否証拠から明示的に除外した |

この版で「実装開始可能」とは、まだ存在しない runner/schema を作る単位について、ファイル、CLI、schema、統計、テスト、完了条件が固定され、実装者が追加設計判断なしに着手できることを指す。実装順は `P0-A1 runner/tests → P0-0 admission → P0-A2 null-control protocol → P0-B profiler` とする。P0-B の counter-only instrumentation は null-control の wall-time 採否とは独立に開始できるが、P1 以降の候補実装・promotion は P0 の実測 gate を通った後だけにする。

P0-A1 の runner、record/build-provenance schema、environment verifier、固定 fixture test は実装済みで、単体テストと target-schema 検証を通過した。runner は phase 間で同一 record root を再利用しつつ leaf を上書きせず、manifest の identity merge、既存 checksum の再検証と aggregate `SHA256SUMS`、role 別の実効 Cargo feature と build sidecar、decision の実行 identity、correctness gate、固定 40-run 条件、calibration invalid 記録を実装している。behavior trace は trace-only metadata と domain digest を fail-closed で検査する。P0-0 の実 workload admission は `firmware-validation/records/rp2040-cpu-p0-baseline-20260830-03/` として完了した。P0-A2 は同一 production runner を A/B に指定する null batch を四回完走させ、いずれも correctness、40 measured run、checksum、target-schema を満たした。最初の二 batch は pre/post host throughput drift が 14.68% と 3.668% で invalid、改訂 batch `rp2040-cpu-p0-null-20260831-04` は null-control の raw/host-corrected 効果と CI はすべて固定閾値内だったが、anchor-after-020 を含む anchor 最大残差が 4.3027% となり invalid、CPU 11 の batch `rp2040-cpu-p0-null-20260831-05` も null-control の raw/host-corrected 効果と CI はすべて固定閾値内だったが、anchor-post-003 の局所外れにより最大残差 4.5046% となり invalid である。第四 batch の `pre_post_relative_drift` は 1.5724% と2%未満だったため、pre/post差だけでは検出できない局所外れ値であることも確認した。従って runner、admission、schema、記録検証、null-effect計算は有効であり、未解決なのは長時間 host stability の単発 anchor 外れ値である。target-schema verifier は、このように個別 null-effect が pass でも calibration gate で invalid になった recordを正しく受け入れるよう修正し、37 checks と regression test が pass した。P0-A2 v2 は、5境界（pre、run 10/20/30直後、post）を各3回測定し、各境界の log-throughput median と scaled MAD（`1.4826 × MAD`）を保存する実装へ更新した。単発外れ値は中央値で吸収するが、各境界の relative MAD が2%を超える、集約5点の anchor residual が2%を超える、または anchor/identity/correctness/host条件が不成立なら新しい batch 全体を invalid とする。P0-B は backend commit `c123933423477b878a1dde8b1f80fb3d731bc8e3` へ counter-only instrumentation を実装し、profile、compile-out、production/behavior-trace correctness を完了した。さらに P1-A は runtime 実装を `2a9e8cf`、SRAM alias を含む正確性修正を `61f8bde`、provenance の feature 列挙を `6f8ce41` として完了した。P1-A の correctness record `rp2040-cpu-p1-a-correctness-20260831-02` は runtime が変わらない `61f8bde` の runner で guest projection/behavior trace を pass し、profile record `rp2040-cpu-p1-a-profile-20260831-02` は provenance 修正後の `6f8ce41` で有効な profile を保存している。`6f8ce41` は build.rs の feature-set 列挙だけを変更し、CPU runtime semantics は `61f8bde` と同一である。この identity 差を記録上明示し、速度向上の採否には profile を使わない。P0-B/P1-A は wall-time の採否を主張しないため、P2-A の実装開始条件は満たすが、P0-A2 の有効な v3 null-control と P1-A/P2-A の性能採否は別途必要である。

P2-A の feature-on diagnostic profile `rp2040-cpu-p2-a-profile-20260831-01` は、両 workloadで `profile_valid=true`、overflowなし、aggregate/core/source conservation pass、no-candidate reject率 99.989%（PicoTetris）/99.943%（PicoEdit）を確認した。従って P2-A の診断内容自体は pass である。ただしこの profile の `measurement_cpu=0`、P2-A correctness の CPU は 1、P1-A correctness は CPU 未記録であり、P2-A の profile/correctness と P1-A の correctness が `ab --cpu` の CPU identity gate を満たさない。P1-A profile は診断専用で A/B admission には使わない。batch 05 は anchor stability gateでinvalidだったため、v3 null-controlがpassした場合にA/B採用CPU 11へ P1-A correctness、P2-A correctness、P2-A profileを揃えて取り直してから production A/Bを開始する。

`rp2040-cpu-p0-null-v2-20260831-02` は 2026-09-01 に CPU 11 で完了した。40 measured run、15 anchor、replicate identity、checksum、correctness、target-schema は passし、各 anchor group の relative MAD は 0.628〜1.818% で固定2% gate内、workload別/combined の raw・host-corrected null effect と95% CIも全条件を満たした。一方、5 group medianを一本の global log-linear modelへ当てた残差は最大5.1743%、RMS 3.1993%、pre/post driftは4.6312%となり、固定2% model gateで `summary.status=invalid` とした。group中央値は 5.243M → 4.938M → 4.712M → 4.898M → 5.000M cycles/s相当で谷形に変動しており、同一 executable の隣接 pair 差分ではなく、非線形な host trajectory が原因である。これは v2 の invalid evidence として保持し、結果を再解釈しない。

v2 の `measurement_policy` は correction method を piecewise interpolation と宣言していたのに、model gateだけを global line として実装していた。この契約不一致を閾値緩和で解決しない。次の v3 は `calibration_method=interleaved-anchor-v3` として別 batch IDで固定し、同じ40 run、9境界×3 replicate（27 anchor）、60秒 cooldown、CPU11、同一 workload/identityを維持する。境界は `pre, after-005, after-010, after-015, after-020, after-025, after-030, after-035, post` とし、各 group median を実際の piecewise log-linear knotsとして measured runを補正する。`anchor_residual_threshold=0.02` は旧互換のglobal residual診断値にのみ適用し、採否は `anchor_local_residual_threshold=0.02` の deterministic leave-one-group-out local residualで判定する。採否gateは (a) 全group relative MAD ≤2%、(b) replicate数・順序・guest projection/backend/runner/CPU/affinity/correctnessが一致、(c) 9 group の local residual 最大値 ≤2%、(d) 隣接 pair の raw-vs-corrected log-ratio差の最大絶対値 ≤2%、(e) 既存の workload別2%・combined1%の raw/corrected null effect絶対値と95% CI条件、の五つに固定する。piecewise knotsが有限・正値で時間順、全 measured midpointが隣接 knot内にあることも必須とする。v2のglobal residual 5.1743%をpassへ読み替えず、v3実装・schema・verifier・unit testを先に完了してから新 batchを測定する。

## 1. 目的

普通の RP2040 アプリケーションを実行したときの CPU エミュレーションを、観測可能な動作を変えずに高速化する。

特定の速度倍率への到達可否や合成命令列の理論上限は、この計画の判断基準にしない。実在するアプリケーションで CPU ホットパスを計測し、実装候補ごとの実効速度差を必ず A/B 測定する。

周辺装置は高速化対象から外す。ただし、測定時には周辺装置を無効化せず、通常のアプリケーション実行を維持する。CPU 側の改善が現実の負荷構成で有効かを確認するためである。

## 2. 完了条件

本計画の完了は「最適化コードを書いたこと」ではなく、次のすべてを満たした状態とする。

1. 実アプリから CPU ホットパスと無駄な処理を定量化している。
2. 各候補を独立した feature または commit として実装している。
3. 各候補について正確性検証と性能 A/B 測定を完了している。
4. 効果が正、ゼロ、負のいずれでも、生データ、集計値、判断理由を保存している。
5. 単独では小さいが独立した改善は候補バンクへ集め、組み合わせた状態も改めて測定している。
6. 採用した変更について、代表アプリで統計的に識別できる改善と、重大な回帰がないことを確認している。重大な回帰は、各アプリの median throughput が共通 baseline より 3% を超えて低下することと定義する。

## 3. 保存場所

### 3.1 Git 管理するもの

`picocalc_emu` には次を保存する。

- 本計画、計測仕様、実行手順
- workload、scenario、admission descriptor の固定情報
- 全測定 run の小容量な JSON/CSV 結果
- 集計結果、グラフ生成スクリプト、採否記録
- backend commit、実行ファイル SHA-256、ホスト条件、コマンドを含む manifest
- 正確性 proof と最終的な回帰テスト

CPU backend のソース変更は `picoem-picocalc` の Git 管理下に置く。

### 3.2 一時物と大容量 raw data

一回の作業開始時に、次の形式で一つだけ一時 root を作る。

```bash
RP2040_CPU_OPT_TMP="$(mktemp -d /tmp/picocalc-rp2040-cpu-opt.XXXXXX)"
```

比較用 worktree、Cargo build directory、`perf.data`、sampling 中間物、PGO raw profile、大容量 trace、再生成可能なログはすべてこの root の下へ置く。`/home/fuyuki/pico_dvl/codex` 直下に新しい受け皿を作らず、`workspace-management` にも本計画の成果物を置かない。

採否に必要な小容量 JSON と要約を Git 側へ収容してから一時 root を廃棄する。大容量 raw data の永続保存が必要になった場合だけ、既存のエミュレーター外部 workspace を使うかを人間に別途確認する。manifest には、永続保存しない raw data についても生成コマンド、生成元 commit、ファイル名、SHA-256 を記録する。

### 3.3 canonical record tree

候補ごとの履歴は上書きせず、次の形で保存する。

```text
firmware-validation/records/rp2040-cpu-<candidate>-YYYYMMDD-NN/
  manifest.json
  admission/
    admission-picotetris-opt1b-vrp5.json
    admission-picoedit-r1-vrp2f.json
  profile/
    picotetris-opt1b-vrp5-r10.json
    picoedit-r1-vrp2f-r4.json
  correctness/
    picotetris-opt1b-vrp5-r10/
      baseline-report.json
      candidate-report.json
      baseline-projection.json
      candidate-projection.json
      baseline-behavior.json
      candidate-behavior.json
      comparison.json
    picoedit-r1-vrp2f-r4/
      baseline-report.json
      candidate-report.json
      baseline-projection.json
      candidate-projection.json
      baseline-behavior.json
      candidate-behavior.json
      comparison.json
  ab/
    run-001.json ... run-040.json
  summary.json
  decision.json
  decision.md
  hotpath-disassembly.txt
  SHA256SUMS
```

P0-0 で target revision が更新された場合は、上の workload filename も新 revision に置き換える。record artifact schema 四つ（profile、profile-comparison、A/B、decision）と build provenance schema 一つを新設し、既存 schema の `schema_version: 1` と混同しないよう `schema_id` を必須にする。

P0-A2 の `comparison.json` は `trace_required=false` とし、behavior artifact 四ファイルは作らない。P0-B/P1以降は `trace_required=true` とし、baseline/candidate behavior artifact を必須にする。この条件分岐を AB schema に持たせる。

- `firmware-validation/rp2040-cpu-profile.schema.json`: `schema_id = "picocalc.rp2040-cpu-profile"`
- `firmware-validation/rp2040-cpu-profile-comparison.schema.json`: `schema_id = "picocalc.rp2040-cpu-profile-comparison"`
- `firmware-validation/rp2040-cpu-ab.schema.json`: `schema_id = "picocalc.rp2040-cpu-ab"`
- `firmware-validation/rp2040-cpu-decision.schema.json`: `schema_id = "picocalc.rp2040-cpu-decision"`
- `firmware-validation/rp2040-cpu-build-provenance.schema.json`: `schema_id = "picocalc.rp2040-build-provenance"`（runner sidecar）

四つの record artifact schema と build provenance schema の初版はすべて `schema_version = 1` とする。互換性を壊す変更では version を上げ、historical record は変換・上書きしない。build provenance は record tree の leaf ではなく、runner に隣接する sidecar の schema とする。

P0-B 実装時に profile schema の nested `cores`/`counters` を counter 名・型・不変条件名まで閉じた
Draft 2020-12 定義へ強化した。既存の schema version は維持し、今回の profile record と過去 record を
同じ validator で再検証する。schema は数値の conservation 自体を再計算しないため、実行時 invariant
と compile-out/correctness evidence を併せて保存する。

## 4. 現時点の根拠

既存の PicoTetris 実行プロファイルには、次の CPU 側の特徴が出ている。

- core 0 decode cache: 172,417,748 hit、297,282 miss、hit 率 99.8279%
- immutable XIP hit: 172,373,954
- SRAM hit: 20,679
- immutable XIP hit run: 平均 4.563 命令
- block 終了の大部分: PC redirect 37,756,069 回
- SRAM decode invalidation address: 9,243,286 回

根拠は [OPT3-A XIP cursor profile](history/OPT3_A_XIP_CURSOR_PROFILE.md) と、対応する [machine-readable profile](../firmware-validation/records/opt3-a-xip-cursor-profile-20260809-01/running-event-horizon-profile.json) にある。

この結果から、miss 時の decoder 自体より、次を先に測定・改善する。

1. hit 済み命令を再利用するまでの処理
2. 命令と無関係な SRAM data write による cache invalidation
3. 命令ごとの pending exception 探索
4. 高頻度命令の operand 再抽出と dispatch
5. 分岐後の次命令検索
6. host compiler が生成する hot path の品質

過去の sequential cursor は、内部 hit を増やしても実アプリ全体で約 4.43% 回帰した。したがって、内部 counter の改善だけを成果とせず、必ずアプリ全体を測る。

compact dispatch key は過去の PicoTetris で約 4.15% 改善したが、当時の固定 5% 閾値だけを理由に採用されなかった。現在の backend で再測定し、小さい実改善を一律に捨てない。

[CPU hot-path measurement](validated-realtime-preview/CPU_HOTPATH_MEASUREMENT_20260830.md) にある `paced_bench_rp2040 --workload basic` の差分測定は、二つの PC を回る合成 loop に対する方向付け資料である。例外 poll、flags、compact dispatch に改善余地があるという仮説には使えるが、通常アプリの採否、改善率、候補順位を確定する証拠には使わない。sampling profiler はホスト権限が許す場合の補助証拠であり、P0 や候補実装の開始条件にはしない。

## 5. 測定契約

### 5.1 実アプリ workload

最低限、次の登録済みアプリを毎候補で測る。

| 役割 | 登録 target | firmware/scenario | 登録時 backend |
|---|---|---|---|
| 主 workload | `picotetris-opt1b-vrp5` revision 10 | BIN `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62` / scenario `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208` | `65c795e87321e79b960ac8a7495a205de6a24ec0` |
| 異種 workload | `picoedit-r1-vrp2f` revision 4 | BIN `17cb513b8dd3ea6525ce6bd92d1ce3081bb6ea9730c590c2afb86a9fa085e8f6` / scenario `d7af28965f49cd7363ca5ac68678572d3e6975eb426b6af828dd09a70505b718` | `c1c20d7d86a3006569375bc333cf72494e95eb46` |

固定 validation は [PicoTetris r10](../firmware-validation/validations/picotetris-opt1b-vrp5-r10.json) と [PicoEdit r4](../firmware-validation/validations/picoedit-r1-vrp2f-r4.json) である。レビュー時点で両 backend object は repository に存在するが、互いに ancestor ではない。さらに `c1c20d7d86a3006569375bc333cf72494e95eb46` は branch/tag のどの ref からも到達不能で、将来の `git gc` で消滅し得る。したがって登録時 backend pin を混ぜて一つの候補効果にしてはならず、PicoEdit は P0-0 の common-baseline admission を必ず通す。

候補比較の共通 baseline は、現行 backend ソースを固定した `73784b96a1afdb34dc1a79577f947b670a138d07` とする。この commit は登録時の `65c795e87321e79b960ac8a7495a205de6a24ec0` に現行 checkout の整形差分を取り込んだものであり、P0-0 ではこの最新の clean commit を基準にする。P0-0 で両 firmware/scenario をこの commit 上で実行し、target の `report_checks` から `backend_build.commit` だけを除いた全条件、登録 timeline SHA、登録 report から作った guest observation projection を満たすことを確認する。`backend_build.dirty == false` は必須である。backend identity を含む登録 `normalized_report_sha256` は candidate report へ直接適用せず、代わりに §5.5 の projection digest を使う。PicoEdit が通らない場合は測定を開始せず、両 workload が通る一つの共通 commit を選ぶか、新 revision を通常の validation 手順で登録する。既存 revision と record は変更しない。

target registry は firmware、scenario、board/device 条件、停止条件を供給する workload contract として使用する。candidate commit は既存 target の accepted backend として偽装せず、CPU候補 record の manifest に独立して記録する。

P0-A1 の runner は admission/profile/correctness/A-B の workload 集合を上記二つへ固定する。第三の workload を追加する場合は、登録・schema・固定 schedule・統計の対応を含む別の runner 拡張を先にレビューし、既存 record の workload 集合を変更しない。固定入力と固定停止条件を持つ登録済みアプリだけを使い、NOP loop、単一命令、`paced_bench_rp2040` の synthetic workload は単体確認には使えても、採否判定には使わない。

### 5.2 profile run と performance run の分離

同じ実行から詳細 counter と速度を同時に評価しない。

- Profile run: `cpu-application-profiler` feature を有効にし、CPU 内部 counter を採取する。
- Correctness run: production release の guest observation を完全一致させ、P1以降は別の diagnostic behavior-trace build の domain digest も完全一致させる。sampling profiler の可用性には依存させない。
- Performance run: profiler、trace、proof、GUI を無効にした production release で時間を測る。

build command は次に固定する。baseline/candidate/profile/trace で `CARGO_TARGET_DIR` を分け、後の build が先の executable を上書きしないようにする。

```bash
# baseline production
cd "$RP2040_CPU_OPT_TMP/backend-baseline"
CARGO_TARGET_DIR="$RP2040_CPU_OPT_TMP/build/baseline-production" \
  cargo build --locked --release -p picocalc-harness --bin picocalc-run
cd "$RP2040_CPU_OPT_TMP/backend-baseline"
cargo tree -e features --format '{p} {f}' --prefix none \
  > "$RP2040_CPU_OPT_TMP/build/baseline-production-tree.txt"

# candidate production; P1以降は下表の feature list を必ず指定
cd "$RP2040_CPU_OPT_TMP/backend-candidate"
CARGO_TARGET_DIR="$RP2040_CPU_OPT_TMP/build/candidate-production" \
  cargo build --locked --release -p picocalc-harness --bin picocalc-run \
  --features <candidate-feature-list>
cd "$RP2040_CPU_OPT_TMP/backend-candidate"
cargo tree -e features --format '{p} {f}' --prefix none \
  > "$RP2040_CPU_OPT_TMP/build/candidate-production-tree.txt"

# baseline diagnostic correctness trace; performanceには使用しない
cd "$RP2040_CPU_OPT_TMP/backend-baseline"
CARGO_TARGET_DIR="$RP2040_CPU_OPT_TMP/build/baseline-trace" \
  cargo build --locked --release -p picocalc-harness --bin picocalc-run \
  --features behavior-trace
cd "$RP2040_CPU_OPT_TMP/backend-baseline"
cargo tree -e features --format '{p} {f}' --prefix none \
  > "$RP2040_CPU_OPT_TMP/build/baseline-trace-tree.txt"

# candidate diagnostic correctness trace; performanceには使用しない
cd "$RP2040_CPU_OPT_TMP/backend-candidate"
CARGO_TARGET_DIR="$RP2040_CPU_OPT_TMP/build/candidate-trace" \
  cargo build --locked --release -p picocalc-harness --bin picocalc-run \
  --features behavior-trace,<candidate-feature-list>
cd "$RP2040_CPU_OPT_TMP/backend-candidate"
cargo tree -e features --format '{p} {f}' --prefix none \
  > "$RP2040_CPU_OPT_TMP/build/candidate-trace-tree.txt"
```

`<candidate-feature-list>` は shell へそのまま渡す文字列ではなく、次表の値へ置換する。P0-A2/P0-B の profiler-OFF production build では `--features` 行自体を省略する。

`feature_set` は記録だけの自己申告にしない。信頼した build wrapper が各 runner の隣に `<runner>.build.json` provenance sidecar を必ず生成し、runner は measured run 前に schema/version、role、backend commit/dirty、runner SHA-256、Cargo の実効 feature 集合、feature 集合の canonical SHA-256、lockfile SHA-256、正確な Cargo argv、`rustc -Vv`/`cargo -V` を照合する。sidecar の `runner_sha256` が binary と一致しない場合、また CLI 宣言・`cargo tree --format '{p} {f}'` の root feature・Cargo実効集合・role が一致しない場合は起動を拒否する。Cargo default の `sd-gen1-multiblock` も実効集合へ含める。sidecar は wrapper による生成証跡であり、測定 runner はその証跡がない build を受け付けない。

sidecar は各 backend checkout で build 後に取得した `cargo tree -e features --format '{p} {f}'` の root feature と lockfile を対象に生成し、record manifest には sidecar の SHA-256 と role 別実効 feature 集合を保存する。CLI の `--feature-set` だけを根拠にしてはならない。sidecar の生成・検証コマンド、Cargo argv、toolchain version は再現できる形で build log に残す。baseline/candidate/trace/profile の tree は、それぞれ対応する checkout で個別に取得する。

| candidate | production feature list | diagnostic trace feature list |
|---|---|---|
| P0-A2/P0-B compile-out check | なし | `behavior-trace` |
| P1-A | `decode-invalidation-tag-guard` | `behavior-trace,decode-invalidation-tag-guard` |
| P1-B | `executable-sram-invalidation-filter` | `behavior-trace,executable-sram-invalidation-filter` |
| P1 A+B | `decode-invalidation-tag-guard,executable-sram-invalidation-filter` | `behavior-trace,decode-invalidation-tag-guard,executable-sram-invalidation-filter` |
| P2-A | `pending-exception-fast-reject` | `behavior-trace,pending-exception-fast-reject` |

P0-B profile build は後述の `build/candidate-profile` へ出す。production build に profiler/trace の field、分岐、counter update、diagnostic CLI を残さない。`cargo tree -e features --format '{p} {f}'` と `objdump` の hot-function 抜粋で確認する。profile/trace run の速度は採否データに使用しない。`[profile.profiling]` は fat LTO が無効なので、performance 比較には使わない。

各 `cargo build` の直後に、その runner と同じ build directory へ `<runner>.build.json` を生成する。sidecar の `role` と実効 feature 集合は baseline production=`[sd-gen1-multiblock]`、candidate production=`[sd-gen1-multiblock] + candidate features`、baseline trace=`[sd-gen1-multiblock,behavior-trace]`、candidate trace=`[sd-gen1-multiblock,behavior-trace] + candidate features`、candidate profile=`[sd-gen1-multiblock,cpu-application-profiler] + candidate features` とする。P0-A2 null batch で同一 executable を A/B 両方へ指定する場合だけ、sidecar role=`production` を両 production role の代わりに使える。sidecar がない runner は P0-0 を含む全 phase で使用しない。

P1-A で実際に発生したように、新しい backend feature を追加した場合は、`picocalc-harness/build.rs` の `PICOEM_FEATURE_SET` 列挙にも同じ feature を追加する。これがない runner はビルド自体が成功しても、guest が出力する `feature_set` と sidecar の実効集合が一致せず、profile/correctness record の入口で fail-closed になる。feature 宣言、harness forwarding、build provenance 列挙、profile JSON、sidecar の五者が一致することを実装完了条件とする。

sidecar は専用 subcommand で生成する。対応する backend checkout で `cargo tree -e features --format '{p} {f}' --prefix none` の出力を一時 root へ保存し、次のように runner、lockfile、tree、全 Cargo argv、toolchain version を結び付ける。

```bash
cd "$RP2040_CPU_OPT_TMP/backend-baseline"
cargo tree -e features --format '{p} {f}' --prefix none > "$RP2040_CPU_OPT_TMP/build/baseline-tree.txt"
python3 /home/fuyuki/pico_dvl/codex/picocalc_emu/tools/benchmark_rp2040_cpu_candidate.py provenance \
  --backend "$RP2040_CPU_OPT_TMP/backend-baseline" \
  --runner "$RP2040_CPU_OPT_TMP/build/baseline-production/release/picocalc-run" \
  --role baseline_production \
  --lockfile "$RP2040_CPU_OPT_TMP/backend-baseline/Cargo.lock" \
  --cargo-tree "$RP2040_CPU_OPT_TMP/build/baseline-tree.txt" \
  --cargo-argv cargo --cargo-argv build --cargo-argv=--locked --cargo-argv=--release \
  --rustc-version "$(rustc -Vv)" --cargo-version "$(cargo -V)"
```

candidate/trace/profile は `--role` と `--feature-set` を対応する build に置き換える。`provenance` は backend clean/embedded commit と runner SHA をその場で検査し、既存 sidecar の上書きも拒否する。

### 5.3 CPU profile counter

P0-B 初版は、P1-A/P2-A の実装判断に必要な次の counter だけを core 別に記録する。将来候補のための load/store、flags、branch link、reuse-distance 全量計測を最初から hot path に入れない。

- `active: bool`、`retired_instructions: uint64`、`emulated_cycles: uint64`
- `pc_region.{boot_rom,immutable_xip,xip_sram,sram,other}: uint64`
- `decode.{lookups,hits,misses}: uint64`
- `decode.by_region.<region>.{lookups,hits,misses}: uint64`
- `invalidation.{requests,examined_slots,matching_clears,unrelated_would_clear,wide_predecessor_clears}: uint64`
- `exception.{polls,reject_primask,reject_no_candidate,reject_active_handler,entries}: uint64`
- `exception.source.{pendsv,systick,nvic}: uint64`
- `handler_group.{thumb16_shift_add_sub,data_processing,load_store,branch_system,thumb32,other}: uint64`

この初版 counter は P1-A/P2-A の開始判定を満たすが、P1-B の executable-page filter 判定に必要な
write 先 page の executable 状態は持たない。P1-B は profile-only 拡張で
`non_executable_sram_write_requests` を追加してから測定する。これを `unrelated_would_clear` から
推定してはならない。

profile root は `interval.start_emulated_cycle` と `interval.end_emulated_cycle`、workload identity、backend commit、runner SHA-256、feature set、core array、`overflowed`、`profile_valid` を持つ。counter は run 全区間の累積 `uint64` とし、reset でゼロに戻す。inactive core は `active=false` かつ全 counter zero とする。加算 overflow は saturate して `overflowed=true`、不変条件違反とともに `profile_valid=false` にする。

初版の不変条件は次である。

- `sum(pc_region) == retired_instructions`
- `decode.hits + decode.misses == decode.lookups`
- 各 region で `hits + misses == lookups`、かつ region 合計が decode 全体と一致
- `reject_primask + reject_no_candidate + reject_active_handler + entries == polls`
- `sum(exception.source) == exception.entries`
- `matching_clears + unrelated_would_clear <= examined_slots`

handler group は相互排他的にし、未知 encoding は `other` へ入れる。分類集合を変える場合は schema version を上げる。不変条件に違反した profile は破棄し、候補実装へ進まない。flags、link、cache geometry などの counter は該当 phase の事前 gate で schema extension として追加する。

### 5.4 performance A/B 手順

候補ごとに baseline と candidate を一つの batch として測る。

1. clean detached worktree を二つ作り、backend commit を固定する。
2. candidate は評価対象の変更だけを baseline に加える。
3. production release、fat LTO、`codegen-units=1` を共通にする。
4. `rustc -Vv`、`cargo -V`、linker、build command、environment、feature set を一致させる。
5. executable、firmware BIN、runner、target contract、scenario の SHA-256 を記録する。
6. 同一ホストの一つの logical CPU に `sched_setaffinity` で pin し、他の benchmark を並行実行しない。
7. workload/binary の各組合せを 1 回 warm-up し、集計から除外する。
8. 各 workload で 10 pair、すなわち 20 measured run を実行する。奇数 pair は AB、偶数 pair は BA とし、合計は 5 AB + 5 BA とする。
9. 二 workload 合計は 40 measured run である。pair ごとに workload 順も交互にして、片方だけが常に先にならないようにする。
10. run ごとの結果を `run-001.json` から順に上書きせず保存する。
11. 各 guest invocation の終了後に固定 60 秒の host-recovery cooldown を置く。cooldown は measured wall time に含めず、manifest、summary、decision の `measurement_policy` に記録する。値は結果を見て変更せず、変更時は新しい runner version と新しい batch ID を使う。

各 run で次を記録する。record の `host` snapshot には model、logical CPU 数、報告周波数中央値、load average、allowed CPU 集合、platform、kernel を保存し、manifest は開始時、summary/decision は完了時の snapshot とする。選択 CPU の affinity は設定直後に実効集合を再読し、要求値と一致しなければ measured run を開始せず失敗させる。

- `time.perf_counter_ns` で runner process 全体を囲った wall-clock time
- emulated cycles/second
- host user/system CPU time
- `RUSAGE_CHILDREN` の process-lifetime high-water mark としての maximum RSS（per-run delta と誤認しないよう `max_rss_scope=children_cumulative` を記録）
- 取得可能なら host cycles、instructions、branches、branch misses、cache misses
- stop reason と emulated cycle

host performance counter と sampling は補助指標であり、権限がないことを batch 失敗にしない。retired guest instructions/second は profiler OFF で無償に得られる場合だけ補助指標とし、取得のために production hot path へ counter を加えない。

統計手順は最初の結果を見る前に次で固定する。

- run throughput: `report.cycles / wall_seconds`
- pair effect: backend 順に関係なく `r_i = ln(candidate_throughput / baseline_throughput)`
- workload の主効果: `exp(mean(r_i)) - 1` で表す geometric mean speedup
- 95% CI: 分母 `n-1` の `sample_sd` を使い、`mean(r) ± 2.262157 * sample_sd(r) / sqrt(10)` を log 空間で計算し、`exp(x)-1` へ戻す
- 記述統計: pair ごとの percent effect の median と IQR。10 値を昇順にし、下位5値/上位5値の各 median を Q1/Q3 とする
- combined effect: 同じ pair index の二 workload の `r_i` を等重みで平均した 10 値に、同じ t 区間を適用する
- 補助指標: wall time、guest instructions/second、host counter
- 10 pair 終了後に run を恣意的に除外または追加しない。個別 run の再試行もしない。
- OS update、thermal throttling、別プロセス負荷など事前定義した異常だけを batch 全体の無効理由にする。

calibration は synthetic command ではなく、共通 baseline の PicoTetris scenario を使う。既存記録は v1（pre×3、run 10/20/30直後×1、post×3）と v2（5境界×3、15 anchor）として固定保存する。現行 null-control は v3を使い、warm-up 後の pre、測定途中の run 5/10/15/20/25/30/35直後、測定後の post の9境界を各3回（計27 anchor）測定する。各境界で `median(log(throughput))` を集約値とし、elapsed も中央値とする。さらに `MAD = median(abs(log_i - median_log))`、`scaled_MAD = 1.4826 × MAD`、`relative_MAD = exp(scaled_MAD)-1` を保存し、各境界の relative MAD が2%以下であることを固定 gate とする。v3 は集約9点の log-throughput を隣接区間ごとに piecewise 線形補間し、global line は診断値として保存する。v3の local leave-one-group-out residual 最大値、pair raw-vs-corrected sensitivity、replicate欠落・重複、identity/provenance/correctness不一致、MAD超過、host snapshot/affinity不成立は batch 全体を invalid とする。calibration run は候補効果へ含めない。無効 batch に run を継ぎ足さず、新 batch ID で warm-up から全体を取り直す。

専用 runner の固定 CLI は次とする。`--target` と `--firmware` は同じ順で二回指定する。候補 feature を評価するときは、実際の feature 名ごとに `--feature-set <candidate-feature>` を追加する。P0-A2 null-control だけは `--candidate-id P0-A2 --final-report-only` を必須とし、同一の production runner path を baseline/candidate の両方へ渡す。

```bash
python3 tools/benchmark_rp2040_cpu_candidate.py ab \
  --baseline-backend "$RP2040_CPU_OPT_TMP/backend-baseline" \
  --candidate-backend "$RP2040_CPU_OPT_TMP/backend-candidate" \
  --baseline-runner "$RP2040_CPU_OPT_TMP/build/baseline-production/release/picocalc-run" \
  --candidate-runner "$RP2040_CPU_OPT_TMP/build/candidate-production/release/picocalc-run" \
  --feature-set <candidate-feature-list> \
  --target picotetris-opt1b-vrp5 --firmware /absolute/path/PicoTetris.bin \
  --target picoedit-r1-vrp2f --firmware /absolute/path/picocalc_app.bin \
  --pairs 10 --warmup 1 --calibration-runs 3 --calibration-method interleaved-anchor-v2 --cpu <logical-cpu> \
  --inter-run-cooldown-seconds 60 \
  --admission-record firmware-validation/records/rp2040-cpu-p0-baseline-YYYYMMDD-NN \
  --batch-id rp2040-cpu-<candidate>-YYYYMMDD-NN \
  --output firmware-validation/records/rp2040-cpu-<candidate>-YYYYMMDD-NN
```

P0-A2 の null-control では `<candidate-feature-list>` を省略し、上の例へ次の二つを追加する。

```bash
--candidate-id P0-A2 --final-report-only
```

このモードは correctness を final-report projection までに限定するため、behavior-trace runner を指定せず、同じ production executable の sidecar role=`production` を A/B 両方で使用する。

runner は clean Git commit、明示された release executable、firmware/scenario/contract SHA、backend embedded commit、feature set、CPU affinity を開始前に検証する。不一致時は measured run を一つも開始しない。`--firmware` は registry の `artifacts.bin_sha256` と一致する任意の絶対 path を受け付ける。

target/scenario/bootrom/board/cycles 等の raw runner argument は既存 `tools.picocalc` の target-command builder から展開するが、builder が registry の accepted commit から作る `--backend-commit` は使用しない。各 run について対象 backend worktree の clean `git rev-parse HEAD` へ `--backend-commit` を置換し、その値が runner の embedded commit と一致することを subprocess 起動前に検証する。baseline/candidate それぞれ別の commit を渡す。この override がない PicoEdit/common-baseline command は unit test で拒否する。

### 5.5 正確性ゲート

性能測定とは別に、同じ firmware/scenario/target contract を production release の baseline/candidate で各 1 回実行する。schema-8 report から、top-level の `backend_build` と `backend_commit`、および harness が CLI の期待値を反映する `audio_sink.expected_count` / `audio_sink.expected_sha256` だけを削除し、Python の `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` を UTF-8 encode したものを `guest_observation_projection` と定義する。`audio_sink` の実測値（DMA write count、PCM SHA-256、status、タイミング）は保持する。その baseline/candidate SHA-256 と canonical JSON を完全一致させる。

この projection は stop reason、総 emulated cycle、virtual elapsed time、execution model、final PC、final exception/fault、UART、framebuffer、audio、PSRAM、SD、keyboard、PIO/PWM、scenario timeline、unsupported MMIO/access、firmware/bootrom/flash identity を保持する。これは final report の guest-visible surface の一致であり、命令単位 trace の一致を主張しない。

P1 以降の CPU候補では、これに加えて baseline/candidate を `--features behavior-trace` で build し、同じ scenario を `--behavior-trace` 付きで各 1 回実行する。既存 behavior artifact の `behavior_projection`、`behavior_sha256`、domain ごとの event count/SHA-256 を完全一致させる。この diagnostic build の wall time は採否性能に使用しない。P0-0 admission と P0-A2 null batch は production final report の projection までを必須とし、P0-B/P1/P2 の correctness gate から behavior trace を必須にする。

firmware、scenario、target contract は baseline/candidate で同一でなければならない。一方、backend commit と runner executable SHA-256 は候補の識別情報なので一致を要求せず、両方を manifest に保存する。Serial target で core 1 が動作しない場合は、存在しない per-core counter を捏造せず、profile では `active=false`/zero とする。

専用 runner の correctness CLI は次とする。

```bash
python3 tools/benchmark_rp2040_cpu_candidate.py correctness \
  --baseline-backend "$RP2040_CPU_OPT_TMP/backend-baseline" \
  --candidate-backend "$RP2040_CPU_OPT_TMP/backend-candidate" \
  --baseline-runner "$RP2040_CPU_OPT_TMP/build/baseline-production/release/picocalc-run" \
  --candidate-runner "$RP2040_CPU_OPT_TMP/build/candidate-production/release/picocalc-run" \
  --baseline-trace-runner "$RP2040_CPU_OPT_TMP/build/baseline-trace/release/picocalc-run" \
  --candidate-trace-runner "$RP2040_CPU_OPT_TMP/build/candidate-trace/release/picocalc-run" \
  --feature-set <candidate-feature-list> \
  --target picotetris-opt1b-vrp5 --firmware /absolute/path/PicoTetris.bin \
  --target picoedit-r1-vrp2f --firmware /absolute/path/picocalc_app.bin \
  --admission-record firmware-validation/records/rp2040-cpu-p0-baseline-YYYYMMDD-NN \
  --output firmware-validation/records/rp2040-cpu-<candidate>-YYYYMMDD-NN/correctness
```

上は P1 以降の完全形である。P0-A2 null batch は trace runner 二引数を省略し、`--final-report-only` を明示する。P1 以降で trace runner が一方でも未指定なら `correctness` は run 前に拒否する。

ここで指定する `--feature-set` は production candidate の追加 feature だけであり、trace runner には runner が自動的に `behavior-trace`（および同じ candidate feature）を要求する。baseline production の実効集合は `sd-gen1-multiblock`、baseline trace はそこへ `behavior-trace` を加えた集合である。

さらに各 report は registry の `report_checks` と timeline SHA を評価する。ただし admission/candidate 比較では `backend_build.commit` の check だけを manifest identity check に置換し、`backend_build.dirty == false` は必須のまま維持する。backend identity を含む full-report `normalized_report_sha256` は candidate との同一条件にせず、baseline/candidate の projection digest を正確性条件にする。新 runner は legacy validator を無変更で呼ばず、この置換規則を専用関数として unit test する。一項目でも不一致なら performance run を開始せず、その候補を不採用にする。

### 5.6 P0-0 common-baseline admission

P0-A1 の runner unit test が通り、baseline production runner とその build provenance sidecar を作成した直後、performance baseline を取る前に次を行う。

```bash
python3 tools/benchmark_rp2040_cpu_candidate.py admit \
  --backend "$RP2040_CPU_OPT_TMP/backend-baseline" \
  --runner "$RP2040_CPU_OPT_TMP/build/baseline-production/release/picocalc-run" \
  --target picotetris-opt1b-vrp5 --firmware /absolute/path/PicoTetris.bin \
  --target picoedit-r1-vrp2f --firmware /absolute/path/picocalc_app.bin \
  --output firmware-validation/records/rp2040-cpu-p0-baseline-YYYYMMDD-NN/admission
```

`admit` は target registry の accepted backend を candidate に強制せず、legacy `validate_report()` の full-report hash check もそのまま呼ばない。raw command の `--backend-commit` は `--backend` の clean HEAD へ置換する。固定 firmware/scenario/contract、clean embedded commit、`report_checks`（commit check のみ置換）、timeline SHA、登録 report と current report の guest projection digest、determinism 2 run を検査する。両 workload が合格した一つの commit と runner SHA を `manifest.json` に common baseline として凍結する。片方でも不合格なら P0 baseline、P1、P2 を開始しない。P0-0 は runner 実装ではなく、P0-A1 の後に一度だけ通す workload gate である。

2026-08-30 の実施結果は pass である。`73784b96a1afdb34dc1a79577f947b670a138d07` の clean backend と、runner SHA-256 `921c923df12d88e0fa8edda470ffff252f62d3047f1836c3080ada824fae25c7`（build-provenance SHA-256 `d32ebab9a7b7f125f7a5087f21feff5aff5ab1817da0a5cd8cc978182aaea7af`）を使用した。PicoTetris r10 は cycles `927528659`、PicoEdit r4 は cycles `827799818` で、各2回の guest observation projection が登録 report と一致し、各 workload 内の2回も一致した。検証済み record は `firmware-validation/records/rp2040-cpu-p0-baseline-20260830-03/`、`verify_environment.py --scope target-schema` は 37 checks pass、record の `SHA256SUMS` は全件 pass である。従って common baseline gate は閉じ、P0-A2 null batch を開始できる。

`correctness` と `ab` は `--admission-record` でこの P0-0 record root を必須入力とし、manifest/decision/checksum/evidence の pass と現行 baseline identity を measured run 前に再検証する。P0-A2 のみ、同一 runner binaryを A/B 両方へ渡すため sidecar `provenance_role=production` への移行を許すが、backend commit/dirty、runner SHA、実効 feature set は必ず一致させる。`profile` も同じ admission record の manifest/decision/checksum/evidence と固定 workload を再検証するが、profile CLI は baseline executable を受け取らないため、別途比較する current baseline identity は持たず、candidate profile runner 自身の sidecar identity を検査する。admission record がない、別 workload、別 baseline、receipt identity の不一致、または partial checksum の場合は subprocess を一つも起動しない。
P2-A の production `ab` だけは `--profile-record` で feature-on diagnostic profile record を追加指定する。runner は profile record の checksum、P2-A candidate ID、二 workload、candidate backend commit、`cpu-application-profiler,pending-exception-fast-reject` feature、aggregate/core counter conservation、passing profile decision を measured run 前に再検証する。profile record がない・不一致なら P2-A A/B subprocess を一つも起動しない。

## 6. 実装フェーズ

依存順に進める。各フェーズは「profile → 実装 → correctness → performance A/B → 判断 → 記録」で閉じ、複数の未測定変更を一度に重ねない。

### P0. 再現可能な実アプリ計測基盤

#### P0-A1: target admission、correctness、A/B runner の実装

新規ファイルを次で固定する。

- `picocalc_emu/tools/benchmark_rp2040_cpu_candidate.py`
- `picocalc_emu/tests/test_benchmark_rp2040_cpu_candidate.py`
- `picocalc_emu/firmware-validation/rp2040-cpu-build-provenance.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-profile.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-profile-comparison.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-ab.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-decision.schema.json`

既存 `benchmark_firmware_realtime.py` は登録 backend 一つの realtime 指標を扱い、理論値や runner startup/output を含む別契約であるため変更しない。新 runner は `provenance`、`admit`、`correctness`、`profile`、`ab`、`summarize` subcommand を持ち、§5 の CLI と統計を実装する。`schema_id`、全 identity、実行順、全 raw run、invalid batch 理由を schema で検証する。

Python unit test は最低限次を固定入力で検査する。

- 10 pair が 5 AB + 5 BA、20 run/workload になる。
- workload 順も交互になり、run ID が一意になる。
- `--target` と `--firmware` の個数不一致、順序不一致、片方だけの指定を subprocess 起動前に拒否する。
- backend 順に依存せず log ratio が candidate/baseline になる。
- geometric mean、sample SD、df=9 の t CI、median、IQR が既知値と一致する。
- firmware/scenario/contract/embedded commit/runner SHA/build-provenance sidecar/実効 feature set の不一致を measured run 前に拒否する。
- sidecar が binary SHA、backend commit/dirty、role、Cargo実効 feature、lockfile/tree SHA、Cargo argv、toolchain を結び付けない場合を拒否する。
- target builder の登録 commit を各 backend の clean HEAD へ置換し、PicoEdit/common-baseline と baseline/candidate の双方で正しい `--backend-commit` を生成する。
- guest projection が `backend_build`/`backend_commit` 以外の一ビット差を拒否する。
- admission では legacy normalized report SHA を使わず、登録/current guest projection、timeline、commit以外の report check を検査する。
- admission gate は二つの receipt の workload/SHA/identity/provenance と decision evidence を再検証し、partial checksum や receipt 改変では subprocess を起動しない。
- P1以降の correctness では behavior SHA、domain event count/SHA の差を拒否する。
- 同じ batch manifest を持つ record root は subcommand 間で再利用できるが、既存 leaf artifact の上書き、record ID/identity 不一致は拒否する。
- 各 runner は build-provenance sidecar（binary SHA と Cargo 実効 feature 集合を含む）がなければ拒否する。
- v2 calibration protocol の境界別 relative MAD または集約 anchor residual が 2% 超、replicate 欠落、または host stability/provenance/correctness の事前定義違反なら batch 全体を invalid にする（pre/post の全体差だけでは直ちに invalid としない）。
- A/B の cooldown は 60 秒の固定値で、adaptive な変更を拒否し、manifest/summary/decision の `measurement_policy` に同じ値を保存する。
- affinity 設定後の実効 CPU 集合が要求値と異なる場合、measured subprocess を開始せず fail-closed にする。

P0-A1 テストコマンド:

```bash
cd /home/fuyuki/pico_dvl/codex/picocalc_emu
python3 -m unittest tests.test_benchmark_rp2040_cpu_candidate
python3 tools/verify_environment.py --scope target-schema
```

`verify_environment.py` には五つの新 schema と、存在する `rp2040-cpu-*` record の必須ファイル validation を追加する。record がまだ 0 件であることは正常とし、P0-A1 の schema fixture test を失敗させない。

P0-A1 完了条件:

1. unit test と environment verification が通る。
2. target command builder が registry から mandatory raw runner argument を展開する unit test が通る。
3. schema fixture、legacy normalized-report置換、projection digest、実行順、統計の unit test が通る。
4. この時点では実 workload を走らせず、次に P0-0 admission を実行する。

#### P0-A2: admitted baseline の null batch

P0-0 合格後、common baseline executable を A と B の両方に指定し、§5.4 の warm-up、calibration、40 measured run をすべて実行する。順序、schema、guest digest が正しく記録されることを確認し、効果を「改善」と解釈せず測定ノイズの基準値として保存する。最後に次を実行する。

```bash
python3 tools/verify_environment.py --scope target-schema
```

2026-08-30 の最初の実行 `rp2040-cpu-p0-null-20260830-02` は、40 measured run と production final-report correctness を完了した。しかし PicoTetris baseline calibration は pre values `[5253901.337729141, 5083548.419297449, 5034495.0317524355]`、post values `[4337170.51868368, 4168671.39552155, 4373826.086797396]`、pre median `5083548.419297449`、post median `4337170.51868368`、relative drift `0.1468222271239661`（14.68%、許容2%）となったため、効果の統計は採用せず `decision.status=invalid` とした。invalid record は `firmware-validation/records/rp2040-cpu-p0-null-20260830-02/` に保存し、40 run、correctness leaf、manifest、decision、`SHA256SUMS` を保持する。この drift は guest projection mismatch や backend identity 不一致ではない。

この batch の検証で、runner が書く audio sink harness expectation を含まない guest projection と environment verifier の実装差も判明した。`tools/verify_environment.py` を runner と同じ projection（`backend_build`、`backend_commit`、`audio_sink.expected_count`、`audio_sink.expected_sha256` を除外し、実測 audio fields は保持）へ修正し、projection 固定テストを追加した。修正後は invalid record の `SHA256SUMS` と target-schema 37 checks が pass した。これは invalid 判定を pass に変えるものではなく、失敗記録を正しく検証可能にする修正である。

同じ batch ID へ追記・再試行はしない。最初の drift を受けて追加した固定 60 秒 cooldown、CPU affinity の実効集合確認、開始・完了時 host snapshot を含めても、二回目の batch は次の値となった。

| batch | pre calibration | post calibration | relative drift | measured runs | correctness/checksum/schema |
|---|---:|---:|---:|---:|---|
| `rp2040-cpu-p0-null-20260830-02` | 5,083,548.419 | 4,337,170.519 | 14.682% | 40 | pass / pass / pass |
| `rp2040-cpu-p0-null-20260831-01` | 4,822,866.850 | 4,999,788.443 | 3.668% | 40 | pass / pass / pass |

二回目の全40 runについては、同一 executable の null A/B ペア差分中央値が PicoTetris `+0.057%`、PicoEdit `+0.792%`、combined `+0.393%` だった。この値は候補改善の証拠には使わないが、今回の無効理由が backend identity や guest correctness ではなく、約3時間の host throughput 変動であることを示す補助資料として保存する。2% の calibration 閾値は緩和しない。三回目以降の A/B に備え、単発 anchor 外れ値を切り分ける v2（5境界×3 replicate、median/MAD、同じ2% gate）を runner/schema/verifier/test へ実装した。既存 batch は再利用せず、新しい batch ID で warm-up から取り直す。

v1 の invalid 記録を再解釈せず、次の v2 calibration protocol を固定仕様として実装する。結果を見て閾値を動かしたものではない。

1. 本測定の 40 run、5 AB + 5 BA、60 秒 cooldown、同一 workload 順を維持する。
2. PicoTetris baseline の calibration anchor を、pre、測定途中の固定境界（run 10、20、30 の直後）、post の5境界へ配置し、各境界を3回測定する（計15 anchor）。anchor の workload、backend、runner、CPU、cooldown は本測定と同一にする。各 replicate は個別 JSON として保存し、ID・順序・境界を固定する。
3. 各境界の `median(log(throughput))` を集約値とし、elapsed も中央値とする。`MAD`、`scaled_MAD=1.4826×MAD`、`relative_MAD=exp(scaled_MAD)-1` を保存し、全境界の relative MAD が2%以下であることを要求する。集約5点の log throughput を経過時間へ線形補間し、各 measured run の host-speed 補正値を記録する。候補効果の主統計は従来どおり同一 pair の candidate/baseline log ratio とし、補正は host drift の診断・感度分析に限定する。
4. 集約 anchor の線形モデル最大残差が2%を超える、いずれかの境界の relative MADが2%を超える、replicate欠落・重複、または host snapshot/affinity/provenance/correctness が不成立なら batch を invalid にする。全体の pre/post 差だけでは直ちに invalid にせず、モデル residual、境界別 MAD、pair-level null-control を decision に明記する。
5. `measurement_policy` に `calibration_method=interleaved-anchor-v2`、5境界の group ID、15 anchor run ID、中央値/MADの集約方法、二つの2%閾値、補正方法、pair-level sensitivity の方式を保存し、実測の raw replicate、`anchor_groups`、residual、補正値、pair-level sensitivity は `summary.calibration` に保存する。schema/verifier/unit test で個数・順序・中央値/MAD・閾値を再計算して固定する。既存の v1 invalid record は変更しない。

P0-A2 の null-control 採否も結果を見る前に固定する。同一 executable の raw pair log ratio を主指標とし、各 workload は geometric mean effect の絶対値 2% 以下かつ 95% CI が 0 を含むこと、二 workload の等重み combined は絶対値 1% 以下かつ 95% CI が 0 を含むことを要求する。anchor 補正後の同じ二組は host-drift sensitivity として同じ閾値で併記する。いずれかの workload、combined、raw、corrected の条件を満たさない場合は `summary.status=invalid` とし、P1-A の production A/B を開始しない。全条件を満たした場合だけ `summary.status=pass`、`decision_kind=null-control`、`decision.status=pass` として P0-A2 を閉じる。CPU 11 の `rp2040-cpu-p0-null-20260831-05` は固定 v1 anchor gateでinvalidとなったため、v3 protocolを実装後に新 batch IDで実行する。

この protocol v2 により、長時間の周波数変動を「無かったこと」にせず、境界内 replicate の中央値/MADで単発外れ値を切り分け、変動を観測・補正したうえで、隣接 pair の実アプリ差分が再現するかを判定できる。`rp2040-cpu-p0-null-20260831-04` は correctness、40 run、checksum、target-schema を完了した。raw/host-corrected の workload別・combined null-effect と CI はすべて固定閾値内だったが、anchor-after-020 の残差 4.3027% を含む anchor 最大残差が固定 2% gate を超えたため `summary.status=invalid`、`decision.status=invalid` とした。この batch は null-effect計算の成功証拠として保持し、P1-A/P2-A の production A/B には使用しない。CPU 11 の `rp2040-cpu-p0-null-20260831-05` も correctness、40 run、checksum、target-schema、raw/host-corrected null-effect と CI はすべて通過したが、`pre_post_relative_drift=1.5724%` の一方で `anchor-post-003` の局所外れにより最大 residual 4.5046%となり、固定2% gateで `summary.status=invalid`、`decision.status=invalid` とした。batch 04/05 はいずれも「null効果の統計」ではなく「単発 anchor による校正モデル不成立」で invalid であり、同じ batch IDへ追記しない。v2 runner/schema/verifier/unit test をコミット後、新 batch IDで warm-upから再測定する。target-schema verifier は calibration gate invalid を正しく受け入れるよう修正済みである。

`rp2040-cpu-p0-null-v2-20260831-02` はこの v2 実装の初回 batch として 2026-09-01 に完了した。40 run、15 anchor、checksum、correctness、target-schema、anchor group dispersion（全 group 0.628〜1.818%）、null-control の raw/host-corrected effect/CI は pass したが、global log-linear model の最大 residual 5.1743%、RMS 3.1993%が固定2% gateを超えたため invalid である。5 group median の非線形変動を原因とし、global residualを緩和・再解釈しない。v2 の宣言（piecewise interpolation）と実装（global model gate）の契約差を是正するため、次の `interleaved-anchor-v3` を別 batch IDで実装・schema/verifier/test検証後に実行する。v3 は同じ40 measured run、60秒 cooldown、CPU11、同一 workload/identityを維持し、`pre, after-005, after-010, after-015, after-020, after-025, after-030, after-035, post` の9境界を各3回（計27 anchor）測定する。各 group median を時系列順の piecewise log-linear correction knot とし、global line は診断値だけにする。採否 gate は (a) 全group relative MAD ≤2%、(b) replicate数・順序・guest projection/backend/runner/CPU/affinity/correctness identity一致、(c) 9 group の deterministic leave-one-group-out log-linear local residual 最大値 ≤2%、(d) 隣接 pair の raw-vs-host-corrected log-ratio差の最大絶対値 ≤2%、(e) 既存の workload別2%・combined1% null effect/CIで固定する。local residualは結果を見て選択せず、内部groupは直前・直後の残存knotを対数線形補間し、両端は最初/最後の二knotを対数線形外挿して算出する。いずれかの gate不成立、欠落、重複、非有限knotなら batch 全体を invalid とし、同じbatchへ追記しない。v3 の runner/schema/verifier/unit test は 212 tests と target-schema 37/37 を通過し、CPU11 correctness record `rp2040-cpu-p0-null-v3-20260901-01` も完了した。次に real null-control を実行する。

P0-A 全体の性能 gate は `P0-A1 pass → P0-0 pass → P0-A2 null batch pass` の三条件のまま維持する。一方、P0-B の profile は emulated instruction/cycle/PC region counter を収集する計測実装であり、wall-time の採否を行わない。P0-B の実装、compile-out、profile、correctness は完了済みで、結果はホットスポット仮説の形成と P1/P2 の実装開始判定に使うが、候補実装の production promotion、P1/P2 の A/B 採否、または「高速化した」という結論には使わない。これらは有効な null-control protocol と correctness/A-B 記録が揃うまで保留する。

#### P0-B: 最小 CPU application profiler

backend の実装位置と公開名を次で固定する。

| 内容 | ファイル/API |
|---|---|
| feature | `crates/rp2040-emu/Cargo.toml`: `cpu-application-profiler = []` |
| harness forwarding | `crates/picocalc-harness/Cargo.toml`: `cpu-application-profiler = ["rp2040-emu/cpu-application-profiler"]` |
| profile state/JSON model | 新規 `crates/rp2040-emu/src/cpu_application_profile.rs` |
| module/API/reset/snapshot | `crates/rp2040-emu/src/lib.rs` |
| retire/decode/region | `crates/rp2040-emu/src/core/decode.rs`、`src/core/mod.rs` |
| invalidation outcome | `crates/rp2040-emu/src/core/mod.rs::invalidate_decode_cache_entries` |
| exception outcome | `crates/rp2040-emu/src/core/mod.rs::step/try_take_any_pending_exception` |
| CLI/output | `crates/picocalc-harness/src/main.rs`: `--cpu-application-profile <path>` |
| build provenance | build wrapper: `<runner>.build.json` sidecar（Cargo実効 feature graph、lockfile、argv、toolchain、binary SHA）を生成 |
| schema | `picocalc_emu/firmware-validation/rp2040-cpu-profile.schema.json` |

既存 `running_profile.rs` の型や pure helper は共有してよいが、`event-horizon-profiler`/`behavior-trace` feature は連鎖させない。既存 event-horizon JSON の schema/意味も変更しない。CPU application profile は別 JSON として出力する。CLI、state、record call はすべて `cfg(feature = "cpu-application-profiler")` で compile out する。

profile subcommand は registry から `--bin`、bootrom、board、LCD、cycles、quantum、scenario、snapshot/report path を展開し、最後に `--cpu-application-profile` を加える。未展開 placeholder は raw runner へ渡さない。

profile 実行例:

```bash
python3 tools/benchmark_rp2040_cpu_candidate.py profile \
  --backend "$RP2040_CPU_OPT_TMP/backend-candidate" \
  --runner "$RP2040_CPU_OPT_TMP/build/candidate-profile/release/picocalc-run" \
  --feature-set cpu-application-profiler \
  --target picotetris-opt1b-vrp5 --firmware /absolute/path/PicoTetris.bin \
  --target picoedit-r1-vrp2f --firmware /absolute/path/picocalc_app.bin \
  --admission-record firmware-validation/records/rp2040-cpu-p0-baseline-YYYYMMDD-NN \
  --output firmware-validation/records/rp2040-cpu-p0-profile-YYYYMMDD-NN/profile
```

P0-B テストコマンド:

```bash
cd "$RP2040_CPU_OPT_TMP/backend-candidate"
cargo test --locked -p rp2040-emu --features cpu-application-profiler
cargo test --locked -p picocalc-harness --features cpu-application-profiler
CARGO_TARGET_DIR="$RP2040_CPU_OPT_TMP/build/candidate-profile" \
  cargo build --locked --release -p picocalc-harness --bin picocalc-run \
  --features cpu-application-profiler
CARGO_TARGET_DIR="$RP2040_CPU_OPT_TMP/build/candidate-production" \
  cargo build --locked --release -p picocalc-harness --bin picocalc-run
```

P0-B 完了条件:

1. 二 workload で §5.3 の全不変条件が成立する。
2. reset 後の zero、inactive core、overflow invalidation を unit test する。
3. profiler OFF build の `CortexM0Plus::step`、inline 化された `decode_execute`、invalidation drain path に counter store/profile branch がないことを `compile-out-evidence.md` の `nm`/`objdump` 証跡で確認する。
4. profiler OFF の baseline/candidate correctness と behavior-trace が一致する。
5. profile から P1-A の `unrelated_would_clear / examined_slots` と P2-A の no-candidate poll 比率を算出できる。

2026-08-31 に P0-B を実施した。backend commit `c123933423477b878a1dde8b1f80fb3d731bc8e3` の
`cpu-application-profiler` buildで、PicoTetris r10（retired `172,705,412`、decode miss
`297,901`）と PicoEdit r4（retired `87,776,861`、decode miss `223,209`）を測定した。
両 workload とも `overflowed=false`、`profile_valid=true`、全8 invariant が成立し、core 1 は
inactive/zero だった。profile record は
`firmware-validation/records/rp2040-cpu-p0-profile-20260831-01/` に保存し、profile 2件と
測定 leaf、compile-out evidence、manifest、decision、`SHA256SUMS` を固定した。

同じ commit の profiler-OFF production buildについては、PicoTetris/PicoEdit の final report
projection と behavior-trace（各 domain count/SHA-256）を baseline commit `73784b96...` と比較し、
両方の correctness gate を pass した record を
`firmware-validation/records/rp2040-cpu-p0-b-correctness-20260831-02/` に保存した。OFF binary の
`step`、`try_take_any_pending_exception`、`populate_decode_cache` を `nm`/`objdump` で確認し、
profiler symbol/string が存在しないことを
`rp2040-cpu-p0-profile-20260831-01/compile-out-evidence.md` に記録した。これは compile-out と
正確性の証明であり、速度向上の主張ではない。profile の `raw_profile.valid_for_wall_time=false`
も維持する。

profile から得た次候補の開始値は次の通りである。

| workload | `unrelated_would_clear / examined_slots` | `unrelated_would_clear / requests` | `reject_no_candidate / polls` |
|---|---:|---:|---:|
| PicoTetris r10 | 0.058399% | 0.116799% | 99.989207% |
| PicoEdit r4 | 4.194210% | 8.388420% | 99.943097% |

従って P1-A（`unrelated_would_clear > 0`）と P2-A（no-candidate reject率 90%以上）は実装開始可能である。P2-A の feature-on diagnostic profile と保存 counter 式の検証は `rp2040-cpu-p2-a-profile-20260831-01` で完了した。P2-A の production A/B は、有効な P0-A2 null-control を取得するまで開始しない。
P1-B の filter は「未実行 SRAM page への write による invalidation request」を省略する候補であり、
`unrelated_would_clear` は full-tag guard の無関係 slot 指標なので P1-B の filter可能 request とは別物である。
現行 P0-B profile は write 先 page の executable 判定を記録していないため、P1-B の gate はまだ判定不能とする。
P1-B を開始する前に、production hot path を汚さない profile-only 拡張で
`non_executable_sram_write_requests` と `invalidation_requests` を workload別に採取し、
`filterable_request_rate = non_executable_sram_write_requests / invalidation_requests` を定義する。
二 workload の各 ratio が欠落せず、等重み combined ratio が 1%以上、かつ各 workload の correctness
projection が pass した場合だけ開始する。分母がゼロ、counter 欠落、または片方の workload が未測定なら
fail-closed で P1-B を開始しない。`unrelated_would_clear / requests` や `/ examined_slots` を代用しない。

### P1. SRAM decode invalidation の不要処理除去

現状は SRAM write ごとに decode invalidation address を queue し、direct-mapped slot を index で消す。full tag を確認しない slot clear は、同じ index の無関係な XIP entry まで失効させ得る。

#### P1-A: full-tag invalidation guard

- candidate ID/feature は `P1-A` / `decode-invalidation-tag-guard` とし、default off で実験する。
- 変更先は `crates/rp2040-emu/src/core/mod.rs::invalidate_decode_cache_entries`、feature 宣言は backend と `picocalc-harness` の両 `Cargo.toml` とする。
- `aligned = addr & !1` の slot は、`entry.matches_invalidation_pc(aligned, slot)` のときだけ clear する。通常の decode lookup は従来どおり full virtual `matches_pc` のままとし、invalidation 判定だけ SRAM alias（0x20..0x23）の backing tag を canonicalize する。
- `prev = aligned - 2` の slot は、`entry.matches_invalidation_pc(prev, slot) && entry.is_wide()` のときだけ clear する。narrow predecessor は残す。
- 4-byte write は現行 queue producer が渡す `{addr, addr+2}` をそのまま使い、重複 clear は許すが無関係 tag は消さない。
- `Emulator::drain_cache_invalidations` の active-core 配送、queue producer、guest cycle、cache geometry は変更しない。core 0 と core 1 は各々が active の場合に同じ判定を行うことを試験する。
- cross-core write が peer core の既存 entry を失効させるかという現行意味論は、P1-A の速度変更へ混ぜず、別 correctness issue として扱う。

測定するもの:

- invalidation request 数
- tag match clear 数
- 従来なら消していた unrelated slot 数
- invalidation 後の decode miss 減少
- 実アプリ全体の cycles/second

追加 unit test:

- 同じ direct-map index を持つ unrelated XIP entry が SRAM data write 後も残る。
- tag が一致する SRAM narrow entry は消える。
- 0x21 alias から fetch した SRAM entry を 0x20 alias write で正しく消す。
- wide instruction の後半 halfword write は `addr-2` の wide entry を消す。
- `addr-2` の narrow entry は消さない。
- 4-byte write の `{addr-2,addr,addr+2}` overlap を正しく処理する。
- 同じ test vector を active core 0/core 1 の双方で通す。

テストコマンド:

```bash
cargo test --locked -p rp2040-emu decode_cache
cargo test --locked -p rp2040-emu --features decode-invalidation-tag-guard decode_cache
cargo test --locked -p picocalc-harness --features decode-invalidation-tag-guard
cargo test --locked --release -p rp2040-emu -p picocalc-board -p picocalc-harness
```

P1-A の実装、profile、correctness は 2026-08-31 に完了した。runtime の候補は
`2a9e8cf`、SRAM alias を含むタグ判定の修正は `61f8bde`、harness の provenance feature
列挙修正は `6f8ce41` である。default-off のため既存 path は変更せず、feature-on unit test は
core 0/1 の同一ベクトル、XIP の同一 index 無関係 entry、narrow/wide predecessor、4-byte
overlap、0x20/0x21 SRAM alias を通過した。profile/correctness の小容量証拠はそれぞれ
`firmware-validation/records/rp2040-cpu-p1-a-profile-20260831-02/` と
`firmware-validation/records/rp2040-cpu-p1-a-correctness-20260831-02/` に保存している。
correctness record の candidate identity は `61f8bde`、profile record は provenance 修正後の
`6f8ce41` であるが、後者は `build.rs` の feature 列挙のみを変更し、CPU runtime semantics は
同一である。両 workload の guest projection と behavior trace は correctness `pass` である。

診断 profile の baseline→candidate は次のとおりで、wall-time の採否証拠ではない。

| workload | decode miss | `unrelated_would_clear / examined_slots` | retired/cycles |
|---|---:|---:|---:|
| PicoTetris r10 | 297,901 → 288,704（−3.087%） | 75.958% | 同一 |
| PicoEdit r4 | 223,209 → 66,316（−70.290%） | 86.560% | 同一 |
| combined | 521,110 → 355,020（−31.872%） | 77.912% | — |

`unrelated_would_clear` は候補 guard があれば historical index-only path で消えていた非空 slot の
診断値であり、同じ request が複数 slot を調べるため高くなり得る。P1-B の
`filterable_request_rate` の分母へ流用しない。P1-A は profile signal と correctness を完了したが、
production A/B はまだ採否していない。v2 `interleaved-anchor-v2` null-control が有効になった後、
同じ二 workload・10 pair（5 AB + 5 BA）で実測し、中央値と combined CI により判断する。

#### P1-B: executable SRAM page の sticky bitmap

- candidate ID/feature は `P1-B` / `executable-sram-invalidation-filter` とし、`rp2040-emu/Cargo.toml` に空 feature、`picocalc-harness/Cargo.toml` に backend forwarding feature を追加する。
- SRAM page が実際に instruction fetch された時点で executable bit を立てる。
- page size は 256 byte、index は SRAM alias を canonicalize した `(addr & 0x00ff_ffff) >> 8` とする。264 KiB に対する 1056 bit の shared sticky bitmap を `Bus` が所有する。
- 一度立った bit は reset または full image replacement まで下げない。`Emulator::reset` と SRAM image replacement は bitmap clear + 従来の region invalidation、通常の bulk poke は false negative を避けるため bitmap を維持して従来の bulk invalidationを行う。
- 一度も実行されていない SRAM page への data write は decode invalidation queue を省略する。
- core 0/core 1 の fetch は同じ bitmap へ mark し、false negative を作らない。
- loader、bulk poke、reset、image replacement は従来どおり full invalidation する。
- 実装位置は `bus/mod.rs` の Bus field/`invalidate_pc_range`、`core/decode.rs` の fetch mark、`lib.rs` の reset/load path とする。

feature 有効 test:

```bash
cargo test --locked -p rp2040-emu --features executable-sram-invalidation-filter decode_cache
cargo test --locked -p rp2040-emu --test multicore --features executable-sram-invalidation-filter
cargo test --locked -p picocalc-harness --features executable-sram-invalidation-filter
```

測定するもの:

- page bit により省略した invalidation 数
- executable page への write 数
- queue 長と drain cost
- decode hit/miss の変化
- 実アプリ全体の cycles/second

#### 完了条件

- self-modifying SRAM code、wide instruction 上書き、両 core からの実行を含む単体試験が一致する。
- 二つの実アプリで correctness gate を通る。
- P1-A、P1-B、A+B の三つを別々に A/B 測定する。P1-B は P1-A 採否記録が閉じ、profile-only 拡張で定義した workload別 `filterable_request_rate` と等重み combined ratio が gate を満たす場合だけ開始する。
- feature-gated 実験後、採用候補は feature を production default に残さず通常 path へ統合し、その統合後 binary を再度 correctness/A-B 測定する。

### P2. pending exception の common-case fast reject

現状の `CortexM0Plus::step` は、各命令の前に `try_take_any_pending_exception` を呼ぶ。通常命令の大半で exception が取られないなら、毎回の完全探索を避けられる。

#### P2-A: 既存状態を読む inline reject

- candidate ID/feature は `P2-A` / `pending-exception-fast-reject` とし、`rp2040-emu/Cargo.toml` に空 feature、`picocalc-harness/Cargo.toml` に backend forwarding feature を追加する。
- `core/mod.rs::try_take_any_pending_exception` の先頭を `#[inline(always)]` の reject 部と `#[cold] #[inline(never)]` の arbitration 部へ分ける。
- reject 部は順に PRIMASK、`ICSR.PENDSVSET|PENDSTSET`、`NVIC.pending_and_enabled()` を読む。三 source がすべて空なら直ちに 0 を返す。
- candidate がある場合だけ既存の priority/tie-break、`can_dispatch_now`、pending clear、`enter_exception` を cold 部で実行する。
- tail-chain からの既存 call も同じ helper を使う。
- 新しい cached state は持たず、NVIC/PPB/SysTick mutation point は変更しない。guest-visible priority、entry cycle、stacking、tail behavior を変更しない。

この形で、正確性リスクの大きい incremental summary を最初から導入せず、通常の no-pending path の host code を短くする。compiler が現行 code と同じものを生成した場合も失敗ではなく、A/B で効果なしとして閉じる。

#### P2-B: cached pending summary

P2-A 後も profiler と optional sampling の両方で exception poll/arbitration が残存 CPU cost と確認された場合だけ別 candidate として設計する。core-local summary を採る場合は、NVIC pending/enable、PendSV/SysTick、SysTick underflow、PRIMASK、exception entry/return、level reassert の mutation matrix と、完全再計算値との debug assertion を先に文書化する。P2-B は本書だけで実装開始せず、P2-A decision record から別 HLD を起票する。

#### 効果測定

- poll 総数、fast reject 数、slow arbitration 数
- source 別 exception entry 数
- `step` あたり host cycles と branch misses
- 実アプリ全体の cycles/second
- production A/B の `ab` には、その診断 profile record を `--profile-record` で渡す。runner/verifier は aggregate と各 core について `polls = reject_no_candidate + reject_primask + reject_active_handler + entries`、`entries = source.pendsv + source.systick + source.nvic` を再計算する。profileのwall timeは採否に使わない。

P2-A diagnostic profile の実行例は次のとおりである。

```bash
python3 tools/benchmark_rp2040_cpu_candidate.py profile \
  --candidate-id P2-A \
  --backend "$RP2040_CPU_OPT_TMP/backend-p2-a" \
  --runner "$RP2040_CPU_OPT_TMP/build/p2-a-candidate-profile/release/picocalc-run" \
  --feature-set cpu-application-profiler \
  --feature-set pending-exception-fast-reject \
  --cpu <logical-cpu> \
  --target picotetris-opt1b-vrp5 --firmware /absolute/path/PicoTetris.bin \
  --target picoedit-r1-vrp2f --firmware /absolute/path/picocalc_app.bin \
  --admission-record firmware-validation/records/rp2040-cpu-p0-baseline-YYYYMMDD-NN \
  --output firmware-validation/records/rp2040-cpu-p2-a-profile-YYYYMMDD-NN/profile
```

#### 完了条件

- PRIMASK、PendSV、SysTick、NVIC IRQ、同時 pending、priority tie-break、active handler、tail-chain、exception return の既存試験が baseline/candidate で一致する。
- 次の通常/feature 有効 test を通す。

```bash
cargo test --locked -p rp2040-emu pending
cargo test --locked -p rp2040-emu exception
cargo test --locked -p rp2040-emu --features pending-exception-fast-reject pending
cargo test --locked -p rp2040-emu --features pending-exception-fast-reject exception
cargo test --locked -p picocalc-harness --features pending-exception-fast-reject
```
- P0-B の `reject_no_candidate / polls` が 90% 未満なら P2-A を開始しない。開始しなかった事実と profile 値を decision record に残す。
- feature-on diagnostic profileで `reject_no_candidate` と `polls` が正しく記録され、二つの実アプリで correctness と production A/B を完了する。

### P3. host 向け build 最適化と PGO

アルゴリズムを変えずに host compiler が CPU hot path を最適化できる余地を測る。

#### 比較構成

1. 現行 canonical release
2. `target-cpu=native` または配布条件に合う固定 ISA level
3. PGO
4. native/fixed ISA + PGO

PGO profile は PicoTetris と PicoEdit の実行比率を事前に固定して生成する。採否測定には、学習に使用した scenario と holdout scenario の両方を含める。

#### 効果測定

- 全構成を同じ 10-pair A/B 手順で測る。
- binary size、hot symbol size、host IPC、branch miss、cache miss を併記する。
- PGO raw profile と比較 build は §3.2 の一時 root、merge 済み profile の SHA-256 と生成 manifest は Git 側に保存する。

#### 完了条件

- 配布可能な host ISA 条件を文書化する。
- 学習 workload だけでなく holdout でも重大な回帰がない。
- 採用 build を再生成できるコマンドと toolchain version が固定されている。

P3 の開始前に、training は登録済み二 workload の固定 scenario、holdout はそれぞれ別の登録済み scenario とし、target revision/SHA、`rustc -Vv`、LLVM profile merge command、host ISA policy を P3 decision preamble に凍結する。holdout が登録されていなければ PGO 実装を開始しない。`target-cpu=native` はローカル専用 binary と明示できる場合だけ候補にし、配布 binary と混同しない。

現行の `load_workloads` は登録済みの二 workload を受け付ける契約であり、holdout scenario はまだ登録されていない。従って P3 は、holdout target/scenario の registry、schema、runner CLI、admission/correctness fixture を追加してから開始する。holdout の登録・admission が完了するまで、training workload だけで PGO の採否を決めない。

### P4. compact dispatch key の再評価

decode cache hit 率が高いため、hit 後の wide check、opcode 確認、operand 再抽出、handler dispatch の短縮を狙う。過去の正の結果を現在の backend と実アプリ二種で再検証する。

#### 実装

- 既存 feature `compact-dispatch-key-prototype` を candidate ID `P4` として使い、現行 baseline 上へ一変更だけ移植する。
- decode 時に compact な handler key を生成する。
- execute 時は key から直接 handler class を選ぶ。
- opcode bits が必要な命令だけ元 opcode を参照する。
- cache layout 変更とは分け、まず dispatch だけを測る。

#### 効果測定

- handler class 別 retired instruction
- dispatch branch 数、branch miss、host instructions
- binary size と I-cache 指標
- PicoTetris/PicoEdit 全体の cycles/second

#### 完了条件

- 全 Thumb encoding と undefined/fault path の一致試験を通す。
- 単独 A/B を行い、結果が正でも 5% 未満という理由だけでは棄却しない。
- 本書 §7 の規則は、旧計画の固定 5% criterion をこの検討について置き換える。

### P5. decode cache geometry と layout の探索

現行 `DecodedOp` は 12 byte、8192 entry で約 96 KiB/core である。過去の単純な 8-byte packing の回帰は、適切な entry 数、associativity、alignment の探索まで否定しない。

#### 実装候補

- entry 数: 1024、2048、4096、8192
- direct-mapped と 2-way
- 16-byte aligned AoS
- tag/metadata と decoded payload を分ける SoA

全組合せを無差別に実装せず、P0 の working set、reuse distance、conflict miss から候補を絞る。

#### 効果測定

- cold/conflict/invalidation miss
- set occupancy と reuse distance
- core 別 cache footprint
- host L1/L2 cache miss と cycles/second

#### 完了条件

- geometry ごとに同一 dispatch 実装で比較する。
- 最良候補を P4 と組み合わせ、単独効果と交互作用を測る。

### P6. predecoded micro-op

P0/P4 の opcode histogram で高頻度 handler と operand 再抽出 cost が確認できた場合に進む。

#### 実装

decode entry に必要な範囲で次を保持する。

- handler class
- register index
- sign/zero extended immediate
- flag action
- memory width と addressing mode
- branch kind と target 計算情報

guest の命令境界、cycle accounting、fault 順序、memory side effect は変えない。全命令を一度に変換せず、上位 handler class から feature-gated に追加する。

#### 効果測定

- handler ごとの host instructions と cycles
- entry size 増加による cache miss
- opcode 再抽出を省略した回数
- handler class 単独および累積の実アプリ A/B

#### 完了条件

- handler class ごとに correctness と性能を閉じる。
- entry 肥大化による回帰を含め、累積構成を再測定する。

### P7. copy しない branch linking

過去の eager sequential staging は work を増やして回帰したため再利用しない。cache entry 間の参照だけを持つ。

#### 実装

- fallthrough/taken target の slot、full tag、generation を source entry に保持する。
- link hit では decode lookup の一部を省略するが、guest 命令は一命令ずつ commit する。
- scheduler、IRQ、fault、memory side effect の観測境界を維持する。
- generation/tag 不一致では通常 lookup へ side exit する。
- invalidation 時に全 link を走査せず、generation で失効させる。

#### 効果測定

- link hit/miss
- miss/side-exit reason
- conditional branch taken/not-taken 別効果
- link metadata による entry footprint と host cache miss
- 実アプリ全体の cycles/second

#### 完了条件

- branch、exception、self-modifying code、cross-core invalidation の一致試験を通す。
- P4/P5/P6 との組合せを別 batch で測る。

### P8. profile 根拠がある場合だけ行う追加候補

P8 は候補ごとに、変更対象の avoidable event が実アプリ dynamic instruction の 5% 以上、または利用可能な sampling で host CPU sample の 5% 以上を占めることを開始条件とする。sampling が使えない場合は内部 counter だけで判定できる候補に限る。閾値未満なら実装せず、profile と見送り判断を記録する。

#### lazy flags

flag write の多くが読まれる前に上書きされることが実アプリ counter で確認できた場合だけ実装する。conditional branch、ADC/SBC、MRS、exception stacking、diagnostic read の前には必ず正確に materialize する。

#### inline memory fast path

SRAM/XIP access が CPU host cycles の有意な割合を占める場合だけ、inline fast path と MMIO/fault cold path を分離する。alias、contention、fault ordering は維持する。blanket inline は行わず、binary size と I-cache 回帰を必ず測る。

#### tiered JIT

上記の interpreter 改善後も immutable XIP block の dispatch が最大の残存 cost である場合に限り、別 HLD を作って判断する。対象は hot な immutable XIP block とし、MMIO、IRQ、fault、invalidation では side exit する。cycle accounting と一命令境界を証明できない設計は実装しない。

P8 の各候補も、通常フェーズと同じ correctness と 10-pair A/B を省略しない。

## 7. 採否規則

候補ごとに次の順で判断する。

1. correctness 不一致: 即時不採用。原因を記録して feature を既定無効にする。
2. profile mechanism 不成立: 対象 event が存在しない、または想定 counter が動かなければ実装しない/不採用とする。
3. 二 workload の combined 95% CI 上限が 0 以下: 不採用。回帰 counter と仮説の誤りを記録する。
4. combined CI がゼロをまたぐ: 単独では production 採用しない。ただし combined point estimate が正、各 workload median が -3% より上、変更が小さく独立なら feature-gated bank に残せる。
5. 単独 production 候補: combined 95% CI 下限が 0 より大きく、両 workload の median が正であること。
6. bank: 組み合わせた production binary を新 batch で直接測る。単独改善率を足し算しない。
7. final production 採用: combined 95% CI 下限が 0 より大きく、どの代表 workload にも median 3% 超の回帰がなく、全 correctness gate が一致すること。
8. combined effect に正の信号がない bank: production tree から除き、履歴は decision record に残す。

combined は §5.4 の等 workload 重み log effect である。3% は測定開始前の「重大なアプリ回帰」判定値であり、候補の最低改善率ではない。固定 5% の改善率を採用条件にはしない。

規則5は、候補一つを単独で通常 production path へ統合する条件である。規則4で bank になった候補は単独統合せず、feature-gated のまま他候補との combined build だけを規則7で再評価できる。規則7を通った組合せだけを一括して通常 path へ統合し、統合後 binary をさらに最終 batch で再確認する。

採否にかかわらず、全候補に decision record を作る。

## 8. decision record の必須項目

- candidate ID、feature、commit
- 仮説と変更した hot path
- baseline/candidate executable SHA-256
- firmware、target revision、scenario、runner、descriptor
- host CPU、OS、kernel、compiler、linker
- build command と environment
- profile counter の前後差
- workload ごと 10 pair、合計 40 measured run の全 raw measurement
- workload 別/combined の geometric mean effect、median、IQR、95% CI
- correctness digest の比較
- binary size、maximum RSS
- 採用、不採用、bank の判断と理由
- 既知の制約と次の候補

結果 JSON は、少なくとも次の identity を機械可読で持つ。

```json
{
  "schema_id": "picocalc.rp2040-cpu-ab",
  "schema_version": 1,
  "candidate_id": "P1-A",
  "baseline_backend_commit": "...",
  "candidate_backend_commit": "...",
  "baseline_executable_sha256": "...",
  "candidate_executable_sha256": "...",
  "workload": "picotetris-opt1b-vrp5-r10",
  "firmware_sha256": "...",
  "target_contract_sha256": "...",
  "scenario_sha256": "...",
  "batch_id": "...",
  "pair_index": 1,
  "order": "AB",
  "run_ids": ["run-001", "run-002"],
  "baseline": {},
  "candidate": {},
  "pair_log_ratio": 0.0,
  "baseline_guest_observation_sha256": "...",
  "candidate_guest_observation_sha256": "...",
  "guest_observation_equal": true,
  "baseline_projection_path": "correctness/.../baseline-projection.json",
  "candidate_projection_path": "correctness/.../candidate-projection.json"
}
```

## 9. 中止条件

次の場合、その batch または候補の測定を止める。

- baseline/candidate の backend worktree が dirty、commit 未記録、または candidate が宣言した変更以外を含む。
- firmware、scenario、target contract、build profile、toolchain、host ISA が baseline/candidate で意図せず異なる。
- embedded backend commit と Git HEAD が一致しない、または runner SHA/feature set が manifest と一致しない。
- correctness digest が一致しない。
- profiler counter の不変条件が破れる。
- v1/v2 の calibration anchor model residual、または v3 の local leave-one-group-out residual・anchor group relative MAD・pair sensitivity がそれぞれ固定2% gateを超える、anchorが欠落する、または host stability の事前定義違反がある。
- 結果を見た後に統計手順、除外規則、停止条件を変更した。
- historical record を上書きしなければ測定を続けられない。

中止後は同じ batch ID に継ぎ足さず、原因を直して新しい batch として最初から測る。

## 10. 実行順と成果物

| 順序 | 実装 | 必須成果物 |
|---:|---|---|
| 1 | P0-A1 runner/schema implementation | Python unit test、schema fixture verification |
| 2 | P0-0 common baseline admission | 二 workload の admission、baseline manifest |
| 3 | P0-A2 null batch | v3 replicated calibration（9境界×3=27、median/MAD、piecewise log knot、local residual）、40-run null record、environment verification |
| 4 | P0-B minimal profiler | profile schema、二 workload profile、disassembly proof |
| 5 | P1-A tag guard | 実装、単独 profile、correctness は完了。null-control pass 後に、A/B CPU と一致する correctness を取り直してから 10-pair/workload A/B、decision |
| 6 | P1-B executable page | 開始 gate、単独・P1 combined 実アプリ A/B、decision |
| 7 | P2-A exception fast reject | 開始 gate、IRQ correctness、feature-on diagnostic profile（poll/source conservation）を完了。null-control pass 後に A/B CPU と一致する correctness/profile を取り直し、その後 10-pair/workload A/B、decision |
| 8 | P3 native/PGO | build matrix、holdout A/B、配布条件 |
| 9 | P4 compact dispatch | 現行 backend での再評価記録 |
| 10 | P5 cache geometry | working-set 根拠、候補別 A/B |
| 11 | P6 predecoded micro-op | handler 単位の累積 A/B |
| 12 | P7 branch linking | link counter、correctness、実アプリ A/B |
| 13 | P8 data-driven candidates | 個別 HLD、correctness、A/B |
| 14 | production candidate | 全採用候補を組み合わせた最終 A/B |

最終報告では、単独候補の改善率を足し算して総効果を推定しない。実際に組み合わせた一つの production candidate を、同じ二つの実アプリで baseline と直接比較した値だけを最終効果とする。

### 10.1 phase gate

2026-09-01 時点では P0-A1、P0-0、P0-B は pass、P0-A2 は六つの immutable invalid recordを保持している。CPU 11 の `rp2040-cpu-p0-null-v2-20260831-02` は 40 run、15 anchor、correctness、checksum、target-schema、group MAD、raw/host-corrected null-effect と CI を pass したが、global log-linear anchor model の最大 residual 5.1743%（RMS 3.1993%）が固定2% stability gateを超えたため invalid である。非線形な host trajectoryが原因であり、閾値緩和や結果の再解釈は行わない。v2の宣言したpiecewise correctionと実装gateの契約差を修正する `interleaved-anchor-v3`（9境界×3 replicate、27 anchor、piecewise log knot、leave-one-group-out local residual ≤2%、pair sensitivity ≤2%）の runner/schema/verifier/unit test と CPU11 correctness record は完了し、real null-control が次の実測マイルストーンである。
P1-A は runtime 実装、profile、correctness を完了し、診断 profile signal を保存済みである。既存 correctness record は `measurement_cpu=null` のため、production A/B の CPU と一致する correctness を取り直す必要がある。既存 profile は診断専用で A/B admission には使わない。P1-A の production 性能 A/B の測定・採否は有効な null-control と CPU-aligned correctness 完了後まで保留している。P2-A は `ba93c1f` で fast-reject実装とfeature testを完了し、`rp2040-cpu-p2-a-correctness-20260831-01` の両 workload correctness、behavior trace、checksumを完了した。`rp2040-cpu-p2-a-profile-20260831-01` で `cpu-application-profiler,pending-exception-fast-reject` の feature provenance、aggregate/core counter 式、no-candidate reject率 99.989%/99.943% を検証済みであるが、correctness は CPU 1、profile は CPU 0 である。性能A/Bはnull-control完了後に行う。batch 05 は anchor stability gateでinvalidだったため、v3 null-controlがpassした場合にCPU 11を共通値として P1-A correctness、P2-A correctness、P2-A profile を取り直し、その pass record だけを pointer gate で production A/B に接続する。
P1-B は executable-page filter 用 counter が未取得のため判定不能であり、下表の fail-closed 条件を維持する。P0-A2 が有効になった後、まず CPU 11 へ P1-A/P2-A の correctness/profile identity を揃え、その後 P1-A の production A/B を同じ二 workload・10 pair で実行する。

| Gate | 必須入力 | pass | fail 時 |
|---|---|---|---|
| P0-A1 | schema/runner unit test | CLI、schema fixture、統計、projection test が通る | 実 workload を走らせず runner を修正 |
| P0-0 | 二 target contract、共通 commit | 二 workload の guest acceptance と2回 determinism | 共通 commit 選定または新 target revision。候補実装停止 |
| P0-A2 | admitted baseline | v3 null batch/calibration が完全記録され、9境界×3 replicate の relative MAD、leave-one-group-out local residual、pair sensitivity が各2%以下で、raw/corrected null effect/CI gateも通る | 閾値を緩和せず、replicate外れ値/局所host軌跡/host条件を切り分けて新 batch ID で全体再実行 |
| P0-B | admitted baseline（counter-only実装はP0-A2 pass前に開始可） | counter invariant と compile-out proof | profiler 修正。P1/P2停止 |
| P1-A | `unrelated_would_clear > 0` | runtime implementation、profile、correctness pass は完了。valid null-control 後に A/B record 完了 | event 0なら未実装、mismatchなら不採用 |
| P1-B | profile-only `non_executable_sram_write_requests`、workload別 ratio、等重み combined ratio 1%以上、P1-A decision | correctness pass、単独/combined A/B | counter欠落・分母0・ratio未達なら見送り |
| P2-A | no-candidate reject率 90%以上、`cpu-application-profiler,pending-exception-fast-reject` profile、aggregate/core poll/source conservation | correctness pass、diagnostic profile検証、A/B record 完了 | 未達・式不一致なら見送り |
| 各 production 候補 | candidate decision | §7 final rule | productionへ統合しない |

## 11. 実装ファイルと検証コマンド

### 11.1 P0-A1 で変更するファイル

- `picocalc_emu/tools/benchmark_rp2040_cpu_candidate.py` — 新規 runner
- `picocalc_emu/tests/test_benchmark_rp2040_cpu_candidate.py` — subprocess を実行しない固定 fixture unit test
- `picocalc_emu/firmware-validation/rp2040-cpu-profile.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-ab.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-decision.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-profile-comparison.schema.json`
- `picocalc_emu/firmware-validation/rp2040-cpu-build-provenance.schema.json`
- `picocalc_emu/tools/verify_environment.py` — schema/record/profile-comparison 検証の登録

P0-A1 は backend hot path を変更しない。ここが最初の実装単位である。`admission/` の二つの receipt は decision schema と同じ identity context を持ち、root decision の evidence と対応させる。

### 11.2 P0-B/P1/P2 で変更する backend file

| Phase | 主な変更ファイル |
|---|---|
| P0-B | `rp2040-emu/src/cpu_application_profile.rs`、`lib.rs`、`core/mod.rs`、`core/decode.rs`、両 Cargo manifest、`picocalc-harness/src/main.rs` |
| P1-A | `rp2040-emu/src/core/mod.rs`、`src/tests.rs`、両 Cargo manifest |
| P1-B | `rp2040-emu/src/bus/mod.rs`、`core/decode.rs`、`lib.rs`、`src/tests.rs`、`tests/multicore.rs`、両 Cargo manifest |
| P2-A | `rp2040-emu/src/core/mod.rs`、`core/exceptions.rs` の test、`src/tests.rs`、両 Cargo manifest、`picocalc-harness/build.rs` |

backend 共通回帰 command:

```bash
cargo fmt --all -- --check
cargo test --locked -p rp2040-emu
cargo test --locked -p rp2040-emu --test firmware
cargo test --locked -p rp2040-emu --test multicore
cargo test --locked -p rp2040-emu --test dual_model --features threading
cargo test --locked -p rp2040-emu --test execution_model --features threading,testing
cargo test --locked --release -p rp2040-emu -p picocalc-board -p picocalc-harness
cargo build --locked --release -p picocalc-harness --bin picocalc-run
```

実機 silicon oracle は既存正確性証拠を変更する候補で別途必要性を判断する。本計画の性能測定は USB/実機操作を含まず、P0/P1-A の開始を実機接続に依存させない。

## 12. 実装開始手順

現在の二 repository の通常 checkout には別作業の変更があるため、そこから性能 binary を作らない。共有 root 直下へ directory を作らず、一時 root 内の clean worktree を使う。

```bash
RP2040_CPU_OPT_TMP="$(mktemp -d /tmp/picocalc-rp2040-cpu-opt.XXXXXX)"

git -C /home/fuyuki/pico_dvl/codex/picoem-picocalc \
  worktree add --detach "$RP2040_CPU_OPT_TMP/backend-baseline" \
  73784b96a1afdb34dc1a79577f947b670a138d07

git -C /home/fuyuki/pico_dvl/codex/picoem-picocalc \
  worktree add --detach "$RP2040_CPU_OPT_TMP/backend-candidate" \
  73784b96a1afdb34dc1a79577f947b670a138d07

git -C /home/fuyuki/pico_dvl/codex/picocalc_emu \
  worktree add --detach "$RP2040_CPU_OPT_TMP/control" HEAD
```

P0-A1 の runner/schema/provenance 実装、unit test、baseline production build、P0-0 admission は完了済みである。P0-A2 の四つの null batchは各40 run、correctness、checksum、target-schemaを完了し、最初の二つは host drift、改訂 batch `rp2040-cpu-p0-null-20260831-04` は anchor 最大残差 4.3027%、CPU 11 の `rp2040-cpu-p0-null-20260831-05` は anchor 最大残差 4.5046% により invalid となった。両 batchの raw/host-corrected null-effect と CI は閾値内だが、有効 null-control ではない。v2 calibration protocol（5境界×3 replicate、中央値/MAD、各2% gate）は runner/schema/verifier/unit test へ実装済みであり、v2初回 batchも global residual 5.1743%で invalidとなった。v3 calibration protocol（9境界×3 replicate、27 anchor、piecewise log knot、local residual、各2% gate）は runner/schema/verifier/unit test へ実装済みであり、新 batch は v3で取り直す。P0-B counter-only profiler は実装・profile・compile-out・correctness まで完了し、profile の `unrelated_would_clear > 0` と no-candidate reject率 90%以上により P1-A/P2-A の実装開始条件を満たした。P1-A は runtime 実装、SRAM alias を含む correctness、diagnostic profile、profile-comparison schema/verifier まで完了しているが、既存 correctness record は CPU 未記録であり、CPU 11 の production A/B 前に correctness を取り直す必要がある。既存 P1-A profile は診断専用で A/B admission には使わない。P2-A は `ba93c1f` で実装・feature test・両 workload correctness（`rp2040-cpu-p2-a-correctness-20260831-01`）と feature-on diagnostic profile（`rp2040-cpu-p2-a-profile-20260831-01`）を完了した。profile の feature provenance、aggregate/core の poll/source conservation 式、no-candidate reject率 99.989%/99.943% は pass であるが、既存 correctness/profile record の CPU は 1/0 であり、CPU 11 の production A/B 前に両方を取り直す必要がある。v3 null-control が passした場合は、CPU 11 で P1-A correctness、P2-A correctness、P2-A profile を揃え、その pass record を pointer gate で検証してから P1-A/P2-A の production 10-pair A/B を実施する。

候補 worktree で commit を作る場合は commit hash を即座に manifest/decision 下書きへ記録し、一時 directory の削除で参照を失わない branch または tag へ保持する。実装成果を既存 checkout へ統合する操作、commit、push は本計画の作成作業には含めない。

### 12.1 P0 implementation-start Definition of Done

- 新 runner の CLI/schema/statistics unit test が通る。
- output overwrite、dirty backend、identity mismatch を run 前に拒否する。
- baseline production runner を明示した `CARGO_TARGET_DIR` に build 済みである。
- common baseline が二 workload に admission され、record と verifier が pass する。
- null batch と calibration が machine-readable record として検証される（`rp2040-cpu-p0-null-20260830-02` と `rp2040-cpu-p0-null-20260831-01` は drift invalid、`rp2040-cpu-p0-null-20260831-04` は anchor residual 4.3027%、`rp2040-cpu-p0-null-20260831-05` は anchor residual 4.5046%による invalid の証拠として保存済み。全四 record は correctness/checksum/target-schemaを完了し、v2 protocolの実装・schema・verifier・unit testも完了している）。
- P0-B counter-only profiler、profile、compile-out、profiler-OFF correctness は完了済みである。P1-A full-tag guard は runtime commit `61f8bde`（provenance 列挙の follow-up `6f8ce41`）で実装・profile・correctness を完了したが、既存 correctness record の CPU は未記録であり、production A/B の CPU 11 と一致する correctness を取り直す必要がある。既存 P1-A profile は診断専用で A/B admission には使わない。P2-A exception fast reject は `ba93c1f` で実装・feature test・correctness・feature-on diagnostic profile（`rp2040-cpu-p2-a-profile-20260831-01`、aggregate/core/source conservation、no-candidate reject率 99.989%/99.943%）を完了したが、既存 correctness/profile の CPU は 1/0 である。次工程は anchor stability 原因を切り分けた有効 null-control、その後 CPU 11 で P1-A correctness、P2-A correctness、P2-A profile を取り直し、各 pass record の CPU identity を pointer gate で検証してから P1-A/P2-A production 10-pair A/B の順で進める。profile の wall-time 採否と P1/P2 の production promotion は、有効 null-control と correctness/A-B 記録の完了後に行う。P1-B は executable-page filter counter の profile-only 拡張と定義済み ratio gate が先である。使用 commit/target revision は各 `manifest.json` に固定する。

この Definition of Done が満たされれば、計測条件を後から都合よく変更せず、P0-B と最初の CPU 速度候補 P1-A の実装・診断計測を閉じ、次に有効 null-control 下の production 効果測定へ進める。
