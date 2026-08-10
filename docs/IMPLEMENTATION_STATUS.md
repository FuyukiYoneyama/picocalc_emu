# 現在の実装状況

この文書は現在値だけを示します。実装経緯や当時の「次の作業」は
[`history/`](history/README.md)へ分離しています。

更新日: 2026-08-10

## 版とbackend

| 項目 | 現在値 |
|---|---|
| Canonical BSP source | 0.9.0 |
| 標準機能の実機相関baseline | 0.8.8 |
| template app版 | `0.8.4-*`（BSP版と独立） |
| 推奨LCD | `pio-rgb565` |
| SD既定 | FAT32。FAT16は明示profile |
| 正確性基準 | Firmware backend `ExecutionModel::Serial` |
| 通常promoted backend | `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`（OPT1-B） |
| 実機相関済みR5 backend | `612b48510452d4012e4ac6639960ca3983b48f66`（不変証拠） |
| backend開発main | transientなbranch headであり、正確性の権威ではない。各targetの固定commitを使用 |

targetはそれぞれ正確なbackend commitを固定します。branch headやローカルmainを自動採用しません。

## 利用できる経路

### Canonical BSP

- 実機確認済みのLCD A/B、keyboard、SD/FatFs、PSRAM、audio API
- 通常アプリの変更範囲を`app/`へ限定
- source fingerprint、board profile、reference evidenceの検査
- FAT32/FAT16共有filesystem API。PicoEditでFAT32同一artifact相関済み
- 音声DMA channel/timer枯渇をpanicにせず`init()==false`で返し、部分claimをrollback
- 生成projectのBSP tree provenanceをCLI buildと直接CMakeの両方で照合

### Host backend

- framebuffer、keyboard FIFO、PSRAM、RAM-backed SD
- deviceと同じfilesystem sourceをネイティブ実行
- 仮想時刻と決定的な繰り返し検査
- hardware-freeなアプリロジックの高速試験

### Firmware backend

- Pico SDK BINのdirect boot、XIP、UART0、exception、unsupported MMIO
- A/B LCD、PIO、DMA、PSRAM、keyboard controller、SPI SD
- scenario、途中snapshot、fail-closed schema 8 verdict
- exact idle fast-forwardとOPT1-B fast path
- target registryとversioned validation
- 外部project用quality gateで、audio観測とoracle評価を`not_evaluated/pass/fail`へ分離
- schema 8を維持した独立audio解析artifact、非正規化raw WAV、schema 3 project契約により、
  控えめな区間音量をadvisory、極端なPWM rail張り付きをFAILとして分離

### 範囲を固定して対応済み

- NEXT-2A: core 1 launch、双方向SIO FIFO、WFE/SEV、core-local SIO IRQ
- NEXT-2B: 48 kHz stereo、固定DMA timer／PWM sliceのdigital sample sink
- NEXT-3: CMD8 mandatory CRC7 errorの実機・emulator negative conformance
- NEXT-4: JSONL schema 1の`run`／`step`／`run_until`／`input`／`observe`／
  `subscribe`／`snapshot`

これらは凍結targetで証明した範囲です。似たworkload全般へ自動的に一般化しません。

## 性能

正式promoted値はPicoTetrisでwall中央値**25.381594秒**、実時間比**14.636593%**です。
R5前baseline 63.247秒から約2.492倍高速化しています。

OPT2候補は追加promotionなし、OPT3-Bは退行、OPT3-Cは4.1542%改善でしたが5%採用基準未達で
revertしました。性能最適化は現在停止しています。

## 実機相関とnegative conformance

- R5 PicoTetris: 同一artifact合格
- NEXT-1 PicoEdit: 同一artifact合格
- NEXT-2A multicore: 凍結v2同一artifact合格
- NEXT-2B audio: 凍結v3同一artifact合格
- OPT1-B: R5 observation contractとのexact equivalenceによりpromoted
- NEXT-3 SD CRC: hardware-confirmed negative母数1

NEXT-3の初回凍結backendはFault BINを誤ってacceptし、修正後backendは実機と同じR1 CRC error理由で
rejectしました。母数1なので一般的なfalse-acceptance率へ外挿しません。

## 未対応または限定事項

- Threaded executionを正確性基準にすること
- NEXT-2A外の同時device access、spinlock timing、core 1 relaunch
- NEXT-2B外のcodec、sample rate、DMA layout、mixing、speaker response。48 kHz PWM5_CCの
  level解析はdigital境界だけで、実際の音圧やspeaker responseは含まない
- bootrom execution、USB MSC boot
- SD multi-block、removal、write protect、raw image persistence、directory-backed storage
- host backendのPIO、DMA、I2C transaction、interrupt、multicore、LCD wire形式
- scenarioのloop／branch、任意report fieldの直接assert
- 実機の色、向き、可読性、キーの物理反応品質。聴感は自動モデルではなく、固定された2問式の
  実機speaker受入記録で判定

完全な機械可読一覧は
[`firmware-validation/capability.json`](../firmware-validation/capability.json)を優先します。

## リポジトリ状態

working treeやpush済みかどうかは一時状態なので本書には固定せず、作業開始・終了時に各repositoryで
`git status --short --branch`を確認します。GitHub Actions節約方針により、通常開発ではCIを起動せず
ローカル検証を主体とし、push／CI実行は別途判断します。

## 詳細履歴

2026-08-10までの詳細な実装記録は
[`history/IMPLEMENTATION_STATUS_DETAIL_20260810.md`](history/IMPLEMENTATION_STATUS_DETAIL_20260810.md)に
保存しています。
