# 実装状況と利用手順

## 現在利用できるもの（BSP 0.8.8、template app 0.8.4-*、RGB565推奨デフォルト）

「空のプロジェクトからAIにハードウェア初期化を書かせない」ためのBSP・テンプレート・
検証器に加え、PC上でRP2040 BINを走らせるfirmware backend、BSP APIのhost model、
scenario runnerまで利用できる。公式サンプルのA系統と標準templateのB系統は、LCD、
PSRAM、SD、keyboardを含めてエミュレーター上で観測できる。個別アプリがhost unit testや
継続回帰targetへ接続済みかどうかは別に判定し、現在のhardening順序は
[`MILESTONES.md`](MILESTONES.md)の「現在の実行順序」を参照する。

R0の生成契約・source identity固定は完了した。schema 2 metadata、生成時BSP版・commit・
実体SHA-256、license/notices、PicoTetrisの履歴復元とGit bundleを
[`R0_BASELINE.md`](R0_BASELINE.md)に記録している。R1はSD/FAT32、verdict、公式keyboard
firmware conformanceを完了し、R2でschema 2 target registry、schema 8 backend build identity、
上位Firmware CLIのfail-closed接続まで完了した。R3ではPicoTetrisの666 host checks、
再現可能BIN/UF2、active firmware target、3回決定性回帰まで完了した。R4の品質ゲートとCIは
2026-08-06に着手し、backendのtest・fmt・Clippyを独立して実行するGitHub Actionsを
`picoem-picocalc` commit `3bc6bbd7833e45fbf94d640eb7fbe056dd9fbd81`で完了した。generatorは
`app_git`をproject自身のGit rootだけから取得するよう修正し、親repository内・外の生成先が
同じ`untracked`になる回帰試験を追加した。`bsp_git`のmetadata由来契約は維持している。
target registryはschema 3へ進め、revision、`supersedes`、SHA固定attestationと不変evidence
recordを接続した。`picotetris-r4` revision 2をbackend `3bc6bbd...bd81`で3回実行し、全runの
exit 0とraw/normalized report、timeline、UART、framebuffer、PNG一致を記録した。
PicoTetrisはcommit `6cd16eb075120140d9073a72db665482f3c2fe95`で、現行sourceの666 host
checksと、R3固定source・SDK 2.2.0・Ubuntu 24.04標準toolchainから登録済みBIN/UF2を
再現する二つのCI jobを接続した。GitHub Actions run `31101591668`で両jobとSHA完全一致を
確認した。`picocalc_emu` commit `f9b596fe01163d69f2396bb3d50aafb44965c825`ではportable、
Python tools、target/schema、host、SDK 2.0互換build、固定PicoTetris firmware regressionを
独立jobへ接続した。run `31103564391`で全6 jobが合格し、3リポジトリのclean-runner full
gateを完了した。詳細は[`R4_CI.md`](R4_CI.md)にある。PicoTetrisのprivate GitHub repositoryは
同日に追加済みである。R0/R3のbundleと`remote: null`は各時点の復旧証拠なので保持する。
R5実機着手前のWSL性能baselineでは、`picotetris-r4`の実時間比中央値を5.874%
（仮想3.715秒をwall 63.247秒、約17.025倍遅い）と測定し、全10 runのreport/UART/PNG一致を
確認した。詳細は[`R5_REALTIME_PERFORMANCE.md`](R5_REALTIME_PERFORMANCE.md)にある。
OPT0-Aではbackend `ace66df91f87cfe18c7bec0ba47bcbc12f5c9345`に通常buildから完全に
分離した`idle-profiler` featureを追加し、clean buildでPicoTetrisを初回計測した。既存の
cycle、UART、framebuffer、85/85 scenarioは一致した。初回schema 1のproven-safe下限0 cycleは、
production用`is_idle()`が時間変化するworkと静的FIFO/IRQ stateを同一視した結果だったため、
backend `9135f5ad09fe86a2330e51cd9a3ee106cb7c9642`で計測専用の意味分類へ修正した。通常実行経路は
変更していない。schema 2再計測では同じ正確性契約を維持し、両core停止618,595,844 cycle
（66.692909%）すべてが観測境界上proven-safeとなった。初回証拠は
[`firmware-validation/records/opt0-a-20260806-01/notes.md`](../firmware-validation/records/opt0-a-20260806-01/notes.md)、
修正後の証拠は
[`firmware-validation/records/opt0-a-20260807-03/notes.md`](../firmware-validation/records/opt0-a-20260807-03/notes.md)
にある。これは最大3.002364倍のvirtual-cycle dispatch削減余地であってwall-time予測ではない。
続く部分cost計測では、CPU固定10 sampleで現行blocked step 52.647255 ns、保守的probe
10.771746 ns、quiescent bulk advance約37.1〜37.8 nsを得た。この時点では全source horizonと
event/IRQ/wake costが未測定だった。履歴記録は
[`firmware-validation/records/opt0-a-20260806-02/notes.md`](../firmware-validation/records/opt0-a-20260806-02/notes.md)
にある。

