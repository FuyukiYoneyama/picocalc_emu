# PERF-Q0（dynamic quantumの機会量・途中遷移安全性）

この記録は、PicoCalc firmware emulatorの待ち時間を短縮する候補を、実アプリの正確性を壊さずに実装できるか確認したものです。1倍速の達成度、現在のエミュレーターの総合性能、LOAD-0の完走時間を測る記録ではありません。

## 結論

- Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）は、step開始時の保守的分類で20%未満にならず、dynamic quantumを調査する機会は棄却しませんでした。
- ただし、step開始時の状態だけを見てquantumを広げる方式は棄却です。CPUが同じstepの途中でPIOを有効化すると、q1参照とq16候補は同じ17 guest cyclesまで進んでもGPIO出力が一致しませんでした。
- したがって次のproduction候補には、意味を持つMMIO／GPIO write直後のtransition barrierと、期限を越えないdeadline capが必要です。まだ実装していません。
- PIO、DMA、SysTickなどの未解決期限はq1へfallbackします。TIMER、PWM、外部scenario境界は既存horizonを利用しますが、running candidateで外部境界を越えないcapを別途明示します。

## 実アプリの観測

`disengaged_percent_upper_bound`は、quantum=1でstep開始時に周辺装置が観測中でなかったcycleの割合です。transition barrierとdeadline capを入れると実際にまとめられる割合はこれ以下になります。高速化率ではありません。

| アプリ | guest cycles | scenario | disengaged上限 | 結果 |
|---|---:|---:|---:|---|
| Tetris（軽ゲーム実装） | 927,528,659 | 85/85 pass | 64.9121% | 機会を棄却しない |
| PicoEdit（テキスト編集実装） | 827,799,818 | 11/11 pass | 76.1119% | 機会を棄却しない |

両runのUART、framebuffer、device observation、stop reasonはraw reportに保存しています。`report.json`のbackend commitはQ0診断runnerのscratch commitであり、既存targetのaccepted pinを書き換えたものではありません。

## 途中遷移fixture

fixtureは、CPUがPIO0 SM0を有効化するThumb-16 MMIO writeを実行する最小プログラムです。開始時はPIO idleですが、q16ではCPU batchが終わるまでPIO schedulerに見えません。q1とq16を同じ17 guest cyclesで比較し、両方でSM0は有効になる一方、交互に`SET PINS`するPIO programのGPIO0が異なることを確認しました。

再現コマンド:

```text
cargo test --locked -p rp2040-emu --test q0_mid_quantum_transition
```

保存したfixture sourceは`fixture/q0_mid_quantum_transition.rs`です。これはbackendのproduction treeへ追加したtestではありません。

## deadline確認

現行コードの確認結果は次の通りです。

- `step_serial_with_external`はCPU stepをquantum targetまで進めた後にperipheral／PIO処理を行うため、途中のCPU MMIO遷移をstep開始時のpredicateから予測できません。
- `idle_event_horizon_internal`はTIMER armed alarm、PWM wrap、caller-owned external boundaryを候補期限として扱います。
- PIO、DMA、SysTick、UART、SPI、I2C、ADCなどは一周期fallbackです。安全性を証明できるexact deadlineがないためです。
- 通常のrunning candidateは、scenarioの外部入力境界を`step_until`のblocked経路だけに任せず、候補自身のquantum capとして扱う必要があります。

## 範囲外

このQ0でproduction backend、formal target registry、release表記、外部プロジェクトを変更していません。1倍qualification、LOAD-0の長時間再試験、全target回帰、PERF-Q1実装も開始していません。

詳細な数値、SHA-256、commit、source lineは同ディレクトリの`record.json`とraw JSON reportを正とします。
