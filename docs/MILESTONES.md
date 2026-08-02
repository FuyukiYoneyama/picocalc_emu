# Milestones

Milestone 0 は現在のBSPスターターキットとして完了しています。Milestone 1以降は
PC上のエミュレーターを実装する将来作業であり、現在のRP2040実機ビルド手順と
混同しないでください。

Firmware backendの開発方針は
[`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md)に定義します。主バックエンドは、
`0x4D44/picoem`から独立派生した`FuyukiYoneyama/picoem-picocalc`です。

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

## Milestone 1: Host device models

- native host App API/Pico SDK shim
- headless LCD framebuffer
- keyboard FIFO model
- directory-backed Fast SD mode
- 仮想時刻、固定乱数、stdout capture

完了条件は、専用`emu_smoke`アプリがPC上で起動し、画面・キー・ファイル結果を
決定的に生成できることです。

## Milestone 2: Scenario runner

- JSONシナリオ
- key/text/wait/reset操作
- pixel、region hash、file、stdout assertion
- PNG、trace JSON、JUnit成果物
- 100回連続実行の決定性検査

## Milestone 3: Hardware correlation

- 実機SPI/I2C/UART trace採取
- host traceとのgolden比較
- `host_pass → hardware_fail`記録
- 変更影響に基づく実機必須判定
- 実機検証回数と時間のKPI

## Milestone 4: Firmware backend

Primary backendとして`picoem-picocalc`を使用する。ソースは
`picocalc_emu`へコピーせず別リポジトリで保守し、正確なcommitを固定する。
初期段階では`ExecutionModel::Serial`を正しさの基準とする。
`rp2040js`はRP2040周辺機器の振る舞い、実装方法、テスト構成の比較参考とし、
`picocalc_emu`に接続する主backendとはしない。

- `picoem-picocalc`のversion/commit固定とcapability manifest
- inherited RP2040 Serial test suiteの基準化
- 同一ELF/BIN/UF2のロードとUART boot log取得
- GPIOとPIO0を通した`pio-rgb565` LCD初期化・framebuffer生成
- I2C1 keyboard、SPI0 SD、PIO1 PSRAM、PWM/DMA audioの段階的接続
- 必要範囲のPIO/DMA/multicore、SIO FIFO、WFE/SEV、IRQ対応
- PNG、UART、trace、filesystem、JUnit等のscenario成果物への接続
- backend commitとcapabilityを各実行結果へ記録

最初の合否ゲートは、LCD DMAを使わない標準`pio-rgb565` firmwareが
`[PICOCALC][BOOT]`へ到達し、LCD初期化と320x320 framebufferを決定的に再現できることとする。

Firmware backendはHost device modelの代替ではない。対象アプリが同一バイナリ
確認を必要とし、backendの対応能力が明示されている場合だけ使用する。
公開版`picocalc_emu`の通常ビルドがprivate依存を要求してはならず、正式統合前に
`picoem-picocalc`も公開または同等に再現可能な配布形態にする。

## Milestone 5: BSP lifecycle

- `picocalc bsp status`
- `picocalc bsp diff`
- `picocalc bsp upgrade`
- BSP changelogとmigration rule
- 既存生成プロジェクトへの安全な修正配布
