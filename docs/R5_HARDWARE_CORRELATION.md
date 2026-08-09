# R5 PicoTetris同一BIN実機相関

**状態:** 実装・再現build・emulator preflight・PicoCalc実機相関完了。OPT1-Aはpromoted。

**audio境界:** 本書の`audio=pass`はfirmwareの設定・stream counterと実機で聞こえた参照音を
相関した結果である。エミュレーターがDMA-paced PCM waveformをsample sinkへ生成したという意味では
ない。後者は`firmware-validation/capability.json`で`audio-output` unsupportedのままである。

## 目的と判定境界

R5は、エミュレーターが合格させたものと**同じfirmware artifact**をPicoCalc実機で動かし、
OPT1-A高速化後も実機相当の結果を保つかを相関する。別のBSP診断BIN、途中のゲーム操作、
時刻に合わせた入力、ゲーム中の写真は使わない。

正典artifactは次である。

| 項目 | 固定値 |
|---|---|
| target | `picotetris-r5` revision 4 |
| PicoTetris source | `9a40a905f3ddcc6dc835655e2a332fce88f98800` |
| recovery bundle | `provenance/picotetris-r5.bundle` — `1187bccb9cc5b414e00c281db3e6782e7e936464bd634dfc7feae32573b707a3` |
| backend | `612b48510452d4012e4ac6639960ca3983b48f66` |
| BIN | `PicoTetris_R5.bin` — `8b4ac5c0026bb582825fd767ecd26d5278710590a2e2312ce4b817d12c60adc0` |
| UF2 | `PicoTetris_R5.uf2` — `0e990cff819b8542a7a96765cd7004c7b23cb52b77494c745b914afd32f084f1` |
| build timestamp | `2026-08-08T00:00:00Z` |
| official keyboard source | ClockworkPi `picocalc_keyboard` commit `a61c1f2f18185b32a667dde5c9393ced9ddd19ca` |

BINとUF2は、固定SDK/toolchainを使った2つのclean clone buildでそれぞれbyte-identicalに
なっている。エミュレーターには上記BIN、実機にはその同じbuildのUF2を使う。

## firmwareが自動で行うこと

起動後、人間のゲーム操作なしで次を順に実行する。

1. LCD RGB565 write/readbackを100回検査する。
2. 1 kHz参照音のaudio stream経路を検査して停止する。
3. PSRAMをwrite/read/compareする。
4. SDをmountし、FAT32既定（FAT16は任意互換profile）でwrite/sync/read/compare/removeする。
5. 実際のPicoTetris `Game`へ固定操作列を与え、line clear、game over、restartを検査する。
6. 公式keyboard firmware由来の67物理キー診断画面へ移る。

固定検査のどれかが失敗してもキー画面までは観測できるが、最終`overall`は`fail`になる。

## 人間が行う1回のセッション

必要なのは、1回の起動セッションと、完了していないキーだけの物理入力である。67キーを
決められた順に連続成功させる試験ではない。

1. 32 GB/FAT32 SDへ上記UF2を配置する。配置前後にUF2のSHA-256を確認し、UART全文の採取を
   起動前から開始する。
2. PicoCalcを起動する。約1 kHzの参照音が聞こえたかを`yes`/`no`で記録する。音の確認に
   音量・音程の主観評価は加えない。
3. 67キー画面が出たら、**`CAPS`以外の66キー**を任意順で入力する。通常キーは押して
   離す。`UP`と`DOWN`だけはrepeatが届くまで長押ししてから離す。
4. **途中では`CAPS`を絶対に押さない。** 他の66キーが緑になり、進捗が`66/67`になったことを
   確認してから、最後に`CAPS`を1回押して離す。これは推奨ではなく、この診断firmwareの
   必須操作条件である。
5. `67/67`と最終PASS画面が安定したら入力を止め、その画面を**1枚だけ**撮影する。
6. UART採取を停止して無加工の全文を保存し、UF2 SHA、PicoCalc board revision、SD製品・容量・
   filesystem、音確認結果、写真名、UARTログ名を実機recordへ記入する。

人間の必須証拠操作は、参照音の確認1件、完了していない67物理キーの確認、最終写真1枚、
UARTログ保存1件である。途中写真、26キーの連続操作、ゲームの手動操作はない。

## 入力ミスと中断からの復旧

- **押しても緑にならない:** そのキーだけをもう一度、明確に押して離す。他キーの成功は失わない。
- **違う順・重複入力:** `CAPS`以外は失敗にしない。確認済みキーは緑のままで、未確認キーだけ続ける。
- **releaseを取り損ねた:** 黄色の該当キーをもう一度押して離す。
- **`UP`/`DOWN`が黄色のまま:** その矢印だけをrepeatまで長押しし、離す。
- **誤って`CAPS`を早く押した:** 通常手順ではなくリカバリである。`PRESS CAPS AGAIN`表示中は
  他キーを入力せず、もう一度`CAPS`を押して通常状態へ戻す。その後は以前の成功を保ったまま
  続行し、`66/67`になってから最後に`CAPS`を検査する。
- **電源断・誤reset:** 同じUF2と同じSDで再起動する。checksum付き`PCR5KEY.DAT`、またはbackupの
  `PCR5KEY.BAK`から完了済みキーを再開する。固定自動検査は再実行される。
- **SD保存失敗:** RAM上の操作は続けられるが最終判定はFAIL。SDを直して再起動し、保存済みの
  有効な進捗から再開する。
- **完全に最初から再試験:** PCでSD上の`PCR5KEY.DAT`、`PCR5KEY.BAK`、残っていれば
  `PCR5KEY.TMP`を削除してから起動する。

