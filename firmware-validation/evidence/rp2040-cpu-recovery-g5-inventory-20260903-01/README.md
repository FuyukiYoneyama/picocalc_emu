# G5（保存領域・起動経路：flash・SD・boot）棚卸し

## 状態

**棚卸し完了 / 実装未着手**。

G4（ヘッドレス実行基盤）candidateの次に戻す機能を、現在のtarget registry、supported capability、
既存のversioned evidence、backend履歴から分類した。ここではproduction code、backend `main`、target
registry、外部project、実機を変更していない。

## マクロな位置づけ

この作業は、約14%で動いていた高速Serial起点から、現在公開している保存領域と起動経路を段階的に
取り戻す性能退行復旧・再構築計画R2のG5である。目的はflash／SD／boot機能を一括復元することではなく、
各機能を使う利用者と既存受入記録を対応づけ、必要な機能だけを一群ずつ移植してTetris（軽ゲーム実装）
の速度退行をその場で検出できるようにすることだ。1倍速、LOAD-0（最大級の継続負荷性能テスト0番）、
特定倍率のqualificationはG5の目的ではない。

## 現在の契約から分かったこと

- registryはschema 3、target 22件、active 21件、pending-revalidation 1件である。
- active targetのうち18件がSDをattachする。したがって通常のSD attach／direct boot回帰は、少数の
  loader専用試験ではなく、現在の利用経路の基礎である。
- active targetで`boot_mode=boot2`を宣言するものは0件である。boot2／watchdog warm resetは、
  固定外部`uf2loader`のbounded capabilityを支える明示的なconformance経路であり、通常app起動へ
  暗黙に追加してはならない。
- supported capabilityには`raw-sd-image`、`directory-snapshot-import`、`flash-erase-program`、
  `uf2loader-e2e`、`sd-multi-block`がある。これらはG5で維持対象だが、完全なSD互換、USB BOOTSEL/MSC、
  任意UF2、live directory syncを意味しない。
- `vrp-nes0-synthetic-nrom`はpending-revalidationであり、sourceに`Picocalc_NESco`と非公開branchを
  含む。これは既存の歴史資料として参照するだけで、G5のactive target、実装根拠、外部branch作成、
  新規公開物には使わない。

registry SHA-256は`7b83c7ef0befc812e2b4cb3bba227096185f11b67ff1235a01b6953acfc7d14b`、capability SHA-256は
`63a56d5e3b4eecdb57f74122f3e9bdf70e400f46ba53c1b3071762f8f519fc29`である。棚卸し時点のvalidation repo
commitはG4記録を固定した`d7b9364`である。

## G5の機能群と移植条件

| 順序 | 表示名 | 主な利用者・契約 | 移植する候補 | Tetris（軽ゲーム実装）での状態 | 合格しない限り次へ進まない条件 |
|---|---|---|---|---|---|
| G5-A | 保存領域基盤（RAW SD・NOR flash mutation） | `raw-sd-image`、`directory-snapshot-import`、`flash-chip-commands`、`flash-erase-program` | file-backed SD、COW overlay／atomic export、NOR erase/program／XIP readback、path安全検査、必要なSD command CRC | 通常短scenarioではRAW export／flash mutationはinactive。SD attachはactive | raw input／outputの安全境界、flash 1→0、XIP readback、既存direct bootが一致しない場合停止 |
| G5-B | loader起動（boot2・watchdog warm reset） | 固定`uf2loader-e2e`のboot2→stage3→SD→flash→warm reset | 明示`--boot-mode boot2`、stage3 handoff、scratch／reset reason、flash／SD backing保持、MCU-side state reset | 通常Tetris／PicoEditではinactive。既定app起動へ追加しない | boot2専用unit、既存U6の固定artifact／trace回帰、再attachと最終flash SHAが一致しない場合停止 |
| G5-C | SD protocol（bounded multiblock） | `sd-multi-block`、SD-GEN-1-P5、SDを使う代表runtime | CMD18/CMD12/CMD23/CMD25、token／CRC／CS／busy、protocol error report、default feature、3回E2E | Tetris短scenarioでは通常multi-blockがinactive。SD capability testでactive | synthetic E2E 3回、既存single-block、RAW export、negative mutationが一致しない場合停止 |

