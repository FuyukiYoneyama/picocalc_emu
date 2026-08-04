# 詳細実装計画（Milestone 1: Firmware backend）

> **文書の位置付け:** 全体計画の正典は`MILESTONES.md`、Gateの受入条件の正典は
> `EMULATOR_ROADMAP.md`である。本書はそれらを変更せず、Milestone 1を実行可能な
> 作業単位へ分解した実行計画を定義する。受入条件の記述が本書と
> `EMULATOR_ROADMAP.md`で食い違う場合は`EMULATOR_ROADMAP.md`を優先する。
>
> 作成日: 2026-08-03。同日、計画レビュー（整合レビューと`picoem-picocalc`
> 実リポジトリの実現可能性調査）の結果を反映して改訂。進捗欄は着手時に更新する。

## 1. 目標の再確認

プロジェクトの目的は「AIがPicoCalc向けプログラムをエミュレーター上で観測・検証・
修正できるようにし、人間の実機検証往復を最小化すること」である。この目的に対して
現在欠けているのは第2段（エミュレーター）であり、その最初の到達目標は、
ClockworkPi公式の無改変`Code/picocalc_helloworld`を`picoem-picocalc`の
`ExecutionModel::Serial`上で完全合格（HELLO-FULL）させ、続いてCanonical BSP Bの
conformance（Gate 7）を通すことである。

本計画の完了条件は`MILESTONES.md`のMilestone 1完了条件と同一である。

## 2. 並行トラック構成

作業は3トラックへ分ける。Track Bが本線であり、Track A/Cは本線を止めない。

| Track | 内容 | 依存 |
|---|---|---|
| A: 0.8.8台帳クローズ | HV-1診断（`diagnostics/bsp-quality`）でLCD readback 100回とguided keyboardを実機確認し、`bsp-0.8.8`台帳のpendingを解消する | 人間の実機セッション1回。Track Bと独立 |
| B: Firmware backend Gate 0〜7 | `picoem-picocalc`と`picocalc_emu`の接続実装。本書§4が詳細 | picoem-picocalcローカルリポジトリ、ClockworkPi公式ソース、Pico SDK |
| C: 文書・CI保守 | Gate合格ごとの状況文書更新、capability manifestのCI検査追加、およびGate 5完了後に`EMULATOR_ROADMAP.md` §2の契約を満たす自作等価fixtureを作成してGate 5/7回帰をCIへ組み込む（公式サンプルはCIへ同梱できないため） | Track Bの各Gate完了 |

Track Aは実機依頼を伴うため、`DEVELOPMENT_WORKFLOW.md` §3に従い一度に
一セッションだけ提示する。Track Bの初期Gate（0〜2）は実機を必要としないため、
実機セッションの待ち時間に本線を進められる。

Track A/B/Cの呼称は本書限定の作業分割名であり、正典の段階番号はMilestone/Gateを
用いる。

## 3. 実装境界（再掲と具体化）

`EMULATOR_ROADMAP.md` §6の境界を、リポジトリ単位の変更範囲として固定する。

| リポジトリ | 担当 | 本計画で変更する場所 |
|---|---|---|
| `picoem-picocalc`（別リポジトリ、`feature/picocalc-integration`ブランチ） | RP2040コア、direct boot、外部SPI/I2C/PIO device hook、Serial correctness | 汎用`rp2040-emu` crateへの外部device interface追加、PicoCalc専用board/device crate新設 |
| `picocalc_emu` | scenario実行、artifact収集・比較、利用者向けCLI | `tools/`へのfirmware runner呼び出し追加、`docs/`、成果物schema |
| ClockworkPi `PicoCalc`公式リポジトリ | conformance対象の供給元 | **変更しない。同梱しない**（`EMULATOR_ROADMAP.md` §2.1） |

禁止事項（全Gate共通）:

- `picocalc_helloworld`のソース・成果物を`picocalc_emu`へコミットしない。
- device modelソースを`picocalc_emu`へコピーしない。固定commitのAPIで接続する。
- 汎用`rp2040-emu` crateへPicoCalc固有のpin・deviceを埋め込まない。
- 未対応MMIOを黙って無視する実装を追加しない。停止または明示記録とする。
- AのRGB666 3-byte転送とBのPIO0/RGB565転送を同じ転送処理へ統合しない。

## 3.1 前提調査の結果（2026-08-03）

`picoem-picocalc`リポジトリ（`feature/picocalc-integration`ブランチ）を実地調査し、
以下を確認した。

