# 任意 I2C 外部モジュール emulation 計画（I2C-EXT）

状態: **E0・E1完了、E2 model/profile接続実装済み、E3以降未完了**（2026-08-23）

E0の固定証拠は[`firmware-validation/evidence/i2c-ext-e0-20260823-01/`](../firmware-validation/evidence/i2c-ext-e0-20260823-01/)
と[`firmware-validation/contracts/i2c-ext-e0-wire-v1.json`](../firmware-validation/contracts/i2c-ext-e0-wire-v1.json)にある。
E0ではproduction codeを変更していない。E1でcontroller address-phase契約、mux、data-NACK伝播、
共有virtual-time抽出を実装した。E2ではDS3231/AT24C32の独立model core、fixture検証、
picocalc-rtc-v1 profileのI2C1 attach、暫定sidecar metadataを実装した。E3の環境sensor、
E4の詳細sidecar/target接続、実機相関は未完了であり、capabilityはまだ変更しない。

## 目的

PicoCalcへ個人的に追加したI2Cモジュールを、通常のPicoCalc構成を変えずに
firmware backendへ任意接続できるようにする。最初の対象は、実績のある共有I2C1
（GP6/GP7）上の次の一式である。

| device | 7-bit address | 初期実装の役割 |
|---|---:|---|
| PicoCalc keyboard controller | `0x1F` | 既存モデル。共存を維持する |
| AHT20 | `0x38` | 温度・湿度のwire response |
| AT24C32 | `0x57` | RTC module上の設定EEPROM |
| DS3231 | `0x68` | RTCの時刻・status/OSF |
| BMP280 | `0x77` | 温度・気圧のwire response |

これはPicoCalc本体に搭載されたRTCではなく、共有I2Cバスへ外付けされた
moduleのモデルである。既存のkeyboard controller、LCD、SD、PSRAM、audioの
既定構成を置き換えない。

## 変更責務と外部依存

| 範囲 | この計画で行うこと | 行わないこと |
|---|---|---|
| `picoem-picocalc` | `rp2040-emu`のI2C/共有virtual time、`picocalc-board` mux・module stub、harness CLI/report | RTC実機sourceのvendorやhost実sensorへの接続 |
| `picocalc_emu` | fixture/schema、target contract、versioned validation、capabilityと利用文書 | 標準PicoCalc capabilityへの無条件昇格 |
| `RTC/` | E0/E5の一次referenceとしてread-onlyで参照 | emulator都合で既存実機appを変更 |
| 実機PicoCalc + 私的module | E5で一回だけ自動probe UF2を実行しUARTを回収 | 手入力、host時刻／実測環境値との完全一致要求 |

E0〜E4の実装とローカル検証はこのworkspaceだけで進められる。E5の同一UF2実機probeだけは、
私的moduleを接続したPicoCalcと利用者によるUF2実行・UART log提供を必要とする。証拠がない状態では
E6のversioned validation／capability昇格を宣言しない。

## 最上位設計原則

### 私的hardwareは既定構成へ入れない

この計画のRTC・environment sensorは、PicoCalcの標準hardwareではなく、個人的に
追加したmoduleである。従って、次を不変条件にする。

- `--board picocalc`、通常の`picocalc.py test`、既存targetはRTC/sensorを自動attachしない
- attachは各emulator runの起動時に`--i2c-profile`で明示し、profileを指定しないrunでは
  moduleが物理的に未接続であるのと同じNACKになる
- 次のrunでprofileを省略すれば取り外された状態へ戻る。process全体、host、既存targetへ
  module stateを持ち越さない
- standard PicoCalc capabilityとしては表示せず、受入後も「optional external I2C profile」の
  bounded capabilityとして記録する
- 実機配線の有無を推測しない。実機でmoduleが未接続・故障・別addressの場合は、emulatorが
  標準構成の成功を偽装しない

「run単位でattach/detachできること」はhot-plugの物理simulationを意味しない。起動後に
配線を抜き差しするmodelは初期範囲外であり、必要になった時だけ別のprotocolとして追加する。

### 将来の改造者のための明確な接続点にする

