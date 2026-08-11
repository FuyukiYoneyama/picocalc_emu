# NEXT-2B Audio conformance

> **文書の役割:** 検証器が読むbounded conformance契約です。NEXT-2Bは完了しています。

**状態:** v3 canonicalのformal emulator acceptanceとsame-artifact hardware correlationが完了した。

## 契約履歴

- `next2-audio-v1-20260809`: 実装前レビューでfirmwareとbackend authorityの混同を検出。削除しない。
- `next2-audio-v2-20260809`: v1をsupersede。quantizerとsoftware-retrigger境界の定義不足を初回backend runで検出。削除しない。
- `next2-audio-v3-20260809`: 現在のcanonical。`firmware-validation/contracts/next2-audio-v3.json`。

v3はSerial Quantum 1、公開 `picocalc::audio` APIのみ、49152 stereo frames（48 kHzで1.024秒）、
キー入力不要を固定する。producer seed SHA `c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a`
と、canonical error-diffusion quantizer後のsink SHA `1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f`
は別物である。

## 初回runと原因

初回firmware runは5 markerとLCD firmware self-verdictをpassしたが、backendは
`24895/49152` writes、sink SHA `845ae384fa617b774c95aec35f2696e61c65328235b6afcc48e2222397bdc954`
でfail-closedした。原因は次の3点である。

1. active level IRQの二重pendingでDMA handlerが二重実行された。
2. v2 oracleがcanonical error-diffusion quantizerを欠落させた。
3. 128-frame software-retrigger境界のgapを通常のintra-block cadenceと区別していなかった。

## Formal emulator acceptance

`picocalc-audio-r1`はbackend `d92db1b391a6bab078ca73ee4eb1b2ca88e394a3`で3回合格した。
2つのclean cloneから作ったBIN/UF2もバイト一致し、3回のreport、UART、timeline、snapshotも
それぞれバイト一致した。正式artifactは次である。

- app commit: `724b3ac74f1401a19d6310af387c65ad1e5476a4`
- BIN SHA: `acaaf220fa9912a4cbd09de923f002ffe1fc0748d7c295ea997c1d28319b0cb6`
- UF2 SHA: `d6986103e74e153fd23ea7ce25111bba0a5752331959367b0aa63f6eb1c28677`
- cycles: `405523032`
- normalized report SHA: `c956af5314c85e5d89d95d632c3838b2d4a9669403610b297e2197bf745a689e`
- timeline SHA: `828895d75e1b46bfb25d36bc4d4e1b5b9466ee9fdb900c582b1c4cb8272c3d55`

- DMA writes: `49152`
- post-quantizer sink SHA: `1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f`
- blocks/boundaries: `384` / `383`
- intra-block gaps: `5208=32640`, `5209=16128`, unexpected `0`
- boundary gap SHA: `bb5372879a362de7eff7283322d1eb30b5879660cd87a90b379904253301bc06`

同じ正常BINへ誤ったcountとhashを要求した2回のfull runner mutationは、firmware markerとLCDが
PASSのままでもexit 1 `audio_sink_mismatch`となった。さらに保存reportのsample、destination、
width、TREQ、cadence、block、boundary、count、exception、unsupported MMIOの10 mutationを
field gateとnormalized-report gateがすべて拒否した。証拠は
`firmware-validation/records/next2-audio-r1-20260809-01/`に固定している。

## Authority境界

Firmwareは公開API初期化、49152 producer frames受理、drain、underrun/drop/clip、BSP carrier/ring/DMA fractionのみを判定する。
backendがDMA-origin PWM5_CC writes、post-quantizer sink hash、block境界、timer due-cycle、service latencyを判定する。
producer seed SHAやR5 counters/録音はsink oracleの代用にならない。

formal emulator要件（3 firmware runs、2 clean builds、byte-identical artifacts/report/timeline/sink、
negative mutations）は完了した。同一UF2の実機でも18組の完全marker block、最終5-PASS画面、
約1.05秒の音響captureを確認した。実機recordは
`firmware-validation/records/next2-audio-r1-hardware-20260809-01/record.json`である。
`audio-output`はこの凍結targetの範囲に限り`supported`／`same_artifact_hardware_correlated`とする。

音響captureは実機から音が出たことと継続時間の相関であり、byte-exact oracleではない。49152 DMA-origin
writes、post-quantizer SHA、due cycle、block境界、gap、service latencyの権威は引き続きemulator recordにある。

## 同一UF2実機相関の人間手順（完了済み・再採取用）

再採取時に生成するファイルは
`/home/fuyuki/pico_dvl/codex/picocalc_emu_ext/picocalc-audio/build/picocalc_app.uf2`で、SHA-256は
`d6986103e74e153fd23ea7ce25111bba0a5752331959367b0aa63f6eb1c28677`である。
`build/`は再生成可能なため共有workspaceには保持していない。target registryの固定source、
SDK、toolchain、timestampで再buildし、SHA-256を確認してから使用する。
キー入力は一切ない。通常は1回のflashと1回の実行で完了する。

1. `sha256sum`でUF2が上記SHAと一致することを確認する。
2. PicoCalcをUF2書込み状態にして、スマートフォン等の動画または音声録音を**先に開始する**。
3. UF2を`RPI-RP2` volumeへコピーする。自動再起動直後に約1.024秒のPCM test音が出る。
4. LCDの`NEXT2 AUDIO`画面でINIT、DMA CFG、STREAM、STATS、FIRMWAREの5行がすべて緑の
   `PASS`になるまで待つ。画面はその状態で停止する。
5. USB CDC monitorを開き、次の完全な5-marker blockを1組以上保存する。markerは1秒ごとに
   反復するため、起動後にmonitorを接続してよい。
6. 最終5-PASS画面を写真1枚に収め、録音を停止する。
7. UART log、写真、音を含む動画または録音の3点を提出する。

音だけ取り逃した場合は再flashしない。録音を開始してからresetまたは電源再投入し、同じUF2を
再実行する。UARTが空なら実行したままmonitorを再接続し、次の反復blockを待つ。LCDにFAILが出た、
音が繰り返し出ない、またはmarker値が異なる場合は合格扱いにせず、その証拠を保存して原因調査へ
戻る。撮影やmonitor接続の失敗だけなら、契約やartifactを変えず同じ手順を再試行できる。