- `ExecutionModel::Serial`は`crates/rp2040-emu`に実在し、Serial/Threaded比較の
  回帰テスト（`tests/execution_model.rs`、`tests/dual_model.rs`）を
  `cargo test -p rp2040-emu`で実行できる。
- `load_bootrom`／`load_flash`（XIP `0x1000_0000`へのマップ）／
  `direct_boot_from_flash(vtor_offset)`は実装済み。ただしSSIはstubでQSPI pad
  モデルがないため、direct bootはbootrom実行を経ずSP/PC/VTORを直接シードする
  近道である。この近道を採用し、bootrom実行経路の再現はMilestone 1の対象外と
  する。
- headless runner（非TUIのCLI）は存在しないため、Gate 1で新規binとして実装する。
- Gate 1実装時の追加知見: bootromはロードのみで実行せず、SDKのvector tableから
  SP/PC/VTORを直接シードする方式で`picocalc_helloworld`の`main()`到達まで成立
  する（XIP `0x1000_0000`からの命令フェッチ・リテラル読み出しを含む）。
  SDK型のvector tableを持たないBIN（`roms/rp2040/blinky.bin`等の手書き像）は
  direct bootせずbootromリセットベクタからの起動へフォールバックし、JSONの
  `boot.mode`で両者を区別する。この場合もbootromは実行しない。
- 汎用SPI/I2Cの外部device traitは存在しない（既存deviceは個別structの直接配線、
  `picoem-devices`のLCDは別物のshowcase用で流用不可）。この汎用hook新設が
  本計画で最も新規実装の比重が高い箇所である。
- DMAは12ch実装済み、PIOはテスト付きで実装済み。ただし`tech_debt.md`に
  Threaded実行のquantum境界でGPIOエッジを取りこぼす既知の負債が記録されており、
  Serialを正しさの基準とする方針の根拠でもある。Threaded側の制約をSerial検証へ
  持ち込まない。
- upstreamの開発重心はRP2350寄りであり、`rp2040-emu`への機能追加は本派生
  リポジトリで自走する前提とする。ライセンス（MIT OR Apache-2.0）とNOTICEの
  維持は確認済み。

## 3.2 実行環境と再現手順の固定（2026-08-03決定）

- 作業環境はWSL（Ubuntu-24.04）。ARM toolchainは`arm-none-eabi-gcc` 13.2.1、
  `cmake` 3.28.3、`ninja` 1.11.1（導入済み確認）。Rustはrustup経由のstable
  1.97.1（2026-08-03導入、`cargo test -p rp2040-emu`で1225テスト全合格を
  確認済み）。
- ClockworkPi公式リポジトリはローカルclone`~/pico_dvl/codex/PicoCalc`を
  読み取り専用で参照する。source identityはupstream`origin/master` =
  commit`553da6f2408963b956779599d179d77fd611a4d7`とする。ローカルには
  これより先の私的コミット1件（`schematic_sheets/`のJPG追加のみ、
  `Code/`無変更と検証済み）と未追跡ファイル`Code/PicoMite/main.c`があるが、
  リセット・cleanはしない。Gate 0受入時に
  `git diff 553da6f2 master -- Code/picocalc_helloworld`が空であることを
  確認する。
- `Code/picocalc_helloworld/rp2040-psram`はネストした取得物
  （`polpo/rp2040-psram`、commit`7786c93`）であり、識別情報へ別項目として
  記録する。
- Pico SDKは`~/pico_dvl/codex/pico-sdk`のtag 2.2.0を使用する
  （実機台帳のビルドと同版）。`picocalc_emu`のCIが使う2.0.0はBSPの
  最低互換検査用であり、Gate 0のsource identityとは別問題である。
- 再現ビルド手順: build dirは公式clone外の
  `~/pico_dvl/codex/build/picocalc_helloworld/`とし、`PICO_SDK_PATH`を
  明示、generatorはNinja、CMakeオプションは`-DCMAKE_BUILD_TYPE=Release`
  とする。加えて、configure時に環境変数`CFLAGS`/`CXXFLAGS`へ
  `-DPICO_NO_BI_PROGRAM_BUILD_DATE=1`を設定する。この定義はPico SDKの
  Cプリプロセッサマクロ（ガードは`#if !PICO_NO_BI_PROGRAM_BUILD_DATE`）で
  あり、`__DATE__`をバイナリへ埋め込むことを止めるための必須設定だが、
  CMakeコマンドライン変数（`-D`）としては効かず警告のみで無視される。
  `-DCMAKE_C_FLAGS=...`によるコンパイラフラグの直接上書きは、SDK
  ツールチェーンが設定するアーキテクチャフラグを消してビルド失敗を
  招くため使用禁止。環境変数`CFLAGS`/`CXXFLAGS`経由はCMakeが
  ツールチェーンの初期化フラグへ安全に連結するため、この方式を正式手順
  とする。これがないと受入条件「同一SHA-256の再現」を満たせない
  （同日ビルドでの偶然のhash一致は日付マクロ無効の証明にならないことに
  注意。日をまたぐと再現性が壊れる）。この設定はビルドオプションの
  固定でありソース無改変の原則に反しない。
