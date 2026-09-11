# UX 1倍速・高速化・性能復旧プロジェクト — 失敗・終了

終了判断: 2026-09-11。本書は終了した取り組みの総括と履歴の入口であり、再開計画ではない。
本体プロジェクトの目的は[エミュレーターを使ったPicoCalc開発](../../PROJECT_OVERVIEW.md)である。

## 目的と結果

正確性と必要な機能を維持しながらエミュレーターを高速化し、実時間1倍速へ近づけることを目指した。
局所最適化、実行単位の調整、高速地点からの機能再構築、音声バッファ確保の限定検証を進めたが、
必要機能を維持した高速化を公開版へ積み上げる結果に至らなかった。
公開版を旧高速地点と同一treeへ戻して終えた。これは原状回復であり、プロジェクトの成果ではない。
UXモードと1倍速の適格性判定は未達。再構築候補の段階的な機能合格も、全体目標の達成を意味しない。

## 全体として何が失敗したか

計測基準、維持する機能、公開状態、採用条件、完了判断を一貫して管理できなかった。
そのため、個別の実装・試験・文書が増えても、利用者の開発環境が改善したかを確実に判断できなかった。
計測手順を開発開始時から共通の前提として確立できなかったことが、判断の混乱の発端となった。
後から手順と台帳を増やしても、旧版・公開版・候補、CPU時間・wall時間の区別を運用に徹底できなかった。

局所改善を全体効果と結びつける根拠が不足した。CPU単体の改善は実アプリの改善と一致せず、
音声バッファの無駄を除去しても全体時間の大部分は残った。原因を十分に帰属できないまま、
解決策の試行や再構築を進めた。段階的な機能合格と、利用する構成全体の性能・正確性の保証を
結びつける検証設計が不十分だった。

旧高速地点と後続版は機能範囲が異なる。「高速な地点」「機能を備えた地点」「公開する地点」を
利用者の要求に沿う一つの基準へまとめられなかった。復旧措置をとっても、必要機能を維持した
高速化が成立したことにはならない。

個々の変更の採用条件、旧速度水準の復旧、1倍速への投資判断も混在した。単一実験で設けた条件を
満たさなかった事実と、全体の改善可能性は同じ判断ではない。一方、旧約14%を復旧できることは、
そこからさらに約7倍必要な1倍速への見通しを与えるものではなかった。

公開版をまず復旧するというユーザーの指示より、候補の整理・commit・clean確認が先行した。
保存状態を依頼の達成と取り違え、現在値と公開状態をユーザーが繰り返し問い直す必要が生じた。
管理と説明を担う側の責任をユーザーへ転嫁した。

文書の量も状態の明確さにつながらなかった。「現行計画」「停止中」「次の作業」が複数箇所に残り、
本来のPicoCalc開発基盤の入口が、性能試験と再構築の経緯に占有された。
最後の再測定では生データまで一時buildと一緒に削除した。検証可能性を維持する運用も失敗した。
その後、公開commitを直接再測定し原本をGitへ保全したが、先の失敗を取消すものではない。

## 数値について確定していること・していないこと

過去の「約6倍」「約7.4倍」は保存された特定の比較系列の値である。
それを公開版の現在値や実装だけが原因の退行として一般化した説明は不適切だった。
過去の差への実装・build・計測条件・環境の寄与は、この終了判断では確定していない。
すべてが実装の問題とも、すべてが計測方法の問題とも断定しない。

DMA音声バッファ検証では更新1000回あたり3000回の確保・解放を除去した。
Tetrisの組ごとのCPU短縮率中央値は約9.85%だったが一組は逆転し、事前条件を満たさず不採用。
大幅な時間差の原因を解明した実験としては扱わない。

公開版復旧commitは32d27ff、treeは旧e985a9dと一致する。
原本を保存し直した公開commit直接測定のTetris中央値は15.1483%（3回、2026-09-11）。
[生データ・測定条件・再現手順](../../../firmware-validation/evidence/public-speed-retained-20260911-01/README.md)
を参照する。全アプリの性能でも、高速化の達成でもない。
前回削除した14.914631%等の原本を復元したものでもない。

## 履歴の扱い

以前の「中断」「hold」「再開条件」は、その時点の判断として保存する。
現在は失敗・終了であり、未完了項目を現行の作業へ自動的に持ち越さない。
OPT1-Bなど以前に採用した変更の事実、各機能の固定版合格、候補の不採用理由は消さない。
計画と失敗の履歴化によって、firmware-validationの不変証拠やregistryのpinを書き換えない。

旧計画は本directoryに移し、元のpathには履歴への案内を残す。
previewのschemaや固定資料は参照整合性のため[元のdirectory](../../validated-realtime-preview/README.md)に保持する。

## 旧計画・判断の一覧

- [PICOCALC_EMULATOR_PERFORMANCE_RECOVERY_PLAN_20260903.md](PICOCALC_EMULATOR_PERFORMANCE_RECOVERY_PLAN_20260903.md)
- [PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md](PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md)
- [RP2040_CPU_APPLICATION_OPTIMIZATION_IMPLEMENTATION_PLAN_20260830.md](RP2040_CPU_APPLICATION_OPTIMIZATION_IMPLEMENTATION_PLAN_20260830.md)
- [RP2040_CPU_P1_A_ADOPTION_DECISION_20260903.md](RP2040_CPU_P1_A_ADOPTION_DECISION_20260903.md)
- [RP2040_CPU_MEASUREMENT_LEDGER_20260903.md](RP2040_CPU_MEASUREMENT_LEDGER_20260903.md)
- [QUANTUM_ENGAGEMENT_GATING_PROPOSAL_20260903.md](QUANTUM_ENGAGEMENT_GATING_PROPOSAL_20260903.md)
- [OPT4_MICRO_OPT_PLAN.md](OPT4_MICRO_OPT_PLAN.md)
- [OPT4_BANK_DECISION.md](OPT4_BANK_DECISION.md)
- [VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md](VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md)
- [VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md](VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md)
- [VRP_DUAL_BUILD_CORRECTION_ADVICE_20260830.md](VRP_DUAL_BUILD_CORRECTION_ADVICE_20260830.md)

## 主要証拠

追加の時点文書:

- [当時の中断判断](VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md)
- [未採用UX概念](UX_MODE_CONCEPT_20260830.md)
- [CPU局所測定](CPU_HOTPATH_MEASUREMENT_20260830.md)

- [R0比較](../../../firmware-validation/evidence/rp2040-cpu-recovery-r0-20260903-01/README.md)
- [G7記録](../../../firmware-validation/evidence/rp2040-cpu-recovery-g7-20260904-01/)
- [DMA限定検証](../../../firmware-validation/evidence/dma-audio-allocation-20260911-01/)
- [保全した公開版再測定](../../../firmware-validation/evidence/public-speed-retained-20260911-01/README.md)

## 今後の開発基盤に残す運用原則

開発の完了は、利用者が求める挙動を、使用版と保存した証拠で説明できることとする。
機能と性能を最終段階だけで確認せず、対象の利用条件で各変更を検証する。
計測は補助作業でなく判断の基盤として扱い、対象・手順・原本を同時に保全する。
原因の理解が深まらないとき、作業量や計画の規模を増やして進捗の代わりにしない。
