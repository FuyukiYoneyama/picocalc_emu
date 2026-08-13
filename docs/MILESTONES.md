# 現行計画の完了状態

**この文書が番号付き作業計画の正典です。** 2026-08-13時点で、定義済みの作業パッケージは
すべて完了または正式終了しています。新しい番号付き作業はまだ定義していません。

## 状態

| 順序 | 作業パッケージ | 最終状態 |
|---|---|---|
| R0 | 基準点・生成契約・provenance | 完了 2026-08-05 |
| R1 | verdict/report、FAT32既定、公式keyboard conformance | 完了 2026-08-05 |
| R2 | Firmware CLI・target registry | 完了 2026-08-06 |
| R3 | PicoTetris正式回帰 | 完了 2026-08-06 |
| R4 | 3リポジトリ品質ゲート | 完了 2026-08-06 |
| R5 | 同一artifact PicoCalc実機相関 | 完了 2026-08-08 |
| R6 | 文書・配布状態確定 | 完了 2026-08-08 |
| R6-M | backend role／回帰境界の分離 | 完了 2026-08-09 |
| OPT1-B | Serial fast-path gate | promoted完了 2026-08-08 |
| OPT2 | exact event batching | 性能条件未達。追加promotionなしで終了 2026-08-09 |
| OPT3 | CPU/decode高速化 | OPT3-Cまで評価。5%条件未達でrevert、終了 2026-08-09 |
| NEXT-1 | 新規blind app（PicoEdit） | 完了 2026-08-09 |
| NEXT-2 | bounded multicore／audio | NEXT-2A・2B完了 2026-08-09 |
| NEXT-3 | negative conformance | 完了 2026-08-10 |
| NEXT-4 | 安定headless machine API | 完了 2026-08-10 |

15項目すべてに最終処置があります。13項目は完了またはpromoted、OPT2とOPT3は正確性を
優先する性能gateにより正式終了しました。不採用candidateはactive targetへ混入していません。

## 現在の品質境界

検証は次の三層を分離します。

1. host unit test — hardware-freeなロジックを高速に保護
2. firmware scenario — 同一RP2040 BINとPicoCalc device modelの権威ある自動判定
3. hardware correlation — 同一artifactを実機で確認する最終相関

Host backendの合格だけでハードウェア挙動を合格にしません。runnerの終了コード0だけでも
合格にせず、targetが固定したBIN、backend、scenario、stop reason、UART、report、snapshotを照合します。

## 次の作業

番号付きのR/NEXT作業は完了しています。次の現行計画は、番号付き作業とは別に固定した
**UF2Loader SD／flash統合（U0〜U6、M-NESCO、未着手）**です。
詳細は[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)を参照してください。
`history/`に残る古い「次はNEXT-*」「次はOPT*」を再開指示として扱いません。
次の実装を開始する前に、目的、受入条件、対象リポジトリ、実機操作、ローカル検証、CI予算を
計画書で固定します。UF2Loader計画では、まずU0を閉じるまでproduction codeを変更しません。

### UF2Loader計画の実施順序と中間マイルストーン

| 順序 | 計画段階 | 状態 |
|---:|---|---|
| 1 | U0 provenance／fixture／first-run trace | 未着手 |
| 2 | U1 SD RAW image | 未着手 |
| 3 | U2 flash erase/program | 未着手 |
| 4 | **M-NESCO** — `Picocalc_NESco`を既存direct bootでdebug開始 | 未着手（U1・U2完了後） |
| 5 | U3 directory snapshot import | 未着手 |
| 6 | U4 実loaderで判明したSD protocol gap | 未着手 |
| 7 | U5 boot2 entry／watchdog warm reset | 未着手 |
| 8 | U6 実`uf2loader` end-to-end | 未着手 |

M-NESCOは番号付きR/NEXTの追加ではなく、U1とU2のGateが閉じた時点で
`Picocalc_NESco`のdebugを解禁する中間マイルストーンです。この時点では
directory import、boot2、watchdog、`uf2loader supported`をまだ宣言しません。

候補にはnegative conformance母数の拡充、追加blind app、SD fault／persistence、machine APIの
client利便性がありますが、いずれも正式計画ではありません。

## 詳細履歴

各作業の当時の受入条件、commit、SHA、測定値、判断経緯は
[`history/MILESTONES_DETAIL_20260810.md`](history/MILESTONES_DETAIL_20260810.md)と
[`history/README.md`](history/README.md)に保存しています。
