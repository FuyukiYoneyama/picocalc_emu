# レジスタ／メモリ観測（正式デバッガ機能）提案書

作成日: 2026-08-13
起票: Sol（heartbeat監督とnes2/mapper_check実プロセスの実地調査から）
対象: `picoem-picocalc` `rp2040-emu` / `picocalc-harness` / `picoem-debug`
状態: **提案のみ。実装・変更は未実施。**

## 1. 要旨

長時間の`--scenario`実行を監督する側（人間・AI）は現在、プロセスの生死と壁時計の経過時間しか
判断材料を持たない。heartbeat（`--run-id`/`--progress-interval`）はこれを大きく改善したが、
「まだ健全に前進しているか」しか答えない。「ファームウェアが特定PCで無限ループしているのか、
正常に処理を続けているのか」には答えられない——サイクル数はループ中も単調に増え続けるからである。

これに答えるには、実行中のレジスタとメモリを外部から観測する手段が要る。本書はこれを
2段階（低コストの即応策と、正式なデバッガ機能）に分けて提案する。

## 2. 根拠

### 2.1 実地で確認した欠落

本書と同じ調査で、稼働中の`nes2/mapper_check`のプロセスを`ps`で確認したところ、
`--scenario`実行はheartbeatフラグなしで動いており、監督していたAIの判断材料は
プロセス生死と壁時計比較だけだった。仮にheartbeatを付けていたとしても、サイクル数と経過時間
以上の情報は得られない。

### 2.2 部分的な機構は既に存在するが、届かない

`docs/HEADLESS_MACHINE_API.md`の`observe`操作は`machine` domainで両coreのPCとpark状態を
返却でき、`run_until`の`pc_equals`条件は実質的なbreakpointとして機能する。しかし
`--machine-api`は`--scenario`・`--stop-pc`・最終report出力と**併用できない**（同文書2節）。
つまり、実際に長時間soakする`--scenario`実行そのものからは、この機構に一切手が届かない。

### 2.3 レジスタ・メモリは「未知のハードウェア」ではない

このプロジェクトが実機traceや公式sourceを要求してきたのは、SDプロトコルのタイミング、
flashコントローラのopcode選択、keyboard controllerのFIFO仕様のような、**外部ハードウェアの
未文書化な挙動**を再現する場面だった（`AI_START_HERE.md`最上位原則）。

レジスタとSRAMはこれに該当しない。`crates/rp2040-emu/src/core/registers.rs`の
`Registers { r: [u32; 16], xpsr, primask, control, msp, psp }`は、エミュレーター自身が
毎命令のfetch/executeで読み書きしている、完全に既知のデータである。`memory.rs`のSRAM
264 KiBも同様に、エミュレーターが内部で保持する既存のバイト配列である。これらを外部へ
公開するのに、外部ハードウェアの謎を解く必要はない。**source不足を理由にこの機能を
見送ることはできない。**

### 2.4 実際に書かれている先送り理由

`crates/picoem-debug/src/lib.rs`（9行）:

```rust
//! picoem-debug — placeholder crate for the future GDB RSP server,
//! instruction trace, and DWT-driven tooling. Slated for Phase 4+ of the
//! HLD roadmap. ... intentionally has no implementation.
```

先送りの理由は「Phase 4+へ順序づけた」というスケジューリングであり、source不足ではない。
machine API v1のdomain一覧も、既存scenario engineが必要としていた範囲（§5「既存scenario
engineは...machine sessionのadvance／input／observation／snapshotを使う」）に合わせた
scope設定であり、これもsource不足が理由ではない。**「source不足」を理由にこの機能が
見送られた形跡はどこにもない。** ただし、実際に見送られている以上、対応する必要がある。

## 3. 提案する機能

### D0: heartbeatへのPC追加（低コスト・即応）

既存の`ProgressReporter`（heartbeat）に、両coreの現在PCを1行に追加する。

```text
[PICOCALC][RUN] event=heartbeat run=... seq=3 cycles=... pc0=0x1000abcd pc1=0x100012ec ...
```

- 既存heartbeat呼び出し箇所から`cores[0].regs.pc()`/`cores[1].regs.pc()`を読むだけで、
  新しいCLI option、protocol、実行mode変更を必要としない。
- `--scenario`実行（heartbeatが既定ONの`picocalc.py test --mode firmware`を含む）で
  そのまま使え、§2.2で指摘した「machine APIが届かない」問題を回避する。
- 連続するheartbeat行でPCが同じ値のまま停滞していれば、ファームウェアが特定アドレスに
  留まっている強い兆候になる（tight pollingか無限ループかは別途判断が要るが、少なくとも
  「前進しているように見えて実は同じ場所」を区別できる）。