- 継承済みSerial回帰の範囲は`cargo test -p rp2040-emu`と定義する。
  2026-08-03時点のbaselineは1225テスト全合格（backend commit`a4e23ca`）。

## 3.3 成果物の保存規約

- Gate受入の証拠（JSONレポート、UARTログ、framebuffer PNG、hash一覧、
  テスト合格ログ）は`picocalc_emu`の新設ディレクトリ
  `firmware-validation/records/gate<N>-YYYYMMDD-NN/`へ保存してコミットする。
  実機台帳`hardware-validation/`と対をなすエミュレーター側台帳である。
- 作業中の一時出力は`.gitignore`済みの`artifacts/`を使い、コミットしない。
- 証拠ファイルには実時刻・絶対パスを含めない（ファイル名の日付は除く）。
  両リポジトリのcommit hash（`picocalc_emu`と`picoem-picocalc`）を証拠JSONへ
  記録し、相互参照とする。
- この規約に伴い、各Gateの「変更可能な場所」に`firmware-validation/records/`
  を追加する（各Gate分担と境界の記述へ「および`firmware-validation/records/`
  への証拠追加」を変更可能な場所へ追記する）。

## 4. Gate別作業計画

各Gateは「合格後に独立したcommitとして残す」（`EMULATOR_ROADMAP.md` §7）。
以下の受入条件はチェック用の要約であり、正式な条件は`EMULATOR_ROADMAP.md` §3〜4。

### 進捗

| Gate | 状態 | record |
|---|---|---|
| Gate 0: 基準の固定 | 完了 2026-08-03 | `firmware-validation/records/gate0-20260803-01/` |
| Gate 1: headless firmware runner | 完了 2026-08-03 | `firmware-validation/records/gate1-20260803-01/` |
| Gate 2: SPI1 LCD vertical slice | 完了 2026-08-03（HELLO-VISIBLE達成） | `firmware-validation/records/gate2-20260803-01/` |
| Gate 3: PIO1/DMA PSRAM | 完了 2026-08-04（全域試験完走） | `firmware-validation/records/gate3-20260804-01/` |
| Gate 4: I2C keyboard controller | 完了 2026-08-04（キーecho確認） | `firmware-validation/records/gate4-20260804-01/` |
| Gate 5: full application acceptance | 完了 2026-08-04（**HELLO-FULL達成**） | `firmware-validation/records/gate5-20260804-01/` |
| Gate 6: `picocalc_emu` integration | 完了 2026-08-04（公開は時期未定・別管理） | `firmware-validation/records/gate6-20260804-01/` |
| Gate 7: Canonical BSP B conformance | 未着手 | — |

### Gate 0: 基準の固定（実機不要）

作業:

1. §3.2で固定したupstream commit`553da6f2…`をsource identityとし、
   リポジトリ全体のcommit hashを記録する。
2. Pico SDK版、arm-none-eabi-gcc版、CMake optionを固定し、`picocalc_helloworld`の
   無改変ELF/BINをビルドしてSHA-256、map、最低限`main`と、UART初期化・PSRAM試験・
   キー入力ループに対応するsymbolをmapから列挙して記録する。symbolの列挙に加え、
   submodule相当の`rp2040-psram`のcommitも記録する。ビルドは§3.2の再現手順に従う。
3. `picoem-picocalc`の対象commitを固定し、継承済みSerial test suiteを全実行して
   合格状態を基準化する。
4. 上記の識別情報一式を`picocalc_emu`側の機械可読ファイル
   （例: `reference-projects/firmware-targets.json`。既存`catalog.json`
   （参照プロジェクト台帳）とは別系統のfirmware conformance対象識別台帳である）
   へ記録する。ELF/BIN自体は記録しない。schema例:

```json
{
  "schema_version": 1,
  "targets": [
    {
      "id": "picocalc-helloworld-a",
      "source": {
        "repo_url": "https://github.com/clockworkpi/PicoCalc.git",
        "commit": "553da6f2408963b956779599d179d77fd611a4d7",
        "nested": [{"path": "Code/picocalc_helloworld/rp2040-psram", "commit": "7786c93"}]
      },
      "sdk": {"version": "2.2.0"},
      "toolchain": {"arm_none_eabi_gcc": "13.2.1"},
      "cmake": {"generator": "Ninja", "options": ["-DCMAKE_BUILD_TYPE=Release", "-DPICO_NO_BI_PROGRAM_BUILD_DATE=1"]},
      "artifacts": {"elf_sha256": "<記録>", "bin_sha256": "<記録>"},
      "backend": {"repo": "picoem-picocalc", "branch": "feature/picocalc-integration", "commit": "<記録>", "test_command": "cargo test -p rp2040-emu", "baseline": "1225 passed"}
    }
  ]
}
```

5. `picoem-picocalc`のXIP、PIO、DMA、PWM、外部device hookの実装状況を棚卸しし、
   Gate 1〜4の作業見積りへ反映する（§3.1の初回調査を出発点とする）。

受入条件: 識別情報ファイルが存在し、記載手順で同一SHA-256のELF/BINを再現できる。
Serial test suiteの合格ログとcommitが記録されている。

分担と境界: Lunaへ渡す単位は(1)§3.2手順による再現ビルドと識別情報採取・
`firmware-targets.json`作成、(2)Serial test suite実行とログ採取、
(3)実装状況棚卸し調査。変更可能な場所は`picocalc_emu`の`reference-projects/`
および`firmware-validation/records/`。Gate固有の禁止は公式サンプルの
ソース・成果物をリポジトリへ持ち込むこと。

### Gate 1: headless firmware runner（実機不要）

作業:

1. `picoem-picocalc`へheadless runnerを追加する。runnerは`picoem-picocalc`の
   新規crate`crates/picocalc-harness`のbin`picocalc-run`とする
   （`EMULATOR_ROADMAP.md` §6の「crate名は最初の実装タスクで確定する」に
   基づく確定。既存`picoem-harness`の`picogus_diff_rp2040`の
   `--flash`/`--bootrom`慣行を実装参考にする）。bootrom＋BINをロードし、
   Pico SDK imageをFlash offset `0x100`からdirect bootする。
   bootromの扱い: bootrom像は`roms/rp2040/bootrom-rp2040-b2.bin`
   （provenance記録済み）を既定とし、SDKが参照するROM table・bootrom関数の
   解決のためにメモリへロードするが、bootromからの実行はしない。実行開始は
   §3.1の近道（SP/PC/VTOR直接シード、offset`0x100`）で行う。
2. cycle上限、UART capture、PC、例外、未対応MMIOアクセス（アドレスとアクセス元PC）、
   終了理由を構造化出力（JSON）で取得する。CLI契約: `--bin <path>`（必須）、
   `--bootrom <path>`（既定`roms/rp2040/bootrom-rp2040-b2.bin`）、
   `--cycles <N>`（既定`1_000_000_000`。超過時は`stop_reason=cycle_limit`で
   正常終了扱いの停止）、`--stop-pc <hex>`（任意。実行PCが一致したら
   `stop_reason=pc_match`で停止する。`main()`到達判定用。2026-08-03の
   Gate 1受入で追加）、`--json <出力先>`、`--uart <出力先>`。
   JSONレポートの必須フィールド: `schema_version`、`backend_commit`、
   `firmware`（basename、sha256）、`stop_reason`、`cycles`、`pc`、
   `exception`（あれば）、`unsupported_mmio[]`（addr、アクセス元pc、count）、
   `uart`（bytes数、sha256）。実時刻・絶対パスを含めない（作業6と整合）。
3. 既知の小さいPico SDK firmware（自作のUART hello等）でrunnerを先に検証する。
   小規模firmwareは既存の`roms/rp2040/`にある`blinky.bin`と生成スクリプト
   （`gen_*.py`）を利用してよい。
4. `picocalc_helloworld`が`main()`とUART初期化へ到達することを確認する。
5. direct bootは§3.1の近道（SP/PC/VTOR直接シード）を用い、XIP領域
   `0x1000_0000`への命令フェッチ・リテラル読み出しが対象ファームウェアで
   成立することを確認する。
6. JSONレポート・ログ等のartifactから実時刻、絶対パス、ビルド環境依存値を
   排除し、決定性比較の対象フィールドを定義する。

受入条件: 対話TUIなしで、コマンド1回からJSONレポートとUARTログが、
同一入力での3回実行が同一出力になる形で得られる。
`picocalc_helloworld`の`main()`到達がPC/symbolで確認できる。

