# 実装状況と利用手順

## 現在利用できるもの（BSP 0.9.0、template app 0.8.4-*、RGB565推奨デフォルト）

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
合格した。`CAPS`以外の66キーは任意順・個別retry・timeoutなし・SD progress resumeであり、
`CAPS`は途中で押さず`66/67`の後に最後に押す必須操作とする。途中写真は要求しない。
同じUF2のPicoCalc実機セッションも完了した。LCD、PSRAM、FAT32、audio、PicoTetris、67/67キーが
`io_errors=0 progress=saved overall=pass`で一致し、最終写真、参照音、CRC-validなSD進捗も固定した。
67/67が証明するのは全物理キーのpress/release到達性であり、Caps状態遷移、終了時Caps off、
操作UXはこのR5合格範囲に含めない。

このR5の`audio=pass`は、firmwareのPWM/DMA設定・stream counterとPicoCalc実機の参照音を相関した
時点証拠であり、それ単独ではemulator sample sinkを意味しない。後続NEXT-2Bはdigital sinkのformal
emulator acceptanceに加えて同一UF2実機相関まで完了したため、凍結v3 targetの範囲で`audio-output`はsupportedである。
操作・結果の正典は[`R5_HARDWARE_CORRELATION.md`](R5_HARDWARE_CORRELATION.md)、preflight証拠は
[`firmware-validation/records/r5-preflight-20260808-01/`](../firmware-validation/records/r5-preflight-20260808-01/)
、実機証拠は
[`firmware-validation/records/r5-hardware-20260808-01/`](../firmware-validation/records/r5-hardware-20260808-01/)
にある。後続recordで`hardware_correlation_completed=true`となりOPT1-Aはpromotedである。
高速化は引き続き実機相当の正確性を最優先する。確定した全体計画は
[`EMULATOR_OPTIMIZATION_PLAN.md`](EMULATOR_OPTIMIZATION_PLAN.md)にある。

