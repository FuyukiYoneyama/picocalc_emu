# OPT4 micro-opt bank

> **現行計画。** これは歴史記録ではない。現在の性能改善作業と採否条件はこの文書を正典とする。

2026-08-16のbackend整合性レビューで、現行mainのOPT4-A featureにempty-sentinel回帰を確認した。
新しい性能測定より先に、backend側の
[`BACKEND_CHANGE_VALIDATION_PLAN.md`](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/main/docs/BACKEND_CHANGE_VALIDATION_PLAN.md)
に従う。sentinel修正とcache representationのfeature matrix、DMA／audioのquantum-invariance
比較、HIGH_PRIORITY／timer競合の局所試験、CLI／report E2E、firmware回帰を完了した。firmware回帰で
cycle差が出た3 targetは暫定分類のうえholdとし、過去の隔離candidateの測定値を現行mainの
exactness合格根拠へ流用しない。

2026-08-16の現行main firmware回帰は実行完了した。audio targetは契約項目が一致し、公式Helloは
registry受入項目に合格したが、
PicoTetris／multicore／PicoEditではUART・framebuffer・scenario等を保ったままcycle指紋に小さな差が
出た。差分は`94818f8` probeと`00b05f5` checkpointでdefault runtime更新帯に暫定的に境界づけられ、後続の
feature-gated OPT4候補の影響ではない。cycle exactnessの不一致を吸収せず、OPT4-Aをbankへ戻さず、
promoted target／backend pinも変更しない。詳細な数値と再現条件はbackend側の計画書へ固定する。

## 目的

OPT1-Bで得た正確性を維持したまま、1%未満の小さな改善も候補として積み上げる。
速度を目的化せず、挙動の完全一致を最優先する。既存のOPT0-B behavior/event契約、
target registry、promoted backendの固定値は変更しない。

## 採否規則

1. exactnessは絶対条件である。cycle、virtual time、timeline、UART、framebuffer、
   PSRAM、scenario、behavior SHA、全domain digestのいずれか1つでも不一致なら即時revertする。
2. 候補はproductionへ直接入れず、独立したfeature gateとcommitで試す。
3. 候補ごとにtrace/proof OFFのA/Bを最低10回、交互順序で実行し、中央値・平均・95% CIを保存する。
4. 主workloadだけでなく、既存の代表workload（Template B、公式Hello等）で退行を確認する。
5. 1候補の「5%以上」という旧gateは、候補を記録するための下限としては使わない。ただし、
   小差をnoiseと区別できない場合は採用しない。
6. 複数候補をまとめる場合は、各候補のexactness記録を残したうえで、
   **micro-opt bank全体**を元のpromoted baselineとA/B比較する。bankには複雑度、保守負担、
   追加メモリ、診断経路への影響を記録し、総合的に採否を決める。
7. 採用してもpromoted targetのpinを自動更新しない。新しいversioned validationとローカル検証を
   完了してから、別途promotion判断を行う。

## 基準点

- 正式なpromoted backendはOPT1-B固定値を使用する。
- 正式なPicoTetris性能値はwall中央値25.381594秒、実時間比14.636593%である。
- 過去のOPT3-Cの25.61秒／4.1541916168%は、当時の26.72秒baselineに対する歴史記録であり、
  現在の改善率やpromotionの証拠として再利用しない。
- すべての性能測定は、同一のsource、toolchain、CPU affinity、workload、trace/proof設定で行う。

## 候補の順序

