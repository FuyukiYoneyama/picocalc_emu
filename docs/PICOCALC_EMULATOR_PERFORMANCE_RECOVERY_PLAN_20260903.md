# PicoCalc firmware emulator 性能退行復旧・再構築計画

- Status: **current / R0（高速化開始原点）・R1 complete / G0 clean verification complete / G1〜G7 candidate evidence provisional / G7全体性能checkpointで重大退行を検出しR2停止 / R3・R4・R5未完了**
- Decision date: 2026-09-03
- 高速化開始原点の固定日: 2026-09-04
- Validation repository: `picocalc_emu`
- Implementation repository: `picoem-picocalc`
- 高速な出発点: backend `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- 現行比較点: backend `f32eba1878aeabc6dfc8954b363230ef1e4c2b52`

## 0. 決定

現行backendを約2%の速度から少しずつ最適化する作業を停止する。先に、Tetris（軽ゲーム実装）が
約14%で動作していたbackend `e985a9d...`を高速な出発点として、現在も必要な正確性修正と機能だけを
段階的に積み直す。

これは公開履歴や現在の`main`を過去へresetする作業ではない。現在のbackend、既存target、validation、
測定recordは不変の証拠として保持する。再構築は`/tmp`の一時worktreeで行い、完成した候補の最終的な
source差分だけを、現行backend `main`から派生した統合候補へ適用する。候補branchはremoteへ公開しない。

従来の
[`PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md`](PICOCALC_EMULATOR_PERFORMANCE_PLAN_20260903.md)
はPERF-Q3までの実施記録として保持するが、PERF-Q4、同文書§5の新規候補探索、P1-Aの追加測定を
実行しない。本書を現在の性能作業の正典とする。

### 0.1 高速化開始原点の固定

今後の高速化は、R0（高速出発点と退行比較点の固定）で確認した`e985a9d...`を開始原点とする。
開始原点は、単なるcommit名ではなく、次の組み合わせで固定する。

- backend commit: `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- workload: Tetris（軽ゲーム実装）
- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- configuration: PicoCalc、PIO RGB565、PSRAM、keyboard、SD FAT32、Serial、step quantum 1、host CPU affinity 11
- canonical whole-system checkpoint: process CPU `27.064558677`秒、wall `25.969372348`秒、
  `real_time_percent = 14.305313006%`

この14.305313006%を、今回の再構築で比較する開始時の実測値として一旦確定する。歴史的なOPT1-Bの
14.636593%は過去の別計測protocolによる参考値として保持し、今回の原点値へ混ぜない。R0の別runで
観測された13.960%は環境・runばらつきとして記録済みだが、今後のcandidate checkpointで14.0%未満を
合格へ丸める根拠にはしない。以後、14.0%未満のcandidateは、事前に登録した一段階限定の回復例を除き
失敗とする。G7候補の2.318077413%は原点へ繰り込まず、不採用の退行証拠として保持する。

## 1. この手戻りが必要な理由

確認済みの値は次のとおりである。

| 比較点 | Tetris（軽ゲーム実装）の処理量 | process CPU時間 | wall時間 | 証拠区分 |
|---|---:|---:|---:|---|
| `e985a9d...` 当時の正式値 | 927,528,660 cycles | 当時は未記録 | 25.381594秒 | immutableな既存record |
| `e985a9d...` R0 sidecar再計測 | 927,528,660 cycles | 中央値25.606484秒 | 中央値26.101495秒 | R0のばらつき記録。開始原点は別途固定したcanonical checkpoint |
| `f32eba1...` PERF-Q3 baseline | 927,528,659 cycles | 中央値189.414730秒 | recordへ保存済み | immutableな既存record |
| `f32eba1...` P1-Aなし | 927,528,659 cycles | 190.172395秒 | 193.368972秒 | `/tmp`の1回診断 |
| `f32eba1...` P1-Aあり | 927,528,659 cycles | 191.252047秒 | 194.785231秒 | `/tmp`の1回診断 |