R5後のOPT1-Bはbackend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`でSerial fast-path gateを
短絡評価する。PIO active時だけ結果を変えない後続predicateを省き、重複DMA判定を除いた。
PicoTetrisのbehavior SHA、173,498,680 event、全9 domain、cycle、timeline、UART、framebufferは
baselineと一致した。trace OFF 10 runのwall中央値は27.122874秒から25.381594秒へ6.419972%短縮、
実時間比は14.636593%となった。Template Bは3 run中央値1.357247%退行で3%以内、公式Helloは
95億cycleと8 MiB PSRAM全域照合を合格した。R5相関firmwareも既存preflightとbackend identity
以外でbyte-identicalであり、既存hardware recordとの推移的同値性を根拠にpromotedである。
証拠は[`OPT1_B_SERIAL_FAST_PATH.md`](OPT1_B_SERIAL_FAST_PATH.md)と
[`firmware-validation/records/opt1-b-20260808-01/`](../firmware-validation/records/opt1-b-20260808-01/)
にある。OPT2 exact event batchingは性能条件未達のまま追加promotionなしで終了した。最初のdispatcher-only候補は、途中で
`clk_sys`変更をbatch境界に含めない誤りをbehavior/event契約が検出した。境界修正後は全eventが
一致したが、同時A/B中央値がOPT1-B `26.16 s`、候補`26.54 s`で約1.45%遅かったためrevertした。
active targetは変更しておらず、次候補は実際のper-cycle orchestrationを減らせるevent horizonを
先に測定してから設計する。OPT2-Bではfeature分離したrunning event-horizon profilerをbackend
`ac0c3052e6c28fcf235a33f98f3a96470d2966f1`へ追加し、同一PicoTetrisで85/85、cycle、UART、
framebuffer一致を維持した。running 308,932,816 cycleのうちpost-hoc candidateは46,411,891 cycle
（15.0233%）、28,608,173 dispatch、2,388,571 intervalだった。これはsafe windowやwall-time上限
ではない。記録は
[`opt2-b-running-horizon-20260808-01/`](../firmware-validation/records/opt2-b-running-horizon-20260808-01/)
に固定した。続くOPT2-Cは、core 1停止、完全horizon、decode-cache hit済みの逐次・bus-free・
1-cycle命令だけをbatchし、behavior/event全9 domainと全counterの一致を確認した。しかし成立したのは
8,420 batch、23,176 cycle（全runの0.002498%）で、trace OFF paired中央値が51.38秒から57.49秒へ
11.89%退行した。candidate `815ef5d`は`c44c87f`でrevertし、active targetはOPT1-Bのままである。
詳細は[`OPT2_C_EXACT_BATCHING.md`](OPT2_C_EXACT_BATCHING.md)にある。次はPIO/UART/DMA deadline
promotionとCPU/decode block workを別々に測って優先順位を決める。OPT2-Dではこの比較を完了した。
PIO/UART/DMA重複signatureのunionはrunningの83.2696%、PIO-onlyは217,025,266 cycle
（runningの70.2500%）だった。decode cache hit率は99.8279%だが、動的sequential hit runは
平均4.563命令だった。このため次prototypeはPIO exact event horizon / bulk advance、UARTは次点、
CPU/decode block workはOPT3とした。証拠は
[`OPT2_D_LEVER_COMPARISON.md`](OPT2_D_LEVER_COMPARISON.md)と
[`opt2-d-lever-comparison-20260809-01/`](../firmware-validation/records/opt2-d-lever-comparison-20260809-01/)
にある。続くOPT2-Eは、全enabled SMが空TX FIFOへの`PULL`で停止している限定状態だけを閉形式で
進めた。candidate `a7ac902`は85/85、cycle、behavior/event全9 domain、UART、framebuffer、
PSRAM tickを完全一致させたが、実workloadの371,982,564 callがすべて1 cycleだった。clean paired
screeningの中央値改善は25.70秒から25.64秒、0.2335%で5%基準に届かず、`a7939e5`でrevertした。
active targetはOPT1-Bのままである。続くOPT2-Fはstationary PIOと、明示opt-inしたPSRAM/LCD/SDの
同一pin sample観測を一つのexact contractへまとめた。candidate `9ec1988`は全eventを一致させ、
23,199,887 outer callで37,012,745回の重複`update_gpio`を削減した。しかしCPU 0固定clean paired
中央値は26.18秒から26.00秒、0.6875%改善で5%条件未達だった。`cdb7584`と`2671d04`でrevertし、active
targetはOPT1-Bのままである。その次候補としてOPT2-Dで次点だったUART deadline promotionを選んだ。詳細は
[`OPT2_E_PIO_PULL_STALL_PROTOTYPE.md`](OPT2_E_PIO_PULL_STALL_PROTOTYPE.md)と
[`opt2-e-pio-pull-stall-20260809-01/`](../firmware-validation/records/opt2-e-pio-pull-stall-20260809-01/)
、[`OPT2_F_STATIONARY_PIN_DEVICE_BULK.md`](OPT2_F_STATIONARY_PIN_DEVICE_BULK.md)と
[`opt2-f-stationary-pin-bulk-20260809-01/`](../firmware-validation/records/opt2-f-stationary-pin-bulk-20260809-01/)
にある。OPT2-GではUART TXのTXRIS/FIFO pop/DREQ境界を対象にしたfail-closed UART-only scheduler
laneをfeature `uart-deadline-prototype`で試作した。実際のrunning fast-forwardはCPU MMIO、clock変更、
DMA orderingを事前証明できないため実装していない。candidate
`593e6d78541722920e1fa903e682d49912eae825`は927,528,660 cycle、85/85、behavior SHA、全9 domain、
UART、framebuffer、PSRAM tickに完全一致したが、CPU 0固定clean A/B/A/B/A/B中央値はbaseline
25.92秒、candidate 28.17秒（`-8.6805555556%`）で5%条件未達だった。exactnessは合格、性能は
不採用とし、`335ecdd7f01cbc5d4f63e18403033bd629efbe77`でrevertした。最終内容はbaselineと一致し、
backend CI run `31287315634`も成功した。active targetとvalidation attestationは変更しない。
OPT2は性能条件未達のまま追加promotionなしで終了した。詳細は
[`OPT2_G_UART_EXACT_LANE.md`](OPT2_G_UART_EXACT_LANE.md)と
[`opt2-g-uart-deadline-20260809-01/`](../firmware-validation/records/opt2-g-uart-deadline-20260809-01/)
にある。OPT3-Aではbackend `0b99b2eabe23205b3c6ac194dcdf016a53de554d`のprofile schema 3で
immutable-XIP lookup/run/invalidationを計測した。85/85、cycle、UART、framebuffer、PSRAM、
behavior/event全9 domainは一致し、XIP hit率99.8287%、hit-only run平均4.563命令、長さ32以上の
massは0.5468%だった。OPT3-Bではscheduler quantumを変えない短いXIP decode cursorを試作し、
85/85、cycle、behavior/event全9 domainを維持したが、trace/proof OFF中央値が25.98秒から
27.13秒へ4.4265%退行した。candidateはrevert済みで、active targetとattestationは変更していない。
OPT3-Cでは既存`DecodedOp`の12 bytesを維持したflags bits 1..6のcompact dispatch keyを試作した。
successor copy、staging、clearなしで、85/85、cycle、UART、framebuffer、PSRAM、behavior/event全9 domainを
一致させたが、trace/proof OFF中央値は26.72秒から25.61秒、4.1541916168%改善に留まり5%条件未達で
revertした。10-run promotion測定は行っていない。性能最適化は一旦区切り、NEXT-1 blind appを
完了した。次優先はmulticore/audio、negative conformance、headless interfaceである。詳細は
[`OPT3_C_COMPACT_DISPATCH_KEY.md`](OPT3_C_COMPACT_DISPATCH_KEY.md)と
[`opt3-c-compact-dispatch-key-20260809-01/`](../firmware-validation/records/opt3-c-compact-dispatch-key-20260809-01/)にある。
[`OPT3_A_XIP_CURSOR_PROFILE.md`](OPT3_A_XIP_CURSOR_PROFILE.md)、
[`OPT3_B_XIP_DECODE_CURSOR.md`](OPT3_B_XIP_DECODE_CURSOR.md)、
[`opt3-a-xip-cursor-profile-20260809-01/`](../firmware-validation/records/opt3-a-xip-cursor-profile-20260809-01/)、
[`opt3-b-xip-decode-cursor-20260809-01/`](../firmware-validation/records/opt3-b-xip-decode-cursor-20260809-01/)にある。

NEXT-1は新規blind app `PicoEdit`として開始した。実装結果へ期待値を合わせないよう、61-byteの
`INPUT.TXT`、固定UI操作、64-byteの`OUTPUT.TXT`とSHA-256、promoted backend、host/firmware/実機の
合否規則を[`NEXT1_PICOEDIT_BLIND_CONTRACT.md`](NEXT1_PICOEDIT_BLIND_CONTRACT.md)と
[`picoedit-contract-v1.json`](../blind-validation/picoedit-contract-v1.json)へ実装前に固定した。
基準BSP 0.8.8に不足していた一般write APIは、BSP 0.9.0のdevice/host共有公開filesystem APIへ
追加した。create/truncate write、sync、stat、remove、renameと個別ErrorをFAT32/FAT16 hostで検査し、
アプリからFatFsを直接使わない境界を維持する。clean generator sourceから新規local repository
`picoedit-picocalc`を生成し、hardware-free editor core、PSRAM正本、FAT32 file list/search/edit、
`OUTPUT.TMP`/`OUTPUT.BAK`安全保存、保存後readback、320x320 UIを実装した。hostは247 assertionsと
反復stdout byte-identical、RP2040 device buildに合格した。canonical buildはapp commit
`82a6e4c76272e8f520d2f8cba42f1a7e549d4933`、BSP commit
`a0041b56516ed56ddff23e80d1900a7c0fc6ab15`、固定時刻`2026-08-09T08:00:00Z`から生成し、BIN SHA-256は
`17cb513b8dd3ea6525ce6bd92d1ce3081bb6ea9730c590c2afb86a9fa085e8f6`、UF2 SHA-256は
`730281ef0070a5cf00610471fec9033a2f53aabebf24f52c3b6f0e520f5c6b73`である。固定scenario
[`picoedit-blind-v1.json`](../scenarios/picoedit-blind-v1.json)は論理段階ごとにUART markerを待ち、
公式keyboard codeを投入する。最初のfirmware blind runは凍結backend `e985a9d7...`へ変更なしで
実行し、一度目で10/10 step、765,299,822 cycles、64-byte readback、固定SHA-256、PSRAM、FAT32、
final framebufferが合格した。exception、unsupported MMIO、key dropはいずれも0である。証拠は
[`next1-picoedit-first-run-20260809-01/`](../firmware-validation/records/next1-picoedit-first-run-20260809-01/)
へ保存した。250 msのrelease drainを追加した正式target `picoedit-r1`も登録し、通常CLI経路で
11/11 step、key delivered 30/remaining 0/dropped 0、正規化reportとtimeline SHAを含む全契約に
合格した。別pathのclean cloneでBIN/UF2も完全一致した（ELF debug sectionは絶対path依存）。証拠は
[`next1-picoedit-r1-20260809-01/`](../firmware-validation/records/next1-picoedit-r1-20260809-01/)にある。
canonical buildの同一UF2によるPicoCalc実機相関も2026-08-09に合格した。実機UARTはBSP 0.9.0、
app/BSP commit、PSRAM、FAT32 load/saveを照合し、64-byte `OUTPUT.TXT`のSHAとreadbackが3回一致した。
SD再読取では`OUTPUT.BAK`も同じ内容で、`OUTPUT.TMP`は残っていなかった。最終写真は
`PicoEdit OUTPUT.TXT 64 bytes`、`status: draft ok`、`SAVED - 64 bytes SHA PASS`を示す。
検索と編集の誤入力はBackspaceで修正しており、連続無誤入力を要求しない回復手順も実証した。
証拠と判定範囲は
[`NEXT1_PICOEDIT_HARDWARE_CORRELATION.md`](NEXT1_PICOEDIT_HARDWARE_CORRELATION.md)および
[`next1-picoedit-hardware-20260809-01/`](../firmware-validation/records/next1-picoedit-hardware-20260809-01/)にある。
NEXT-1は完了し、NEXT-2のmulticore/audio capability範囲拡張へ進んだ。

NEXT-2AはPico SDK公開APIだけを使う新規app `picocalc-multicore`で、core 1 launch、双方向
SIO FIFO固定4-vector、WFE/SEV、`SIO_IRQ_PROC1` deliveryを検査する。期待値は実装前に
[`next2-multicore-v1.json`](../firmware-validation/contracts/next2-multicore-v1.json)へ凍結した。
promoted backend `e985a9d7...`での最初のfirmware runはlaunch/FIFOがPASS、WFE/IRQがFAILとなり、
[`next2-multicore-first-run-20260809-01/`](../firmware-validation/records/next2-multicore-first-run-20260809-01/)
へ改変せず保存した。WFEの失敗はcore 0のdisplay/stdio mutex unlockが発生させるSDK SEVと判明し、
app内のprepare-word barrierで明示SEV区間を分離した。IRQの失敗はSerial backendがSIO FIFOの
`VLD/WOF/ROE` levelを受信core専用NVIC IRQへ投影していなかったことが原因であり、backend
`38683d65800ef36026f674dd47228024d69eb5e7`で修正した。shared peripheral IRQ bitmapは使わず、
core 0 IRQ15とcore 1 IRQ16を個別に再assertする。harnessはcore 1 NMI/HardFaultもfail-closedにする。

正式app commit `9dfb04e1ed6bb4600b4ce4ade6a3a6b72c321837`のBINは
`4d99a40413f31d3b83586083a036325bbe651bcba73297b101bd88a78b451675`、UF2は
`d9fe9beda7a1ba63c98cc811c0009cd8982d84e40f6e1e8066bf46fcc0337de8`である。別々のclean clone
2本から両artifactを再現した。v1 target `picocalc-multicore-r1`を通常CLIで3回実行し、
152,548,085 cycle、615 ms、全phase PASS、exception/unsupported MMIO 0となった。raw report、UART、
2-step timeline、snapshotは3回byte-identicalである。正式証拠は
[`next2-multicore-r1-20260809-01/`](../firmware-validation/records/next2-multicore-r1-20260809-01/)
に固定した。これによりSerialの限定multicore capabilityはsupportedへ移ったが、Threaded、両coreの
同時LCD/PSRAM、spinlock contention timing、core 1 relaunch、DMA-paced PCMは未証明である。

同一v1 UF2の実機最終画面は全5項目PASSだったが、試験完了が約615 msと短く、one-shot markerが
USB CDC列挙前に失われて2回のcaptureが0 byteだった。写真だけで凍結UART要件を満たしたことにはせず、
[`next2-multicore-hardware-attempt-20260809-01/`](../firmware-validation/records/next2-multicore-hardware-attempt-20260809-01/)
へ実機機能PASS・証拠未完了として保存した。

後続`picocalc-multicore-r2`は実装前にlate-attach契約を固定し、phaseや最終画面を変更せず、最終結果
blockだけを1秒周期で再送する。3回の通常CLI、500,000,000-cycle repeat probe、別々のclean clone
2 buildはすべて合格した。2026-08-09、同一v2 UF2の実機ログで完全な5-marker blockを72回、
最終写真で5項目すべてのPASSを確認し、NEXT-2Aを正式完了した。証拠は
[`next2-multicore-r2-hardware-20260809-01/`](../firmware-validation/records/next2-multicore-r2-hardware-20260809-01/)
に固定した。後続の独立契約NEXT-2B audioも現在は完了している。

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

Canonical BSPのsource currentは`0.9.0`、全標準BSP機能の基準台帳は`0.8.8`、標準templateの
app版は`0.8.4-*`であり、この三つを区別して管理する。0.9.0で追加したfilesystem write APIは
PicoEditの同一artifact実機相関に合格した。`bsp-0.8.8-20260802-01.json`には、
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
この旧template音声判定はPWM/DMA設定とcounter/underrunの観測であり、それ自体はPCM sinkの証拠では
ない。後続NEXT-2Bのdigital sink証拠と役割を区別する。NEXT-2Bは同一UF2実機相関まで完了し、凍結v3 targetに限って
capabilityの`audio-output=supported`へ移した。
NEXT-2Bはv3 canonical契約 `next2-audio-v3-20260809` でformal emulator acceptanceを完了した。v1/v2は履歴として保持する。
初回firmware marker/LCD pass後にbackendが24895/49152・hash mismatchを検出してfail-closedした。原因はactive level IRQ二重pending、
v2 oracleのquantizer欠落、128-frame software-retrigger境界gap未分離。backend d92db1bの探索結果は49152 writes、post-quantizer SHA
`1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f`、384 blocks/383 boundaries、intra gap 5208=32640・5209=16128・unexpected=0、
boundary SHA `bb5372879a362de7eff7283322d1eb30b5879660cd87a90b379904253301bc06`。2 clean builds、3 deterministic runs、誤count/hashのfull run、10 report mutationはすべて合格し、記録は`next2-audio-r1-20260809-01`へ固定した。
2026-08-09、同一UF2の実機ログで完全な5-marker blockを18組、動画で約1.05秒の音響出力と最終5-PASS画面を確認した。
証拠は`next2-audio-r1-hardware-20260809-01`へ固定し、NEXT-2Bを完了した。

NEXT-3 negative conformanceを開始した。NEXT3-0ではcase schema、KPI schema、実行前契約を固定し、
negative分母0件の率を`0%`ではなく`null`／`no_negative_denominator`で表すよう機械化した。positive
実機相関は直接4系列とOPT1-B推移的同値1系列の計5件で、positive側の
`emulator PASS -> hardware FAIL`は0件である。最初に監査したLCD 0.3.1候補は、記録された
`51380fa` UF2が実機未確認で、UF2本体・BIN SHA・build timestamp・SDK commit・toolchain版・generatorが
残っていなかった。既存FAILログのboot identityも`5b12a7c`であり同一artifactではない。このため
`artifact_not_reproducible`としてnegative母数へ入れず、現行正常版へCS保持欠陥だけを注入する
明示的fault版へ切り替える。契約、分類、監査結果は
[`NEXT3_NEGATIVE_CONFORMANCE.md`](NEXT3_NEGATIVE_CONFORMANCE.md)にある。

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
出力がバイト一致する（Milestone 2の完了条件）。BSP 0.9.0の現行stdout SHA-256は
`e8061a221d52d838ac89974737a4e254106988706ea8b761ae078cf3419d16aa`で、所要は1秒未満。

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

0.9.0は、0.8.8の実機相関済み参照経路を維持したまま、AIが利用する汎用filesystem write APIを
追加したsource currentである。A/BのLCD経路は従来どおり独立しており、音声は
`PICOCALC_AUDIO_REFERENCE_TONE`で切り替える。ログ1行目の
`app=0.8.4-b-pio-rgb565-default`、
`app=0.8.4-b-pio-rgb565-psram-lcd-coexist`、または
`app=0.8.4-a-hwspi-rgb888-rgb666-compat`、音声の`mode=`、PSRAMの`reference=pico_rescue`
を照合する。推奨デフォルトはBのRGB565/PIO blocking/DMA OFFであり、Aは互換・診断用に残す。
ソース検査とA/Bビルドを実施し、0.8.8のSD/音声実機検証まで完了している。0.9.0の追加APIは
FAT32/FAT16 host検査に加え、PicoEditのFAT32同一artifact実機試験でload、write、sync、rename、
readback、安全backupを相関済みである。標準アプリは
`[PICOCALC][LCD][VERIFY] app_status=`の直後に
`[PICOCALC][AUDIO] status=stopped reason=lcd_verify_complete`を出力し、LCD検証後は無音になる。

したがって現時点の価値は、LCD と SD を毎回 AI が再実装する問題を止めること、
および最初の実機試験で「どこが失敗したか」を一度で観測可能にすることである。
