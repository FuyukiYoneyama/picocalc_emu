# 複数 `picocalc-run` 実行の運用

この文書は、複数の PicoCalc firmware run を同時に監視するための最小手順です。
heartbeat は進捗の診断情報であり、report、verdict、UART、framebuffer、audio、scenario の
合否やハッシュには入りません。

## まず守ること

各 run に別の run ID と出力ディレクトリを割り当てます。run ID だけではファイル衝突を防げないため、
`--json`、`--uart`、`--fb-png`、`--snapshot-dir`、`--audio-analysis`、`--audio-wav`、profiler／trace
出力を同じ path に向けてはいけません。

```sh
set -eu
root=/tmp/picocalc-runs
mkdir -p "$root/run-a" "$root/run-b"

python3 tools/picocalc.py test --mode firmware \
  --target <target-id> \
  --firmware /absolute/path/to/app.bin \
  --run-id run-a \
  --progress-interval 10 \
  --json "$root/run-a/report.json" \
  --uart "$root/run-a/uart.bin" \
  --snapshot-dir "$root/run-a/snapshots"
```

`picocalc.py test --mode firmware` は heartbeat を既定で有効にし、run ID を省略すると
`<target>-<wrapper-pid>` を生成します。再試行をまたいで同じ論理 run を追跡したい場合は、呼び出し側で
`--run-id` を明示します。`--no-progress` を指定すると runner へ heartbeat option を渡しません。
host mode ではこれらの option は拒否されます。

低レベル runner を直接呼ぶ場合は、次の2 optionを組で指定したときだけ heartbeat が有効です。

```sh
picocalc-run --run-id run-a --progress-interval 10 \
  --bin /absolute/path/to/app.bin \
  --json /tmp/picocalc-runs/run-a/report.json
```

同時実行数は host の CPU と memory に合わせます。並列実行中の wall time は性能測定に使いません。
各 process の memory-backed SD は独立しています。将来 RAW SD image を使う場合も、同じ image を
複数 writer が共有する運用は許可しません。

## heartbeat の読み方

観測行は stdout ではなく stderr に出ます。stdout は report または machine API の transport なので、
heartbeat を混ぜません。

```text
[PICOCALC][RUN] event=start run=run-a pid=12345 budget=1000000000
[PICOCALC][RUN] event=heartbeat run=run-a pid=12345 seq=1 cycles=123400000 budget=1000000000 pct=12.340 elapsed_s=10.002 rate_mcycles_s=12.338
[PICOCALC][RUN] event=finish run=run-a pid=12345 cycles=927528660 elapsed_s=25.382 stop=scenario_done exit=0
```

`event=start` は run の開始、`event=heartbeat` は best-effort の定期通知、`event=finish` は runner が
verdict を確定して終了したことを示します。指定秒数以内の厳密な発行は保証しません。stderr が閉じた
場合は heartbeat を停止しますが、firmware verdict は変更しません。

判定は次の順で行います。

1. まず対象 run ID の `event=finish` が存在するか確認する。
2. `finish` があれば、その `exit` と report/verdict を採用する。
3. process が終了したのに `finish` がなければ、正常完了とはみなさない。
4. POSIX の process 終了コードは補助信号として併用する。

runner 内部の exit code は `pass=0`、`fail=1`、`cannot_judge=2` で、`finish.exit` と一致します。
ただし `wsl.exe` 経由では外側の終了コードが 0 に見える場合があるため、AI の監督者は `finish` と
report を優先します。`SIGKILL`、host crash、電源断、fatal な引数／artifact 読込みエラーでは
`finish` が出ないことがあります。

## 停止と後片付け

run ごとの process を個別に停止し、出力ディレクトリを混ぜません。停止後に `finish` がなければ、
report の有無、stderr、OS の process 状態を調べ、`cannot_judge` 相当として再現条件を記録します。
同じ出力 path を使った再実行で証拠を上書きしないでください。

この機能は daemon、socket、中央 registry、自動 directory 管理を提供しません。長寿命の対話操作は
[Headless machine API](HEADLESS_MACHINE_API.md)を使いますが、初版 heartbeat と machine API は併用できません。
