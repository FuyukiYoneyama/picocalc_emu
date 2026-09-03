# PERF-Q1 baseline（P2-A cleanup後の比較出発点）

これは高速化の成果を示す記録ではなく、次の候補を比較するための「同じ出発点」を固定した記録です。P2-Aの不採用runtimeをbackend mainから削除した`f32eba1`から、通常版`picocalc-run`をclean buildしました。

固定したもの:

- backend commit: `f32eba1878aeabc6dfc8954b363230ef1e4c2b52`
- runner SHA-256: `282d27c79caef9f8a74abdd02e2cb84fa34b0b6ffaac6b10ec58f74d8f39e2b7`
- Cargo.lock SHA-256: `2496607b2d2460231543814e57441f1ed1e5d6460d7517c7d895e959f0f710e6`
- default features: `sd-gen1-multiblock`, `decode-invalidation-tag-guard`
- `pending-exception-fast-reject`: backendから削除済み

cleanup後のbackendでは、rp2040-emu本体1264件、quantum不変性10件、firmware 9件、multicore 9件、PSRAM/PIO 4件、smoke 8件、WFE/IRQ 5件、harness runner 78件を通過しました。commit後にもquantum不変性10件とrunner 78件を再確認しています。

このbaselineは、Tetris（軽ゲーム実装）／PicoEdit（テキスト編集実装）の固定artifactとscenarioを、候補backendと比較するために使います。まだA/B測定、全target回帰、正式target revision更新は行っていません。

詳細なコマンド、toolchain、cleanup範囲、未着手項目は`record.json`を正とします。
