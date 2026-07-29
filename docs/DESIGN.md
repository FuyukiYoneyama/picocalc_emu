# picocalc_emu 将来設計

AI に PicoCalc 向けアプリを開発させるための利用者要求、標準開発フロー、
BSP・テンプレート・実働プロジェクトの扱いは
[REQUIREMENTS.md](../REQUIREMENTS.md) に定義する。本書は、その要求を実現する
将来のエミュレーターと検証基盤の技術構成を定義する。

> **実装状況:** Canonical BSP、RP2040 アプリテンプレート、プロジェクト生成器、
> 実働プロジェクト証拠台帳、静的契約検査、LCD/SD/keyboard 起動時スモークを
> Canonical BSP MVP 0.2.1 として実装済み。利用方法と未実装のエミュレーター範囲は
> [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) を参照。

## 1. 目的

`picocalc_emu` は、PC 上で PicoCalc 向けソフトウェアを反復実行・観測・検証するための開発環境である。
目的は、AI を含む開発ループで発生する実機への書き込み、再起動、キー入力、画面確認を PC 上で自動化し、通常の実機検証回数を 10 回程度から 1〜2 回程度へ削減することにある。

ここでいうエミュレーションの対象は、単なる CPU ではなく、アプリケーションから見える PicoCalc の動作契約である。

* 実機確認済みの Canonical PicoCalc BSP とプロジェクトテンプレート
* 実働プロジェクトから採取した正常画面、通信トレース、SD 操作結果
* LCD: ST7365P の ILI9488 互換 SPI コマンド、320x480 GRAM、320x320 可視領域、RGB565/18-bit 転送
* キーボード: STM32F103 側の I²C デバイス、アドレス `0x1f`、レジスタ/FIFO/修飾キー
* SD カード: FAT ファイルシステム、PicoCalc の `/firmware` および SD アプリ配置
* RP2040/RP2350 の GPIO、SPI、I²C、タイマ、乱数、UART/stdio、PSRAM、PWM/音声のうち対象アプリが利用する部分
* PicoCalc で使われる実行環境: Pico SDK C/C++、LVGL、PicoMite、uLisp、FUZIX の優先順

同梱の ST7365P 仕様書では内部 GRAM は 320x480 である。一方、既存ドライバは ILI9488 互換コマンドを使い、320x320 を可視領域としている。このため、LCD コントローラー、物理 GRAM、可視領域、回転・オフセットを別々のプロファイル値として扱う。

既存リポジトリには、LCD の GPIO 10〜15 と `spi1`、キーボード I²C の `i2c1`/SDA 6/SCL 7/アドレス `0x1f`、キーボードレジスタ定義が存在する。I²C 速度はアプリにより 10 kHz と 400 kHz が使われているため、デバイスの固定値ではなく各トランザクションの属性として扱う。

## 2. 成功条件

最初のリリースで、次の条件を満たすことを成功とする。

1. C/C++ の PicoCalc アプリを `picocalc_emu run` で起動できる。
2. 画面を連続フレーム、指定領域、または PNG として保存できる。
3. キー入力を文字列・キー列・JSON シナリオで再生できる。
4. 画面、キーボード FIFO、stdio、ファイル変更をテスト結果として記録できる。
5. 同じ入力シナリオを 100 回以上再実行しても結果が安定する。
6. 実機で一度確認した基準ケースについて、画面差分と入力応答差分が許容範囲内になる。
7. AI が一回のコマンドで「ビルド→起動→入力→アサート→成果物保存」まで実行できる。
8. Host 合格後に実機で不合格となる `host_pass → hardware_fail` の割合を計測できる。
9. 変更ごとのホスト実行回数、実機実行回数、検証時間を継続的に計測できる。

削減率は感覚ではなく、変更単位に `host_pass`, `host_fail`, `hardware_pass`, `hardware_fail`, `hardware_required` を記録して測定する。目標は、通常の修正サイクルの 80〜90% をホスト検証で完了させ、実機確認を 1〜2 回に抑えることである。ただし、実機回数の削減より予測精度を優先し、`host_pass → hardware_fail` が許容値を超えた場合は対象機能を実機必須へ戻す。

## 3. 全体構成

```text
AI / CLI / CI
      |
Project Generator ---- Canonical BSP ---- Reference Project Catalog
      |
  Scenario Runner ---- Golden/Trace Store ---- PNG/JSON/JUnit
      |
  Emulator Kernel
   |          |           |
  App API  Pico SDK shim  Device Bus
              |           |
        Virtual FS/Clock  Device models
                          |    |    |
                         LCD  KBD  SD/PSRAM
      |
  Host backend (SDL2 または headless)

Optional: firmware backend (ARM/RP2040/RP2350 CPU + MMIO)
```

