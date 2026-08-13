# 複数runの監視

複数のfirmware runを同時に動かすときは、**runごとに一意なIDと専用出力directory**を割り当てます。
同じartifact pathを共有しないことが最重要です。

次の例は2つのfirmware processを実際にbackground起動し、各processを別の出力directoryへ
分離して終了コードを回収します。`backend`、`runner`、`bootrom`、`bin`、`scenario`は
実際の絶対pathへ置き換えてください。fresh cloneからのbackend準備は
[`SCENARIOS.md`](SCENARIOS.md)の手順を使います。

```sh
set -u
root=/tmp/picocalc-runs
backend=/absolute/path/to/picoem-picocalc
runner="$backend/target/release/picocalc-run"
bootrom="$backend/roms/rp2040/bootrom-rp2040-b2.bin"
bin=/absolute/path/to/app.bin
scenario=/absolute/path/to/scenario.json
mkdir -p "$root/run-a/snapshots" "$root/run-b/snapshots"
test -x "$runner"
test -f "$bootrom"
test -f "$bin"
test -f "$scenario"

"$runner" --bin "$bin" --bootrom "$bootrom" \
  --board picocalc --lcd-variant pio-rgb565 --keyboard \
  --scenario "$scenario" --run-id run-a --progress-interval 10 \
  --snapshot-dir "$root/run-a/snapshots" \
  --uart "$root/run-a/uart.bin" --json "$root/run-a/report.json" \
  2>"$root/run-a/stderr.log" &
pid_a=$!

"$runner" --bin "$bin" --bootrom "$bootrom" \
  --board picocalc --lcd-variant pio-rgb565 --keyboard \
  --scenario "$scenario" --run-id run-b --progress-interval 10 \
  --snapshot-dir "$root/run-b/snapshots" \
  --uart "$root/run-b/uart.bin" --json "$root/run-b/report.json" \
  2>"$root/run-b/stderr.log" &
pid_b=$!

wait "$pid_a"; rc_a=$?
wait "$pid_b"; rc_b=$?
printf 'run-a pid=%s exit=%s\n' "$pid_a" "$rc_a"
printf 'run-b pid=%s exit=%s\n' "$pid_b" "$rc_b"
```

この例では`$pid_a`と`$pid_b`が設定された時点で2 processが並行実行されています。
片方の`wait`がfailureでももう片方の終了結果を回収するため、`set -e`は使いません。
両方の`stderr.log`、report、UART、snapshotをrun IDごとに確認してください。

登録済みtargetの正式なwrapper判定を並列に行う場合は、上のrunner直接実行を
[`TESTING.md`](TESTING.md)の`picocalc.py test --mode firmware`へ置き換えます。その場合も
target registryに固定されたBINと`backend.accepted` commitを使い、runごとに`--json`、`--uart`、
`--snapshot-dir`を分離してください。

`--json`、`--uart`、`--snapshot-dir`、`--fb-png`、audio／profiler／trace出力をrun間で共有しません。
memory-backed SDもprocessごとに独立しています。同じraw imageを複数writerで共有する運用は許可しません。

## heartbeat

`picocalc.py test --mode firmware`はheartbeatを既定で有効にします。run IDを省略すると
`<target>-<wrapper-pid>`が生成されます。再試行を同じ論理runとして追跡する場合だけ、`--run-id`を明示します。

低レベルrunnerを直接呼ぶ場合は、次の2 optionを組で指定します。

```sh
picocalc-run --run-id run-a --progress-interval 10 \
  --bin /absolute/path/to/app.bin --json /tmp/picocalc-runs/run-a/report.json
```

heartbeatはstderrだけに出ます。stdoutはreportまたはmachine APIのtransportです。

```text
[PICOCALC][RUN] event=start run=run-a pid=12345 budget=1000000000
[PICOCALC][RUN] event=heartbeat run=run-a pid=12345 seq=1 cycles=123400000 pct=12.340 elapsed_s=10.002
[PICOCALC][RUN] event=finish run=run-a pid=12345 cycles=927528660 stop=scenario_done exit=0
```

## 判定順序

1. 対象runの`event=finish`があるか確認します。
2. `finish`があれば`finish.exit`とreport／verdictを採用します。
3. processが終了したのに`finish`がなければ、正常完了とみなしません。
4. process終了コードは補助信号です。WSL／`wsl.exe`経由では外側が0に見える場合があります。

`finish`なし、SIGKILL、crash、電源断は`cannot judge`相当として再現条件を記録します。
並列実行中の壁時計は性能測定に使いません。

既定heartbeatを止める場合だけ`--no-progress`を使います。machine APIとの併用はできません。
詳細なrunner仕様は[`../docs/CONCURRENT_RUNS.md`](../docs/CONCURRENT_RUNS.md)にありますが、通常運用では
この文書を正本として扱えます。
