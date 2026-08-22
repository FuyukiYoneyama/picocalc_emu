# UF2Loader U5-A boot2 起動経路 preflight

作成日: 2026-08-22
対象: `picocalc_emu` / `picoem-picocalc`
状態: **production実装・受入完了。U6のclean loader Gateでboot2→stage3→SRAM UI到達を再確認済み**

## 1. 目的と境界

U5-Aは、通常のアプリ開発で使う既定の`direct_boot_from_flash(0x100)`を変更せず、
`picocalc-run --boot-mode boot2`を明示した場合だけ、flash先頭のboot2へ入る経路を追加する。

この段階で実装するのは、RP2040のreset後にboot2へ制御を渡し、boot2がflash上のstage3へ
handoffする経路である。**実RP2040 bootromの実行、QSPI padの完全再現、USB BOOTSEL/MSCは対象外**である。
boot2の入口契約をエミュレーター側で明示し、後続U4の実loader SD traceを取得できる状態を作る。

既存の`app` modeは次を保証する。

- `--boot-mode`未指定時は従来どおり`direct_boot_from_flash(0x100)`。
- 既存targetのreport、UART、framebuffer、cycle、scenarioの意味を変えない。
- `boot2`を指定しないrunへ新しいboot2依存を持ち込まない。

## 2. 実ソースで確認した前提

### backendの既存経路

`crates/picocalc-harness/src/main.rs`の`boot()`は、現在次の順序で初期化する。

1. firmwareをXIP flashへload
2. board／keyboard／SD／PSRAM deviceをattach
3. bootromをload（ROM function lookup用、実行しない）
4. `emu.reset()`
5. SDK vector table (`flash + 0x100`) を検査
6. `emu.direct_boot_from_flash(0x100)`

`rp2040-emu::Emulator::direct_boot_from_flash()`はSP、PC、VTORをvector tableから設定し、core 1をhaltする。
このAPIは既定`app` modeとして残す。

### boot2を支える既存モデル

`rp2040-emu/src/bus/ssi_flash.rs`には、既に次がある。

- SSI flash command parser
- CS解除時のtransaction commit
- boot2が使うQuad-I/O read (`0xEB`)の既知command扱い
- XIP flash windowと同一のflash backing
- SSI transactionのunknown command／mutation diagnostics

従ってU5-Aの第一候補は、SD／flash protocolを先回り拡張することではなく、既存emulator APIに
boot2 entry helperを追加し、runnerの起動選択へ接続することである。

## 3. uf2loader artifactの実配置

一次sourceとprovenanceはU0／U4 preflightの固定に従う。

- source: 外部`pelrun/uf2loader`
- pinned commit: `5c44a4b64749062b0200507ceeff3ef2b475e288`
- RP2040 custom boot2: flash offset `0x000000`
- stage3 vector table: `BOOTLOADER_START = 0x101fc000`（2 MiB flash末尾から16 KiB）

uf2loaderの`stage3/CMakeLists.txt`は、RP2040 stage3へ`boot2_custom`を組み込み、
`BOOTLOADER_START=0x101fc000`を定義している。boot2のloader-specific handoffでは、
flash先頭のboot2がstage3 vector tableを読み、stage3の初期SP／PCへ移る。

初期probeはprivateな共有workspaceのdirty checkoutを使った仕組み確認用であり、単独の受入証拠には
使わない。正式U5-A確認は、U6で同じpinned commitのdetached clean clone、固定SDK、固定toolchain、
完全なbuild commandを使って行った。

## 4. 一時probeで確認したこと

本番コードを変更せず、外部`build_pico/stage3/bootloader_pico.bin`をflashへ置いた一時テストで、
次の入口契約を試した。

- `SP = 0x2004_2000`
- `LR = 0`（uf2loader custom boot2のstage3 handoffを選ぶ値）
- `PC = 0x1000_0000`（flash先頭のboot2）
- core 1は`reset()`後のhalt状態を維持
- step quantum 1

2,000,000 cycleのprobeは次を得た。

```text
result       = Ok(2000000)
pc           = 0x101fd64e
sp           = 0x20042000
vtor         = 0x2003f000
bus_fault    = false
unknown SSI  = []
SSI commands = [(0x35, 1), (0xeb, 1)]
```

これは、現在のSSI/XIP/CPUモデルがboot2を実行し、stage3側へ制御を渡せることの確認である。
dirty artifactを使ったため、cycle値、PC、command列、stage3の動作を正式なhardware／protocol
証拠として扱わない。また、これをもってU4のCMD18／CMD12実装根拠とはしない。

## 5. U5-Aで実装した最小変更

### 5.1 emulator API

`rp2040-emu::Emulator`へ、直接bootの既定動作と分離した`boot2_from_flash` entry helperを追加した。
helperの責務は次に限定する。

- flash先頭のboot2へPCを設定（`0x1000_0000`）
- RP2040 SRAM stack上端（`RP2040_SRAM_TOP = 0x2004_2000`）を初期SP／R13へ設定
- custom boot2のstage3 handoffを選ぶためLR=0を設定
- Thumb状態、core 1 halt、reset後のdevice stateを維持
- boot2開始時のboot modeを呼び出し側がreportできるようにする

helperは任意のboot2 binaryを「正しい」と宣言しない。boot2が停止、fault、未知MMIO、cycle limit
へ到達した場合はvisible failureとし、stage3へ到達したことだけをboot2成功条件の一部とする。

### 5.2 runner CLI

`picocalc-run`へ次を追加した。

