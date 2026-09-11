# 公開版速度の再測定・証拠保全

対象は公開mainの32d27ff4179a993ae9fac6ff4a1d5e8999570fa9そのもの。
旧e985a9dの代用実行ではなく、計測patchなし・clean release build。
検証repoの基点は857e2cb7c6f51dcc85a0493d8d352492acb6efe3。

## 条件

固定picotetris-opt1b、PIO RGB565、PSRAM、keyboard、SD FAT32、quantum 1、
cycle上限8000000000、CPU affinity 11。warmup 1回、本測定3回を直列実行。
計時は既存benchmark_firmware_realtime.pyと同じperf_counter_nsによる
runnerプロセス全体。起動・出力を含み、buildと検証は含まない。
CPU時間は補助値としてRUSAGE_CHILDRENで取得する。run_loopのCPU時計とは別物。
失敗・warmupを含め各回の原本を保持し、既存出力への上書きを拒否する。

## 再現

既存workspaceルールを確認し、単一の/tmp作業領域に以下を作る。
BACKEND_REPOとVALIDATION_REPOとFIRMWARE_REPOは各ローカルrepoの絶対パス。
結果の保存先OUTPUTは新規の永続保存先を指定する。

```bash
TASK_DIR=$(mktemp -d /tmp/picoem-evidence-XXXXXX)
git -C "$BACKEND_REPO" worktree add --detach "$TASK_DIR/backend" 32d27ff4179a993ae9fac6ff4a1d5e8999570fa9
git -C "$FIRMWARE_REPO" worktree add --detach "$TASK_DIR/firmware" fed84f358d7dcadb1457752e687355ddb1875c48
(cd "$TASK_DIR/backend" && CARGO_TARGET_DIR="$TASK_DIR/target" cargo build --locked --release -p picocalc-harness --bin picocalc-run)
python3 "$VALIDATION_REPO/tools/picocalc.py" build --project "$TASK_DIR/firmware" --sdk /home/fuyuki/pico/pico-sdk --picotool-dir /usr/local/lib/cmake/picotool --lcd-variant pio-rgb565 --jobs 2 --build-timestamp 2026-08-06T00:00:00Z --generator Ninja
python3 "$VALIDATION_REPO/firmware-validation/evidence/public-speed-retained-20260911-01/measure.py" --backend "$TASK_DIR/backend" --runner "$TASK_DIR/target/release/picocalc-run" --firmware "$TASK_DIR/firmware/build/PicoTetris.bin" --output "$OUTPUT"
```

今回のbuildではRUSTFLAGS、CARGO_ENCODED_RUSTFLAGS、CARGO_BUILD_TARGET、
CARGO_PROFILE_RELEASE_OPT_LEVEL、CARGO_PROFILE_RELEASE_LTOは未設定。
SDK commitはa1438dff1d38bd9c65dbd693f0e5db4b9ae91779。
buildログ、firmware build history、Cargo.lock、feature tree、Rust/Cargo版を同梱。
binaries/には実際に実行したrunnerとBINを保持する。

## 検証の扱い

レポート原本のbackend_build.commitとbackend_commitを公開commitと照合し、dirty=falseを要求。
旧登録レポートのnormalized hashと比較する際に限り、メモリ内のコピーの両commit欄を
e985a9dへ置換する。それ以外のフィールドは変更せず、既存のvalidate_reportを適用。
原本は書き換えない。UART実ファイルとPNGも既存hashへ照合する。

measurement/は初回の検証script不備で停止した系列。FAILURE.mdと旧scriptも保全。
measurement-v2/は修正後の独立系列。前回会話の13.76%や14.91%の原本を復元したものではない。

証拠directoryで`sha256sum -c SHA256SUMS`を実行して保全ファイルを検査する。
結果・証拠のGit保全確認が済むまで一時領域を削除しない。