注意: bootromが未実装SSI/QSPI経路からUF2待ちへ進んだ状態を「実行できた」と
混同しない（`EMULATOR_ROADMAP.md` Gate 1）。

分担と境界: Lunaへ渡す単位は(1)runner骨組み（bin新設・bootromロード・direct
boot・終了理由）、(2)観測系（UART capture・未対応MMIO記録・JSON出力）、
(3)小規模firmwareでのrunner検証、(4)`picocalc_helloworld`の`main()`到達確認。
変更可能な場所は`picoem-picocalc`の新規bin/crateと、`rp2040-emu`への公開API
追加、および`firmware-validation/records/`。Gate固有の禁止は`rp2040-emu`
コアの実行semanticsを変更すること。

### Gate 2: SPI1 LCD vertical slice → HELLO-VISIBLE（実機不要）

作業:

1. 着手前にSolがSPI外部device transaction interfaceのAPI仕様（transfer粒度、
   CS/DC/RESETの観測経路、既存`spi.rs`の`read32/write32/tick`モデルとの
   接続点）を設計して確定する。この設計はLunaへ委任しない。本Milestoneで
   hookを通すのはSerial実行のみとし、Threaded側への対応は行わない。
   確定後、RP2040側SPIへ外部device transaction interfaceを追加する
   （汎用crate側はPicoCalcを知らない汎用hookとする）。
2. PicoCalc board adapterでSPI1とGP13/14/15のCS/DC/RESETをLCD modelへ接続する。
3. ST7365P modelを実装する。内部GRAM 320×480、可視viewport 320×320。
   command subsetは最低limitでreset、sleep/display state、MADCTL、COLMOD、CASET、
   RASET、RAMWR。
4. 3-byte RGB666 wire dataをdecodeし、共通RGB565 framebufferへ正規化する。
5. framebufferのPNG/hash出力を追加し、同一入力での3回実行の一致を検査する
   （Gate 1・Gate 5と同じ基準）。HELLO-VISIBLEの初回判定規則: 初回のgolden
   framebufferは存在しないため、最初の`Hello World PicoCalc`表示はSolが
   PNGを目視して確定し、そのhashを以後のgoldenとする。PNG/hashの決定性
   規約: 正準hashはRGB565 framebufferの生バイト列（320×320×2 byte、行優先、
   little-endian）のSHA-256とする。PNGは人間の確認用の派生物であり、
   encoder crateと版はCargo.lockで固定し、時刻メタデータchunkを含めない。

受入条件: HELLO-VISIBLEの7条件（`EMULATOR_ROADMAP.md` §3）。
`Hello World PicoCalc`のframebufferがPNG/hashで決定的に取得できる。

リスク: LCD初期化列の解釈差。公式ファームウェアはILI9488名でST7365Pを駆動する。
判定に迷う場合の一次資料の優先順位は、最優先はClockworkPi公式
`picocalc_helloworld/lcdspi`のソース、次に実機合格記録（COLMOD `0x66`等）、
`bsp/vendor/README.md`のA系統は補助資料とする。公式リポジトリのルートに
`ST7365P_SPEC_V1.0.pdf`（コントローラーのデータシート）が同梱されており、
公式`lcdspi`ソースと併せて一次資料とする。PIO/SPI駆動転送のエッジ精度は
Serialで確立し、Threadedのquantum境界負債（§3.1）を検証経路へ持ち込まない。
Gate 1で確認した先行ブロッカーとして、全コアがWFE/haltedのときSerial実行
ループが0サイクルで抜け、消費サイクル数に比例するペリフェラルtickと
TIMERアラームがいずれも進まなくなる凍結がある（`picocalc_helloworld`は
約1.53Mサイクル、`lcd_init`の遅延処理内で停止する。詳細は
`firmware-validation/records/gate1-20260803-01/notes.md`）。LCD描画も
キー入力ループもSDKのsleepの先にあるため、Gate 2着手時に「全コアアイドル時に
次の予定イベントまで仮想時間を進める」機構を、Solのhook API仕様確定と併せて
先に解決する。コア実行semanticsへ触れる変更であるためSolが設計し、既存の
1225回帰の維持を受入条件とする。

分担と境界: Lunaへ渡す単位は(1)SPI hook実装と既存回帰の全合格（Sol設計
確定後）、(2)PicoCalc board/device crateの骨組みとpin配線、(3)ST7365P
command decoderとLCD state、(4)GRAM書き込み・address window・RGB666→RGB565
decode、(5)PNG/hash出力。変更可能な場所は`rp2040-emu`のhook追加と新設
PicoCalc専用crate、および`firmware-validation/records/`。Gate固有の禁止は
汎用crateへPicoCalc固有のpin・定数を埋め込むこと。

