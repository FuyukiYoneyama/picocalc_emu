# Milestones（2026-08-10時点の詳細履歴）

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


**この文書が全体計画の正典です。** 全体の実装順序とMilestone単位の完了条件を
定義します。Firmware Gateの詳細受入条件は`EMULATOR_ROADMAP.md`が定義し、
他文書に出てくる段階表現は本書のMilestone番号へ対応付けます。

Milestone 0〜3の中核受入条件は完了しています。Milestone 4は最初の実機相関まで
到達しています。現行PicoTetris成果物の一意な再現と継続CIへの接続はR3/R4で完了し、
R5専用の単一BIN、回復可能な67キー診断、emulator preflight、同一artifactのPicoCalc実機相関も
完了しました。R5前の観測契約OPT0と、正確性を維持する最初の高速化OPT1-Aは実機相関を通過して
promotedとなりました。R5後のOPT1-Bも全event一致、性能gate、代表workload、R5同値性を通過して
promotedです。R5の現在状態、時点証拠、配布境界を文書と機械検証へ統合し、R6も完了しました。
R6後の保守としてbackendの`hardware_correlated`、`promoted`、`experimental_main`を分離し、
前二者を独立したfirmware CI jobで継続検証する契約へ更新しました。
OPT2は追加promotionなしで終了しました。最初のdispatcher-only候補は正確性契約を通した後、同時A/Bで性能改善がなく
revertしました。その後のOPT2-B running event-horizon profilerは完了し、PicoTetris running
cycleの15.0233%にpost-hoc candidateを観測しました。OPT2-Cでは、そのうち事前証明できる限定
prototypeを実装し、全event一致を確認しましたが、対象は全runの0.002498%に留まり、paired中央値が
11.89%遅かったためrevertしました。OPT2-Dの比較はPIOを第一候補に選び、OPT2-Eで空TX FIFOへの
`PULL`停止を閉形式で進める限定prototypeを実装しました。全eventは一致しましたが、実runでは
全callが1 cycleで、中央値改善は0.2335%に留まったためrevertしました。続くOPT2-Fは外側の
pin/device観測をexactにまとめ、37,012,745回の`update_gpio`を削減しましたが、中央値改善は
0.6875%で5%条件未達のためrevertしました。OPT2-G UART exact scheduler laneはexactnessに合格しましたが、
CPU 0固定clean A/B/A/B/A/B中央値が25.92秒から28.17秒へ`-8.6805555556%`退行したため不採用・revert済みです。
実際のrunning fast-forwardはCPU MMIO/DMA ordering未証明のため実装せず、fail-closed laneだけを試作しました。
OPT2は性能条件未達のまま追加promotionなしで終了しました。OPT3-Aでimmutable-XIP decode cursorの
機会分布を計測し、OPT3-Bで短いcursorを試作しました。全eventは一致しましたが、wall中央値が
4.4265%退行したため不採用・revert済みです。OPT3-C compact dispatch keyも全event一致を維持しましたが、
中央値4.1541916168%改善で5%閾値未達のため不採用・revert済みです。性能最適化は一旦区切り、次優先は
blind app、multicore/audio、negative conformance、headless interfaceです。
NEXT-1はPicoEdit（FAT32 ASCII editor）に決定し、実装前blind契約を
[`NEXT1_PICOEDIT_BLIND_CONTRACT.md`](../NEXT1_PICOEDIT_BLIND_CONTRACT.md)へ固定しました。現行BSPの
一般write API不足を先に記録したうえで、アプリからFatFsへ迂回せず、device/host共有の公開APIを
BSP 0.9.0として追加しました。clean sourceからPicoEditを生成・実装し、247 host assertions、
PSRAM正本、FAT32安全保存、RP2040 canonical buildと固定scenarioまで完了しました。凍結backendの
最初のfirmware blind runは一度目で合格し、結果を保存しました。正式target `picoedit-r1`も登録・
通常CLI再実行・clean clone BIN/UF2再現まで合格しました。同一artifact実機相関も
2026-08-09に合格し、誤入力からの回復、FAT32安全保存、最終写真を含む証拠を固定しました。
NEXT-1は完了し、NEXT-2のmulticore/audio capability範囲拡張へ進みました。NEXT-2Aは、凍結backend
初回runのlaunch/FIFO合格、WFE/SEV・IRQ_PROC1不合格を時点証拠として保持したまま原因を分離し、
SDK由来のSEVとSerial SIO FIFO IRQ投影を修正しました。v1実機では5項目の最終画面がすべてPASSに
なりましたが、起動後615 msまでの一回限りのmarkerをUSB CDC列挙前に出し終え、2回のログが0 byteに
なりました。凍結契約のUART要件は緩めず、この結果を`evidence_incomplete`として保存しています。
実装前にv2 evidence契約を固定し、最終marker blockを1秒ごとに再送する
`picocalc-multicore-r2`を3回決定一致、clean clone 2 build、late-attach probeまで合格させました。
2026-08-09、同一v2 UF2の実機ログで完全な5-marker blockを72回、最終写真で全5項目PASSを
確認し、NEXT-2Aを正式完了しました。NEXT-2B audioもexact digital sinkと同一UF2実機相関を完了し、次はNEXT-3 negative conformanceです。
詳細な順序は本書の「現在の実行順序」に従います。完了済みMilestoneの記述は、
基盤が存在することを示すものであり、個別アプリがその基盤へ接続済みであることまでは
意味しません。

Canonical BSP 0.8.8の実機台帳は
`hardware-validation/records/bsp-0.8.8-20260804-02.json`で`overall_status=pass`となり、
LCDとkeyboardのpendingを解消しました。0.4.0台帳に残る`pending`は、当時の装置識別情報や
未試験項目を後から補わないために保持する履歴状態であり、0.8.8の現在状態ではありません。

Firmware backendの開発方針は
[`FIRMWARE_BACKEND.md`](../FIRMWARE_BACKEND.md)に定義します。主バックエンドは、
`0x4D44/picoem`から独立派生した`FuyukiYoneyama/picoem-picocalc`です。

## 他文書との対応

過去に複数の文書がそれぞれ独自の段階番号を持っていたため、対応表を残します。
番号が食い違う場合は本書を優先してください。