| 候補 | 状態 | 方針 |
|---|---|---|
| OPT4-A unconditional cache lookup | **sentinel／DMA・audio／priority低レベル／CLI E2E合格、firmware差分hold** | backend `37c50e6`で回帰を修正し、default／unconditional／8-byte／compactのfeature matrix、`6a675b1`のDMA／audio quantum-invariance 5/5、`00b05f5`のHIGH_PRIORITY／timer競合5/5、`e0eda1c`のboard-less audio／WAV／UART marker E2Eを合格。現行main firmwareはHelloを含め実行完了したが、Tetris -1 cycle、multicore +5、PicoEdit -4が残るためbankへ戻さない。詳細は[`OPT4_A_UNCONDITIONAL_CACHE_LOOKUP.md`](OPT4_A_UNCONDITIONAL_CACHE_LOOKUP.md) |
| OPT4-B NVIC bitmap scan | **exactness pass／速度改善未確認。promotionなし** | pending bitだけを`trailing_zeros`で走査したが、10-run A/Bの差はnoiseの範囲。詳細は[`OPT4_B_NVIC_BITMAP_SCAN.md`](OPT4_B_NVIC_BITMAP_SCAN.md) |
| OPT4-C 8-byte `DecodedOp` | **exactness合格／性能不採用** | tag圧縮、valid bit、region invalidation、fault entryをfeature-gatedで試作。10-run A/Bで中央値退行、promotion／bank追加なし。詳細は[`OPT4_C_DECODED_OP_8BYTE.md`](OPT4_C_DECODED_OP_8BYTE.md) |
| OPT4-D diagnostic PC compile-out | **exactness合格／性能不採用** | 通常命令の`active_pc`更新をfeature-gatedでcompile-out。正式PicoTetris（`--psram --keyboard --sd --sd-format fat32`）で再測定したが、分散が大きく正の改善を識別できず、診断時はPC attributionがstaleになり得るためpromotion／bank追加なし。詳細は[`OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md`](OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md) |
| OPT4-E compact dispatch key | **exactness合格／性能不採用** | 既存flags領域へdispatch keyを格納。正式シナリオ10-run A/Bはhost slowdownで未完了、100M-cycle短縮screeningでも正の信号なし。OPT4-Cの8-byte表現とは併用拒否。詳細は[`OPT4_E_COMPACT_DISPATCH_KEY.md`](OPT4_E_COMPACT_DISPATCH_KEY.md) |

| OPT4 bank判定 | **promotionなし。現在のbankは空** | Aは低レベルtest／CLI E2Eまで合格し、firmware回帰もHelloを含め完了したが、3 targetのcycle差が残る。B〜Eは不採用。差分のversioned validation判断までbankへ戻さない。詳細は[`OPT4_BANK_DECISION.md`](OPT4_BANK_DECISION.md)に固定する。 |

## OPT4-Aの境界

`populate_decode_cache`は現在もcacheableなROM/XIP/SRAM PCだけを書き込む。invalidateは既存entryを
消すだけで、新しいnon-cacheable entryを作らない。OPT4-Aはこの不変条件を利用するが、通常
12-byte表現ではempty tagも`u32::MAX`であるため、full PC tag比較だけではfaulting PC
`u32::MAX`を除外できない。representation共通helperは、有効entryであることも確認しなければならない。

この変更はfeature `unconditional-cache-lookup-prototype`でのみ有効で、default buildの挙動と
コード経路は変更しない。候補の受入には、既存unit test、全firmware exactness、10-run A/B、
代表workload退行、clean working treeを必要とする。候補が採用されない場合はfeatureとcommitを
revertし、active targetを変更しない。

## 実行順序

1. OPT4-Aのempty-sentinel回帰を修正し、default／12-byte／8-byte／compactの有効feature matrixをローカルで確認する。**完了 2026-08-16**。
2. DMA quantum-invarianceの比較状態をtimer／audio観測まで拡張する。**完了 2026-08-16**。
3. HIGH_PRIORITYとtimer競合をquantum 1／16／64で局所試験する。**完了 2026-08-16**。
4. timer-miss report、board-less audio/WAV、UART marker profileのCLI E2Eを追加する。**完了 2026-08-16**。
5. 公開文書を実装とtestの実範囲へ同期する。**完了 2026-08-16**。
6. source変更が固まった後にfmt／Clippy gateを閉じる。**完了 2026-08-16**（対象crate gate）。
7. 新backendでPicoTetris、audio、multicore、PSRAM、SD、PicoEdit、公式Helloをローカル再回帰する。**実行完了 2026-08-16**（audioは契約項目、Helloはregistry受入項目に合格。3 targetはcycle差以外一致）。
8. 差分を**暫定分類**し、Hello fullをregistry受入項目単位で閉じる。**検証reportと境界probeは
   `firmware-validation/evidence/opt4-current-main-20260816-01/`へ固定済み**。ただし、cycle exactnessの
   不一致を受け入れるversioned validation／実機相関は今回実施せず、差分targetはholdとした。audio／Helloの
   個別契約項目合格は記録したが、OPT4-Aをbankへ戻すか、versioned validation候補を作るpromotion判断は
   行わない。責任commit／domainの確定はOPT4再開時の後続課題である。

GitHub Actionsは通常開発では実行しない。測定・回帰・採否判断はローカルで完結させる。
