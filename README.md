# picocalc_emu — AIがPicoCalcプログラムを観測・検証・修正できる開発基盤

[![CI](https://github.com/FuyukiYoneyama/picocalc_emu/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/FuyukiYoneyama/picocalc_emu/actions/workflows/ci.yml)

<!-- 注: 本リポジトリは現在privateです。上のCIバッジはアクセス権のない閲覧者には
     表示されません。公開時に解消します。 -->


## このプロジェクトの目的

**PicoCalc向けのプログラム開発をAIに依頼したとき、AIがエミュレーター上で結果を
観測・検証し、失敗原因を特定して修正できるようにすること。** その成果指標として、
人間が行う実機検証の回数を最小にし、実機と相関を確認できた範囲では検証なしで
完成へ到達できる開発の枠組みを提供します。

「実機検証を減らす」の主語は人間です。AIは実機を操作できません。UF2をSDカードへ
コピーし、PicoCalcへ挿し、電源を入れ、画面を見て、写真を撮り、UARTログを回収する
作業は、すべて人間が行います。**AIが1回推測を外すたびに、人間がこの往復を1回払う。**
このプロジェクトが削減する対象は、この人間の往復です。

したがって最終目標は「エミュレーターを作ること」自体ではありません。
AIが自分で観測し、自分で失敗原因を特定し、自分で直せる状態を作り、人間の出番を
**最後の1〜2回の確認、理想的には0回**にすることです。

## PicoCalcとは

[ClockworkPi PicoCalc](https://www.clockworkpi.com/picocalc)
（[ソース](https://github.com/clockworkpi/PicoCalc)）は、Raspberry Pi Picoシリーズを
差し替え可能なメインボードとして搭載する、電池駆動のスタンドアロン携帯マイコンです。
ポケット電卓の形をした、それ自体で完結した小さなコンピューターだと考えてください。

| 要素 | 内容 |
|---|---|
| メインボード | Pico 1 / 1 W（RP2040、Cortex-M0+ 133 MHz）または Pico 2 / 2 W（RP2350、Cortex-M33 150 MHz）を差し替え |
| 画面 | 4インチ 320×320 IPS、SPI接続 |
| キーボード | 67キーQWERTY、バックライト付き。STM32が管理し**I²C経由**で接続 |
| 音声 | PWMスピーカー2基＋3.5 mmジャック |
| ストレージ | SDカードスロット |
| メモリ | オンボード8 MB PSRAM |
| 電源 | 18650リチウム電池1本、ホットスワップ対応 |

本リポジトリの現在の対象は**RP2040（Pico 1）搭載構成**です。

重要なのは、この構成が「PCに繋いだ開発ボード」ではないという点です。プログラムは
UF2としてSDカード経由で書き込み、実行結果は本体の画面とUARTログにしか現れません。
**AIからは画面もSPI波形もSDカードの中身も一切見えません。**

## なぜ難しいのか

AIにPicoCalc向けアプリを書かせると、動作実績のあるプロジェクトを何本渡しても
LCDが映らず、SDがmountできず、原因が特定できないまま実機デバッグが10回以上続きます。
原因は資料不足ではなく、次の2つです。

1. **合成の誤り** — 複数の実働プロジェクトには異なるドライバ、ピン設定、I²C速度、
   ビルド構成が混在します。AIがそれらを部分的に組み合わせると、各部分は正しいのに
   全体として動かない構成ができます。
2. **観測不能** — AIに返る信号は「映る／映らない」の1ビットだけです。
   1ビットのオラクルでは、リセット波形・CS粒度・clkdiv・転送形式・クロックといった
   多次元の仮説空間を絞り込めません。だから推測し、外し、人間の往復が増えます。

この2つを実際に踏み抜いた記録が
[LCD不動作調査記録](docs/LCD_INVESTIGATION_20260729.md)です。LCDに1枚表示させる
だけのために、UF2ビルド17回・実機書き込み15回以上を要しました。確定した原因は、
動作実績コードを手作業で再実装した際に、転送処理と呼び出し粒度を変質させたことでした。

## どう解くか

観測できない相手には推測が生まれます。そこで三段構えで、推測の余地を順に消します。

| 段 | 手段 | 消す推測 | 状態 |
|---|---|---|---|
| 1 | **Canonical BSP** — 実機で確認した転送契約と由来を固定し、AIの変更範囲を`app/`に限定する | ハードウェア初期化をAIに再発明させない | **完了**。BSP 0.8.8実機台帳はLCD・keyboardを含め`pass` |
| 2 | **エミュレーター** — PC上でアプリを実行し、画面・SPI/I²C・SD・キー入力をAI自身が観測して自力で直す | 「なぜ動かないか」をAIが自分で特定できる | A/BのLCD・PSRAM・SD・キー入力を観測可能（Milestone 1〜3完了）。scenarioとhost基盤は完成。個別アプリのhost test・継続target化は別途必要 |
| 3 | **実機相関** — 実機結果を証拠台帳へ記録し、エミュレーターの予測精度を校正する | エミュレーター合格が実機合格を意味するかを測定で担保 | 一部実装 |

第2段のエミュレーターは、目的の異なる2つのバックエンドで構成します。

- **Host backend** — アプリロジックをPCネイティブ実行する高速経路。UI・入力・
  ファイル処理の反復検証に使います。
- **Firmware backend** — 実機と同一のRP2040バイナリをそのまま実行する経路。
  PIO・DMA・割り込み・マルチコアなど、Host backendが置き換えて消してしまう層を
  検証します。Rust製[`picoem-picocalc`](https://github.com/FuyukiYoneyama/picoem-picocalc)を
  主バックエンドとして使用します。

**なぜ2本必要か:** 前述のLCD障害はPIOプログラム、clkdiv、CSトグル粒度に潜んでいました。
これらはHost backendがshimで置き換える層そのものであり、ホストをいくらグリーンにしても
検出できません。人間の往復を本当にゼロへ近づけるには、同一バイナリを実行して
実際の信号を観測する経路が不可欠です。詳細は
[主Firmware backend方針](docs/FIRMWARE_BACKEND.md)を参照してください。

## 現在地

第1段のCanonical BSPのソース、portable検証、テンプレート基盤は **0.8.8** として
整備済みです（Milestone 0）。実機動作済みプロジェクトから抽出したBSP、アプリ
テンプレート、プロジェクト生成器、証拠台帳、検証ツールが利用できます。標準templateの
アプリ版名は`0.8.4-*`としてBSPとは独立に管理します。最新0.8.8自身の実機台帳は
`bsp-0.8.8-20260804-02`でLCD・SD・keyboard・audio・PSRAMを含め`pass`です。

**第2段のエミュレーターは、公式サンプルの縦断まで到達しました（2026-08-04）。**
ClockworkPi公式の無改変`Code/picocalc_helloworld`が、Firmware backend
（`picoem-picocalc`、`ExecutionModel::Serial`）上でHELLO-FULLの8条件すべてを
満たして動作します。LCD描画、8 MiB PSRAM全域試験（8/16/32/128-bit、全バイト一致）、
I2Cキーボードのbattery/backlight、シナリオから投入したキーのLCD echo、PWM初期化の
観測までをPC上で確認でき、3回連続実行でUART・framebuffer・JSONがバイト一致します。
記録は`firmware-validation/records/gate5-20260804-01/`にあります。

**続いてGate 7も完了し、標準templateがエミュレーター上で検証できるようになりました。**
`tools/picocalc.py new`で生成したプロジェクト（B系統: PIO0/RGB565/LCD DMA OFF）が
起動し、250 MHzクロック設定、PIO0経由のLCD初期化と既知パターン描画、SIO bitbang
経路でのGRAM readbackによる`app_status=pass`、音声参照トーンの正常動作までを
PC上で確認できます。3回連続実行でreport・UART・PNGがバイト一致します。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target picocalc-template-b --firmware <path-to.bin>
```

R2でこの上位CLIをschema 2 target registryへ接続しました。source/toolchain/BSP、BINと
scenarioのSHA-256、backend build commit、LCD/PSRAM/keyboard/SD設定、停止理由、UART marker、
structured report期待値を1つの契約として固定します。CLIは宣言をrunnerへ全転送し、毎回
新しいreportだけを読み、runnerの終了コード0/1/2とschema 8 verdictの一致まで検査します。
引数overrideが契約と違う場合やBIN・scenario・backendが違う場合は実行前に失敗します。
R4ではschema 3へ更新し、revisionとvalidation attestationを追加しました。新しいtargetは
旧targetを上書きせず`supersedes`で結び、各契約を不変のevidence recordへSHA-256で接続します。

実機検証（2026-08-05）の後、**SPI0のSDカードも実装しました。** これで標準template
が全機能を完走します。

SDのSPI block protocolはFAT形式に依存しません。テスト用volume自体は64 MiBですが、
購入時付属の32 GBカードのfilesystemに合わせ、firmware backendとhost backendは
**FAT32をデフォルト**とし、FAT16は`--sd-format fat16`またはhost APIの明示指定で
利用できます。両形式ともBSP自身のmount/write/sync/read/compare/removeを通します。
firmwareはFAT32/FAT16を各3回実行して決定一致、hostは両形式のCTest合格に加え、
既定FAT32を使う`emu_smoke`の3回バイト一致を確認済みです。

```text
[PICOCALC][LCD][VERIFY] app_status=pass
[PICOCALC][SD][SMOKE] stage=end status=ok result_stage=ok detail=0
[PICOCALC][SMOKE] lcd=ok sd=ok stage=ok detail=0 status_region=green
```

**ただし、人間の実機検証がゼロになったわけではありません。** multicoreと音声の
実再生は未対応です。そして何より、**実機の色・向き・可読性・聴感はエミュレーターでは
判定できません。** エミュレーターは「firmwareが何を書いたか」は再現しますが、
「人がそれをどう見るか、どう聞こえるか」は再現しません。最終的な確認には
引き続き実機が必要です。

Milestone 1（Firmware backend）はこれで完了です。

**続いてMilestone 3（scenario runner）とMilestone 2（host backend）も完了しました
（2026-08-05）。** きっかけは実際にアプリを1本書いたことです。テトリス風ゲームを
firmware backend上だけで作ってみたところ、`--keys`が起動前にキーを一括投入する
だけで「画面を見て次のキーを決める」ことができず、**ライン消去のコードが一度も
発火しないまま**残りました（記録:
[`DOGFOODING_20260805.md`](docs/DOGFOODING_20260805.md)）。

scenario runnerはこれに応えます。JSON手順を実行ループの内側で評価するため、
1ステップが画面とUART出力を見てから次のキーを決められます。証拠として、
このscenarioが実際に**ライン消去を発火させ**ました（13ライン、スコア1400、
種を固定した乱数から事前計算した予測スコアと一致することを確認）。詳細は
[`SCENARIO_RUNNER.md`](docs/SCENARIO_RUNNER.md)。

host backendはBSPの公開APIをホストのモデルに対してビルドし、アプリのロジックを
RP2040バイナリを作らずに1秒未満で検査できるようにします。framebuffer digestの
正規形はfirmware backendと同一なので、安いhost実行を高いfirmware実行の代わりに
使ってよい根拠が取れます。ただし**firmware backendが権威であることは変わりません**。
詳細は[`HOST_BACKEND.md`](docs/HOST_BACKEND.md)。

現行`test --mode host`はBSPの専用`emu_smoke`を実行します。Host backendが完成したことは、
任意アプリのロジック試験が自動接続されるという意味ではありません。PicoTetrisはR3で
hardware-freeなゲーム規則へ分離し、666 checksの個別host unit testを追加しました。

このscenarioの実装中、エミュレーター側の欠陥も1件見つかりました。キーボード
モデルのFIFOに上限がなく、滞留が32の倍数に達するとBSPの`key_info[0] & 0x1f`が0を
読んでドライバが恒久停止していました。実機のコントローラは深さを5ビットでしか
報告できずその状態になり得ないため、エミュレーター側の欠陥として修正済みです。

実装順と受入条件は[Milestones](docs/MILESTONES.md)と
[Emulator implementation roadmap](docs/EMULATOR_ROADMAP.md)、作業単位と経緯は
[詳細実装計画](docs/IMPLEMENTATION_PLAN.md) §4、エミュレーターの対応・未対応の
一覧は[capability manifest](firmware-validation/capability.json)にあります。

生成契約・source identityの固定（R0）、R1（SD/FAT32、backend verdict、公式keyboard
conformance）、上位CLI/target registry（R2）、PicoTetris正式回帰（R3）は完了しました。
R4の3リポジトリfull品質ゲート/CIも完了しました。backendのtest・fmt・Clippy gate、generatorの
親Git継承修正、schema 3 versioned validation、PicoTetris R4 revision、PicoTetrisの
unit＋固定RP2040再現build、`picocalc_emu`のportable/host/target-schema/firmware regressionを
clean runnerで合格させました。次はR5の同一BIN実機相関です。R3の全SHAと受入結果は
[`R3_PICOTETRIS_REGRESSION.md`](docs/R3_PICOTETRIS_REGRESSION.md)、keyboard conformanceは
[`KEYBOARD_CONFORMANCE.md`](docs/KEYBOARD_CONFORMANCE.md)にあります。詳細な依存関係と
受入条件は[Milestonesの「現在の実行順序」](docs/MILESTONES.md#現在の実行順序2026-08-06-r4完了反映)が正典です。

R5実機着手前の性能baselineとして、Ryzen 5 5600X上のWSL2で`picotetris-r4`を10回測定し、
実時間比中央値5.874%（仮想3.715秒をwall 63.247秒、約17.025倍遅い）を記録しました。
全runのreport/UART/PNGは一致しています。これは実機合格ではなく、実機相関前の速度基準です。

## 読む順番

AIがアプリを作る場合は、まず [AI向け開始手順](AI_START_HERE.md) を読みます。
本書は目的と全体像、`AI_START_HERE.md`は変更範囲・A/B選択・ログ判定を含む正規手順です。
文書全体の読む順序は末尾の[文書](#文書)にあります。

## 現在できること

- 実機で動作したLCD・キーボード・SD/FatFS実装を固定して再利用する
- AIの通常の変更範囲を生成プロジェクトの`app/`へ限定する
- LCD初期化とCS分割をhost SPI fakeで実トランザクション検査する
- JSON board profileからC++定数を一方向生成し、差分をCI検査する
- SD、audio pinに加え、公式STM32 keyboard firmwareとRP2040 consumerのsource fingerprintを検査する
- SDのmount/write/sync/read/compare/removeスモークテストを実機で実行する
- LCDのsolid fillとRAMRDによるGRAM readback一致検証を実機で実行する
- Picocalc_ment実績ベースの48 kHz PWM/DMA音声ストリームと固定サイン参照試験を提供する
- PicoCalc V2の8 MiB PSRAMをPIO1で初期化し、read/write APIと範囲管理付きBufferを提供する
- LCD・キーボード・SD・PSRAM・音声を個別にコピーできる最小例を提供する
- 基準プロジェクトのcommitと証拠ファイルSHA-256を完全照合する
- Canonical BSP自身の実機結果を構造化台帳へ記録する
- RP2040用ELF/BIN/UF2を生成する

エミュレーター（第2段）のfirmware backendでは、A/B両系統について次ができます。

- Pico SDK形式のBINをPC上でdirect bootし、決定的に実行する
- UART0の出力を取得する
- symbol/PC一致で到達点を判定する（`main()`到達など）
- LCD framebufferをRGB565 hashとPNGで取得する（A: SPI1/RGB666、B: PIO0/RGB565）
- 8 MiB PSRAMの内容を範囲指定で検証する（実機一致するチップIDを含む）
- SPI0のSDカードで、FAT32（既定）とFAT16（明示）の
  mount/write/sync/read/compare/removeを完走する
- **JSON scenarioで条件付きにキーを投入し、画面・UART出力を機械的に判定する**
- PWM設定と未対応MMIOアクセスを観測する
- `python3 tools/picocalc.py test --mode firmware --target <id> --firmware <bin>`で、
  target契約に固定したbackend設定と期待値を1コマンドで検証する

host backendでは、アプリのロジックをRP2040バイナリを作らずに検査できます。

- BSPの公開APIをホストのモデル（framebuffer・keyboard FIFO・PSRAM・SDカード）に
  対してビルドし、ネイティブで直接実行する
- `src/filesystem.cpp`はデバイスと同一ソースを未改変で使う
- framebuffer digestはfirmware backendと同一の正規形で、両者を直接比較できる
- `python3 tools/picocalc.py test --mode host`で1秒未満・3回連続バイト一致を確認する

## 現在できないこと（これができないため、人間の実機検証がまだ必要です）

- SPI/I2C故障の注入
- 音声の実再生・multicore・UF2直接ロード
- SDカードの取り外し・書き込み禁止・マルチブロック転送
- directory-backed Fast SDモード（host backend）
- host合格と実機結果の相関を自動集計する（Milestone 4）
- JUnit成果物、100回連続実行の決定性検査（R4受入条件外。必要時は独立したsoak作業にする）

**そして、エミュレーターが原理的に判定できないものがあります。** 実機の色の見え方、
画面の向き、文字の可読性、音の聞こえ方です。エミュレーターは「firmwareが何を書いたか」
は再現できますが、「人がそれをどう見るか」は再現しません。ここは人間に残ります。

実装順は[Milestones](docs/MILESTONES.md)、対応・未対応の詳細は
[capability manifest](firmware-validation/capability.json)にあります。

## Firmware backendの取り扱い

`picoem-picocalc`は`0x4D44/picoem`の履歴と`MIT OR Apache-2.0`ライセンスを維持した
独立派生リポジトリです。`picocalc_emu`へソースをコピーせず別リポジトリで保守し、
正確なcommitを固定して利用します。初期段階では単一ホストスレッドの
`ExecutionModel::Serial`を正しさの基準とし、最初にSPI1のA、次にPIO1 PSRAMとI2C1
keyboard、その後PIO0のB、SPI0 SD、PWM/DMA audio、multicoreを段階的に接続します。

これはBSPと同じ規律をエミュレーター層へ適用したものです。BSPで
`bsp/vendor/`（Bの無改変コピー、Aの独自実装、由来を記録した派生コード）と
`bsp/src/`（薄いアダプタ）を分けたのと同様に、
汎用RP2040コアへPicoCalc固有の条件を埋め込まず、PicoCalc側はboard adapterと
device modelに置きます。**手作業の再実装で実績済みの転送契約を変質させない**という
Canonical BSPの教訓は、エミュレーター本体にもそのまま適用されます。

`rp2040js`はRP2040周辺機器の挙動、テスト構成、実装差を調べる比較資料として
利用しますが、`picocalc_emu`へ接続する主バックエンドにはしません。一つの正統な経路
だけを持ち、二つの実装を混ぜないためです。

最初のFirmware縦断対象は、ClockworkPi公式の無改変`Code/picocalc_helloworld`です。
公式サンプルを選ぶのは、自分で書いたコードで自分のエミュレーターを検定すると、
合格する方向へ無意識に調整できてしまうためです。まずAのSPI1/RGB666 3-byte転送で
`Hello World PicoCalc`を320×320 framebufferへ決定的に描画し、その後、PSRAM全域試験、
I2C keyboard controller、scripted key echoまで通して完全合格とします。

これはCanonical BSPの推奨表示デフォルトを変更するものではありません。公式サンプルAの
縦断合格後、BのPIO0/RGB565/LCD DMA OFFもGate 7でFirmware conformanceを完了しています。
詳細な実装順と受入条件は
[Emulator implementation roadmap](docs/EMULATOR_ROADMAP.md)を参照してください。

## 30秒で試す

必要条件は**Python 3.9以降**とC++17 host compilerです。clone単体で動くportable
検証にはPico SDKは不要です。

`tools/`のスクリプトは`list[str]`などのビルトインジェネリクス記法（PEP 585）を
使うため、Python 3.8では起動時に`TypeError`になります。CIは3.11で実行しています。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
```

生成後、通常編集するファイルは`../MyApp/app/main.cpp`です。

ビルドにはPico SDKを明示します。

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
```

`PICOCALC_DIAGNOSTIC_MODE`を宣言するアプリでは、通常の`build`がこのcache値を明示的に
`OFF`へ戻します。以前の診断buildの`CMakeCache.txt`が残っていても、製品UF2へ診断処理を
混入させません。診断を意図して作る場合だけ`--diagnostic-mode`を指定します。

生成物は`../MyApp/build/picocalc_app.uf2`です。引数を省略した推奨表示デフォルトは
`pio-rgb565`（RGB565、PIO blocking、LCD DMAなし）です。

LCDは実績のある二種類を別BSPとして選択できます。ファイル名はどちらも同じです。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
python3 tools/picocalc.py build --project ../MyApp --lcd-variant hwspi-rgb888
```

前者は推奨デフォルトのPIO0/RGB565、後者は互換・診断用のSPI1/
`COLMOD=0x66`です。AのLCDバスはRGB666をR/G/B各1バイトの3-byte containerで送るため、
既存variant名は`hwspi-rgb888`のまま維持します。選択した版はUF2の名前ではなく、
起動ログ先頭行の`variant`とソースコミットで識別します。

PSRAMとLCDの共存クロックを実機で測る場合は、標準UF2名のまま専用モードを
ビルドします。B（PIO/RGB565）でLCDを動かしながら、PSRAMの候補clkdivを全て
検証し、ログの`[PICOCALC][PSRAM][COEX]`を比較します。

```sh
python3 tools/picocalc.py build --project ../MyApp \
  --lcd-variant pio-rgb565 --psram-lcd-coexist-test
```

このモードの起動ログ先頭は`bsp=0.8.8`かつ
`app=0.8.4-b-pio-rgb565-psram-lcd-coexist`です。

### UF2と版管理の運用規約

PicoCalcではUF2をSDカードへコピーして使うため、同じプロジェクト内でUF2の
ファイル名を変更しない。標準templateの生成物は`build/picocalc_app.uf2`、PicoTetrisは
`build/PicoTetris.uf2`に固定し、検証版・分岐版でもプロジェクト内の名前を維持する。
UF2自体はリポジトリやプロジェクトの
成果物として保存せず、必要なときに対象コミットから生成する。通常ビルドは
ビルド時刻を埋め込むためSHA-256が変わり得る。実機記録など再現性が必要な
証拠ビルドでは、`--build-timestamp YYYY-MM-DDTHH:MM:SSZ`を指定し、同じ
ソース、BSP、SDK、ツールチェーン、ビルド設定を揃えた場合に限り同一成果物を
再生成できる。

版の識別はファイル名ではなく、次の組み合わせで行う。

- 対象ブランチとソースコミット（`git rev-parse HEAD`）
- BSP版番号
- アプリ版番号またはビルドサブコメント（例：`0.2.1-sd-validation`）
- UF2のSHA-256

起動ログの1行目は必ず次の`[PICOCALC][BOOT]`行とし、BSP版、ソースコミット、
ビルド時刻を出力する。実機検証ではこの1行を読んでから、画面・
SD・キーボードの動作を判定する。特別な検証を行う場合は版番号またはビルド
サブコメントをソースへ反映してコミットし、そのコミットからUF2を作る。

`tools/picocalc.py build`は既定ではビルド開始時刻をUTCでUF2へ埋め込み、生成したUF2の
SHA-256をプロジェクト直下の`.picocalc-build-history.json`へ記録します。再現性が必要な
場合は`--build-timestamp`で固定値を指定します。同じBSP版と
アプリ版で過去に成功したビルドがある場合は警告しますが、再ビルドは禁止しません。
同じ版を意図的に使う場合はそのまま続行できます。新しいリリースや実機検証対象を
区別する場合だけ、テンプレートの版番号またはビルドサブコメントを更新し、先に
コミットしてください。

ビルドログには次の識別情報が出ます。

```text
[PICOCALC][BOOT] bsp=... app=... variant=... bsp_git=... app_git=... build=...
[PICOCALC][APP] version=... build=...
```

`build`はビルド開始時刻です。UF2を実機へ
書き込む前に、コマンドが出力するSHA-256と実機ログの版・時刻を記録してください。

`app_git`は、`--project`で指定したdirectory自身がGit working treeのrootである場合だけ
そのcommitを記録します。生成先が別repositoryの子directoryに偶然置かれても、親のcommitを
継承せず`untracked`になります。`bsp_git`はこれとは別の由来情報で、生成時metadataに固定した
canonical BSP source commitと、コピー後BSP treeのdirty状態から決まります。

## 検証レベル

### Portable

cloneしたこのリポジトリだけで実行します。生成board header、LCD
transaction、BSP source fingerprint、実機台帳、テンプレートを検査します。

```sh
python3 tools/picocalc.py verify
```

### Reference evidence

実働プロジェクトをcatalog指定のcommitで用意し、証拠ファイルを完全照合します。
既定ではこのリポジトリの親ディレクトリを検索します。

```sh
python3 tools/picocalc.py verify --references --strict-commit
```

別の配置なら次のように指定できます。

```sh
python3 tools/picocalc.py verify \
  --references \
  --strict-commit \
  --reference-root /path/to/reference-workspace
```

取得元URL、commit、証拠SHA-256は
[reference-projects/catalog.json](reference-projects/catalog.json)にあります。
参照プロジェクトがまだ手元にない場合は、空の出力ディレクトリ名を指定して固定commitを
自動取得できます。

```sh
python3 tools/picocalc.py fetch-references --output /path/to/references
python3 tools/picocalc.py verify \
  --references \
  --strict-commit \
  --reference-root /path/to/references
```

## Canonical hardware contract

| 機能 | 実機基準 | 重要条件 |
|---|---|---|
| LCD A（互換・診断） | `bsp/vendor/lcd_hwspi_rgb888.cpp` | SPI1 GP10–15、25 MHz、COLMOD `0x66`、RGB666を3-byte RGB888 containerで送信、MADCTL `0x48`、window transaction中CS保持 |
| LCD B（推奨デフォルト） | `bsp/vendor/lcd_rgb565_pio.cpp` | PIO0 blocking、LCD DMAなし、clkdiv `2.0`、COLMOD `0x65`、RGB565を2 bytes/pixelで送信、RAMRD時はSIOへ切替 |
| Keyboard | [ClockworkPi公式`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)（STM32F103R8T6 firmware。ローカル: `/home/fuyuki/pico_dvl/codex/PicoCalc/Code/picocalc_keyboard`） | **protocol producerの一次リファレンス**。I2C target `0x1f`、register `0x04`/FIFO `0x09`、31-event FIFO、key state・modifier・repeat・overflow・backlight・battery・power。`picocalc-life`はRP2040 consumerの実機証拠 |
| SD/FatFS | `picocalc-life` | SPI0 GP16–19、detect GP22、400 kHz init、12 MHz run |
| Audio evidence | `Picocalc_ment` | GP26/27、48 kHz PWM/DMA、wrap 255、固定サインとPCM ring producer |
| PSRAM | `pico_rescue` | 8 MiB、PIO1、CS20/SCK21/MOSI2/MISO3、24-byte以下のread/write、250 MHz通常候補は2/0→3/0→1.5/1、125 MHz通常候補は1/0→1.5/0→2/0→3/0→4/0 |

通常のアプリ開発では`bsp/`を変更しません。BSP変更にはsource fingerprint更新、
reference evidence照合、実機相関確認が必要です。

## エミュレーターと実機の相関（2026-08-05）

Gate 7でエミュレーターが`app_status=pass`と判定したのと**同一ソース・同一設定**の
UF2を実機で3回起動し、予測と突き合わせました。

| 項目 | エミュレーター | 実機 | 一致 |
|---|---|---|---|
| BOOT行（版・commit・timestamp） | 予測どおり | 同一 | ✓ |
| system clock | `actual_khz=250000` | 同じ | ✓ |
| **LCD `app_status`** | **pass** | **pass**（3回とも） | **✓** |
| GRAM readback（全5色＋パターン） | mismatches=0 | 同じ | ✓ |
| 音声 | `underruns=0` | 同じ | ✓ |
| PSRAM | fail | **pass** | **✗** |
| SD | 未対応（停止） | pass | 既知のギャップ |
| keyboard | この経路では未到達 | 138イベント | 既知のギャップ |

**「エミュレーターがpassと言い、実機がfailする」事例は0件でした。** これがこの
プロジェクトの最も避けたい失敗であり、その不在がGate 7の結果を信頼してよい根拠に
なります。PSRAMの不一致は逆方向（エミュレーターが厳しすぎる）で、危険ではありませんが
モデルの欠陥です。記録は
[bsp-0.8.8-20260804-02](hardware-validation/records/bsp-0.8.8-20260804-02.json)。

**上表のPSRAMとSDの2件は、この相関確認と同じ日（2026-08-05）に解消しました。**
PSRAMは実機が返したチップIDを根拠にRead IDを実装し、SDはSPI0のカードを実装して
templateの全機能スモークが完走するようにしました。keyboardは別のscenario実行で
138イベントを観測済みです。この表は相関確認の**時点の記録**として残しています。

## Canonical BSP自身の実機記録

参照プロジェクトの証拠と、抽出後BSP自身の証拠は分離しています。実機検証時は
[hardware-validation](hardware-validation/README.md)のテンプレートへPicoCalc
revision、toolchain、SDカード、UF2 SHA-256、ログ・写真を記録します。

**A（`hwspi-rgb888`）とB（`pio-rgb565`）のLCD転送は、BSP 0.4.0で実機合格しました。**
2026-07-30、Aはcommit `e2d53ad55afa`、Bはcommit `f763b91eae95`のUF2で、既知パターンの
表示とRAMRDによる全色一致（`app_status=pass`）を確認しています。AはさらにSDスモークと
キーボード148イベント（pressed/released各74）も合格しています。記録は
[Aの台帳](hardware-validation/records/bsp-0.4.0-20260730-02.json)と
[Bの台帳](hardware-validation/records/bsp-0.4.0-20260730-01.json)です。

この0.4.0台帳は過去のA/B分離検証記録であり、Bのキーボードと装置識別情報が未記入のため
`overall_status=pending`を保持しています。履歴recordは後から書き換えません。
最新BSP 0.8.8では、ClockworkPi PicoCalc `CPI2.0`、SanDisk Ultra 32 GB/FAT32を使用し、
LCD readback 3回、keyboard 138イベント、SD、audio、PSRAMを確認しました。
`bsp-0.8.8-20260804-02.json`は`overall_status=pass`であり、0.8.8のLCD・keyboard pendingを
閉じています。実機では一度に一方だけを
`build/picocalc_app.uf2`へ生成して検証します。UF2は保存せず、通常ビルドは各ソース
コミットから生成し、実機記録用は固定タイムスタンプの証拠ビルドとして生成します。

## RAMRDの解釈

RAMRDはこの実機で正常に動作します（`life`のスクリーンショット取得ビルドが同じ手順で
正しい画像を出力しています）。BのRAMRDは`life`の手順をそのまま使い、**読み値が期待と
違う場合はパネルではなく書き込み経路を疑います。**

これは経験則ではなく実測に基づく規則です。過去に読み値の不一致を「この個体のRAMRDは
信頼できない」と実機側へ帰属させた判断は誤りで、後に撤回しています。RAMRDは
「書き込みが成立していない」ことを正しく報告していました。詳細は
[LCD不動作調査記録](docs/LCD_INVESTIGATION_20260729.md)にあります。

## BSPの変更履歴

版ごとの変更内容と理由は[`bsp/CHANGELOG.md`](bsp/CHANGELOG.md)に分離しました。
本書と`bsp/README.md`には現行0.8.8の契約だけを置きます。過去版の記述を
現行仕様として実装・検証に使わないでください。

## 文書

分類は読む順序です。①を読まずに②以降へ進まないでください。

### ① 必ず読む

- [AI向け開始手順](AI_START_HERE.md) — 目的、変更範囲、A/B選択、ログ判定
- 本書 — 目的と全体像

### ② 作業に着手するとき読む

- [現在の実装状況](docs/IMPLEMENTATION_STATUS.md) — 今どこまで動くか
- [Canonical BSP](bsp/README.md) — 守るべきハードウェア契約（**現行のみ**）
- [Milestones](docs/MILESTONES.md) — **実装順序の正典**。他文書の段階番号はここへ対応付ける
- [Sol / Luna 開発運用](docs/DEVELOPMENT_WORKFLOW.md) — 役割と受入の境界
- [実機検証台帳](hardware-validation/README.md) — 実機結果の記録方法

### ③ 該当作業のときだけ参照する

- [要求仕様](REQUIREMENTS.md) — 全体要求と受け入れ条件
- [Firmware backend開発方針](docs/FIRMWARE_BACKEND.md) — `picoem-picocalc`の扱い
- [Emulator implementation roadmap](docs/EMULATOR_ROADMAP.md) — Gate 0〜7の受入条件
- [詳細実装計画](docs/IMPLEMENTATION_PLAN.md) — 実施済みMilestone 1をGate別に分解した計画と判断記録
- [Scenario runner](docs/SCENARIO_RUNNER.md) — JSON scenarioの形式、条件付きキー投入、画面の機械判定
- [Host backend](docs/HOST_BACKEND.md) — アプリロジックをホストのモデルに対してビルドし単体試験する
- [R0 baseline](docs/R0_BASELINE.md) — 開始点、生成契約、PicoTetris source identityと再取得bundle
- [R2 Template B再現手順](docs/R2_TEMPLATE_B_REPRODUCTION.md) — clean generator cloneとGit管理外生成先を分離し、固定BIN/UF2を再生成する契約
- [R3 PicoTetris正式回帰](docs/R3_PICOTETRIS_REGRESSION.md) — host logic、再現可能build、firmware 3回決定性と現行bundle
- [Versioned validation](docs/VERSIONED_VALIDATION.md) — schema 3 target revision、attestation、時点証拠の不変契約
- [R4 品質ゲートとCI](docs/R4_CI.md) — 3リポジトリのclean-runner full gate、job境界、private backend認証
- [R5実機相関前の実時間性能](docs/R5_REALTIME_PERFORMANCE.md) — 理論上限、WSL 10回実測、再測定手順
- [capability manifest](firmware-validation/capability.json) — エミュレーターの対応・未対応機能
- [公開前チェックリスト](docs/RELEASE_CHECKLIST.md) — 本リポジトリを公開する時点で満たす条件
- [将来のエミュレーター設計](docs/DESIGN.md) — **未実装**の設計。Phase番号は旧体系
- [Vendored drivers](bsp/vendor/README.md) — driverごとの由来、変更規約、呼び出し粒度
- [Third-party notices](THIRD_PARTY_NOTICES.md) — third-party由来コードの扱い

### ④ 歴史記録（現在の手順ではない）

以下を現行仕様として実装・検証に使わないでください。過去のUF2やコミットを
現在版として再利用しないでください。

- [LCD不動作調査記録](docs/LCD_INVESTIGATION_20260729.md) — このプロジェクトが
  なぜエミュレーターを必要とするかを示す一次記録
- [開発・実機検証総合履歴](docs/PROJECT_HISTORY_20260729.md)
- [ドッグフーディング記録](docs/DOGFOODING_20260805.md) — 実アプリ（PicoTetris）を
  書いて見つけたワークフローの穴と、その解消記録
- [BSP変更履歴](bsp/CHANGELOG.md)

## プロジェクトの位置付け

このリポジトリを「PicoCalc向けBSPスターターキット」と要約しないでください。
それは目的ではなく、目的に到達するための第1段です。

**第一目的は、AIがPicoCalc向けプログラムを自ら観測・検証・修正できることです。**
人間の実機検証回数は、その効果と予測精度を測る成果指標です。
第1段（Canonical BSP）は整備済みで、第2段（エミュレーター）はMilestone 1〜3を完了し、
**AIが自作アプリの画面とキー入力をPC上で検証できる**段階に到達しました。標準
templateから生成したプロジェクトが、LCD描画とGRAM readbackまで通ります。

LCD、PSRAM、SD、keyboardを使う標準templateと、条件付きscenarioまでPC上で観測できます。
上位CLIのfail-closed判定とtarget registryはR2、PicoTetrisの個別host unit testと正式targetは
R3、3リポジトリの継続CIへの接続はR4で完了しました。また実機の色・向き・可読性・聴感は
エミュレーターでは判定できません。
**人間の実機検証はまだゼロになっていません。**

到達度は感覚ではなく、変更単位に`host_pass`、`host_fail`、`hardware_pass`、
`hardware_fail`、`hardware_required`を記録して測ります。ただし実機回数の削減より
予測精度を優先します。エミュレーターで合格したものが実機で落ちる割合が許容値を
超えた機能は、モデルが直るまで`hardware_required`へ戻します。
**エミュレーターは実機の代用であって、真実ではありません。**
