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

trace/proof OFFの正式PicoTetris workloadを、`--psram --keyboard --sd --sd-format fat32`
付きで実行し、baselineとcandidateのreportは一致しました。使用BINはR5の正式artifact
（SHA-256 prefix `0784d80d`）です。

| 項目 | 値 |
|---|---|
| formal candidate report SHA-256 | `eeb68c32c479b8c18ce1211297dbed8dbd1ed0c47e29f743297be96b9bdcd976` |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer SHA-256 | `e3a90df645eba0bb11eb642190dea5dda9928394cf4aa7880c7a552d815d4958` |

trace ONの独立確認でも、baselineとcandidateのbehavior artifactはbyte単位で一致しました。

- behavior artifact SHA-256: `26ad7d06fd3de19c163070b6251669799d453d2e062a5f8fa64cda6013f36b4b`
- `behavior_sha256`: `20fb8f8683345c7e2deef1c2a6b981fad48637fcfcd7b196e5e21945703d1e10`
- event total: `173498680`
- event trace SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- event domains: 9
- baseline/candidate behavior artifact: byte-identical

## 性能A/B

trace/proof OFF、CPU 0固定、warmup除外、10回のpaired sequential tasksetで測定しました。
各runは正式PicoTetris targetと同じ `--psram --keyboard --sd --sd-format fat32` 条件です。
測定値の分散が大きく、候補の正の改善を識別できる状態ではありませんでした。

| 系列 | 平均 (s) | 中央値 (s) | SD (s) | 95% CI (s) |
|---|---:|---:|---:|---:|
| baseline | 43.045 | 50.585 | 12.360959 | [34.202502, 51.887498] |
| OPT4-D candidate | 41.893 | 50.510 | 13.619496 | [32.150200, 51.635800] |

paired diff（baseline − candidate）:

- 平均: `1.152 s`
- 中央値: `0.2 s`
- SD: `3.328913 s`
- 95% CI: `[-1.229361, 3.533361] s`
- 中央値改善率: `+0.148265%`
- 平均改善率: `+2.676269%`

95% CIは0を含み、分散も大きいため、正の改善は確認できませんでした。中央値の差も
`+0.148265%`に留まり、採用条件を満たしません。10-run A/Bの全reportは次のSHAで
byte-identicalでした。

- A/B report SHA-256（10/10共通）: `290603e7633012cd5e588a46f5680e032d0844bf92df0de49d5a833666522e62`

trace ONのbehavior証拠は、上記のtrace OFF exactnessとは別採取です。

## 最終処置

- exactness: **合格**
- 性能: **正の改善未確認**
- promotion: **なし**
- micro-opt bank: **追加なし**
- promoted backend、target registry、versioned validation: **変更なし**

OPT4全体の採否規則は[`OPT4_MICRO_OPT_PLAN.md`](../../OPT4_MICRO_OPT_PLAN.md)を参照してください。
