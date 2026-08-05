# Milestones

**この文書が全体計画の正典です。** 全体の実装順序とMilestone単位の完了条件を
定義します。Firmware Gateの詳細受入条件は`EMULATOR_ROADMAP.md`が定義し、
他文書に出てくる段階表現は本書のMilestone番号へ対応付けます。

Milestone 0〜3の中核受入条件は完了しています。Milestone 4は最初の実機相関まで
到達しましたが、現行成果物を一意に再現して継続回帰へ載せる作業が残っています。
次に行う作業は本書の「現在の実行順序」に従います。完了済みMilestoneの記述は、
基盤が存在することを示すものであり、個別アプリがその基盤へ接続済みであることまでは
意味しません。

Canonical BSP 0.8.8の実機台帳は
`hardware-validation/records/bsp-0.8.8-20260804-02.json`で`overall_status=pass`となり、
LCDとkeyboardのpendingを解消しました。0.4.0台帳に残る`pending`は、当時の装置識別情報や
未試験項目を後から補わないために保持する履歴状態であり、0.8.8の現在状態ではありません。

Firmware backendの開発方針は
[`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md)に定義します。主バックエンドは、
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

## 現在の実行順序（2026-08-05レビュー反映）

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
| R0 | 基準点・生成契約・provenanceの固定 | `picocalc_emu`、`picotetris` | 開始baselineとして3リポジトリのcommitと合否契約schemaを記録する。生成後metadataのBSP版が`bsp/VERSION`と一致し、必要なlicense/noticesとローカル参照が揃う。PicoTetrisを固定source identityから再取得できる | 未着手 |
| R1 | backend verdict・reportの厳密化 | `picoem-picocalc`＋`picocalc_emu` host | cycle切れ、必須marker不足、scenario失敗、exception、未対応MMIO、key dropを誤ってPassにしない。SDを含む必須観測値をstructured reportへ出す。keyboard modelは[公式`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)を一次リファレンスとしてregister/FIFO/state/modifier/repeat/overflowをconformance testする。SDはFAT32既定/FAT16明示profileを両backendで通す。正常系・異常系のRust/C++ testが合格する | **R1-SD完了**。verdict・keyboardは未着手 |
| R2 | Firmware CLI・target registryの一般化 | `picocalc_emu`＋backend | R1完了commitをaccepted backend pinとし、source/toolchain/BSP/BIN/device/scenario/期待reportを構造化登録する。CLIが宣言どおりrunnerへ渡し、wrong BIN・scenario・backend・LCD variantが明示的に失敗し、正しいtargetが1コマンドで合格する | R0・R1後 |
| R3 | PicoTetrisの正式回帰化 | `picotetris`＋`picocalc_emu` | ゲームロジックをhardware-freeに分離し、全7形状・回転・境界衝突・1〜4ライン・score・固定seed・game-over/resetをhostで検査する。固定条件のfresh build 2回でBIN SHAが一致する。firmware scenario 3回が85/85、13 lines、score 1400、key delivered 362/drop 0、exceptionなし、unsupported MMIO 0となり、UART SHA・framebuffer SHA・正規化report/timelineが一致する | R2後 |
| R4 | 品質ゲートとCI | 3リポジトリ | clean cloneから同じpinで再現する。`picotetris`はunit＋RP2040 build、backendはtest＋fmt＋Clippy、`picocalc_emu`はportable＋host＋target/schema＋firmware regressionを実行し、失敗した層を特定できる | R3後 |
| R5 | 現行成果物の実機相関 | `picocalc_emu`＋実機 | 回帰登録済みPicoTetris BINと同一SHAでLCD・ゲーム操作キー・line clear・game-over・restart・PSRAM・SD・audio初期化仕様を確認する。全67キーは別のBSP diagnostic BINで確認し、両BINのSHA、UART、写真、操作記録を新規台帳へ保存する | R4後 |
| R6 | 文書・配布状態の最終確定 | 3リポジトリ | README、status、Milestones、dogfood記録、target、license/noticesが用語と時点を一貫して記述し、現在状態・時点履歴・未実装を明確に区別する。第三者がclean cloneから再現できる | R5後 |