2026-08-03受入完了。golden hashと詳細は`firmware-validation/records/gate2-20260803-01/`。

### Gate 3: PIO1/DMA PSRAM（実機不要）

作業:

1. PIOコアの対応範囲を確認し、公式サンプルのPSRAM PIO programをそのまま実行する。
2. GP20/21/2/3のPIO1出力を8 MiB PSRAM modelへ接続し、DMA transactionを通す。
3. 8/16/32/128-bit全域試験を完走させ、host実行時間を計測する。
4. 遅すぎる場合も試験範囲を削らず、transaction等価と検証できるbackend側最適化
   だけを追加する。

受入条件: 全域試験完走、不一致0、UART/LCD上の完了結果取得。

リスク（本計画最大）: 8 MiB全域×4幅の試験はSerial実行で長時間になり得る。
対策順序は (1)まず正確さを確立して所要時間を実測 → (2)PIO/DMAのbatch実行等の
等価最適化 → (3)それでも非現実的な場合の限定的な緩和、の順とする。
非現実的とは、HELLO-FULL相当のscenario 1回のhost実行が60分以内に完走できない
状態を指す。その場合もHELLO-FULL本体のscenarioは
`EMULATOR_ROADMAP.md`が定める3回連続の決定的合格を維持し、調整してよいのは
補助的なscenarioの反復回数だけとする。ファームウェア側の試験範囲は削らない。

実測結果（2026-08-04）: 全域試験の完走に要したのは約8.7×10⁹サイクル・host実行約5.6分で、
60分基準に対し約10倍の余裕があった。緩和策(3)は発動していない。本Gateの実際のブロッカーは
実行時間ではなく、sub-quantum edge lossとPSRAM読み出しタイミングという2つの正確さの欠陥
だった。詳細は`firmware-validation/records/gate3-20260804-01/`。2026-08-04受入完了。

分担と境界: Lunaへ渡す単位は(1)PSRAM modelのPIO1/DMA接続、(2a)縮小領域での
PSRAM経路確立、(2b)全域試験の実測、(2c)transaction等価なbackend最適化
（必要時のみ）。変更可能な場所はPSRAM model、PIO/DMA接続部、最適化対象の
backend内部、および`firmware-validation/records/`。Gate固有の禁止は
ファームウェア側の試験範囲を削ること。

### Gate 4: I2C keyboard controller（実機不要）

作業:

1. 外部I2C device interfaceを追加する（固定ACK・固定`0xff`応答の即席実装を禁止）。
2. address `0x1f`のSTM32 controller modelを実装する。register `0x04`、
   FIFO（register `0x09`）、battery、backlight registerとrepeated-start
   transactionを含む。速度は公式サンプルの10 kHz設定と
   BSPの400 kHz設定の両方を受ける。
3. シナリオ入力からFIFOへキーを投入し、ファームウェアのLCD echoまで検証する。

受入条件: scripted keyがFIFO経由でLCDへechoされ、framebuffer/hashで確認できる。

分担と境界: Lunaへ渡す単位は(1)外部I2C device interfaceの追加、(2)address
`0x1f`のSTM32 controller modelの実装とキー注入・echo検証。変更可能な場所は
I2C hookと新設controller model、および`firmware-validation/records/`。
Gate固有の禁止は固定ACK・固定`0xff`応答などの即席実装。

### Gate 5: full application acceptance → HELLO-FULL（実機不要）

作業:

1. HELLO-FULLの8条件（`EMULATOR_ROADMAP.md` §3）を一つのscenarioで実行する
   runnerスクリプトを作る。本Gateでいうscenarioはrunnerへの入力ファイル
   （形式は本Gateで定義する）であり、Milestone 3のJSONシナリオschemaを
   先取り実装しない。Milestone 3で置き換える。
2. UART、PNG、trace、PSRAM結果、keyboard結果、capability、backend/source commit、
   成果物SHA-256を構造化artifactへ保存する。
3. 3回以上連続実行して同一結果（決定性）を確認する。

受入条件: 3回連続の決定的合格。この時点で初めて
「公式`picocalc_helloworld`がエミュレーター上で動く」と宣言できる。

