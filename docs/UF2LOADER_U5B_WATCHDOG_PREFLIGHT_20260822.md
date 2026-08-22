# UF2Loader U5-B watchdog warm reset preflight

作成日: 2026-08-22
対象: `picocalc_emu` / `picoem-picocalc`
状態: **実装・受入完了。U6 clean Gateで各runのwatchdog epoch 1、flash／SD保持、boot2再入場を確認済み**

この文書は、[`UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`](UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md)
のU5-Bを実装する前に、RP2040 watchdogの一次仕様、現行backendの境界、実装順序、受入条件を固定する。
通常のdirect-bootアプリdebugの起動方法は変更しない。U6の実`uf2loader` end-to-endで必要になる
`watchdog_reboot(0, 0, 0)`の最小経路だけを対象とし、任意タイマーの完全なwatchdog再現やUSB BOOTSEL/MSCは
この作業には含めない。

## 1. 一次資料で確認した事実

### 1.1 Pico SDKの`watchdog_reboot(0,0,0)`

固定SDK (`/home/fuyuki/pico_dvl/codex/pico-sdk`) の
`src/rp2_common/hardware_watchdog/watchdog.c`では、`watchdog_reboot(0, 0, 0)`は次の順序で動く。

1. `WATCHDOG_CTRL.ENABLE`をclearする。
2. `scratch[4]`へ`0`を書き、「通常のflash経路へ戻る」ことを示す。
3. `_watchdog_enable(0, false)`を呼ぶ。
4. `PSM_WDSEL`へ、ROSC/XOSC以外のreset対象を書き込む。
5. pause-on-debugをclearする。
6. `WATCHDOG_CTRL.TRIGGER` (bit 31) をsetする。

従ってU5-Bの必須MMIOは、タイマーのcountdownではなく、**CTRLのsoftware triggerとscratch保持**である。
`LOAD`による遅延timeoutは今回の対象外とする。

### 1.2 uf2loaderの実使用

外部`uf2loader` pinned source (`5c44a4b64749062b0200507ceeff3ef2b475e288`) の
`ui/main.c`は、SD上のUF2をflashへ書き終えた後に`watchdog_reboot(0, 0, 0)`を呼ぶ。
また`common/bootloader/proginfo.c`では、stage3への一時コマンドを`scratch[0..2]`へ保存し、
`bl_get_command()`がmagicを読んだ後に`scratch[0]`だけをclearする。

したがってwarm resetでは、少なくとも次を保持しなければならない。

- XIP flashの内容（erase/program後のbytes）
- SDカードのsector backingとCOW overlay
- watchdog `scratch[0..7]`（stage3 commandを含む）

scratchは「reset時に全消去する診断用レジスタ」ではない。実機同様、warm resetを跨ぐ通信領域として扱う。

### 1.3 現行backendの境界

`rp2040-emu::Emulator::reset()`は現在、CPU、SIO、RESETS、clock、TIMER、SPI、I2C、DMA、NVIC、PIO等を
初期化する一方、`Memory`のflash backingは消去しない。SPI外部deviceもboard deviceとして保持する。
ただし`reset()`は次を行うため、そのままwarm resetへ流用してはいけない。

- `clock.cycles`と`bus.master_cycle`を0へ戻す
- `watchdog_tick`をpower-on相当へ戻し、scratchを消す
- PSRAMのprotocol stateをresetする
- runnerが持つscenario時刻・UART蓄積・dispatch履歴を知らない

SDは`Arc<Mutex<SdCard>>`でrunnerと`SdCardWire`が共有され、RAW file本体とCOW overlayはカード側にある。
SPI controller resetでFIFOを捨てても、card backing自体は消えてはならない。一方、reset時にCS下で残った
command/data phaseは次のrunへ漏らしてはならないため、wire/cardのtransaction stateだけを明示的にidleへ戻す。

## 2. 実装境界

### U5-B-0: watchdog register model

現行`WatchdogTickRegs`を、既存のTICK／scratch互換を保ったまま次の最小状態へ拡張する。