新規アプリは空の構成から開始せず、Project Generator が実機確認済み BSP、CMake、リンカ設定、smoke test を含むテンプレートから生成する。通常の AI 開発では `app/` と `assets/` を変更対象とし、BSP、profile、ビルド基盤の変更は conformance test と実機相関テストを必要とする。

### 3.1 Emulator Kernel

イベントループ、仮想時刻、リセット、停止条件、ログ、スナップショットを管理する。実時間に依存させず、`sleep_ms` やタイマを仮想時刻で進める。これによりゲームや UI のテストを高速化し、タイミング依存バグを再現可能にする。

### 3.2 実行境界（初期版の主経路）

Pico SDK の依存部分をインターフェース化し、PC 用実装へリンクする。すべてを一つの HAL に押し込まず、次の四つの境界に分ける。

* App API: LCD 描画、キー取得、ファイル、時刻など、移植性の高いアプリ向け API
* Pico SDK shim: GPIO、SPI、I²C、timer/sleep、stdio/UART、IRQ のホスト実装
* Device Bus: CS/DC を含む SPI バイト列、速度とタイムアウトを含む I²C トランザクション
* Optional devices: PSRAM、PWM/音声、ADC、PIO/DMA の必要範囲

既存アプリは、アプリ本体の UI・状態機械・ゲームロジックを維持し、platform adapter または Pico SDK shim にリンクする。既存の `picocalc_helloworld` は PSRAM、PWM/IRQ、PIO、UART まで含む総合ハードウェアテストであるため、MVP の最初の fixture には使わない。最初に LCD とキーボードだけを使う小さな `emu_smoke` を作り、Optional devices の実装に合わせて既存 Hello World の対応範囲を広げる。

ホストビルドでは同じデバイスモデルを SDL2 表示版と headless 版で共有する。headless 版を標準にし、AI/CI は GUI を必要としない。

### 3.3 LCD モデル

初期プロファイルは `controller: ST7365P`、`command_compatibility: ILI9488-subset`、`gram: 320x480`、`viewport: 320x320` とする。コントローラーの全コマンドを最初から実装せず、既存コードが使う `MADCTL`、`CASET`、`PASET`、`RAMWR`、`COLMOD`、リセット、表示 ON/OFF、RGB565 APIからの18-bit wire書き込みを優先する。

内部では 320x480 の GRAM と、そこから切り出される 320x320 の可視 framebuffer を分ける。回転、開始座標、オフセット、RGB/BGR 順、範囲外アクセスはプロファイルに従って処理する。出力用 framebuffer は RGBA8888 に正規化する。

提供機能:

* `frame.png`、raw framebuffer、領域別ハッシュ
* フレーム単位の差分画像、PSNR/一致率、許容色差
* 画面の意味付け用アクセシビリティ/デバッグレイヤー（任意）
* 画面更新が停止した、想定領域外へ書いた、過剰転送した場合の警告

### 3.4 キーボードモデル

実機の STM32 ファームウェアを PC で動かすのではなく、ホスト上で同じ I²C レジスタ契約を提供する。FIFO、キー押下/解放、CapsLock/NumLock、修飾キー、割り込み状態、バックライト、バッテリー値をモデル化する。

I²C 速度、read/write 長、repeated-start、タイムアウトはトランザクションの一部として記録する。NACK、timeout、short read/write、FIFO overflow、バス速度違反、読み込み前待機不足をシナリオから故障注入できるようにする。

入力例:

```json
[
  {"at_ms": 0, "key": "ESC", "state": "down"},
  {"at_ms": 30, "key": "ESC", "state": "up"},
  {"at_ms": 100, "text": "hello"},
  {"at_ms": 500, "key": "ENTER", "state": "down"}
]
```

物理キー配列と論理キー列を分離し、AI は通常論理キー列を使う。配列・デバウンス・FIFO オーバーフローの検証だけは別シナリオで実行する。

### 3.5 SD/時刻/乱数

SD は用途に応じて二つのモードを提供する。

* Fast mode: 実ディレクトリを sandbox としてマウントし、アプリロジックと通常のファイル操作を高速に検証する
* Compatibility mode: FAT イメージまたはブロックデバイスモデルを使い、大文字小文字、8.3 名、容量不足、破損、SD_DET、カード抜去、書き込み遅延、マウント失敗を検証する