分担と境界: Lunaへ渡す単位は(1)HELLO-FULL統合scenarioの作成、
(2)構造化artifact保存と3回連続の決定性確認。変更可能な場所はscenario・
artifact関連、および`firmware-validation/records/`。Gate固有の禁止は
ファームウェアへテスト専用の変更を加えること。

### Gate 6: `picocalc_emu` integration（実機不要）

作業:

1. `picoem-picocalc`の検証済みcommitを固定し、`picocalc_emu`から
   ソースコピーなしで接続する（例: `tools/picocalc.py test --mode firmware`が
   固定commitのrunnerバイナリを呼び出す。`REQUIREMENTS.md` §5の標準コマンド
   体系に合わせる）。
2. runnerの構造化artifactを`picocalc_emu`のscenario/artifact interfaceへ接続する。
3. capability manifest（対応済み: SPI1/PIO1/DMA/I2C1/UART0等、未対応: SPI0 SD、
   multicore等）を機械可読で公開し、portable検証の検査対象へ加える。
   スナップショットを`picocalc_emu`内に機械可読ファイルとして保持し、
   backend不在のclone単体でも`verify`のportable検査が完結する構成にする。
4. 公開**準備**を整える。`picocalc_emu`と`picoem-picocalc`はどちらも現在private
   であり、この状態では`FIRMWARE_BACKEND.md`の公開条件と矛盾しない。同条件は
   「`picocalc_emu`を公開する時点」で満たすべきものであって、本Gateの完了条件
   ではない。本Gateでは次を用意するにとどめる。
   - backend不在でもportable検証が完結する構成（作業3で達成）
   - 公開前チェックリストの文書化と、機械検査できる項目の自動化
     （`docs/RELEASE_CHECKLIST.md`）

**公開の実施時期は未定である。** 方針としては公開予定であり、ライセンス面
（`MIT OR Apache-2.0`とNOTICE維持）の確認は済んでいる。ただし十分な完成度に
達するまで公開しない。この判断は人間が行い、Gate進行の前提条件にはしない。

受入条件: clone＋固定commit取得だけでGate 5と同じ合格を`picocalc_emu`側の
コマンドから再現できること、およびbackend不在のcloneで`verify`が完結すること。
公開そのものは受入条件に含めない。

分担と境界: Lunaへ渡す単位は(1)`picocalc_emu`側CLI接続、(2)capability
スナップショットと`verify`検査の追加。公開の実施とリリース検査の最終判定は
Solと人間の判断事項であり、Lunaへ委任しない（検査スクリプト等の準備作業は
Lunaに渡せる）。変更可能な場所は`picocalc_emu`の`tools/`・`docs/`・検査データ、
および`firmware-validation/records/`。Gate固有の禁止はdevice modelソースを
`picocalc_emu`へコピーすること。

### Gate 7: Canonical BSP B conformance（実機不要、相関はMilestone 4）

作業:

1. PIO0 blocking転送用のbus adapterをAとは別に実装する（転送電文を統合しない）。
2. `tools/picocalc.py new`で生成した標準template（B: PIO0/RGB565/LCD DMA OFF）の
   UF2/ELFを実行する。
3. 起動時スモークのLCD GRAM readback（RAMRD、SIO切替手順）をmodel側で対応し、
   `[PICOCALC][LCD][VERIFY] app_status=pass`到達を確認する。
4. SD/SPI0は本Gateでは未対応でよいが、未対応を黙殺せずcapabilityと停止理由で
   明示する。標準templateはSD失敗でもステータス領域を赤にして継続する設計の
   ため、runtime停止ではなくcapabilityに`sd: unsupported`を明示し、SDスモークの
   失敗を記録として扱う。
5. 標準templateが起動時に要求する機能— 250 MHzへのPLL再設定、既定ONの音声
   参照トーン（PWM＋DMA timer＋IRQ）、400 kHz I2C、62.5 MHz PSRAM — の対応可否を
   Gate 6までのcapability棚卸しで判定する。未対応が残る場合は、templateやBSPを
   変更せず、`PICOCALC_AUDIO_REFERENCE_TONE=OFF`等のビルド設定でGate 7の
   対象構成を明示的に限定し、その構成をcapabilityへ記録する。

受入条件: 標準templateのBOOT行・LCD VERIFY pass・RAMRD readbackが
エミュレーター上で観測でき、`MILESTONES.md`のMilestone 1完了条件を満たす。

