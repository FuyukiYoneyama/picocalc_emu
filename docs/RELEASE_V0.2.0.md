# picocalc_emu v0.2.0 — RP2040 SIO除算器修正版の公開

日付: 2026-10-12。両repoの注釈付き `v0.2.0` タグによる技術プレビューです。
両方の最終full SHAはGitHub Release notesの対応表に記載します。

## 対応表

| 項目 | この公開版 |
| --- | --- |
| picocalc_emu | `v0.2.0`（本記録を含むコミット） |
| picoem-picocalc | `v0.2.0` / `9503a58baeba47588037397855344168aa63e0ce` |
| 除算器の実装修正 | `d91f2bb7189b3a534cec01f8ae3670fd3a22297a` |
| Canonical BSP | `0.9.0`（標準機能の実機相関baselineは0.8.8） |
| firmware report schema | `8` |
| machine API | tagged backendでは未提供。schema 1は対応する過去の固定版で使用 |
| target registry schema | `3`。各targetの `backend.accepted` は従来どおり |
| 通常のpromoted PicoTetris backend | `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`（今回の除算器修正を含まない） |
| immutable hardware-correlated backend | `612b48510452d4012e4ac6639960ca3983b48f66` |

その他のtargetも[registry](../reference-projects/firmware-targets.json)の個別SHAを要求します。
この表の修正版を既存targetの `backend.accepted` へ代入してはいけません。
registry／capabilityの受入範囲は、この公開操作によって拡張していません。

## 不具合修正

Serial／ThreadedのRP2040 SIO除算器を修正しました。operandの全alias書き込みによる
再計算、最後のaliasによる符号選択、8cycleでのREADY、QUOTIENT読み出しだけでのDIRTY解除、
結果書き込みによる計算中断、coreごとの独立性、Threadedの状態引継ぎを確認済みです。

6144通りのレジスター計算と、固定Pico SDKの無変更assemblyによる64bit除算104呼び出しを
回帰確認しています。[修正記録](https://github.com/FuyukiYoneyama/picoem-picocalc/blob/v0.2.0/docs/rp2040_sio_divider_fix_20261012.md)
と[元の調査記録](RP2040_SIO_DIVIDER_BUG_20261012.md)を参照してください。

## v0.1.0からの移行

今回の公開内容には、SD image pack/extract、UF2補助tools、プレビュー経路、I2C外部モデルの
固定版受入記録、ユーザーガイド、保持証拠の検査など、前タグ以降の変更を含みます。
一方、backendは2026-09-11の旧基準版への復旧後に除算器を修正した構成です。
旧タグで提供していたmachine APIや追加audio解析等は、このbackendタグにはありません。
preview、heartbeat、SD／loader拡張、外部I2C等には、それぞれ対応する過去のbackend pinが必要です。

`v0.2.0` は後方互換なPATCHではなく、対応範囲の変更を含む技術プレビューです。
[0.y.zの版管理方針](VERSIONING.md)に従ってMINORを上げています。
report schema 8という番号だけで、すべての機能・CLI optionの互換性を推定しません。

## 除算器修正版を取得・実行する

```sh
git clone --branch v0.2.0 https://github.com/FuyukiYoneyama/picocalc_emu.git
git clone --branch v0.2.0 --recurse-submodules \
  https://github.com/FuyukiYoneyama/picoem-picocalc.git
cd picoem-picocalc
cargo build --locked --release -p picocalc-harness
target/release/picocalc-run \
  --bin /path/to/app.bin \
  --bootrom roms/rp2040/bootrom-rp2040-b2.bin \
  --board picocalc --lcd-variant pio-rgb565 --psram --sd --keyboard \
  --cycles 1000000 --quantum 1 \
  --uart /tmp/app-uart.log --json /tmp/app-report.json \
  --snapshot-dir /tmp/app-snapshots
```

新規BINの直接診断用です。受入条件を指定していないため通常は `cannot_judge`／終了2となります。
report、UART、snapshotを確認し、用途に応じたscenarioと受入条件を追加してください。
修正版を使うこの経路は、旧backendに固定された登録targetの正式な回帰合格を意味しません。
既存targetを再現する方法は[TESTING](../USER_GUIDE/TESTING.md)を参照してください。

## ローカル公開ゲート

| 確認 | 結果 |
| --- | --- |
| `python3 tools/picocalc.py verify` | 86/86合格 |
| `python3 -m unittest tests.test_tools` | 126合格 |
| board／harness／RP2040のCargo tests（doc testを含む） | 1382合格 |
| RP2040 threading/testing構成 | 1492合格 |
| release runner build、PicoCalcのfmt／厳格Clippy | 合格 |
| dividerの厳格Clippy、idle-profiler／behavior-trace構成のtests／Clippy | 合格 |

全ログ・command manifestは両GitHub Releaseの添付
`picocalc-v0.2.0-validation.tar.gz`に保存します。公開前には最終clean commitからの
再ビルド・backend identity確認と、タグの匿名fresh cloneでのportable検証も実施し、添付に記録します。
通常開発の検証としてGitHub Actionsを手動起動・再実行していません。

Pythonは3.9以降、Rust workspace minimumは1.88です。ローカル検証環境はPython 3.12.3、
Rust/Cargo 1.97.1、x86_64 Linuxです。生成／portable検証にはPico SDKは不要です。
RP2040アプリのビルドはSDK 2.0.0以降を対象とし、既存の再現可能targetはSDK 2.2.0
`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`、Arm GCC 13.2.1、CMake 3.28.3、Ninja 1.11.1等の
各target指定値を優先します。SDK除算fixtureはSDK 2.2.0／Arm GCC 13.2.1で生成済みで、
通常のCargo testsではSDK checkout不要です。

## 配布物と制限

backendでは旧基準版への復旧時に失われたv0.1.0のライセンス・帰属文書を復元し、
新しいSDK除算fixtureのBSD-3-Clause本文・provenance・NOTICEを追加しています。
既存の測定証拠とSHAは変更していません。公開repoからのcloneにはprivate依存は不要です。
歴史的アプリを再ビルドする場合は、対応する外部source／source bundleが別途必要です。

Serialはfirmwareの参照実行経路です。Threadedの除算器確認は全PicoCalc workloadの
同等性を保証しません。実時間1倍速・任意firmwareへの互換性は保証していません。
今回の公開で実機比較、ClockCalc再実行、新しいアプリ受入は実施していません。
公開済みの `v0.1.0` は変更せず、crate／BSP／schemaの番号はrepoタグとは独立して管理します。
