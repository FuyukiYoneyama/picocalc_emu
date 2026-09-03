# RP2040 CPU P1-A 採用決定

- 決定日: 2026-09-03
- candidate: `P1-A` / `decode-invalidation-tag-guard`
- backend commit: `58e73010636bb1b60fdb1ccace40db29b5bb96cc`
- 決定: **採用**

## 採用理由

PicoTetris r10 と PicoEdit r4 の二つの実アプリを等重みで集約した CPU-time の combined raw point estimate が **+1.218973%** で、マイナスではなかった。今回の採用基準はこの総合値がマイナスでないことであり、5%などの固定最低改善率は設けない。

| workload | combined raw geometric effect | 95% CI |
|---|---:|---:|
| PicoTetris r10 | +0.527860% | -0.762822%〜+1.835329% |
| PicoEdit r4 | +1.914838% | +0.730276%〜+3.113330% |
| **combined（等重み）** | **+1.218973%** | **+0.437619%〜+2.006406%** |

## 測定上の注意

production A/B は CPU 11、`interleaved-anchor-v3`、5 AB＋5 BAの10 pair/workload、60秒 cooldownで実施した。40/40 measured run、27/27 anchor、correctness projection、guest observation、pair-level sensitivity、checksum、target-schema 37/37を確認した。

記録の `summary.status=invalid` / `decision.status=invalid` は、leave-one-group-out local residual が **3.096448%** で事前固定の校正診断閾値2%を超えたことを示す。これは校正プロトコルの注意事項であり、raw point estimateをゼロまたは負へ読み替えるものではない。元の A/B record は immutable な証拠として変更せず、raw効果と校正状態を併記する。

根拠 record: `firmware-validation/records/rp2040-cpu-p1-a-production-v3-20260902-03/`

## ソース統合

- `rp2040-emu` の default feature に `decode-invalidation-tag-guard` を追加した。
- `picocalc-harness` の default featureにも追加し、build provenanceへ採用feature名を出力する。
- 比較用の歴史的 index-only path は `--no-default-features` で再現できる。
- P1-B (`executable-sram-invalidation-filter`) の最終実装は一時候補ブランチ `codex/p1b-executable-sram-filter` にのみ存在していたが、P1-Bの判定完了後にブランチ参照と一時worktreeを削除済みで、`main`へは統合していない。decisionと検証記録は保持する。P2-A (`pending-exception-fast-reject`) は `main`にコードを残すが既定オフのまま保持する。

## 検証

- `cargo test --locked -p rp2040-emu`（default）: pass
- `cargo test --locked -p rp2040-emu --no-default-features`: pass
- `cargo test --locked -p picocalc-harness`（default）: pass
- `cargo test --locked -p picocalc-harness --no-default-features`: pass
- `cargo fmt --all -- --check`、`git diff --check`、default feature tree確認: pass

詳細な測定契約・履歴・他候補の扱いは [RP2040 CPU 実アプリ高速化 実装・効果測定計画](RP2040_CPU_APPLICATION_OPTIMIZATION_IMPLEMENTATION_PLAN_20260830.md) に記載する。
