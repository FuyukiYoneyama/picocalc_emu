# 作業パッケージの履歴と最終状態

本プロジェクトの本筋は[エミュレーターを使ったPicoCalc開発](PROJECT_OVERVIEW.md)です。
ここは作業履歴の台帳です。現在の利用手順は[USER_GUIDE](../USER_GUIDE/README.md)、
使用版は[IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)を参照します。

| 取り組み | 最終状態と扱い |
|---|---|
| R0〜R6 | BSP・生成・firmware検証・回帰・実機相関・配布の基盤を整備した履歴 |
| NEXT-1〜NEXT-4 | PicoEdit、限定multicore／audio、negative conformance、machine APIの固定版受入履歴 |
| UF2Loader／M-NESCO／SD-GEN-1 | 固定source・backend・artifactでの限定受入履歴 |
| I2C-EXT | 任意profileでの固定版受入履歴 |
| OPT1-B | 過去に採用したSerial fast path。公開版復旧先の基準 |
| OPT2／OPT3／OPT4 | 不採用・保留を含む過去の実験。現行作業ではない |
| UX 1倍速／PERF／PERF-RECOVERY | **失敗・終了**。1倍速未達、機能維持した高速化の公開に至らず、旧地点へ原状回復 |
| DMA音声バッファ限定検証 | 2026-09-11不採用・終了。確保除去は確認したが採用条件未達 |
| 公開版復旧と再測定 | 32d27ffへ復旧。無変更公開commitの再測定と原本保全を実施。高速化達成ではない |

各機能の過去の「完了」は、その固定backendでの受入です。復旧後公開mainに全機能があることを意味しません。

## 履歴の所在

- [高速化失敗の総括と計画一覧](history/performance/README.md)
- [整理前の詳細台帳](history/project-status-20260911/MILESTONES.md)
- [全履歴](history/README.md)
- [最新の保全済み公開版測定](../firmware-validation/evidence/public-speed-retained-20260911-01/README.md)

旧文書の中断・hold・再開条件は当時の記録として保持します。
終了した高速化の未完了項目を、PicoCalc開発環境の現行作業へ自動的に持ち越しません。