ファイルアクセスを記録し、テストごとに初期スナップショットへ戻す。PicoCalc SD の `/firmware`、`picoware/apps`、`fonts` などを fixture として取り込めるようにする。multi-booter と FAT/SD ドライバの検証では Compatibility mode を必須とする。

時計と乱数は seed を固定可能にする。現実時刻・ホストの乱数・ネットワークはデフォルトで禁止し、必要なテストだけ明示的な mock を与える。

## 4. 二つの実行モード

### Mode A: Host App（MVP）

Pico SDK のハードウェア依存を shim に置き換えてアプリを PC ネイティブ実行する。起動が速く、デバッガ・Sanitizer・カバレッジを使用できる。UI、入力、ファイル処理、状態遷移の大半をここで検証する。

初期対象は `emu_smoke`、`picocalc_lvgl_graphics_demo`、今後の AI 生成アプリとする。その後、`pico_multi_booter` の UI/SD ロジック、`picocalc_helloworld` の各ハードウェア機能へ段階的に対応する。

### Mode B: Firmware/System

UF2/HEX/ELF を対象に、実際の RP2040 ファームウェアを実行するバックエンドを追加する。RP2040 の初期バックエンドには `rp2040js` を採用し、検証済みの commit/tag を固定して利用する。完全互換を一括目標にせず、対象 ELF/UF2 と受け入れシナリオを各段階へ紐付ける。

このモードは「実機と同じバイナリを動かす」確認用であり、Mode A の高速な回帰テストを置き換えない。`rp2040js` の未対応機能は capability manifest で管理し、未対応 MMIO を成功扱いにしない。Wokwi クラウド版は相関確認の補助候補とするが、通常のローカル実行と CI は外部サービスに依存させない。

実装順は次の通りとする。

1. `rp2040js` で既知の Pico SDK UF2、UART、停止条件を確認する
2. GPIO、SPI1、I²C1 を PicoCalc LCD/keyboard model へ接続する
3. SPI0、SD_DET、SD block-device model を接続する
4. 対象アプリが必要とする DMA と PIO の対応状況を検証・補完する
5. core1/SIO FIFO と PSRAM を追加する
6. RP2350 の別 backend を選定する

各段階は「対象 ELF が起動する」だけでなく、対応するシナリオの画面・イベント・ファイル結果が Mode A または実機と一致した時点で完了とする。

## 5. AI 向け CLI とシナリオ

```text
picocalc_emu build --target host --project ./app
picocalc_emu new calculator --board rp2040
picocalc_emu run --target host --scenario tests/smoke.yaml --out artifacts/run-001
picocalc_emu run --target firmware --firmware build/app.uf2 --scenario tests/smoke.yaml
picocalc_emu replay --trace artifacts/run-001/trace.json
picocalc_emu diff --golden tests/golden/home.png --actual artifacts/run-001/frame.png
picocalc_emu doctor --compare-reference
picocalc_emu test --suite tests/ --format junit
picocalc_emu hw-check --scenario tests/smoke.yaml
```

シナリオは YAML/JSON とし、`reset`、`wait`、`key`、`text`、`assert_pixel`、`assert_region_hash`、`assert_file`、`assert_stdout`、`screenshot`、`snapshot` を持つ。失敗時は最終画面だけでなく、入力列、仮想時刻、I²C/SPI 主要トレース、stdout、SD 差分を一つの成果物ディレクトリへ保存する。

## 6. 検証戦略

| 層 | 主な検証 | 実機要否 |
|---|---|---|
| Unit | キー変換、描画領域、状態機械、ファイル処理 | 不要 |
| Host scenario | 起動、画面遷移、入力、SD、LVGL、異常系 | 不要 |
| Protocol | SPI/I²C バイト列、FIFO、リセット、タイムアウト | 原則不要 |
| Golden | 画面・ログ・ファイルの再現性 | 不要 |
| Firmware | ELF/UF2 そのもの、割り込み、メモリ配置 | 原則ホスト、最終のみ実機 |
| HIL | LCD 色、電源、実クロック、キーボード電気的差異 | 必要 |

実機は、各リリースの代表シナリオ、変更したドライバ/リンカ/割り込み、エミュレーターで再現できない電気・性能差だけに限定する。目安は「ホスト全件 → 変更影響分析 → HIL 1〜2件」である。

### 6.1 効果と予測精度の KPI

変更または開発セッションごとに、次の値を JSON/JUnit レポートへ記録する。

