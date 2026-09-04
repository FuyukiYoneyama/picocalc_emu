# 全体性能checkpoint（高速化開始原点の確定・G7候補停止記録）

## 目的

G7（preview境界／bounded transport：実アプリpreview接続）候補を次の統合段階へ進める前に、
高速出発点からPicoCalcエミュレーター全体の速度が退行していないかを確認した。対象は局所的な
preview機能ではなく、同じTetris（軽ゲーム実装）正式scenarioの全体実行である。

この記録の高速出発点runを、R0（高速出発点と退行比較点の固定）で使う**高速化開始原点**として一旦確定する。
この記録は同時にR2（Recovery 2：高速地点からの段階再構築）の停止gateであり、G7の機能正確性passを
性能passへ読み替えない。性能結果によりG7候補は次段階へ進めず、計画は重大退行地点で停止する。

## 固定条件

- firmware: `PicoTetris.bin`, SHA-256 `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario: `picocalc_emu/scenarios/tetris-line-clear.json`, SHA-256 `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- board: `picocalc`
- LCD variant: `pio-rgb565`
- PSRAM／keyboard／SD: 有効、SD format `fat32`
- execution model: `Serial`
- step quantum: `1`（PSRAM接続により固定）
- host CPU affinity: vCPU `11`
- cycle budget: `1,000,000,000`
- successful stop: `scenario_done`
- virtual elapsed: `3.715000` seconds
- timing scope: `picocalc-harness::run_loop`
- timing source: `CLOCK_PROCESS_CPUTIME_ID` と同じrun-loop境界の`Instant`

計測値は、次の式で計算した。

`real_time_percent = emulated_seconds / emulation_wall_seconds * 100`

CPU時間も同じrun-loop境界で記録した。G7側のtiming runnerには比較専用sidecarを追加したため、
`backend_build.dirty=true`である。これはG7 production sourceがdirtyだったという意味ではなく、
計測器を一時的に追加したという意味である。sidecar差分は[`g7-timing-harness.patch`](g7-timing-harness.patch)、
実行binaryは[`g0-timing-runner`](g0-timing-runner)と[`g7-timing-runner`](g7-timing-runner)に保存した。

## 結果

| 地点 | backend | cycles | process CPU秒 | wall秒 | real-time比率 | 判定 |
|---|---|---:|---:|---:|---:|---|
| R0高速化開始原点`T_fast` | `e985a9d7ecb51ef760506a105edd34e31cf9b5f1` | 927,528,660 | 27.064558677 | 25.969372348 | **14.305313006%** | **開始原点として確定** |
| 現行G7候補`T_regressed` | `9db10c0313547e9463510ffe3ae6d7474e008494` | 927,528,659 | 167.759749206 | 160.262119737 | **2.318077413%** | **重大退行・失敗** |

G7候補は高速出発点よりprocess CPU時間で`6.198503039`倍遅く、real-time比率は14.0%の最低維持値を
満たさない。10.0%の重大退行赤旗も下回る。既知のguest cycle差は1 cycleだけであり、この速度差の
説明にはならない。両runともTetris scenarioのguest-visible判定はpassしたため、今回検出したのは
正確性失敗ではなく、全体性能の退行である。

## 停止判断

- `R_fast >= 14.0%`: **成立**（14.305313006%）。このrunを今回の高速化開始原点として固定する。
- `R_candidate >= 14.0%`: **不成立**（2.318077413%）。
- `R_candidate < 10.0%`: **成立**。予見済みdeltaによる暫定受入の対象にもできない。
- よって、G7候補を通常合格、性能改善、統合可能、1倍速、またはLOAD-0（最大級の継続負荷性能テスト0番）
  完走とは記録しない。R4（Recovery 4：現行mainへの統合可能性確認）は開始しない。

## 成果物

- [`g0-host-timing.json`](g0-host-timing.json)
- [`g7-host-timing.json`](g7-host-timing.json)
- [`g0-report.json`](g0-report.json)
- [`g7-report.json`](g7-report.json)
- [`g0-uart.raw`](g0-uart.raw)
- [`g7-uart.raw`](g7-uart.raw)
- [`g7-timing-harness.patch`](g7-timing-harness.patch)

両runのUART SHA-256は`bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`で一致した。
個別SHA-256は親recordの`SHA256SUMS`に固定する。
