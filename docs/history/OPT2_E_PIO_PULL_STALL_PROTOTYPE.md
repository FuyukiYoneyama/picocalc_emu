# OPT2-E PIO exact pull-stall bulk prototype

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


## 結論

限定したPIO bulk advanceは正確性を満たしたが、性能採用基準を満たさなかったため
**不採用・revert済み**である。OPT2全体は継続する。

候補は、全enabled SMが空TX FIFOに対する`PULL`で停止している場合だけ、divider phaseと
stall診断値を閉形式で更新した。CPU/DMAが介入できない同一`step_n_with_pins(n)`内では、
この停止は自律的に解除されず、命令、pin、FIFO、DREQ、IRQイベントも発生しない。
それ以外は従来の1 tick経路へfallbackした。

## 正確性

clean candidate `a7ac9020b9861c1c4803187b7092512b65f60835`で、PicoTetris回帰は
927,528,660 cycle、85/85 stepを完走した。UART、framebuffer、behavior SHA、streaming
event SHA、全9 domainのcount/hash、PSRAM tickはOPT1-Bと完全一致した。

## 実測

実workloadで候補が受理したのは371,982,564 call、371,982,564 system cycle、
185,895,678 PIO tickだった。すなわち**全callが1 cycle**である。現在のrunnerはPIO tickの
直後にpin/device観測を行うため、PIO内部のbulk処理に複数cycleを渡せなかった。

trace-OFF、CPU 0固定、warm-up除外、交互3 pairのscreening結果は次の通りである。

| variant | wall中央値 |
|---|---:|
| baseline | 25.70秒 |
| candidate | 25.64秒 |

改善は0.233463%であり、採用基準5%を下回った。候補は
`a7939e5`でrevertした。active targetとpinは変更していない。

## 次の判断

PIO状態そのものの静止証明は成立した。次にPIOで大きな利得を得るには、constant-pinが続く
区間についてPSRAM/LCD側の反復観測をexactにbulk accountingできる契約を先に設計し、同じ
静止条件で外側の`tick_pio + update_gpio`ループをまとめる必要がある。これは今回の小規模
試作より広い変更なので別候補とする。独立候補ではUART deadline promotion、CPU側ではOPT3の
block/decode cacheが残る。

証拠は
[`opt2-e-pio-pull-stall-20260809-01`](../../firmware-validation/records/opt2-e-pio-pull-stall-20260809-01/notes.md)
に固定する。
