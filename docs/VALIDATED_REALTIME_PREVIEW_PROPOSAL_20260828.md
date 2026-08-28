# 確実版通過後の 1× 簡略版エミュレーター提案

Status: Proposal  
Date: 2026-08-28

## 1. 目的

`picocalc_emu` に、**確実版の Firmware backend で合格したソースだけを対象に、実時間 1× で人間が画面・入力・音・待ち時間を確認する簡略版エミュレーター**を追加する。

この層の目的はハードウェア互換性の判定ではない。目的は、すでに確実版で互換性を確認したソースについて、次のような UX を低コストで確認することである。

- 起動から最初の画面までの待ち時間
- メニュー遷移のテンポ
- キー押下、長押し、離したときの反応
- アニメーションやゲーム進行の体感速度
- 画面更新の見え方
- 音の開始・停止・テンポの概略
- リセット、再起動、再読込を含む反復確認

本提案では、この層を **Validated Realtime Preview**（以下 `validated-preview`）と呼ぶ。

## 2. 最重要原則

### 2.1 順序を逆転させない

開発フローは必ず次の順序とする。

```text
source
  |
  v
Firmware backend（確実版）
  |
  | PASS
  v
validated source snapshot
  |
  v
validated-preview（簡略版、1×、対話操作）
  |
  v
UX確認
  |
  v
必要なら実機最終確認
```

`validated-preview` は、確実版の代わりにはならない。

```text
Firmware backend PASS -> validated-preview
```

は正しいが、

```text
validated-preview PASS -> hardware compatible
```

という推論は禁止する。

### 2.2 簡略版は「検証器」ではなく「表示・操作器」

