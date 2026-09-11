# PicoCalc開発を中心にした文書再編

日付: 2026-09-11。変更前commit: b5536033a778c50a59e3a4f08e40a48fc950927e。

## 変更の目的

エミュレーターを使ったPicoCalcアプリ開発という本来の目的に、入口と文書体系を戻した。
README、利用ガイド、要求仕様、AI／開発者ガイド、文書索引、現在状態、作業台帳を整合させた。
生成・host確認・BIN build・エミュレーター実行・scenario観測・回帰・実機確認の流れを入口とした。

高速化・UX 1倍速・性能復旧は失敗・終了としてperformance/へ総括した。
14件の計画・判断・測定解説を移動し、元のpathには案内を残した。
当時の本文は保持し、履歴の注記と移動に必要な相対リンクを調整した。
旧IMPLEMENTATION_STATUS／MILESTONESはproject-status-20260911/へ時点記録として残した。

現在の公開backendと、過去の機能受入が指定するbackendを区別した。
公開mainの旧状態への復旧を、新しい高速化や全機能の対応として記載しない。

## 確認

- 再編対象のMarkdown 45件についてローカルリンク先の欠落なし（本記録追加前の件数）。
- 移動した14件の本文は、履歴注記・リンク先を除き変更前と一致。
- git diff --check合格。
- firmware-validation／hardware-validation／reference-projects／tools／tests／bsp／scenariosに差分なし。
- public-speed-retained-20260911-01のSHA256SUMS全件合格。原本は維持。
- backend repoは無変更。エミュレーターのコード・挙動・性能を変更する作業ではないため再計測なし。
- 既知のrelease-layout不整合は本変更で解決していない。全体テスト合格とは記録しない。

現在の構成は[PROJECT_OVERVIEW](../PROJECT_OVERVIEW.md)、
終了した高速化の総括は[performance/README](performance/README.md)を参照。
