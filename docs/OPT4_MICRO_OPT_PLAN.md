# OPT4 micro-opt bank

> **現行計画。** これは歴史記録ではない。現在の性能改善作業と採否条件はこの文書を正典とする。

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
| OPT4-A unconditional cache lookup | **screening pass / bank候補** | cache lookupから重複したcacheable-region判定を除去する。full tag比較と番兵除外を維持する。詳細は[`OPT4_A_UNCONDITIONAL_CACHE_LOOKUP.md`](OPT4_A_UNCONDITIONAL_CACHE_LOOKUP.md) |
| OPT4-B NVIC bitmap scan | **exactness pass／速度改善未確認。promotionなし** | pending bitだけを`trailing_zeros`で走査したが、10-run A/Bの差はnoiseの範囲。詳細は[`OPT4_B_NVIC_BITMAP_SCAN.md`](OPT4_B_NVIC_BITMAP_SCAN.md) |
| OPT4-C 8-byte `DecodedOp` | **exactness合格／性能不採用** | tag圧縮、valid bit、region invalidation、fault entryをfeature-gatedで試作。10-run A/Bで中央値退行、promotion／bank追加なし。詳細は[`OPT4_C_DECODED_OP_8BYTE.md`](OPT4_C_DECODED_OP_8BYTE.md) |
| OPT4-D diagnostic PC compile-out | **exactness合格／性能不採用** | 通常命令の`active_pc`更新をfeature-gatedでcompile-out。正式PicoTetris（`--psram --keyboard --sd --sd-format fat32`）で再測定したが、分散が大きく正の改善を識別できず、診断時はPC attributionがstaleになり得るためpromotion／bank追加なし。詳細は[`OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md`](OPT4_D_DIAGNOSTIC_PC_COMPILE_OUT.md) |
| OPT4-E compact dispatch key | **exactness合格／性能不採用** | 既存flags領域へdispatch keyを格納。正式シナリオ10-run A/Bはhost slowdownで未完了、100M-cycle短縮screeningでも正の信号なし。OPT4-Cの8-byte表現とは併用拒否。詳細は[`OPT4_E_COMPACT_DISPATCH_KEY.md`](OPT4_E_COMPACT_DISPATCH_KEY.md) |

## OPT4-Aの境界

`populate_decode_cache`は現在もcacheableなROM/XIP/SRAM PCだけを書き込む。invalidateは既存entryを
消すだけで、新しい非cacheable entryを作らない。OPT4-Aはこの不変条件を利用し、lookup時には
slotのentryとfull PC tagだけを比較する。tagが一致しない場合は従来どおりslow pathへ進む。

この変更はfeature `unconditional-cache-lookup-prototype`でのみ有効で、default buildの挙動と
コード経路は変更しない。候補の受入には、既存unit test、全firmware exactness、10-run A/B、
代表workload退行、clean working treeを必要とする。候補が採用されない場合はfeatureとcommitを
revertし、active targetを変更しない。

## 実行順序

1. OPT4-Aをcurrent promoted baselineへ適用し、exactnessをローカルで確認する。
2. trace/proof OFFの10-run以上A/Bと95% CIを記録する。
3. OPT4-Bは独立候補として測定済みであり、速度改善未確認のためpromotionしない。
4. OPT4-Cは実装・exactness・10-run A/Bまで完了した。性能改善未確認かつ中央値退行のため、promotion／bank追加を行わない。
5. OPT4-Dは実装・exactness・正式SD/FAT32条件での10-run A/Bまで完了した。測定分散が大きく、平均・中央値とも正の改善を識別できなかった。診断PC attributionの制約もあるため、promotion／bank追加を行わない。
6. OPT4-Eは実装・exactnessまで完了した。正式シナリオ10-run A/Bはhost slowdownで未完了、短縮screeningでも正の改善信号がなく、promotion／bank追加を行わない。
7. 次候補へ進む場合も、元のpromoted baselineとのexactnessと10-run A/Bを独立に記録し、候補をbank化する場合はbank全体で総合比較する。

GitHub Actionsは通常開発では実行しない。測定・回帰・採否判断はローカルで完結させる。