- stderrのみ、決定性artifactに触れない。heartbeat自体の既存契約を変えない。

### D1: `observe`の`registers` domain

machine API（`--machine-api`）へ、両coreの完全なレジスタファイルを返すdomainを追加する。

```json
{"schema":1,"id":"r1","op":"observe","domains":["registers"]}
```

```json
{"core0":{"r":[...16個...],"xpsr":...,"primask":...,"control":...,"msp":...,"psp":...},
 "core1":{...}}
```

`registers.rs`の`Registers`構造体をそのままシリアライズするだけであり、新しいCPUモデルを
書き起こす必要はない。既存の`machine` domain（PCのみ）の上位互換として設計する。

### D2: メモリ読み取りop

境界を明示した範囲読み取りopを追加する。

```json
{"schema":1,"id":"r2","op":"read_memory","address":"0x20001000","length":256}
```

- 副作用のある読み取り（MMIOレジスタ、FIFO、ADCなど）は対象にしない。SRAM／XIP／ROMの
  範囲だけを許可し、それ以外は`unsupported_observation`として拒否する。
- 上限length（例: 4 KiB）を設け、無制限な一括ダンプを許可しない。
- 読み取りは`observe`と同じく副作用なしとする。

### D3: `--machine-api`と長時間実行の非併用を解消する

D0だけでは「PCが動いているか」しか分からず、「今どのレジスタ値か」「特定アドレスの値」は
見えない。D1/D2をscenario実行中に使うには、§2.2の非併用を解消する必要がある。二案あるが、
優劣は実装段階で検証する。

- **案A**: `--machine-api`を`--scenario`と併用可能にし、machine sessionがscenario engineを
  進めながら、外部からの`observe`/`read_memory` requestを合間に処理できるようにする。
  設計上の一方向依存（`docs/HEADLESS_MACHINE_API.md`§5の図）を壊さない範囲で検討する。
- **案B**: 実行中プロセスへの非同期signal（例: `SIGUSR1`）で、現在のレジスタ・PC・
  指定済みwatchアドレスのスナップショットを別fileへ書き出す、軽量な片方向の仕組みにする。
  プロトコル実装が小さく、決定性artifactへの影響が最も少ない。

### D4（別scope・大規模）: `picoem-debug`のGDB RSP実装

`arm-none-eabi-gdb`やLLDBが標準プロトコルで直接attachできるようにする、最も「正式」な
形。single-step、hardware/software breakpoint、レジスタ・メモリの読み書きが標準ツールで
行えるようになる。D0〜D3とは実装規模・複雑度が一段違うため、別の提案・別の工数見積りとして
切り離す。本書では「将来の到達点」として記録するに留める。

## 4. 意図的にscopeへ入れないもの（初版）

- レジスタ・メモリへの**書き込み**。観測専用に限定し、決定性への影響経路を作らない。
- MMIO領域の読み取り。副作用のある観測はunsupportedのまま明示する。
- D4（GDB RSP）本体の実装。別途起票する。
- 既存`observe`／`run_until`／heartbeatの出力形式・契約の変更。

## 5. 決定性への影響

D0〜D3はいずれも読み取り専用の観測である。report／verdict／UART／framebuffer／behavior
hashのいずれにも書き込まない。D0はheartbeat同様stderr限定、D1/D2はmachine APIの
既存response envelope内に収まる。既存のexactness gate（cycle、report、UART、framebuffer
digest比較）に触れない設計とする。

## 6. 優先度

D0は工数が小さく、今日直面した具体的な問題（PC不明のまま「時間だけで判断」する状況）に
即効性がある。D1/D2はmachine API利用者（今のところscenario engine自身のみ）を広げる。
D3は「非併用」という構造上の制約そのものを解く必要があり、設計判断を要する。D4は
別提案とする。

着手するならD0を最初に提案する。既存heartbeatの実装・試験・文書化パターン
（`docs/history/PICOCALC_RUN_PROGRESS_HEARTBEAT_REQUEST_20260813.md`）をそのまま踏襲でき、
工数も同程度に収まる見込みである。

## 7. 参考

- `crates/rp2040-emu/src/core/registers.rs`（`Registers`構造体）
- `crates/rp2040-emu/src/memory.rs`（SRAM/XIPバッキング）
- `docs/HEADLESS_MACHINE_API.md`（`observe`/`run_until`/実装境界）
- `crates/picoem-debug/src/lib.rs`（GDB RSP stub、9行）
- `docs/history/PICOCALC_RUN_PROGRESS_HEARTBEAT_REQUEST_20260813.md`（heartbeat、同種の実装パターン）
