# PicoCalc firmware emulator 高速化 — 現行計画

- Status: **current / PERF-Q0 complete / opportunity not rejected, step-start-only policy rejected**
- Decision date: 2026-09-03
- Validation repository: `picocalc_emu`
- Implementation repository: `picoem-picocalc`
- Active execution model: `Serial`（PicoCalc firmware検証の正確性基準）

## 0. 決定

1倍速UX qualificationは中断したままとし、現在の高速化プロジェクトから外す。今後の目的は、
**正確性を維持したPicoCalc firmware emulatorで、実アプリの検証待ち時間を継続的に短縮すること**
である。1倍、特定の最終倍率、またはLOAD-0の完走をプロジェクトの成功条件にしない。

現在の作業候補は、`step_quantum engagement gating（周辺装置が観測中でない区間だけ実行単位を
広げる候補）`である。ただし2026-09-03版の提案にある「step開始時の現在状態と1 stepの
ヒステリシス」だけでは、同じstepの途中でCPUがPIO、DMA、CS、I2Cを有効化する
`false → true`遷移を事前に知ることができない。そのままproduction実装へ進めない。

本計画では、該当MMIO／GPIO書込みを実行した命令の直後でCPU batchを終了する
**engagement transition barrier**と、次の割込み・外部入力deadlineによるquantum上限を、
動的quantumの前提条件とする。

高速化の方法は、ゲストCPU cycle、命令、IRQ、DMA／PIO／audio eventを省略することではない。
周辺装置が何も観測できない区間で、同じcycle進行を処理するhost側のscheduler呼出しをまとめる。
内部の関数呼出し回数counterは変化し得るが、命令境界、device event順序、UART、framebuffer、audio、
SD／PSRAM、keyboard、interrupt結果は同じにする。これが「結果を変えずに簡略化して速くする」の
具体的な方針である。性能比較ではartifact、scenario、入力、停止理由、guest cycle数を固定し、
既存の`--host-timing`が測るemulation区間のprocess CPU時間を主指標にする。runner起動・report出力・
host待ちを含むwall時間は、利用者の待ち時間を確認する副指標として別に記録する。

## 1. 何を速くするのか

利用者が実際に待つ次の二つを主対象にする。

| 表示名 | 内部target | 役割 |
|---|---|---|
| Tetris（軽ゲーム実装） | `picotetris-opt1b-vrp5` revision 10 | LCD、keyboard、PIOを含むゲーム経路 |
| PicoEdit（テキスト編集実装） | `picoedit-r1-vrp2f` revision 4 | 編集、SD、keyboardを含むアプリ経路 |

この2 IDはfirmware artifact、scenario、device設定を選ぶための入力識別子として使う。既存targetが
固定した歴史的backend pinをcandidateへ書き換えない。性能実験では同一artifact／contractのSHAを
固定し、cleanなbaseline backendとcandidate backendだけを実験record内で差し替える。採用前に
registry revisionや既存validation recordを更新しない。

性能の主指標は、固定したguest処理量に対する**emulation区間のprocess CPU時間**とする。
具体的には`emulation_cpu_ns / guest_cycles`（小さいほどよい）、または同値の
`cycles_per_emulation_cpu_second`（大きいほどよい）を使う。計測区間は既存`--host-timing`の
`run_loop`直前・直後であり、runner起動、初期化、report出力、subprocess待ち、cooldownを含めない。
guest cycle数、stop reason、guest-visible observationが一致しないrunは性能比較から除外し、成功扱いに
しない。

wall時間は**end-to-endのUX副指標**として必ず記録する。ただしhostのスケジューリング、VM、I/Oを
含むため、1%程度の性能改善をwall時間だけで認定しない。process CPU時間が改善してもwall時間での
利用者待ち時間短縮が確認できない場合は、「emulator計算コスト改善、UX効果未確認」と表記する。
emulated cycles/second、CPU-only MHz相当、subsystem counterは原因帰属の補助指標であり、主指標や
wall時間の代用にはしない。

LOAD-0（最大級の継続負荷性能テスト0番、内部ID `VRP-LOAD-0`）は人工的なstress fixtureとして
保存するが、この高速化プロジェクトのbaseline、開始gate、性能合否には使用しない。3回
determinism、10 virtual分run、1倍qualificationは再開しない。

## 2. 現在分かっていること

