# NEXT-3 LCD fault v2 candidate design

**状態（2026-08-10）:** A1はemulator／実機ともPASSした。Fault Bも再現可能artifactとして固定し、
uf2loaderで実機先行実行したが、凍結oracleには一致しなかった。実測はred/green/blue solidが各4 mismatch、
patternも`0x7c00`×4・4 mismatchで、v1と同じ広い症状だった。この候補は`inconclusive`として停止し、
Fault Bのエミュレーター実行は解禁しない。oracleも変更しない。実機後のsource gap分析も完了し、
observer差が十分条件でないこと、最大の残差が旧`fill_rect()`の160x160 tilingであることを確認した。
複数の未固定変数を重ねた再試行はせず、次は決定的なSD CMD8 CRC negative候補を事前設計する。

機械可読な正典は
`firmware-validation/contracts/next3-lcd-cs-fault-v2.json`である。本書は判断根拠と人が読む
実行順を説明する。

## v1がnegative caseにならなかった理由

旧ログのboot identityは`5b12a7cbff45a928c440a70a4e3a77750c1daa13`である。その
`bsp/src/display.cpp`とv1 fault sourceを比較すると、書込み側は同じ欠陥を再現している。

- CASET commandとdataでCSを分ける。
- RASET commandとdataでCSを分ける。
- RAMWR commandの後にCSを上げる。
- pixel payloadを新しいCS Lowで送る。

したがって「注入したwrite defectが旧版と違う」がv1不一致の原因ではない。

一方、結果を判定するRAMRD observerは一致していなかった。

| 系列 | write framing | RAMRD observer | 実機結果 |
|---|---|---|---|
| 旧`5b12a7c` | CS separated | SIO bitbang、約500 kHz、falling-edge sample、1 us delay | solid 5色PASS、pattern red×4、3 mismatch |
| v1 fault | CS separated | hardware SPI、6 MHz | solidのred/green/blue FAIL、pattern `0x7c00`×4、4 mismatch |
| 現行正常版 | single CS-low | hardware SPI、6 MHz | positive conformance PASS |

旧版source SHA-256は
`8f297c88c9ccfda7fc5f1b7344fdd6b3049e8cc1dd69c48b2c35c5b39bc80f38`、旧UART log SHA-256は
`4f0d4de4a58b5e78c80683e28a1406cad1feacef89947d13f906440f8a01d1fb`である。v1 driver
SHA-256は`772a81f2ba098eca00ede3caf759044f348dacd2776fc20a39e052917c67f5a7`である。

よってv1は、旧write defectは再現したが、凍結oracleを生成した完全な測定系を再現していなかった。
observer差は確認済みの主要な未制御変数である。ただしv2の制御実験前には、oracle不一致の唯一の原因と
断定しない。

v1のred `7c8000`、green `007c80`、blue `80007c`は、RGB666の18 bit列を1 bit右回転した値と厳密に
一致する。blackとwhiteは回転しても不変なので、2色だけPASSした結果も説明できる。sampling phase差と
いう説明は強い推論だが、電気的波形を測定していないため確定事実にはしない。

## v2で答える問い

v2は次の一問だけをA/Bする。

> 同一の旧SIO bitbang observerで測ったとき、write transactionを単一CS Lowから旧CS-separated
> framingへ変えることだけで、旧ログの正確なFAILが再現するか。

observerを変えながらfaultを変えることを禁止する。これにより、hardware SPI readback由来の差と
write-side CS保持欠陥を分離する。

4色patternの先頭pixelを繰り返すfaultなら同じ画面症状を容易に作れるが、これはpixel progressionの
欠陥であり、旧CS保持欠陥でもbackendのCS model検査でもない。negative caseを作ること自体を目的化せず、
v2候補から除外する。

## A-B-A設計

### A1: v2 baseline

現行の正しいwriterを使い、RAMRDだけを旧`5b12a7c`のSIO bitbang方式へ置き換える。