依存関係は次のとおりです。R0とR1は並行できますが、R2は両方の完了後に行います。

```text
R0 生成契約・source identity ─┐
                               ├→ R2 CLI/registry → R3 PicoTetris → R4 CI
R1 backend verdict/report ─────┘                                  → R5 実機 → R6 配布
```

各パッケージの終了時にREADME・`IMPLEMENTATION_STATUS.md`・capability・target/recordの
該当箇所を同じ変更単位で更新します。旧hardware/firmware recordは時点証拠なので書き換えず、
後続recordまたは現在状態の文書から参照します。Solが仕様・受入・統合を担当し、Lunaは
限定された実装、定型更新、独立照合を行います。責任境界は`DEVELOPMENT_WORKFLOW.md`に従います。

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

### 実装着手レビュー（2026-08-05）

**判定はGOです。** 公式keyboard producer、既存FAT16の境界、FAT32で追加する構造、
CLI/report/target契約、host/firmware共通の合否条件まで決まっており、未決の製品判断は
ありません。portable検証39件、Python 24件、host smoke 3回決定一致、Rust board 56件、
runner 24件、doctest 1件が合格しています。

ただし現在の3リポジトリには統合文書差分があるため、ソース実装を混ぜる前にR0として
この文書・catalog・capability・baseline test結果をレビュー可能な変更単位へ固定します。
これは設計上のblockerではなく、後から「どの仕様に対する実装か」を失わないための
provenance gateです。R0固定後のR1-SD実装順は次のとおりです。

1. Rust側にvolume format型とFAT16/FAT32 geometry単体試験を追加する。
2. `SdCard`生成器へFAT32 profileを接続し、block readでBPB/FSInfo/FAT/rootを検査する。
3. runnerの`--sd-format`、引数エラー、structured reportを追加する。
4. host側に同じformat選択を追加し、共有Chan FatFsのsmokeを両形式で実行する。
5. target registryへ形式を固定し、FAT16/FAT32各3回の決定性回帰を記録する。

keyboard conformanceは同じR1内の独立作業であり、R0固定後はR1-SDと並行できます。

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
なるため、R1全体はまだ完了ではありません。SD経路の合格とは分離し、次はR1 verdictを
厳密化してこの種のfalse passを終了コード1にします。

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
- 次のconformance対象としてBのPIO0/RGB565/LCD DMA OFFを接続
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
[`HOST_BACKEND.md`](HOST_BACKEND.md)、証拠は
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

ここで完了したのはhost device modelと専用`emu_smoke`です。PicoTetrisの
`clear_lines()`や衝突判定はまだhost testへ接続されていないため、アプリ固有の単体試験は
R3で行います。

## Milestone 3: Scenario runner

**完了（2026-08-05）。** JSON手順を実行ループの内側で評価し、条件付きキー投入と
画面の機械判定ができるようになった。詳細は
[`SCENARIO_RUNNER.md`](SCENARIO_RUNNER.md)、証拠は
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

この作業がエミュレーターの欠陥を1件見つけた。キーボードモデルのFIFOに上限が
なかったため、滞留が32の倍数に達するとBSPの`key_info[0] & 0x1f`が0を読み、
ドライバが恒久停止していた。31で頭打ちにする修正を`picoem-picocalc`へ入れた。

## Milestone 4: Hardware correlation

**一部完了。** Gate 7と同一ソース・同一設定のUF2を実機で3回確認し、BOOT、250 MHz、
LCD `app_status=pass`、GRAM readback、audioの一致を記録しました。そこで見つかった
PSRAMとSDのmodel gapも解消済みです。ただし、この記録のBINは現在の生成契約から
一意に再生成できず、PicoTetrisも継続回帰targetとして未登録です。R0〜R4で現行成果物を
固定した後、R5で同一BIN SHAによる相関を追加します。

- 実機SPI/I2C/UART trace採取
- host traceとのgolden比較
- `host_pass → hardware_fail`記録
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