- `CTRL`: `TRIGGER`（write-one/software command）、`ENABLE`等の観測可能なstorage
- `LOAD`: 値を保持するが、遅延timerとしては動かさない
- `REASON`: force reset bitをwarm reset後にreadback可能にする
- `SCRATCH0..7`: read/write、warm resetで保持、cold resetだけpower-onへ戻す
- `TICK`: 既存のtimer cadence互換を維持

`WATCHDOG` blockがRESETS bit 24でheld中の書込みは、現行のbus-level gateと同じくdropする。
TRIGGERは通常のMMIO writeの結果として「pending reset」をlatchし、同じ命令の途中でCPUを破壊しない。

### U5-B-1: reset requestの命令境界

CTRL.TRIGGERを書いた直後のscheduler境界で一度だけrequestを消費する。
trigger命令の後に次のfirmware命令を実行してからresetする実装は禁止する。逆に、write callbackの
内部でRust stackを巻き戻すような非局所resetも禁止する。

最低限、次を公開またはrunner内部で取得可能にする。

- pending requestの有無
- reset reason (`force`)
- request発生時のcore／PC
- reset epoch／回数

### U5-B-2: warm reset transaction

`Emulator::warm_reset()`相当の専用経路を追加する。cold `reset()`とは別APIにし、次の契約を持たせる。

保持するもの:

- `Memory`のXIP flash bytes、SSI flashのerase/program結果
- 接続されたSD cardのRAW backingとCOW overlay
- watchdog scratch、reset reasonのwarm-reset観測値
- runnerが管理する単調なepoch／累積cycle基準

初期化するもの:

- CPU 0/1のregister、halt/WFE、VTOR、exception state
- SIO FIFO、NVIC pending/enable、SysTick、IRQ bitmap
- DMA channel state、PIO SM/FIFO/IRQ、TIMER alarm state
- SPI/I2C/UART/ADC/PWMのMCU-side FIFO・status・clock state
- SSI/SD/SPIの**transaction parserとFIFO**（外部データbackingは保持）
- GPIO／RESETS／PLL／clock tree等のMCU peripheral state

外部board deviceは「電源断」と同一視しない。LCD、SD、PSRAMのデータ内容は消さず、MCU resetで
CS/transactionが中断された場合だけwire protocol stateを安全なidleへ戻す。PSRAM protocol resetは既存の
`reset_state()`方針を再利用するが、将来buffer backingを持つdeviceを追加する場合は、protocol stateと
storage stateを分離する。

### U5-B-3: runnerの再入場

runnerはtriggerを検出したら、同じ`boot mode`を明示的に再入場させる。

- `--boot-mode boot2`: warm reset後に`boot2_from_flash()`へ再入場する。U6のuf2loader経路はこれを使う。
- `app`: 既存の`direct_boot_from_flash(0x100)`を再適用する。既定app debugを暗黙にboot2へ変更しない。
- `bootrom_reset_vector`: 既存のreset-vector経路を再適用する。

実RP2040のfull bootrom／USB経路をここで追加するわけではない。boot2を選んだrunだけが実loaderの
flash先頭boot2を再実行する。

runnerのscenario／machine sessionは同一sessionとして継続し、次を巻き戻さない。

- 累積master cycle（cycle budget判定）
- virtual timeとheartbeat sequence
- scenario dispatch countとUART蓄積
- reset epoch／reset count

各boot epochの開始PC、mode、reset reason、flash/SD digestをreportへoptionalなreset recordとして追加する。
既存のresetなしtargetのreport byte列は変更せず、新しいU5-B targetだけversioned validationで受け入れる。

## 3. 実装しないもの

- watchdogの任意delay／countdown／`watchdog_enable()` timeoutのcycle-accurate再現
- USB BOOTSEL/MSC、実RP2040 bootrom全体
- GPIO resetだけを理由にLCD/SD/PSRAMのstorageを消去すること
- `--boot-mode app`を常時boot2へ置き換えること
- machine APIへ暗黙にreset commandを追加すること（必要なら別schema／別受入）
- uf2loader sourceのvendor、外部checkoutへの変更

## 4. 受入条件

### 4.1 unit / host