この実装はDS3231/AHT20/BMP280専用のif文をrunnerへ増やすものではない。将来の利用者が
forkして独自I2C hardwareを追加できるよう、次の責務を分離する。

| 層 | 責務 | 独自module追加時に触る範囲 |
|---|---|---|
| `rp2040-emu` | I2C controller、明示的address phase、ACK/NACK、STOP/repeated START、仮想時間hook | I2C wire contractを一般化するときだけ |
| `picocalc-board` I2C bus mux | address重複拒否、active childへのwire分配 | 新しいmoduleをprofileへ登録するときだけ |
| 各module model | address、register state、time advance、fixture、状態要約 | 新規ファイルとして追加 |
| harness/profile registry | CLI profile名、fixture検証、sidecar report | 新profileを明示登録するときだけ |
| versioned target | BIN、profile、fixture、期待値 | 相関を正式化するときだけ |

E1では、上記の最小interfaceを示す**接続点sample/stub**をboard側の開発用sourceとして
追加する。stubは通常runにもbuilt-in profileにも入れず、addressをclaimしない状態では何も
attachしない。新しいmoduleは、少なくとも次を独立して定義する。

1. 一意な7-bit address（既存keyboard/profileとのcollisionは構成時エラー）
2. write/read/STOP/repeated STARTのwire state
3. 必要なら仮想時間advanceとreset後に保持するstate
4. fixtureのschemaと状態要約
5. unknown/unsupported操作を成功に見せないnegative test

実行時に任意native pluginをloadする機構は初期範囲外である。利用者はこの明確なstubを
コピーしてsourceを追加し、自分のbackendをbuildする。これによりuntrusted code loadingを
導入せず、profile・fixture・reportのprovenanceを保つ。

## 到達点と非目標

到達点は、PicoCalc向けアプリが上記moduleを使う開発ループを、実機へ送る前に
決定的に検査できることとする。

- profileを明示したrunで、RTC・EEPROM・環境sensorのI2C transactionを実行できる
- 同一fixture・同一BIN・同一backendなら、RTC進行、readback、UART、reportが再現する
- RTC/EEPROMのwriteと、AHT20/BMP280の測定ready待ちを仮想時間で扱う
- keyboardと同じI2C1上で共存し、未知address・重複address・未対応registerを黙って成功にしない
- 新しいversioned targetと実機相関を通した範囲だけをcapabilityへ昇格する

初期範囲外は次の通りである。

- hostの現在時刻、hostの温湿度、USB機器、ネットワークから実値を読むこと
- I2Cの電気波形、プルアップ抵抗、配線不良、multi-master arbitration、clock stretchingの物理再現
- DS3231 alarm/SQW/aging/temperature、AT24C32の耐久性、AHT20/BMP280の全register面
- 任意のI2C機器をJSONだけで自動生成する汎用plugin機構

後続のmoduleは、同じ「source確認 → fixture → unit/firmware/hardware相関 →
capability」の手順で名前付きprofileとして追加する。未観測protocolを推測で
generalizeしない。

## 一次参照と確認済み前提

計画時の一次参照はローカル`RTC/`の実機用sourceである。これは公開runtimeの
依存ではなく、実装前にcommit・BSP・toolchainを固定し直すためのreferenceである。

- `RTC/Picocalc_RTCtest`: ZS-042のDS3231/AT24C32、I2C1、GP6/GP7、10 kHzの確認経路
- `RTC/Picocalc_Clock`: DS3231/AT24C32/AHT20/BMP280を同じI2C1で使う実アプリ
- `RTC/Picocalc_Clock/src/platform/env_sensor_probe.cpp`: AHT20/BMP280の実際の
  register/command sequence
- `RTC/Picocalc_Clock/src/rtc/ds3231.c`: BCD時刻、status/OSF、read/write sequence
- `RTC/Picocalc_Clock/src/settings/settings_store.cpp`: AT24C32の2-byte pointer、
  32-byte page write、ready pollingの使用法

確認済みの設計上の制約は次の通りである。

1. 現在の`I2cExternalDevice`はcontrollerごとに一つだけ保持する。
   `--keyboard`はI2C1へkeyboard wireを接続するため、RTC moduleを別々にattachすると
   後からattachしたmodelが前者を置換してしまう。
