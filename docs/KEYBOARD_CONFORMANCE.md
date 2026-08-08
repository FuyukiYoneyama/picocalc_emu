# 公式keyboard firmware conformance

## 一次リファレンスと固定点

protocol producerの一次リファレンスはClockworkPi公式
[`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)
です。ローカルでは`/home/fuyuki/pico_dvl/codex/PicoCalc/Code/picocalc_keyboard`にあります。
RP2040側のBSPやアプリはconsumer実装の証拠であり、producerの仕様を上書きしません。

conformance実装時の公式checkoutは`a61c1f2f18185b32a667dde5c9393ced9ddd19ca`、
keyboard subtreeは`8584a4755ee85d2e49b3ef1f27276c6184c88970`です。このsubtreeは
`reference-projects/catalog.json`で固定済みのcommit
`553da6f2408963b956779599d179d77fd611a4d7`と同一です。対象ファイルのSHA-256は同台帳を
規範値とし、`picocalc.py verify`で検査します。

## R1で固定した契約

backend commit `d54ee24d816d4595f2ee750f25ccd7e44f103a22`で次を実装・試験しました。

- I2C 7-bit address `0x1f`、register `0x01`から`0x0e`の公式reply
- firmware version `0x16`、key countの31件maskとCaps/Num flag
- `[state,key]`のFIFO pop、Idle/Pressed/Held/Releasedのstate値
- 31-event FIFO、既定の到着event drop、内部`CFG_OVERFLOW_ON`時のoldest overwrite、overflow latch
- LCD backlightの16刻みとkeyboard backlightの32刻み、battery、reset、power-off
- C64 matrix 10-byte replyとjoystick reply
- 7×8 matrixと12 direct buttonの公式keymap、modifier code `0xa1`から`0xa5`
- Shift/Caps/Alt/Num変換、Alt+I、backlight shortcut、repeat対象key
- hold `>300 ms`、repeat `>100 ms`というstrict boundary
- STOPを挟むselect/readとrepeated STARTの両方、requestごとのreply先頭からの再送

公式firmware内のCFG既定値は`0xd2`ですが、現行`receiveEvent()`にはCFG/INT/DEB/FRQのcaseが
ありません。このためモデルもこれらをI2Cで読み書き可能にはせず、zero replyまたはunsupported
writeとして扱います。テスト用の内部CFG setterだけがoverwrite policyを切り替えます。

既存scenarioの`key`操作と`--keys`は論理keycodeのFIFO注入です。これを物理matrix処理へ暗黙に
切り替えると、従来`A`を投入したscenarioが公式のunshifted変換で`a`になり互換性を壊します。
そこで論理注入は維持し、物理matrix/button transitionは別のconformance APIに分離しました。

公式controllerはCtrl reportを`0xa5`と定義します。古い`picocalc_helloworld` consumerには
`0x7e`をCtrlとして扱う箇所がありますが、producer一次の原則に従ってモデルは`0xa5`を採用し、
全5 modifier codeを試験します。またSymbol `0xa4`はfirmwareに分岐とcode定義がある一方、
現行matrix/button tableには`MOD_SYM` entryがないため、宣言上は存在しても物理入力からは
到達不能です。conformance APIではこの宣言済みtransition自体を試験可能にしています。

## runnerの判定

keyboard reportにはdrop/overwrite、内部config/interrupt、lock、両backlight、unknown select/writeを
出します。unknown register selectまたはunsupported register writeが1件でもあれば
`keyboard_protocol_error`でfailします。ACK後に無言で捨てられたwriteをPassにすることはありません。

## 意図的に残す境界

R1はRP2040 consumerから観測できるproducer契約を固定します。STM32のGPIO電気走査、debounce、
16 ms poll scheduler、10-key physical tracking、PMU IRQ、battery sampling、電源key・低電圧shutdownの
実時間lifecycleは実行していません。物理mapとstate変換は純粋なtransition APIで検証し、scenarioの
仮想時計に結合する作業が必要になった場合は、論理注入とは別schemaで追加します。またI2C bus速度、
NACK、timeout、short transferの故障注入も今回のproducer register conformance外です。

R5相関firmwareの67キー診断は、このR1 producer conformance全体を実機で再試験するものでは
ありません。R5のscenarioはraw FIFO eventを投入し、実機recordは全物理キーのpress/release
到達性を確認しますが、診断appはstatus registerのCaps bitを利用しません。そのためCaps toggle、
後続英字の大小文字変換、開始・終了時のCaps状態はR5の合格主張に含めません。R5 artifact固有の
必須操作条件と既知の表示上の制約は[`R5_HARDWARE_CORRELATION.md`](R5_HARDWARE_CORRELATION.md)
を参照してください。