旧地点と現行地点では、同じTetris firmware／scenarioに対するhost計算コストが約7.4倍になっている。
一方、現行地点でのP1-A有無は約0.6%差で、P1-Aなしがわずかに速かった。この1回診断を精密な
P1-A効果量とは呼ばないが、約7.4倍の退行原因をP1-Aの局所比較へ求める根拠はない。

現行計画は`f32eba1...`を次候補のbaselineとしていたため、仮に10%改善しても約170 CPU秒であり、
旧地点の約25.6 CPU秒から大きく離れたままになる。したがって、現行値は高速化の出発点ではなく
**性能退行状態の比較点**として扱う。

## 2. 目的と完了条件

目的は、`e985a9d...`の高速なSerial実装へ、現在必要なguest-visible behaviorと公開機能だけを戻し、
機能追加ごとのhost計算コストを明示したbackendを作ることである。

完了条件は次のすべてである。

1. 現在も維持すると決めたfirmware targetで、cycle／停止理由、UART、framebuffer、audio、SD、PSRAM、
   keyboard、interruptなど、そのtargetが要求するguest-visible observationが現行accepted結果と一致する。
2. Tetris（軽ゲーム実装）のprocess CPU時間を、高速出発点R0の値、直前段階、現行退行点の3方向で
   比較できる。
3. 高速出発点から増えたCPU時間が、採用した機能群ごとの明示的な差分で説明できる。説明されない
   CPU時間増加を、新しいbaselineへ繰り込まない。
4. 使用されていないoptional capabilityや診断処理は、通常Tetris実行へ継続的なper-cycle costを
   加えない。加える実装は移植せず、event-drivenまたは実使用時だけ有効になる形へ直す。
5. 完成候補を現行`main`から派生した統合候補へ適用し直しても、同じ正確性と性能結果を再現する。

最終CPU時間へ先に恣意的な合格率を置かない。R0で確定する高速出発点を`T_fast`、人間が必要性と
代償を明示的に承認した機能群の追加コストを`delta_i`とし、説明可能な最終上限を
`T_fast + sum(delta_i)`として管理する。承認されていない差分を「現在値だから」という理由で上限へ
加えない。

## 3. 対象外

- 1倍速、特定の最終倍率、LOAD-0（最大級の継続負荷性能テスト0番）の完走
- 過去のどのcommitが悪かったかを説明すること自体を目的にした全履歴bisect
- P1-A、P1-B、P2-A、dynamic quantum、OPT2〜OPT4の旧候補をそのまま再投入すること
- profiler、trace、計測器そのものを高速化成果として数えること
- `Picocalc_NESco`、`uf2loader`、PicoTetrisなど外部projectのsource改変、branch作成、公開
- 実機試験。guest-visible差が既存証拠だけで判定できない場合に限り、別の明示判断を行う

## 4. 作業構成とGit境界

### 4.1 再構築lane（高速地点から積み直す場所）

`e985a9d...`をcheckoutした一つの一時worktreeを`/tmp`に作り、必要機能を元の依存順で一群ずつ
再実装または移植する。意味の確定していないbranchを増やさず、remoteへpushしない。各段階は
再現可能なlocal commitにし、段階名、含めた機能、除外した機能、測定結果を作業recordへ残す。

### 4.2 統合lane（現在の履歴を保ったまま採用する場所）

再構築candidateが完了するまで現在のbackend `main`を変更しない。完了後、現行`main`から一つだけ
一時統合candidateを作り、再構築candidateとの差分からproduction sourceと必要testの最終差分だけを
適用する。過去record、公開文書、無関係な履歴を置き換えない。統合candidateで全gateを再実行し、
合格後にだけ`main`へ統合する。force pushや公開履歴の書換えは行わない。

## 5. 固定する性能・正確性契約