| 本書 | `DESIGN.md`（旧Phase番号） | `REQUIREMENTS.md §7`（旧優先順位） | `EMULATOR_ROADMAP.md` |
|---|---|---|---|
| Milestone 0 | Phase 1 MVP | 1〜4 | — |
| Milestone 1 | Phase 3 | 7〜9 | Gate 0〜7 |
| Milestone 2 | Phase 2 の host 部分 | 6 | — |
| Milestone 3 | Phase 2 の scenario 部分 | 6 | — |
| Milestone 4 | Phase 0 の golden 採取＋Phase 4 の HIL | 5 | — |
| Milestone 5 | Phase 4 の高互換性部分 | 10 | Gate 7完了後の拡張 |

`EMULATOR_ROADMAP.md`のGateだけは階層が異なります。Gateは現行Milestone 1の
Firmware backendを分割したものであり、本書と競合しません。

**順序変更の記録:** `DESIGN.md`のPhase 0は、ロジックアナライザによるSPI/I²Cトレース
採取とgolden採取を最初に行う計画でした。現行計画ではこれをMilestone 4
（Hardware correlation）へ移しています。Canonical BSPを先に固定した方が、採取すべき
golden の対象が確定して手戻りが少ないためです。`DESIGN.md §7`のPhase番号は
歴史的記述として残っており、実行順序としては本書が優先します。

## 現在の実行順序（2026-08-09 backend role/CI整合反映）

以下は新しいMilestone体系ではありません。完了済みMilestone 0〜3を再現可能な
継続回帰として固め、Milestone 4の継続相関へ進むための作業パッケージです。
`IMPLEMENTATION_PLAN.md`はMilestone 1のGate 0〜7を実施した当時の詳細計画であり、
今後の順序は本節を優先します。

検証は次の三層に分けます。

1. **host unit test** — アプリの純粋ロジックを高速に保護する
2. **firmware scenario** — 実際のRP2040 BINとPicoCalc device modelを通す権威ある自動判定
3. **hardware correlation** — 同一BIN SHA-256を実機で確認する最終相関

Host backendが存在することと、PicoTetris自身のhost unit testが存在することを混同しません。
Firmware runnerが終了コード0を返すだけでも合格にしません。targetが宣言したscenario、
停止理由、UART marker、exception、未対応MMIO、key drop、LCD・PSRAM・SDの期待値を
構造化reportから判定します。

