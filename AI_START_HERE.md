# AI向け開始手順

このファイルを最初に読みます。ここに書かれている内容が、PicoCalc上で動く
アプリを作るときの短い正規手順です。過去の調査経緯や将来のエミュレーター設計は
この手順を上書きしません。

## 最初に理解すること

**あなたが書いたコードを実機で確かめるのは、人間です。**

PicoCalcは[ClockworkPi](https://www.clockworkpi.com/picocalc)の電池駆動の
スタンドアロン携帯マイコンです（4インチ320×320 IPS、I²C接続の67キーQWERTY、
SDカード、8 MB PSRAM、PWMスピーカー2基。メインボードはRaspberry Pi Picoを
差し替え。本リポジトリの対象はRP2040搭載構成）。PCに常時接続された開発ボード
ではありません。

そのため、あなたが1回ビルドするたびに、人間が次を手作業で行います。

```text
UF2をSDカードへコピー → PicoCalcへ挿す → 電源を入れる → 画面を見る
→ 写真を撮る → UARTログを回収する → あなたへ渡す
```

**あなたには画面もSPI波形もSDカードの中身も見えません。** 見えるのは人間が
渡してくれたログと写真だけです。つまり、あなたの推測が1回外れるたびに、
人間がこの往復を1回払います。

このリポジトリの第一目的は、**PicoCalc向け開発をAIに依頼したとき、AIが
エミュレーター上で結果を観測・検証し、失敗原因を特定して修正できるようにすること**
です。人間の実機検証回数の削減は、その効果を測る成果指標です。あなたはその枠組みの
利用者であり、同時に検証対象でもあります。

したがって、この手順書のすべての規則は次の一点に還元されます。

> **推測でハードウェアを触らない。動作実績のある実装を、実績のある呼び方で使う。**

過去に、この規則を破って動作実績のある転送コードを手作業で再実装した結果、
LCDに1枚表示させるだけでUF2ビルド17回・実機書き込み15回以上を人間に払わせた
記録があります（[LCD不動作調査記録](docs/LCD_INVESTIGATION_20260729.md)）。
確定した原因は、再実装時に転送処理と呼び出し粒度を変質させたことでした。
以降の規則は、この事故の再発防止として読んでください。

## 監督体制

Solが要件、計画、設計、受入、レビュー、統合、commit/push、CI・実機結果の判定と
最終報告を担当します。LunaはSolが限定した実装・調査・定型処理を行い、差分と検証結果を
提出します。詳細な委任、報告、検収、権限の境界は
[`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md)を参照してください。

## このリポジトリの現在の段階

目的は3段階で達成します。現在は第1段だけが完成しています。

| 段 | 内容 | 状態 | あなたへの影響 |
|---|---|---|---|
| 1 | Canonical BSP — 実績済みの転送契約と由来を固定し、あなたの変更範囲を`app/`へ限定する | ソース・portable基盤は**完了**（BSP 0.8.8）。0.8.8実機台帳はLCD/keyboard pending | ハードウェア初期化を書かない。既存APIを呼ぶ |
| 2 | エミュレーター — PC上で実行し、画面・SPI/I²C・SDをあなた自身が観測する | **未実装** | **まだ自分で確認できない。人間にログと写真を依頼する** |
| 3 | 実機相関 — 実機結果を台帳へ記録し、予測精度を校正する | 一部 | 実機結果は必ず台帳へ記録する |

第2段が未実装であるため、**あなたは現時点で自分の変更が正しいかを自力で確認できません。**
だからこそ、推測でハードウェア層を触らないことと、人間へ渡す1回のUF2の情報量を
最大にすること（版の識別、機械可読ログ、合否の判定基準を先に決めておくこと）が、
現在のあなたの最重要責務です。

現在のCanonical版はBSP `0.8.8`です。標準templateのアプリ版名は`0.8.4-*`のまま
独立して管理されています。実機で使用する対象は、ログ先頭の`[PICOCALC][BOOT]`に出る
`bsp`、`app`、`variant`、`bsp_git`、`app_git`で識別します。

## 作業別の入口

- 通常のアプリ作業: 本書の「AIが行う正規手順」以降を読む。
- エミュレーター作業: `docs/MILESTONES.md` → `docs/EMULATOR_ROADMAP.md` →
  `docs/IMPLEMENTATION_PLAN.md` → `docs/FIRMWARE_BACKEND.md`の順に読む。
- BSP・driver作業: `bsp/README.md` → `bsp/vendor/README.md` →
  `THIRD_PARTY_NOTICES.md`の順に読み、通常アプリの変更範囲と混同しない。

エミュレーターのFirmware backendはRust製`picoem-picocalc`を主系とし、
`ExecutionModel::Serial`と継承済み回帰テストから始めます。`rp2040js`は周辺機器の
振る舞いと実装方法の比較参考であり、主バックエンドではありません。

## AIが行う正規手順

リポジトリのルートで実行します。

```sh
python3 tools/picocalc.py verify
python3 tools/picocalc.py new MyApp --output ../MyApp
export PICO_SDK_PATH=/path/to/pico-sdk
python3 tools/picocalc.py build --project ../MyApp
```

通常buildは、プロジェクトが`PICOCALC_DIAGNOSTIC_MODE`を宣言している場合、その値を必ず
`OFF`へ明示設定する。古いbuild cacheから診断modeを継承しない。診断UF2を意図する場合だけ
`--diagnostic-mode`を付ける。

生成物は常に次です。

```text
../MyApp/build/picocalc_app.uf2
```

PicoCalcのSDカード上でファイル名を管理するため、UF2名と場所を変更しません。
実機へコピーする前に、ビルドが出力するSHA-256と実機ログ1行目を記録します。

## AIが変更してよい場所

通常のアプリ開発で変更するのは、生成されたプロジェクトの次だけです。

```text
MyApp/app/main.cpp
MyApp/assets/       （必要な場合だけ）
```

LCDのGPIO、LCD初期化、転送形式、SD初期化、キーボードI2C、PSRAMクロックを
`app/`へコピーして書き直してはいけません。公開ヘッダーのAPIを呼びます。
生成された`MyApp/bsp/`は、そのプロジェクトが使用するBSPの固定コピーです。
`board_generated.h`はJSON profileから生成されるため直接編集しません。

BSPやprofileを変更する作業は通常のアプリ作業ではありません。変更する場合は、
変更理由、source fingerprint、host test、実機検証を同じコミットに記録します。

## LCDはA/Bから一つだけ選ぶ

AとBは同じドライバに統合しません。個体や目的に応じてビルド時に一つを選びます。

| variant | 用途 | 実際の転送 |
|---|---|---|
| `pio-rgb565`（B、推奨） | 通常のアプリ | PIO0 blocking、RGB565、2 bytes/pixel、LCD DMA OFF、clkdiv 2.0 |
| `hwspi-rgb888`（A） | 互換・bring-up・診断 | SPI1 blocking、RGB666 wire、3 bytes/pixel、25 MHz |

アプリの公開画素形式は常にRGB565です。Aの3-byte転送をBへ持ち込んだり、Bの
PIO転送をAへ持ち込んだりしません。選択例は次です。

```sh
python3 tools/picocalc.py build --project ../MyApp --lcd-variant pio-rgb565
python3 tools/picocalc.py build --project ../MyApp --lcd-variant hwspi-rgb888
```

実機検証は同時に二つ行わず、一つずつ同じ
`../MyApp/build/picocalc_app.uf2`を生成します。A/Bの判定はUF2名ではなく、
ログ先頭の`variant`と`app_status`で行います。

## PSRAMの制約

PSRAMは8 MiB、PIO1、CS/SCK/MOSI/MISOはGP20/21/2/3です。250 MHz通常起動の
推奨候補は、最初に`clkdiv=2.0/fudge=false`（62.5 MHz）を使い、失敗時だけ
`3.0/false`、`1.5/true`へ進みます。高速候補を通常設定へ勝手に追加しません。

公開APIのread/writeはBSP内部で最大24 byteへ分割されます。PSRAMは任意機能で、
起動ログが`status=unavailable`ならSRAMとして扱わず、アプリ側で代替動作を選びます。
LCD更新との共存速度を測るときだけ、B専用の次のモードを使います。

```sh
python3 tools/picocalc.py build --project ../MyApp \
  --lcd-variant pio-rgb565 --psram-lcd-coexist-test
```

## 音声の扱い

既定の`PICOCALC_AUDIO_REFERENCE_TONE=ON`は、実機動作確認済みの固定1 kHz音を
`picocalc::init()`中に開始します。標準テンプレートはLCDのGRAM検証が終わった直後に
`picocalc::audio::stop()`を呼び、次のログを出します。

```text
[PICOCALC][AUDIO] status=stopped reason=lcd_verify_complete
```

PCMを使うアプリは、`PICOCALC_AUDIO_REFERENCE_TONE=OFF`でビルドし、
`audio::init()` → `audio::write_sample()` → `audio::start()`の順に使います。
不要になったら必ず`audio::stop()`を呼びます。最小例は
`templates/rp2040-basic/examples/audio_stream.cpp`です。

## 実機ログの合格判定

画面だけで合否を判断しません。最低限、次を順番に確認します。

1. 最初の行が`[PICOCALC][BOOT]`で、意図した`bsp/app/variant/bsp_git/app_git`である
2. LCD各色の`[PICOCALC][LCD][VERIFY] ... status=pass`が出る
3. `[PICOCALC][LCD][VERIFY] app_status=pass`が出る
4. BではRAMRDの`format=rgb565`と期待値が一致する
5. LCD検証直後に音声停止ログが出る
6. SDの`[PICOCALC][SD][SMOKE] stage=end status=ok`が出る
7. キーボードを操作し、Pressed/Releasedイベントが記録される

LCDの`app_status=pass`は、塗りつぶしと既知パターンをGRAMから読み戻し、公開APIの
RGB565値と一致したという意味です。`stage=end status=drawn`だけではreadback合格を
意味しません。

## 版管理

実機に渡す版は、版番号またはサブコメントをソースへ反映してからコミットし、その
コミットからUF2を生成します。UF2自体は保存・コミットせず、同じ名前で再生成します。
ブランチを統合するときも、資産を捨てず、必要なソース・文書・検証をすべて統合します。

## 参照先の読み方

分類は読む順序です。①を読まずに②以降へ進まないでください。

### ① 必ず読む

- 本書
- `README.md`: 目的、PicoCalcとは何か、全体像

### ② アプリを作るとき読む

- `templates/rp2040-basic/README.md`: 生成後のビルドと起動時スモーク
- `bsp/README.md`: 固定ハードウェア契約（**現行0.8.8のみ**。過去版は`bsp/CHANGELOG.md`）
- `docs/IMPLEMENTATION_STATUS.md`: 実装済み範囲と実機確認状況
- `docs/DEVELOPMENT_WORKFLOW.md`: Sol / Lunaの責任境界

### ③ 該当作業のときだけ参照する

- `docs/MILESTONES.md`: **実装順序の正典**。他文書の段階番号はここへ対応付ける
- `REQUIREMENTS.md`: 将来のエミュレーターを含む要求仕様
- `docs/FIRMWARE_BACKEND.md`: `picoem-picocalc`を主系、`rp2040js`を比較参考とする方針
- `docs/EMULATOR_ROADMAP.md`: 無改変`picocalc_helloworld`から始める実装順と段階別受入条件
- `docs/IMPLEMENTATION_PLAN.md`: Milestone 1をGate別の作業単位へ分解した実行計画
- `docs/DESIGN.md`: **未実装**エミュレーターの将来設計。Phase番号は旧体系であり、
  実行順序は`docs/MILESTONES.md`が優先する
- `bsp/vendor/README.md`: driverごとの由来、変更規約、呼び出し粒度
- `THIRD_PARTY_NOTICES.md`: third-party由来コードの扱い

### ④ 歴史記録（現在の手順ではない）

以下を現行仕様として使わないでください。**古いUF2やコミットを現在版として
再利用しないでください。**

- `docs/LCD_INVESTIGATION_20260729.md`: LCD問題の調査記録。本書の規則の根拠
- `docs/PROJECT_HISTORY_20260729.md`: 開発・実機検証の総合履歴
- `bsp/CHANGELOG.md`: BSP版ごとの変更理由