backend `8bd6809116ad9e38de9deea961603dfb2884101b`では、現行modelの全sourceを覆う
保守的なevent horizonを実装し、schema 3 profileでblocked区間を実際のTIMER/PWM境界へ
分割した。PicoTetrisは従来どおり85/85、927,528,660 cycle、UART SHA-256
`bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c`、framebuffer SHA-256
`f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2`で合格した。
618,595,844 safe cycleは2,064,042 segmentへ分かれ、そのうちPWM境界が2,063,903件、
TIMER境界が138件だった。続くbackend `67fc4bce7934885b439bc80629175dafeab2299f`で、診断featureを
含まないproduction blocked-path baselineを分離した。CPU固定10 sampleの中央値は
`Cblocked=48.621175 ns`、`Chorizon=30.388395 ns`、`Cadvance(1)=39.412803 ns`、
TIMER event/route/wake増分`7.122434 ns`で、損益分岐は2 cycleだった。既存63.247秒baselineへの
33.329秒・実時間比11.146%という値は優先順位選択用の算術投影であり、最適化実測ではない。
完全なraw data、SHA-256、再現手順は
[`firmware-validation/records/opt0-a-20260808-04/notes.md`](../firmware-validation/records/opt0-a-20260808-04/notes.md)
に固定した。これでOPT0-Aは優先順位決定まで完了し、最初の候補はOPT1-A exact idle
fast-forwardに決定した。OPT0-Bではbackend `763595fedefa08886b41298be79bff69324ac51f`へ
通常buildから完全分離した`behavior-trace` featureを追加した。canonical eventを配列へ保持せず
全体/domain別SHA-256へ逐次投入し、明示allow-list projectionからprovenance-freeな
`behavior_sha256`を作る。PicoTetris全走行2回のnormal report、behavior artifact、UARTは
byte-identicalで、feature無しproduction binaryのnormal reportもtrace ON時とbyte-identicalだった。
証拠は
[`firmware-validation/records/opt0-b-20260808-01/notes.md`](../firmware-validation/records/opt0-b-20260808-01/notes.md)、
契約詳細は[`OPT0_B_BEHAVIOR_CONTRACT.md`](OPT0_B_BEHAVIOR_CONTRACT.md)にある。これでOPT0-Bは
完了した。OPT1-Aはbackend `c68c58f6c37fb31eb9313566c8b16883db9063b6`で、両core blocked時の
全source horizonとrunner所有scenario/input境界を`step_until()`へ接続した。PicoTetrisのcycle、
UART、framebuffer、85/85 timelineを維持し、host UART drain cadence依存を除いたbehavior schema 2
でもone-cycle referenceと全9 domainが一致した。CPU固定10 runのwall中央値は63.247秒から
27.123秒へ57.116%短縮し、実時間比は5.874%から13.697%へ向上した。versioned target
`picotetris-opt1a` revision 3と不変recordを追加済みである。詳細は
[`OPT1_A_EXACT_IDLE_FAST_FORWARD.md`](OPT1_A_EXACT_IDLE_FAST_FORWARD.md)にある。この時点では
R5前のcandidateだったが、後述の同一artifact実機相関を通過して現在はpromotedである。

R5の実装とemulator preflightも完了した。PicoTetris source
`9a40a905f3ddcc6dc835655e2a332fce88f98800`は、既存666 checksを履歴として維持しながら、
固定ゲーム診断とキー復旧を含む690 host checksを通す。2つのclean cloneから同一の
`PicoTetris_R5.bin`（SHA-256 `8b4ac5c...adc0`）とUF2（`0e990cff...4f1`）を得た。
登録target `picotetris-r5` revision 4はbackend `612b485...f66`で、LCD 100回、PSRAM、FAT32 SD、
audio経路、line-clear、game-over、restart、公式FW由来67キーを全自動または回復可能な入力で
合格した。キーは任意順、個別retry、timeoutなし、SD progress resumeであり、途中写真を要求しない。
同じUF2のPicoCalc実機セッションも完了した。LCD、PSRAM、FAT32、audio、PicoTetris、67/67キーが
`io_errors=0 progress=saved overall=pass`で一致し、最終写真、参照音、CRC-validなSD進捗も固定した。
操作・結果の正典は[`R5_HARDWARE_CORRELATION.md`](R5_HARDWARE_CORRELATION.md)、preflight証拠は
[`firmware-validation/records/r5-preflight-20260808-01/`](../firmware-validation/records/r5-preflight-20260808-01/)
、実機証拠は
[`firmware-validation/records/r5-hardware-20260808-01/`](../firmware-validation/records/r5-hardware-20260808-01/)
にある。後続recordで`hardware_correlation_completed=true`となりOPT1-Aはpromotedである。
高速化は引き続き実機相当の正確性を最優先する。確定した全体計画は
[`EMULATOR_OPTIMIZATION_PLAN.md`](EMULATOR_OPTIMIZATION_PLAN.md)にある。

