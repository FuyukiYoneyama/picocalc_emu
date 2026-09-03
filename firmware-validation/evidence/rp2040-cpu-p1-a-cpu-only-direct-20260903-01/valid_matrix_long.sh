#!/usr/bin/env bash
set -u

root=/tmp/picocalc-rp2040-cpu-p1a-direct.7AoYCt
out="$root/valid-runs-1b"
cycles=1000000000
pairs=10
mkdir -p "$out"
printf 'kind\tpair\tarm\tstart\tend\tstatus\tlog\n' > "$out/metadata.tsv"

run_arm() {
    local kind=$1 pair=$2 arm=$3 bin=$4
    local log="$out/${kind}-${pair}-${arm}.log"
    local start end status
    start=$(date --iso-8601=seconds)
    taskset -c 11 "$bin" \
        --workload self-invalidate --unpaced --model serial \
        --cycles "$cycles" --reps 1 --core 11 \
        --quantum 125 --clock-mhz 125 --step-quantum 256 \
        >"$log" 2>&1
    status=$?
    end=$(date --iso-8601=seconds)
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$kind" "$pair" "$arm" "$start" "$end" "$status" "$log" \
        >> "$out/metadata.tsv"
    if [ "$status" -ne 0 ]; then
        printf 'failed %s/%s/%s status=%s\n' "$kind" "$pair" "$arm" "$status" >&2
        exit "$status"
    fi
}

run_arm warmup 0 baseline "$root/target-baseline-self/release/paced_bench_rp2040"
sleep 1
run_arm warmup 0 candidate "$root/target-candidate-self/release/paced_bench_rp2040"

for pair in $(seq 1 "$pairs"); do
    if [ $((pair % 2)) -eq 1 ]; then
        run_arm pair "$pair" baseline "$root/target-baseline-self/release/paced_bench_rp2040"
        sleep 1
        run_arm pair "$pair" candidate "$root/target-candidate-self/release/paced_bench_rp2040"
    else
        run_arm pair "$pair" candidate "$root/target-candidate-self/release/paced_bench_rp2040"
        sleep 1
        run_arm pair "$pair" baseline "$root/target-baseline-self/release/paced_bench_rp2040"
    fi
    sleep 1
done

date --iso-8601=seconds > "$out/COMPLETE"