### 5.1 正式な比較workload

主workloadはTetris（軽ゲーム実装）に固定する。

- firmware SHA-256: `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`
- scenario SHA-256: `b1cefa5c24eb20739e67f60980898b45e4feba00846c61ef5092bff341aaf208`
- current contract SHA-256: `1a296b1faa9088e22f9939bc61b3963475af7005343038361cf1db4ddcb28a5f`
- execution model: `Serial`
- host affinity: 一つの同じvCPUへ固定し、番号と実効affinityを記録
- 全体性能の主判定値: `real_time_percent = emulated_seconds / emulation_wall_seconds * 100`。14.0%を最低維持値とする
- 実装コストの補助値: `emulation_cpu_ns / guest_cycles`。wall時間の変動要因を切り分けるために同時記録する

ここでいう14.0%は、1倍速の合格率ではない。高速化開始原点であるR0の全体性能を再構築中に
下回らせないための最低維持値である。固定したcanonical originの測定条件で原点を再確認して
14.0%未満になった場合は、candidateの作業へ進まず、計測条件または原点recordを再審査する。

scenario完了cycleは旧地点927,528,660、現行地点927,528,659という既知の1 cycle差があるため、
値を丸めて同一とは書かない。正確性比較では各段階の理由とguest-visible observationを確認し、性能の
約7倍差を分類する際には、この1 cycle差を速度差の説明へ使用しない。

PicoEdit（テキスト編集実装）は`e985a9d...`時点に同じ現在契約がないため、手戻り地点の主anchorへ
しない。PicoEditが初めて現在契約で動作する段階を同アプリの`T_picoedit_first`として固定し、以後の
段階でbaselineを無断更新しない。

### 5.1.1 機能群ごとの全体性能checkpoint

局所的なunit test、peripheral test、またはtarget固有のpassだけでは、次の機能群へ進めない。各G段階の
candidateを作った直後、次のG段階へ入る前に、同じTetris（軽ゲーム実装）の**全体scenario**を1回実行し、
全体の性能を確認する。これは機能群の局所的な効果を測るrunではなく、emulator全体の速度が高速出発点から
退行していないかを検出するための停止gateである。

全checkpointは次の条件を固定する。

1. firmware BIN、scenario、device configuration、runner executable、toolchain、host CPU affinityを
   R0と同じにする。変更が必要な場合は、変更理由と新しいanchorを先に記録する。
2. 同じ一時host-timing harnessで、process CPU時間とemulation区間のwall時間を同じrun-loop境界から取得する。
   14.0%最低維持値の判定には固定式`real_time_percent = emulated_seconds / emulation_wall_seconds * 100`を使い、
   CPU時間`emulation_cpu_ns / guest_cycles`は環境変動と実装差を切り分ける補助値として同時に記録する。
   `report.elapsed_us`だけ、またはrun全体の外部経過時間だけを性能値にしない。
3. `T_fast`（高速出発点）、`T_prev`（直前checkpoint）、`T_regressed`（現行退行点）を同じ表に置く。
   candidateの値を単独で「速くなった」と解釈しない。
4. 直前checkpointからの増加が測定ばらつきの範囲を超えた場合、増加理由を機能群の必須`delta_i`として説明し、
   人間が承認するまで次の機能群へ進めない。未説明の増加は性能退行として扱う。
5. checkpointは原則1回で判定する。平均値を作るための3回、10回、長時間runは行わない。値が判定境界に
   入った場合だけ、原因を明示した確認runを人間が承認する。

全体速度の判定は次のように固定する。

- `R_candidate >= 14.0%`で、正確性も満たした場合だけ、そのcheckpointを通常の合格とする。
- `R_candidate < 14.0%`は原則すべて失敗であり、candidateを通常のbaselineへ更新しない。
- ただし、次の機能群で回復することを**測定前に**予見できる、必須機能の一時的な低速化だけは、
  「暫定受入」として一段階だけ保留できる。暫定受入recordには、低速化の原因、対象target、予想する
  `delta_i`、回復を担当する次の機能群、回復後に戻す最低値`14.0%`、失敗時のrollback地点を先に記録する。
