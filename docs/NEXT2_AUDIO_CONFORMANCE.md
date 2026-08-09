# NEXT-2B Audio conformance

**状態:** v2実装前契約を凍結済み。application、backend、target、実機証拠はまだ未実装である。

正典は`next2-audio-v2-20260809`である。v1はapplication実装前レビューで、firmware UARTに
backendだけが観測できるtiming PASSを名乗らせていたため採用しない。v1を削除・書換えず、v2が
SHA付きでsupersedeした。v2はNEXT-2B audio（`picocalc-audio`）の事前凍結版であり、
Serial Quantum 1、公開 `picocalc::audio` API のみを許可する。

## 固定条件

- 契約ID: `next2-audio-v2-20260809`
- 実行モデル: `Serial`
- 実行量子: `1`
- API境界: `picocalc::audio` の公開APIのみ（privateヘッダやMMIO直アクセスは不可）
- ハードウェア制約: 追加ヒューマン入力不要

## 固定サンプル仕様

- フレーム数: `49152`（stereo、48 kHzで1.024秒）
- pattern period: `256` frameを192回。実機でも一度の再生を録音できる長さにする。
- 左チャネル: `left_duty = (i * 17 + 3) & 255`
- 右チャネル: `right_duty = 255 - ((i * 29 + 7) & 255)`
- PCM変換: `pcm = duty * 257 - 32768`（`i` は0始まり）
- メモリパッキング: little-endian `u32`（A=左チャネル低16bit、B=右チャネル高16bit）
- 期待SHA-256: `c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a`

このSHAはproducerが計算した値を信用するためのものではない。backendが、DMA engineから
`PWM5_CC`へ成功した32-bit bus writeだけを取得し、各wordをlittle-endian 4 byteとして逐次hashする。
CPUによる初期center-duty書込みや、producer ringの直接hashは含めない。

## DMA/タイミング設定（固定）

- Timer: `timer0`, `X=3`, `Y=15625`
- DMA `TREQ`: `59`
- Destination: PWM slice5 の `CC`
- 転送幅: `32-bit`
- Destination: fixed (`inc=0`)
- BSPの128-frame double bufferをDMA IRQで再armし、finite streamのdrainまで継続する。
- 受理するDMA-origin sample write数: `49152` exactly
- 1回目後のDMA timer due-cycle間隔: `5208`/`5209` のみ

backendのCPU実行はinstruction境界でperipheralをserviceするため、DMA bus writeのservice cycleは
timerの理論due cycleから遅れる場合がある。timer accumulatorが決めるdue-cycle列を正確性判定に使い、
実際のservice-cycle latencyは別fieldで報告する。両者を混ぜてsilicon cycle accuracyを主張しない。

## 受入判定と必須観測

### Emu側

5つの固定UART markerを必須とする。UARTとLCDが判定するのはfirmware自身が観測できるproducer、
public audio driver、statsだけであり、backend sink/timingのPASSを名乗らない。

- `[NEXT2][AUDIO][INIT] ...`
- `[NEXT2][AUDIO][DMA_CFG] ...`
- `[NEXT2][AUDIO][STREAM] ...`
- `[NEXT2][AUDIO][STATS] ...`
- `[NEXT2][AUDIO][FIRMWARE_VERDICT] ...`

最終emulator PASSはUART markerだけでは成立しない。structured reportの`audio_sink` sectionが
DMA-origin sample count/hash、timer due-cycle列、service latencyを提示し、両側がPASSして初めて成立する。

追加 fail-closed条件:

- exception発生、unsupported MMIO非ゼロ、サンプル変異、間違いdest、間違いwidth、間違いTREQ、間違いcadenceは全てfail扱い。
- underrun/drop/clip が 0 以外ならfail、49152個以上/未満の転送はfail、drain未完了はfail。
- timer due-cycle列とsample streamは3 runでbyte-identicalでなければfail。
- firmware marker内のproducer vector SHAが正しくても、backend sinkのcount/hashが違えばfail。

### 再現性（エミュレーター）

- 初回runはbackend凍結を保持したまま実施し、失敗しても結果記録は必須。
- 3回の決定的runを要求。
- 2回のclean clone再現buildを要求。

### エビデンス境界

- R5の`audio=pass`は設定/counterと実機参照音の証拠であり、新しいPCM hashの根拠ではない。
- NEXT-2Bのエミュレーターauthorityは、実際のDMA-origin `PWM5_CC` write streamである。
- 実機の音響はハード側の補助証拠であり、byte-exact判定のoracleとはしない。

## ハード実機側

- 同一buildのBIN/UF2を使用し、UART全文と最終PASS写真を採取。
- 音の確認は追加の**補助**採点で、byte-exact oracle にはしない。

人間操作はUF2書込み、UART保存、最終写真1枚、1.024秒の再生を含む録音だけとする。markerは
再生終了後も周期再送し、USB CDCを起動前に開くタイミング合わせを要求しない。具体手順はartifactが
固定された後に別節へ追加する。

## 実装順序

1. この契約と独立vector oracleを先にcommitする。
2. backendへDMA fractional timer DREQを実装する。
3. DMA-origin `PWM5_CC` writeだけをstreaming観測するsample sinkを実装する。
4. 新規appを公開audio APIだけで作り、最初のfrozen-backend runを失敗時も保存する。
5. fail-closed negative、3 run決定性、2 clean buildを確認してtarget revisionを固定する。
6. 同一UF2の実機証拠を一度の人間セッションで採取する。

## 主張しないこと

本契約はanalog PWM carrier、PicoCalc speakerの伝達特性、microphone録音のbyte一致、Threaded実行、
multicore producer、一般audio file decoderを証明しない。
