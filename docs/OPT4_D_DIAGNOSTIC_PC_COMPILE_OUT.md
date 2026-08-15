# OPT4-D: diagnostic PC compile-out 試作・検収記録

更新日: 2026-08-15

## 判定

**exactness は合格、性能の正の改善は確認できず、不採用。promotion と micro-opt bank への追加は行わない。**

試作は `picoem-picocalc` の実装commit [`33bd5ea`](https://github.com/FuyukiYoneyama/picoem-picocalc/commit/33bd5ea) を、独立feature
`diagnostic-pc-compile-out-prototype` で有効化したものです。再現可能な性能測定では isolated benchmark commit `850faea9113f8098f84a40f937786e988f07e958` を使用しました。

## 実装範囲と診断境界

`decode_execute`から通常命令ごとの`active_pc`更新だけをfeature時にcompile-outしました。

- `CoreBus::set_active_pc_for_instruction`を追加
- default buildでは従来どおり`set_active_pc`へ委譲
- feature buildでは通常命令境界のメソッドをinline no-op化
- exception entry/returnと明示的な`set_active_pc`は維持
- Serial `Bus`とThreaded `WorkerBus`の両経路を同じfeature境界で実装

このfeatureはtrace/proof OFFの性能候補専用です。feature buildでは通常命令に対するMMIO trace／unsupported-MMIOのPC attributionが stale になり得ます。その記録を診断的に正しいものとして扱ったり、通常のcorrectness PASSの根拠にしたりしてはいけません。default buildと明示的診断経路は変更していません。

## exactness

trace/proof OFFの正式PicoTetris workloadで、baselineとcandidateのreportは一致しました。

| 項目 | 値 |
|---|---|
| candidate report SHA-256 | `6720d3a6e696a1009fe37e97f741e2de7d9d5693cf4e3bf38e02f959e728ba4c` |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer SHA-256 | `e3a90df645eba0bb11eb642190dea5dda9928394cf4aa7880c7a552d815d4958` |

trace ONの独立確認でも、baselineとcandidateのbehavior artifactはbyte単位で一致しました。

- behavior artifact SHA-256: `6984f19d1810cbb111a8e0b8699842ca906f48dc51a5292f71f2190dfa31bfa0`
- `behavior_sha256`: `ab47124978270d4c8c506a773e0c383352dd7f8ecfa7e3a27b6c6613c655b5ee`
- event total: `173498680`
- event trace SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- event domains: 9
- baseline/candidate behavior artifact: byte-identical

## 性能A/B

trace/proof OFF、CPU 0固定、warmup除外、10回のpaired sequential tasksetで測定しました。

| 系列 | 平均 (s) | 中央値 (s) | SD (s) | 95% CI (s) |
|---|---:|---:|---:|---:|
| baseline | 25.849 | 25.980 | 0.523609 | [25.474433, 26.223567] |
| OPT4-D candidate | 26.035 | 26.055 | 0.948780 | [25.356284, 26.713716] |

paired diff（baseline − candidate）:

- 平均: `-0.186 s`
- 中央値: `0.230 s`
- SD: `0.963849 s`
- 95% CI: `[-0.875496, 0.503496] s`
- 中央値改善率: `-0.288684%`
- 平均改善率: `-0.719564%`

95% CIは0を含み、正の改善は確認できませんでした。したがって採用条件を満たしません。

## 最終処置

- exactness: **合格**
- 性能: **正の改善未確認**
- promotion: **なし**
- micro-opt bank: **追加なし**
- promoted backend、target registry、versioned validation: **変更なし**

OPT4全体の採否規則は[`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md)を参照してください。