- 暫定受入は合格ではない。次の一段階の直後に同じ全体checkpointを実行し、`R >= 14.0%`へ戻らなければ、
  その機能群を不採用として直前の14.0%以上のcheckpointへ戻る。暫定受入を二段階以上積み重ねない。
- `R_candidate < 10.0%`は重大退行の赤旗とし、予見済みであっても自動的な暫定受入を認めない。直ちに停止し、
  実装差分、artifact、harness、affinity、環境を再確認する。

各checkpointにはwall-clock上限を設ける。まず短い固定cycleのpilotで実行可能性を確認し、全体scenarioの
本runは**1回5分を上限**とする。5分を超えたrunは「遅いが継続」とせず、結果を保存して停止し、測定経路・
candidate差分・計画を再審査する。上限は性能合格値ではなく、無制限に次の試験へ進まないための運用gateである。

### 5.2 短い段階screening

各機能群の実装中は、まずscenarioを付けない固定guest-cycleのTetris probeを、`cycle_limit`停止として使用する。
R0で高速地点と現行退行点を各1回実行し、同じ短いprobeが両者を明確に分離できることを人間が確認した後に固定する。
ただしprobeは実装中の早期screeningに限る。機能群candidateを次へ進める前には、§5.1.1の全体scenario
checkpointを必ず1回実行し、14.0%維持判定を行う。

短いprobeで差が分離しなければ、次の長さを自動実行しない。どのguest phaseが不足しているかを確認し、
probeを一度だけ修正して再審査する。これにより「短い試験が終わったから次は長い試験」という自動進行を
禁止する。

各段階は原則1回だけscreeningする。正確性差、直前段階からのCPU時間増加、または環境変動と実装差を
区別できない結果が出た場合だけ、原因を述べて確認runを追加する。平均値を得る目的だけで3回、10回、
長時間runへ進まない。

### 5.3 段階ごとの停止条件

次のいずれかが起きたら、その機能群を積んだまま次へ進まない。

- guest-visible observationが直前のaccepted段階または現在の要求契約と一致しない
- Tetrisで使用していない機能群が、再現するCPU時間増加を発生させる
- 使用している必須機能のCPU時間増加について、処理内容と必要性を説明できない
- 計測器、feature set、artifact、scenario、toolchain、affinityが前段階から変わっている
- 結果の検討と人間の続行判断を行わず、次の機能群または長時間試験へ進もうとしている
- 全体scenario checkpointが未実施、または全体速度が14.0%未満なのに、§5.1.1の暫定受入条件を
  事前記録せず次へ進もうとしている
- 全体scenario checkpointが5分のwall-clock上限を超えた

必須機能に避けられないコストがある場合は、機能名、利用target、絶対CPU秒、直前比、高速出発点からの
累積値を示し、人間が代償を承認した後にだけ`delta_i`へ追加する。

## 6. 移植する機能の棚卸し

R0完了後、コードを移植する前に`e985a9d...`から現行backendまでの変更を次の機能群へ分類する。
commit数ではなく、ユーザーとfirmwareから見た目的で分類する。同じcommitに複数目的が混在する場合は
commit全体をcherry-pickせず、必要部分だけを再実装する。