- 旧promoted Tetris測定は
  [`history/OPT1_B_SERIAL_FAST_PATH.md`](history/OPT1_B_SERIAL_FAST_PATH.md)に記録された
  wall中央値25.381594秒、実時間比14.636593%だった。これは
  backend `e985a9d...`と当時のtargetに対する歴史的な正式値であり、現在のbackend全体の速度と
  呼び替えない。
- 採用済みP1-A `decode-invalidation-tag-guard（decode cacheの無関係slot破棄を防ぐ変更）`は、
  CPU-only `self-invalidate`で+15.324225%だったが、Tetris（軽ゲーム実装）と
  PicoEdit（テキスト編集実装）の実アプリCPU-time combined rawは+1.218973%だった。
  CPU単体の大きな効果が、実アプリ全体には小さく現れることが確認できた。
- 同じP1-A実アプリrecordのwall pairは、20件で約-13.31%〜+3.77%に振れ、幾何平均効果は約+0.249%に
  とどまった。一方、process CPU-timeのcombined効果は+1.218973%、95% CIは+0.437619%〜+2.006406%
  だった。wall時間を1%級の主判定へ使わない根拠は、既存recordで確認済みである。
- `--psram`によりrun全体が`step_quantum=1`となる一方、TetrisのPSRAM実通信は7 transaction、
  58 byteに限られる。周辺装置が観測していない時間にも1-cycle scheduler costを支払っている
  可能性が高い。
- `picoem-picocalc`には既に`CLOCK_PROCESS_CPUTIME_ID`を使う`--host-timing`経路がある。今回の候補の
  ために新しいwall時計や新しい測定器を作らず、この既存経路を固定guest cycle数と組み合わせて使う。
- OPT2、OPT3、OPT4の過去候補は、小改善、退行、exactness差、または効果未確認として判断済みで
  ある。新しいprocess CPU-time帰属または新しい安全機構がない限り、同じ候補を再実装・再測定しない。

性能指標とCPU最適化数値の定義・出典は
[`RP2040_CPU_MEASUREMENT_LEDGER_20260903.md`](RP2040_CPU_MEASUREMENT_LEDGER_20260903.md)
を正とする。ただし、同ledgerに未収録の旧Tetris wall中央値25.381594秒は、上記history文書を
直接の出典とし、ledger由来の数値として扱わない。

## 3. プロジェクトの原則

1. **正確性を先に守る。** Serialのguest-visible behavior、UART、framebuffer、audio、SD、
   PSRAM、keyboard、interrupt結果を性能のために例外扱いしない。
2. **安い反証を先に行う。** counter、最小fixture、代表2アプリ、全target回帰の順に費用を上げる。
3. **効果を確認してから全回帰する。** 効果不明の候補へ22 targetの長時間回帰を投入しない。
4. **効果量に測定量を合わせる。** 10%以上を狙う構造変更に40 run、27 anchor、60秒cooldownの
   CPU micro-optimization用protocolを流用しない。
5. **実アプリで採否を決める。** synthetic workloadだけでdefaultへ昇格しない。
6. **一度に一候補だけ変える。** candidateの実装、計測器、baseline更新を同じ差分へ混ぜない。
7. **不採用コードを残さない。** `default-off`を理由に候補実装をmainへ恒久保存しない。
8. **既存recordを直さない。** 過去の測定、invalid判定、1倍中断記録はその時点の証拠として保持する。
9. **計画完了を成果に数えない。** 成果は、正確性gateを通ってmainへ統合されたemulator計算コスト
   または利用者待ち時間の短縮、または高コストな誤候補を安価に棄却した記録である。
10. **測定validityと効果を混同しない。** validity gateに失敗したrecordのraw効果は診断値として保持
    するが、性能改善の採用根拠へ戻さない。validity失敗を結果の解釈で帳消しにしない。

既存backend `main`には、不採用P2-Aの`pending-exception-fast-reject`が既定オフで残っている。
これは原則7に対する既知の負債である。PERF-Q0は妨げないが、production候補を作るPERF-Q1より前に、
backendから候補runtime／featureを独立cleanupとして削除する。P2-Aのcommitと測定record、過去recordを
検証する`picocalc_emu`側のreaderは履歴再現用に保持し、P2-Aを再測定しない。PERF-Q0で記録する
backend commitは機会量を観測したsourceであり、PERF-Q3の性能baselineではない。cleanup完了後の
clean commitを新しい共通baselineとして固定し、PERF-Q1候補は必ずそのcommitから作る。PERF-Q3の
開始直前にもbaseline commitとcandidateの派生元を照合し、cleanup差分を性能差へ混入させない。

