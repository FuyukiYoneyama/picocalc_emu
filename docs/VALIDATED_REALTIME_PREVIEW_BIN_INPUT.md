# Validated Realtime Preview: firmware input format

Status: Normative clarification  
Date: 2026-08-28

この文書は [`VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md`](VALIDATED_REALTIME_PREVIEW_PROPOSAL_20260828.md) の firmware artifact 入力形式を明確化する。

## 結論

Validated Realtime Preview が実際に起動する対象は **Pico SDK が生成した raw `*.bin`** に固定する。

```text
source
  |
  v
build
  |
  +--> application.bin   <- Firmware backend / Preview の実行対象
  |
  +--> application.uf2   <- 実機への転送用 artifact
```

P0/P1 では Firmware backend が PASS した **同一 `*.bin`** を Validated Realtime Preview でも実行する。

`*.uf2` を preview の入力形式にはしない。UF2 は同一 build から生成される実機転送用 artifact として保持するが、preview の admission gate や direct-boot input の基準にはしない。

## identity / gate

preview の firmware identity は raw BIN の SHA-256 を正典とする。

- validation 時に実際に実行した `*.bin` の SHA-256 を記録する
- preview 起動時にディスク上の `*.bin` を再 SHA-256 して一致を確認する
- `Ctrl+R` reload 時も同じ `*.bin` SHA-256 gate を再実行する
- BIN が 1 byte でも変われば preview は拒否し、新しい BIN を Firmware backend に通してから preview する

```text
Firmware backend PASS: application.bin (sha256=A)
                           |
                           v
Preview input:             application.bin (sha256=A) -> allowed
Preview input:             application.bin (sha256=B) -> refused
```

## UF2 の位置付け

`*.uf2` は削除しない。同一 build の実機配布・転送 artifact として引き続き生成してよい。

ただし Validated Realtime Preview の仕様上は次を固定する。

- preview は UF2 を直接 boot しない
- preview gate は UF2 hash を要求しない
- UF2 の direct-loader 実装を P0/P1 の前提にしない
- Firmware backend / preview の実行 payload は raw BIN とする
- 実機最終確認時に必要なら同一 build の UF2 を使用する

この分離により、現在の `picoem-picocalc` の raw BIN direct-boot 実装と一致し、preview の artifact identity も単純な same-BIN contract として維持できる。