| 順序 | 機能群 | 検討する内容 | 移植条件 |
|---|---|---|---|
| G1 | CPU・割込み正確性 | multicore IRQ、level IRQ、watchdog handoffなど | 現行accepted targetが依存する修正だけ |
| G2 | LCD・PIO・PSRAM正確性 | LCD readback、RAMRD、PIO／PSRAM edge semantics | 現行accepted observationに必要な修正だけ |
| G3 | DMA・audio（音声DMA実装） | DMA-paced audio、priority、timer競合、capture | 現行audio targetの契約を満たす最小実装 |
| G4 | headless実行基盤 | stable machine API、heartbeat、report入口 | 現行利用者の実行経路に必要で、emulation hot pathへ不要なcostを加えないこと |
| G5 | flash・SD・boot | G5-A保存領域（RAW SD・NOR flash mutation）、G5-B loader起動（boot2・watchdog warm reset）、G5-C SD protocol（bounded multiblock） | 現行公開capabilityを維持する最小実装 |
| G6 | 外部I2C module | RTC、EEPROM、AHT20、BMP280、観測値 | capabilityを維持する場合だけ。未使用時costを加えないこと |
| G7 | preview境界 | preview API、replay、bounded audio transport | 中断済み1倍計画ではなく、現在の利用経路に必要と確認できた部分だけ |

各機能群について、移植前に次の4点を1行ずつ確定する。

1. どのtargetまたは利用者が必要としているか
2. 移植しない場合に何が失われるか
3. 合否を判定する既存test／recordは何か
4. Tetrisでその機能がactiveかinactiveか

必要性を説明できない機能は移植しない。文書、format-only変更、profiler、過去にrevertされたprototype、
P1-A／P2-Aなどの性能候補はこの棚卸しの移植対象へ含めない。

### G7棚卸し（2026-09-04）

G7は中断した1倍速計画を再開する段階ではなく、現行のactive VRP targetが要求するpreview境界を
失わないための機能群である。registry上の対象は`picotetris-opt1b-vrp2`／`vrp2e`／`vrp2f`／`vrp4`／`vrp5`
と`picoedit-r1-vrp2`／`vrp2e`／`vrp2f`であり、これらのtarget contractを維持するために、次を候補移植の対象とする。

| G7機能 | 必要性 | 移植しない場合 | 既存gate／Tetrisでの扱い |
|---|---|---|---|
| preview API／protocol | active VRP targetのpreview invocationとversioned observationを維持する | preview targetを既存のmachine APIだけで代用することになり、VRP-2〜4の契約を失う | `preview_api_e2e`、machine schema-1 golden、既存VRP-2E／VRP-4 record。preview commandでのみactive、通常のTetris実行ではinactive |
| replay／shared session | preview、machine、batchの同一cycle観測境界を維持する | 三者の再現可能な比較と既存replay contractが失われる | `machine_api_schema1_golden`および三者digest gate。通常のTetris pathには追加のreplayを自動起動しない |
| bounded audio transport | VRP-4のpreview monitorに必要な上限付き音声経路を維持する | preview monitorのdrop／underrun／epoch契約を失う | VRP-4 off／on／forced-drop record。authoritative batch runnerのaudio oracleや通常Tetrisの経路は変更しない |

G4で復元済みのmachine API／heartbeatはG7でやり直さない。`vrp-load0-r1-vslice`と
`vrp-nes0-synthetic-nrom`はpreview-only／歴史資料であり、G7のactive target復元対象から除外する。
旧preview commitの一括cherry-pickは行わず、G6 candidateの現行APIへ必要な境界だけを手動移植する。
候補record作成後もactive target registryは変更せず、統合判断の前にpreview E2E、既存machine golden、
三者観測digest、Tetris短screeningを実行する。

## 7. 実施段階

### R0 — 高速出発点と退行比較点の固定

プロジェクト全体では、手戻りの出発点が本当に高速で、比較方法が同じであることを確定する段階である。

1. cleanな`e985a9d...`へ、現行`--host-timing`と同じrun-loop周囲のprocess CPU sidecarだけを一時適用する。
   production sourceの起点が正確に`e985a9d...`であることと、計測用patch自体のSHAを別々に保存する。