2. 現在のlegacy ACK stubは`[0x3C, 0x50]`である。外部deviceをattachしてもfallbackが
   有効なままなので、`0x57`のAT24C32 profileではphantom `0x50`を作り得る。
   profile使用時はこのstub全体を無効にし、muxがclaimしない`0x3C`と`0x50`の両方を
   NACKにしなければならない。一方、profileなしおよび既存`--keyboard`だけのrunは
   historical fallbackを維持する。
3. backendはI2C transactionをtransaction-levelで扱い、10 kHzと400 kHzのSCL速度を
   timing modelとして区別しない。初期profileもこの既存境界を超えて主張しない。
4. RTCの進行、EEPROM write cycle、sensor conversion waitをhost wall clockで進めると、
   report・scenario・parallel runの再現性が失われる。
5. 現在の`I2cExternalDevice::responds_to(&self, addr)`は不変borrowで、controllerは
   `IC_DATA_CMD`ごとに呼ぶだけで選択済みslaveを保持しない。`write_byte`、`read_byte`、
   `transaction_end`にはaddressが渡らないため、このままではmuxがactive childを正しく
   選べない。E1ではinterior mutabilityで回避せず、controllerとtraitを明示的な
   address-phase契約へ変更する必要がある。
6. 現在の`I2cExternalDevice::write_byte`は`bool`でdata NACKを表せるが、controllerが
   戻り値を捨てている。従って現状ではchild data NACKは`TX_ABRT`へ伝播しない。E1で
   controller側の既存欠落として修正し、公式`IC_TX_ABRT_SOURCE.ABRT_TXDATA_NOACK`（bit 3）
   を用いる回帰を追加する。
7. trait実装は`Keyboard`、`KeyboardWire`、I2C controller unit test用`SpyDevice`の3箇所である。
   E1のtrait移行はこの3実装と、それらを使う既存keyboard／controller回帰を同一変更単位で
   更新する。`KeyboardWire`だけを移行対象として扱わない。
8. `DATA_CMD_RESTART`は定義済みだが、現行controllerはbitを読まず、RESTARTのwire意味を
   実装していない。E1のrepeated STARTは既存動作の確認ではなく新規のcontroller semanticsであり、
   address phase・active child切替・STOP非送出をunit testで固定する。
9. 現在のunsupported 10-bit address abortは`ABRT_10ADDR1_NOACK`をbit 2としているが、
   RP2040 SDKのDW_apb_i2c定義では`10ADDR1`はbit 1、bit 2は`10ADDR2`である。I2C-EXTが
   10-bit addressを対応化するものではないが、E1でdata NACKのbit 3を追加する前に、既存の
   10-bit fail-closed経路をbit 1へ訂正し、bit 2と混同しない回帰を置く。
10. harnessには既にclock-rate rebasingを行う`VirtualClock`があり、scenarioと既存reportの
    `elapsed_us`を決めている。一方`rp2040-emu`はharnessへ依存できない。I2C用に別の時計を
    追加すると、scenario時刻とdevice時刻が二重化・乖離し得るため、E1では既存algorithmを
    core側の共有primitiveへ抽出し、harnessも同じsnapshotを読む形にする必要がある。
11. 現在のDW I2C modelは`IC_ENABLE.EN=1`の間の`IC_TAR` writeを無視する。このため
    「別addressへrepeated START」は現行モデル／対象firmwareのwire contractとして約束しない。
    初期範囲で別childを選ぶ正規経路はSTOP → disable → `IC_TAR`設定 → enable → 最初の
    DATA_CMDである。`RESTART`は同一targetでwrite/read phaseをつなぐ場合だけを扱い、
    enabled中の`IC_TAR`変更を許可してはならない。

## 固定する設計

### 1. Board側I2C bus mux

RP2040 coreのI2C controllerには、引き続き一つの`I2cExternalDevice`だけをattachする。
PicoCalc board crateに`I2cBusMux`を追加し、その内部で複数のchild modelを7-bit addressで
分配する。これによりcoreをPicoCalc固有のaddress表へ依存させない。

