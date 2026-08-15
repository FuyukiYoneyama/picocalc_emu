# OPT4-C: 8-byte `DecodedOp` 試作・検収記録

更新日: 2026-08-15

## 判定

**exactness は合格、性能改善は不採用。promotion と micro-opt bank への採用は行わない。**

試作は `picoem-picocalc` の実装commit [`77590e8`](https://github.com/FuyukiYoneyama/picoem-picocalc/commit/77590e8) を、独立feature
`decoded-op-8byte-prototype` で有効化したものです。default buildとpromoted targetのpinは変更していません。

## 実装範囲

`DecodedOp` の実験レイアウトは、従来の12 bytesから8 bytesへ縮小しました。

- `tag_flags: u32` にPC上位18 bits、wide flag、valid bitを格納
- direct-mapped cache slotからPC下位bitsを復元
- empty/fault entryはvalid bitを持たず、fault時のwide分類だけを保持
- cache lookup、populate、fault、region invalidation、wide dispatchを同一表現で処理
- 静的サイズassert（feature時8 bytes、default時12 bytes）と境界unit testを追加

## exactness

正式PicoTetris workloadを、元のpromoted baselineとcandidateで比較しました。以下はcandidate側の固定値です。

| 項目 | 値 |
|---|---:|
| cycles | `927528660` |
| elapsed_us | `3715000` |
| scenario | 85/85 |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer RGB565 SHA-256 | `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2` |

cycle、virtual time、timeline、UART、framebuffer、PSRAM、scenario、report、behaviorおよび全event domainを照合し、**reportはbyte単位で一致**しました。

trace ONの独立確認でも、baselineとcandidateのbehavior artifactはbyte単位で一致しました。

- behavior artifact SHA-256: `93b9d9d205f99b3a2e54bb79dd89edbb883934e1ebe8553eaea1d6c75178dfcc`
- `behavior_sha256`: `29457d2b880764ec06a2f9b97ae1b27dcd99ae51ff06a58983e522868e3c2162`
- event trace count: `173498680`
- event trace SHA-256: `2ead20411384942ea71eb1c00cd92951ff52361c9e81ba095d7f88304364a789`
- event domains: 9

## 性能A/B

trace/proofを無効化し、同一環境で10回交互実行しました。

| 系列 | 平均 (s) | 中央値 (s) | 95% CI (s) | 最小–最大 (s) |
|---|---:|---:|---:|---:|
| baseline | 27.150 | 26.710 | [26.292884, 28.007116] | 25.96–29.70 |
| OPT4-C candidate | 27.503 | 27.220 | [26.775826, 28.230174] | 26.22–29.56 |

paired diff（baseline − candidate）は次のとおりです。

- 平均: `-0.353 s`
- 95% CI: `[-0.963969, 0.257969] s`
- 中央値改善率: `-1.9094%`
- 平均改善率: `-1.3002%`

CIは0を含み、中央値はcandidate側の退行でした。したがって「正確で、再現性のある正の改善」というOPT4採否条件を満たしません。

## 最終処置

- exactness: **合格**
- 性能: **改善未確認／中央値退行**
- promotion: **なし**
- micro-opt bank: **追加なし**
- promoted backend、target registry、versioned validation: **変更なし**

この記録は試作の証拠であり、featureをdefaultへ昇格する根拠ではありません。OPT4の採否規則は[`OPT4_MICRO_OPT_PLAN.md`](OPT4_MICRO_OPT_PLAN.md)を参照してください。