- `bsp/`: 実働プロジェクトを基準にした LCD二系統・キーボード・SD/FatFS・音声・PSRAM BSP。推奨デフォルトのBはPIO blocking/RGB565、互換・診断用Aはloader-style SPI/RGB666 3-byte containerを使う
- `templates/rp2040-basic/`: BSP を利用する最小アプリ、音声モード切替、個別コピペ例
- `tools/picocalc.py`: 新規プロジェクト生成、ビルド、検証
- `tools/benchmark_firmware_realtime.py`: 登録済みfirmware targetの仮想時間／wall time比を反復測定
- `picocalc.py build --build-timestamp ...`: 実機記録用に UTC build timestamp を固定した evidence build
- `tools/verify_environment.py`: portable fingerprint と基準証拠の段階別検査
- `profiles/picocalc-rp2040.json`: 機械可読なboard contract
- `bsp/include/picocalc/board_generated.h`: profileから生成したC++定数
- `tests/lcd_protocol_test.cpp`: SPI fakeによるLCD transaction検査
- `reference-projects/catalog.json`: 実機成功根拠と SHA-256
- `hardware-validation/`: Canonical BSP自身の実機検証schemaと台帳
- `tests/test_tools.py`: 検証器と生成器の回帰テスト

既存の実働プロジェクトは変更せず、次を Canonical BSP の根拠にしている。