2. Tetris正式scenarioを1回実行し、既存のcycle、UART、framebuffer、timelineと一致することを確認する。
3. 現行`f32eba1...`をP1-Aなしのfeature setで同じ契約により1回実行する。
   top-levelの`--no-default-features`だけでP1-Aなしと判定せず、`picocalc-harness`と
   `picocalc-board`から`rp2040-emu`へ入るdependency defaultも無効化した一時buildを使う。
   現行Tetris契約に必要な`sd-gen1-multiblock`は明示的に有効化する。
   `cargo tree -e features`相当の出力で`decode-invalidation-tag-guard`と`rp2040-emu/default`が
   入っていないことを保存する。
4. 高速地点と退行点の値、runner／backend／toolchain SHA、feature set、host情報を新しい診断recordへ保存する。
5. 短い固定guest-cycle probeを両地点で各1回実行し、段階screeningに使えるか人間が判断する。

R0は精密なP1-A比較や平均値作成ではない。約7倍の両端と、短い判別手段を固定した時点で終了する。

### R1 — 必要機能の選別

プロジェクト全体では、現在の複雑さを無条件に持ち帰らないための範囲決定である。

§6のG1〜G7について必要性、依存関係、既存gate、active/inactiveを表にする。移植順序と除外項目を
人間が承認するまでproduction codeを変更しない。この段階で新しい性能案を追加しない。

### R2 — 高速地点からの段階再構築

プロジェクト全体では、必要な正確性と機能を一つずつ取り戻し、性能退行を混入した地点で止める段階である。

G1から承認済み順序で一群ずつ移植する。各群について、対象unit／integration test、target固有の
正確性確認、短いTetris性能screening、**Tetris（軽ゲーム実装）全体scenario checkpoint**、結果の
人間レビューをこの順で行う。複数群を一つのcandidateへ混ぜない。全体速度が14.0%未満なら、事前に
記録した一段階限定の暫定受入に該当する場合を除き失敗として止める。停止条件に該当した群は、同じ
実装を残したまま次へ進まず、inactive fast pathまたはevent-driven設計へ直す。

### R3 — 現行機能契約の受入

プロジェクト全体では、速い再構築candidateが現在必要なエミュレーター機能を本当に代替できるかを
確認する段階である。

承認した機能群を積み終えた後に初めて、Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）の
正式scenarioを各1回実行する。R2最終candidateからR3へ入る前にも、Tetris全体scenario checkpointを
実行し、14.0%以上を確認する。続いてmulticore、audio、SD、I2C、PSRAMの代表targetを各1回実行する。
差があれば全target回帰へ進まない。代表集合が合格し、性能内訳が説明可能な場合だけ、登録target全件の
最終回帰を各1回行う。

### R4 — 現行mainへの統合可能性確認

プロジェクト全体では、過去の履歴を壊さず再構築結果を採用できる形へ変換する段階である。

現行backend `main`から作った一時統合candidateへ、再構築後のproduction sourceと必要testのnet diffを
適用する。再構築lane固有の診断、worktree path、測定用patchは含めない。R3と同じ代表正確性、全target、
Tetris／PicoEdit性能を再確認する。統合candidateを作った直後、代表正確性へ進む前にTetris全体scenario
checkpointを実行し、14.0%以上を確認する。結果が再構築laneと一致しなければ統合しない。

### R5 — 採用、文書訂正、後始末

統合candidateだけをbackend `main`へ統合する。validation repositoryでは新しいbackend pinが必要な
targetだけを通常のrevision規則で更新する。既存recordを編集せず、次を新しいdecisionとして追加する。

- 約7.4倍の退行状態をbaselineとして扱わない判断
- 採用した機能群と各`delta_i`
- 除外した機能と理由
- P1-Aの旧採用判断を維持するか、実アプリ改善未証明としてsupersedeするか
- 新しい絶対性能anchorと、現行退行点から回復したCPU秒

