# OPT2-C 限定exact running batching

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


**状態:** 完了、不採用・revert  
**candidate:** `picoem-picocalc` `815ef5daa5117c29a8a7505d5e5f1929d92d5b99`  
**revert:** `c44c87f1ed4235343c5fd18860fde47b64b54325`

OPT2-Bのpost-hoc gapをそのままsafe windowとみなさず、事前に完全証明できる最小subsetだけで
running batchを試した。core 1停止、pending IRQなし、完全な保守的event horizon、decode-cache
hit済みの逐次・bus-free・fault-free・1-cycle Thumb-16命令という条件をすべて満たす場合だけ、
最大64 cycleをまとめた。memory/MMIO、branch、system命令、cache miss、stop PC、外部event境界は
必ずreference pathへ戻した。

正確性は合格した。PicoTetrisは85/85、927,528,660 cycle、behavior SHA、173,498,680 event、
全9 domain、UART、framebuffer、PSRAM counterまでOPT1-Bと一致した。しかし実際に成立したのは
8,420 batch、23,176 cycle、14,756 dispatch省略、最大13 cycleで、全run cycleの0.002498%に
留まった。

Trace OFFの交互順3 paired screeningでは、baseline中央値51.38秒に対してcandidate 57.49秒で
11.89%遅かった。全pairが8.56〜11.89%退行し、5%改善基準から明確に外れたため、既存の
dispatcher-only候補と同じ早期停止規則で10 run promotion測定へ進めずrevertした。active target、
validation、R5/OPT1-B evidenceは変更していない。

結論は「exact batching全般が不可能」ではない。今回の厳しいCPU subsetでは対象massが小さすぎ、
事前証明costを回収できない、という限定された否定結果である。次はPIO/UART/DMA deadline promotion
とCPU/decode block workを別レバーとして測り、より大きい側から次候補を選ぶ。

完全な条件、trace artifact、性能値は
[`opt2-c-exact-batching-20260808-01`](../../firmware-validation/records/opt2-c-exact-batching-20260808-01/notes.md)
に固定した。
