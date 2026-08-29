# 対話型 Validated Preview GUI

firmware backendでPASSした同一BINを画面・キー・UARTで対話的に確認するための
薄型frontendです。エミュレーターをGUIへ再実装せず、`preview`が生成したadmitted
descriptorに記録されたrunnerをそのまま子processとして起動します。これはfirmware
validation、実機相関、または1倍速度保証の代替ではありません。

## 起動

まず、既存のfirmware validationでreceiptを作成し、descriptorをadmitします。
詳細は[`TESTING.md`](TESTING.md)と
[`../docs/validated-realtime-preview/VRP3_GUI_20260829.md`](../docs/validated-realtime-preview/VRP3_GUI_20260829.md)
を参照してください。

```sh
python3 tools/picocalc.py preview \
  --firmware /absolute/path/to/app.bin \
  --receipt /absolute/path/to/validation-receipt.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --descriptor-out /absolute/path/to/admitted-descriptor.json

python3 tools/picocalc.py preview-gui \
  --descriptor /absolute/path/to/admitted-descriptor.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --audio on \
  --audio-host-rate 48000 \
  --audio-queue-blocks 8
```

WSLgではPicoCalc本体スキン windowと、PicoCalc UART0 console windowが同時に開きます。
skinを使わずLCDだけを見る場合は`--skin none --scale 2`を追加します。UART consoleは
hostの標準入出力ではなく、エミュレートされたUART0 TX/RX wireです。text入力はUTF-8、
`raw hex`は`00 ff 41`のようなbyte列として送信します。

`preview-gui`の音声monitorは任意のhost presentationです。`--audio on`（既定）はPCRPの
bounded PCM blockを利用可能な`ffplay`へ送ります。`--audio off`はhost再生だけを無効にし、
emulated PWM/DMA、virtual cycle、UART、framebuffer、validation digestを変えません。
`--audio-host-rate`はmonitor側の出力rate、`--audio-queue-blocks`はhost側のbounded queue容量です。
いずれもdescriptorやrunner contractには入りません。`ffplay`が無い場合は`timing-only`、
player終了・queue満杯・IPC/ingress dropは`degraded`として表示されます。これはemulatorの
PASS/FAILや実機スピーカー品質の判定ではありません。

## キーと状態

- 通常キー、Enter、Space、Tab、BackspaceはPicoCalc keyboardへ送られます。
- 最初の押下は`down`、押下中は120 ms間隔の`held`、離すと`up`です。
- OSのauto-repeatによる重複`down`は抑止します。
- UART consoleの入力欄にフォーカスがある間は、文字キーをPicoCalc keyboardへ奪わず、入力欄へ入力できます。
- F5はheld keyを解放してからpreview reset、Ctrl+Rはdescriptorの再admission後reload、F12はscreenshot、Escはquitです。
  Escは予約キーなのでゲストへEscapeを送る用途には使いません。

F5ではsticky `UX INVALID`表示を消しません。Ctrl+RがBIN、runner、backend、registry、
validation record、launch contractを再検証して成功した場合だけ、sticky stateをclearします。
改変・欠落時は`VALIDATION LOST — RELOAD REFUSED`を表示し、mutableな代替argvでは起動しません。

## 表示と制約

status lineにはadmitted validation receipt identity、target/revision、backend/BIN pin、
`hardware not_claimed` banner、virtual cycle、実測pacer ratio、timing lag/behind、coverage、
audioのsource/host rate・resampling・queue・underrun/overrun、backend/IPC/ingress/hostのdrop、
`stream_epoch`、UART TX/RX accepted・overrun・disabled・error counter、presentation frame drop、
skin状態を表示します。旧`audio=not_streamed`はauthoritativeなemulated audio digestの状態であり、
host PCM再生済みを意味しません。host monitorの状態は別の`audio_monitor`（`off`／`inactive`／
`streaming`／`timing-only`／`degraded`）で表示されます。skinの合成とscreenshotはpresentation専用で、
raw framebuffer・cycle・UART・device event・validation digestを変更しません。詳細は
[`VRP4_AUDIO_MONITOR_20260829.md`](../docs/validated-realtime-preview/VRP4_AUDIO_MONITOR_20260829.md)を参照してください。

自動化された契約テストは次で実行します（CI不要です）。

```sh
python3 -m unittest -q tests.test_preview_gui
```

WSLgの短時間起動確認は次です。

```sh
python3 tools/picocalc.py preview-gui \
  --descriptor /absolute/path/to/admitted-descriptor.json \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --smoke-seconds 2
```