- muxはaddressの重複を構成時に拒否する
- E1で`I2cExternalDevice`を次のaddress-phase中心の契約へ進化させる。`address_phase`は
  `&mut self`でaddress ACKを返すため、muxはinterior mutabilityなしにactive childを選べる。
  `write_byte`の`false`はdata NACKであり、controllerはabort sourceとSTOP処理へ伝播する。

  ```rust
  trait I2cExternalDevice: Send {
      fn address_phase(&mut self, addr: u16) -> bool;
      fn write_byte(&mut self, byte: u8) -> bool;
      fn read_byte(&mut self) -> u8;
      fn transaction_end(&mut self);
      fn advance_virtual_time(&mut self, delta: I2cVirtualTimeDelta) {}
  }
  ```

- E1ではharness内の既存`VirtualClock`のepoch/rebase algorithmを、harness非依存の
  `rp2040-emu`共有virtual-time primitiveへ抽出する。Busがその唯一のinstanceを所有し、
  harnessのscenario／`elapsed_us` reportも同じsnapshotを読む。既存targetの`elapsed_us`を
  不必要に変えないことを回帰で確認する
- `I2cVirtualTimeDelta`はこの共有clockの前回snapshotとの差分である、単調な`u64`整数
  nanosecondsとする。既存`VirtualClock`と同じく`u128`整数演算でcycle/rateを換算し、
  浮動小数点は使わない。個別moduleが`master_cycle`やhost wall clockから時刻を再計算してはならない
- `tick_peripherals(cycles: u32)`と`advance_lazy_scheduled(consumed: u64)`は、各々が担当する
  advance windowについて共有clockをちょうど一度だけ進め、接続済みdeviceへ同じ形式の
  deltaを渡す。同じwindowを両経路で二重に進めない。E1では通常step、idle fast-forward、lazy scheduled advance、
  clock rate変更境界の同値性を回帰にする
- controllerはenable後の最初のDATA_CMD、disable中にtargetを設定し直してからenableした後の
  最初のDATA_CMD、または**同一target**の`RESTART`時だけ
  `address_phase`を呼び、選択済みaddressを保持する。STOPまたはaddress/data abortで
  選択状態をclearする。I2C controller disableとMCU resetでも選択状態をclearする。repeated STARTは前childへ`transaction_end`を送らず、新しい
  address phaseとして同じactive childのread/write phaseを切り替える。enabled中の`IC_TAR` writeは
  従来どおり無視する
- muxはactive transactionのchildだけへwrite/read/STOPを渡し、unclaimed addressをNACKにする
- `write_byte == false`は`INT_TX_ABRT`、`ABRT_TXDATA_NOACK`（bit 3）、FIFO flush、STOP/endの
  順に処理する。child data NACKを正常なwriteやsidecar passとして扱わない
- keyboardは既存の`KeyboardWire`のままchildとして入る。scenarioからのkey注入・counter観測を壊さない
- `I2cRegs`にはlegacy fallbackを明示的に無効化するexclusive attach modeを追加する。
  profileはmuxをこのmodeでattachし、`0x3C`／`0x50`を含めmuxがclaimしないaddressはNACKする。
  従来の`attach_device`とprofileなし／keyboard-only runはhistorical fallbackを維持する
- profileを使わない従来runでは、既存のsingle-device/fallback挙動を変えない

外部device interfaceには、既存のperipheral advanceと同じ仮想時間へ結合するための
time-advance hookを追加する。default実装はno-opとし、keyboardなど既存modelの挙動を
変えない。hookは通常のperipheral tickとidle fast-forwardの両方で**ちょうど一度**進める。
この点はRTC秒進行の正確性だけでなく、OPT1-Bのexact fast-forwardを保つ前提である。

### 2. 明示profileとfixture

初期CLIは次の名前付きprofileだけを持つ。

```text
--i2c-profile picocalc-rtc-v1
--i2c-profile picocalc-rtc-env-v1
--i2c-fixture <fixture.json>       # 任意。省略時はprofile固定のbuilt-in fixture
--i2c-report <report.json>         # profile指定時は必須
```

