# R4 品質ゲートとCI

R4は2026-08-06に完了した。目的は、3リポジトリの検証をclean GitHub runnerから実行し、
失敗した層をjob名で特定できる状態にすることである。target、attestation、過去evidenceを
都合よく書き換える作業ではない。

## Full gate

| repository | 固定commit | GitHub Actions run | 合格した層 |
|---|---|---|---|
| `picoem-picocalc` | `3bc6bbd7833e45fbf94d640eb7fbe056dd9fbd81` | `31098630797` | Rust test、release build、fmt、Clippy `-D warnings` |
| `picotetris` | `6cd16eb075120140d9073a72db665482f3c2fe95` | `31101591668` | 666 host checks、固定RP2040 BIN/UF2再現 |
| `picocalc_emu` | `f9b596fe01163d69f2396bb3d50aafb44965c825` | `31103564391` | portable、Python tools、target/schema、host、SDK 2.0互換build、固定firmware regression |

最後のfirmware jobは、同梱したR3 bundleのSHA-256を確認してPicoTetris source
`fed84f358d7dcadb1457752e687355ddb1875c48`を復元し、Pico SDK 2.2.0、ARM GCC 13.2.1、
CMake 3.28.3、Ninja 1.11.1、固定timestamp/identityからBINを再構築する。BIN
`0784d80d...e62`を直接照合してから、accepted backend `3bc6bbd...bd81`で
`picotetris-r4`を実行する。scenario 85/85、13 lines、score 1400、UART/framebuffer/report/
timelineを含むregistryの全条件に合格しなければjobは失敗する。

## `picocalc_emu`のjob境界

- `portable`: `verify_environment.py --scope core`。board header、source fingerprint、portable
  provenanceを検査する。
- `python-tools`: 生成器、CLI、異常系を含むPython unit test全件を実行する。
- `target-schema`: registry、JSON schema、versioned attestation、evidence SHAとfail-closed
  異常系を検査する。
- `host`: BSP host modelをbuildし、FAT32既定/FAT16明示を含むCTestと`emu_smoke`を3回実行する。
  stdout SHA-256も`84afb65d...b4b`へ固定する。
- `rp2040-compat`: 最低互換対象のPico SDK 2.0.0で標準templateをcompileする。
- `firmware-regression`: SDK 2.2.0の登録BINを再構築し、実RP2040 BINをfirmware backendで
  scenario実行する権威ある判定である。

ローカルで構造・host層まで確認する最小コマンドは次である。

```sh
python3 tools/verify_environment.py --scope core
python3 tools/verify_environment.py --scope target-schema
python3 -m unittest discover -s tests -v
python3 tools/picocalc.py test --mode host --repeat 3
```

固定firmware回帰の完全なbuild/実行コマンドは`.github/workflows/ci.yml`を正本とする。
ローカルではregistryが指定するcommitのclean backend checkoutを`--backend-dir`へ渡す。

### R5による現行firmware jobの更新

上のrun IDとR4成果物は時点証拠であり変更しない。R5 preflight後、現行
`firmware-regression`は旧R3 bundle/R4 targetから、独立した
`provenance/picotetris-r5.bundle`（SHA-256 `1187bccb...7a3`）、backend `612b485...f66`、
target `picotetris-r5`へ進めた。clean checkoutからR5 BIN/UF2の両SHAを照合し、自動周辺機器・
ゲーム診断と67キーscenarioを毎pushで実走する。旧R3/R4 target、bundle、attestationは履歴証拠
としてそのまま保持する。

## Private backendの認証境界

`GITHUB_TOKEN`は別private repositoryをcloneできないため、`picoem-picocalc`に
`picocalc_emu R4 firmware CI`という**読み取り専用deploy key**を一つ登録し、対応する秘密鍵を
`picocalc_emu`のActions secret `PICOEM_DEPLOY_KEY`に保存した。書き込み権限や個人PATは使わない。
workflowはclone後にHEADがaccepted commitと完全一致し、working treeがcleanであることを検査する。
鍵をrotationする場合も同じ名前・read-only境界を維持し、run全体を再実行する。

## R4に含めないもの

JUnit変換と100回連続firmware実行は未実装だが、R4の受入条件には含めない。R4では層別job、
host 3回バイト一致、PicoTetris build SHA、R3/R4で記録したfirmware 3回決定一致、毎pushの
権威あるfirmware 1回を組み合わせている。100回soakや別形式のreportが必要になった場合は、
所要時間と保存方針を定めた独立作業パッケージとして追加する。

R5の実装・emulator preflight・CI接続後、CIが再現したものと同一SHAの
`PicoTetris_R5.uf2`を実機へ書き込み、UART全文、参照音、67/67、最終PASS写真1枚を相関した。
結果は`firmware-validation/records/r5-hardware-20260808-01/`に保存し、R5を完了した。
