# OPT4-B NVIC bitmap pending scan

> **現行の実験記録。** この候補は正確性を通過したが、速度改善を統計的に確認できなかった。
> promoted backend、target registry、既存の性能基準は変更していない。

## 判定

**exactness pass／速度改善未確認／promotionなし**とする。

pending-and-enabled bitmapのset bitだけを`trailing_zeros`で昇順に走査する実装は、既存の
priority選択と同じ結果を返した。しかしPicoTetrisの10回交互A/Bでは、中央値の差が0.0484%
に留まり、対応差の95% CIが0を含んだ。したがって、この候補をproductionまたはmicro-opt bankへ
昇格しない。

## 変更

- 実装commit: `886494f1c259ae99c73b01f1ccfa88f53535067f`
- feature: `nvic-bitmap-scan-prototype`
- 対象: `Nvic::highest_priority_pending`
- default build: 従来の32本走査を維持
- candidate build: `pending & enabled`のset bitだけを昇順走査

候補経路はlowest IRQから訪問するため、同一priorityでは従来どおりlowest IRQが勝つ。priorityが
異なる場合も、最小priorityを保持する比較は従来と同じである。feature forwardingは
`picocalc-harness`にも追加したが、runnerの既定経路では有効化していない。

## ローカル検証

feature有効化時の`rp2040-emu`はunit 1245件、firmware 9件、multicore 9件、PSRAM 4件、smoke 6件、
WFE/IRQ 5件、`picocalc-harness`は65件が合格した。featureなしの既定経路もrp2040-emu unit 1244件と
同じintegration test群が合格した。

NVICの疎なbitmap、priority winner、同一priority tie-breakを追加unit testで確認した。

## PicoTetris exactness

正式基準のsourceを汚さないため、OPT1-B由来の隔離checkoutへ候補だけを適用した。featureなし／ありの
runnerを同じcommit `023fdf0fb76fc058fb3b567b23daf94e882a63a2` からrelease buildし、同じBINとscenarioを
実行した。

- BIN SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- cycles: `927528660`
- elapsed_us: `3715000`
- stop: `scenario_done`
- scenario: 85/85 pass
- UART SHA-256: `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`
- snapshot PNG SHA-256: `e3a90df645eba0bb11eb642190dea5dda9928394cf4aa7880c7a552d815d4958`
- report SHA-256: `41d4d2d429a7417de6ba23be81acc60535ff697d54751254a910ce81b268648f`

featureなし／ありのreport、UART、snapshotはbyte-identicalだった。trace/proofは速度測定では無効にし、
exactnessは構造化reportとartifact hashで確認した。

## 10回交互A/B

WSL2、logical CPU 0固定、release、同一BIN/scenario、warmup各1回を除外して逐次測定した。

| 統計量 | featureなし | bitmap候補 |
|---|---:|---:|
| n | 10 | 10 |
| mean wall (s) | 27.364563 | 26.903024 |
| median wall (s) | 26.778430 | 26.765461 |
| mean 95% CI (s) | [26.583857, 28.145269] | [26.260582, 27.545467] |
| min–max (s) | 26.377109–29.310533 | 25.931930–28.470201 |

中央値改善は **0.048429%**、平均改善は1.686630%だった。ただし同一組のwall差
（featureなし−候補）の平均95% CIは **[−0.331772, 1.254849]秒**で0を含む。候補が速いという主張を
再現可能な改善として採用するには証拠が不足している。

## 処置

このcommitとfeatureは、後続候補との比較用に保持するが、default build、promoted target、
capability、versioned validationへは混入させない。OPT4-C（`DecodedOp` 8-byte化）は、OPT4-Aとの
bank全体評価で必要性を再確認してから着手する。
