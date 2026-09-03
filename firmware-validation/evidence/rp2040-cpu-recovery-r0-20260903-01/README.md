# R0（高速出発点と退行比較点の固定）診断記録

この記録は、約14%で動作していたTetris（軽ゲーム実装）を復旧再構築の出発点へ固定するための
診断資料である。これは新しいproduction target、性能qualification、P1-Aの採用根拠ではない。

## 状態

**R0 complete。** 旧高速地点のprocess CPU測定、現行退行地点のP1-Aなし測定、短い固定guest-cycle
probeを一時worktreeからアーカイブした。保存したraw runは既存の一時診断結果を移動したもので、
同じ長時間測定を追加していない。必要機能の棚卸しR1も完了し、e985のクリーンbackend testと
PicoEdit（テキスト編集実装）のsourceを変更しないクリーンbuildをG0として確認した。次はG1（CPU・
multicore・割込み正確性）の最小移植であり、production sourceは現行backend `main`へまだ適用していない。

## 比較対象

| 対象 | backend | featureの扱い | process CPU時間 | guest cycles |
|---|---|---|---:|---:|
| 高速出発点 | `e985a9d7ecb51ef760506a105edd34e31cf9b5f1` | 旧promoted runtime。host timing sidecarのみ一時適用 | 中央値25.606484192秒（3 run） | 927,528,660 |
| 現行退行点 | `f32eba1878aeabc6dfc8954b363230ef1e4c2b52` | P1-Aなし、`sd-gen1-multiblock`のみ明示有効 | 190.172394647秒（1 run） | 927,528,659 |

同じfirmware／scenarioに対するhost計算コストは約7.4倍異なる。旧地点のsidecarは計測区間を
`picocalc-harness::run_loop`へ限定し、現行地点は同じscopeを使用した。旧地点と現行地点の
`backend_build.dirty=true`は、前者がhost timing patch、後者がP1-Aを本当に無効にするための
dependency feature設定を一時適用したことを示す。いずれもproduction repositoryの変更ではない。

## 短probe

scenarioなしの100,000,000-cycle probeでは、旧地点0.968871112 CPU秒、現行退行点2.162936577 CPU秒
（約2.23倍）だった。最初の3配置だけを含む7-step短縮scenarioでは、旧地点4.641699414 CPU秒、
現行退行点19.648377229 CPU秒（約4.23倍）だった。両probeとも`cycle_limit`または`scenario_done`で
正常終了し、UARTとscenario判定はpassした。最初のprobeだけで正式scenario全体の倍率を推定せず、
段階screeningの「fast／slowを分離する短い検査」として使用する。

## 固定入力

- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- current contract SHA-256: `1a296b1faa9088e22f9939bc61b3963475af7005343038361cf1db4ddcb28a5f`
- board: `picocalc`
- execution model: `Serial`
- CPU affinity: logical CPU 11
- full scenario stop: `scenario_done`

旧高速地点のhost timing patchは`host-timing-sidecar.patch`、P1-Aなしbuildのfeature設定は
`p1a-off-feature-config.patch`、その有効feature treeは`p1a-off-feature-tree.txt`に保存した。
両patchは復旧candidateへ移植しない。

## 次の作業

R0完了後に、必要機能の棚卸し（G1〜G7）へ進む。再構築laneでは、移植する機能を一群ずつ選び、
短probeで性能と既存testで正確性を確認する。必要性を説明できない機能は持ち帰らない。