採用後、一時branchとworktreeを削除する。再現に必要なcommit、コマンド、SHA、decision recordは
Git管理下へ残す。不採用candidate codeをdefault-offで`main`へ残さない。

## 8. 報告形式

段階名だけで報告しない。毎回、次の順で説明する。

1. **マクロな位置づけ:** 高速地点から現在必要な機能を何番目まで戻しているか
2. **今回の内容:** どの利用者／targetのために何を移植したか
3. **正確性:** 何が一致し、何が未確認か
4. **性能:** 高速出発点、直前段階、現行退行点に対するCPU秒
5. **判断:** 採用、再設計、除外、または人間判断待ち
6. **次の作業:** 次に移植する機能と、その開始条件

内部IDやcommit番号だけを、作業内容の説明として使用しない。

## 9. 着手境界

本計画は承認後にR0（高速出発点と退行比較点の固定）、R1（必要機能の選別）を完了した。G0では
e985のクリーンbackendの`rp2040-emu`テストと、既存PicoEdit（テキスト編集実装）のsourceを変更しない
クリーンhost／RP2040 buildを確認した。G1（CPU・multicore・割込み正確性）は、必要部分を一時worktreeへ
移植し、対象test、Tetris（軽ゲーム実装）短screening、NEXT-2A（マルチコア割込み受入実装）scenarioを
通過した。記録は[`rp2040-cpu-recovery-g1-20260903-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g1-20260903-01/)
にある。

G1・G2・G3候補はbackend `main`へまだ統合していない。G1の既受入artifactとのcycle差16は未丸めで記録し、性能改善とは
扱わない。G2はLCD・PIO・PSRAMの必要部分だけを移植し、board／emu／harnessの対象test、Tetris（軽ゲーム実装）
短screening、NEXT-3 A1（LCD readback・SD・PSRAM positive-control）を通過した。G2短screeningのguest-visible
report、UART、framebuffer digest、PSRAM観測は直前G1 controlと一致し、CPU時間は一回screeningのため改善値として
扱わない。記録は[`rp2040-cpu-recovery-g2-20260903-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g2-20260903-01/)
にある。