- CASET、RASET、RAMWR、全pixel payloadは単一CS Lowを維持する。
- readbackはSPI1をdeinitし、SCK/MOSI/MISOをSIOへ切り替える。
- 1 us delay、falling-edge後のMISO sample、dummy byte、RGB888→RGB565変換を旧版と一致させる。
- emulatorと実機の両方でsolid 5色と4色patternが完全PASSしなければ停止する。

この段階はobserver自体が正常版を誤判定しないことを証明するcontrolである。

### B: v2 fault

A1からwrite-side CS framingだけを旧版へ変更する。許される差分はfirmware identity／証拠markerと
writerのCS境界だけである。readback transport、clock、edge、delay、dummy count、色変換、座標、
sample数、期待色、backendを変更してはならない。

実機oracleは実装前に次へ固定する。

| 検査 | raw RGB888 | RGB565 | mismatch |
|---|---|---|---:|
| solid black | `000000` | `0000` | 0 |
| solid white | `fcfcfc` | `ffff` | 0 |
| solid red | `fc0000` | `f800` | 0 |
| solid green | `00fc00` | `07e0` | 0 |
| solid blue | `0000fc` | `001f` | 0 |
| pattern | `fc0000`×4 | `f800`×4 | 3 |

最終状態は`app_status=fail`、`sd=pass`である。結果を見た後にoracleを合わせてはいけない。

Fault Bのcanonical sourceはcommit
`3a073fbf206b02993dd80a0a7158c1e3c865efff`である。A1とのnet tree diffは次の3 pathだけで、
observer、座標、期待色、sample数、色変換は不変である。

- `CMakeLists.txt`: application identityのみ
- `app/main.cpp`: evidence markerのみ
- `bsp/vendor/lcd_hwspi_rgb888.cpp`: `begin_window()`のwrite-side CS framingのみ

同じA1 timestampでcanonical treeと別clean cloneをbuildし、両方で次のartifactが一致した。

- BIN SHA-256: `f9f5a347c36b38fbcb93967cd6a6bcd7caafb8d19805d235e0bfc7a27c5a18a4`
- UF2 SHA-256: `8f45245d8b0c8f1d543d1f909368ca4c48438e898352b48c3afcdaa172cb291f`
- source bundle SHA-256: `876a1889897517d01a18ee813922a725f602c52df988627b8eccaf1b71534de0`

artifact凍結時recordは`firmware-validation/records/next3-v2-b-20260810-01/record.json`、実機結果は
`firmware-validation/records/next3-v2-b-hardware-attempt-20260810-01/record.json`である。前者は当時の
hardware pending状態を時点証拠として書き換えず、後者がoracle不一致とemulator禁止継続を記録する。

### B実機結果

一般利用経路のuf2loaderでcanonical Fault B UF2を実行した。boot identity、source commit、timestamp、
SD、最終markerは期待と一致したが、LCD oracleは一致しなかった。

| 検査 | 凍結oracle | 実機 |
|---|---|---|
| solid black / white | PASS | PASS |
| solid red | `fc0000` / `f800`、PASS | `7c8000` / `7c00`、4 mismatch |
| solid green | `00fc00` / `07e0`、PASS | `007c80` / `03f0`、4 mismatch |
| solid blue | `0000fc` / `001f`、PASS | `80007c` / `800f`、4 mismatch |
| pattern | red×4、3 mismatch | `7c8000` / `7c00`×4、4 mismatch |

`app=fail`、`sd=pass`、15 markerは一致したが、部分一致でoracleを変更してはならない。v1で使った
hardware SPI observerをhistorical SIO observerへ戻しても同じrotated-bit症状となったため、observer差は
v1 oracle不一致を説明する十分条件ではなかった。旧`5b12a7c`証拠との差には、まだ別の未固定変数がある。

UARTの`window_cs=held_from_caset_through_ramwr`はA1から残った古い診断文字列で、Fault B sourceの実際の
CS-separated writerと矛盾する。writer authorityはcanonical source diffであり、この文字列はtransaction
証拠に使わない。後続候補ではwriter modeを独立して正しく出力する。