G5-A〜Cの候補を一つの大きなcherry-pickへしない。各群は、対象test、Tetris（軽ゲーム実装）短probe、
必要な代表targetを順に通し、常時costまたは未説明のguest-visible差が出た群で止める。

## 履歴と依存関係

次のcommitは候補の出典であり、無条件のcherry-pick順ではない。必要部分を現行G4 candidateへ再実装
または部分適用する。

| 機能群 | 履歴commit | 内容 | 注意 |
|---|---|---|---|
| G5-A | `ae49c6c090dbd26c08c8360821cc6b2cc2c66dbe`、`749ba884f78a37a6c2c7adece341ef7068e16e49`、`5edca80ae3cd9f73d381399628a7cc1ab801bdf3` | RAW SD／XIP flash mutation、RAW export path hardening、mandatory SD CRC | flash／SDのstorageとwire parserを混ぜず、Tetris inactive時の常時costを確認する |
| G5-B | `d1360cbb13fd807661474b49a1b5516b12567d00` | UF2 loader boot2 entry、watchdog warm reset、再入場 | boot2は明示opt-inのみ。real bootrom／USB MSCは対象外 |
| G5-C | `0e1288e4c516b7da3ad21f3cf1ec3532374ab8da`、`f6cd89dda7e8bcaf2cdc23d574a1794067f7c302`、`84162a3171c19f76271674b612e4c47c1631c051`、`0126d1bd08495fa157cd038b68465937a74f7abe`、`b0a4c05bb53ae043a70cf531bd7413849f494bcf`、`4ee4d1df20a69f023b9697fd51fb28d3a7723f88`、`e805f1c1752eb2e6e0a26e68db4e330a08e4a9d2` | bounded SD multiblock、protocol report、default promotion、legacy boundary、3回回帰 | feature／default境界を確認し、既存single-blockとSD-GEN-1 recordを上書きしない |

現在のG4 candidateと高速起点との差分には、`sdcard.rs`、`sd_wire.rs`、`ssi_flash.rs`、
`watchdog_tick.rs`、`picoem-common/src/memory.rs`のG5 storage／boot実装は含まれていない。G4で追加した
`rp2040-emu/src/lib.rs`の差分はCPU／scheduler側の復旧であり、boot2復元済みとは扱わない。

## 既存recordの扱い

| 既存資料 | G5での役割 | 書き換え |
|---|---|---|
| `sd-gen1-p5-20260823-01` | bounded `sd-multi-block`の契約、3回determinism、negative境界 | しない |
| `sd-gen1-p4-20260823-01` | default runtimeのsynthetic CMD18／CMD12／CMD23／CMD25／CMD17 E2EとRAW export | しない。候補で再実行する |
| `uf2loader-u6-20260822-01` | 固定外部loaderのboot2→SD→flash→warm resetの既存受入 | しない。外部sourceを改変・branch公開しない |
| `vrp-nes0-synthetic-nrom-20260829-01` | flash／SD mutationの歴史的境界 | pendingのまま保持し、G5の新targetにしない |

G5の実行証拠は、新しいrecovery evidenceとして保存する。既存recordを現行G5 candidateのbackend pinへ
書き換えない。

## 開始条件と未実装範囲

G5-Aを開始できる条件は、G4 candidate `f2d4d527...`がcleanで、G4記録のmachine API／heartbeatが
再現可能であり、上表のG5-A対象testを明示できることである。この条件は満たしている。次に行うのは
G5-Aの必要差分の移植と、raw storage／flash mutation unit test、Tetris短screeningである。

まだ行わないことは次のとおりである。

- `Picocalc_NESco`または`uf2loader`のsource改変、branch作成、公開。
- USB BOOTSEL/MSC、実RP2040 bootrom全体、card removal、write-protect、live directory sync。
- 既存targetのregistry revision更新、既存recordの書換え、性能baselineの更新。
- 1倍速、LOAD-0、長時間平均を合否条件にすること。

## 次の作業

次はG5-A（保存領域基盤：RAW SD／NOR flash mutation）の必要部分だけをG4 candidateへ移植する。
移植後に対象unit／integration testとTetris（軽ゲーム実装）短screeningを1回行い、未説明のguest-visible
差または通常実行への常時costがあれば、G5-Bへ進まず再設計する。