| 順序 | 作業パッケージ | 主な対象 | 受入条件 | 状態 |
|---|---|---|---|---|
| R0 | 基準点・生成契約・provenanceの固定 | `picocalc_emu`、`picotetris` | 開始baselineとして3リポジトリのcommitと合否契約schemaを記録する。生成後metadataのBSP版が`bsp/VERSION`と一致し、必要なlicense/noticesとローカル参照が揃う。PicoTetrisを固定source identityから再取得できる | **完了（2026-08-05）** |
| R1 | backend verdict・reportの厳密化 | `picoem-picocalc`＋`picocalc_emu` host | cycle切れ、必須marker不足、scenario失敗、exception、未対応MMIO、key dropを誤ってPassにしない。SDを含む必須観測値をstructured reportへ出す。keyboard modelは[公式`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)を一次リファレンスとしてregister/FIFO/state/modifier/repeat/overflowをconformance testする。SDはFAT32既定/FAT16明示profileを両backendで通す。正常系・異常系のRust/C++ testが合格する | **完了 2026-08-05**。R1-SD、verdict、公式keyboard conformanceを完了 |
| R2 | Firmware CLI・target registryの一般化 | `picocalc_emu`＋backend | R1完了commitをaccepted backend pinとし、source/toolchain/BSP/BIN/device/scenario/期待reportを構造化登録する。CLIが宣言どおりrunnerへ渡し、wrong BIN・scenario・backend・LCD variantが明示的に失敗し、正しいtargetが1コマンドで合格する | **完了 2026-08-06**。schema 2 registry、schema 8 backend build identity、Template B実走合格 |
| R3 | PicoTetrisの正式回帰化 | `picotetris`＋`picocalc_emu` | ゲームロジックをhardware-freeに分離し、全7形状・回転・境界衝突・1〜4ライン・score・固定seed・game-over/resetをhostで検査する。固定条件のfresh build 2回でBIN SHAが一致する。firmware scenario 3回が85/85、13 lines、score 1400、key delivered 362/drop 0、exceptionなし、unsupported MMIO 0となり、UART SHA・framebuffer SHA・正規化report/timelineが一致する | **完了 2026-08-06**。666 host checks、再現可能BIN/UF2、active target、3回決定一致 |
| R4 | 品質ゲートとCI | 3リポジトリ | clean cloneから同じpinで再現する。`picotetris`はunit＋RP2040 build、backendはtest＋fmt＋Clippy、`picocalc_emu`はportable＋host＋target/schema＋firmware regressionを実行し、失敗した層を特定できる | **完了 2026-08-06**。3リポジトリのclean-runner full gate合格 |
| R5 | 現行成果物の実機相関 | `picotetris`＋`picocalc_emu`＋実機 | `picotetris-r5`の同一BIN/UF2でLCD・line clear・game-over・restart・PSRAM・SD・audioと公式FW由来67キーを確認する。自動ゲーム診断後、`CAPS`以外の66キーは任意順・個別retry・SD進捗resume可能とし、`CAPS`は途中で押さず`66/67`の後に必ず最後に押す。途中写真を求めない。UF2 SHA、UART全文、最終PASS写真1枚、音確認を新規台帳へ保存する | **完了 2026-08-08**。`r5-hardware-20260808-01`で最終verdict、写真、参照音、SD進捗67/67を固定。67/67は到達性の証拠であり、Caps状態遷移・終了時Caps off・操作UXは合格範囲外。OPT1-A promoted |
| R6 | 文書・配布状態の最終確定 | 3リポジトリ | README、status、Milestones、dogfood記録、target、license/noticesが用語と時点を一貫して記述し、現在状態・時点履歴・未実装を明確に区別する。第三者がclean cloneから再現できる | **完了 2026-08-08**。R5 recordを機械検証へ接続し、README/status/Milestones/dogfood/OPT1-AとPicoTetris文書を現在状態へ同期。既存CI再現契約とlicense/noticesを確認 |
| R6-M | backend role/CI整合保守 | `picocalc_emu`＋backend | 実機相関済み、現在promoted、実験中mainを機械可読に分離し、相関baselineとpromoted targetを別々のCI jobで固定source/BIN/UF2/backendから再現する。audioの実機証拠と未実装PCM出力を混同しない | **完了 2026-08-09**。capability schema 2、role/target/CI相互検証、R5相関job＋OPT1-B promoted jobを接続 |
| OPT1-B | Serial fast-path gate | `picoem-picocalc`＋`picocalc_emu` | PIO active時の不要predicateと重複DMA判定だけを省き、全event digest、主性能5%、代表workload退行3%、R5相関contractを守る | **promoted完了 2026-08-08**。全9 domain一致、PicoTetris 6.420%短縮、Template B退行1.357%、公式Hello/R5同値性合格 |
| OPT2 | exact event batching | backend＋firmware regression | CPU running区間を含め、全boundary eventのcycle/orderを変えず、有意な性能改善を得る | **終了 2026-08-09（性能条件未達）**。OPT2-G UART laneまでexact候補を検証し、追加promotionなし。棄却候補はrevert・証拠固定済み。OPT3 CPU/decodeへ移行 |
| OPT3 | CPU/decode高速化 | backend＋firmware regression | immutable XIPとmutable codeを分離し、exception/IRQ/invalidation/scheduler順序を変えずdecode/execute overheadを削減する | **OPT3-C完了・不採用 2026-08-09**。全event一致、中央値4.1542%改善だが5%未達でrevert。性能最適化は一旦区切る |
| NEXT-1 | 新規blind app回帰 | 新規app＋3リポジトリ | PicoTetris固有の実装・scenarioへ最適化せず、受入条件を先に固定した新規単一core appをエミュレーターで完成させ、同一artifact実機相関で未知workloadへの一般化を測る | **完了 2026-08-09**。PicoEdit v1 blind契約、BSP 0.9.0、247 host assertions、PSRAM/FAT32/UI、canonical BIN/UF2を実装。初回blind run、`picoedit-r1`登録、CLI回帰、clean clone再現、同一UF2実機相関に合格。`next1-picoedit-hardware-20260809-01`へUART、SD入出力、backup、最終写真、誤入力回復を固定 |
| NEXT-2 | capability範囲拡張 | backend＋新規app | multicore launch/SIO FIFO/WFE-SEV/IRQと、DMA-paced PCM sample sinkを別々のfail-closed gateで実装・相関する。設定/counter合格と実PCM出力を混同しない | **NEXT-2A／NEXT-2B完了 2026-08-09**。NEXT-2B v1/v2は履歴として保持。2 clean buildsと3 firmware runsが決定一致し、49152 writes、post-quantizer SHA `1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f`、384 blocks/383 boundaries、intra gap 5208=32640・5209=16128・unexpected=0を合格。誤count/hashのfull runと10 report mutationもfail-closed。同一UF2実機で18 UART blocks、最終5-PASS画面、約1.05秒の音響captureも合格し、bounded audio-outputをsupportedへ移した |
| NEXT-3 | negative conformance | backend＋実機証拠 | 実機で壊れる既知版をエミュレーターもFAILにし、正常版→PASS、故障版→FAIL、修正版→PASSの履歴とfalse-acceptance KPI母数を増やす | **完了 2026-08-10**。旧LCD候補1件はartifact再現不能、明示的LCD fault 2件は`inconclusive`。SD CMD8 bad-CRCでA1 emulator／実機PASS、Fault B実機R1=`0x09` FAIL、凍結backendの初回PASS=`false_accept`を固定した。backend `5edca80`のmandatory CRC7修正後は同一Fault BINが同じR1理由でFAIL、A1/A2はPASS。候補4、negative母数1、artifact failure 1、inconclusive 2、positive相関7系列。versioned KPIは初回検出0/1・false accept 1/1と、post-fix検出1/1・false accept 0/1を両方保存。母数1から一般率へ外挿しない。ローカル検証のみ、CI未使用 |
| NEXT-4 | 安定headless machine API | backend＋scenario runner | `run` / `step` / `run_until` / `input` / `observe` / `subscribe` / `snapshot`の小さなAPIを定義し、既存scenario runnerを利用者として載せる | **完了 2026-08-10**。JSONL schema 1、共有`MachineSession`、7操作、決定的pull型subscribe、fail-closed field/device/input/path境界を実装。API transcript 3回byte一致、all-feature test 62件、既存PicoTetris 85/85と正規化report byte一致をローカル確認。CI／pushなし |

依存関係は次のとおりです。R0とR1は並行できますが、R2は両方の完了後に行います。

```text
R0 生成契約・source identity ─┐
                               ├→ R2 CLI/registry → R3 PicoTetris → R4 CI
R1 backend verdict/report ─────┘                                  ├→ OPT0/OPT1候補 ─┐
                                                                 └→ R5 実機 ←──────┘ → R6 配布
```

各パッケージの終了時にREADME・`IMPLEMENTATION_STATUS.md`・capability・target/recordの
該当箇所を同じ変更単位で更新します。旧hardware/firmware recordは時点証拠なので書き換えず、
後続recordまたは現在状態の文書から参照します。Solが仕様・受入・統合を担当し、Spark workerは
小さく明確なコード修正、Luna workerは明確で反復的・大量な作業を行います。責任境界と構成不調時の
停止規則は`DEVELOPMENT_WORKFLOW.md`に従います。

### R1のSD/FAT32受入条件

着手時のfirmware backendとhost backendは、どちらも64 MiBの空FAT16 volumeをコードで
生成していました。SPI command/block read/writeとChan FatFs自体はFAT16専用ではなく、
実機ではSanDisk Ultra 32 GB/FAT32が合格済みです。この差をR1-SDで解消しました。

R1では次を満たします。

1. firmware runnerに`--sd-format fat32|fat16`を追加し、`--sd`なしの指定はエラーにする。
   `--sd`単独は購入時付属32 GBカードに合わせてFAT32、FAT16は明示指定とする。
2. FAT32 profileは有効なBPB、FSInfo、backup boot sector、root cluster、2面のFATを持つ。
   64 MiB cardでもFAT32判定に必要なcluster数を満たすgeometryを使用する。
3. host backendにも同じ`fat16`/`fat32`選択を設ける。両profileでBSP自身の
   mount/write/sync/read/compare/removeを実行する。
4. reportとtarget registryへ選択したSD形式を記録し、形式の取り違えを合格にしない。
5. FAT16既存回帰とFAT32新規回帰を各3回実行し、終了状態、UART、filesystem結果、
   読み書きsector数が決定的に一致する。

raw imageのload/saveやdirectory-backed Fast SDはこの受入条件とは分離し、FAT32対応を
それらの大きな機能に依存させません。

### 実装着手時レビュー（2026-08-05、時点記録）

**判定はGOです。** 公式keyboard producer、既存FAT16の境界、FAT32で追加する構造、
CLI/report/target契約、host/firmware共通の合否条件まで決まっており、未決の製品判断は
ありません。portable検証39件、Python 24件、host smoke 3回決定一致、Rust board 56件、
runner 24件、doctest 1件が合格しています。

この判定時には3リポジトリに統合文書差分があったため、ソース実装を混ぜる前にR0として
この文書・catalog・capability・baseline test結果をレビュー可能な変更単位へ固定する方針と
した。R0とR1-SDはその後完了している。以下は着手時に定めたR1-SD実装順の履歴である。

1. Rust側にvolume format型とFAT16/FAT32 geometry単体試験を追加する。
2. `SdCard`生成器へFAT32 profileを接続し、block readでBPB/FSInfo/FAT/rootを検査する。
3. runnerの`--sd-format`、引数エラー、structured reportを追加する。
4. host側に同じformat選択を追加し、共有Chan FatFsのsmokeを両形式で実行する。
5. target registryへ形式を固定し、FAT16/FAT32各3回の決定性回帰を記録する。

keyboard conformanceは同じR1内の独立作業であり、R0固定後はR1-SDと並行できます。

### R0実装結果（2026-08-05）

R0は完了した。開始commit、合否schema、R1既知gapを
[`R0_BASELINE.md`](R0_BASELINE.md)と`provenance/r0-baseline.json`へ固定した。
generator metadataをschema 2へ更新し、`bsp/VERSION`、source commit、dirty状態、BSP実体
SHA-256を生成時に記録する。生成先用のMIT Licenseと自己完結したthird-party noticesも
追加した。

PicoTetrisは元の生成commitを推測せず、完全一致するcanonical BSP commit
`cbfc90467e2b8392fbd0429c83925b94ca365824`を根拠に`kind: reconstructed`として復元した。
R0時点ではremoteを作らず、R0固定commitを含む完全Git bundleとSHA-256を保存した。
R4準備でprivate remoteを追加した後も、このR0時点のbundleと`remote: null`は維持する。
`picocalc.py verify --r0 --workspace-root ..`が固定commit、metadata、BSP hash、license/notices、
bundleを検査する。R0完了時点ではR1-SDだけが先に完了し、verdictと公式keyboard conformanceは
未完了だった。両項目はその後2026-08-05に完了している。

### R1-SD実装結果（2026-08-05）

R1-SDは完了しました。Rust `SdCard`とhost block deviceの両方でFAT32を既定にし、FAT16を
明示profileとして保持しました。FAT32はBPB、FSInfoとbackup、backup boot sector、
root cluster 2、2面FATを持ちます。runner schema 6の`sd.format`に選択形式を記録し、
template targetも`fat32`を明示固定します。targetの現行backend pinはR1-SDを含む
`6a618010dc8b8217b6035951b361dc859f472301`で、Gate 7時点の`b285fa22...`は履歴として
別フィールドに保持します。これはR1全体のverdict hardening完了を意味しません。

- Rust board test: 61件合格（FAT profile構造試験5件を含む）
- runner test: 26件合格（CLI依存条件とSD report試験を含む）
- host CTest: FAT32/FAT16両形式で共有Chan FatFs smoke合格。既定FAT32の`emu_smoke`は
  3回バイト一致（stdout SHA-256 `84afb65deb46c3133f19ee22a2212e0e758722d7fa8564fe663dd61af8e82b4b`）
- firmware: 同一BIN SHA-256 `3fdb8231c164dbec73c17b556a964d9c16da44ae7ae6cbf615d39b7b08b934a5`
  でFAT32/FAT16ともSD smoke合格、exceptionなし、unsupported MMIO 0
- FAT32 report 3回一致: SHA-256 `7d62d9cfc71ebb85d066ab9846271ba73c06f63d32c6f8db18bbfa5f088b5df0`
- FAT16 report 3回一致: SHA-256 `9bd503e0cb4d49f9cf90fb88f1ddf5d02a76930cba435c825d4852329319a954`
- UARTは両形式・全6回一致: SHA-256 `71ff8d89a478f9df8f3da784dab84a3f0ed967f666d851700fbc39c22c733830`

このSD試験に使った旧template BINはLCD readbackがfailでもscenarioなしならrunner終了0に
なる問題があった。このfalse passは次のR1 verdict実装で解消した。SD時点のschema 6 recordは
履歴証拠として書き換えず、schema 7以降の判定とは区別する。

### R1-verdict実装結果（2026-08-05）

backend commit `914fcef65b5fe662142c3bdf529c5754aada4954`でrunner reportをschema 7へ更新した。
`verdict.status`、安定したreason code、許可stop reason、必須UART markerと不足markerを記録し、
同じ判定値からprocess終了コード0=pass、1=judged failure、2=cannot judgeを返す。

- exception、emulator error、unsupported MMIO、MMIO log truncation、keyboard dropは常時fail
- scenario assertion・timeout・未完了、stop mismatch、必須marker不足はfail
- scenario実行基盤のI/O/model faultはcannot judge
- cycle limitは`--expect-stop cycle_limit`で明示許可しない限りPassにしない
- markerだけ、空marker、競合stop条件を誤ってPassにしない

Rust board 61件、runner 33件、doctest 1件、Clippyが合格し、実processで2/0/1の終了コードと
schema 7 verdictの一致を確認した。上位`picocalc.py`とtarget registryがこの期待値を構造化して
runnerへ渡す作業は当時R2へ残し、後述のR2実装で完了した。

### R1-keyboard実装結果（2026-08-05）

backend commit `d54ee24d816d4595f2ee750f25ccd7e44f103a22`で、公式STM32 firmwareを一次資料に
consumer-visibleなregister `0x01`から`0x0e`、31-event FIFO、state、modifier、lock、
hold/repeat、overflow、両backlight、battery、reset、C64、power-offを固定した。公式7×8 matrixと
12 direct buttonのkeymapも物理transition APIに写し、既存の論理key injectionとは分離した。

runner reportはdrop/overwrite、内部config/interrupt、lock、両backlight、unknown register
select/writeを記録する。未知selectまたはunsupported writeを`keyboard_protocol_error`としてfailに
するため、実装していないkeyboard registerをACK後に捨ててPassにする判定漏れも解消した。

Rust board 72件、runner 33件、doctest 1件、Clippyが合格した。一次ソースidentity、実装範囲と
GPIO scan/PMU lifecycle等の意図的な境界は[`KEYBOARD_CONFORMANCE.md`](../KEYBOARD_CONFORMANCE.md)に
記録した。これでR1は全項目完了し、次はR2である。

### R2実装結果（2026-08-06）

R2は完了した。`firmware-targets.json`をschema 2へ更新し、active targetをsource/toolchain、
exact BIN/scenario SHA-256、backend build、device設定、accepted stop、UART marker、任意階層の
report checkからなる不可分の契約にした。CLI overrideは契約と同値の場合だけ許可し、違いは
runner起動前のjudged failureとして明示する。

backendはbuild時の実commitとdirty状態をrunnerへ埋め込み、report schema 8の
`backend_build`へ出す。CLI引数で古いbinaryに新しいHEADを名乗らせることはできない。
CLIは一意な一時reportを使うため既存JSONを再利用せず、report欠落・破損・必須field不足、
runner exitとverdictの不一致を終了2にする。判定済みfailureの1、cannot-judgeの2も潰さず返す。

Template Bをgenerator commit `82e943ab1942ef869e9bff38ae6fcf8074930361`から2回fresh buildし、
BIN `1e6abac...a3d`とUF2 `1ab0d16f...c757`が一致した。異なる絶対build pathを含むELFは一致
しなかったため、ELFのpath非依存再現性は主張しない。再現には、上記commitのclean Git cloneを
sourceとして保持し、生成先だけを全Git working treeの外へ置く必要がある。これにより埋込み値は
`bsp_git=82e943ab1942`、`app_git=untracked`となる。完全な環境・コマンド・SHA検査は
[`R2_TEMPLATE_B_REPRODUCTION.md`](../R2_TEMPLATE_B_REPRODUCTION.md)に固定した。このBINをbackend
`0d434d789ed2aa0743520eb0d411fa2ced1974e4`で1コマンド実行し、12億cycle、FAT32 read 9/write 10、
LCD/SD/READY marker、drop 0、unknown SD/MMIO 0、schema 8 verdict passを確認した。wrong BIN、
scenario、backend、LCD variant、missing/malformed/stale reportの異常系も回帰試験に固定した。
公式A targetも同じCLIで95億cycleを完走し、PSRAM 8,388,608 byte全一致、keyboard 4 event、
必須marker不足0、exception/MMIO 0でpassした。これによりactive A/Bの両方を現行pinで実証した。
証跡は`firmware-validation/records/r2-20260806-01/`にある。後続のR3も完了した。

### R3実装結果（2026-08-06）

PicoTetrisのゲーム規則と状態をBSP-freeな`game.h`/`game.cpp`へ分離し、描画・UART・BSPだけを
`app/main.cpp`へ残した。666 host checksで全7形状×4回転、各境界・占有衝突、回転と壁蹴り、
1〜4ラインの100/300/500/800点、固定seed、game-over、`R` restart、gravity tick resetを合格した。
この分離により、restart後も旧poll tickを引き継ぐ欠陥を修正した。

source commit `fed84f358d7dcadb1457752e687355ddb1875c48`を別々のclean cloneから固定toolchain・
timestampでbuildし、BIN `0784d80d...46e62`とUF2 `44ec6227...e274`がbyte-identicalになった。
絶対build pathを含むELFは一致しないため、その再現性は主張しない。

`picotetris-r3`をactive firmware targetへ登録し、backend `0d434d789ed2...`で同じscenarioを
3回実行した。3回とも85/85、13 lines、score 1400、key 362/0、exception/error/MMIO 0で、
UART、RGB565、PNG、raw/正規化report、85-step timelineが一致した。remoteを持たない方針は
R3完了時点まで維持し、`provenance/picotetris-r3.bundle`へR3完全履歴を追加した。R4の
clean-clone CI準備として2026-08-06にprivate GitHub repositoryを追加したが、R3のbundleと
`remote: null`は時点証拠として変更しない。詳細と全SHAは
[`R3_PICOTETRIS_REGRESSION.md`](R3_PICOTETRIS_REGRESSION.md)、機械可読証跡は
`firmware-validation/records/r3-20260806-01/`にある。完了後はR4へ進んだ。

### R4実装結果（2026-08-06）

R4に着手し、最初の変更単位として`picoem-picocalc`のbackend品質ゲートを完了した。
backend commit `3bc6bbd7833e45fbf94d640eb7fbe056dd9fbd81`から、固定した
Ubuntu 24.04/Rust 1.97.1上でtest、fmt、Clippyを独立jobとして実行する。testは
`picocalc-board`、`picocalc-harness`、`rp2040-emu`とrelease build、fmt/Clippyは
保守責任を持つPicoCalc固有crateを対象とする。GitHub Actions run `31098630797`で全jobの
成功を確認した。

このcommitはbackendのcurrent mainに対する品質ゲートであり、既存firmware targetの
accepted backend pinを更新しない。履歴targetはregistryに記録したcommitの専用checkoutを
`--backend-dir`へ渡して実行する。したがってR2/R3のtarget、record、SHAは変更していない。

続いてgeneratorの`project_commit()`を修正した。`--project`のdirectory自身がGit working
treeのrootである場合だけ`app_git`へcommit/dirtyを記録し、単に親repositoryの子である
directoryは`untracked`とする。親Git内・Git外の二配置が一致する回帰試験と、project自身が
Git rootの場合はcommitを保持する試験を追加した。`bsp_git`は生成時metadataの
`source_commit`とコピー後tree hashから計算する既存契約を変更していない。R2 targetは
固定generator commitと履歴再現手順を使う時点証拠なので、target/record/SHAを書き換えない。

target registryをschema 3へ更新し、全targetに`revision`とSHA固定validation attestationを
追加した。attestationは`validation`を除いたtarget contract SHAと、既存evidence recordの
path/SHA/record ID/sectionを結ぶ。target・attestation・evidenceの改変、repository外path、
未知の`supersedes`、revision逆行はportable verifierがfail-closedで拒否する。R2/R3 recordは
変更せず、R4 attestationから参照する。

`picotetris-r4` revision 2を`picotetris-r3`の後継として追加し、clean cloneからR3と同じ
BIN/UF2を再生成した。backend `3bc6bbd...bd81`で3回実行し、全runがexit 0、85/85、
13 lines、score 1400となり、raw/normalized report、timeline、UART、framebuffer、PNGが
それぞれ3回一致した。詳細は[`VERSIONED_VALIDATION.md`](../VERSIONED_VALIDATION.md)と
`firmware-validation/records/r4-20260806-01/report.json`にある。

PicoTetrisはcommit `6cd16eb075120140d9073a72db665482f3c2fe95`でGitHub Actionsへ接続した。
`unit` jobは現行sourceの666 checksと厳密な成功行を検査する。
`rp2040-reproducible-build` jobはR3固定source `fed84f3...c48`、Pico SDK 2.2.0
`a1438df...179`、Ubuntu 24.04のARM GCC 13.2.1/CMake 3.28.3/Ninja 1.11.1、固定timestampと
`app_git`/`bsp_git`からbuildし、登録済みBIN `0784d80d...e62`とUF2 `44ec6227...274`の
SHA-256を直接照合する。run `31101591668`で両jobの成功を確認した。

`picocalc_emu` commit `f9b596fe01163d69f2396bb3d50aafb44965c825`では、portable、Python
tools、target/schema、host、Pico SDK 2.0互換build、固定PicoTetris firmware regressionを
6つの独立jobへ接続した。読み取り専用deploy keyでprivate backendを取得し、accepted commit
`3bc6bbd...bd81`とclean treeを確認してからrelease runnerをbuildする。PicoTetrisはR3 bundleの
SHAを検査して復元し、SDK 2.2.0の固定条件で登録BIN `0784d80d...e62`を再生成してから
`picotetris-r4`を実行する。run `31103564391`で全jobが合格した。

backend run `31098630797`、PicoTetris run `31101591668`と上記runを合わせ、3リポジトリの
clean-runner full gateは完了した。R4の完全なjob境界、pin、認証境界は
[`R4_CI.md`](R4_CI.md)に記録した。その後、R5の同一BIN実機相関で使う観測契約と最初の
高速化candidateをOPT0〜OPT1-Aで整備した。

### R5実機着手前の性能baseline（2026-08-06）

実機との機能相関に入る前に、`picotetris-r4`の仮想時間とWSL wall timeの比を固定した。
AMD Ryzen 5 5600X上のWSL2で、1 warm-up後に同一CPUへ固定して10回測定した結果、仮想
3.715秒に対するwall time中央値は63.247秒、実時間比中央値は5.874%（約17.025倍遅い）だった。
全runのreport/UART/PNGは一致した。これはR5実機合格ではなくpreflightであり、実機検証は
未着手のままである。定義、理論上限、全測定値、再測定コマンドは
[`R5_REALTIME_PERFORMANCE.md`](R5_REALTIME_PERFORMANCE.md)に記録した。

このbaselineを起点に、実機相当の正確性を維持したまま開発turnaroundを短縮する高速化を
R5と並行する作業列として行う。OPT0の観測契約と最初のOPT1候補はR5前に実施できるが、
実機相関前は暫定候補であり、R5で一致した後に正式採用する。blocked上界と安全に飛ばせる
下界を分離した計測、event horizon、正確性・性能gate、OPT0〜OPT3の実施順序は
[`EMULATOR_OPTIMIZATION_PLAN.md`](EMULATOR_OPTIMIZATION_PLAN.md)を正典とする。

OPT0-Aの最初の変更単位として、backend `ace66df91f87cfe18c7bec0ba47bcbc12f5c9345`に
feature-gated Serial idle profilerを実装した。通常buildとschema 8 reportは変更せず、診断build
だけがschema 1 profileを別出力する。登録済みPicoTetris BINのclean実測では既存契約値を維持し、
both-blocked上界618,595,844 cycle（66.692909%、139 episodes）に対して、現行の保守的な
proven-safe下限は0 cycleだった。記録は
[`firmware-validation/records/opt0-a-20260806-01/notes.md`](../../firmware-validation/records/opt0-a-20260806-01/notes.md)
に不変証拠として保存した。

この0 cycleはproduction用`is_idle()`が時間変化するworkと静的FIFO/IRQ stateを同一視したためで、
backend `9135f5ad09fe86a2330e51cd9a3ee106cb7c9642`では通常実行経路を変えずに計測専用の意味分類を
追加した。schema 2はtemporal/wake blocker、stationary state、existing exact-bulk workを分離する。
同じPicoTetris回帰で全618,595,844 blocked cycleが観測境界上proven-safeとなり、85/85、cycle、
UART、framebufferは従来値と一致した。記録は
[`firmware-validation/records/opt0-a-20260807-03/notes.md`](../../firmware-validation/records/opt0-a-20260807-03/notes.md)
に保存した。これはvirtual-cycle dispatch削減余地であってwall-time speedupではない。この時点では
full horizonとboundary/event cost modelが残っていた。

続いてbackend `5d01c8072c70841336cf48e46bc5aa7b8a669349`に同一release build内で
blocked step、保守的probe、quiescent bulk advanceを比較する専用microbenchmarkを追加した。
CPU 0固定・各100万iteration・10 sampleでは、それぞれ52.647255 ns、10.771746 ns、
37.108583〜37.825914 nsだった。全source horizon、clock更新、boundary/event、IRQ route、
wake checkは未測定なので、この時点ではscreeningの部分値であり優先順位は確定しなかった。raw sampleと
再現手順は
[`firmware-validation/records/opt0-a-20260806-02/notes.md`](../../firmware-validation/records/opt0-a-20260806-02/notes.md)
に保存した。

backend `8bd6809116ad9e38de9deea961603dfb2884101b`では現行modelの全sourceを覆う保守的horizonを
実装し、schema 3 profileで618,595,844 safe cycleを2,064,042 segmentへ分割した。境界は
PWM 2,063,903件、TIMER 138件であり、PicoTetrisの85/85、cycle、UART、framebufferは従来値と
一致した。backend `67fc4bce7934885b439bc80629175dafeab2299f`では診断featureを含まない
production blocked-path baselineを分離し、CPU固定10 sampleで`Cblocked=48.621175 ns`、
`Chorizon=30.388395 ns`、`Cadvance(1)=39.412803 ns`、TIMER event/route/wake増分
`7.122434 ns`を得た。損益分岐は2 cycleである。63.247秒から33.329秒・実時間比11.146%という
値は優先順位選択用の算術投影であり、最適化実測ではない。完全な証拠は
[`firmware-validation/records/opt0-a-20260808-04/notes.md`](../../firmware-validation/records/opt0-a-20260808-04/notes.md)
に保存した。これでOPT0-Aは完了し、OPT1-A exact idle fast-forwardを第一候補に選んだ。
OPT0-Bではbackend `763595fedefa08886b41298be79bff69324ac51f`にfeature分離した
behavior/streaming event契約を追加した。PicoTetrisのtrace ON二重走行とtrace OFF走行で既存の
cycle、UART、framebuffer、85/85 scenarioを維持し、`behavior_sha256`、全体/domain別event hashと
countを固定した。詳細は[`OPT0_B_BEHAVIOR_CONTRACT.md`](OPT0_B_BEHAVIOR_CONTRACT.md)にある。
OPT1-Aではbackend `c68c58f6c37fb31eb9313566c8b16883db9063b6`に両core blocked時だけの
exact fast-forwardを実装した。runner所有のscenario/input境界を接続し、未証明sourceは1 cycle
fallbackする。PicoTetrisは85/85、cycle、UART、framebuffer、timelineを維持し、host UART drain
cadence依存を除いたbehavior schema 2でもone-cycle referenceと全9 domainが一致した。CPU固定
10 runのwall中央値は63.247秒から27.123秒へ57.116%短縮した。詳細は
[`OPT1_A_EXACT_IDLE_FAST_FORWARD.md`](OPT1_A_EXACT_IDLE_FAST_FORWARD.md)にある。実機相関前の
この時点ではcandidateだった。その後、R5で同一artifactの実機相関に合格し、現在はpromotedである。

R5 preflightではPicoTetris source `9a40a905...`から、製品targetとは別名だが相関では単一の
`PicoTetris_R5.bin`/UF2を再現buildした。firmware自身がLCD 100回readback、audio、PSRAM、
FAT32 SD、line-clear、game-over、restartを自動実行した後、公式keyboard firmware由来の
`CAPS`以外の66物理キーを任意順・個別retry・SD進捗resumeで確認し、`CAPS`は`66/67`の後に
最後に確認する。エミュレーターでは全5 scenario step、
67/67、最終verdictが合格した。同じUF2のPicoCalc実機相関も、参照音、未完了キーのresume、
UART全文、安定した最終PASS画面、CRC-validなSD進捗を含めて完了した。固定値、復旧手順、
preflight SHA、実機結果は[`R5_HARDWARE_CORRELATION.md`](R5_HARDWARE_CORRELATION.md)を正典とする。

## Milestone 0: Canonical BSP — implemented

- 実働プロジェクトを根拠にしたLCD・keyboard・SD/FatFS BSP
- アプリ変更を`app/`に限定するRP2040テンプレート
- portable source fingerprint check
- host SPI fakeによるLCD初期化・CS分割transaction test
- JSON profileからのboard header一方向生成
- reference commit/SHA-256 evidence check
- ClockworkPi公式STM32 keyboard firmwareをprotocol producerの一次リファレンスとして固定
- Canonical BSP実機検証schema・pending template
- LCD pattern、SD read/write、keyboardログの実機スモーク
- PythonテストとRP2040 compile CI

完了条件は、clone単体のportable検証とテンプレートcompileがCIで成功し、
初回のBSP実機スモーク結果を記録できることです。

## Milestone 1: Firmware backend — `picocalc_helloworld` first

**Gate 0〜7完了（2026-08-04）。** 無改変の公式`picocalc_helloworld`が
`ExecutionModel::Serial`上でHELLO-FULLの8条件を満たし、続いてCanonical BSPの
推奨デフォルトB（PIO0/RGB565/LCD DMA OFF）で生成した標準templateが
`[PICOCALC][LCD][VERIFY] app_status=pass`に到達した。Gate別の進捗表と証拠は
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §4と
`firmware-validation/records/`にある。

完了条件のうち、継承済みSerial回帰の全合格とGate 7のB conformanceは満たしている。
本Milestoneが目指した「AIが自作アプリを自力で検証できる」状態を妨げていた
SPI0のSD（templateのSDスモークが停止していた）とPSRAM ID読み出しの不一致は、
どちらも2026-08-05に解消した。実機相関で得たチップIDを根拠にPSRAM Read IDを
実装し、SPI0のSDカードを実装してtemplateの全機能スモークが完走するようにした。
証拠は`firmware-validation/records/`、実機との相関確認は
`hardware-validation/records/bsp-0.8.8-20260804-02.json`にある。

Milestone 1の作業単位分解と実行計画は[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)に
定義する。

Primary backendとして`picoem-picocalc`を使用する。ソースは
`picocalc_emu`へコピーせず別リポジトリで保守し、正確なcommitを固定する。
初期段階では`ExecutionModel::Serial`を正しさの基準とする。
`rp2040js`はRP2040周辺機器の振る舞い、実装方法、テスト構成の比較参考とし、
`picocalc_emu`に接続する主backendとはしない。

- `picoem-picocalc`のversion/commit固定とcapability manifest
- inherited RP2040 Serial test suiteの基準化
- 無改変`Code/picocalc_helloworld`のsource/build identity固定
- ELF/BINのdirect bootとUART、PC、例外、未対応MMIO、停止理由の取得
- SPI1とGPIOを通したAのRGB666 3-byte LCD初期化・framebuffer生成
- `Hello World PicoCalc`を最初の可視化到達点として取得
- PIO1/DMA PSRAM全域試験、I2C1 keyboard controller、battery、backlightの接続
- シナリオ入力したキーのLCD echoを含む`picocalc_helloworld`完全合格
- Aの次のconformance対象だったBのPIO0/RGB565/LCD DMA OFFを接続（Gate 7完了）
- 必要範囲のPIO/DMA、PNG、UART、trace、capability成果物への接続

最初のFirmware縦断対象は、ClockworkPi公式の無改変`Code/picocalc_helloworld`とする。
最初の可視化到達点はAのSPI1/RGB666 3-byte転送を解釈し、320x320 framebufferへ
`Hello World PicoCalc`を決定的に描画できることである。ただし、この時点では完全合格と
しない。8 MiB PSRAM全域試験、I2C controller、scripted keyboard echo、未対応MMIOなし、
構造化artifactの反復一致まで満たして完全合格とする。

この優先順位はCanonical BSPの推奨デフォルトを変更しない。BのPIO0/RGB565/
LCD DMA OFFは、Aの公式サンプル縦断試験に続くFirmware conformance対象とする。
詳細は[`EMULATOR_ROADMAP.md`](EMULATOR_ROADMAP.md)に定義する。

Firmware backendはHost device modelの代替ではない。対象アプリが同一バイナリ
確認を必要とし、backendの対応能力が明示されている場合だけ使用する。
公開版`picocalc_emu`の通常ビルドがprivate依存を要求してはならず、正式統合前に
`picoem-picocalc`も公開または同等に再現可能な配布形態にする。

完了条件は、`EMULATOR_ROADMAP.md`のHELLO-FULLとGate 7のCanonical BSP B conformanceを
満たし、継承済みSerial回帰がすべて合格した状態を、commitと構造化artifactで固定すること。

## Milestone 2: Host device models

**完了（2026-08-05）。** BSPの公開APIをホストのモデルに対してビルドし、専用
`emu_smoke`アプリ（`bsp/host/tests/emu_smoke.cpp`）がPC上で起動、画面・キー・
ファイル結果を決定的に生成する（25個の明示的check＋初期化前提、3回連続実行で
バイト一致）。詳細は
[`HOST_BACKEND.md`](../HOST_BACKEND.md)、証拠は
`firmware-validation/records/milestone2-20260805-01/`にある。

- native host App API/Pico SDK shim（`stdio_init_all`・`sleep_ms`のみ）
- headless LCD framebuffer
- keyboard FIFO model（上限31イベント、実機コントローラの5ビット深さ制約を反映）
- 仮想時刻、stdout capture

`directory-backed Fast SD mode`は**未実装のまま残っている**。カードはホストメモリ上の
セクタ配列で、ホストのディレクトリを見せる経路がない。`固定乱数`は該当するアプリが
なく検証していない。Milestone 2の中核完了条件は、同一filesystemソースを使う
memory-backed cardと専用`emu_smoke`の決定性までとし、directory-backed modeは
Milestone 5へ明示的に繰り延べる。

`src/filesystem.cpp`・`src/fatfs_diskio.cpp`はデバイスと同一ソースを未改変で使う
（Pico SDK依存が無いため）。framebuffer digestの正規形はfirmware backendと同一で、
両者は直接比較できる。**firmware backendが権威であることは変わらない**。PIO・DMA・
I2C・割り込み・LCDのwire形式はhostに存在しない。

ここで完了したのはhost device modelと専用`emu_smoke`です。後続R3ではPicoTetrisの
ゲーム規則をhardware-freeに分離し、アプリ固有の666 host checksへ接続しました。

## Milestone 3: Scenario runner

**完了（2026-08-05）。** JSON手順を実行ループの内側で評価し、条件付きキー投入と
画面の機械判定ができるようになった。詳細は
[`SCENARIO_RUNNER.md`](../SCENARIO_RUNNER.md)、証拠は
`firmware-validation/records/milestone3-20260805-01/`にある。実例として、ドッグ
フーディングで一度も発火させられなかったPicoTetrisのライン消去を実際に発火させた
（`scenarios/tetris-line-clear.json`、13ライン、スコア1400）。

- JSONシナリオ（`op`: wait / wait_cycles / wait_until / key / snapshot / assert）
- pixel、region_non_black、region_hash、region_stable、region_changed、
  uart_containsのassertion
- PNGとJSON成果物

`trace JSON`・`JUnit成果物`・`100回連続実行の決定性検査`は**未実装**。現状は
UARTログとPSRAM/keyboard等の観測カウンタで足りているが、CI組み込み時には
JUnit形式の出力が要る見込み。Milestone 3の中核完了条件はscenarioの条件評価、
構造化report、snapshotによる実アプリ合格までとし、CI出力と長期反復はR4へ繰り延べる。

> **R4での決定（2026-08-06）:** R4の受入条件は層別job、host 3回一致、固定成果物SHA、
> firmware regression実走とした。JUnit変換と100回soakはその完了条件に含めず、必要時に
> 所要時間と保存方針を定める独立作業パッケージとする。現時点では未実装である。

この作業がエミュレーターの欠陥を1件見つけた。キーボードモデルのFIFOに上限が
なかったため、滞留が32の倍数に達するとBSPの`key_info[0] & 0x1f`が0を読み、
ドライバが恒久停止していた。31で頭打ちにする修正を`picoem-picocalc`へ入れた。

## Milestone 4: Hardware correlation

**最初の同一artifact相関はR5で完了。継続相関は進行中。** Gate 7の初期相関でBOOT、
250 MHz、LCD `app_status=pass`、GRAM readback、audio pathを実機で確認し、PSRAMとSDのmodel gapを
解消した。後続R3/R4でPicoTetrisを再現可能build・active target・CIへ固定し、R5では同一buildの
BINをエミュレーター、UF2をPicoCalc実機で動かした。LCD、PSRAM、FAT32、ゲーム診断、67キー、
audio pathが一致し、`emulator pass -> hardware fail`はR5範囲で0件だった。R6でこの証拠を
文書とmachine verifierへ接続した。

R5の`audio=pass`はfirmware設定/counterと実機参照音の相関であり、それ単独ではemulator PCM sinkを
意味しない。後続NEXT-2Bはexact digital sinkと独立した同一UF2実機相関を完了し、凍結v3 targetに限ってcapability上supportedである。また0件という値は一般的な
false-acceptance率0%ではない。Milestone 4へ戻るときの継続作業はnegative conformanceとKPI母数の
追加である。NEXT-1 blind appは完了し、全体の直近順序では、その前にNEXT-2 capability範囲拡張を行う。

- 実機SPI/I2C/UART trace採取
- host traceとのgolden比較
- `host_pass → hardware_fail`を含むnegative conformance記録
- 変更影響に基づく実機必須判定
- 実機検証回数と時間のKPI

## Milestone 5: BSP lifecycle and broader compatibility

- `picocalc bsp status`
- `picocalc bsp diff`
- `picocalc bsp upgrade`
- BSP changelogとmigration rule
- 既存生成プロジェクトへの安全な修正配布
- directory-backed Fast SD、故障注入、PWM/DMA audio playback、multicore、
  SIO FIFO、WFE/SEV、IRQの拡張
- PicoMite、uLisp、FUZIX等の対象workload別runner
