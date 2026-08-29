# VRP-NES-0 外部依存の是正 — レビュー助言

作成日: 2026-08-29
起票: Sol（レビュワー）
対象: `docs/VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md` および
      `docs/VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md`
状態: **採用済み。正典計画と状態案内へ反映済み。`VRP-LOAD-0`の実装・測定は未実施。**

## 0. この文書の位置づけ

これは新しい作業計画ではなく、既存VRP計画の**誤った前提を取り除くための助言**である。
採否は所有者が決める。助言の内容は、この計画自身が別の箇所で既に確立している原則を、
適用し忘れている箇所へ適用し直すことに尽きる。

## 1. 何が問題か

VRP-5の正式な`realtime-1x-qualified`判定は、`picotetris-opt1b`と**NES-class workload**の
2つを要求している。しかしその実現手段として、外部プロジェクト`Picocalc_NESco`のローカル
診断branch（`codex/mnesco-extension`）が使われ、そのbranchを公開しない限りtargetが
`pending-revalidation`から動けない状態になっている。

これには3つの独立した問題がある。

### 1.1 「なぜNESか」が計画のどこにも書かれていない

提案書の該当箇所は次の通りで、循環論法になっている。

> registryには現在NES-class targetが存在しない**ため**、NES-class workloadは`VRP-NES-0`として
> 別途再配布可能なtarget/fixtureを準備する。

他の受入条件（device 6項目、10分連続、audio fidelity target）はいずれも理由が明記されている
のに対し、**NES-classという要求だけ根拠が空白である**。「NESでなければ満たせない性質」が
一度も定義されていない。

### 1.2 外部プロジェクトを改変し、その改変版を受入証拠にしようとしている

`main..codex/mnesco-extension`の差分は**778行の追加**で、内容は次の通りである。

```
platform/mnesco_oracle.cpp   258行（新規）
platform/test_oracle.cpp     204行（新規）
platform/core1_worker.c       56行
platform/test_oracle.h        35行
platform/mnesco_oracle.h      20行
...
```

commit messageが性格を示している。

```
Add diagnostic NES test oracle
Add diagnostic NES oracle progress heartbeat
Observe protected SRAM writes in test oracle
Add M-NESCO extension diagnostics
```

**これらはすべて、こちらのemulatorを検証するための計測コードである。** NESco本体の機能改善
ではなく、NEScoの利用者にとって価値がない。この改変版branchを公開しなければtargetが成立
しない、という構造になっている。

### 1.3 同一リポジトリ内に、正しい前例が既に存在する

`docs/UF2LOADER_SD_FLASH_IMPLEMENTATION_PLAN_20260813.md`は、GPL-3.0の外部プロジェクト
`uf2loader`をworkloadに使うにあたり、次を明文化している。

> `uf2loader`本体、生成UF2、ゲームデータはMITの`picocalc_emu`へ**vendorしない**。公開
> repositoryには自作の小さなfixture、プロトコルテスト、**外部sourceのcommit/SHAと再現手順
> だけ**を置く。GPL成果物を必要とするend-to-end検証は、**利用者が別途取得した外部checkout
> を明示指定するoptional conformance**とする。

さらに、改変の扱いについても明確である。

> 現在のローカルcheckoutには`ui/text_directory_ui.c`の未コミット変更がある。これは
> **調査用に限り、正式な受入証拠には使わない**。受入時は同commitの**clean checkout**と、
> 固定したSDK/toolchainから再ビルドする。

**「調査のために外部を改変することはある。しかし改変版を受入証拠にはしない」** という原則が
既に確立され、U6はこの形で実際に完走している。VRP-NES-0はこの原則の適用を失念している。

## 2. 是正の方針

次の順序で判断する。§2.1で解決すれば、§2.2以降は不要になる。

### 2.1 【採用】要求を「NES」から「負荷プロファイル」へ書き換える

VRP-5が本当に必要としているのは、**最悪ケース負荷でも1倍が出るかを示すworkload**である。
`picoedit-r1`（テキスト編集、部分描画、音声なし）では軽すぎて1倍の証明にならない、という
のが実質的な理由と考えられる。これはNESという意味論ではなく、負荷特性の要求である。

本プロジェクトの実測（`docs/history/OPT2_D_LEVER_COMPARISON.md`）では、実行中サイクルの
**70.25%をPIOが占める**。すなわち支配的なのは全画面LCD転送であり、NESエミュレータで
なければ再現できない性質ではない。

**要求仕様（NESという語を使わずに定義する）:**

- 320×320 RGB565の**全画面**を固定レートで連続更新し続ける
- 同時に音声を連続ストリーミングする（既存の48 kHz DMA-paced audio経路を使用）
- CPUを継続的に負荷し、idle fast-forwardが効かない状態を作る
- 10分以上連続で決定的に動作する
- **リポジトリ所有のsourceからclean cloneで再ビルドできる**

この作業には新規技術を要さない。`templates/rp2040-basic`、SD-GEN-1の合成firmware fixture、
`picocalc-audio-r1`の48 kHz DMA音声、`picocalc-multicore-r2`のcore 1運用という実績が
すべて既存であり、公開BSP APIの組み合わせで構成できる。工数は現行`VRP-NES-0`の10〜20時間と
同等か、NESエミュレータの挙動理解が不要な分だけ軽い見込みである。

**この方式の利点:**

1. 外部依存が正式qualificationの依存グラフから消え、歴史的targetが`pending-revalidation`でもVRP-5へ進める
2. 負荷を**設計できる**ため、qualificationの意味が明確になる。NESの実装がたまたま軽い／
   重いことによる曖昧さがない