### CAPS表示と検証範囲に関する既知の制約

現行画面の`ANY ORDER - CAPS LAST`は、`CAPS`だけが任意順の例外であり、途中押下を禁止する
必須条件だと十分明確に伝えない。さらに`CAPS`を通常の物理配置内に表示しているため、最後の
確定操作であることも視覚的に弱い。現行artifactを再実装しないため、実機操作では上記の
明示手順を画面表示より優先する。

R5の`67/67`は`CAPS`のraw code `0xc1`を含む全物理キーのpress/release到達性を示す。一方、
この診断はkeyboard status registerのCaps bitを読み取らず、開始時および終了時のCaps状態を
assertしない。またemulator preflightは登録scenarioからraw FIFO eventを投入するため、物理matrix
入力によるCaps toggleと後続英字の大小文字変換を相関した証拠ではない。したがって本recordから
主張するのは67キー到達性までとし、Caps状態遷移・終了時Caps off・完全な操作UXは合格範囲に
含めない。

リトライ上限とtimeoutは設けない。リトライ対象は失敗したキーだけであり、全67キーを最初から
繰り返す必要はない。

## emulator preflightの固定結果

登録scenarioは67 unique codeを136 raw eventで投入し、`UP`/`DOWN`は公式repeatに合わせて
`pressed, pressed, released`、`CAPS`は最後としている。最終runは次で合格した。

| 観測 | 値 |
|---|---|
| stop / scenario | `scenario_done` / 5 of 5 pass |
| virtual time | 9,879,987,214 cycles / 39,525,002 us |
| keyboard | 136 delivered、0 remaining、0 dropped、67/67 |
| SD / PSRAM | FAT32・unknown command 0 / attached |
| UART SHA-256 | `202f5b83617147a1536b4729c33a31168072001169c104f2dbffcd768251bb83` |
| RGB565 framebuffer SHA-256 | `3f630e04d2fb2c6c9fcd8446052d48d03a4a00aab797d7aef21e67a459830abe` |
| normalized report SHA-256 | `f983959ae020f1633046e73fedb843485d1f52617615f3e1b5638c6cd7b020ce` |
| timeline SHA-256 | `d2bfa45832408c909460cd7579d211b0c05730751549d76617a9d36662a16d19` |

最終UART verdictは次の完全な1行である。

```text
[R5_DIAG_VERDICT] lcd=pass psram=pass sd=pass audio=pass tetris=pass keyboard=67/67 io_errors=0 progress=saved overall=pass
```

preflight証拠は
[`firmware-validation/records/r5-preflight-20260808-01/`](../firmware-validation/records/r5-preflight-20260808-01/)
に保存する。`result=pass`は再現buildとemulator preflightだけを意味し、同recordの
`hardware_correlation_completed=false`はpreflight時点の不変証拠として保持する。現在の実機相関状態は
後続の`r5-hardware-20260808-01`を正典とする。

## PicoCalc実機相関結果

2026-08-08に、上記UF2をCPI2.0/RP2040のPicoCalcと32 GB SanDisk FAT32 SDで実行した。
UARTは途中再起動と`resumed=1`を含み、回復契約を実地に通した後、次の完全な最終行で終了した。

```text
[R5_DIAG_VERDICT] lcd=pass psram=pass sd=pass audio=pass tetris=pass keyboard=67/67 io_errors=0 progress=saved overall=pass
```

| 証拠 | SHA-256 / 結果 |
|---|---|
| UART全文 `uart.log` | `d9b2b8417bb88af4f6a5432235fd12a0bbe83e86500668998b6c349093b0181a` |
| 最終写真 `final.jpg` | `7cb0e8789476b82168e8d0250385267290bfaa0fef42ea0bbfab48a38690ab1a`、`R5 ALL PASS` |
| SD進捗 `PCR5KEY.DAT` | `0e6e09a6f787c2ee95ccc4671ef2bd67caab8d6434456071cf125ded1ca0c16e`、CRC32一致、67/67 |
| 参照音抜粋 `reference-tone.flac` | `5266ee1337d58191ebde23d08dc1aeabbc65183b4068d9b2c60e113425687f19`、FFT peak 984.375 Hz |

証拠と解析は
[`firmware-validation/records/r5-hardware-20260808-01/`](../firmware-validation/records/r5-hardware-20260808-01/)
に保存する。エミュレーターがpassで実機がfailになった項目は0件で、同一artifact相関は合格した。

キーボードは67キーの到達性とI2C error 0を満たす一方、operatorは一部キーの反応が悪くretryを
要したと報告した。本試験はイベントを発生しなかった物理押下を観測できないため、miss率、押下圧、
latencyを測定したとは扱わない。この入力品質上の制約は67/67 conformanceとは分離して残す。

## 実機合格条件

- 起動UARTのsource/BSP/build identityと使用UF2 SHAが上の固定値に一致する。
- LCD、PSRAM、SD、audio path、line clear、game over、restart、keyboardがすべて`pass`になる。
- `keyboard=67/67`、`io_errors=0`、`progress=saved`、`overall=pass`の完全verdict行がある。
- 最終写真でPASS画面が可読で、色・向き・ノイズに実用上の異常がない。
- 参照音が実機で聞こえた記録がある。
- UART全文、最終写真、操作環境を新しい実機recordへ保存する。

全条件は`r5-hardware-20260808-01`で一致したためOPT1-Aはpromotedである。今後の高速化でも、
実機不一致があれば速度向上を理由に許容せず、まずmodelまたはfirmwareの差を特定して正確性を修正する。
