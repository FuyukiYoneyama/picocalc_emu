# PicoCalc firmware emulator 性能退行復旧・再構築計画

- Status: **current / plan only / implementation not started**
- Decision date: 2026-09-03
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

## 1. この手戻りが必要な理由

確認済みの値は次のとおりである。

| 比較点 | Tetris（軽ゲーム実装）の処理量 | process CPU時間 | wall時間 | 証拠区分 |
|---|---:|---:|---:|---|
| `e985a9d...` 当時の正式値 | 927,528,660 cycles | 当時は未記録 | 25.381594秒 | immutableな既存record |
| `e985a9d...` 現行sidecarの一時backport | 927,528,660 cycles | 中央値25.606484秒 | 中央値26.101495秒 | `/tmp`診断。R0で正式化が必要 |
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
- 主性能値: `emulation_cpu_ns / guest_cycles`。小さいほどよい
- UX確認値: emulation区間のwall時間。性能の主判定へ代用しない

scenario完了cycleは旧地点927,528,660、現行地点927,528,659という既知の1 cycle差があるため、
値を丸めて同一とは書かない。正確性比較では各段階の理由とguest-visible observationを確認し、性能の
約7倍差を分類する際には、この1 cycle差を速度差の説明へ使用しない。

PicoEdit（テキスト編集実装）は`e985a9d...`時点に同じ現在契約がないため、手戻り地点の主anchorへ
しない。PicoEditが初めて現在契約で動作する段階を同アプリの`T_picoedit_first`として固定し、以後の
段階でbaselineを無断更新しない。

### 5.2 短い段階screening

各機能群の後にfull scenarioを何度も実行しない。まずscenarioを付けない固定guest-cycleのTetris
probeを、`cycle_limit`停止として使用する。R0で高速地点と現行退行点を各1回実行し、同じ短いprobeが
両者を明確に分離できることを人間が確認した後に固定する。

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
| G3 | DMA・audio | DMA-paced audio、priority、timer競合、capture | 現行audio targetの契約を満たす最小実装 |
| G4 | headless実行基盤 | stable machine API、heartbeat、report入口 | 現行利用者の実行経路に必要で、emulation hot pathへ不要なcostを加えないこと |
| G5 | flash・SD・boot | RAW SD、flash mutation、UF2 boot、multiblock | 現行公開capabilityを維持する最小実装 |
| G6 | 外部I2C module | RTC、EEPROM、AHT20、BMP280、観測値 | capabilityを維持する場合だけ。未使用時costを加えないこと |
| G7 | preview境界 | preview API、replay、bounded audio transport | 中断済み1倍計画ではなく、現在の利用経路に必要と確認できた部分だけ |

各機能群について、移植前に次の4点を1行ずつ確定する。

1. どのtargetまたは利用者が必要としているか
2. 移植しない場合に何が失われるか
3. 合否を判定する既存test／recordは何か
4. Tetrisでその機能がactiveかinactiveか

必要性を説明できない機能は移植しない。文書、format-only変更、profiler、過去にrevertされたprototype、
P1-A／P2-Aなどの性能候補はこの棚卸しの移植対象へ含めない。

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
正確性確認、短いTetris性能screening、結果の人間レビューをこの順で行う。複数群を一つのcandidateへ
混ぜない。停止条件に該当した群は、同じ実装を残したまま次へ進まず、inactive fast pathまたは
event-driven設計へ直す。

### R3 — 現行機能契約の受入

プロジェクト全体では、速い再構築candidateが現在必要なエミュレーター機能を本当に代替できるかを
確認する段階である。

承認した機能群を積み終えた後に初めて、Tetris（軽ゲーム実装）とPicoEdit（テキスト編集実装）の
正式scenarioを各1回実行する。続いてmulticore、audio、SD、I2C、PSRAMの代表targetを各1回実行する。
差があれば全target回帰へ進まない。代表集合が合格し、性能内訳が説明可能な場合だけ、登録target全件の
最終回帰を各1回行う。

### R4 — 現行mainへの統合可能性確認

プロジェクト全体では、過去の履歴を壊さず再構築結果を採用できる形へ変換する段階である。

現行backend `main`から作った一時統合candidateへ、再構築後のproduction sourceと必要testのnet diffを
適用する。再構築lane固有の診断、worktree path、測定用patchは含めない。R3と同じ代表正確性、全target、
Tetris／PicoEdit性能を再確認する。結果が再構築laneと一致しなければ統合しない。

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

本書作成時点では計画だけであり、backend source、branch、worktree、target registry、validation recordを
変更しない。人間が本計画を承認した後、R0（高速出発点と退行比較点の固定）から開始する。