* `host_runs`: ホスト実行回数
* `hardware_runs`: 実機実行回数
* `host_duration_sec`, `hardware_duration_sec`: 検証所要時間
* `host_pass_hardware_pass`: ホストと実機の双方で合格
* `host_pass_hardware_fail`: ホストでは合格したが実機で不合格
* `host_fail_hardware_pass`: ホストでは不合格だが実機で合格
* `host_fail_hardware_fail`: ホストと実機の双方で不合格
* `hardware_only_defects`: 実機で初めて発見された不具合と分類
* `unsupported_change`: エミュレーター対象外となった変更理由

主要指標は以下とする。

```text
hardware_reduction = 1 - hardware_runs / baseline_hardware_runs
false_pass_rate =
  host_pass_hardware_fail /
  (host_pass_hardware_pass + host_pass_hardware_fail)
prediction_agreement =
  (host_pass_hardware_pass + host_fail_hardware_fail) / all_correlated_runs
```

初期目標は `hardware_reduction >= 80%`、代表シナリオの `prediction_agreement >= 95%` とする。Phase 0 の代表 3 シナリオは基準データ作成用とし、予測精度の判定には各対応プロファイルについて累積 20 件以上の相関実行を必要とする。`false_pass_rate` は重大度別に管理し、クラッシュ、データ破損、起動不能については 0 件をリリース条件とする。許容値を超えた機能領域は自動的に `hardware_required` とし、モデル修正と相関テスト追加が完了するまで実機確認を省略しない。

基準となる `baseline_hardware_runs` は、エミュレーター導入前または同等規模の過去変更について、書き込み、起動、入力、目視確認を一組として計測する。単に CI ステータス数を数えず、実際の実機操作回数と時間を記録する。

## 7. 段階的な実装計画

### Phase 0: 仕様固定

既存の実働プロジェクトを棚卸しし、再現可能なビルド、Pico SDK 版、ボード、利用機能を manifest 化する。LCD、SD、キーボードについて正常動作する実装と設定を選定し、RP2040/Pico1 と RP2350/Pico2 のプロファイルに分ける。実機から起動時の SPI/I²C トレース、代表画面、キー列、SD 内容を採取する。PDF 回路図と既存ドライバのピン定義を機械可読な `profiles/picocalc-v2.yaml` にする。

基準データの採取方法を次のように固定する。

* SPI/I²C: ロジックアナライザーの生データと、ファームウェア内の論理イベント記録を併用する
* 画面: 可能な場合は LCD RAM 読み出しまたは描画トレースを主基準とし、色・残像・可視領域は外部カメラで補完する
* キー入力: テスト治具または手動操作にシナリオ ID と同期マーカーを付け、I²C トレースと対応づける
* SD: 元イメージのハッシュ、パーティション、FAT 属性、テスト後のブロック差分を保存する
* 識別情報: 基板版、Pico/RP 型式、LCD コントローラー/パネル版、STM32 ファームウェア版を全 artifact に付与する

トレースはバージョン付き JSON schema と raw capture の両方を保存する。正規化イベントは少なくとも `timestamp_us`, `bus`, `direction`, `address_or_cs`, `speed_hz`, `payload`, `result`, `scenario_id`, `profile_id` を持つ。golden の追加・更新は実機 artifact、変更理由、レビュー承認を必要とし、テスト失敗時の自動更新は禁止する。

### Phase 1: MVP（最優先）

実機確認済みの Canonical PicoCalc BSP と新規プロジェクトテンプレートを作る。生成直後のプログラムが実機上で LCD 表示、SD mount/read/write/sync、キーボード入力に成功する状態を固定する。AI の通常変更範囲を `app/` と `assets/` に分離し、BSP/profile/build 基盤の変更検出を追加する。

### Phase 2: 実開発への接続

App API、Pico SDK shim の最小部分、headless framebuffer、キーボード FIFO、Fast/Compatibility mode SD、仮想時計、CLI、シナリオランナーを実装する。既存 CMake プロジェクトに `PICOCALC_EMU=ON` を追加し、共通のアプリコードと platform adapter を分離する。LCD/SD conformance test と変更影響分析を追加し、失敗成果物と KPI を次の修正プロンプトへ渡せる JSON レポートを作る。

### Phase 3: RP2040 Firmware backend

`rp2040js` の採用検証とバージョン固定を行い、ST7365P LCD、I²C keyboard、SD block-device を GPIO/SPI/I²C へ接続する。実際の UF2 を起動し、実働プロジェクトと新規テンプレートの画面、UART、通信トレース、SD 結果を比較する。