- `picocalc-rtc-v1`: DS3231 + AT24C32 (`0x57`)
- `picocalc-rtc-env-v1`: 上記にAHT20 + BMP280を追加
- profileは`--board picocalc`を要求する。keyboardを自動的に有効化はしないが、
  実アプリ相関targetでは`--keyboard`を明示して共存を検査する
- profileを指定しないことが唯一の既定であり、`--board picocalc`だけでprivate moduleを
  attachしてはならない。profile名が不明な場合も起動前エラーにする
- `--i2c-fixture`はschema/version、address、長さ、日時範囲、register byte列を起動前に検証する
- fixtureはbasenameとSHA-256をsidecar reportへ記録し、absolute pathをreportへ残さない

fixtureは「温度25.0度」のような高水準の値ではなく、deviceが返すregister/measurement
bytesを正典にする。これによりAHT20/BMP280の変換式を使うアプリを、wire値から検査できる。
人間が読みやすい期待温湿度・気圧はfixtureの検証値として併記するが、emulatorが推測で
逆算した値を出力しない。

初期fixtureは常に静的である。RTCの初期日時、OSF、EEPROM初期image、AHT20 measurement、
BMP280 calibration/dataは固定する。hostの時刻や実sensor値を読むoptionは追加しない。

### 3. 仮想時間とreset境界

- DS3231はbackendが使う単一の仮想経過時間から進める。instruction数、wall time、CPU速度は使わない
- clock tree変更をまたぐ経過時間は、同じvirtual-time定義で積算し、日付境界・閏年・day-of-weekを検査する
- DS3231時刻writeは次のreadから反映し、OSF clear/writeはregister semanticsに従う
- AT24C32 page writeのcommitとready NACK window、AHT20/BMP280 conversion readyは仮想時間で扱う
- MCU reset/warm resetでは外付けmoduleのstateを保持する。新しいrunner processはfixtureから新規に始める
- module stateのhost fileへの自動保存は初期範囲外である。必要なら後続で明示export/importを計画する

### 4. sidecar reportとfail-closed

既存のschema 8 reportと凍結targetを不必要に変更しないため、profile runは
`--i2c-report`で独立した`i2c-module-report` schema 1を出す。少なくとも次を含める。

- profile、fixture provenance、I2C instance/pin、attached address一覧
- deviceごとのtransaction数、read/write byte数、状態要約、streaming transaction digest
- RTC initial/final日時、OSF、EEPROM final image SHA-256、conversion/busyの観測回数
- unknown address、duplicate address、unsupported register/command、invalid fixture、protocol error
- `status: pass/fail`とfail reason

profile指定runでsidecarが生成できない、fixtureが不正、module protocol errorがある場合は
runner verdictをfailにする。unknown registerを`0xFF`で黙って成功扱いにはしない。
通常run（profileなし）はsidecar不要で、既存reportのbytesと既存target contractを変えない。

`picocalc.py test --mode firmware`にも同じoptionを追加し、新規targetではprofileとfixture SHA、
sidecar期待値をcontractで固定する。registered targetのdevice optionを任意overrideして通す経路は作らない。

## 実装順序

| 段階 | 内容 | 完了条件 | 概算 |
|---|---|---|---:|
| E0 | source/provenanceとwire contract固定 | RTC sourceのclean commit、SDK/BSP、I2C trace、fixture schema、対象register表を記録 | 5–8 h |
| E1 | I2C address-phase契約、bus muxと仮想時間hook | 3 trait実装移行、same-target RESTART semantics、10-bit abort bit訂正、既存VirtualClockの共有primitive化、keyboard + 複数childのactive routing、data NACK abort、duplicate拒否、legacy ACK isolation、通常/fast-forward時間advance test、独自module向け接続点stub | 18–28 h |
| E2 | DS3231 + AT24C32 | BCD/read/write/OSF、calendar rollover、EEPROM pointer/page/readback/ready polling unit test | 12–18 h |
| E3 | AHT20 + BMP280 | 実sourceが使うcommand/register sequence、ready待ち、fixture byte/CRC/calibration/data test | 12–20 h |
| E4 | runner/wrapper/report接続 | CLI validation、sidecar provenance、fail-closed verdict、`picocalc.py` target contract接続 | 8–12 h |
| E5 | firmware回帰と実機相関 | standalone transaction fixture、既存Clock app、3回determinism、実機1回の自動probe | 12–18 h |
| E6 | versioned validation/capability | 新target、record、capability境界、利用文書を確定 | 6–10 h |