## 3.1 外部プロジェクトと公開の境界

- `Picocalc_NESco`、`uf2loader`その他の外部projectを改造、branch作成、公開しない。
- PERF-Qはvalidation repositoryがSHAで受け入れ済みのfirmware artifactとrepository-owned scenarioを
  入力にし、外部アプリのsourceを改造・再buildしない。変更対象は`picoem-picocalc`だけにする。
- candidate branchをremoteへ公開しない。採用変更だけをbackend `main`へ統合する。
- host emulatorの内部scheduler最適化なので、実機runを開始gateにしない。guest-visible差が見つかり、
  既存の実機相関だけでは原因を判定できない場合に限り、別の明示判断でhardware correlationを行う。
- target registry、capability、release表記は、採用と全回帰が完了するまで変更しない。

## 4. 現在の候補: PERF-Q（安全なdynamic quantum）

### PERF-Q0 — 機会と危険経路の確認

production codeは変更せず、一つの`/tmp` scratch worktreeで次だけを行う。

1. Tetris／PicoEditのartifact、scenario、contractが利用可能であることをSHAとともに確認し、cleanな
   **Q0観測元backend commit**を記録する。これはPERF-Q3の性能baselineではない。開始時点の候補は
   P1-A採用済み`58e7301...`だが、短縮SHAを仮定せず実際のcommitを保存する。
2. quantumを1のままにして、保守的な`engaged`述語のtrue／false cycle数を
   Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）で各1回数える。
3. `disengaged`で開始したstepの途中にCPUが次を行う最小fixtureを作り、現在状態だけに基づく
   dynamic quantumではq1結果と一致しないこと、または一致する理由を確認する。
   - LCD／PSRAMのCS assert
   - PIO SM enableまたはTX FIFO write
   - DMA start
   - 外部I2C transaction start
4. 次のTIMER、SysTick、DMA、PIO、外部入力scenario deadlineまでの距離を、step開始前に
   quantum上限へ使えるかコード上で確認する。

`disengaged_cycles / total_cycles`は、quantum=1のstep開始時状態だけで数える**機会量の上限値**で
あり、wall-time改善率でも、実際にbatch可能なcycle比率でもない。transition barrierとdeadline capは
window途中でbatchを打ち切るため、実際にまとめられる比率はこの値以下になる。上限値の時点で
両アプリとも20%未満ならPERF-Qを棄却する。どちらかが20%以上でも採用余地が確定したとは扱わず、
transition barrierを実装できない場合は棄却する。述語を事後に緩めて合格させない。

### PERF-Q1 — transition barrierの最小実装

初版は`quantum=16`だけを候補にする。64は同じ変更へ含めない。
P2-A cleanupを独立commitとして完了し、そのclean commitを性能baselineへ固定してから、候補を
同じcommitから派生させる。この順序を満たすまでproduction候補の実装を始めない。

- step開始時にdeviceがengagedならq1
- disengagedなら最大q16。ただし次の既知deadlineまでに短縮する
- CPUがsemantics-affectingなMMIO／GPIO writeを行ったら、その命令の直後でcore loopを終了する
- 終了したcycle幅だけperipheral／PIO／GPIOを進め、次stepをq1で開始する
- q1と同じ命令境界・device順序を維持できない操作は、最初からq1へfallbackする

1 stepヒステリシスは補助防御として使用できるが、transition barrierの代わりにはしない。

### PERF-Q2 — 小さい正確性gate

全target回帰の前に次を通す。

1. transition fixtureのq1／candidate一致
2. 既存`crates/rp2040-emu/tests/psram_pio_edge_interleave.rs`を拡張し、dynamic quantumの
   transition barrier前後でもPSRAMのCS／SCK edge系列がq1と一致することを確認する
3. 既存`crates/rp2040-emu/tests/dma_quantum_invariance.rs`を拡張し、既に契約されている
   q1／q16／q64のTIMER、DMA、audio sink、NVIC結果をcandidate policyでも維持する。SysTickは
   このtestの対象ではないため、既存のSysTick／exception test群を拡張してdeadline直前・一致・
   直後の境界を確認する
4. Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）の通常report、UART、framebuffer、
   behavior trace、対象固有device observation一致

既存testで表せる契約のために重複した新規test fileを作らず、上記fileへcandidate policyのcaseを
追加する。既存の配置では契約を表現できない場合に限り、その理由をrecordへ書いて最小の新規fixtureを
追加する。

