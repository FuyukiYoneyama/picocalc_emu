# Firmware backend

`picocalc_emu`のRP2040 firmware backendは、独立リポジトリ
[`FuyukiYoneyama/picoem-picocalc`](https://github.com/FuyukiYoneyama/picoem-picocalc)です。
`0x4D44/picoem`の履歴と`MIT OR Apache-2.0`を維持した派生であり、sourceを本リポジトリへ
コピーしません。

## 役割

Firmware backendは、Pico SDKが生成したraw BINをdirect bootし、同じbuildから作るUF2と
実行payloadを共有します。RP2040とPicoCalc device modelを通してUART、framebuffer、PSRAM、
SD、keyboard、exception、unsupported MMIO、structured reportを観測します。

- Host backend: アプリロジック、UI、file処理を高速にネイティブ実行
- Firmware backend: PIO、DMA、GPIO、interrupt、multicoreなどbinary／hardware固有挙動を検証

正確性基準は`ExecutionModel::Serial`です。Threaded modelを一般的な正確性基準にはしません。

## Backend identity

branch名や最新commitは受入レベルではありません。targetごとに正確なcommitを固定します。

| 役割 | commit | 意味 |
|---|---|---|
| hardware-correlated | `612b485...f66` | R5同一artifact実機相関に使った不変証拠 |
| promoted | `e985a9d...5f1` | 通常PicoTetris回帰に使うOPT1-B accepted backend |
| bounded audio acceptance | `d92db1b...1a3` | NEXT-2Bの凍結audio targetで受入済み |
| local development main | `ae49c6c` | U1 RAW SD、U2 flash erase/program、M-NESCO-S1 direct-boot debug経路を含む。general promotedとは別 |

新しいmainが既存targetを自動的に置き換えることはありません。backend更新時は新しいtarget revision、
validation、recordを作り、旧実機証拠を書き換えません。

機械可読な役割は[`capability.json`](../firmware-validation/capability.json)、target pinは
[`firmware-targets.json`](../reference-projects/firmware-targets.json)を参照してください。

## Runner verdict

runner report schema 8の`verdict`が合否の正典です。

- `0`: pass
- `1`: judged failure
- `2`: cannot judge

cycle exhaustionを暗黙の成功にしません。exception、emulator error、unsupported/truncated MMIO、
keyboard loss、scenario failure、stop mismatch、marker不足、backend identity不一致はfail-closedです。
CLIは毎回新しいreportを生成し、過去runのstale reportを受け入れません。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target <target-id> \
  --firmware /absolute/path/to/app.bin \
  --backend-dir ../picoem-picocalc
```

## 実装済みの主要範囲

- Pico SDK BIN direct boot、XIP、bootrom lookup用image
- UART0 capture、PC、exception、unsupported MMIO
- SPI1/RGB666 LCD AとPIO0/RGB565 LCD B
- PIO、DMA、8 MiB PSRAM、SPI0 SD
- 公式STM32 firmwareを一次参照とするkeyboard controller
- scenario runner、snapshot、schema 8 verdict
- exact idle fast-forward、OPT1-B predicate fast path
- NEXT-2Aの凍結Serial multicore契約
- NEXT-2Bの凍結DMA-paced audio sink契約
- PWM5_CCの音量解析と非正規化raw WAV（schema 8 reportとは独立）
- digital音量advisoryと、人間による内蔵speakerの2問式通過記録
- NEXT-3のmandatory SD CRC rejection
- NEXT-4のJSONL machine API
- file-backed RAW SD (`--sd-image`) とcopy-on-write/atomic export (`--sd-image-out`)
- SPI-NOR erase/program、XIP mutation、flash report/export (`--flash-image-out`)
- M-NESCO-S1: `Picocalc_NESco` direct bootでのSD ROM選択・flash staging診断

完全な対応・制限は`capability.json`を優先します。

## RAW SD／flash診断（M-NESCO-S1）

通常の登録target回帰は従来どおり`picocalc.py test --mode firmware`を使います。RAW SDと
flash mutationを診断する場合だけ、cleanな`picoem-picocalc` checkoutのrunnerへ明示的に
入力を渡します。

```sh
picocalc-run \
  --bin /absolute/path/Picocalc_NESco.bin \
  --sd-image /absolute/path/sd.img \
  --sd-image-out /absolute/path/sd-out.img \
  --flash-image-out /absolute/path/flash-after.bin \
  --scenario /absolute/path/m-nesco-scenario.json \
  --cycles 1400000000 \
  --json /absolute/path/report.json
```

`--bin`は初期XIP flash image（現在はraw BIN）であり、`--flash-image-out`はrun後の2 MiB
imageをatomicに出力します。`--sd-image`は入力RAWをrun中に変更せず、firmwareのsector
writeをCOW overlayへ保持します。input/outputを同じpathへ指定してはいけません。M-NESCO-S1の
再現可能なscenarioと実測値は
[`firmware-validation/evidence/m-nesco-20260813-01/`](../firmware-validation/evidence/m-nesco-20260813-01/)
にあります。これは`uf2loader`のmenu、boot2、watchdog、USB BOOTSELを実装したことを意味しません。

## Keyboard一次リファレンス

protocol producerの一次リファレンスはClockworkPi公式
[`PicoCalc/Code/picocalc_keyboard`](https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard)
です。ローカル配置は
`<PicoCalc checkout>/Code/picocalc_keyboard`です。

RP2040アプリはconsumer側の実機証拠であり、producer仕様の代用ではありません。model変更は公式の
register、FIFO、key state、modifier、repeat、overflowに一致させてから既知consumerと実機recordへ
照合します。詳細は[Keyboard conformance](KEYBOARD_CONFORMANCE.md)を参照してください。

## Board実装の境界

- PicoCalc固有条件はboard adapterとexternal-device modelへ置く
- 汎用RP2040 coreへPicoCalc前提を埋め込まない
- upstream履歴、copyright、license、attributionを維持する
- upstream変更を自動mergeせず、固定targetで回帰してから採用する
- `rp2040js`は比較資料であり、主backendとdevice pathを混在させない

LCD A/Bは別々のbus adapterです。Aを合格させるためにBのwire形式を変えたり、その逆を行ったり
しません。Canonical BSPの通常デフォルトはB（PIO0/RGB565/LCD DMAなし）です。

## Headless machine API

`picocalc-run --machine-api`はstdin/stdoutのJSON Lines schema 1で一回のsessionを操作します。
APIは状態操作面であり、target registryの最終合否を置き換えません。契約と利用例は
[Headless machine API](HEADLESS_MACHINE_API.md)を参照してください。

## 未対応または限定事項

- ELF／UF2の直接入力。現在はraw BINを使う
- bootromの実行とUSB MSC boot
- Threaded modelの正確性同等性
- NEXT-2A外の一般multicore、同時device access、relaunch、spinlock timing
- NEXT-2B外の任意audio構成
- audio解析から実機speaker音圧・周波数応答・物理volume位置を推定すること
- 人間の聴感をphone動画またはdigital metricだけで自動決定すること
- GDB/debugger integration

未対応機能は、具体的workloadと事前に固定した受入条件がある場合だけ拡張します。

## 公開と配布

公開版がprivate dependencyを要求してはいけません。public release前にbackend sourceを公開可能に
するか、同等に再現可能なsource packageを用意します。第三者conformance sourceや生成BINを
無断で配布せず、[Third-party notices](../THIRD_PARTY_NOTICES.md)を維持します。

完了済みのGate実装順と過去の判断は
[`history/EMULATOR_ROADMAP.md`](history/EMULATOR_ROADMAP.md)に保存しています。
