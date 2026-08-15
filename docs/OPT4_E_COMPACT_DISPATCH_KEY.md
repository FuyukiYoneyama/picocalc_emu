# OPT4-E: compact dispatch key 試作・検収記録

更新日: 2026-08-15

## 判定

**exactness は合格。性能は正式な10-runシナリオA/Bを完了できず、正の改善信号なし。promotion／micro-opt bank追加は行わない。**

実装は `picoem-picocalc` の [`5181736c`](https://github.com/FuyukiYoneyama/picoem-picocalc/commit/5181736c4b65df7b3436f809e95bc2209b1e7125) で、feature
`compact-dispatch-key-prototype` として実装されています。default pathは変更せず、既存の
12-byte `DecodedOp` flags領域へdispatch keyを格納します。OPT4-Cの8-byte representation
との併用はcompile errorで明示的に拒否しています。

## exactness

正式PicoTetris BIN（SHA-256 prefix `0784d80d`）を、`--psram --keyboard --sd --sd-format fat32`
付きで実行しました。candidateと同一sourceのdefault buildを比較対象とし、両方ともbackend
commit `5181736c`、working tree cleanです。

### trace/proof OFF

| 項目 | 値 |
|---|---|
| report SHA-256 | `026d7f6d7e74edb4f5f24412030c82d31ed88188d7c784403b4decbc94411eb1` |
| UART SHA-256 | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| framebuffer | candidate/default byte-identical |

### trace/proof ON

- behavior artifact SHA-256: `160d5c0ba5da31d148d05c1c59b166b88fe821f8bca6f88abe8bb45d039bed96`
- report SHA-256: `026d7f6d7e74edb4f5f24412030c82d31ed88188d7c784403b4decbc94411eb1`
- behavior JSON: candidate/default byte-identical
- behavior projection event total: `173495620`
- event trace SHA-256: `a06475c13e220d1761cd2fbaa391b768624a0002619aa5f8052ad1f380a5b32d`

exactness gateは合格です。

## 性能スクリーニング

正式シナリオの単発測定は、host runtimeが通常の約6〜10倍に悪化していました。
default `186.41 s`、candidate `179.31 s`でしたが、この環境ではノイズが支配的であり、
正式な性能A/B結果として扱いません。正式シナリオの10-run A/Bは未完了です。

同じBIN／board／PSRAM／keyboard／SD条件で、scenarioを使わない100M-cycle短縮screeningを
10-run実施しました。

| 系列 | 測定値 (s) | 中央値 (s) |
|---|---|---:|
| default | 1.66, 1.70, 1.70, 1.66, 1.68, 1.65, 1.63, 1.64, 1.68, 1.70 | 1.670 |
| candidate | 1.64, 1.64, 1.75, 1.65, 1.63, 1.69, 1.69, 1.67, 1.68, 1.69 | 1.675 |

- 中央値改善率: `-0.299401%`
- 平均改善率: `-0.179641%`
- paired diff（default − candidate）平均: `-0.003 s`
- paired diff中央値: `+0.005 s`
- paired diff 95% CI: `[-0.032408, +0.026408] s`
- 10-run report SHA-256（全run共通）: prefix `8a7482b6`（提供された記録はprefixのみ）

短縮screeningにも正の性能信号はありません。正式シナリオA/Bが未完了であるため、性能合格とは
記録しません。

## 最終処置

- exactness: **合格**
- 性能: **正式10-runシナリオA/B未完了／短縮screeningで正の信号なし**
- promotion: **なし**
- micro-opt bank: **追加なし**
- promoted backend、target registry、versioned validation: **変更なし**

OPT4-Eは、旧OPT3-Cのdispatch分類を現行mainへ安全に移植できることを確認した試作として
記録します。性能採用判断は、環境が安定したうえで正式シナリオA/Bを再測定するまで保留ではなく、
今回の候補については不採用とします。