比較fieldの事前棚卸しは次で固定する。

| field／group | 性質 | PERF-Q2での扱い |
|---|---|---|
| `psram.tick_count` | `Psram::tick()`のhost呼出し回数 | projection比較から除外し、予測方向を別記録 |
| `step_quantum` | 現在はrun全体の静的スカラ | projection比較から除外し、dynamic時の意味を再定義 |
| `audio_sink.*`、TIMER／DMA event・miss counter | ゲスト駆動で、既存quantum不変testの契約対象 | 全field一致 |
| `flash.erase_count`／`program_count`、`sd.block_count`、`scenario.*` | ゲスト動作または固定入力に由来 | 全field一致 |

除外は`psram.tick_count`と`step_quantum`の2 fieldだけに固定する。これはbaseline projectionの
counter系fieldを棚卸しし、既存`dma_quantum_invariance`が`audio_sink`観測ブロック全体を含めて
不変性を要求していることから導出した。結果を見て除外を追加しない。full report diffも保存し、
除外した2 fieldの変化理由と再定義後の値を記録する。

### PERF-Q3 — 効果screening（process CPU-time主指標）

PERF-Q2合格後に、二つの実アプリでbaseline／candidateをAB・BAの2 pairずつ実行する。これは
効果のscreeningであり、1%級の改善をこのrun数だけで確定する確認試験ではない。開始前に、P2-A
cleanup後のclean baseline commitとcandidateの派生元が同一であることを再確認する。artifact、
scenario、入力、stop reason、guest cycle数も固定し、これらが一致しないrunは性能比較に使わない。

測定は既存`picocalc-run --host-timing`のemulation interval（`CLOCK_PROCESS_CPUTIME_ID`）を使い、
`cycles_per_emulation_cpu_second`を主指標とする。wall時間、`emulation_cpu_ns`、guest cycle数、
stop reason、guest observation digestを全runへ併記する。起動、初期化、report出力、cooldownをCPU
主指標へ混ぜない。

hostで利用可能な単一vCPUを一つ選び、baseline／candidateの全runを`--cpu`相当の同一affinityへ固定する。
選択したvCPUと実効affinityをrecordへ保存し、affinityを固定できないhostではPERF-Q3を開始しない。
これは同一host内の比較条件を揃えるものであり、物理coreの占有や完全なnoise排除を意味しない。
warm-up、60秒cooldown、calibration anchorは使わない。

各アプリのCPU-time効果とcombined効果はpaired log ratioから計算し、95% CIと計算式をrecordへ保存する。
validity gate（同一guest work、正のCPU／wall clock、実効affinity、実行エラーなし、correctness
projection一致）のいずれかに失敗したrecordは、raw値を診断資料として保持するだけで、性能採用の
根拠にしない。

以下の5%は測定誤差の境界ではない。新しい構造的複雑性を追加する候補に対して、保守・回帰リスクに
見合う実用的な効果を要求する費用対効果の基準である。測定誤差の扱いはvalidity gateとCPU-timeの
95% CIで別に判定する。

- combined CPU-time効果の95% CI下限が0以下: **性能改善は未証明**。数値を理由に候補を採用しない
- CI下限が0を超え、候補がコード量・複雑性を増やさない: 1〜5%でも小改善の採用候補にできる。
  ただし1〜5%を性能効果として認定するには、run数を結果後に追加せず、別途事前固定した確認protocol
  で同じCPU-time効果を確認する
- CI下限が0を超え、候補が新しい構造的複雑性を追加する: combined効果が5%未満なら棄却、5%以上
  10%未満ならコード削減・単純化がない限り棄却、10%以上なら全target回帰へ進む
- wall時間はUX副指標とし、CPU-time改善をwall時間の改善と読み替えない。wall時間に明確な実アプリ
  退行があれば、CPU-time効果があってもUX改善候補としては棄却する

2 pairのscreening結果を見て、都合のよい方向へrun数を増やしたり、5%を測定後に変更したりしない。
小改善の確認が必要な場合のprotocol、run数、判定を候補実装前に別recordへ固定する。

### PERF-Q4 — 採用前の全回帰

効果screening合格後に限り実施する。

- 登録済みtarget全件を各1回、固定contractで再実行する
- Tetris、PicoEdit、multicore、audio、SD、I2C外部module、PSRAM大量read/writeを覆う代表集合で
  behavior traceを比較する
