# Milestones

## Milestone 0: Canonical BSP — implemented

- 実働プロジェクトを根拠にしたLCD・keyboard・SD/FatFS BSP
- アプリ変更を`app/`に限定するRP2040テンプレート
- portable source fingerprint check
- reference commit/SHA-256 evidence check
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

- RP2040JSのversion/commit固定とcapability manifest
- 同一ELF/UF2のUART・GPIO・SPI・I2C接続
- 必要範囲のPIO/DMA/multicore対応

Firmware backendはHost device modelの代替ではない。対象アプリが同一バイナリ
確認を必要とし、backendの対応能力が明示されている場合だけ使用する。

## Milestone 5: BSP lifecycle

- `picocalc bsp status`
- `picocalc bsp diff`
- `picocalc bsp upgrade`
- BSP changelogとmigration rule
- 既存生成プロジェクトへの安全な修正配布