合計は **73–114時間** を見込む。E1にはcontroller trait移行、shared virtual-time抽出、
data-NACK回帰を含む。
実機確認はE5で一回にまとめ、手入力を不要にした
自動probe UF2とUART log回収にする。E0でcleanなreference artifactを固定できない場合は、
E1以降へ進まず、最小の独立probe firmwareを新規sourceとして固定する。

## 段階ごとの検証

### E0 — wire contract

- `Picocalc_RTCtest`からDS3231 status/read/write/tickのtransaction列を採取する
- `Picocalc_Clock`からstartup probe、AT24C32 read/page write/ready polling、AHT20 init/measure/read、
  BMP280 ID/calibration/config/measurement readの列を採取する
- 現在のsourceが期待するaddressは`0x57`と`0x77`であり、`0x50`や`0x76`をprofileへ勝手に追加しない
- 各列についてACK/NACK、repeated START、STOP、read/write byte数、待機条件を機械可読contractへ固定する

### E1 — muxと時間基盤

**実装完了（backend commit `60ac700`、2026-08-23）**。E1の完了条件を満たす範囲として、
controller/trait migration、same-target RESTART、data-NACK abort、legacy ACK isolation、
board mux、共有`VirtualClock`、normal/lazy windowのdelta回帰、接続点stubを実装した。
profile CLI、fixture/report、AHT20/BMP280を含む環境profileはE2以降の範囲である。

- keyboard `0x1F`、DS3231 `0x68`、AT24C32 `0x57`、AHT20 `0x38`、BMP280 `0x77`を一つのI2C1 muxで識別する
- `Keyboard`、`KeyboardWire`、`SpyDevice`の3実装を同一trait migrationで更新し、既存keyboard
  transactionとcontroller unit testが変わらないことを確認する
- `address_phase`がenable後の最初のcommand、disable/reconfigure/enable後の最初のcommand、
  同一targetのrepeated STARTでのみ呼ばれること、
  muxが選択したchild以外へdata/STOPを渡さないことをunit testする。`Cell`／`RefCell`等で
  `responds_to(&self)`の副作用を持たせる実装は採用しない
- `DATA_CMD_RESTART`を明示的にdecodeし、same-addressでaddress phaseを開始する一方、前childへ
  STOPを送らないことをtestする。別address選択はSTOP/disable/`IC_TAR`/enable経路で検査し、
  enabled中の`IC_TAR` writeが引き続き無視されることも回帰する。RESTART未使用の従来実装を
  前提にしない
- childのdata NACKで`INT_TX_ABRT`と`ABRT_TXDATA_NOACK`（bit 3）が立ち、FIFO flush、STOP、
  active child clearが一度ずつ起きることをcontroller unit testする。address NACKとdata NACKの
  abort sourceを混同しない
- unsupported 10-bit addressは引き続きNACKし、`ABRT_10ADDR1_NOACK`が公式定義どおりbit 1、
  `ABRT_10ADDR2_NOACK`がbit 2であることをcontroller unit testする。I2C-EXTは10-bit deviceを
  profileへ追加しない
- I2C controller disableとMCU resetでもactive childが残らず、次のenable後に必ず新しい
  `address_phase`から始まることをunit testする
- profile attach時は`0x3C`と`0x50`のlegacy stubがACKしないことを確認する。profileなしと
  keyboard-only runではhistorical fallbackが変わらないことも別々に回帰する