- unit、integration、CLI E2E、feature matrixを実行する
- guest-visible差が1件でもあれば、例外を追加せず候補を棄却する

全targetを新revisionへ書き換える必要はない。候補backendの回帰証拠を別recordへ保存し、採用後に
新しいbackend pinが必要なtargetだけを通常のversioning規則で更新する。

PERF-Q0〜Q3のために新しい正式target、capability、release、実機記録を作らない。小さい調査recordと
candidate code以外の成果物を増やさない。

### PERF-Q5 — 採用と後始末

PERF-Q4まで合格した変更だけをbackend `main`へ統合する。不採用candidateは理由、再現コマンド、
必要なcommit識別子をdecision recordへ残し、一時branchとworktreeを削除する。採用candidateも
main統合後に作業branchを残さない。

## 5. PERF-Qが不成立だった場合

次の候補を推測で選ばず、TetrisとPicoEditを各1回だけ使ったprocess CPU-time帰属を先に取得する。
wall時間は副指標として併記する。CPU core、scheduler、PIO、GPIO/device observation、DMA、report／
presentationの大分類だけを測り、細かなcounterを最初から追加しない。

次候補は、両アプリのcombined process CPU-timeを10%以上短縮できる説明があるものに限定する。

- OPT2-C `bounded-exact-batching`（旧候補を新しいCPU-time帰属に基づいて再評価する場合に限る）:
  peripheral scheduler／PIO／GPIOのexact batching
- PSRAM transaction外の観測呼出し削減
- 実アプリで支配的と確認されたCPU hot path

上記OPT2-Cは新案ではなく、登録済み旧候補の条件付き再開である。新しいCPU-time帰属が旧不採用理由を
覆し、combined CPU-timeを10%以上短縮できる説明がある場合だけ、旧recordを参照して再開判断を別途記録する。

Threaded execution、basic-block JIT、PGO、`ux` semantic shortcutは現時点の次候補にしない。
ThreadedはPicoCalcのPSRAM／UART／SPI／I2C／PWM／DMA意味論が未完了で、CPU候補は実アプリ全体の
寄与が小さい可能性が高く、`ux`モードは1倍UX中断判断の範囲にあるためである。

process CPU-time帰属でcombined CPU-timeの10%以上を説明できる大分類が見つからなければ、候補コードを
作らずプロジェクトを一時停止する。小さなmicro-optを無期限に積み上げる計画へ戻さない。
採用改善が出た場合だけ、その採用commitを次のbaselineとしてCPU-timeとwall時間の両方を記録し、
累積短縮率をCPU-time基準で更新する。

## 6. 明示的に停止する作業

- 1倍速UX qualification、`picocalc-run --ux-mode`、realtime capability昇格
- LOAD-0の3回determinism、10 virtual分run、1倍性能判定
- P1-B／P2-Aの再測定または既定化（P2-Aの不採用runtimeを削除するcleanupは除く）
- 既存OPT2／OPT3／OPT4候補の根拠なしの再開
- 構造変更に対する40 measured run＋27 anchor＋60秒cooldown
- 効果確認前の22 target全件回帰

## 7. 現在の次の一手

PERF-Q0（dynamic quantumの機会量上限とmid-quantum遷移危険の確認）は完了した。
実アプリ2件では機会量上限を理由に棄却しなかったが、step開始時だけで判断する方式はfixtureで棄却され、
transition barrierが必要であることを確認した。deadlineはTIMER／PWM／外部境界のexact候補と、
PIO／DMA／SysTick等の1-cycle fallbackに分かれる。Q0の証拠は
[`firmware-validation/evidence/quantum-engagement-20260903-01/`](../firmware-validation/evidence/quantum-engagement-20260903-01/)
に保存した。次はこの記録をreviewし、P2-A cleanup後に新しいclean performance baselineを固定してから
PERF-Q1へ進む。番号だけで報告せず、毎回
「PicoCalc firmware backendのどの待ち時間を、何を守りながら減らす作業か」を併記する。

1倍速UXの旧計画と関連概念は
[`validated-realtime-preview/VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md`](validated-realtime-preview/VRP_1X_PROJECT_SUSPENSION_DECISION_20260903.md)
に従って履歴として保持する。engagement gatingの元提案とレビュー上の補正は
[`QUANTUM_ENGAGEMENT_GATING_PROPOSAL_20260903.md`](QUANTUM_ENGAGEMENT_GATING_PROPOSAL_20260903.md)
を参照する。
