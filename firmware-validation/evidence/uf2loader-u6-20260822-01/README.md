# U6実uf2loader end-to-end証拠

作成日: 2026-08-22

このrecordは、外部`uf2loader`のclean source/buildと、cleanな
`picoem-picocalc` backendを使ったU6ローカルGateの結果です。GitHub Actionsは使用していません。
生成途中のraw flash／SD imageは保存せず、Gate manifestと各観測artifact、入力SHA-256を保存します。

## provenance

- backend commit: `d1360cbb13fd807661474b49a1b5516b12567d00`
- backend worktree: clean
- uf2loader source commit: `5c44a4b64749062b0200507ceeff3ef2b475e288`
- uf2loader source worktree: clean
- bootloader UF2 SHA-256: `209ed48bf9b91d51768386274a8d02bece157f1b889139cf7e2ebb560c92d40d`
- SD `BOOT2040.UF2` SHA-256: `3f1a096937d38de98f7b4eed2b1ceae1c34c789d8fcb1e3f529a1ee9fab5a25c`
- selected app UF2 SHA-256: `95efae84fddd9c5ff0cb64b20641418a4c9036b1217c78b578cc0cb9740dcbd6`
- scenario: `scenarios/uf2loader-u6-e2e.json`
- reattach scenario: `scenarios/uf2loader-u6-reattach.json`

`u6-gate.json`が機械判定の正典です。`run-01`〜`run-03`は同じ入力を別出力ディレクトリで実行し、
`reattach`はrun-01のflash exportを再attachしてアプリを起動した結果です。

## 実行したGate

```sh
python3 tools/picocalc.py uf2 e2e \
  --runner /path/to/picoem-picocalc/target/release/picocalc-run \
  --backend-dir /path/to/picoem-picocalc \
  --backend-commit d1360cbb13fd807661474b49a1b5516b12567d00 \
  --loader-source-dir /path/to/uf2loader/src \
  --loader-source-commit 5c44a4b64749062b0200507ceeff3ef2b475e288 \
  --bootloader-uf2 /path/to/bootloader_pico.uf2 \
  --loader-uf2 /path/to/BOOT2040.UF2 \
  --app-uf2 /path/to/lcd_hwspi_rgb565_expand.uf2 \
  --sd-dir /path/to/u6-sd-tree \
  --scenario scenarios/uf2loader-u6-e2e.json \
  --reattach-scenario scenarios/uf2loader-u6-reattach.json \
  --output ./u6-gate-output \
  --flash-end 0x101fc000 \
  --selected-path /pico1-apps/test.uf2 \
  --repetitions 3
```

## 受入結果

全条件が`u6-gate.json`で`true`または`pass`です。

- UF2 family／block count／block番号／payload範囲のstrict検査: pass
- boot2不変、loader領域（top 16 KiB）不変: pass
- flash erase/programのloaderモデルとのreadback一致: pass
- SD unknown command、flash unknown command、flash mutation error: 0
- watchdog warm reset: 各run 1回、epoch 1
- SD trace: 3 run同一、970 events、digest `bbbf1bf99d180a26fda0b8f470d70ef0af7bc8819e617b541bf044ac4f2bece3`
- report SHA: 3 run同一、`fa83ee1935728abab2543896c412491b1fa6e9ae512ec1e0f569d107199e0de9`
- UART SHA: 3 run同一、`1a1ff8de54237fae11773825e29d627dfd90a5473c5a6db4c924610e1089448b`
- framebuffer SHA: 3 run同一、`db449bc298f72dbd0a14ea9d482cf719622ac93782c17580a3ad6774f6f28c45`
- final flash SHA: 3 run同一、`853b9d711fe82364b88a59c756b43dfb3456eddc4328640d660c5912df434d0c`
- final flash再attach: pass、flash SHAとSD SHAを保持

この証拠は、cleanな外部loader sourceのこのcommit、RP2040向けclean build、2 MiB raw flash、
FAT32 snapshot、`pico1-apps/test.uf2`という**限定された実uf2loader経路**を支持します。
USB BOOTSEL/MSC、任意のUF2 family、任意のloader fork、ライブSD同期を意味しません。
