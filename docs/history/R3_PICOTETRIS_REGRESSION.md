# R3 PicoTetris正式回帰

> **資料区分: 歴史記録。** この文書の「次は」「未着手」「予定」は作成時点の判断です。
> 現在状態は `../IMPLEMENTATION_STATUS.md`、現在計画は `../MILESTONES.md` を優先します。


R3は2026-08-06に完了した。対象はR3完了時点でremoteを意図的に持たない`picotetris`と、
`picocalc_emu`のhost/firmware検査基盤である。機械可読なtargetは
`reference-projects/firmware-targets.json`の`picotetris-r3`、実測記録は
`firmware-validation/records/r3-20260806-01/report.json`、再取得用の完全履歴は
`provenance/picotetris-r3.bundle`に固定した。

R4のclean-clone CI準備として、R3完了後の2026-08-06にprivate GitHub repository
`FuyukiYoneyama/picotetris`を追加した。R3 manifestの`remote: null`とbundleは、当時の
復旧契約を示す時点証拠なので変更しない。

```sh
git clone -b main provenance/picotetris-r3.bundle /tmp/picotetris-r3
git -C /tmp/picotetris-r3 checkout --detach fed84f358d7dcadb1457752e687355ddb1875c48
```

## Host logic

ゲーム規則と状態を`include/picotetris/game.h`・`src/game.cpp`へ分離し、BSPを使う描画と
I/Oだけを`app/main.cpp`へ残した。gravity tickもgame stateへ移し、game-over後の`R` restartで
盤面・score・lines・乱数・tickがすべて初期化される。

```sh
cmake -S tests -B <fresh-host-build>
cmake --build <fresh-host-build>
ctest --test-dir <fresh-host-build> --output-on-failure
```

666 checksは、7形状×4回転のgolden座標、全形状・回転の左右端・床・占有セル衝突、回転、
I pieceの壁蹴りと全候補blocked、1〜4ラインと100/300/500/800点、固定seedの40-piece列と
reset再現、game-over、`R` restart、gravity周期を検査する。Pico SDKやBSPはリンクしない。

## 固定build

source commit `fed84f358d7dcadb1457752e687355ddb1875c48`を別々のclean cloneへcheckoutし、
Pico SDK 2.2.0、arm-none-eabi GCC 13.2.1、CMake 3.28.3、Ninja 1.11.1、Release、
PIO/RGB565、UTC timestamp `2026-08-06T00:00:00Z`で2回buildした。

| artifact | 結果 |
|---|---|
| BIN | `0784d80d0d00c9bf86d06e903234bc022db5bda2ff193e17533c65b9c2546e62`、byte-identical |
| UF2 | `44ec62270175aac16add07ca8d7c99abb0942bcff341c4c36c0d884fc857e274`、byte-identical |
| ELF | `31e9e9aa...a76f0` / `47f51d1e...1caff`、不一致 |

ELFは異なる絶対build pathを保持するため、path非依存再現性を主張しない。配布payloadである
BINとUF2は一致する。両build historyは`app_git=fed84f358d7d`、
`bsp_git=cbfc90467e2b`、dirtyなしを記録した。

## Firmware scenario 3回

backendはclean commit `0d434d789ed2aa0743520eb0d411fa2ced1974e4`、report schema 8、
Serial execution、PIO/RGB565、PSRAMあり、keyboardあり、SD FAT32、quantum 1で固定した。

```sh
python3 tools/picocalc.py test --mode firmware \
  --target picotetris-r3 \
  --firmware <PicoTetris.bin> \
  --backend-dir <picoem-picocalc> \
  --snapshot-dir <fresh-snapshot-dir> \
  --uart <uart.log> \
  --json <report.json>
```

3回すべて85/85 steps、13 lines、score 1400、927,528,660 cycles、仮想3,715 ms、
key delivered 362 / remaining 0 / dropped 0、exception/errorなし、unsupported MMIO 0、
unknown keyboard register 0、unknown SD command 0で合格した。
各回のraw report・UART byte stream・snapshot PNGは`records/r3-20260806-01/runs/run-{1,2,3}/`
に保存し、portable verifierが以下のSHAを実ファイルから再計算して3回相互一致も検査する。

| 比較対象 | 3回共通SHA-256 |
|---|---|
| UART | `bff1f2452ee65a2279a805c828a6c3afc75bb238fd1859f43962f8e1f6e9266c` |
| 最終/途中snapshot RGB565 | `f63b598fb0e00e2e0ab0b39d0304ef341a4a30393b77f41d56e534945054e4a2` |
| snapshot PNG | `e3a90df645eba0bb11eb642190dea5dda9928394cf4aa7880c7a552d815d4958` |
| raw report | `2c005ef05fecab56343aae75fd9f4fb2b1a83fe89a36d2d264d63a7029554730` |
| 正規化report | `eca38c789523f25429b64eed29de77adcde0d60f18537803f79cc1e6e1232b10` |
| 85-step timeline | `50eb1f6c7382b9c5d4f7764b8825a7aa641bbb744433899c6d644108e6be2dd1` |

正規化reportはJSON全体をkey昇順・compact UTF-8・末尾改行へ変換したもの、timelineは同じ
正規化を`.scenario.steps`へ適用したものとする。この実装ではraw reportもbyte-identicalで、
正規化によって不一致を隠してはいない。両SHAはtargetのacceptanceへ固定し、以後の
`picocalc.py test --mode firmware`でも構造化fieldに加えて直接照合する。固定後の実target
再受入も合格した。

## 境界と次工程

R3はゲーム規則、固定build、firmware統合の継続回帰契約を完成させた。実機での正しさは
まだ主張しない。R3完了時点の次工程は、R4でclean cloneからunit/build/backend/registry/
firmware regressionをCIの品質ゲートへ接続し、R5でこの同一BIN SHAを実機相関することだった。

> **R4追記（2026-08-06）:** PicoTetris commit `6cd16eb075120140d9073a72db665482f3c2fe95`
> でunit testと固定RP2040再現buildをGitHub Actionsへ接続した。run `31101591668`で666
> checksと、上記BIN/UF2 SHAのclean runner上での完全一致を確認した。続いて`picocalc_emu`
> run `31103564391`で同じBINの再構築と権威あるfirmware regressionを含む全6 jobが合格した。
> 3リポジトリfull gateを完了し、次はR5でこの同一BINを実機相関する。

> **R5追記（2026-08-08）:** R3の時点証拠は変更せず、後続の単一R5 artifactをemulatorと
> PicoCalc実機で相関した。LCD、PSRAM、FAT32、audio、PicoTetris、keyboard 67/67が一致し、
> `r5-hardware-20260808-01`へ証拠を固定した。
