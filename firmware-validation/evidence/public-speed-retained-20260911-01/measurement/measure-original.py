#!/usr/bin/env python3
"""Measure the clean restored public commit; retain every run before validation."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import benchmark_firmware_realtime as benchmark

PUBLIC = '32d27ff4179a993ae9fac6ff4a1d5e8999570fa9'
ANCHOR = 'e985a9d7ecb51ef760506a105edd34e31cf9b5f1'

def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', type=Path, required=True)
    p.add_argument('--runner', type=Path, required=True)
    p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.backend, a.runner, a.firmware, a.output = [x.resolve() for x in (a.backend, a.runner, a.firmware, a.output)]
    assert not a.output.exists(), 'output must be new; never overwrite evidence'
    assert git(a.backend, 'rev-parse', 'HEAD') == PUBLIC
    assert not git(a.backend, 'status', '--porcelain', '--untracked-files=no')
    tree = git(a.backend, 'rev-parse', 'HEAD^{tree}')
    assert tree == git(a.backend, 'rev-parse', ANCHOR + '^{tree}')
    target = benchmark.picocalc.load_firmware_target('picotetris-opt1b')
    sha = benchmark.sha256_file
    assert sha(a.firmware) == target['artifacts']['bin_sha256']
    scenario = ROOT / target['scenario']['path']
    assert sha(scenario) == target['scenario']['sha256']
    bootrom = a.backend / 'roms/rp2040/bootrom-rp2040-b2.bin'
    assert sha(bootrom) == '9c19b46f068c21f90d200c514faad4a0d5cecfc978f155b8c9d25cb6bc2efd81'
    affinity = sorted(os.sched_getaffinity(0))
    assert 11 in affinity
    a.output.mkdir(parents=True)
    save(a.output / 'manifest.json', {
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_commit': PUBLIC, 'source_tree': tree, 'anchor_commit': ANCHOR,
        'source_dirty': False, 'instrumentation_patch': None,
        'runner_sha256': sha(a.runner), 'firmware_sha256': sha(a.firmware),
        'scenario_sha256': sha(scenario), 'bootrom_sha256': sha(bootrom),
        'platform': platform.platform(), 'cpu': benchmark.host_cpu(),
        'affinity_before': affinity, 'measurement_cpu': 11,
        'target': target, 'measurement_script_sha256': sha(Path(__file__)),
        'method': 'perf_counter_ns around subprocess.run; includes startup and output writes; excludes build and validation',
        'cpu_method': 'RUSAGE_CHILDREN user+system delta; whole process, not run_loop',
        'warmup_runs': 1, 'measured_runs': 3,
        'definition': '100 * report.elapsed_us / 1e6 / wall_seconds',
        'validation': 'Require actual public clean identity; substitute anchor identity only in a copy for historical normalized-report comparison',
    })
    os.sched_setaffinity(0, {11})
    command_target = copy.deepcopy(target)
    command_target['backend']['accepted'] = PUBLIC
    measured = []
    for index in range(4):
        name = 'warmup' if index == 0 else 'run-%03d' % index
        out = a.output / name
        (out / 'snapshots').mkdir(parents=True)
        command = benchmark.target_command(command_target, a.firmware, a.runner, out / 'report.json', out / 'uart.bin', out / 'snapshots')
        command += ['--bootrom', str(bootrom)]
        save(out / 'invocation.json', {'argv': command, 'cwd': str(a.backend), 'affinity': sorted(os.sched_getaffinity(0))})
        print(name, flush=True)
        with (out / 'stdout.log').open('xb') as stdout, (out / 'stderr.log').open('xb') as stderr:
            cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
            started = time.perf_counter_ns()
            result = subprocess.run(command, cwd=a.backend, stdout=stdout, stderr=stderr)
            wall_ns = time.perf_counter_ns() - started
            cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        timing = {'exit_code': result.returncode, 'wall_ns': wall_ns, 'wall_seconds': wall_ns / 1e9,
                  'process_cpu_seconds': cpu_after.ru_utime + cpu_after.ru_stime - cpu_before.ru_utime - cpu_before.ru_stime}
        save(out / 'timing.json', timing)
        assert result.returncode == 0, 'failed run retained'
        report = json.loads((out / 'report.json').read_text())
        assert report['backend_build'] == {'commit': PUBLIC, 'dirty': False}
        comparison = copy.deepcopy(report)
        comparison['backend_build']['commit'] = ANCHOR
        benchmark.validate_report(target, sha(a.firmware), comparison)
        assert sha(out / 'uart.bin') == report['uart']['sha256']
        png_hash = sha(out / 'snapshots/tetris-line-clear.png')
        assert png_hash == 'e3a90df645eba0bb11eb642190dea5dda9928394cf4aa7880c7a552d815d4958'
        row = dict(timing, run=name, elapsed_us=report['elapsed_us'], cycles=report['cycles'],
                   real_time_percent=report['elapsed_us'] / 1e6 / timing['wall_seconds'] * 100,
                   report_sha256=sha(out / 'report.json'), uart_sha256=sha(out / 'uart.bin'), png_sha256=png_hash)
        save(out / 'validation.json', dict(row, historical_contract_pass=True, actual_public_identity_pass=True))
        if index:
            measured.append(row)
        print(json.dumps(row), flush=True)
    assert len({r['report_sha256'] for r in measured}) == 1
    save(a.output / 'summary.json', {'runs': measured, 'all_reports_identical': True,
        'real_time_percent': benchmark.summarize([r['real_time_percent'] for r in measured]),
        'wall_seconds': benchmark.summarize([r['wall_seconds'] for r in measured])})

if __name__ == '__main__':
    main()