### Phase 4: 高い互換性と HIL

GDB 接続、core1/SIO FIFO、PIO/DMA、PSRAM、PicoMite/uLisp/FUZIX の専用ランナー、USB またはシリアル経由の HIL ランナーを追加する。PicoMite は BASIC/SD/UI の外部観測を優先し、完全な VM 再現は依存度と費用を見て判断する。エミュレーターの合格判定は「実機を再現したこと」ではなく、「対象テストについて実機結果を予測できたこと」とする。

## 8. 推奨ディレクトリ

```text
picocalc_emu/
  README.md
  REQUIREMENTS.md
  bsp/                      # 実機確認済み Canonical PicoCalc BSP
  templates/                # 新規プロジェクトの動作保証済み雛形
  reference-projects/       # 実働プロジェクト manifest と artifact
  profiles/                 # 基板・ピン・周辺機器設定
  schemas/                  # profile、scenario、trace、report の JSON schema
  include/picocalc_emu/     # App API、Device Bus、scenario API
  src/kernel/               # event loop, clock, snapshot, trace
  src/shim/pico_sdk/        # host 用 Pico SDK shim
  src/devices/lcd_st7365p/  # GRAM、viewport、ILI9488 互換コマンド
  src/devices/keyboard/     # I2C register/FIFO model
  src/devices/sd/           # Fast/Compatibility filesystem
  src/devices/psram/        # Optional device
  src/backend/headless/     # CI 用
  src/backend/sdl/          # 人間/AI の対話用
  adapters/                 # アプリ/LVGL 用 platform adapter
  scenarios/                # 再生可能なテスト
  golden/                   # 画面・ログ基準値
  fixtures/                 # SD image、emu_smoke、実機基準データ
  tools/                    # CLI、trace/diff、HIL
```

## 9. リスクと対策

* ST7365P と ILI9488 互換実装の差、LCD 初期化コマンド、色順、可視領域が版によって異なる: 320x480 GRAM と 320x320 viewport を分離し、SPI トレース、プロファイル、golden を版別に持つ。
* キーボードは MCU のデバウンス/FIFO がアプリ挙動に影響する: レジスタモデルと物理配列モデルを分離し、代表波形を再生する。
* 10 kHz/400 kHz、待機時間、timeout の差が隠れる: I²C トランザクション属性を検証し、速度違反とエラーを注入する。
* ホストディレクトリでは FAT/SD の不具合を再現できない: 通常は Fast mode、multi-booter とドライバ検証では Compatibility mode を使う。
* host と ARM の未定義動作が異なる: `-fsanitize`、固定幅型、警告最大化、Mode B/HIL の境界テストを使う。
* エミュレーターが現実から乖離する: 定期的な実機採取、トレース差分、予測精度 KPI、変更影響に基づく少数 HIL を必須化する。
* AI が画面画像だけで誤判定する: 画面差分に加え、キーイベント、状態ログ、ファイル差分、終了理由を構造化して返す。

## 10. 最初に実装すべき受け入れテスト

1. `emu_smoke`: リセット後に LCD 初期化、期待文字列表示、キー echo が成功する。
2. `keyboard`: A/Shift/CapsLock/Enter/Esc の押下・解放と FIFO 順序、10 kHz/400 kHz、NACK/timeout が一致する。
3. `lcd`: 320x480 GRAM 上の 320x320 viewport について、1 pixel、矩形、全画面、回転、オフセット、RGB565/18-bit の golden が一致する。
4. `lvgl`: フォーカス移動、Enter、画面遷移、再描画が再現する。
5. `sd-fast`: fixture の読み込み、書き込み、再起動後の保持、sandbox 外アクセス拒否。
6. `sd-compat`: FAT 属性、容量不足、破損、SD_DET、抜去、マウント失敗を再現する。
7. `determinism`: 同一 profile、seed、fixture、シナリオを 100 回実行し、画面、イベント、ファイル差分、終了理由のハッシュが一致する。
8. `hardware-correlation`: 代表 3 シナリオで host と実機の画面/イベント結果を比較し、KPI レポートを生成する。
9. `existing-helloworld`: PSRAM、PWM/IRQ、PIO、UART の実装済み範囲を機能別に検証し、未対応機能を明示して停止する。

この順で作ると、最初の価値は「完全な PicoCalc の再現」ではなく、AI が毎回実機へ行っていた観測可能な反復作業を PC の決定的なテストへ移すこととして得られる。