- CTRL.TRIGGERがWATCHDOG reset gate解除後だけpendingになる。
- trigger write後の同一命令内ではregister／memoryアクセスが完了し、次命令は実行されない。
- `REASON_FORCE`、`LOAD`、`SCRATCH0..7`のread/writeとalias動作を固定する。
- cold resetはscratch／reasonをpower-onへ戻し、warm resetはscratchとflashを保持する。
- warm reset後にCPU、DMA、PIO、IRQ、timer、MCU-side FIFOが初期状態になる。
- SD/SSIのparserだけがidleへ戻り、SD backing／COW overlayとflash bytesがbyte一致する。
- reset epochと累積cycleが単調で、既存resetなしrunのreport／hashは変わらない。

### 4.2 firmware integration

最小fixture firmwareで、次を同一run内に検査する。

1. flashの既知byteを読み、SD sectorを読み書きする。
2. watchdog scratchへmarkerを書き、`WATCHDOG_CTRL.TRIGGER`を発行する。
3. reset後のentry markerで再入場を確認する。
4. flash、SD sector、scratch、reset reason、epochをUART/reportへ出す。
5. 同じfixtureを`app`と`boot2`の両modeで3回ずつ実行し、結果を比較する。

### 4.3 uf2loader integration（U6へ接続）

U5-B単独では外部loader全体を正式受入しない。U4のclean trace条件を保ったclean uf2loaderで、
flash program後の`watchdog_reboot(0,0,0)`が発行され、boot2再入場後に次のappが起動することをU6で確認する。
受入artifactには、reset count／epoch、scratch command、flash before/after、SD source/dirty、
boot mode、UART、scenario、final flash SHAを含める。

## 5. fail-closed項目

次は明示的にFAILとする。

- TRIGGERが検出されたのにreset epochが増えない。
- reset後にflashまたはSD backingが変化／消失する。
- scratch commandが消える、またはmagicを二重消費する。
- trigger後に余分なfirmware命令を実行する。
- 累積cycleが減る、cycle budgetをリセットして無限に走る。
- reset後にSD/SSIの途中transactionを前runから再利用する。
- boot2 modeなのにdirect appへ戻る、またはapp modeへboot2を暗黙適用する。

## 6. 実装順序とローカル検証

CIは使わず、次の順序でローカル検証する。

1. `WatchdogRegs`のunit test（CTRL/LOAD/REASON/scratch、alias、gate）
2. `Emulator::warm_reset`のSerial unit test（保持／初期化／単調cycle）
3. SD/SSI wire parser reset test（backing保持、途中transaction破棄）
4. runnerのtrigger検出・boot mode再入場・optional report test
5. synthetic fixtureの`app`／`boot2` 3-run deterministic比較
6. 既存firmware regression（PicoTetris、PicoEdit、NEXT-2、M-NESCO-S1、U4 traceなし／あり）
7. clean uf2loaderを使うU6 Gate（U5-Bの受入を包含）

最終的なローカルコマンドは少なくとも次を含む。

```sh
cargo test --locked
cargo clippy --locked -p rp2040-emu -p picocalc-board -p picocalc-harness --all-targets -- -D warnings
python3 tools/picocalc.py verify
python3 -m unittest tests.test_tools
```

### 6.1 工数見積り

| 作業 | 目安 |
|---|---:|
| watchdog register／trigger model | 2〜4時間 |
| warm reset境界と保持／初期化テスト | 3〜5時間 |
| runner再入場・report・scenario接続 | 2〜4時間 |
| 既存回帰・fixture・U6接続用preflight | 2〜4時間 |
| **合計** | **9〜17時間** |

実装中にfull watchdog countdown、bootrom、または外部deviceの電源モデルが必要と判明した場合は、
このgateで停止して再見積りする。未観測の仕様を推測で追加しない。

## 7. 着手判定

U4-P2のprotocol判断、U5-Aのboot2 production実装、現行のSD/flash保持経路、U5-B production実装と
local regressionが完了している。U6 clean Gateでは、同じbackend commitでwatchdog resetを各run一回、
epoch 1として観測し、reset後のSD／flash保持とboot2再入場を確認した。今後の変更は新しいclean
backend commitでU6 Gateを再実行する。