| 機能 | 基準 | 固定した成功条件 |
|---|---|---|
| LCD A（互換・診断） | `general/lcd/src/main_hwspi_rgb888_probe.cpp` + `PicoCalc/Code/picocalc_helloworld/lcdspi` | `bsp/vendor/lcd_hwspi_rgb888.cpp`、SPI1 GP10〜15、25 MHz、COLMOD `0x66`、RGB666を3-byte RGB888 containerで送信、CASET/RASET/RAMWRから画素列までCS保持、RAMRDは6 MHz |
| LCD B（推奨デフォルト） | `general/lcd` / `pico_skyace` / `life` | 転送は`bsp/vendor/lcd_rgb565_pio.cpp`（無改変コピー、PIO0 blocking、LCD DMA OFF、clkdiv `2.0`、COLMOD `0x65`、RGB565を2 bytes/pixelで送信）。アダプタ側の契約はウィンドウ160×160以下・画素160ピクセル単位、RAMRDは`life`のキャプチャ手順 |
| Keyboard | **一次:** [ClockworkPi公式`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)（ローカル`/home/fuyuki/pico_dvl/codex/PicoCalc/Code/picocalc_keyboard`）。**consumer実機証拠:** `picocalc-life` | STM32F103R8T6側はI2C target `0x1f`、register `0x04`/FIFO `0x09`、31-event FIFO、7×8 matrix＋12 buttons。RP2040側はI2C1 GP6/7、400 kHz、repeated-start |
| SD/FatFS | `picocalc-life` | SPI0 GP16〜19、CS GP17、detect GP22、400 kHz初期化、12 MHz運用、CMD0/8/55/ACMD41/58 |
| Audio | `Picocalc_ment` | GP26/27 PWM、48 kHz、wrap 255、DMA timer、128 sample二重buffer、512 sample ring。固定サイン参照とPCM streamを切替可能 |
| PSRAM | `pico_rescue` | 8 MiB、実機検証済み通常候補（250 MHz: 2/false→3/false→1.5/true、125 MHz: 1/false→1.5/false→2/false→3/false→4/false）、24 byte chunk、read/write自己検証、Buffer API |

## 新規プロジェクト

`picocalc_emu` で次を実行する。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
python3 tools/picocalc.py build --project ../MyApp --sdk /path/to/pico-sdk
```

引数を省略した場合はB（`pio-rgb565`）をビルドする。

共存クロックの実機検証は、標準UF2名の専用ビルドで行う。

```sh
python3 tools/picocalc.py build --project . \
  --lcd-variant pio-rgb565 --psram-lcd-coexist-test
```

起動ログの`bsp=0.8.8`と`app=0.8.4-b-pio-rgb565-psram-lcd-coexist`、各候補の
`[PICOCALC][PSRAM][COEX]`行を記録する。`display_failures=0`かつ
`psram_failures=0`のcandidateがLCD更新と共存できたPSRAM速度である。

2026-08-01の実機結果では、250 MHz system clockにおける共存合格は
`clkdiv=1.5/fudge=true`（約83.3 MHz）、`clkdiv=2.0/fudge=false`（62.5 MHz）、
`clkdiv=3.0/fudge=false`（約41.7 MHz）。ただし通常スモーク起動では83.3 MHzに
1 byte不一致が発生したため、通常運用の推奨値は62.5 MHzとする。
全候補のLCD側は`display_failures=0`であり、PSRAM側の不一致だけが候補を不合格にした。

LCD BSPはA/Bを混ぜず、ビルド時に一方を選ぶ。生成物名は常に同じである。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant hwspi-rgb888
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
```

実機試験は同時に二つのUF2を扱わず、一度に一方だけを標準名
`build/picocalc_app.uf2`へ生成する。A（`hwspi-rgb888`）とB（`pio-rgb565`）は
どちらも独立した合格対象であり、Aの結果でBを廃棄しない。各ログ先頭の
`variant`と、LCDの`[PICOCALC][LCD][VERIFY] app_status=pass`および画面写真を
個別に確認する。

生成後に AI が通常変更する場所は `MyApp/app/` だけである。`MyApp/bsp/` は
生成時点の既知動作版を固定したコピーであり、アプリ都合で初期化コードを
作り直さない。

Pico SDK は `--sdk` または `PICO_SDK_PATH` で明示する。picotool は
`--picotool-dir`、`PICOTOOL_DIR`、または `PATH` 上の実行ファイルから探索する。
作者固有の絶対パスには依存しない。

音声モードはCMakeで選ぶ。

```sh
# 動作実績コードをそのまま鳴らす参照経路（既定値）
cmake -S . -B build -DPICO_BOARD=pico -DPICOCALC_AUDIO_REFERENCE_TONE=ON
# AIアプリがPCMを投入する汎用経路
cmake -S . -B build -DPICO_BOARD=pico -DPICOCALC_AUDIO_REFERENCE_TONE=OFF
```

`OFF`では`picocalc::audio::init()`、`write_sample()`、`start()`を使う。
最小コードは`templates/rp2040-basic/examples/audio_stream.cpp`にある。
PSRAMの実用例は`examples/psram.cpp`で、`picocalc::psram::Buffer`が領域境界と
24 byte以下への分割をBSP側で担当する。

## UF2と実機検証の版管理規約

PicoCalcのUF2はSDカードへコピーして使用するため、同じプロジェクト内のUF2名を固定する。
標準templateは`build/picocalc_app.uf2`、PicoTetrisは`build/PicoTetris.uf2`とし、検証版や
ブランチ版でもそれぞれの名前を変更しない。UF2そのものは保存しない。
専用HV-1診断は別プロジェクトであり、そのプロジェクト内では
`diagnostics/bsp-quality/build/PicoCalc_BSP_Diagnostic.uf2`に常に固定する。
どちらもビルドごとに名前を変えない。

版を区別するときは、対象ブランチのソースコミット、BSP版、アプリ版または
ビルドサブコメント、UF2のSHA-256を記録する。特別な実機試験を行う場合も、
版番号／サブコメントをソースへ反映してコミットしてからUF2を生成する。
これにより、実機ログの先頭行に出る識別情報を使って対象を確定できる。通常ビルドは
ビルド時刻によりSHA-256が変わり得るため、同一成果物の再生成が必要な実機記録では
`tools/picocalc.py build --build-timestamp YYYY-MM-DDTHH:MM:SSZ`を使う。同じソース、
BSP、SDK、ツールチェーン、ビルド設定を揃えた場合に限り、対象コミットから同じ
`build/picocalc_app.uf2`を再生成できる。

起動時の最初の機械可読ログは次の形式でなければならない。

```text
[PICOCALC][BOOT] bsp=... app=... variant=... bsp_git=... app_git=... build=...
```

この1行を実機ログの版判定に使う。UF2ファイル名を版識別に使ってはならない。

## 起動時スモークテスト

生成した `picocalc_app.uf2` は、起動時に次を行う。

1. 選択したBSPの基準クロック（A: 125 MHz、B: 250 MHz）、100 ms安定待ち、LCD、PSRAM、キーボードを初期化する（バックライトの明るさは変更しない）
2. LCD を黒・白・赤・緑・青で塗りつぶし、2x2 sampleを`RAMRD (0x2e)`で読み戻して一致比較する
3. LCD に黒・白・RGB の既知パターンを描画し、2x2の書き込み／GRAM readback一致を確認する
4. SD を mount し、`PICOTEST.TXT` を write/sync/close/read/compare する
5. テストファイルを削除する
6. 成功時は画面のステータス領域を緑、失敗時は赤にする
7. キーボード FIFO をポーリングし、キーイベントを UART/USB CDC に記録する

主要ログは次の形式なので、人だけでなく AI も失敗段階を判定できる。

```text
[PICOCALC][LCD][VERIFY] stage=end status=drawn regions=top(0,0,320,24),bottom(0,296,320,24),white(16,48,288,224),inset(20,52,280,216),red(32,72,80,80),green(120,72,80,80),blue(208,72,80,80) colors=top:0x07e0,bottom:0x001f,white:0xffff,inset:0x0000,red:0xf800,green:0x07e0,blue:0x001f
[PICOCALC][LCD][READ] ramrd dummy=0x.. pixels=4 format=rgb565
[PICOCALC][LCD][VERIFY] status=pass pixels=4 mismatches=0
[PICOCALC][LCD][VERIFY] stage=pattern_readback status=pass pixels=4 mismatches=0
[PICOCALC][LCD][VERIFY] app_status=pass
[PICOCALC][SD][SMOKE] stage=begin path=0:/PICOTEST.TXT sequence=mount,write,sync,close_write,read,compare,close_read,remove
[PICOCALC][SD][SMOKE] stage=end status=ok result_stage=ok detail=0
[PICOCALC][SD] component=init status=ok detail=1
[PICOCALC][SMOKE] lcd=ok sd=ok stage=ok detail=0 status_region=green
[PICOCALC][KEY][VERIFY] stage=waiting requirement=multiple_press_release_events
[PICOCALC][KEY][VERIFY] stage=event count=1 state=pressed state_code=1 code=0x.. pressed_count=1 released_count=0
[PICOCALC][VERIFY] stage=ready lcd=ok sd=ok keyboard=waiting
[PICOCALC][READY] keyboard=waiting
```

LCDの`[LCD][VERIFY] app_status=pass`は、塗りつぶしとパターンの書き込み後に
GRAMを`RAMRD`で読み出し、公開APIのRGB565値と一致したことを表す。BはRGB565の
2-byte読出し、AはRGB666の3-byte containerをRGB565へ変換して比較する。
`[LCD][READ]`にはMISOアイドル、RDDID/RDDST、RAMRDダミー、各pixelの生バイト列を出す。
SD エラーは `mount`, `open_write`, `write`, `sync`, `open_read`, `read`,
`compare`, `remove` のどこで発生したかを出力する。

B（`pio-rgb565`）のRAMRDは`life`のスクリーンショット取得ビルドと同じ手順である。
PIOステートマシンを停止してSCK/MOSI/MISOをSIOへ移し、CS保持で`CASET`/`RASET`/`RAMRD`を
送り、ダミー1バイトの後に2バイト/ピクセルをfallingでサンプルし、ピンをPIOへ戻す。
`life`はこの手順で実機のスクリーンショットを正しく取得しているため、読み値が期待と
異なる場合はRAMRDではなく書き込み経路を疑う。

UF2は従来どおり `build/picocalc_app.uf2` として生成する。LCDの`stage=end`は
既知の色パターン描画呼び出し完了、SDの`result_stage`は失敗箇所、キーの`count`は
実機で取得したイベント数と押下／リリース数を表す。LCDの色・向き・ノイズの有無はログだけでは判定
できないため、画面写真と合わせて記録する。

## 検証済み範囲

- Canonical BSP とテンプレートは `arm-none-eabi-gcc 13.2.1`、
  Pico SDK 2.x 系でコンパイル可能
- GitHub Actionsは最低互換条件としてPico SDK 2.0.0を固定し、実機台帳は
  Pico SDK 2.2.0を使う。両方でコンパイルできるAPIを保つ
- `picocalc_app.elf`、`.bin`、`.uf2` の生成を確認済み
- clone単体のportable検証が合格
- 生成器・検証器・異常系のPython回帰テストが合格
- LCD初期化とCS分割は実行可能なhost transactionテストで検査
- `--json`は入力ファイル破損・不正引数でも構造化された失敗を返す
- GitHub Actionsでportable検証、Pythonテスト、RP2040 template compileを実行

実機でBSP 0.2.0のLCD/SD/keyboardスモークを確認した。その後LCDを二系統へ分離し、
Bの転送を無改変コピー、Aの転送を専用vendorドライバへ固定したBSP 0.4.0で、**A/B両方の
LCDが実機表示に成功した**（2026-07-30）。以下の台帳はその時点の履歴である。

- A（`hwspi-rgb888`）：commit `e2d53ad55afa`、LCD/SD/keyboard合格。キーボードは148イベント
  （pressed/released各74）。記録は`bsp-0.4.0-20260730-02.json`。
- B（`pio-rgb565`）：commit `f763b91eae95`、LCD/SD合格。記録は
  `bsp-0.4.0-20260730-01.json`。キーボードはこの記録では未試験。

両記録とも基板revisionとSDカード識別情報が未記入のため、台帳の`overall_status`は
`pending`にしている。LCD A/Bの実機合格自体は、各ログの`app_status=pass`、GRAM readback
全色一致、写真で個別に確定している。

## 最新BSPの実機確認

Canonical BSPは`0.8.8`、標準templateのapp版は`0.8.4-*`であり、
この二つは独立して管理する。`bsp-0.8.8-20260802-01.json`には、
ClockworkPi PicoCalc `CPI2.0`とSanDisk Ultra SDHC 32 GB/FAT32での実機情報を記録した。

- SD: filesystem smoke、`/MUSIC`列挙、MP3/MIDIのEOF到達を確認
- Audio: 3,549,641 samples、underrun/clip/dropがすべて0で、聴感上も音楽・コード・速度を確認
- LCD: 0.8.3の3回起動中2回はGRAM readback合格、1回は不合格で間欠性が残る
- Keyboard: 過去の標準スモークでPressed/Releasedを確認済みだが、0.8.8台帳では未完了

この最初の0.8.8台帳`bsp-0.8.8-20260802-01.json`の`overall_status`は`pending`である。
残るLCDとkeyboardは
専用HV-1診断`diagnostics/bsp-quality`で独立して閉じる。この診断はSDへmount/writeせず、
音声も起動せず、LCD GRAM write/readbackを100回繰り返し、
Up/Down/Enter/Escapeを誘導して最後に`[BSP_DIAG_VERDICT]`を出力する。

BSP 0.8.4から0.8.8までの音声変更は、cross-core SPSC ring、quantizer clamp、
EOF drain half切替、DMA IRQ source再開、wrap-255 duty再構成の等価式への変更である。
0.8.8の実機音声記録により、この経路の連続再生を確認した。

**後続の相関台帳でpendingを解消した（2026-08-05）。** 同一ソース・同一設定のUF2を
3回起動し、LCD readbackは全回合格、keyboardは138イベントを記録した。
`bsp-0.8.8-20260804-02.json`は`overall_status=pass`であり、上記の最初の台帳に残した
pendingを閉じる。過去record自体は時点証拠なので書き換えない。

## エミュレーターの現在地（2026-08-05）

Firmware backend（Milestone 1）はGate 0〜5が完了し、**HELLO-FULLに到達した**。
無改変の公式`Code/picocalc_helloworld`を`picoem-picocalc`の
`ExecutionModel::Serial`上でdirect bootし、次のすべてをPC上で実行できる。

- `Hello World PicoCalc`の描画（HELLO-VISIBLE）
- PIO1/DMA経由8 MiB PSRAMの全域試験（8/16/32/128-bit）を試験範囲を削らずに完走し、
  8,388,608バイト全一致・不一致0
- I2C1のkeyboard controller（address `0x1F`）でbattery・backlightを扱い、
  シナリオから投入したキーをLCDへecho
- PWM初期化の観測（サンプルは再生を開始しないため可聴音は要求されない）
- 未対応MMIO・例外なし、3回連続実行でUART・framebuffer・JSONがバイト一致

現時点で可能なのは、UART0ログの取得、symbol/PCによる到達判定、LCD framebufferの
hash/PNG取得、PSRAM内容の範囲検証、キーシナリオの投入、PWM設定の観測である。
対応・未対応機能は`firmware-validation/capability.json`に記録している。
Gate 6（`picocalc_emu`統合）も完了し、`python3 tools/picocalc.py test --mode firmware`
から固定commitのbackendを駆動できる。R2で上位CLIをschema 2 registryへ接続し、targetの
scenario、SD、LCD variantを含む全device設定、停止理由、必須UART marker、structured report
期待値を自動判定するようにした。BIN/scenario/backend/override不一致は実行前に失敗し、
毎回fresh reportだけを検査する。登録conformance targetはこの1コマンド経路を正典とする。

**Gate 7（Canonical BSP B conformance）も完了した（2026-08-04）。**
`tools/picocalc.py new`で生成した標準template（B: PIO0/RGB565/LCD DMA OFF）が
エミュレーター上で起動し、次を確認できる。

- `[PICOCALC][BOOT]`行と250 MHzクロック設定（`actual_khz=250000`）
- PIO0経由のLCD初期化と既知パターン描画
- SIO bitbang経路でのGRAM readbackによる`app_status=pass`（全色一致）
- 音声参照トーンの`[PICOCALC][AUDIO][VERIFY] status=ok`（underrun 0）
- 3回連続実行でreport・UART・PNGがバイト一致

これによりA（公式サンプル）とB（標準template）の両系統がPC上で観測可能になった。

**実機との相関を確認した（2026-08-05、`bsp-0.8.8-20260804-02`）。** エミュレーターが
検証したBINと同一ソース・同一設定のUF2を実機で3回起動し、BOOT行、250 MHzクロック、
LCDの`app_status=pass`、全5色＋パターンのGRAM readback一致、音声の`underruns=0`が
**すべて一致した**。**「エミュレーターがpassと言い実機がfailする」事例は0件**であり、
これがGate 7の結果を根拠に実機検証を減らしてよい根拠になる。あわせて0.8.8台帳の
LCD・keyboard pendingを解消した（0.8.3で見られた間欠readback失敗は3回とも再現せず、
キーボードは138イベントを取得）。

相関で見つかった**PSRAMの不一致は修正済み**である（2026-08-05）。実機が返した
チップIDを一次情報として`0x9F` Read IDを実装し、その読み出しにもFast Readと同じ
出力遅延を適用した（遅延はチップの出力ドライバの性質でありコマンドの種類とは
無関係なため）。現在はエミュレーターも`status=pass id=0d5d5332c6817946`を返し、
実機と一致する。

**あわせてSPI0のSDカードを実装した。** これで標準templateが全機能を完走する。

```text
[PICOCALC][LCD][VERIFY] app_status=pass
[PICOCALC][SD][SMOKE] stage=end status=ok result_stage=ok detail=0
[PICOCALC][SMOKE] lcd=ok sd=ok stage=ok detail=0 status_region=green
```

SDカードモデルはSPIモードのbring-up（CMD0/CMD8/CMD55+ACMD41/CMD58）と
単一ブロックread/writeを実装する。空volumeは64 MiBのテストgeometryを使い、
filesystemは購入時付属32 GBカードに合わせて**FAT32がデフォルト**で、FAT16は
明示選択できる（BSPはmountするだけでformatしない）。
両形式でmount/write/sync/read/compare/removeの全系列をhost/firmware両backendで通し、
runner reportはschema 8でschema 6の`sd.format`、block数、read/write数、unknown commandを
保持し、さらに規範的な`verdict`を記録する。

schema 8ではcycle limitを暗黙のPassにしない。許可stop reasonと必須UART markerを明示し、
exception、emulator error、unsupported/truncated MMIO、keyboard drop、scenario失敗、stop
mismatch、marker不足を終了コード1にする。判定条件不足またはscenario基盤faultは終了コード2、
すべての条件を満たす場合だけ0である。keyboardの未知register select/writeも
`keyboard_protocol_error`として終了コード1にする。さらにschema 8はrunnerへcompileされた
backend commitとdirty状態を記録するため、古いrunner binaryへCLIから新しいcommitを名乗らせ
られない。R2 accepted backend固定commitは`0d434d789ed2aa0743520eb0d411fa2ced1974e4`である。

R2のactive Template B targetはgenerator commit `82e943ab...0361`、BIN
`1e6abac2...a3d`、PIO-RGB565、PSRAM、keyboard、FAT32を固定する。2回のfresh buildでBIN/UF2が
一致した。sourceは`.git`を保持したclean clone、生成先は全Git working treeの外とし、
`bsp_git=82e943ab1942`と`app_git=untracked`を同時に埋め込む。正規手順は
[`R2_TEMPLATE_B_REPRODUCTION.md`](R2_TEMPLATE_B_REPRODUCTION.md)にある。1コマンド実走で
12億cycle、LCD/SD/READY marker、SD read/write、drop 0、unknown
command/MMIO 0、schema 8 verdict passを確認した。詳細は
`firmware-validation/records/r2-20260806-01/`に記録している。activeの公式A targetも同じ経路で
95億cycle、PSRAM全8 MiB一致、keyboard 4 event、必須marker不足0としてpassした。

**注意:** `--lcd-variant`の選択は性能に影響する。B系統はpin監視デバイスを接続し、
Serial実行をper-cycle GPIO観測へ切り替えるため、A系統のファームウェアで
B（既定値）のまま実行すると到達サイクルが約3分の1に減る。公式サンプルを走らせる
場合は`--lcd-variant hwspi-rgb888`を明示する。どの系統で走ったかはレポートの
`lcd_variant`に記録される。経緯は[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §4.7、
証拠は`firmware-validation/records/`にある。

### Scenario runner（Milestone 3、2026-08-05）

**キー投入のタイミングを制御でき、画面を機械的に判定できるようになった。**
JSONで書いた手順を実行ループの内側で評価するため、1ステップが画面とUART出力を
見てから次のキーを決められる。形式は[`SCENARIO_RUNNER.md`](SCENARIO_RUNNER.md)にある。

```sh
picocalc-run --bin app.bin --board picocalc --lcd-variant pio-rgb565 \
  --scenario scenarios/tetris-line-clear.json --snapshot-dir out/
```

- 操作: `wait` / `wait_cycles` / `wait_until` / `key` / `snapshot` / `assert`
- 条件: `pixel` / `region_non_black` / `region_hash` / `region_stable` /
  `region_changed` / `uart_contains`
- msは仮想時間（ファームウェアが設定したクロックから換算、`clk_sys`変更で再基準化）
- 終了コード 0=合格、1=判定して不合格、2=判定できず

**証明として、ドッグフーディングで一度も発火させられなかったPicoTetrisの
ライン消去を発火させた。** 13ライン、スコア1400。しかも「たまたま何か消えた」では
なく、種を固定した乱数からオフラインで計算した**予測スコアと一致すること**を
`assert`している。証拠は`firmware-validation/records/milestone3-20260805-01/`。

このscenarioが**エミュレーターの欠陥を1件見つけた**。キーボードモデルのFIFOに
上限がなく、滞留が32の倍数に達するとBSPの`key_info[0] & 0x1f`が0を読み、
ドライバが恒久的に停止していた。実機のコントローラは深さを5ビットでしか報告できず
その状態になり得ないため、エミュレーター側の欠陥である。31で頭打ちにし、
溢れを`key_events_dropped`へ数えて警告するよう修正した。

**まだできないこと:** ループ・分岐の構文がない（繰り返しはscenario生成側で展開する）。
条件の評価は`poll_ms`ごとなので、1周期の内側で現れて消える状態は見落とす
（時間待ちの精度は別で、こちらは正確）。レポート項目（`key_events_dropped`など）に
対する`assert`は書けない。

### Host backend（Milestone 2、2026-08-05）

**アプリのロジックをRP2040バイナリを作らずに検査できるようになった。** BSPの公開APIを
ホストのモデルに対してビルドする。詳細は[`HOST_BACKEND.md`](HOST_BACKEND.md)。

```sh
python3 tools/picocalc.py test --mode host
```

`bsp/host/tests/emu_smoke.cpp`が25個の明示的checkと初期化前提を検査し、3回連続実行で
出力がバイト一致する（Milestone 2の完了条件）。FAT32既定化後の現行stdout SHA-256は
`84afb65deb46c3133f19ee22a2212e0e758722d7fa8564fe663dd61af8e82b4b`で、所要は1秒未満。

**firmware backendが権威である。** hostにはPIO・DMA・I2C・割り込みが存在しないため、
ハードウェアの挙動は問いとして成立しない。その代わり次の2点が効く。

- **framebuffer digestが両backendで同じ正規形**（row-major RGB565生バイト列の
  SHA-256）。同じ絵を描いたアプリは両方で同じ64文字を出すので、安いhost実行が
  高いfirmware実行の代わりを務めてよい根拠が取れる
- **`src/filesystem.cpp`と`src/fatfs_diskio.cpp`はデバイスと同一ソースをコンパイル
  する**（Pico SDK依存が無いため）。差し替えるのは下のブロックデバイスだけで、
  hostのファイルシステム試験は代用品ではなく出荷するコードを動かしている

これはhost基盤と専用`emu_smoke`の合格である。任意アプリのソースが自動的に
`test --mode host`へ接続されるわけではない。PicoTetrisについては後続R3で
ライン消去・衝突・回転・seed・resetを666 checksの独立host unit testへ追加した。

**まだできないこと:** directory-backed Fast SDモードは未実装（カードはホストメモリ上の
セクタ配列）。multicore・割り込み・DMA・PIOは存在しない。LCDのwire形式の違い（A/B）も
hostには無く、`verify_pixels`は常に`transport_ok=true`を返す。scenario runnerは
firmware backend専用で、hostのテストはC++で書く。

また、次の機能は今後のエミュレーター段階である。

- directory-backed Fast SDモードと故障注入
- JUnit成果物、100回連続実行の決定性検査
- PIO/DMA、multicoreを使う既存アプリのPC上での実行

最初の可視化到達点と公式サンプル完全合格、ならびにその後のBのFirmware conformanceは
[`EMULATOR_ROADMAP.md`](EMULATOR_ROADMAP.md)に定義する。現在の作業順序は
[`MILESTONES.md`](MILESTONES.md)、実施済みGate計画は
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)にある。エミュレーターの最初の対象がAでも、
Canonical BSPの推奨表示デフォルトはBのままである。

0.8.8は、実機動作済みコードを基準にした参照経路と、AIが利用する汎用経路を
同じBSP内に用意する現行版である。A/BのLCD経路は従来どおり独立しており、音声は
`PICOCALC_AUDIO_REFERENCE_TONE`で切り替える。ログ1行目の
`app=0.8.4-b-pio-rgb565-default`、
`app=0.8.4-b-pio-rgb565-psram-lcd-coexist`、または
`app=0.8.4-a-hwspi-rgb888-rgb666-compat`、音声の`mode=`、PSRAMの`reference=pico_rescue`
を照合する。推奨デフォルトはBのRGB565/PIO blocking/DMA OFFであり、Aは互換・診断用に残す。
ソース検査とA/Bビルドを実施し、0.8.8のSD/音声実機検証まで完了している。標準アプリは
`[PICOCALC][LCD][VERIFY] app_status=`の直後に
`[PICOCALC][AUDIO] status=stopped reason=lcd_verify_complete`を出力し、LCD検証後は無音になる。

したがって現時点の価値は、LCD と SD を毎回 AI が再実装する問題を止めること、
および最初の実機試験で「どこが失敗したか」を一度で観測可能にすることである。