既存の [`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md) が定義する Firmware backend は、PIO、DMA、GPIO、interrupt、multicore など binary / hardware 固有挙動を検証する正確性側の backend であり、`ExecutionModel::Serial` を正確性基準としている。

`validated-preview` は、その責務を持たない。

簡略版で省略、近似、最適化を行ってもよいのは、**その実行対象が先に確実版を通過していることを機械的に確認できる場合だけ**とする。

### 2.3 ソース変更時は確実版へ戻る

一度確実版を通過した後でも、対象ソースに変更が入った時点で preview の資格を失う。

```text
source A -> firmware PASS -> preview OK
source A'                    -> preview NG
source A' -> firmware PASS -> preview OK
```

空白やコメントだけの変更を特別扱いするかは初期実装では判断しない。最初は安全側に倒し、検証対象スナップショットと一致しなければ再検証を要求する。

## 3. 現在の構成との整合

既存の要求仕様は、Host App mode と Firmware mode を分離し、Firmware mode で RP2040 と PicoCalc device model を通した実行を行う方針を持つ。 [`REQUIREMENTS.md`](../REQUIREMENTS.md)

現在の Firmware backend は [`FIRMWARE_BACKEND.md`](FIRMWARE_BACKEND.md) に定義され、raw Pico SDK BIN を direct boot し、同じ build から作られる UF2 と実行 payload を共有する。登録 target の実行では schema 8 report、backend/source identity、artifact hash、device arguments、期待結果を fail-closed で判定する。

また `picoem-picocalc` 自体には wall-clock real-time pacing の実装がある。このため、最初の実装では新しい RP2040 emulator core を作る必要はない。

本提案は既存の二層を置き換えず、次の三層に役割を明確化する。

| 層 | 主目的 | 正確性の権限 | 速度 |
|---|---|---|---|
| Host backend | アプリロジック、UI、file処理の高速反復 | なし | 最速 |
| Firmware backend | RP2040 / PicoCalc 固有挙動の合否判定 | **あり** | 任意 |
| validated-preview | 確実版通過済みソースの人間向け UX 確認 | **なし** | 実時間 1× |

## 4. 実働アプリから見える必要条件

今回の PicoCalc NES 実装は、UX に関係する処理がハードウェア機能と密接に結びつく例になっている。

- `CMakeLists.txt` は PIO、PWM、DMA、IRQ、SPI、I2C、multicore をリンクしている。
- `picocalc_nes.cpp` は core0 / core1 を分け、PPU 側で 16,666 us 単位の VSync 待ちを行う。
- 同ファイルは PWM audio と DMA buffer を使って継続再生する。
- `common.cpp` / `i2ckbd.cpp` は I2C keyboard の press / release を読み、入力状態へ反映する。
- `boot_menu.cpp` はキー入力待ちと画面更新を組み合わせて ROM 選択 UI を構成する。
- `picocalc.cpp` は PIO、DMA、LCD command、reset 待ちを含む表示経路を持つ。

したがって、UX preview を単なる「最終 framebuffer の表示」にしてはいけない。少なくとも**時間の進行、画面更新、キー down/up、音の進行**は連続したセッションとして扱う必要がある。

一方、これらの PIO/DMA/I2C/SPI の wire-level 正確性を preview 側で再度保証する必要はない。そこは先行する Firmware backend の役割である。

## 5. 検証済みソースの受け渡し

### 5.1 Validation receipt

`validated-preview` は、単に「ユーザーが PASS 済みと言った」だけでは起動しない。

Firmware backend の成功結果から、preview 用の `validation receipt` を作成する。

概念例:

```json
{
  "schema": 1,
  "status": "validated",
  "source": {
    "git_commit": "<commit>",
    "dirty": false,
    "tree_identity": "<source snapshot identity>"
  },
  "firmware": {
    "sha256": "<validated BIN sha256>",
    "target": "<firmware target id>"
  },
  "validation": {
    "report": "<schema 8 report path>",
    "verdict": "pass",
    "backend_commit": "<accepted backend commit>"
  }
}
```

フィールド名と snapshot identity の方式は実装時に固定する。重要なのは、**preview が確実版 PASS と同じソーススナップショットを参照していることを確認できること**である。

### 5.2 初期実装では同一 BIN を使ってもよい

最初の段階では、最も安全な実装として、確実版が PASS した **同一 BIN** を realtime UI で動かす方式を採用できる。

この場合は schema 8 report が持つ artifact hash をそのまま gate に利用しやすい。

その後、速度または対話性の理由で source-level / host-assisted な簡略実行へ進む場合に、source snapshot identity を gate として追加する。

この順番にすれば、簡略版そのものを先に大規模実装せずに UX loop の価値を検証できる。

## 6. validated-preview の実行契約

### 6.1 起動条件

preview は次の条件をすべて満たす場合だけ起動する。

1. 対応する Firmware backend report が `pass`
2. report が accepted target / backend identity を満たす
3. preview 対象の source または BIN が receipt と一致する
4. receipt より後に対象 source が変更されていない

一致しない場合は、自動で無視して起動するのではなく、明示的に拒否する。

例:

```text
validated-preview refused
reason: source snapshot differs from validated receipt
next: run firmware validation again
```

### 6.2 表示する状態

window または UI 上に最低限、次を表示する。

```text
Validated Realtime Preview
Source: validated
Speed: 1.000x target
Hardware verdict: NOT PROVIDED BY THIS MODE
```

「Validated」は preview 自身が検証したという意味ではなく、**入口の source snapshot が確実版を通過済み**という意味に限定する。

### 6.3 1× の意味

`1×` は、実機の全電気的タイミングを再現する意味ではない。

この mode での `1×` は、アプリから見える時間進行を wall clock に合わせ、次を人間が体感比較できる状態を意味する。

- firmware delay
- frame pacing
- menu wait
- animation interval
- key repeat / hold の時間進行
- audio stream の進行

初期実装では固定 `1.000x target` とし、0.5×、2×、turbo などの速度変更は入れない。速度変更機能を入れると UX 確認という目的が曖昧になるためである。

実時間追従の数値受入幅は、現在の backend と代表 workload の baseline を測定した後に固定する。提案段階で根拠のない許容値は決めない。

## 7. 対話 UI

最小 UI は次でよい。

- PicoCalc LCD を表示
- PC keyboard から PicoCalc keyboard event を入力
- key down / key up を保持
- reset
- reload
- screenshot
- quit

概念 CLI:

```sh
python3 tools/picocalc.py preview \
  --receipt artifacts/validation-receipt.json \
  --backend-dir ../picoem-picocalc
```

または初期段階では、同一 BIN を明示する。

```sh
python3 tools/picocalc.py preview \
  --validated-report artifacts/firmware-report.json \
  --firmware build/picocalc_app.bin \
  --backend-dir ../picoem-picocalc
```

UI shortcut の例:

```text
F5       reset
Ctrl+R   reload validated artifact
F12      screenshot
Esc      quit
```

アプリ固有 key profile を持てるようにする。今回の NES consumer では矢印、`-`、`=`、`[`、`]` が方向、Select、Start、B、A に対応しており、preview adapter はこの種の consumer mapping を壊さず key press / release を渡せる必要がある。

## 8. 簡略版で保持するもの / 捨ててよいもの

### 保持するもの

UX に直接効くため、原則として保持する。

- wall-clock pacing
- firmware / app の delay
- LCD framebuffer の時系列更新
- keyboard down / up / hold
- reset / reboot の見え方
- audio stream の時間進行
- SD 読込待ちが UX に現れる場合の時間進行

### preview から外してよいもの

確実版で検証済みであり、preview 自身は verdict を持たないため、初期実装では外してよい。

- deterministic scenario assertion
- UART marker による合否判定
- pixel / region hash assertion
- trace の完全採取
- unsupported MMIO による preview verdict
- evidence package 生成
- CI 用 fail-closed 判定
- backend promotion 判定
- hardware correlation 記録
- exhaustive diagnostics

ただし、簡略化によって画面・入力・時間進行そのものが変わる場合は、その簡略化は UX preview の目的を壊すので採用しない。

## 9. 実装方針

### Phase P0: thin realtime frontend

最初は `picoem-picocalc` の既存 RP2040 / PicoCalc device path と wall-clock pacer を使い、対話 window と keyboard frontend だけを追加する。

目的:

- 新しい emulator core を作らない
- 既存の correctness asset を最大限再利用する
- 1× UX loop が実際に有用かを最短で確認する
- 代表 workload で realtime が維持できるか測定する

P0 では「簡略版」というより、確実版から verdict / evidence / scenario の重い責務を外した preview frontend に近い。

### Phase P1: validation receipt gate

Firmware backend PASS と preview 対象を機械的に結び付ける。

- validated BIN hash
- target
- backend identity
- report verdict
- source snapshot identity

を receipt に固定し、mismatch 時は preview 起動を拒否する。

### Phase P2: 必要な場合だけ実行を簡略化

P0 の計測で、通常の代表 workload が 1× を安定維持できない場合にのみ、preview 専用の簡略化を行う。

候補は、正確性モデルを無差別に削るのではなく、実測 profiler で支配的な箇所を限定して最適化する。

重要な順序は次である。

```text
まず既存 core で 1× を測る
  -> 足りる: 新しい簡略 core は作らない
  -> 足りない: bottleneck を測る
  -> UX に影響しない範囲だけ簡略化
```

「簡略版を作ること」自体を目的にしない。

## 10. 受け入れ条件

最初の完成条件を次とする。

1. Firmware backend PASS がない source / artifact では preview を起動できない
2. PASS 後に source / artifact を変更すると preview gate が拒否する
3. 代表アプリで LCD を連続表示できる
4. key down / key up を対話入力できる
5. reset と reload ができる
6. wall-clock 1× target で連続実行でき、実測比率を観測できる
7. scenario / trace / evidence を要求しなくても UX セッションを開始できる
8. preview の結果から hardware compatibility の PASS を生成しない
9. Firmware backend の既存 schema 8 verdict、target registry、promotion policy を変更しない
10. 代表 workload の実測後にのみ realtime 許容幅を固定する

## 11. 非目標

この提案では次を目標にしない。

- preview 単体による実機互換性保証
- Firmware backend の置換
- `ExecutionModel::Serial` の正確性基準の変更
- arbitrary UF2 の直接 boot 実装
- USB BOOTSEL / MSC の再現
- speaker / enclosure / physical volume を含む実音響再現
- 物理キーの押し心地の再現
- LCD の物理的な色、残像、視野角の再現
- preview を CI の authoritative verdict にすること

## 12. 開発ループの最終形

本提案を採用した場合、通常のアプリ開発は次の形になる。

```text
AI / developer edits source
        |
        v
host test
        |
        v
build
        |
        v
Firmware backend authoritative validation
        |
        | PASS + validation receipt
        v
Validated Realtime Preview (1× interactive)
        |
        v
human / AI-assisted UX inspection
        |
        v
必要なら hardware final check
```

ここで重要なのは、**簡略版が確実版の前に来ないこと**である。

確実版は「この source / artifact を PicoCalc hardware model 上で信頼してよいか」を判定し、簡略版は「その検証済み内容を人間が 1× で触ったときに UX として成立しているか」を見る。

この一方向の責務分離を守れば、preview 側は将来かなり大胆に高速化・簡略化しても、Firmware backend が持つ互換性保証の意味を壊さずに済む。
