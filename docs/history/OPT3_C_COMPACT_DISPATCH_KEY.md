# OPT3-C compact predecoded dispatch key

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


## 結論

OPT3-Cは正確性gateに合格したが、性能gateの5%閾値に届かず不採用・revertとなった。
wall中央値はbaseline 26.72秒からcandidate 25.61秒へ4.1541916168%改善したが、10-run promotion測定は行っていない。
active target、validation attestation、production optimizationは変更していない。

## 試作境界

- feature: `compact-dispatch-key-prototype`
- `DecodedOp`の12 bytesを維持し、flags bits 1..6を使用
- successor copy、staging、clearなし
- Serial core 0限定、scheduler quantum 1命令
- baseline `e58e67f...648`、candidate `3819a9d...ec3`、revert `04b2eb2...290`

## exactness

85/85、`scenario_done`、927,528,660 cycles、3,715,000 virtual usを維持した。
UART SHA `bff1f245...e9266c`、framebuffer SHA `f63b598f...54e4a2`、PSRAM tick 305,747,113、
behavior SHA `79dedc15...e2dfc8`、173,498,680 events、全9 domain digestがOPT1-Bと一致した。

## 性能gate

trace/proof OFFのclean A/B/A/B/A/Bで、baselineは`27.18/26.26/26.72 s`、candidateは
`25.31/25.61/25.77 s`。pair改善率は`6.8800588668% / 2.4752475248% / 3.5553892216%`、
中央値改善率は`4.1541916168%`で、要求値5%未達のため棄却した。

完全な証拠は[`opt3-c-compact-dispatch-key-20260809-01`](../../firmware-validation/records/opt3-c-compact-dispatch-key-20260809-01/)
に固定する。revert HEAD `04b2eb2fb26f126e848b5c041177324954a98290`に対するbackend CI run
`31299159125`はfmt、test、Clippyの全jobに成功した。