```text
--boot-mode app|boot2
```

- 既定値は`app`。
- `app`は現在の`direct_boot_from_flash(0x100)`と完全に同じ。
- `boot2`はflash offset `0x000000`へ入る。
- `--boot-mode`の未知値はparse error。
- U5-A初版では`--machine-api`との併用を拒否する。machine APIへboot2を追加する場合は、別の明示的な
  contract／schema／受入試験を先に定義し、暗黙のstartup変更として通さない。
- `boot2` modeではvector tableがflash+0x100にあることを起動前条件にしない。

reportには既存の`boot.mode`へ`"boot2"`を追加した。boot2では`vtor_flash_offset`を`null`とし、
direct bootの値を誤って流用しない。`app`の既存report byte列は変更しない。
boot2では、direct boot専用の`vtor_flash_offset`を誤って意味付けしないよう、report builderと
schema testで「boot modeごとの意味」を固定する。schema revisionが必要な場合はboot2利用時だけ
新revisionを出し、既存targetのschema 8を変更しない。

### 5.3 `tools/picocalc.py` forwarding

U5-A初版では、通常の`picocalc.py test --mode firmware`へboot2を暗黙追加しない。
まず`picocalc-run --boot-mode boot2`を明示した専用conformance実行で入口を閉じる。
registry経由の再現が必要になった段階で、`boot_mode=boot2`を宣言したtargetだけへ固定引数を付ける
専用contractを追加する。任意firmwareへboot2を既定適用する一般passthroughは作らない。

## 6. U5-A受入条件

### unit / host

- `boot2_entry` helperがSP、LR、PC、core 1 haltを正しく設定する。
- `app` modeが既存direct bootと同一のSP、PC、VTOR、reportを生成する。
- 空flash、boot2領域不足、boot2開始後のbus faultをvisible failureにする。
- `boot.mode=boot2`をJSON parser／schema testが受け入れる。
- `--boot-mode`のparse／help／forwarding testが合格する。

### firmware integration

clean uf2loader artifactで、flash offset 0のboot2が実行され、stage3 vector／entryへ到達する。
最低限、次を記録する。

- source／SDK／toolchain／build flags／artifact SHA
- initial flash SHAとstage3 vector offset
- boot2 entry cycle、stage3 entry PC、SP、VTOR
- SSI command counts、unknown command、bus fault、exception
- boot2 modeのreport、UART、scenario stop reason

boot2入口からstage3へ到達できても、SD directory列挙、UF2選択、flash program、watchdog resetが
未完ならU5-Aだけを合格とする。`uf2loader supported`へのcapability昇格はU6まで行わない。

### 回帰

- PicoTetris／PicoEdit／NEXT-2／M-NESCO-S1の既存direct boot regressionはlocalで合格する。
- `--boot-mode`未指定の既存targetにreport差分を出さない。
- trace／heartbeat／boot2 diagnosticsはexactness hashへ混入させない。
- CIは実行しない。必要性が生じた場合は、ローカルで代替できない理由とActions使用量を先に確認する。

## 7. U4以降との依存関係

U5-Aを先に閉じる理由は、U4のclean実loader SD traceが現在のdirect-boot runnerでは取得できない
ためである。順序は次のとおりとする。

```text
U5-A boot2 entry
  -> U4 clean loader SD protocol trace（CMD18/CMD12は観測時だけ実装）
  -> U5-B watchdog warm reset
  -> M-NESCO拡張受入
  -> U6実uf2loader end-to-end
```

U5-Aが失敗した場合は、U4のSD production codeを推測で追加せず、boot2入口で停止して原因を
記録する。U5-Aの成功は「boot2からstage3へ入れる」ことだけを意味し、bootrom／USB BOOTSEL／
watchdog／UF2Loader全体の対応宣言ではない。

## 8. 実装開始前チェックリスト

- [x] production codeを変更せず、既存SSI/XIPモデルでboot2→stage3の一時probeを確認
- [x] default app modeを保持する境界を確認
- [x] 外部checkoutのdirty状態を正式証拠から除外
- [x] clean artifact再生成とprovenance記録を正式受入の前提にする
- [x] `Emulator::boot2_from_flash`相当のproduction APIを実装
- [x] runner `--boot-mode app|boot2`を実装
- [x] report/schema／CLI forwarding testを追加
- [x] clean artifactでU5-A evidenceを保存（U6 Gateのboot2／loader snapshot／reportへ包含）
- [x] U5-A入口を使ったU4-P2 clean loader traceでstage3→SRAM UI到達を確認

## 9. 実装後のローカル検証

production変更後、CIを使わず次をローカルで確認した。

- `cargo check --locked -p rp2040-emu -p picocalc-harness`
- `cargo test --locked -p rp2040-emu --test smoke --lib`（1246 unit + 8 smoke）
- `cargo test --locked -p picocalc-harness --bin picocalc-run`（65 tests）
- `--boot-mode boot2`で外部loader artifactを実行し、reportの`boot.mode=boot2`、
  `vtor_flash_offset=null`、boot2→stage3側PC遷移、SSI `0xEB`観測を確認
- unknown boot modeと`--machine-api`併用をfail-closedで拒否

初期のdirty checkout実行は機構確認に限る。正式closeはU6のclean Gateで行い、pinned commitの
detached clean clone、固定SDK／toolchain、artifact SHA、stage3 entryを含むreportとsnapshotを
`firmware-validation/evidence/uf2loader-u6-20260822-01/`へ保存した。
