# 検証：host backendとfirmware backend

## 使い分け

| 経路 | 速さ | 分かること | 分からないこと |
|---|---:|---|---|
| host | 高速 | アプリロジック、framebuffer、keyboard、PSRAM、filesystemの基本 | PIO、DMA、I2C transaction、interrupt、multicore、LCD wire形式 |
| firmware | hostより低速 | raw BINのRP2040実行、PIO、DMA、GPIO、I2C、interrupt、LCD、SD、keyboard、multicoreの固定範囲 | 対応範囲外の機能、実機の見え方・聞こえ方・物理操作 |
| HIL | 実機依存 | 実RP2040の起動、実クロック、実UART、実リセット、実loader／flash経路、実ペリフェラル初期化 | UARTに出していない内部状態、画面の見え方、音の聴感、物理操作 |

firmware backendがhardware挙動の権威です。ただし、対応範囲を推測で広げず、
[`capability.json`](../firmware-validation/capability.json)のsupported／unsupportedを確認してください。

firmware backendの合格後、プロジェクトに安全なHIL runnerがある場合は、同じapplication
artifactを実機で起動し、UART marker・リセット・周辺機器初期化を確認します。HILはfirmware
backendを置き換えず、実シリコンと実基板でのみ見える差を補完します。runnerの既定動作は
flashを書き換えないものとし、loader保護されたartifactの明示的な書き込みだけを別途許可します。
詳細は[`HARDWARE_IN_THE_LOOP.md`](../docs/HARDWARE_IN_THE_LOOP.md)を参照してください。

## portable検証

```sh
python3 tools/picocalc.py verify
```

参照repositoryまで固定commitで照合する場合だけ、次を使います。

```sh
python3 tools/picocalc.py verify --references --strict-commit
```

## host検証

```sh
python3 tools/picocalc.py test --mode host
```

必要なら`--build-dir`、`--repeat`、`--json`を追加できます。hostの合格はfirmwareの合格を
意味しません。

## firmware検証：登録済みtarget

登録済みtargetはBIN SHA、scenario SHA、backend commit、device構成、期待UART／停止条件を固定しています。
対象BINとtargetの組を変えずに実行します。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target <target-id> \
  --firmware /absolute/path/to/picocalc_app.bin \
  --backend-dir /absolute/path/to/picoem-picocalc \
  --snapshot-dir /tmp/picocalc-snapshots
```

この経路はtarget registryのpinを検査します。backendの`main`や別commitを勝手に使わないでください。
必要なtargetと`backend.accepted`は[`firmware-targets.json`](../reference-projects/firmware-targets.json)にあります。
登録targetと一致しない新規BINは、このコマンドでは合格になりません。

### accepted backend checkoutを作る

target registryの`backend.accepted`を`<accepted-commit>`へ置き換え、backendのmainを直接使わずに
detached worktreeを作ります。

```sh
backend_source=/absolute/path/to/picoem-picocalc
backend_target=/tmp/picoem-target-<target-id>
accepted=<accepted-commit>
git -C "$backend_source" fetch --all --tags
git -C "$backend_source" worktree add --detach "$backend_target" "$accepted"
(cd "$backend_target" && cargo build --locked --release -p picocalc-harness)
git -C "$backend_target" status --porcelain --untracked-files=no
```

最後の`git status`は空でなければなりません。以後の`--backend-dir`には
`$backend_target`を指定します。target registryが要求するcommitを省略したり、別commitで
「動いたからよい」と判断したりしません。

wrapperはheartbeatを既定で出します。長い実行を複数同時に監視する方法は
[`CONCURRENT_RUNS.md`](CONCURRENT_RUNS.md)を参照してください。

### この経路を使ってよい条件

`--target`のtarget registryに、実行するBINのSHA-256とscenarioのSHA-256が登録されている場合だけ
使います。新規アプリのBINをこのコマンドへ渡して「target-idだけ合わせる」ことは禁止です。
SHAが違えばfailureになるのが正しい動作です。

## firmware検証：新規BINを直接実行

新規アプリをまだtarget registryへ登録していない段階では、backend runnerを直接使います。
これは動作観察用であり、登録targetのfail-closed回帰判定、release evidence、hardware correlationを
置き換えません。直接runnerが`pass`を返しても、registry targetの正式合格とは記録しません。

```sh
backend=/absolute/path/to/picoem-picocalc
(cd "$backend" && cargo build --release -p picocalc-harness)
"$backend/target/release/picocalc-run" \
  --bin /absolute/path/to/MyApp/build/picocalc_app.bin \
  --bootrom "$backend/roms/rp2040/bootrom-rp2040-b2.bin" \
  --board picocalc \
  --lcd-variant pio-rgb565 \
  --psram --sd --sd-format fat32 --keyboard \
  --json /tmp/myapp-report.json \
  --snapshot-dir /tmp/myapp-snapshots
```

firmware runnerはraw BINを実行します。UF2／ELFを直接渡しません。終了コードは`0=pass`、
`1=judged failure`、`2=cannot judge`です。`report.json`の`verdict`、UART、snapshotをセットで確認し、
古いreportを再利用しないでください。

## 固定targetへ追加する場合

新しいアプリを正式な回帰targetにする場合は、BIN／scenario／backend commit／toolchain／受入条件を
新しいtarget revisionとして固定します。過去recordを書き換えません。target registryの詳細設計を読む必要が
あるときだけ[`VERSIONED_VALIDATION.md`](../docs/VERSIONED_VALIDATION.md)を参照してください。

## CIの扱い

通常のbuild、test、lint、validationはローカルで行います。GitHub Actionsをデバッグ用途に使ったり、
pushして結果を確認する反復を行ったりしません。CI workflowを変更する場合は、先に使用量と必要性を判断します。