- profileなしではmuxもprivate moduleもattachされず、既存targetのI2C結果が変わらないことを確認する
- unknown addressはaddress NACK、duplicate addressは起動前エラー、child data NACKはcontrollerの正しいabort経路へ入ることを確認する
- normal stepping、idle fast-forward、clock tree変更、warm resetで仮想経過時間の二重計上・欠落がないことを確認する
- 同じcycle/rate timelineを1 cycle stepping、bulk `tick_peripherals`、lazy scheduled advanceで
  実行して、共有virtual-timeのnanosecond delta列、既存harnessの`elapsed_us`、
  DS3231/EEPROM/sensorの状態遷移が一致することを確認する
- profileなしのkeyboard unit/firmware regressionを先に再実行し、既存挙動が変わらないことを確認する
- 接続点stubを使った最小custom address modelのunit testを置き、DS3231等の実装をコピーしなければ
  新moduleを追加できない構造になっていないことを確認する

### E2 — RTC/EEPROM

**model coreとprofile接続実装済み（backend commits `f1ae8dc`、`5802b2e`、2026-08-23）**。
`picocalc-rtc-v1`を明示指定したrunだけがDS3231/AT24C32をI2C1へattachし、
`--i2c-fixture`をschema 1として検証してfixture basename/SHAと接続addressを暫定sidecarへ記録する。
profileなしの通常runは変わらない。E2のmodel/profile範囲は完了したが、詳細transaction digest、
picocalc.py target contract、firmware相関はE4/E5で行う。

- DS3231は`0x00..0x06`のBCD時刻、`0x0F` status/OSF、およびsourceが実際にwriteする範囲だけをモデル化する
- 2000–2099の月末、閏年、年越し、day-of-week、時刻write直後のreadbackをunit testする
- AT24C32は4 KiB、2-byte pointer、32-byte page、sequential read、STOPでのwrite確定、
  deterministic ready pollingを対象にする
- 未対応DS3231 featureやEEPROM page境界違反はreportへ残し、profile runをpassにしない

### E3 — 環境sensor

- AHT20はsourceが使うstatus、init command、measurement command、measurement responseを対象にする
- BMP280はchip ID、calibration block、config/control write、measurement blockを対象にする
- 返すAHT20 CRCとBMP280 calibration/dataはfixtureに固定し、既存アプリの補償計算結果をunit testする
- conversion完了前read、誤command、未定義registerは明示的なprotocol errorとしてsidecarに残す

### E4/E5/E6 — runnerから実機相関まで

1. profileなしの既存targetとunit testをローカルで完走する
2. DS3231/AT24C32/AHT20/BMP280のbyte-level fixtureをunit testする
3. 独立I2C probe firmwareをfirmware backendで走らせ、address、read/write/readback、時間進行、
   keyboard共存、sidecar digestを3回一致させる
4. 固定した`Picocalc_Clock`または同等clean sourceを使い、startup probeと画面/UARTの期待値を検査する
5. 同一UF2を実機へ一度だけ送る。自動probeのUART logでaddress ACK、RTC read、EEPROM readback、
   AHT20/BMP280のread成功を確認する。実機の環境値は固定fixture値との一致を要求しない
6. source/BIN/UF2/backend/profile/fixture/sidecarを新しいversioned recordへ固定してから、
   `capability.json`へbounded capabilityを追加する

GitHub Actionsはデバッグに使わない。各段階はlocal unit/build/firmware verificationを先に通し、
関連変更をまとめてcommitする。CI構成を変える必要が出た場合は、使用量と理由を事前に承認する。

## capabilityの昇格条件

E6以前は`capability.json`へ「RTC/environment supported」と書かない。E6で次を満たした場合だけ、
たとえば`i2c-external-rtc-env-v1`としてbounded capabilityを追加する。

- E0のsource/provenanceとfixture contractが固定されている
- E1〜E4のunit test・negative test・profileなし回帰が合格している
- E5の同一BIN firmware runが3回deterministicである
- keyboard共存、RTC write/readback、EEPROM write/readback、AHT20/BMP280 readが同じtargetで合格している
- 実機の自動probeで、同じaddressと基本transactionが成功している
- limitationとして、private optional profile、静的fixture、I2C電気特性非モデル、未対応register、host sensor非連携を明記している

この条件を満たしても、実機の現在の温湿度・気圧そのものや、外付け配線不良をemulatorが判定できるとは主張しない。