G3（DMA・audio正確性）は、現行`picocalc-audio-r1`のDMA-to-PWM5_CC契約、PCM／due-cycle／block boundary／
service-latency観測、UART authority markerをclean candidateで通過した。Tetris（軽ゲーム実装）短screeningは
passしたが、G2比で完了cycleが3増えた。この差は復元したaudio timer pacingに由来する候補境界差として記録し、
性能改善とは扱わない。audio sinkは期待値指定runだけで有効にし、通常Tetris runへ常時hashコストを加えていない。
記録は[`rp2040-cpu-recovery-g3-20260903-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g3-20260903-01/)にある。
再構築laneは`/tmp`の一時worktreeだけを使用し、現行backend `main`、target registry、既存validation record、
remote branchは変更していない。G4（ヘッドレス実行基盤）はschema 1 machine APIのgolden要求8件を3回再生して
応答JSONLとsnapshotを完全一致させ、Tetris（軽ゲーム実装）の短scenarioで1秒間隔heartbeat 15回と正常finishを
確認した。G3比のguest-visible差はなく、heartbeatは性能改善値へ使っていない。記録は
[`rp2040-cpu-recovery-g4-20260903-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g4-20260903-01/)にある。
G5（保存領域・起動経路）の棚卸しは完了した。G5-A（保存領域基盤：RAW SD・NOR flash mutation）は、
RAW SD／NOR mutation／mandatory CRCの対象test、clean release build、RAW実行入口、Tetris（軽ゲーム実装）
短screeningを通過した。G4 controlとのguest-visible normalized結果も一致している。記録は
[`rp2040-cpu-recovery-g5a-20260903-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g5a-20260903-01/)にある。
続くG5-B（loader起動：boot2・watchdog warm reset）は、明示`--boot-mode boot2`、watchdog reset event、
flash／SD保持、structured SD traceを候補へ戻し、既存U6の受入条件・scenario・traceと照合した3回回帰と
final flash再attachを通過した。記録は[`rp2040-cpu-recovery-g5b-20260904-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g5b-20260904-01/)にある。
続くG5-C（SD protocol：bounded multiblock）は、CMD18/CMD12 read、CMD23/CMD25 write、protocol
errorのfail-closed、feature-off後方経路、release CLI E2Eをcandidateへ戻した。Tetris（軽ゲーム実装）の
guest-visible normalized projectionはG4 controlと一致し、U6候補3回回帰とfinal flash再attachも通過した。
記録は[`rp2040-cpu-recovery-g5c-20260904-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g5c-20260904-01/)にある。
G5-A／G5-B／G5-C candidateはbackend `main`へ未統合であり、速度改善や1倍速は主張しない。旧U6のraw UF2は
保存されていなかったため、G5-Bはbyte-identicalな旧runの再実行とは称さず、今回再生成した入力hashと
一致したtraceを別recordに固定した。G5-Cも同じ制約のもと、今回の入力hashとcandidate source差分を
新しいrecordへ固定した。G5全体のcandidate差分確認は完了した。

G6（外部I2C module：RTC／EEPROM／AHT20／BMP280）は、G5-C candidateを起点に、明示profileでの
I2C1 mux、共有virtual-time、DS3231／AT24C32／AHT20／BMP280、fixture検証、schema 2 sidecar、
protocol errorのfail-closedを候補へ戻した。既存E5相当の固定`Picocalc_Clock.bin`を3回実行し、
report／I2C sidecar／UART／framebufferをbyte-identicalで確認した。I2C profileなしのTetris（軽ゲーム実装）
短screeningもG5-C normalized projectionと一致し、feature有効／無効のunit testとrelease buildも通過した。
記録は[`rp2040-cpu-recovery-g6-20260904-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g6-20260904-01/)にある。
G6 candidateはbackend `main`、active target registry、既存E5 recordへ未統合であり、速度改善や1倍速は主張しない。
次のG7（preview境界／延期機能）は、active VRP targetに必要なpreview protocol、shared replay／session、
bounded audio transportだけをG6 candidateへ戻した。preview API E2E 5件、rp2040-emu 1,254件、UART／
audio focused test、release buildを通過し、登録済みPicoTetris binaryの通常batch screeningではG6と
normalized guest-visible projectionが一致した。さらに同じPicoTetris binaryを共通replay境界から
実際のpreview processへ接続し、PCRP 14 frame、status 3件、RGB565 frame 1件、PCM frame 8件、Goodbye、
return code 0、backend／IPC drop 0を確認した。記録は
[`rp2040-cpu-recovery-g7-20260904-01`](../firmware-validation/evidence/rp2040-cpu-recovery-g7-20260904-01/)にある。
これはpreview境界の機能candidate-passであり、audio fidelity oracleのpass、性能改善、1倍速、LOAD-0（最大級の
継続負荷性能テスト0番）完走を意味しない。G7 candidateもbackend `main`、active target registry、既存
validation recordへ未統合である。その後、R2の停止gateとして同じTetris（軽ゲーム実装）全体scenarioを
高速出発点とG7 candidateで計測した結果、高速出発点は14.305313006%、G7 candidateは2.318077413%だった。
G7は14.0%最低維持値と10.0%重大退行赤旗の両方を下回ったため、G7機能candidateを全体性能の合格とは
扱わず、R2をここで停止する。R3（現行機能契約の受入）の代表target evidenceは機能確認資料として保持するが、
R3完了、R4（現行mainへの統合可能性確認）、または統合可否判断へは進まない。全体性能evidenceは
[`whole-system-checkpoint`](../firmware-validation/evidence/rp2040-cpu-recovery-g7-20260904-01/whole-system-checkpoint/)
にある。
