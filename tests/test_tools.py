import json
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from provenance import directory_sha256


ROOT = Path(__file__).resolve().parents[1]
PICOCALC = ROOT / "tools/picocalc.py"
VERIFY = ROOT / "tools/verify_environment.py"
GENERATE_BOARD = ROOT / "tools/generate_board_header.py"
BENCHMARK_REALTIME = ROOT / "tools/benchmark_firmware_realtime.py"
NEXT2_AUDIO_ORACLE = ROOT / "tools/next2_audio_oracle.py"
NEXT2_AUDIO_ORACLE_V3 = ROOT / "tools/next2_audio_oracle_v3.py"
NEXT2_AUDIO_NEGATIVE = ROOT / "tools/verify_next2_audio_negative.py"


def run(*arguments, env=None):
    return subprocess.run(
        [sys.executable, *map(str, arguments)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )


class ToolTests(unittest.TestCase):
    def load_picocalc_module(self):
        specification = importlib.util.spec_from_file_location("picocalc_r2", PICOCALC)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module

    def load_realtime_benchmark_module(self):
        specification = importlib.util.spec_from_file_location(
            "benchmark_firmware_realtime", BENCHMARK_REALTIME
        )
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module

    def test_realtime_benchmark_statistics_and_target_command(self):
        module = self.load_realtime_benchmark_module()
        summary = module.summarize([1.0, 2.0, 3.0])
        self.assertEqual(summary["mean"], 2.0)
        self.assertEqual(summary["median"], 2.0)
        self.assertEqual(summary["sample_stddev"], 1.0)
        self.assertEqual(summary["minimum"], 1.0)
        self.assertEqual(summary["maximum"], 3.0)
        self.assertLess(summary["mean_ci95"][0], 2.0)
        self.assertGreater(summary["mean_ci95"][1], 2.0)

        target = self.load_picocalc_module().load_firmware_target("picotetris-r4")
        command = module.target_command(
            target,
            Path("firmware.bin"),
            Path("picocalc-run"),
            Path("report.json"),
            Path("uart.bin"),
            Path("snapshots"),
        )
        self.assertEqual(command[0], "picocalc-run")
        self.assertIn("--quantum", command)
        self.assertEqual(command[command.index("--quantum") + 1], "1")
        self.assertIn("--psram", command)
        self.assertIn("--keyboard", command)
        self.assertIn("--sd", command)
        self.assertIn("--scenario", command)

    def test_normalized_json_sha256_is_order_independent_and_utf8(self):
        module = self.load_picocalc_module()
        left = {"z": [2, 1], "a": {"日本語": True}}
        right = {"a": {"日本語": True}, "z": [2, 1]}
        self.assertEqual(
            module.normalized_json_sha256(left),
            module.normalized_json_sha256(right),
        )
        expected = hashlib.sha256(
            '{"a":{"日本語":true},"z":[2,1]}\n'.encode("utf-8")
        ).hexdigest()
        self.assertEqual(module.normalized_json_sha256(left), expected)

    def test_target_contract_hash_excludes_only_validation_attestation(self):
        module = self.load_picocalc_module()
        target = {
            "id": "fixture",
            "revision": 1,
            "backend": {"accepted": "a" * 40},
            "validation": {"record": "first.json", "sha256": "b" * 64},
        }
        original = module.firmware_target_contract_sha256(target)
        target["validation"] = {"record": "second.json", "sha256": "c" * 64}
        self.assertEqual(module.firmware_target_contract_sha256(target), original)
        target["backend"]["accepted"] = "d" * 40
        self.assertNotEqual(module.firmware_target_contract_sha256(target), original)

    def make_firmware_fixture(self, temporary, with_scenario=True):
        root = Path(temporary)
        backend = root / "backend"
        backend.mkdir()
        subprocess.run(["git", "init", "-q", backend], check=True)
        subprocess.run(["git", "-C", backend, "config", "user.email", "r2@example.invalid"], check=True)
        subprocess.run(["git", "-C", backend, "config", "user.name", "R2 Test"], check=True)
        (backend / "tracked").write_text("backend\n", encoding="utf-8")
        subprocess.run(["git", "-C", backend, "add", "tracked"], check=True)
        subprocess.run(["git", "-C", backend, "commit", "-qm", "fixture"], check=True)
        commit = subprocess.run(
            ["git", "-C", backend, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

        firmware = root / "firmware.bin"
        firmware.write_bytes(b"R2 firmware fixture\n")
        firmware_sha = hashlib.sha256(firmware.read_bytes()).hexdigest()
        scenario = root / "scenario.json"
        scenario.write_text('{"schema_version":1,"name":"fixture","steps":[]}\n', encoding="utf-8")
        scenario_contract = None
        if with_scenario:
            scenario_contract = {
                "path": "scenarios/fixture.json",
                "sha256": hashlib.sha256(scenario.read_bytes()).hexdigest(),
            }

        registry = root / "firmware-targets.json"
        registry.write_text(json.dumps({
            "schema_version": 3,
            "policy": "test",
            "targets": [{
                "id": "fixture",
                "revision": 1,
                "status": "active",
                "source": {"repo": "fixture", "commit": "0" * 40},
                "toolchain": {"pico_sdk": "2.2.0", "gcc": "13.2.1"},
                "build": {"command": "fixture"},
                "artifacts": {"bin_basename": firmware.name, "bin_sha256": firmware_sha},
                "backend": {
                    "repo": "picoem-picocalc", "branch": "main",
                    "accepted": commit, "report_schema": 8,
                },
                "runner": {
                    "board": "picocalc", "lcd_variant": "hwspi-rgb888",
                    "cycles": 123, "quantum": 1, "psram": True,
                    "psram_verify_range": "0:16", "keyboard": True,
                    "keys": "HI", "sd": {"attached": True, "format": "fat32"},
                },
                "scenario": scenario_contract,
                "acceptance": {
                    "expected_stop_reason": "scenario_done" if with_scenario else "cycle_limit",
                    "required_uart_markers": ["READY"],
                    "report_checks": [{"path": "probe", "op": "eq", "value": "ok"}],
                },
                "validation": {
                    "record": "firmware-validation/validations/fixture.json",
                    "sha256": "0" * 64,
                },
            }],
        }), encoding="utf-8")

        runner = backend / "target/release/picocalc-run"
        runner.parent.mkdir(parents=True)
        runner.write_text("""#!/usr/bin/env python3
import hashlib, json, sys
from pathlib import Path
args = sys.argv[1:]
root = Path(__file__).resolve().parents[2]
(root / "argv.json").write_text(json.dumps(args), encoding="utf-8")
mode_path = root / "mode"
mode = mode_path.read_text(encoding="utf-8").strip() if mode_path.exists() else "pass"
def value(flag):
    return args[args.index(flag) + 1]
if mode == "missing":
    raise SystemExit(0)
report_path = Path(value("--json"))
if mode == "malformed":
    report_path.write_text("not json", encoding="utf-8")
    raise SystemExit(0)
if mode == "nonobject":
    report_path.write_text("[]", encoding="utf-8")
    raise SystemExit(0)
status = {"fail": "fail", "cannot": "cannot_judge"}.get(mode, "pass")
code = {"fail": 1, "cannot": 2, "rc-mismatch": 1}.get(mode, 0)
commit = value("--backend-commit")
report = {
    "schema_version": 8,
    "backend_commit": commit,
    "backend_build": {"commit": "wrong" if mode == "wrong-built" else commit, "dirty": False},
    "firmware": {"sha256": hashlib.sha256(Path(value("--bin")).read_bytes()).hexdigest()},
    "execution_model": "Serial",
    "board": value("--board"),
    "lcd_variant": "pio-rgb565" if mode == "wrong-lcd" else value("--lcd-variant"),
    "step_quantum": int(value("--quantum")),
    "cycle_limit": int(value("--cycles")),
    "cycles": int(value("--cycles")),
    "stop_reason": value("--expect-stop"),
    "exception": None,
    "error": None,
    "unsupported_mmio": [],
    "unsupported_mmio_truncated": False,
    "verdict": {"status": status},
    "scenario": {"steps": []},
    "probe": "ok",
}
if mode == "missing-field":
    del report["backend_build"]
if mode == "missing-timeline":
    del report["scenario"]
report_path.write_text(json.dumps(report), encoding="utf-8")
if "--uart" in args:
    Path(value("--uart")).write_bytes(b"UART fixture\\n")
raise SystemExit(code)
""", encoding="utf-8")
        runner.chmod(0o755)
        return backend, commit, firmware, scenario, registry

    def run_firmware_fixture(self, module, backend, firmware, scenario, registry, **overrides):
        arguments = dict(
            target_id="fixture", firmware=firmware, backend_dir=backend,
            cycles=None, keys=None, sd=None, sd_format=None,
            lcd_variant=None, scenario_override=scenario, snapshot_dir=None,
            uart_out=None, json_out=None,
        )
        arguments.update(overrides)
        with mock.patch.object(module, "FIRMWARE_TARGETS", registry):
            return module.firmware_test(**arguments)

    def test_bsp_quality_diagnostic_is_focused_and_bounded(self):
        project = ROOT / "diagnostics/bsp-quality"
        cmake = (project / "CMakeLists.txt").read_text(encoding="utf-8")
        source = (project / "app/main.cpp").read_text(encoding="utf-8")
        self.assertIn('PICOCALC_UF2_NAME "PicoCalc_BSP_Diagnostic"', cmake)
        self.assertIn("PICOCALC_AUDIO_REFERENCE_TONE OFF", cmake)
        self.assertIn("constexpr uint32_t kReadbackIterations = 100;", source)
        self.assertIn("keyboard::read_diagnostic(&sample)", source)
        self.assertIn("[BSP_DIAG_VERDICT]", source)
        self.assertNotIn("filesystem::", source)
        self.assertNotIn("sdcard::", source)

    def test_build_mode_definitions_override_stale_cache(self):
        specification = importlib.util.spec_from_file_location("picocalc", PICOCALC)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        self.assertEqual(
            module.build_mode_definitions(False, False, True),
            [
                "-DPICOCALC_PSRAM_LCD_COEXIST_TEST=OFF",
                "-DPICOCALC_DIAGNOSTIC_MODE=OFF",
            ],
        )
        self.assertEqual(
            module.build_mode_definitions(True, True, True),
            [
                "-DPICOCALC_PSRAM_LCD_COEXIST_TEST=ON",
                "-DPICOCALC_DIAGNOSTIC_MODE=ON",
            ],
        )
        self.assertEqual(
            module.build_mode_definitions(False, False, False),
            ["-DPICOCALC_PSRAM_LCD_COEXIST_TEST=OFF"],
        )
        self.assertEqual(
            module.build_mode_definitions(False, False, True, True, True),
            [
                "-DPICOCALC_PSRAM_LCD_COEXIST_TEST=OFF",
                "-DPICOCALC_DIAGNOSTIC_MODE=OFF",
                "-DPICOCALC_HARDWARE_VALIDATION_MODE=ON",
            ],
        )

    def test_build_versions_selects_non_coexistence_variant(self):
        specification = importlib.util.spec_from_file_location("picocalc", PICOCALC)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        project = ROOT / "templates/rp2040-basic"
        _, standard = module.build_versions(project, "pio-rgb565", False)
        _, coexistence = module.build_versions(project, "pio-rgb565", True)
        self.assertEqual(standard, "0.8.4-b-pio-rgb565-default")
        self.assertEqual(coexistence, "0.8.4-b-pio-rgb565-psram-lcd-coexist")

    def test_build_identities_detect_app_and_copied_bsp_changes(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q", project], check=True)
            subprocess.run(
                ["git", "-C", project, "config", "user.email", "build@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", project, "config", "user.name", "Build Test"],
                check=True,
            )
            (project / "tracked").write_text("source\n", encoding="utf-8")
            subprocess.run(["git", "-C", project, "add", "tracked"], check=True)
            subprocess.run(
                ["git", "-C", project, "commit", "-qm", "fixture"], check=True
            )
            self.assertNotIn("-dirty", module.project_commit(project))
            (project / "new-source.cpp").write_text("// new\n", encoding="utf-8")
            self.assertTrue(module.project_commit(project).endswith("-dirty"))

            bsp = project / "bsp"
            bsp.mkdir()
            (bsp / "VERSION").write_text("0.8.8\n", encoding="utf-8")
            commit = "a" * 40
            metadata = {
                "provenance": {
                    "bsp": {
                        "source_commit": commit,
                        "tree_sha256": directory_sha256(bsp),
                    }
                }
            }
            (project / ".picocalc-project.json").write_text(
                json.dumps(metadata), encoding="utf-8"
            )
            self.assertEqual(module.bsp_build_identity(project), "a" * 12)
            (bsp / "VERSION").write_text("changed\n", encoding="utf-8")
            self.assertEqual(module.bsp_build_identity(project), "a" * 12 + "-dirty")

    def test_project_commit_does_not_inherit_parent_repository(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "source"
            parent.mkdir()
            subprocess.run(["git", "init", "-q", parent], check=True)
            subprocess.run(
                ["git", "-C", parent, "config", "user.email", "build@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", parent, "config", "user.name", "Build Test"],
                check=True,
            )
            (parent / "tracked").write_text("source\n", encoding="utf-8")
            subprocess.run(["git", "-C", parent, "add", "tracked"], check=True)
            subprocess.run(
                ["git", "-C", parent, "commit", "-qm", "fixture"], check=True
            )

            inside_parent = parent / "generated-project"
            outside_parent = root / "generated-project"
            inside_parent.mkdir()
            outside_parent.mkdir()

            self.assertEqual(module.project_commit(inside_parent), "untracked")
            self.assertEqual(module.project_commit(outside_parent), "untracked")

            subprocess.run(["git", "init", "-q", inside_parent], check=True)
            subprocess.run(
                [
                    "git", "-C", inside_parent, "config", "user.email",
                    "app@example.invalid",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", inside_parent, "config", "user.name", "App Test"],
                check=True,
            )
            (inside_parent / "tracked").write_text("app\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", inside_parent, "add", "tracked"], check=True
            )
            subprocess.run(
                ["git", "-C", inside_parent, "commit", "-qm", "app fixture"],
                check=True,
            )
            self.assertNotEqual(module.project_commit(inside_parent), "untracked")

    def copy_project(self, temporary):
        project = Path(temporary) / "project"
        shutil.copytree(
            ROOT,
            project,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "third_party", "build", "build-ci"
            ),
        )
        return project

    def test_lcd_protocol_emits_exact_transactions_and_cs_chunks(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "a C++17 host compiler is required")
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "lcd_protocol_test"
            compiled = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "bsp/include"),
                    str(ROOT / "tests/lcd_protocol_test.cpp"),
                    "-o",
                    str(executable),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run(
                [str(executable)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn("transaction test passed", executed.stdout)

    def test_generated_board_header_is_current(self):
        completed = run(GENERATE_BOARD, "--check")
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_portable_verification_and_json_schema(self):
        completed = run(VERIFY, "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["mode"], "portable")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["failed"], 0)
        self.assertTrue(report["checks"])

    def test_target_schema_verification_includes_opt2b_running_horizon_record(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        self.assertEqual(report["mode"], "target-schema")
        self.assertEqual(report["status"], "pass")
        opt2b = next(
            check for check in report["checks"]
            if check["name"] == "opt2-b:running-event-horizon-profile"
        )
        self.assertEqual(opt2b["status"], "pass")
        self.assertEqual(opt2b["target"], "picotetris-opt1b")
        self.assertGreaterEqual(opt2b.get("running_steps", 0), 0)

    def test_target_schema_rejects_opt2b_running_horizon_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = project / "firmware-validation/records/opt2-b-running-horizon-20260808-01/record.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt2b = next(
            check for check in report["checks"]
            if check["name"] == "opt2-b:running-event-horizon-profile"
        )
        self.assertEqual(opt2b["status"], "fail")

    def test_target_schema_verification_includes_opt2c_rejected_candidate(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt2c = next(
            check for check in report["checks"]
            if check["name"] == "opt2-c:bounded-exact-batching"
        )
        self.assertEqual(opt2c["status"], "pass")
        self.assertEqual(opt2c["result"], "rejected")
        self.assertEqual(opt2c["paired_runs"], 3)

    def test_target_schema_verification_includes_opt2d_lever_comparison(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt2d = next(
            check for check in report["checks"]
            if check["name"] == "opt2-d:lever-comparison"
        )
        self.assertEqual(opt2d["status"], "pass")
        self.assertEqual(opt2d["target"], "picotetris-opt1b")
        self.assertEqual(
            opt2d["decision_selected_next_prototype"],
            "PIO exact event horizon and bulk advance",
        )
        self.assertGreaterEqual(opt2d.get("fallback_union_cycles", 0), 0)

    def test_target_schema_verification_includes_opt2e_pio_pull_stall(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt2e = next(
            check for check in report["checks"]
            if check["name"] == "opt2-e:pio-pull-stall"
        )
        self.assertEqual(opt2e["status"], "pass")
        self.assertEqual(opt2e["target"], "picotetris-opt1b")
        self.assertEqual(opt2e["backend_commit"], "a7ac9020b9861c1c4803187b7092512b65f60835")
        self.assertTrue(opt2e.get("candidate_calls_single_cycle"))

    def test_target_schema_verification_includes_opt2f_stationary_pin_bulk(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt2f = next(
            check
            for check in report["checks"]
            if check["name"] == "opt2-f:stationary-pin-bulk"
        )
        self.assertEqual(opt2f["status"], "pass")
        self.assertEqual(opt2f["target"], "picotetris-opt1b")
        self.assertEqual(opt2f["backend_commit"], "9ec1988ec4c5c4fa240a1f409ac9524364e017de")
        self.assertEqual(opt2f.get("candidate_median_improvement_percent"), 0.6875477463712747)
        self.assertEqual(opt2f.get("paired_runs"), 3)
        self.assertEqual(opt2f.get("candidate_pio_system_cycles"), 371_982_564)

    def test_target_schema_verification_includes_opt2g_uart_deadline(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt2g = next(
            check
            for check in report["checks"]
            if check["name"] == "opt2-g:uart-deadline"
        )
        self.assertEqual(opt2g["status"], "pass")
        self.assertEqual(opt2g["target"], "picotetris-opt1b")
        self.assertEqual(opt2g["backend_commit"], "593e6d78541722920e1fa903e682d49912eae825")
        self.assertEqual(opt2g.get("candidate_median_improvement_percent"), -8.680555555555555)
        self.assertEqual(opt2g.get("paired_runs"), 3)
        self.assertEqual(opt2g.get("lane_calls"), 3_137_790)

    def test_target_schema_verification_includes_opt3a_xip_cursor_profile(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt3a = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-a:xip-cursor-profile"
        )
        self.assertEqual(opt3a["status"], "pass")
        self.assertEqual(opt3a["target"], "picotetris-opt1b")
        self.assertEqual(opt3a["result"], "measurement_complete")
        self.assertEqual(
            opt3a.get("next_prototype"),
            "short immutable-XIP decode cursor",
        )

    def test_target_schema_verification_includes_opt3b_xip_decode_cursor(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt3b = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-b:xip-decode-cursor"
        )
        self.assertEqual(opt3b["status"], "pass")
        self.assertEqual(opt3b["target"], "picotetris-opt1b")
        self.assertEqual(opt3b["result"], "rejected_performance_reverted")
        self.assertEqual(
            opt3b.get("candidate_backend"),
            "0e22846186e68d2d726e49817a9f74c246f517ca",
        )
        self.assertEqual(
            opt3b.get("revert_backend"),
            "e58e67f1be69357edec0bd47e879039f47a42648",
        )

    def test_target_schema_verification_includes_opt3c_compact_dispatch_key(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        opt3c = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-c:compact-dispatch-key"
        )
        self.assertEqual(opt3c["status"], "pass")
        self.assertEqual(opt3c["target"], "picotetris-opt1b")
        self.assertEqual(opt3c["result"], "rejected_performance_reverted")
        self.assertEqual(
            opt3c.get("baseline_backend"),
            "e58e67f1be69357edec0bd47e879039f47a42648",
        )
        self.assertEqual(
            opt3c.get("candidate_backend"),
            "3819a9d093b8ce980a61724ac8ab33ffe3003ec3",
        )
        self.assertEqual(
            opt3c.get("revert_backend"),
            "04b2eb2fb26f126e848b5c041177324954a98290",
        )
        self.assertEqual(opt3c.get("opt3_overall_status"), "complete_no_additional_promotion")

    def test_target_schema_verification_includes_next1_picoedit_blind_contract(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next1 = next(
            check
            for check in report["checks"]
            if check["name"] == "next1:picoedit-blind-contract"
        )
        self.assertEqual(next1["status"], "pass")
        self.assertEqual(
            next1.get("contract_id"),
            "next1-picoedit-blind-v1-20260809",
        )
        self.assertEqual(next1.get("repo"), "picoedit-picocalc")
        self.assertEqual(next1.get("host_min_assertions"), 100)

    def test_target_schema_verification_includes_next3_negative_contract(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "pass")
        self.assertEqual(
            next3.get("contract_id"),
            "next3-negative-conformance-v1-20260810",
        )
        self.assertEqual(next3.get("positive_correlations"), 7)
        self.assertEqual(next3.get("negative_denominator"), 1)
        self.assertEqual(next3.get("rate_state"), "measured")
        self.assertEqual(next3.get("candidates_audited"), 4)
        self.assertEqual(
            next3.get("first_candidate_classification"),
            "artifact_not_reproducible",
        )
        self.assertEqual(next3.get("explicit_fault_status"), "hardware_observed")
        self.assertEqual(next3.get("explicit_fault_classification"), "inconclusive")
        self.assertEqual(next3.get("inconclusive_cases"), 2)
        self.assertEqual(next3.get("correct_detections"), 1)
        self.assertEqual(next3.get("false_accepts"), 0)
        self.assertEqual(next3.get("false_accept_rate"), 0.0)
        self.assertEqual(next3.get("emulator_first_run"), "complete")
        self.assertEqual(
            next3.get("v2_contract_id"),
            "next3-lcd-cs-fault-v2-predesign-20260810",
        )
        self.assertEqual(
            next3.get("v2_status"), "fault_hardware_oracle_mismatch_inconclusive"
        )
        self.assertEqual(next3.get("v2_fault_hardware_status"), "hardware_observed")
        self.assertEqual(next3.get("v2_fault_classification"), "inconclusive")
        self.assertEqual(
            next3.get("v2_next_step"),
            "NEXT-3_complete",
        )
        self.assertEqual(
            next3.get("v2_top_remaining_variable"),
            "160x160 fill tiling and resulting window/CS boundary sequence",
        )
        self.assertIs(next3.get("v2_emulator_run_allowed"), False)
        self.assertEqual(
            next3.get("sd_crc_contract_id"),
            "next3-sd-cmd8-crc-v1-predesign-20260810",
        )
        self.assertEqual(
            next3.get("sd_crc_status"),
            "closed_correct_detection_after_false_accept_fix",
        )
        self.assertEqual(next3.get("sd_crc_required_hardware_runs"), 2)
        self.assertIs(next3.get("sd_crc_fault_implementation_allowed"), True)
        self.assertIs(next3.get("sd_crc_fault_emulator_run_allowed"), False)
        self.assertEqual(next3.get("sd_crc_fault_classification"), "false_accept")
        self.assertIs(next3.get("sd_crc_backend_change_allowed"), True)
        self.assertEqual(
            next3.get("sd_crc_post_fix_backend"),
            "5edca80ae3cd9f73d381399628a7cc1ab801bdf3",
        )
        self.assertEqual(
            next3.get("sd_crc_post_fix_classification"),
            "correct_negative_detection",
        )
        self.assertIs(next3.get("sd_crc_a2_exact_a1"), True)
        self.assertEqual(
            next3.get("sd_crc_fault_artifact_result"),
            "fault_artifact_frozen_hardware_pending",
        )
        self.assertEqual(
            next3.get("sd_crc_fault_hardware_result"), "fail_oracle_match"
        )
        self.assertEqual(
            next3.get("sd_crc_hardware_negative_denominator_delta"), 1
        )
        self.assertEqual(next3.get("sd_crc_baseline_result"), "pass")
        self.assertEqual(next3.get("sd_crc_baseline_hardware_result"), "pass")
        self.assertEqual(
            next3.get("sd_crc_baseline_record"),
            "firmware-validation/records/next3-sd-cmd8-crc-a1-20260810-01/record.json",
        )
        self.assertEqual(
            next3.get("sd_crc_baseline_hardware_record"),
            "firmware-validation/records/next3-sd-cmd8-crc-a1-hardware-20260810-01/record.json",
        )

    def test_target_schema_rejects_next3_zero_denominator_as_zero_percent(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            kpi_path = (
                project
                / "firmware-validation/records/next3-1-20260810-01/kpi.json"
            )
            kpi = json.loads(kpi_path.read_text(encoding="utf-8"))
            kpi["rates"]["false_accept_rate"] = 1.0
            kpi_path.write_text(json.dumps(kpi), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_post_fix_classification_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/"
                "next3-sd-cmd8-crc-b-post-fix-20260810-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["classification"] = "false_accept"
            record["kpi_effect"]["correct_detection_delta"] = 0
            record["kpi_effect"]["false_accept_delta"] = 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_sd_crc_oracle_weakening(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project
                / "firmware-validation/contracts/next3-sd-cmd8-crc-v1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["frozen_hardware_oracle"]["cmd8_r1"] = "01"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_sd_crc_baseline_filesystem_io(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            report_path = (
                project
                / "firmware-validation/records/"
                "next3-sd-cmd8-crc-a1-20260810-01/run-report.json"
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["sd"]["blocks_read"] = 1
            report_path.write_text(json.dumps(report), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_sd_crc_hardware_marker_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/"
                "next3-sd-cmd8-crc-a1-hardware-20260810-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["physical_run"]["evidence_marker_count"] = 38
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_fault_emulator_early_unlock(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project
                / "firmware-validation/contracts/next3-sd-cmd8-crc-v1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["baseline_progress"]["fault_emulator_run_allowed"] = True
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_fault_artifact_oracle_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/"
                "next3-sd-cmd8-crc-b-20260810-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["frozen_hardware_oracle"]["cmd8_r1"] = "01"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_fault_emulator_reunlock_after_first_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project
                / "firmware-validation/contracts/next3-sd-cmd8-crc-v1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["fault_progress"]["emulator_run_allowed"] = True
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_measured_false_accept_rate_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            kpi_path = (
                project
                / "firmware-validation/records/"
                "next3-sd-cmd8-crc-b-first-emulator-20260810-01/kpi.json"
            )
            kpi = json.loads(kpi_path.read_text(encoding="utf-8"))
            kpi["rates"]["false_accept_rate"] = 0.0
            kpi_path.write_text(json.dumps(kpi), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_first_run_classification_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/"
                "next3-sd-cmd8-crc-b-first-emulator-20260810-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["classification"] = "correct_negative_detection"
            record["kpi_effect"]["correct_detection_delta"] = 1
            record["kpi_effect"]["false_accept_delta"] = 0
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_wrong_reason_as_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            audit_path = (
                project
                / "firmware-validation/records/"
                "next3-lcd-031-audit-20260810-01/record.json"
            )
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["classification"] = "correct_negative_detection"
            audit["kpi_effect"]["negative_denominator_delta"] = 1
            audit["kpi_effect"]["correct_detection_delta"] = 1
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_rejects_next3_v2_observer_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project
                / "firmware-validation/contracts/next3-lcd-cs-fault-v2.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["controlled_experiment"]["fault"]["readback_observer"] = (
                "hardware SPI at 6 MHz"
            )
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next3 = next(
            check
            for check in report["checks"]
            if check["name"] == "next3:negative-conformance-contract"
        )
        self.assertEqual(next3["status"], "fail")

    def test_target_schema_verification_includes_next1_picoedit_hardware(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next1 = next(
            check
            for check in report["checks"]
            if check["name"] == "next1:picoedit-hardware-correlation"
        )
        self.assertEqual(next1["status"], "pass")
        self.assertEqual(next1.get("target"), "picoedit-r1")
        self.assertEqual(next1.get("save_count"), 3)
        self.assertIs(next1.get("human_recovery_exercised"), True)
        self.assertEqual(next1.get("verdict"), "pass")

    def test_target_schema_rejects_next1_hardware_output_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            output_path = (
                project
                / "firmware-validation/records/next1-picoedit-hardware-20260809-01/OUTPUT.TXT"
            )
            output_path.write_bytes(output_path.read_bytes() + b"tampered\n")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        next1 = next(
            check
            for check in report["checks"]
            if check["name"] == "next1:picoedit-hardware-correlation"
        )
        self.assertEqual(next1["status"], "fail")

    def test_target_schema_verification_includes_next2_multicore_contract(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:multicore-contract"
        )
        self.assertEqual(next2["status"], "pass")
        self.assertEqual(next2.get("phase_count"), 4)
        self.assertEqual(next2.get("marker_count"), 5)
        self.assertEqual(
            next2.get("backend"),
            "e985a9d7ecb51ef760506a105edd34e31cf9b5f1",
        )

    def test_target_schema_rejects_next2_multicore_vector_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project / "firmware-validation/contracts/next2-multicore-v1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["fixed_phases"][1]["vectors"][0]["output"] = "0x00000000"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:multicore-contract"
        )
        self.assertEqual(next2["status"], "fail")

    def test_target_schema_verification_includes_next2_multicore_acceptance(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:multicore-acceptance"
        )
        self.assertEqual(next2["status"], "pass")
        self.assertEqual(next2.get("target"), "picocalc-multicore-r1")
        self.assertEqual(next2.get("runs"), 3)
        self.assertEqual(next2.get("cycles"), 152548085)
        self.assertIs(next2.get("core1_fatal_fail_closed"), True)
        self.assertEqual(next2.get("hardware_correlation"), "pending")

    def test_target_schema_rejects_next2_multicore_run_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            uart_path = (
                project
                / "firmware-validation/records/next2-multicore-r1-20260809-01"
                / "runs/run-2/uart.log"
            )
            uart_path.write_bytes(uart_path.read_bytes() + b"tampered\n")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:multicore-acceptance"
        )
        self.assertEqual(next2["status"], "fail")

    def test_target_schema_verification_includes_next2_v2_hardware_evidence(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:multicore-v2-evidence"
        )
        self.assertEqual(next2["status"], "pass")
        self.assertEqual(next2.get("target"), "picocalc-multicore-r2")
        self.assertEqual(next2.get("hardware_uart_blocks"), 72)
        self.assertEqual(next2.get("physical_function"), "pass")
        self.assertEqual(next2.get("hardware_correlation"), "pass")

    def test_target_schema_verification_includes_next2_audio_contract_hardware_correlation(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:audio-contract"
        )
        self.assertEqual(next2["status"], "pass")
        self.assertEqual(next2.get("implementation"), "same_artifact_hardware_correlated")
        self.assertEqual(next2.get("contract_id"), "next2-audio-v3-20260809")
        self.assertEqual(next2.get("hardware_correlation"), "pass")
        self.assertEqual(next2.get("hardware_uart_blocks"), 18)

    def test_next2_audio_hardware_evidence_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            uart_path = (
                project
                / "firmware-validation/records/next2-audio-r1-hardware-20260809-01"
                / "usb-cdc.log"
            )
            uart_path.write_bytes(uart_path.read_bytes() + b"tampered\r\n")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:audio-contract"
        )
        self.assertEqual(next2["status"], "fail")

    def test_next2_audio_oracle_reports_expected_sha256(self):
        completed = run(
            NEXT2_AUDIO_ORACLE,
            "--verify",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["frame_count"], 49152)
        self.assertEqual(payload["pattern_period"], 256)
        self.assertAlmostEqual(payload["duration"], 49152 / 48000, places=12)
        self.assertEqual(
            payload["sha256"],
            "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a",
        )
        self.assertEqual(payload["first_words"][:4], [0x00F80003, 0x00DB0014, 0x00BE0025, 0x00A10036])
        self.assertEqual(payload["verify"]["status"], "match")

    def test_next2_audio_oracle_verify_mismatch_fails(self):
        completed = run(
            NEXT2_AUDIO_ORACLE,
            "--verify",
            "--expected-sha256",
            "0" * 64,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["verify"]["status"], "mismatch")

    def test_next2_audio_v3_oracle_separates_producer_and_quantized_sink(self):
        completed = run(NEXT2_AUDIO_ORACLE_V3, "--verify")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["contract_id"], "next2-audio-v3-20260809")
        self.assertEqual(
            payload["producer"]["sha256"],
            "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a",
        )
        self.assertEqual(
            payload["sink"]["sha256"],
            "1b1798dbe461b5a4b59964f8cf5b7c3ec12d2c4b34b2bc1dba9783d7f1b9876f",
        )
        self.assertEqual(payload["producer"]["first_words"][0], 0x00F80003)
        self.assertEqual(payload["sink"]["first_words"][0], 0x00F90003)
        self.assertEqual(payload["verify"]["status"], "match")

    def test_next2_audio_v3_oracle_is_stateful_across_frames(self):
        completed = run(NEXT2_AUDIO_ORACLE_V3, "--frame-count", "2")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["sink"]["first_words"], [0x00F90003, 0x00DB0014])

    def test_next2_audio_v3_negative_matrix_is_fail_closed(self):
        completed = run(NEXT2_AUDIO_NEGATIVE)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"], "pass")
        self.assertEqual(len(payload["mutations"]), 10)
        self.assertTrue(all(item["rejected"] for item in payload["mutations"]))

    def test_target_schema_rejects_next2_v2_hardware_uart_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            uart_path = (
                project
                / "firmware-validation/records"
                / "next2-multicore-r2-hardware-20260809-01/usb-cdc.log"
            )
            uart_path.write_bytes(uart_path.read_bytes() + b"tampered\r\n")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        next2 = next(
            check
            for check in report["checks"]
            if check["name"] == "next2:multicore-v2-evidence"
        )
        self.assertEqual(next2["status"], "fail")

    def test_target_schema_rejects_next1_seed_content_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project / "blind-validation/picoedit-contract-v1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["seed_file"]["content"] = "tampered\n"
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False), encoding="utf-8"
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        next1 = next(
            check
            for check in report["checks"]
            if check["name"] == "next1:picoedit-blind-contract"
        )
        self.assertEqual(next1["status"], "fail")

    def test_target_schema_rejects_next1_backend_pin_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            contract_path = (
                project / "blind-validation/picoedit-contract-v1.json"
            )
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["frozen_baseline"]["promoted_backend_commit"] = "b" * 40
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False), encoding="utf-8"
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        next1 = next(
            check
            for check in report["checks"]
            if check["name"] == "next1:picoedit-blind-contract"
        )
        self.assertEqual(next1["status"], "fail")

    def test_target_schema_rejects_opt3c_compact_dispatch_key_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/opt3-c-compact-dispatch-key-20260809-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt3c = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-c:compact-dispatch-key"
        )
        self.assertEqual(opt3c["status"], "fail")

    def test_target_schema_rejects_opt3c_compact_dispatch_key_artifact_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            artifact_path = (
                project
                / "firmware-validation/records/"
                "opt3-c-compact-dispatch-key-20260809-01/run-report.json"
            )
            artifact_path.write_text(
                artifact_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt3c = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-c:compact-dispatch-key"
        )
        self.assertEqual(opt3c["status"], "fail")

    def test_target_schema_rejects_opt3b_xip_decode_cursor_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/opt3-b-xip-decode-cursor-20260809-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt3b = next(
            check for check in report["checks"] if check["name"] == "opt3-b:xip-decode-cursor"
        )
        self.assertEqual(opt3b["status"], "fail")

    def test_target_schema_rejects_opt3b_xip_decode_cursor_artifact_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            artifact_path = (
                project
                / "firmware-validation/records/opt3-b-xip-decode-cursor-20260809-01/run-report.json"
            )
            artifact_path.write_text(
                artifact_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt3b = next(
            check for check in report["checks"] if check["name"] == "opt3-b:xip-decode-cursor"
        )
        self.assertEqual(opt3b["status"], "fail")

    def test_target_schema_rejects_opt3a_xip_cursor_profile_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/opt3-a-xip-cursor-profile-20260809-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt3a = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-a:xip-cursor-profile"
        )
        self.assertEqual(opt3a["status"], "fail")

    def test_target_schema_rejects_opt3a_xip_cursor_profile_artifact_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            artifact_path = (
                project
                / "firmware-validation/records/opt3-a-xip-cursor-profile-20260809-01/run-report.json"
            )
            artifact_path.write_text(
                artifact_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt3a = next(
            check
            for check in report["checks"]
            if check["name"] == "opt3-a:xip-cursor-profile"
        )
        self.assertEqual(opt3a["status"], "fail")

    def test_target_schema_rejects_opt2g_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/opt2-g-uart-deadline-20260809-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt2g = next(
            check
            for check in report["checks"]
            if check["name"] == "opt2-g:uart-deadline"
        )
        self.assertEqual(opt2g["status"], "fail")

    def test_target_schema_rejects_opt2e_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/opt2-e-pio-pull-stall-20260809-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt2e = next(
            check for check in report["checks"]
            if check["name"] == "opt2-e:pio-pull-stall"
        )
        self.assertEqual(opt2e["status"], "fail")

    def test_target_schema_rejects_opt2f_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = (
                project
                / "firmware-validation/records/opt2-f-stationary-pin-bulk-20260809-01/record.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt2f = next(
            check
            for check in report["checks"]
            if check["name"] == "opt2-f:stationary-pin-bulk"
        )
        self.assertEqual(opt2f["status"], "fail")

    def test_target_schema_rejects_opt2c_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = project / "firmware-validation/records/opt2-c-exact-batching-20260808-01/record.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["projection_byte_identical"] = False
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        opt2c = next(
            check for check in report["checks"]
            if check["name"] == "opt2-c:bounded-exact-batching"
        )
        self.assertEqual(opt2c["status"], "fail")

    def test_target_schema_rejects_opt2d_exactness_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            record_path = project / "firmware-validation/records/opt2-d-lever-comparison-20260809-01/record.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["exactness"]["cycles"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        opt2d = next(
            check for check in report["checks"]
            if check["name"] == "opt2-d:lever-comparison"
        )
        self.assertEqual(opt2d["status"], "fail")

    def test_ci_scopes_separate_core_from_target_schema(self):
        core = run(VERIFY, "--scope", "core", "--json")
        core_report = json.loads(core.stdout)
        self.assertEqual(core.returncode, 0, core_report)
        self.assertEqual(core_report["mode"], "portable-core")
        core_names = {check["name"] for check in core_report["checks"]}
        self.assertNotIn("firmware-targets:schema-and-contracts", core_names)
        self.assertFalse(any(name.startswith("r3:") for name in core_names))

        contracts = run(VERIFY, "--scope", "target-schema", "--json")
        contract_report = json.loads(contracts.stdout)
        self.assertEqual(contracts.returncode, 0, contract_report)
        self.assertEqual(contract_report["mode"], "target-schema")
        contract_names = {check["name"] for check in contract_report["checks"]}
        self.assertIn("firmware-targets:schema-and-contracts", contract_names)
        self.assertIn("firmware-targets:versioned-validations", contract_names)
        self.assertIn("r3:picotetris-contract", contract_names)
        self.assertFalse(any(name.startswith("source-fingerprint:") for name in contract_names))

    def test_capability_check_passes_for_current_capability(self):
        completed = run(VERIFY, "--scope", "target-schema", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, report)
        capability = next(
            check for check in report["checks"] if check["name"] == "firmware-validation:capability"
        )
        self.assertEqual(capability["status"], "pass")

    def test_capability_requires_correlated_audio_output_in_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            capability_path = project / "firmware-validation/capability.json"
            capability = json.loads(capability_path.read_text(encoding="utf-8"))
            audio = next(
                item for item in capability["supported"] if item["id"] == "audio-output"
            )
            capability["supported"].remove(audio)
            capability["unsupported"].append(audio)
            capability_path.write_text(json.dumps(capability), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        capability_check = next(
            check for check in report["checks"] if check["name"] == "firmware-validation:capability"
        )
        self.assertEqual(capability_check["status"], "fail")

    def test_capability_rejects_tampered_promoted_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            capability_path = project / "firmware-validation/capability.json"
            capability = json.loads(capability_path.read_text(encoding="utf-8"))
            capability["backend"]["roles"]["promoted"]["commit"] = "b" * 40
            capability_path.write_text(json.dumps(capability), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        capability_check = next(
            check for check in report["checks"] if check["name"] == "firmware-validation:capability"
        )
        self.assertEqual(capability_check["status"], "fail")

    def test_capability_rejects_missing_role(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            capability_path = project / "firmware-validation/capability.json"
            capability = json.loads(capability_path.read_text(encoding="utf-8"))
            del capability["backend"]["roles"]["experimental_main"]
            capability_path.write_text(json.dumps(capability), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        capability_check = next(
            check for check in report["checks"] if check["name"] == "firmware-validation:capability"
        )
        self.assertEqual(capability_check["status"], "fail")

    def test_capability_rejects_experimental_promoted_true(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            capability_path = project / "firmware-validation/capability.json"
            capability = json.loads(capability_path.read_text(encoding="utf-8"))
            capability["backend"]["roles"]["experimental_main"]["promoted"] = True
            capability_path.write_text(json.dumps(capability), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        capability_check = next(
            check for check in report["checks"] if check["name"] == "firmware-validation:capability"
        )
        self.assertEqual(capability_check["status"], "fail")

    def test_versioned_target_validation_fails_closed_on_tampering(self):
        mutations = ("attestation", "target", "evidence")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                project = self.copy_project(temporary)
                registry_path = project / "reference-projects/firmware-targets.json"
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                target = next(
                    item for item in registry["targets"]
                    if item["id"] == "picocalc-template-b"
                )
                if mutation == "attestation":
                    path = project / target["validation"]["record"]
                    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                elif mutation == "target":
                    target["backend"]["accepted"] = "b" * 40
                    registry_path.write_text(json.dumps(registry), encoding="utf-8")
                else:
                    validation = json.loads(
                        (project / target["validation"]["record"]).read_text(encoding="utf-8")
                    )
                    path = project / validation["evidence"]["record"]
                    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                completed = run(
                    VERIFY,
                    "--project-root",
                    project,
                    "--json",
                )
                report = json.loads(completed.stdout)
                validation_check = next(
                    check for check in report["checks"]
                    if check["name"] == "firmware-targets:versioned-validations"
                )
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(validation_check["status"], "fail")
                self.assertTrue(validation_check["errors"])

    def test_target_schema_rejects_tampered_ci_promoted_backend_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            ci_path = project / ".github/workflows/ci.yml"
            ci = ci_path.read_text(encoding="utf-8")
            replaced = False
            lines = []
            for line in ci.splitlines():
                if not replaced and line.startswith("  PICOEM_PROMOTED_COMMIT:"):
                    lines.append("  PICOEM_PROMOTED_COMMIT: " + "b" * 40)
                    replaced = True
                else:
                    lines.append(line)
            if not replaced:
                self.fail("PICOEM_PROMOTED_COMMIT not found in ci.yml")
            ci_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--scope",
                "target-schema",
                "--json",
            )

        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        r4_ci = next(
            check for check in report["checks"] if check["name"] == "r4:backend-role-ci"
        )
        self.assertEqual(r4_ci["status"], "fail")

    def test_audio_dma_restart_check_detects_missing_channel_reenable(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            source = project / "bsp/vendor/audio_picoment/platform/picocalc_audio_pwm.cpp"
            original = source.read_text(encoding="utf-8")
            start = original.index("void start_output()")
            end = original.index("void init_common(", start)
            body = original[start:end]
            body = body.replace(
                "    // EOF drain disables the DMA channel's IRQ source as well as the NVIC\n"
                "    // line.  Re-enable both sides for every subsequent track or replay.\n"
                "    dma_channel_set_irq0_enabled(static_cast<uint>(g_dma_channel), true);\n",
                "",
                1,
            )
            source.write_text(original[:start] + body + original[end:], encoding="utf-8")
            completed = run(VERIFY, "--project-root", project, "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        check = next(
            check for check in report["checks"]
            if check["name"] == "source-fingerprint:audio-dma-restart"
        )
        self.assertEqual(check["status"], "fail")

    def test_audio_dma_check_rejects_sdk_2_1_only_transfer_count_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            source = project / "bsp/vendor/audio_picoment/platform/picocalc_audio_pwm.cpp"
            original = source.read_text(encoding="utf-8")
            source.write_text(
                original.replace(
                    "dma_channel_set_trans_count(static_cast<uint>(g_dma_channel), kHalfSamples, false);",
                    "dma_channel_set_transfer_count(static_cast<uint>(g_dma_channel), kHalfSamples, false);",
                    1,
                ),
                encoding="utf-8",
            )
            completed = run(VERIFY, "--project-root", project, "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        check = next(
            check for check in report["checks"]
            if check["name"] == "source-fingerprint:audio-dma-restart"
        )
        self.assertEqual(check["status"], "fail")
        self.assertFalse(check["sdk_2_0_compatible"])

    def test_reference_verification_reports_missing_repositories(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = run(
                VERIFY,
                "--references",
                "--strict-commit",
                "--reference-root",
                temporary,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        missing = [
            check
            for check in report["checks"]
            if check["name"].startswith("reference-commit:")
        ]
        self.assertEqual(len(missing), 5)
        self.assertTrue(
            any(check["name"] == "reference-commit:PicoCalc" for check in missing)
        )
        self.assertTrue(all(check["actual"] == "missing" for check in missing))

    def test_strict_commit_requires_reference_mode(self):
        completed = run(VERIFY, "--strict-commit")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("require --references", completed.stdout)

    def test_sd_format_requires_attached_card(self):
        completed = run(
            PICOCALC,
            "test",
            "--mode",
            "firmware",
            "--sd-format",
            "fat16",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--sd-format requires --sd", completed.stderr)

    def test_host_mode_rejects_firmware_sd_selection(self):
        completed = run(
            PICOCALC,
            "test",
            "--mode",
            "host",
            "--sd",
            "--sd-format",
            "fat16",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("host mode tests FAT32 and FAT16 automatically", completed.stderr)

    def test_lcd_transaction_test_detects_changed_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            protocol = project / "bsp/include/picocalc/detail/lcd_protocol.h"
            protocol.write_text(
                protocol.read_text(encoding="utf-8").replace(
                    "{0x3a, {board::kLcdColmod}, 1}",
                    "{0x3a, {0x65}, 1}",
                ),
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        lcd = next(
            check
            for check in report["checks"]
            if check["name"] == "host-test:lcd-transactions"
        )
        self.assertEqual(lcd["status"], "fail")
        self.assertEqual(lcd["stage"], "execute")

    def test_generated_header_check_detects_profile_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            profile_path = project / "profiles/picocalc-rp2040.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["display"]["visible_width"] = 321
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        generated = next(
            check
            for check in report["checks"]
            if check["name"] == "structured-profile:generated-board-header"
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(generated["status"], "fail")
        self.assertTrue(generated["stale"])

    def test_json_mode_normalizes_malformed_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            (project / "profiles/picocalc-rp2040.json").write_text(
                "{broken",
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("Traceback", completed.stderr)
        generated = next(
            check
            for check in report["checks"]
            if check["name"] == "structured-profile:generated-board-header"
        )
        self.assertEqual(generated["error_type"], "JSONDecodeError")

    def test_json_mode_normalizes_malformed_reference_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            (project / "reference-projects/catalog.json").write_text(
                "[] not-json",
                encoding="utf-8",
            )
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--references",
                "--reference-root",
                temporary,
                "--json",
            )
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(
            any(check["name"] == "reference-catalog" for check in report["checks"])
        )
        self.assertNotIn("Traceback", completed.stderr)

    def test_json_mode_normalizes_invalid_arguments(self):
        completed = run(VERIFY, "--strict-commit", "--json")
        report = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(report["mode"], "invalid")
        self.assertEqual(report["checks"][0]["name"], "invocation:arguments")
        self.assertEqual(completed.stderr, "")

    def test_hardware_record_rejects_unsubstantiated_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            template_path = project / "hardware-validation/template.json"
            record = json.loads(template_path.read_text(encoding="utf-8"))
            record["overall_status"] = "pass"
            record_path = project / "hardware-validation/records/unsubstantiated.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        ledger = next(
            check
            for check in report["checks"]
            if check["name"] == "hardware-validation:records"
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(ledger["status"], "fail")
        self.assertGreaterEqual(len(ledger["invalid"][0]["errors"]), 7)

    def test_hardware_record_accepts_complete_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.copy_project(temporary)
            template_path = project / "hardware-validation/template.json"
            record = json.loads(template_path.read_text(encoding="utf-8"))
            evidence_dir = project / "hardware-validation/records/session"
            evidence_dir.mkdir()
            relative_files = {
                "lcd": "hardware-validation/records/session/lcd.png",
                "sd": "hardware-validation/records/session/uart.log",
                "keyboard": "hardware-validation/records/session/keys.log",
            }
            for relative in relative_files.values():
                (project / relative).write_text("evidence", encoding="utf-8")
            build_log = "hardware-validation/records/session/build.log"
            (project / build_log).write_text("build passed", encoding="utf-8")

            record.update(
                {
                    "validation_id": "bsp-0.1.0-20260729-01",
                    "repository_commit": "a" * 40,
                    "validation_date": "2026-07-29",
                    "operator": "test",
                    "overall_status": "pass",
                }
            )
            record["firmware"]["uf2_sha256"] = "b" * 64
            record["firmware"]["build_log"] = build_log
            record["hardware"]["board_revision"] = "1.0"
            record["software"]["compiler"] = "arm-none-eabi-g++ 9.2.1"
            record["software"]["cmake"] = "3.16.3"
            record["sd_card"].update(
                {
                    "manufacturer": "test-vendor",
                    "model": "test-model",
                    "capacity": "8 GB",
                }
            )
            for name, relative in relative_files.items():
                record["tests"][name] = {
                    "status": "pass",
                    "observed": "verified",
                    "evidence_files": [relative],
                }
            record_path = project / "hardware-validation/records/complete.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            completed = run(
                VERIFY,
                "--project-root",
                project,
                "--json",
            )
        report = json.loads(completed.stdout)
        ledger = next(
            check
            for check in report["checks"]
            if check["name"] == "hardware-validation:records"
        )
        self.assertEqual(completed.returncode, 0, report)
        # The synthetic record must be accepted. The count is not pinned
        # to one: real hardware records also reach `pass`, and a test
        # that assumed otherwise would start failing the day one did.
        self.assertGreaterEqual(ledger["passing_records"], 1)
        self.assertEqual(ledger.get("invalid", []), [])

    def test_project_generator_pins_bsp_and_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "Demo_App-1"
            completed = run(
                PICOCALC,
                "new",
                "Demo_App-1",
                "--output",
                destination,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((destination / "app/main.cpp").is_file())
            self.assertTrue((destination / "bsp/src/display.cpp").is_file())
            self.assertTrue(
                (
                    destination
                    / "bsp/include/picocalc/detail/lcd_protocol.h"
                ).is_file()
            )
            self.assertTrue(
                (
                    destination
                    / "bsp/include/picocalc/board_generated.h"
                ).is_file()
            )
            self.assertFalse((destination / "build").exists())
            self.assertFalse((destination / ".picocalc-build-history.json").exists())
            metadata = json.loads(
                (destination / ".picocalc-project.json").read_text(encoding="utf-8")
            )
            bsp_version = (ROOT / "bsp/VERSION").read_text(encoding="utf-8").strip()
            self.assertEqual(metadata["project_name"], "Demo_App-1")
            self.assertEqual(metadata["schema_version"], 2)
            self.assertEqual(metadata["bsp_version"], bsp_version)
            self.assertEqual(metadata["provenance"]["kind"], "generated")
            self.assertEqual(
                metadata["provenance"]["bsp"]["version"], bsp_version
            )
            self.assertEqual(
                metadata["provenance"]["bsp"]["tree_sha256"],
                directory_sha256(destination / "bsp"),
            )
            self.assertRegex(
                metadata["provenance"]["bsp"]["source_commit"], r"^[0-9a-f]{40}$"
            )
            self.assertTrue((destination / "LICENSE").is_file())
            self.assertTrue((destination / "THIRD_PARTY_NOTICES.md").is_file())

    def test_project_generator_rejects_invalid_name(self):
        completed = run(PICOCALC, "new", "../bad")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("name must start with a letter", completed.stderr)

    def test_project_generator_does_not_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = run(
                PICOCALC,
                "new",
                "Existing",
                "--output",
                temporary,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("destination already exists", completed.stderr)

    def test_build_rejects_missing_sdk(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.13)\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.pop("PICO_SDK_PATH", None)
            completed = run(
                PICOCALC,
                "build",
                "--project",
                project,
                "--sdk",
                project / "missing-sdk",
                env=environment,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Pico SDK not found", completed.stderr)

    def test_build_rejects_invalid_picotool_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            project = temporary_path / "project"
            sdk = temporary_path / "sdk"
            project.mkdir()
            (project / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.13)\n",
                encoding="utf-8",
            )
            (sdk / "external").mkdir(parents=True)
            (sdk / "external/pico_sdk_import.cmake").write_text("", encoding="utf-8")
            completed = run(
                PICOCALC,
                "build",
                "--project",
                project,
                "--sdk",
                sdk,
                "--picotool-dir",
                temporary_path / "missing-picotool",
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid picotool", completed.stderr)

    def test_reference_fetch_dry_run_uses_catalog_urls_and_commits(self):
        catalog = json.loads(
            (ROOT / "reference-projects/catalog.json").read_text(encoding="utf-8")
        )
        official = next(
            project for project in catalog["projects"] if project["name"] == "PicoCalc"
        )
        self.assertEqual(
            official["official_source_url"],
            "https://github.com/clockworkpi/PicoCalc/tree/master/Code/picocalc_keyboard",
        )
        self.assertEqual(official["source_subpath"], "Code/picocalc_keyboard")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "references"
            completed = run(
                PICOCALC,
                "fetch-references",
                "--output",
                output,
                "--dry-run",
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.count("fetch https://github.com/"), 5)
        self.assertIn("https://github.com/clockworkpi/PicoCalc.git", completed.stdout)
        self.assertIn("553da6f2408963b956779599d179d77fd611a4d7", completed.stdout)
        self.assertIn("0d677d07cb0a037ee9cf331106400052622603ee", completed.stdout)

    def test_reference_fetch_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "picocalc-life").mkdir()
            completed = run(
                PICOCALC,
                "fetch-references",
                "--output",
                output,
                "--dry-run",
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("destination already exists", completed.stderr)

    def test_r2_target_drives_the_complete_runner_command(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            backend, _, firmware, scenario, registry = self.make_firmware_fixture(
                temporary
            )
            output = Path(temporary) / "accepted.json"
            uart = Path(temporary) / "accepted.uart"
            result = self.run_firmware_fixture(
                module, backend, firmware, scenario, registry,
                json_out=output, uart_out=uart,
            )
            self.assertEqual(result, 0)
            self.assertTrue(output.is_file())
            self.assertEqual(uart.read_bytes(), b"UART fixture\n")
            argv = json.loads((backend / "argv.json").read_text(encoding="utf-8"))
            for item in (
                "--lcd-variant", "hwspi-rgb888", "--quantum", "1",
                "--psram", "--psram-verify-range", "0:16", "--keyboard",
                "--keys", "HI", "--sd", "--sd-format", "fat32",
                "--scenario", "--expect-stop", "scenario_done", "--expect-uart", "READY",
                "--snapshot-dir", "--uart",
            ):
                self.assertIn(item, argv)

    def test_r2_target_driver_includes_audio_sink_expectations(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            backend, _, firmware, scenario, registry = self.make_firmware_fixture(
                temporary
            )
            contract = json.loads(registry.read_text(encoding="utf-8"))
            contract["targets"][0]["runner"]["audio_sink"] = {
                "expected_count": 49_152,
                "expected_sha256": "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a",
            }
            registry.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
            output = Path(temporary) / "accepted.json"
            result = self.run_firmware_fixture(
                module, backend, firmware, scenario, registry, json_out=output
            )
            self.assertEqual(result, 0)
            self.assertTrue(output.is_file())
            argv = json.loads((backend / "argv.json").read_text(encoding="utf-8"))
            for item in (
                "--expect-audio-sink-count", "49152",
                "--expect-audio-sink-sha256",
                "c66c76b2003a9e24fc16b3d9a6aa3bbc1cd0d6faf2d469244d9db3823d46367a",
            ):
                self.assertIn(item, argv)

    def test_r2_registry_rejects_audio_sink_missing_fields(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            _, _, _, _, registry = self.make_firmware_fixture(temporary)
            document = json.loads(registry.read_text(encoding="utf-8"))
            document["targets"][0]["runner"]["audio_sink"] = {
                "expected_count": 49_152,
            }
            registry.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(module, "FIRMWARE_TARGETS", registry):
                with self.assertRaises(ValueError):
                    module.load_firmware_registry()

    def test_r2_registry_rejects_audio_sink_invalid_count(self):
        module = self.load_picocalc_module()
        mutations = (
            {"audio_sink": {"expected_count": 0, "expected_sha256": "a" * 64}},
            {"audio_sink": {"expected_count": True, "expected_sha256": "a" * 64}},
        )
        for mutation in mutations:
            with tempfile.TemporaryDirectory() as temporary:
                _, _, _, _, registry = self.make_firmware_fixture(temporary)
                document = json.loads(registry.read_text(encoding="utf-8"))
                document["targets"][0]["runner"]["audio_sink"] = mutation["audio_sink"]
                registry.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
                with mock.patch.object(module, "FIRMWARE_TARGETS", registry):
                    with self.assertRaises(ValueError):
                        module.load_firmware_registry()

    def test_r2_registry_rejects_audio_sink_invalid_sha256(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            _, _, _, _, registry = self.make_firmware_fixture(temporary)
            document = json.loads(registry.read_text(encoding="utf-8"))
            document["targets"][0]["runner"]["audio_sink"] = {
                "expected_count": 49_152,
                "expected_sha256": "x" * 64,
            }
            registry.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(module, "FIRMWARE_TARGETS", registry):
                with self.assertRaises(ValueError):
                    module.load_firmware_registry()

    def test_r2_registry_rejects_incomplete_or_old_contracts(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            _, _, _, _, registry = self.make_firmware_fixture(temporary)
            original = json.loads(registry.read_text(encoding="utf-8"))
            mutations = (
                lambda value: value.update(revision=0),
                lambda value: value.update(supersedes="missing-target"),
                lambda value: value.pop("build"),
                lambda value: value["backend"].update(report_schema=7),
                lambda value: value["runner"].update(cycles=True),
                lambda value: value["acceptance"]["report_checks"].append(
                    {"path": "items", "op": "length_eq", "value": True}
                ),
                lambda value: value["acceptance"].update(
                    normalized_report_sha256="not-a-sha"
                ),
                lambda value: value["validation"].update(record="../escape.json"),
            )
            for mutate in mutations:
                document = json.loads(json.dumps(original))
                mutate(document["targets"][0])
                registry.write_text(json.dumps(document), encoding="utf-8")
                with mock.patch.object(module, "FIRMWARE_TARGETS", registry):
                    with self.assertRaises(ValueError):
                        module.load_firmware_registry()

    def test_r2_rejects_wrong_bin_scenario_lcd_and_backend_before_running(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            backend, _, firmware, scenario, registry = self.make_firmware_fixture(temporary)
            wrong_bin = Path(temporary) / "wrong.bin"
            wrong_bin.write_bytes(firmware.read_bytes() + b"x")
            self.assertEqual(self.run_firmware_fixture(
                module, backend, wrong_bin, scenario, registry
            ), 1)
            self.assertFalse((backend / "argv.json").exists())

            wrong_scenario = Path(temporary) / "wrong.json"
            wrong_scenario.write_text("{}\n", encoding="utf-8")
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, wrong_scenario, registry
            ), 1)
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry,
                lcd_variant="pio-rgb565",
            ), 1)

            (backend / "tracked").write_text("second\n", encoding="utf-8")
            subprocess.run(["git", "-C", backend, "add", "tracked"], check=True)
            subprocess.run(["git", "-C", backend, "commit", "-qm", "wrong head"], check=True)
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry
            ), 1)

    def test_r2_report_must_be_new_well_formed_and_match_the_device(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            backend, _, firmware, scenario, registry = self.make_firmware_fixture(temporary)
            stale = Path(temporary) / "stale.json"
            stale.write_text('{"old":true}\n', encoding="utf-8")
            for mode in ("missing", "malformed", "nonobject"):
                (backend / "mode").write_text(mode, encoding="utf-8")
                self.assertEqual(self.run_firmware_fixture(
                    module, backend, firmware, scenario, registry, json_out=stale
                ), 2, mode)
            self.assertEqual(stale.read_text(encoding="utf-8"), '{"old":true}\n')
            for mode in ("missing-field", "rc-mismatch"):
                (backend / "mode").write_text(mode, encoding="utf-8")
                self.assertEqual(self.run_firmware_fixture(
                    module, backend, firmware, scenario, registry, json_out=stale
                ), 2, mode)
            for mode in ("wrong-lcd", "wrong-built"):
                (backend / "mode").write_text(mode, encoding="utf-8")
                self.assertEqual(self.run_firmware_fixture(
                    module, backend, firmware, scenario, registry, json_out=stale
                ), 1, mode)

    def test_r2_preserves_judged_failure_and_cannot_judge_exit_codes(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            backend, _, firmware, scenario, registry = self.make_firmware_fixture(temporary)
            for mode, expected in (("fail", 1), ("cannot", 2)):
                (backend / "mode").write_text(mode, encoding="utf-8")
                self.assertEqual(self.run_firmware_fixture(
                    module, backend, firmware, scenario, registry
                ), expected)

    def test_r3_target_pins_normalized_report_and_timeline(self):
        module = self.load_picocalc_module()
        with tempfile.TemporaryDirectory() as temporary:
            backend, _, firmware, scenario, registry = self.make_firmware_fixture(temporary)
            first_report = Path(temporary) / "first.json"
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry, json_out=first_report
            ), 0)
            report = json.loads(first_report.read_text(encoding="utf-8"))
            document = json.loads(registry.read_text(encoding="utf-8"))
            acceptance = document["targets"][0]["acceptance"]
            normalized_report_sha = module.normalized_json_sha256(report)
            acceptance["normalized_report_sha256"] = normalized_report_sha
            acceptance["timeline_sha256"] = module.normalized_json_sha256(
                report["scenario"]["steps"]
            )
            registry.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry
            ), 0)

            acceptance["normalized_report_sha256"] = "0" * 64
            registry.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry
            ), 1)
            acceptance["normalized_report_sha256"] = normalized_report_sha
            registry.write_text(json.dumps(document), encoding="utf-8")

            (backend / "mode").write_text("missing-timeline", encoding="utf-8")
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry
            ), 2)
            (backend / "mode").unlink()

            acceptance["timeline_sha256"] = "0" * 64
            registry.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(self.run_firmware_fixture(
                module, backend, firmware, scenario, registry
            ), 1)


if __name__ == "__main__":
    unittest.main()