3. clean cloneから誰でも再現でき、versioned targetの要件を完全に満たす（現行のNESco依存
   では原理的に達成できない）
4. 他プロジェクトを改変・公開しない

### 2.2 それでもNESで検証したい場合 — uf2loader方式に従う

NES workload自体に固有の価値を認めるなら、§1.3の前例をそのまま適用する。

- 使用するのは`Picocalc_NESco`の**無改変のclean checkout**（現在の公開`main`）
- `picocalc_emu`が保持するのはcommit SHAと再現手順のみ。sourceもBINもvendorしない
- 利用者が別途checkoutを取得して指定する**optional conformance**として扱う
- **診断branchは受入証拠に使わない**

この場合、診断オラクルなしで観測できる範囲へ受入条件を縮小する必要がある。縮小できない
なら§2.3の問題に突き当たる。

### 2.3 診断オラクルが必要だった理由を問い直す

778行の観測コードを**外部プロジェクトへ埋め込まないと検証できない**のであれば、それは
emulator側の観測能力の不足を示している。ゲスト側にoracleを実装させる構造そのものが、
本プロジェクトの「推測でハードウェア層を再実装しない／観測はemulatorが行う」という姿勢と
整合しない。

この論点は、既に起票済みの
[`docs/history/MACHINE_API_DEBUG_OBSERVABILITY_REQUEST_20260813.md`](history/MACHINE_API_DEBUG_OBSERVABILITY_REQUEST_20260813.md)
（レジスタ／メモリ観測の欠落）と同根である。emulator側にwatch機能があれば、ゲストへ
oracleを埋め込む必要はなかった可能性が高い。

§2.1を採る場合、この論点は1倍qualificationのblockerではなくなるが、**別課題として残る**
ことを記録しておくべきである。

## 3. 反映した修正箇所

§2.1を採用したため、次を修正した。

| 文書 | 修正内容 |
|---|---|
| `VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md` 受入条件11 | 「`VRP-NES-0`で固定したNES-class workload」→ §2.1の負荷プロファイルで定義したworkloadへ。**なぜその負荷が必要かの理由を必ず併記する** |
| 同 §workload選定 | NES-classへの言及を削除し、負荷特性の要求として書き直す |
| `VALIDATED_REALTIME_PREVIEW_IMPLEMENTATION_PLAN_20260828.md` §VRP-NES-0 | `VRP-LOAD-0`へ改称。要求仕様を§2.1へ差し替え。NESへの言及を削除 |
| 同 §9 完成の定義 | `realtime-1x-qualified`の前提targetを差し替え |
| 同 §6 進捗表 | `VRP-NES-0`を`VRP-LOAD-0`へ置換し、既存証拠は歴史資料として計画本文に残す |
| 同 §4.2／NESco境界節 | 「所有者提供待ち」→「**NES-class依存を撤回したため不要**」へ。外部プロジェクトを改変・公開しない原則の記述自体は残す |
| `MILESTONES.md`、`IMPLEMENTATION_STATUS.md`、`README.md`、`AI_START_HERE.md`、`docs/README.md` | 上記に合わせて状態記述を更新 |

## 4. 既存成果の扱い

`firmware-validation/evidence/vrp-nes0-synthetic-nrom-20260829-01/`は**破棄しない**。

このevidenceが実際に示したのは、synthetic NROMとFAT32経路を通じてSD→flash→XIPが動作し、
`source_region=xip`、`core1_xip=pass`、`dma_xip=pass`が3回byte-identicalに再現したこと
である。これはM-NESCO経路の正当な時点証拠であり、その価値は失われない。

**時点証拠として保持し、VRP-5の1倍qualification要件からは外す。** 計画書・状態案内・fixture／
scenario案内へ、NES-class依存が撤回された経緯と、この証拠が何を示し何を示さないかを追記する。
証拠ディレクトリ内の既存ファイルは不変のまま保持する。

repository-owned synthetic NROM fixture
（`firmware-validation/fixtures/vrp-nes0-synthetic-nrom/`）も自作物なので保持してよい。

## 5. 採用した決定

- §2.1の負荷プロファイル化を採用し、`VRP-LOAD-0`をVRP-5正式qualificationの前提とする。
- §2.2は将来NES固有の適合性を確認する場合のoptional conformanceとして保持する。ただし未改変の
  公開clean refまたは再現可能なartifactだけを使い、改変branchを正式証拠にしない。
- §2.3のemulator側観測能力は、1倍qualificationのblockerではなく別課題として記録する。
- 既存`VRP-NES-0` fixture／target／evidenceは削除せず、`historical / non-qualifying`として保持する。

したがって、本書は選択肢の提示だけでなく、採用された計画修正のdecision recordでもある。

## 6. レビュワーとしての記録

`VRP-NES-0`を独立パッケージとして切り出す修正は、レビュワー（Sol）が
「registryにNES-class targetが存在しない」という工数・順序の指摘を行った結果として
導入された。その際、**「では何を使ってNES-class targetを作るのか」「その入手元は誰の管理下
か」を確認しなかった**ことが、本件の外部依存を見逃した直接の原因である。

同一セッション内でuf2loaderの前例（外部プロジェクトを改変せず、改変版を証拠にしない）を
読んでいたにもかかわらず、NES-class要求へ同じ基準を適用しなかった。

**今後、外部リソースを要求する作業項目については、次を必ず確認する。**

1. その入手元は誰の管理下にあるか
2. こちらの変更を伴うか。伴うならその変更を証拠として公開する必要が生じないか
3. 同種の前例が既にリポジトリ内にないか