### 実機後のsource gap分析

旧`5b12a7c`、v1、v2 Fault Bを再比較した。v1のhardware-SPI RAMRDとv2のhistorical-SIO RAMRDは、
現行runtime上で同じrotated-bit値を返した。したがってobserver差は実在したが、旧oracleを回復する
十分条件ではなかった。

残る差は次の順で評価した。

1. **最高:** 旧`fill_rect()`は矩形を最大160x160へ分割し、tileごとにwindowとCS境界を作る。現行Bは
   矩形全体を1 windowにするため、CS faultが通るcommand/window列が直接異なる。
2. **高:** 旧runtimeはkeyboard→LCDの直後に検証し、PSRAM probeとaudio pathを持たない。現行runtimeは
   PSRAMをprobeし、audio DMA/PWMを開始して250 ms後に検証する。実測では検証前にaudio IRQが104回ある。
3. **高だが回収不能:** 旧SDKの正確なcommit、compiler/binutils/CMake/generator、BIN、UF2が残っていない。
4. **中〜低:** SPI function選択前のSCK/MOSI directionとMISO pull初期化が異なる。ただしSIO設定と
   観測idle levelは一致する。

座標、期待色、mismatch計算、SIO bit order、edge、dummy count、SPI restoreは同等である。差分記録は
`firmware-validation/records/next3-v2-gap-analysis-20260810-01/record.json`に固定した。

160x160 tilingだけを次に試せば原因の切り分けにはなるが、旧artifactとbuild環境を復元できない以上、
tiling、runtime、toolchainを順次または同時に変えてもnegative caseの同一性を証明できない。このためv2を
`inconclusive`で閉じ、追加の人手hardware retryを要求しない。次候補は、結果がタイミングや表示observerに
依存しないSD SPIのCMD8 bad-CRC caseを、正常版／fault版／修正版とhardware-first順序で事前設計する。

### A2: fixed

BからwriterだけをA1へ戻す。observerは同じままとし、emulatorと実機の完全PASSを再確認する。

## backendに対する事前予測

promoted backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`のST7365P modelは、CSがHighに
なってもcommand stateを保持し、`command_state_survives_cs_pulsing_between_bytes`でその性質を
試験している。このため旧fault framingを受理し、hardware FAIL artifactをPASSさせる可能性がある。

これはfalse acceptの事前仮説であって、結果ではない。契約順序を守るため、v2 faultが実機oracleへ
完全一致するまではfault BINをエミュレーターで実行しない。最初の結果はPASSでもFAILでも保存し、
後から期待に合わせてbackendを変更しない。

## 実行順と停止条件

1. A1を実装し、source/toolchain/timestampを固定してclean cloneからBIN/UF2を再現する。
2. A1 BINをemulator、同一build UF2を実機で実行し、両方の完全PASSを固定する。
3. A1から許可された差分だけでBを作り、BIN/UF2/source bundleとoracleを凍結する。**完了**
4. 一般利用経路のuf2loaderでBを実機実行する。**完了、oracle不一致**
5. 実機結果がoracleへ完全一致した場合だけ、同一BINを凍結backendで初回実行する。**禁止のまま**
6. hardwareとemulatorの理由を比較し、`correct_negative_detection`、`false_accept`、
   `wrong_reason_failure`のいずれかへ分類する。
7. A2を作り、emulatorと実機の完全PASSを固定する。**停止条件により未実施**

A1がPASSしない、clean clone再現に失敗する、Bのdiffがobserverへ触れる、実機結果がoracleと違う、
identityが不完全、のいずれかで停止する。oracle不一致はv1と同様`inconclusive`であり、negative母数へ
加えない。

## 人間操作とCI

実機段階ではA1、B、A2の最大3回、uf2loaderから起動してUART logと最終画面を保存する。BOOTSEL限定の
技術的理由はない。キー入力は不要である。実装・build・schema・emulator検証はローカルで行い、通常の
試行錯誤でGitHub Actionsを起動しない。workflow変更、push、CI実行はこの事前設計に含まれない。
