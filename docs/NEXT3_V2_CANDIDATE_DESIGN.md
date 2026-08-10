# NEXT-3 LCD fault v2 candidate design

**状態（2026-08-10）:** A1実装・clean clone再現・emulator PASS・同一UF2のuf2loader実機PASSまで
完了した。positive control gateは閉じ、次はwriter CS境界とidentityだけを変更するfault Bを固定する。
fault Bは実機oracle確認前にエミュレーターで実行しない。

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
3. A1から許可された差分だけでBを作り、BIN/UF2/source bundleとoracleを凍結する。
4. 一般利用経路のuf2loaderでBを実機実行する。
5. 実機結果がoracleへ完全一致した場合だけ、同一BINを凍結backendで初回実行する。
6. hardwareとemulatorの理由を比較し、`correct_negative_detection`、`false_accept`、
   `wrong_reason_failure`のいずれかへ分類する。
7. A2を作り、emulatorと実機の完全PASSを固定する。

A1がPASSしない、clean clone再現に失敗する、Bのdiffがobserverへ触れる、実機結果がoracleと違う、
identityが不完全、のいずれかで停止する。oracle不一致はv1と同様`inconclusive`であり、negative母数へ
加えない。

## 人間操作とCI

実機段階ではA1、B、A2の最大3回、uf2loaderから起動してUART logと最終画面を保存する。BOOTSEL限定の
技術的理由はない。キー入力は不要である。実装・build・schema・emulator検証はローカルで行い、通常の
試行錯誤でGitHub Actionsを起動しない。workflow変更、push、CI実行はこの事前設計に含まれない。
