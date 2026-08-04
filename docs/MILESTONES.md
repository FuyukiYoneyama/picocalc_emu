# Milestones

**この文書が全体計画の正典です。** 全体の実装順序とMilestone単位の完了条件を
定義します。Firmware Gateの詳細受入条件は`EMULATOR_ROADMAP.md`が定義し、
他文書に出てくる段階表現は本書のMilestone番号へ対応付けます。

Milestone 0 は完了しています。Milestone 1以降は
PC上のエミュレーターを実装する将来作業であり、現在のRP2040実機ビルド手順と
混同しないでください。

ここでいうMilestone 0完了は、Canonical BSPのソース、portable検証、テンプレート、
証拠台帳の基盤が整ったという意味である。最新BSP 0.8.8自身の実機台帳はLCDとkeyboardが
pendingであり、0.8.8の全機能実機合格を意味しない。

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

## Milestone 0: Canonical BSP — implemented

- 実働プロジェクトを根拠にしたLCD・keyboard・SD/FatFS BSP
- アプリ変更を`app/`に限定するRP2040テンプレート
- portable source fingerprint check
- host SPI fakeによるLCD初期化・CS分割transaction test
- JSON profileからのboard header一方向生成
- reference commit/SHA-256 evidence check
- Canonical BSP実機検証schema・pending template
- LCD pattern、SD read/write、keyboardログの実機スモーク
- PythonテストとRP2040 compile CI

完了条件は、clone単体のportable検証とテンプレートcompileがCIで成功し、
初回のBSP実機スモーク結果を記録できることです。

## Milestone 1: Firmware backend — `picocalc_helloworld` first

**進行中（2026-08-04時点でGate 0〜5完了、HELLO-FULL達成）。** 無改変の公式
`picocalc_helloworld`が`ExecutionModel::Serial`上でHELLO-FULLの8条件を満たした。
残るはGate 6（`picocalc_emu`統合の仕上げと公開条件）とGate 7（Canonical BSP B
conformance）であり、この2つを満たした時点でMilestone 1完了となる。
Gate別の進捗表と証拠は[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §4と
`firmware-validation/records/`にある。

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

- native host App API/Pico SDK shim
- headless LCD framebuffer
- keyboard FIFO model
- directory-backed Fast SD mode
- 仮想時刻、固定乱数、stdout capture

完了条件は、専用`emu_smoke`アプリがPC上で起動し、画面・キー・ファイル結果を
決定的に生成できることです。

## Milestone 3: Scenario runner

- JSONシナリオ
- key/text/wait/reset操作
- pixel、region hash、file、stdout assertion
- PNG、trace JSON、JUnit成果物
- 100回連続実行の決定性検査

## Milestone 4: Hardware correlation

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
- SPI0 SD、PWM/DMA audio playback、multicore、SIO FIFO、WFE/SEV、IRQの拡張
- PicoMite、uLisp、FUZIX等の対象workload別runner
