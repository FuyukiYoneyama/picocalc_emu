# 現行計画の完了状態

**この文書が番号付き作業計画の正典です。** R0〜NEXT-4は完了または正式終了しています。
性能改善については、旧OPT3終了後の現行計画としてOPT4 micro-opt bankを定義しています。

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
| OPT4 | micro-opt bank | **Aのempty-sentinel／DMA・audio／priority低レベル回帰完了。backend `00b05f5`でquantum-invariance 10/10。CLI／firmware再回帰が終わるまでbank復帰は保留、B〜Eは採用なし。promoted targetはOPT1-Bを維持。詳細は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)** |
| NEXT-1 | 新規blind app（PicoEdit） | 完了 2026-08-09 |
| NEXT-2 | bounded multicore／audio | NEXT-2A・2B完了 2026-08-09 |
| NEXT-3 | negative conformance | 完了 2026-08-10 |
| NEXT-4 | 安定headless machine API | 完了 2026-08-10 |

R0〜NEXT-4の15項目には最終処置があります。OPT2とOPT3は正確性を優先する性能gateにより
正式終了しました。不採用candidateはactive targetへ混入していません。OPT4はその後に定義した
現行の実験計画であり、OPT4-Aはsentinel回帰とDMA／audio／priority低レベル回帰を修正・合格済みですが、
CLI／firmware再回帰を
閉じるまでbank復帰を保留します。隔離candidateの測定記録は保持しますが、全体再回帰前の現行main
のexactness根拠には流用しません。OPT4-Bは速度改善未確認、OPT4-Cは
中央値退行、OPT4-Dは正式SD/FAT32条件でも正の改善未確認、OPT4-Eは正式性能測定未完了かつ短縮screeningで正の信号なしのため、いずれもpromoted targetへは採用していません。OPT4-C/D/Eの
実装・exactness・A/B結果は[`OPT4_C_DECODED_OP_8BYTE.md`](OPT4_C_DECODED_OP_8BYTE.md)／
[`OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md`](OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md)／
[`OPT4_E_COMPACT_DISPATCH_KEY.md`](OPT4_E_COMPACT_DISPATCH_KEY.md)に記録しています。

## 現在の品質境界

検証は次の三層を分離します。

1. host unit test — hardware-freeなロジックを高速に保護
2. firmware scenario — 同一RP2040 BINとPicoCalc device modelの権威ある自動判定
3. hardware correlation — 同一artifactを実機で確認する最終相関

Host backendの合格だけでハードウェア挙動を合格にしません。runnerの終了コード0だけでも
合格にせず、targetが固定したBIN、backend、scenario、stop reason、UART、report、snapshotを照合します。

## 次の作業

R/NEXTの機能作業は完了しています。現行作業は、性能面では
[`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md)、機能面では番号付き作業とは別に固定した
**UF2Loader SD／flash統合（U0〜U6、M-NESCO）**です。U0〜U2、M-NESCO-S1、U3-Aは完了し、
U3-B以降が未着手です。
OPT4／backend側は、性能測定を再開する前に
[`picoem-picocalc/docs/BACKEND_CHANGE_VALIDATION_PLAN.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/BACKEND_CHANGE_VALIDATION_PLAN.md)
の修正・低レベルtest・CLI E2E・既存firmware再回帰をこの順序で完了します。
詳細は[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)を参照してください。
`history/`に残る古い「次はNEXT-*」「次はOPT*」を再開指示として扱いません。U3-B以降を開始する前に、
目的、受入条件、対象リポジトリ、実機操作、ローカル検証、CI予算を計画書で再確認します。U0の
provenance固定は完了しており、現在はproduction codeを変更できる状態です。

### UF2Loader計画の実施順序と中間マイルストーン

| 順序 | 計画段階 | 状態 |
|---:|---|---|
| 1 | U0 provenance／fixture／first-run trace | **完了 2026-08-13** |
| 2 | U1 SD RAW image | **完了 2026-08-13** |
| 3 | U2 flash erase/program | **完了 2026-08-13** |
| 4 | **M-NESCO-S1** — `Picocalc_NESco`を既存direct bootでSD/flash debug開始 | **完了 2026-08-13** |
| 5a | U3-A host directory ↔ RAW pack／extract tool | **完了 2026-08-13** |
| 5b | U3-B runner-integrated directory snapshot import | 未着手 |
| 6 | U4 実loaderで判明したSD protocol gap | 未着手 |
| 7 | U5 boot2 entry／watchdog warm reset | 未着手 |
| 8 | U6 実`uf2loader` end-to-end | 未着手 |

M-NESCO-S1は番号付きR/NEXTの追加ではなく、U1とU2のGateが閉じた時点で
`Picocalc_NESco`のdirect-boot SD/flash debugを解禁する中間マイルストーンです。
FAT32 RAWからROMを選択し、erase/programとXIP反映を同一runで確認した証拠を
`firmware-validation/evidence/m-nesco-20260813-01/`へ保存しています。この時点では
複数size/mapperの網羅、run-to-run再attach比較、directory import、boot2、watchdog、
`uf2loader supported`をまだ宣言しません。

候補にはnegative conformance母数の拡充、追加blind app、SD fault／persistence、machine APIの
client利便性がありますが、いずれも正式計画ではありません。

## 詳細履歴

各作業の当時の受入条件、commit、SHA、測定値、判断経緯は
[`history/MILESTONES_DETAIL_20260810.md`](history/MILESTONES_DETAIL_20260810.md)と
[`history/README.md`](history/README.md)に保存しています。