分担と境界: Lunaへ渡す単位は(1)PIO0用bus adapterの新設、(2)RAMRD/SIO切替
手順のmodel対応、(3)capability可否判定（250 MHz PLL・参照トーン・
400 kHz I2C・62.5 MHz PSRAM。Gate 6までに実施しSolが判定）、(4)標準
template UF2の実行と判定。変更可能な場所はB用bus adapterとmodel拡張、
および`firmware-validation/records/`。Gate固有の禁止はAとBの転送処理の
統合、およびtemplate・BSP側の変更。

## 5. Track A: 0.8.8実機台帳クローズ

Gate作業と独立に、次の1セッションを人間へ依頼する。

1. `diagnostics/bsp-quality`のHV-1診断UF2を、版番号またはビルドサブコメントを
   ソースへ反映してコミットした対象コミットから、
   `--lcd-variant pio-rgb565 --build-timestamp YYYY-MM-DDTHH:MM:SSZ`を付けた
   証拠ビルドで生成する。UF2は保存せずSHA-256のみ記録する。
2. 実機でLCD GRAM write/readback 100回とUp/Down/Enter/Escapeのguided入力を実行し、
   `[BSP_DIAG_VERDICT]`を含むUARTログと画面写真を回収する。
3. 結果を`hardware-validation/records/`の0.8.8台帳へ、新規record
   （例: `bsp-0.8.8-<日付>-02.json`）を追加して記録し、LCD/keyboardの
   pendingを解消する。0.8.3で観測された間欠readback失敗が再現した場合は、
   合格扱いにせず発生率を記録して原因調査タスクを起票する。

このセッションはGate 2以降のLCD model実装の一次資料（実機のRAMRD挙動）としても
価値がある。Gate 2の受入判定までにTrack Aの結果が揃わない場合、Gate 2は
暫定合格とし、Track A完了後に実機RAMRD挙動と突き合わせて再確認する。
Gate 0〜2の着手はTrack Aを待たない。

## 6. 検証と記録の規律

- 各Gateの合否はSolが独立検証してから確定する（`DEVELOPMENT_WORKFLOW.md` §2）。
- Gate合格ごとに`docs/IMPLEMENTATION_STATUS.md`の該当節とcapability記録を更新する。
- `python3 tools/picocalc.py verify`はGate 6以降、firmware-targets識別情報と
  capability manifestの整合検査を含める。
- 到達度は変更単位に`host_pass`/`host_fail`/`hardware_pass`/`hardware_fail`/
  `hardware_required`で記録する（`README.md`末尾の測定方針）。
- エミュレーター合格・実機不合格が発生した機能は`hardware_required`へ戻す。
- 各Gateの着手時に、Solが`EMULATOR_ROADMAP.md` §7に従い対象、受入条件、
  変更可能範囲、禁止事項、検証方法を先に定義し、Lunaタスクを一件ずつ発行する。
- 汎用`rp2040-emu` crateへ変更を加えたGate（Gate 2以降）の受入には、継承済み
  Serial test suiteの全合格（回帰ゼロ）を含める。Gate 7の受入では、その最終
  合格ログとcommitを構造化artifactへ固定する（`MILESTONES.md`のMilestone 1
  完了条件）。
- `picoem-picocalc`側の作業は`feature/picocalc-integration`ブランチへ積み、
  Gate合格時に受入コミットを確定する。`picocalc_emu`側はGateごとに
  `firmware-targets.json`と証拠recordでbackend commitを参照する。commit・
  pushはSolが行う（`DEVELOPMENT_WORKFLOW.md` §1）。

## 7. 順序と依存関係

```text
Track A: [HV-1実機セッション]（人間1回、任意時点）
Track B: Gate 0 → Gate 1 → Gate 2(HELLO-VISIBLE) → Gate 3 → Gate 4
         → Gate 5(HELLO-FULL) → Gate 6 → Gate 7
Track C: 各Gate完了ごとに文書・CI更新
```

Gate 2完了（HELLO-VISIBLE）が最初の対外的な可視成果である。Gate 3のPSRAM性能が
本線最大のリスクであり、Gate 2完了時点で全域試験の所要時間見積りを先行取得する。
Gate 1のXIP/bootrom近道の成立確認と、Gate 2で新設する汎用device hookが
先行リスクであり、Gate 0の棚卸しで見積りを確定する。Gate 0開始時点の
環境ブロッカー（Rust toolchain不在）は2026-08-03に解消済みである（§3.2）。

## 8. Milestone 2以降への接続

Milestone 1完了後の順序は`MILESTONES.md`に従う（Host device models →
Scenario runner → Hardware correlation → BSP lifecycle）。本書はMilestone 1の
完了をもって役目を終え、後続Milestoneの詳細計画は着手時に別途起こす。
