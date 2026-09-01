import importlib.util
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))


def load_runner():
    specification = importlib.util.spec_from_file_location(
        "benchmark_rp2040_cpu_candidate", TOOLS / "benchmark_rp2040_cpu_candidate.py"
    )
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


def load_verifier():
    specification = importlib.util.spec_from_file_location(
        "verify_environment_for_cpu_candidate", TOOLS / "verify_environment.py"
    )
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


class CandidateRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_runner()

    def fixture_target(self):
        return {
            "id": "fixture",
            "revision": 1,
            "runner": {
                "board": "picocalc",
                "lcd_variant": "pio-rgb565",
                "quantum": 1,
                "cycles": 123,
                "psram": True,
                "keyboard": True,
                "keys": None,
                "sd": {"attached": True, "format": "fat32"},
            },
            "acceptance": {
                "expected_stop_reason": "scenario_done",
                "required_uart_markers": ["done"],
                "report_checks": [
                    {"path": "backend_build.commit", "op": "eq", "value": "a" * 40},
                    {"path": "stop_reason", "op": "eq", "value": "scenario_done"},
                ],
            },
            "scenario": None,
        }

    def test_schedule_has_equal_ab_ba_and_alternating_workload_order(self):
        schedule = self.module.make_ab_schedule(["tetris", "edit"], 10)
        self.assertEqual(len(schedule), 40)
        self.assertEqual({item["run_id"] for item in schedule}, {"run-{:03d}".format(i) for i in range(1, 41)})
        for workload in ("tetris", "edit"):
            selected = [item for item in schedule if item["workload"] == workload]
            self.assertEqual(len(selected), 20)
            self.assertEqual({item["order"] for item in selected}, {"AB", "BA"})
            self.assertEqual(sum(item["order"] == "AB" for item in selected), 10)
            self.assertEqual(sum(item["order"] == "BA" for item in selected), 10)
        self.assertEqual(
            [item["workload"] for item in schedule if item["pair"] == 1],
            ["tetris", "tetris", "edit", "edit"],
        )
        self.assertEqual(
            [item["workload"] for item in schedule if item["pair"] == 2],
            ["edit", "edit", "tetris", "tetris"],
        )

    def test_short_block_schedule_covers_fixed_pairs_and_anchor_ids(self):
        blocks = self.module.make_short_block_schedule(["tetris", "edit"])
        self.assertEqual(len(blocks), self.module.SHORT_BLOCK_COUNT)
        self.assertEqual(
            [block["pair_indices"] for block in blocks],
            [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]],
        )
        self.assertEqual(sum(len(block["runs"]) for block in blocks), 40)
        self.assertEqual(
            blocks[0]["pre_anchor_ids"],
            ["block-01-anchor-pre-001", "block-01-anchor-pre-002", "block-01-anchor-pre-003"],
        )
        self.assertEqual(
            blocks[-1]["post_anchor_ids"][-1], "block-05-anchor-post-003"
        )
        with self.assertRaisesRegex(ValueError, "fixes pairs"):
            self.module.make_short_block_schedule(["tetris", "edit"], 8)

    def test_option_pairing_rejects_one_sided_or_unequal_options(self):
        with self.assertRaisesRegex(ValueError, "same number"):
            self.module.validate_target_firmware_pairs(["x"], [])
        with self.assertRaisesRegex(ValueError, "same number"):
            self.module.validate_target_firmware_pairs(["x", "y"], [Path("x")])

    def test_target_command_requires_and_overrides_backend_commit(self):
        target = self.fixture_target()
        with self.assertRaisesRegex(ValueError, "override is required"):
            self.module.target_command(
                target, Path("firmware.bin"), Path("runner"), Path("report"),
                Path("uart"), Path("snapshots"), backend_commit=None,
            )
        command = self.module.target_command(
            target, Path("firmware.bin"), Path("runner"), Path("report"),
            Path("uart"), Path("snapshots"), backend_commit="b" * 40,
        )
        self.assertEqual(command[command.index("--backend-commit") + 1], "b" * 40)
        self.assertNotIn("a" * 40, command)
        self.assertIn("--scenario", command) if target.get("scenario") else None

    def test_target_command_preserves_registered_audio_observation_contract(self):
        import picocalc

        for target_id, expected in (
            ("picotetris-opt1b-vrp5", ("--expect-audio-sink-count", "1000")),
            ("picoedit-r1-vrp2f", ("--audio-analysis", "/tmp/audio-analysis.json")),
        ):
            target = picocalc.load_firmware_target(target_id)
            self.assertIsNotNone(target)
            command = self.module.target_command(
                target, Path("firmware.bin"), Path("runner"), Path("/tmp/report.json"),
                Path("/tmp/uart"), Path("/tmp/snapshots"), backend_commit="b" * 40,
            )
            self.assertIn(expected[0], command)
            self.assertEqual(command[command.index(expected[0]) + 1], expected[1])

    def test_load_shape_command_uses_short_cycle_limit_and_host_timing(self):
        command = self.module.load_shape_command(
            self.fixture_target(),
            Path("firmware.bin"),
            Path("runner"),
            Path("report.json"),
            Path("uart.bin"),
            Path("host-timing.json"),
            10_000_000,
            backend_commit="b" * 40,
        )
        self.assertEqual(command[command.index("--cycles") + 1], "10000000")
        self.assertEqual(command[command.index("--expect-stop") + 1], "cycle_limit")
        self.assertIn("--host-timing", command)
        self.assertNotIn("--scenario", command)

    def test_pilot_dispersion_uses_scaled_mad(self):
        summary = self.module._pilot_dispersion([10.0, 11.0, 12.0])
        self.assertEqual(summary["median"], 11.0)
        self.assertAlmostEqual(summary["mad"], 1.0)
        self.assertAlmostEqual(summary["scaled_mad"], 1.4826)
        self.assertAlmostEqual(summary["relative_mad"], math.exp(1.4826 / 11.0) - 1.0)

    def test_pilot_cli_fixes_cpu_and_replicate_contracts(self):
        affinity = self.module.parse_arguments(
            [
                "affinity-pilot", "--cpu", "0", "--backend", "/tmp/backend",
                "--runner", "/tmp/runner", "--output", "/tmp/affinity.json",
            ]
        )
        self.assertEqual(affinity.replicates, self.module.AFFINITY_PILOT_REPLICATES)
        cooldown = self.module.parse_arguments(
            [
                "cooldown-pilot", "--cpu", "0", "--backend", "/tmp/backend",
                "--runner", "/tmp/runner", "--output", "/tmp/cooldown.json",
            ]
        )
        self.assertEqual(cooldown.replicates, self.module.COOLDOWN_PILOT_REPLICATES)

    def test_short_block_cli_fixes_cpu_replicates_and_cooldown(self):
        args = self.module.parse_arguments(
            [
                "short-block", "--cpu", "0",
                "--baseline-backend", "/tmp/baseline",
                "--candidate-backend", "/tmp/candidate",
                "--baseline-runner", "/tmp/baseline-runner",
                "--candidate-runner", "/tmp/candidate-runner",
                "--admission-record", "/tmp/admission",
                "--output", "/tmp/short-block",
            ]
        )
        self.assertEqual(args.cycles, self.module.SHORT_BLOCK_DEFAULT_CYCLES)
        self.assertEqual(args.replicates, self.module.SHORT_BLOCK_ANCHOR_REPLICATES)
        self.assertEqual(args.inter_run_cooldown_seconds, 0.0)

    def test_primary_metric_fields_select_cpu_or_wall_clock(self):
        self.assertEqual(
            self.module.primary_metric_fields("cpu-time"),
            {
                "raw": "cycles_per_emulation_cpu_second",
                "corrected": "corrected_emulated_cycles_per_cpu_second",
                "predicted": "predicted_anchor_cpu_throughput",
            },
        )
        self.assertEqual(
            self.module.primary_metric_fields("wall-time")["raw"],
            "emulated_cycles_per_wall_second",
        )
        with self.assertRaisesRegex(ValueError, "unknown primary metric"):
            self.module.primary_metric_fields("process-time")

    def test_ab_cli_defaults_to_cpu_time_primary_metric(self):
        args = self.module.parse_arguments(
            [
                "ab", "--cpu", "0",
                "--baseline-backend", "/tmp/baseline",
                "--candidate-backend", "/tmp/candidate",
                "--baseline-runner", "/tmp/baseline-runner",
                "--candidate-runner", "/tmp/candidate-runner",
                "--admission-record", "/tmp/admission",
                "--batch-id", "fixture-ab",
                "--output", "/tmp/ab",
            ]
        )
        self.assertEqual(args.primary_metric, "cpu-time")

    def test_registered_report_follows_validation_evidence_record(self):
        report = {"cycles": 123, "observable": "fixed"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            validation_path = root / "firmware-validation" / "validations" / "fixture.json"
            record_path = root / "firmware-validation" / "records" / "fixture" / "record.json"
            report_path = root / "firmware-validation" / "records" / "fixture" / "run-report.json"
            validation_path.parent.mkdir(parents=True)
            record_path.parent.mkdir(parents=True)
            report_path.write_text(json.dumps(report), encoding="utf-8")
            report_sha256 = self.module.sha256_file(report_path)
            record_path.write_text(
                json.dumps(
                    {
                        "firmware_run": {
                            "report": {
                                "path": "firmware-validation/records/fixture/run-report.json",
                                "sha256": report_sha256,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            record_sha256 = self.module.sha256_file(record_path)
            validation_path.write_text(
                json.dumps(
                    {
                        "evidence": {
                            "record": "firmware-validation/records/fixture/record.json",
                            "sha256": record_sha256,
                        }
                    }
                ),
                encoding="utf-8",
            )
            target = {
                "validation": {
                    "record": "firmware-validation/validations/fixture.json"
                }
            }
            with mock.patch.object(self.module, "ROOT", root):
                self.assertEqual(self.module._registered_report({"target": target}), report)

            record_path.write_text(record_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with mock.patch.object(self.module, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "evidence record SHA-256 mismatch"):
                    self.module._registered_report({"target": target})

    def test_runner_embedded_commit_mismatch_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "picocalc-run"
            runner.write_bytes(b"runner-build-" + b"a" * 40)
            self.module.validate_runner_embedded_commit(runner, "a" * 40)
            with self.assertRaisesRegex(ValueError, "does not embed"):
                self.module.validate_runner_embedded_commit(runner, "b" * 40)

    def test_runner_requires_build_provenance_bound_to_binary_and_features(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "picocalc-run"
            commit = "a" * 40
            runner.write_bytes(b"runner-build-" + commit.encode("ascii"))
            effective = self.module.effective_feature_set(["behavior-trace"])
            provenance = {
                "schema_id": self.module.BUILD_PROVENANCE_SCHEMA_ID,
                "schema_version": self.module.BUILD_PROVENANCE_VERSION,
                "role": "baseline_production",
                "backend_commit": commit,
                "backend_dirty": False,
                "runner_sha256": self.module.sha256_file(runner),
                "feature_set": effective,
                "cargo_features": effective,
                "cargo_tree_features": effective,
                "effective_features_sha256": self.module.canonical_json_sha256(effective),
                "lockfile_sha256": "b" * 64,
                "cargo_tree_sha256": "c" * 64,
                "cargo_argv": ["cargo", "build", "--locked", "--release"],
                "rustc_version": "rustc 1.90.0",
                "cargo_version": "cargo 1.90.0",
            }
            self.module.runner_provenance_path(runner).write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            result = self.module.validate_runner_provenance(
                runner, commit, ["behavior-trace"], expected_role="baseline_production"
            )
            self.assertEqual(result["feature_set"], effective)
            with self.assertRaisesRegex(ValueError, "feature set"):
                self.module.validate_runner_provenance(
                    runner, commit, ["cpu-application-profiler"], expected_role="baseline_production"
                )

    def test_cargo_tree_root_features_are_parsed_and_default_is_normalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary) / "tree.txt"
            tree.write_text(
                "picocalc-harness v0.1.0 (/tmp/backend) behavior-trace,default,sd-gen1-multiblock\n",
                encoding="utf-8",
            )
            self.assertEqual(
                self.module.cargo_tree_root_features(tree),
                ["behavior-trace", "sd-gen1-multiblock"],
            )
            tree.write_text(
                "picocalc-harness v0.1.0 (/tmp/backend) default\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "no effective"):
                self.module.cargo_tree_root_features(tree)

    def test_production_sidecar_role_requires_explicit_shared_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Path(temporary) / "picocalc-run"
            commit = "a" * 40
            runner.write_bytes(b"runner-build-" + commit.encode("ascii"))
            effective = self.module.effective_feature_set([])
            provenance = {
                "schema_id": self.module.BUILD_PROVENANCE_SCHEMA_ID,
                "schema_version": self.module.BUILD_PROVENANCE_VERSION,
                "role": "production",
                "backend_commit": commit,
                "backend_dirty": False,
                "runner_sha256": self.module.sha256_file(runner),
                "feature_set": effective,
                "cargo_features": effective,
                "cargo_tree_features": effective,
                "effective_features_sha256": self.module.canonical_json_sha256(effective),
                "lockfile_sha256": "b" * 64,
                "cargo_tree_sha256": "c" * 64,
                "cargo_argv": ["cargo", "build", "--locked", "--release"],
                "rustc_version": "rustc 1.90.0",
                "cargo_version": "cargo 1.90.0",
            }
            self.module.runner_provenance_path(runner).write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "role differs"):
                self.module.validate_runner_provenance(
                    runner, commit, [], expected_role="baseline_trace"
                )
            self.assertEqual(
                self.module.validate_runner_provenance(
                    runner, commit, [], expected_role="baseline_production",
                    allow_production_role=True,
                )["role"],
                "production",
            )

    def test_projection_removes_only_top_level_backend_identity(self):
        report = {
            "backend_build": {"commit": "a" * 40, "dirty": False},
            "backend_commit": "a" * 40,
            "cycles": 10,
            "audio_sink": {
                "dma_write_count": 1000,
                "pcm_sha256": "b" * 64,
                "expected_count": 1000,
                "expected_sha256": "b" * 64,
            },
            "nested": {"backend_commit": "guest-visible"},
        }
        projection = self.module.guest_observation_projection(report)
        self.assertNotIn("backend_build", projection)
        self.assertNotIn("backend_commit", projection)
        self.assertNotIn("expected_count", projection["audio_sink"])
        self.assertNotIn("expected_sha256", projection["audio_sink"])
        self.assertEqual(projection["audio_sink"]["dma_write_count"], 1000)
        self.assertEqual(projection["nested"]["backend_commit"], "guest-visible")
        changed = dict(report)
        changed["cycles"] = 11
        self.assertNotEqual(
            self.module.guest_observation_sha256(report),
            self.module.guest_observation_sha256(changed),
        )

    def test_admission_identity_allows_only_documented_production_role_transition(self):
        base = {
            "commit": "a" * 40,
            "dirty": False,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
            "feature_set": ["sd-gen1-multiblock"],
            "role": "baseline_production",
            "provenance_role": "baseline_production",
        }
        production = dict(base)
        production.update(
            {
                "build_provenance_sha256": "d" * 64,
                "provenance_role": "production",
            }
        )
        self.assertTrue(self.module._admission_baseline_identity_matches(base, production))
        changed_runner = dict(production, runner_sha256="e" * 64)
        self.assertFalse(self.module._admission_baseline_identity_matches(base, changed_runner))
        unrecognized_role = dict(production, provenance_role="candidate_production")
        self.assertFalse(self.module._admission_baseline_identity_matches(base, unrecognized_role))

    def test_log_ratio_is_candidate_over_baseline_independent_of_order(self):
        ratio_ab = self.module.log_ratio(110.0, 100.0)
        ratio_ba = self.module.log_ratio(110.0, 100.0)
        self.assertAlmostEqual(ratio_ab, ratio_ba)
        self.assertAlmostEqual(math.exp(ratio_ab) - 1.0, 0.10)

    def test_statistics_use_df9_t_critical_and_median_iqr_definition(self):
        values = [math.log(0.98 + index * 0.01) for index in range(10)]
        summary = self.module.summarize_log_effect(values)
        self.assertEqual(summary["n"], 10)
        self.assertEqual(self.module.T_CRITICAL_95[9], 2.262157)
        self.assertAlmostEqual(
            summary["geometric_mean_effect"],
            math.exp(sum(values) / 10.0) - 1.0,
        )
        self.assertAlmostEqual(summary["percent_effect"]["median"], 0.025)
        self.assertAlmostEqual(summary["percent_effect"]["q1"], 0.0)
        self.assertAlmostEqual(summary["percent_effect"]["q3"], 0.05)
        self.assertAlmostEqual(summary["percent_effect"]["iqr"], 0.05)
        self.assertEqual(len(summary["ci95_log_ratio"]), 2)

    def test_null_control_uses_ten_pair_means_and_fixed_effect_ci_gates(self):
        workloads = ["tetris", "edit"]
        pair_results = [
            {
                "workload": workload,
                "pair_index": pair,
                "pair_log_ratio": 0.0,
                "corrected_pair_log_ratio": 0.0,
            }
            for pair in range(1, 11)
            for workload in workloads
        ]
        result = self.module.evaluate_null_control(pair_results, workloads)
        self.assertTrue(result["pass"])
        self.assertEqual(result["workloads"]["tetris"]["raw"]["n"], 10)
        self.assertEqual(result["combined"]["raw"]["n"], 10)
        self.assertEqual(result["checks"][-1]["max_abs_effect"], 0.01)
        for item in pair_results:
            if item["workload"] == "tetris":
                item["pair_log_ratio"] = math.log(1.03)
        failed = self.module.evaluate_null_control(pair_results, workloads)
        self.assertFalse(failed["pass"])
        self.assertIn("tetris raw effect/CI", failed["reasons"])

    def test_p2_profile_requires_pending_exception_instrumentation(self):
        with self.assertRaisesRegex(ValueError, "pending-exception-fast-reject"):
            self.module.validate_profile_feature_set(
                "P2-A", ["cpu-application-profiler"]
            )
        self.assertEqual(
            self.module.validate_profile_feature_set(
                "P2-A", ["cpu-application-profiler", "pending-exception-fast-reject"]
            ),
            ["cpu-application-profiler", "pending-exception-fast-reject"],
        )

    def test_p2_ab_requires_diagnostic_profile_record(self):
        with self.assertRaisesRegex(ValueError, "--profile-record"):
            self.module._require_profile_gate(None, [], {"commit": "a" * 40}, 0)

    def test_p2_profile_gate_checks_cpu_and_passing_decision(self):
        workloads = [
            {
                "id": workload_id,
                "revision": revision,
                "firmware_sha256": "f" * 64,
                "scenario_sha256": "s" * 64,
                "contract_sha256": "c" * 64,
            }
            for workload_id, revision in (
                ("picotetris-opt1b-vrp5", 10),
                ("picoedit-r1-vrp2f", 4),
            )
        ]
        features = [
            "cpu-application-profiler",
            "pending-exception-fast-reject",
            "sd-gen1-multiblock",
        ]
        identity = {
            "commit": "a" * 40,
            "feature_set": features,
        }

        def exception():
            return {
                "polls": 10,
                "reject_no_candidate": 6,
                "reject_primask": 1,
                "reject_active_handler": 1,
                "entries": 2,
                "source": {"pendsv": 1, "systick": 0, "nvic": 1},
            }

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "rp2040-cpu-p2-a-profile-fixture"
            profile_dir = record / "profile"
            profile_dir.mkdir(parents=True)
            manifest = {
                "record_type": self.module.RECORD_TYPE,
                "record_version": self.module.SCHEMA_VERSION,
                "record_id": record.name,
                "candidate_id": "P2-A",
                "workloads": workloads,
                "measurement_cpu": 0,
                "backend_identities": {"candidate_profile": identity},
                "feature_set": features,
            }
            decision = {
                "decision_kind": "profile",
                "status": "pass",
            }
            (record / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (record / "decision.json").write_text(json.dumps(decision), encoding="utf-8")
            (record / "SHA256SUMS").write_text("", encoding="utf-8")
            for workload in workloads:
                profile = {
                    "candidate_id": "P2-A",
                    "workload": {
                        key: workload[key]
                        for key in ("id", "revision", "firmware_sha256", "scenario_sha256")
                    },
                    "feature_set": features,
                    "counters": {"exception": exception()},
                    "cores": [{"exception": exception()}],
                    "invariants": {
                        "exception_poll_conservation": True,
                        "exception_source_conservation": True,
                    },
                }
                path = profile_dir / "{}-r{}.json".format(workload["id"], workload["revision"])
                path.write_text(json.dumps(profile), encoding="utf-8")
            with mock.patch.object(self.module, "_validate_record_root"), \
                 mock.patch.object(self.module, "_verify_existing_sha256sums"):
                self.module._require_profile_gate(record, workloads, {"commit": "a" * 40}, 0)
                with self.assertRaisesRegex(ValueError, "CPU differs"):
                    self.module._require_profile_gate(record, workloads, {"commit": "a" * 40}, 1)
                manifest["measurement_cpu"] = 0
                decision["status"] = "invalid"
                (record / "decision.json").write_text(json.dumps(decision), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "decision is not passing"):
                    self.module._require_profile_gate(record, workloads, {"commit": "a" * 40}, 0)

    def test_p2_profile_verifies_aggregate_and_core_exception_conservation(self):
        verifier = load_verifier()

        def exception():
            return {
                "polls": 10,
                "reject_no_candidate": 6,
                "reject_primask": 1,
                "reject_active_handler": 1,
                "entries": 2,
                "source": {"pendsv": 1, "systick": 0, "nvic": 1},
            }

        profile = {
            "counters": {"exception": exception()},
            "cores": [{"exception": exception()}, {"exception": exception()}],
            "invariants": {
                "exception_poll_conservation": True,
                "exception_source_conservation": True,
            },
        }
        problems = []
        verifier._verify_pending_exception_poll_equation(
            Path("profile.json"), profile, problems
        )
        self.assertEqual(problems, [])

        profile["counters"]["exception"]["polls"] = 11
        problems = []
        verifier._verify_pending_exception_poll_equation(
            Path("profile.json"), profile, problems
        )
        self.assertTrue(any("aggregate exception polls" in item for item in problems))

        profile["counters"]["exception"] = exception()
        profile["cores"][0]["exception"]["source"]["nvic"] = 2
        problems = []
        verifier._verify_pending_exception_poll_equation(
            Path("profile.json"), profile, problems
        )
        self.assertTrue(any("core-0 exception entries" in item for item in problems))

        bad_profile = {
            "counters": {"exception": exception()},
            "cores": [{"exception": exception()}],
            "invariants": {
                "exception_poll_conservation": True,
                "exception_source_conservation": True,
            },
        }
        bad_profile["counters"]["exception"]["source"]["nvic"] = 2
        with self.assertRaisesRegex(ValueError, "source conservation"):
            self.module.validate_pending_exception_profile(bad_profile)

    def test_guest_projection_pair_rejects_one_bit_difference(self):
        baseline = {"cycles": 10, "framebuffer": {"rgb565_sha256": "a"}}
        candidate = {"cycles": 10, "framebuffer": {"rgb565_sha256": "b"}}
        with self.assertRaisesRegex(ValueError, "projection mismatch"):
            self.module.validate_guest_projection_pair(baseline, candidate)

    def test_behavior_pair_checks_projection_digest_and_domain_summary(self):
        projection = {
            "event_trace": {
                "schema_version": 2,
                "canonical_encoding": "PICOEM-EVENT-v1",
                "streaming": True,
                "retains_event_array": False,
                "total_events": 1,
                "sha256": "b" * 64,
                "domains": [{"name": "clock", "events": 1, "sha256": "a" * 64}],
            },
            "cycles": 10,
        }
        artifact = {
            "schema_version": 1,
            "mode": "correctness_trace_on",
            "valid_for_wall_time": False,
            "normal_report_schema_version": 8,
            "behavior_projection_encoding": "sorted-json-v1",
            "backend_build": {"commit": "a" * 40, "dirty": False},
            "behavior_projection": projection,
            "behavior_sha256": self.module.canonical_json_sha256(projection),
        }
        self.module.validate_behavior_pair(artifact, artifact)
        changed = dict(artifact)
        changed["behavior_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "does not match projection"):
            self.module.validate_behavior_pair(artifact, changed)

    def test_report_validation_skips_legacy_backend_commit_hash_check(self):
        target = self.fixture_target()
        workload = {
            "target": target,
            "firmware_sha256": "f" * 64,
        }
        report = {
            "schema_version": 8,
            "verdict": {"status": "pass"},
            "backend_build": {"commit": "b" * 40, "dirty": False},
            "firmware": {"sha256": "f" * 64},
            "step_quantum": 1,
            "cycle_limit": 123,
            "exception": None,
            "error": None,
            "unsupported_mmio": [],
            "stop_reason": "scenario_done",
        }
        self.module.validate_report(workload, report, "b" * 40)

    def test_calibration_drift_invalidates_above_two_percent(self):
        valid = self.module.calibration_drift([100.0, 101.0, 99.0], [101.0, 100.0, 102.0])
        invalid = self.module.calibration_drift([100.0, 101.0, 99.0], [103.0, 104.0, 105.0])
        self.assertTrue(valid["valid"])
        self.assertFalse(invalid["valid"])
        self.assertGreater(invalid["relative_drift"], 0.02)
        self.assertEqual(valid["pre_values"], [100.0, 101.0, 99.0])
        self.assertEqual(valid["post_values"], [101.0, 100.0, 102.0])

    def test_interleaved_anchor_policy_is_fixed(self):
        policy = self.module.interleaved_anchor_measurement_policy()
        self.assertEqual(policy["calibration_method"], "interleaved-anchor-v1")
        self.assertEqual(policy["anchor_layout"], {
            "pre_count": 3,
            "after_measured_runs": [10, 20, 30],
            "post_count": 3,
        })
        self.assertEqual(len(policy["anchor_run_ids"]), 9)
        self.assertEqual(policy["anchor_residual_threshold"], 0.02)

    def test_interleaved_anchor_model_and_interpolation_are_deterministic(self):
        anchors = [
            {"anchor_id": "a0", "elapsed_seconds": 0.0, "throughput": 100.0},
            {"anchor_id": "a1", "elapsed_seconds": 10.0, "throughput": 110.0},
            {"anchor_id": "a2", "elapsed_seconds": 20.0, "throughput": 120.0},
        ]
        model = self.module._anchor_log_linear_model(anchors)
        self.assertTrue(model["valid"])
        self.assertEqual(model["model"], "global-log-linear-v1")
        self.assertAlmostEqual(
            self.module.interpolate_anchor_throughput(anchors, 5.0),
            math.sqrt(100.0 * 110.0),
        )
        with self.assertRaisesRegex(ValueError, "outside"):
            self.module.interpolate_anchor_throughput(anchors, 21.0)

    def test_replicated_anchor_policy_is_fixed(self):
        policy = self.module.interleaved_anchor_measurement_policy_v2()
        self.assertEqual(policy["calibration_method"], "interleaved-anchor-v2")
        self.assertEqual(policy["anchor_layout"], {
            "pre_count": 3,
            "after_measured_runs": [10, 20, 30],
            "post_count": 3,
            "replicates_per_group": 3,
        })
        self.assertEqual(policy["anchor_group_ids"], ["pre", "after-010", "after-020", "after-030", "post"])
        self.assertEqual(len(policy["anchor_run_ids"]), 15)
        self.assertEqual(policy["anchor_residual_threshold"], 0.02)
        self.assertEqual(policy["anchor_group_dispersion_threshold"], 0.02)
        self.assertTrue(policy["anchor_group_dispersion_gate_used"])

    def test_replicated_anchor_v3_policy_is_fixed(self):
        policy = self.module.interleaved_anchor_measurement_policy_v3()
        self.assertEqual(policy["calibration_method"], "interleaved-anchor-v3")
        self.assertEqual(policy["anchor_layout"], {
            "pre_count": 3,
            "after_measured_runs": [5, 10, 15, 20, 25, 30, 35],
            "post_count": 3,
            "replicates_per_group": 3,
        })
        self.assertEqual(
            policy["anchor_group_ids"],
            ["pre", "after-005", "after-010", "after-015", "after-020", "after-025", "after-030", "after-035", "post"],
        )
        self.assertEqual(len(policy["anchor_run_ids"]), 27)
        self.assertEqual(policy["anchor_local_residual_method"], "leave-one-group-out-log-linear-v1")
        self.assertEqual(policy["anchor_local_residual_threshold"], 0.02)
        self.assertTrue(policy["global_residual_diagnostic_only"])

    def test_v3_piecewise_model_has_fixed_local_residual_gate(self):
        groups = [
            {"group_id": "g{}".format(index), "elapsed_seconds": index * 10.0, "throughput": 100.0 + index}
            for index in range(9)
        ]
        model = self.module._anchor_piecewise_local_residual_model(groups)
        self.assertEqual(model["model"], "piecewise-log-linear-v3")
        self.assertEqual(model["knot_ids"], ["g{}".format(index) for index in range(9)])
        self.assertTrue(model["valid"])
        self.assertEqual(model["local_residual_method"], "leave-one-group-out-log-linear-v1")
        self.assertIn("global_diagnostic", model)
        curved = [dict(group) for group in groups]
        curved[4]["throughput"] = 130.0
        curved_model = self.module._anchor_piecewise_local_residual_model(curved)
        self.assertFalse(curved_model["valid"])
        self.assertGreater(curved_model["max_relative_residual"], 0.02)

    def test_v3_pair_sensitivity_gate_rejects_large_correction_delta(self):
        pair_results = [
            {
                "pair_log_ratio": 0.0,
                "corrected_pair_log_ratio": math.log(1.03),
            }
        ]
        sensitivity = self.module._pair_level_sensitivity(pair_results)
        self.assertEqual(sensitivity["n"], 1)
        self.assertGreater(
            sensitivity["max_abs_delta_log_ratio"],
            self.module.CALIBRATION_PAIR_SENSITIVITY_LIMIT,
        )
        self.assertFalse(
            sensitivity["max_abs_delta_log_ratio"]
            <= self.module.CALIBRATION_PAIR_SENSITIVITY_LIMIT
        )

    def test_v3_complete_27_anchor_fixture_aggregates_and_models(self):
        specs = self.module._interleaved_anchor_v3_group_specs()
        anchors = []
        for group_index, spec in enumerate(specs):
            for replicate in range(1, 4):
                anchors.append(
                    {
                        "anchor_id": "anchor-{}-{:03d}".format(spec["group_id"], replicate),
                        "group_id": spec["group_id"],
                        "elapsed_seconds": group_index * 10.0 + replicate / 100.0,
                        "throughput": 100.0 * math.exp(0.01 * group_index),
                    }
                )
        self.assertEqual(len(anchors), 27)
        groups = self.module._aggregate_anchor_groups(anchors, specs)
        self.assertEqual(len(groups), 9)
        self.assertEqual([group["anchor_count"] for group in groups], [3] * 9)
        self.assertTrue(all(group["dispersion_valid"] for group in groups))
        model = self.module._anchor_piecewise_local_residual_model(groups)
        self.assertTrue(model["valid"])
        self.assertEqual(model["knot_ids"], [spec["group_id"] for spec in specs])
        self.assertEqual(len(model["residuals"]), 9)

    def test_host_stability_summary_has_fixed_mad_and_adjacent_gates(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        samples = [
            {
                "sample_id": "sentinel-{:03d}".format(index),
                "throughput": 100.0 * (1.0 + (index - 5) * 0.0005),
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "host_snapshot_start": snapshot,
                "host_snapshot_end": snapshot,
            }
            for index in range(1, 11)
        ]
        summary = self.module.summarize_host_stability(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertTrue(summary["valid"])
        self.assertTrue(summary["gates"]["relative_mad_valid"])
        self.assertTrue(summary["gates"]["adjacent_log_throughput_valid"])
        self.assertEqual(summary["sample_count"], 10)

    def test_host_stability_summary_rejects_regime_step(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        samples = [
            {
                "sample_id": "sentinel-{:03d}".format(index),
                "throughput": 100.0 if index <= 5 else 130.0,
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "host_snapshot_start": snapshot,
                "host_snapshot_end": snapshot,
            }
            for index in range(1, 11)
        ]
        summary = self.module.summarize_host_stability(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertFalse(summary["valid"])
        self.assertFalse(summary["gates"]["adjacent_log_throughput_valid"])
        self.assertFalse(summary["gates"]["relative_mad_valid"])

    def test_host_stability_v2_groups_three_replicates_and_keeps_raw_diagnostic(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        group_medians = [100.0, 100.8, 101.5, 101.2]
        samples = []
        for group_index, median in enumerate(group_medians):
            for replicate in range(3):
                samples.append(
                    {
                        "sample_id": "sentinel-{:03d}".format(len(samples) + 1),
                        "throughput": median * (1.0 + (replicate - 1) * 0.0005),
                        "backend_commit": identity["commit"],
                        "runner_sha256": identity["runner_sha256"],
                        "build_provenance_sha256": identity["build_provenance_sha256"],
                        "host_snapshot_start": snapshot,
                        "host_snapshot_end": snapshot,
                    }
                )
        summary = self.module.summarize_host_stability_v2(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["sample_count"], 12)
        self.assertEqual(len(summary["group_medians"]), 4)
        self.assertEqual(len(summary["group_relative_mads"]), 4)
        self.assertEqual(len(summary["adjacent_abs_log_deltas"]), 11)
        self.assertTrue(summary["gates"]["group_adjacent_log_throughput_valid"])
        self.assertTrue(summary["gates"]["group_relative_mad_valid"])

    def test_host_stability_v2_rejects_group_dispersion_even_when_group_medians_are_stable(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        samples = []
        for group_index in range(4):
            values = [100.0, 100.5, 101.0]
            if group_index == 1:
                values = [96.0, 100.0, 104.0]
            for value in values:
                samples.append(
                    {
                        "sample_id": "sentinel-{:03d}".format(len(samples) + 1),
                        "throughput": value,
                        "backend_commit": identity["commit"],
                        "runner_sha256": identity["runner_sha256"],
                        "build_provenance_sha256": identity["build_provenance_sha256"],
                        "host_snapshot_start": snapshot,
                        "host_snapshot_end": snapshot,
                    }
                )
        summary = self.module.summarize_host_stability_v2(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertFalse(summary["valid"])
        self.assertFalse(summary["gates"]["group_relative_mad_valid"])
        self.assertTrue(summary["gates"]["group_adjacent_log_throughput_valid"])

    def test_host_stability_v3_requires_cpu_pressure_and_scheduler_snapshots(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
            "cpu_pressure": {
                "some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 1.0},
                "full": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0.0},
            },
            "proc_cpu_stat": {
                "user": 100, "nice": 0, "system": 50, "idle": 1000, "iowait": 0,
                "irq": 0, "softirq": 0, "steal": 2, "guest": 0, "guest_nice": 0,
            },
            "cgroup_cpu_stat": {
                "usage_usec": 1000, "user_usec": 900, "system_usec": 100,
                "nice_usec": 0, "nr_periods": 1, "nr_throttled": 0, "throttled_usec": 0,
            },
            "scheduler": {"policy": 0, "priority": 0, "nice": 0},
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        samples = [
            {
                "sample_id": "sentinel-{:03d}".format(index),
                "throughput": 100.0 + (index // 4) * 0.2,
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "host_snapshot_start": snapshot,
                "host_snapshot_end": snapshot,
            }
            for index in range(1, 13)
        ]
        summary = self.module.summarize_host_stability_v3(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertTrue(summary["valid"])
        self.assertTrue(summary["gates"]["diagnostics_valid"])
        missing = [dict(sample) for sample in samples]
        missing[0]["host_snapshot_start"] = dict(snapshot)
        missing[0]["host_snapshot_start"].pop("scheduler")
        missing_summary = self.module.summarize_host_stability_v3(
            missing, expected_cpu=11, expected_identity=identity
        )
        self.assertFalse(missing_summary["valid"])
        self.assertFalse(missing_summary["gates"]["diagnostics_valid"])

    def test_cpu_time_attribution_reports_wall_and_cpu_metrics_without_promotion(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        samples = [
            {
                "cycles": 1000,
                "wall_seconds": 10.0 + index * 0.1,
                "user_seconds": 8.0,
                "system_seconds": 1.0,
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "host_snapshot_start": snapshot,
                "host_snapshot_end": snapshot,
            }
            for index in range(4)
        ]
        summary = self.module.summarize_cpu_time_attribution(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertTrue(summary["valid"])
        self.assertGreater(summary["cpu_throughput"]["median"], summary["wall_throughput"]["median"])
        self.assertEqual(len(summary["cpu_throughputs"]), 4)
        self.assertIn("cpu_to_wall_ratio", summary)

    def test_cpu_time_attribution_prefers_in_process_run_loop_clock(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
        }
        samples = [
            {
                "cycles": 1000,
                "wall_seconds": 10.0,
                "emulation_wall_seconds": 2.0,
                "emulation_cpu_seconds": 1.0,
                "user_seconds": 0.01,
                "system_seconds": 0.01,
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "host_snapshot_start": snapshot,
                "host_snapshot_end": snapshot,
            }
            for _ in range(4)
        ]
        summary = self.module.summarize_cpu_time_attribution(
            samples, expected_cpu=11, expected_identity=identity
        )
        self.assertEqual(summary["primary_cpu_time_scope"], "in_process_run_loop")
        self.assertAlmostEqual(summary["cpu_throughput"]["median"], 1000.0)

    def test_host_stability_gate_requires_passing_pointer_record(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "dirty": False,
            "runner_sha256": "b" * 64,
            "feature_set": ["sd-gen1-multiblock"],
            "build_provenance_sha256": "c" * 64,
            "role": "baseline_production",
            "provenance_role": "baseline_production",
        }
        samples = [
            {
                "sample_id": "sentinel-{:03d}".format(index),
                "protocol_elapsed_seconds": 1.0,
                "throughput": 100.0,
                "cycles": 123,
                "wall_seconds": 1.23,
                "backend_commit": identity["commit"],
                "runner_sha256": identity["runner_sha256"],
                "build_provenance_sha256": identity["build_provenance_sha256"],
                "host_snapshot_start": snapshot,
                "host_snapshot_end": snapshot,
            }
            for index in range(1, 11)
        ]
        workload = {
            "id": "picotetris-opt1b-vrp5",
            "revision": 10,
            "firmware_sha256": "d" * 64,
            "scenario_sha256": "e" * 64,
            "contract_sha256": "f" * 64,
        }
        record = {
            "schema_id": self.module.HOST_STABILITY_SCHEMA_ID,
            "schema_version": 1,
            "artifact_type": "host-stability",
            "record_id": "rp2040-cpu-host-stability-fixture",
            "status": "pass",
            "measurement_policy": self.module.host_stability_measurement_policy(),
            "measurement_cpu": 11,
            "cpu_affinity": {"requested": 11, "effective": [11]},
            "inter_run_cooldown_seconds": 60.0,
            "workload": workload,
            "backend_identity": identity,
            "samples": samples,
            "summary": self.module.summarize_host_stability(
                samples, expected_cpu=11, expected_identity=identity
            ),
            "reasons": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            record_path = Path(temporary) / "host-stability.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            self.module._require_host_stability_gate(
                record_path,
                [workload],
                identity,
                11,
                60.0,
            )
            record["status"] = "invalid"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not passing"):
                self.module._require_host_stability_gate(
                    record_path,
                    [workload],
                    identity,
                    11,
                    60.0,
                )

    def test_host_stability_gate_accepts_v2_grouped_record(self):
        snapshot = {
            "model": "test-host",
            "logical_cpus": 12,
            "reported_mhz": 3693.107,
            "loadavg": [0.1, 0.2, 0.3],
            "allowed_cpus": [11],
            "platform": "test-platform",
            "kernel": "test-kernel",
        }
        identity = {
            "commit": "a" * 40,
            "dirty": False,
            "runner_sha256": "b" * 64,
            "feature_set": ["sd-gen1-multiblock"],
            "build_provenance_sha256": "c" * 64,
            "role": "baseline_production",
            "provenance_role": "baseline_production",
        }
        samples = []
        for index in range(12):
            samples.append(
                {
                    "sample_id": "sentinel-{:03d}".format(index + 1),
                    "protocol_elapsed_seconds": 1.0,
                    "throughput": 100.0 + (index // 3) * 0.5,
                    "cycles": 123,
                    "wall_seconds": 1.23,
                    "backend_commit": identity["commit"],
                    "runner_sha256": identity["runner_sha256"],
                    "build_provenance_sha256": identity["build_provenance_sha256"],
                    "host_snapshot_start": snapshot,
                    "host_snapshot_end": snapshot,
                }
            )
        workload = {
            "id": "picotetris-opt1b-vrp5",
            "revision": 10,
            "firmware_sha256": "d" * 64,
            "scenario_sha256": "e" * 64,
            "contract_sha256": "f" * 64,
        }
        record = {
            "schema_id": self.module.HOST_STABILITY_SCHEMA_ID,
            "schema_version": 1,
            "artifact_type": "host-stability",
            "record_id": "rp2040-cpu-host-stability-v2-fixture",
            "status": "pass",
            "measurement_policy": self.module.host_stability_measurement_policy_v2(),
            "measurement_cpu": 11,
            "cpu_affinity": {"requested": 11, "effective": [11]},
            "inter_run_cooldown_seconds": 60.0,
            "workload": workload,
            "backend_identity": identity,
            "samples": samples,
            "summary": self.module.summarize_host_stability_v2(
                samples, expected_cpu=11, expected_identity=identity
            ),
            "reasons": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            record_path = Path(temporary) / "host-stability-v2.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            accepted = self.module._require_host_stability_gate(
                record_path,
                [workload],
                identity,
                11,
                60.0,
            )
            self.assertEqual(accepted["record_id"], record["record_id"])

    def test_replicated_anchor_group_aggregation_uses_log_median_and_mad(self):
        anchors = []
        for group_index, spec in enumerate(self.module._interleaved_anchor_v2_group_specs()):
            for index in range(1, 4):
                anchors.append({
                    "anchor_id": "anchor-{}-{:03d}".format(spec["group_id"], index),
                    "group_id": spec["group_id"],
                    "elapsed_seconds": group_index * 10.0 + index,
                    "throughput": 100.0 + group_index * 10.0 + (index - 2) * 0.1,
                })
        groups = self.module._aggregate_anchor_groups(
            anchors, self.module._interleaved_anchor_v2_group_specs()
        )
        self.assertEqual([group["group_id"] for group in groups], ["pre", "after-010", "after-020", "after-030", "post"])
        self.assertEqual([group["anchor_count"] for group in groups], [3] * 5)
        self.assertAlmostEqual(groups[0]["throughput"], 100.0)
        self.assertGreater(groups[0]["relative_mad"], 0.0)
        self.assertTrue(all(group["dispersion_valid"] for group in groups))
        model = self.module._anchor_log_linear_model(groups, model_name="global-log-linear-v2")
        self.assertEqual(model["model"], "global-log-linear-v2")
        self.assertTrue(model["valid"])
        unstable = [dict(anchor) for anchor in anchors]
        for anchor in unstable:
            if anchor["group_id"] == "after-020" and anchor["anchor_id"].endswith("002"):
                anchor["throughput"] *= 1.10
            elif anchor["group_id"] == "after-020" and anchor["anchor_id"].endswith("003"):
                anchor["throughput"] *= 0.90
        unstable_group = self.module._aggregate_anchor_groups(
            unstable, self.module._interleaved_anchor_v2_group_specs()
        )
        self.assertFalse(unstable_group[2]["dispersion_valid"])
        with self.assertRaisesRegex(ValueError, "replicates"):
            self.module._aggregate_anchor_groups(
                anchors[:-1], self.module._interleaved_anchor_v2_group_specs()
            )

    def test_ab_inter_run_cooldown_is_fixed_before_measurement(self):
        self.assertEqual(
            self.module.validate_inter_run_cooldown(
                self.module.AB_INTER_RUN_COOLDOWN_SECONDS
            ),
            self.module.AB_INTER_RUN_COOLDOWN_SECONDS,
        )
        with self.assertRaisesRegex(ValueError, "fixed at 60"):
            self.module.validate_inter_run_cooldown(0.0)
        with self.assertRaisesRegex(ValueError, "fixed at 60"):
            self.module.validate_inter_run_cooldown(float("nan"))

    def test_calibration_sleeps_between_guest_runs(self):
        measurement = {
            "measurement": {"emulated_cycles_per_wall_second": 123.0}
        }
        with mock.patch.object(self.module, "run_guest", return_value=measurement) as run_guest:
            with mock.patch.object(self.module.time, "sleep") as sleep:
                values = self.module._run_calibration(
                    {}, Path("backend"), Path("runner"), 3,
                    inter_run_cooldown_seconds=self.module.AB_INTER_RUN_COOLDOWN_SECONDS,
                )
        self.assertEqual(values, [123.0, 123.0, 123.0])
        self.assertEqual(run_guest.call_count, 3)
        self.assertEqual(
            sleep.call_args_list,
            [mock.call(self.module.AB_INTER_RUN_COOLDOWN_SECONDS)] * 3,
        )

    def test_cpu_affinity_fails_closed_when_kernel_does_not_apply_request(self):
        with mock.patch.object(self.module.os, "sched_getaffinity", side_effect=[{0, 1}, {0}]), \
             mock.patch.object(self.module.os, "sched_setaffinity") as set_affinity:
            self.assertEqual(self.module._set_cpu_affinity(0), [0, 1])
            set_affinity.assert_called_once_with(0, {0})

        with mock.patch.object(self.module.os, "sched_getaffinity", side_effect=[{0, 1}, {1}]), \
             mock.patch.object(self.module.os, "sched_setaffinity") as set_affinity:
            with self.assertRaisesRegex(ValueError, "was not applied"):
                self.module._set_cpu_affinity(0)
            self.assertEqual(set_affinity.call_args_list, [mock.call(0, {0}), mock.call(0, {0, 1})])

    def test_record_root_must_be_a_canonical_direct_child(self):
        records_root = ROOT / "firmware-validation" / "records"
        valid = records_root / "rp2040-cpu-fixture-20260830-01"
        self.module._validate_record_root(valid)
        with self.assertRaisesRegex(ValueError, "directly below"):
            self.module._validate_record_root(valid / "nested")
        with self.assertRaisesRegex(ValueError, "record directory must start"):
            self.module._validate_record_root(records_root / "other-fixture")

    def test_record_manifest_merges_phase_identities_without_overwriting_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "rp2040-cpu-fixture"
            common = {
                "record_id": record.name,
                "candidate_id": "candidate",
                "workloads": [],
                "backend_identities": {
                    "baseline_production": {"commit": "a" * 40, "dirty": False, "runner_sha256": "b" * 64}
                },
                "feature_set": ["behavior-trace", "sd-gen1-multiblock"],
                "measurement_cpu": 0,
            }
            self.module._record_manifest(record, common)
            self.module._write_sha256sums_once(record)
            second = dict(common)
            second["backend_identities"] = {
                "candidate_production": {"commit": "c" * 40, "dirty": False, "runner_sha256": "d" * 64}
            }
            second["feature_set"] = ["cpu-application-profiler"]
            self.module._record_manifest(record, second)
            manifest = self.module._read_json(record / "manifest.json")
            self.assertEqual(set(manifest["backend_identities"]), {"baseline_production", "candidate_production"})
            self.assertEqual(
                manifest["feature_set"],
                ["behavior-trace", "cpu-application-profiler", "sd-gen1-multiblock"],
            )
            context = self.module._manifest_decision_context(record, [], {}, feature_set=[])
            self.assertEqual(set(context["backend_identities"]), {"baseline_production", "candidate_production"})
            self.assertEqual(
                context["feature_set"],
                ["behavior-trace", "cpu-application-profiler", "sd-gen1-multiblock"],
            )

    def test_base_manifest_records_measurement_policy(self):
        identity = {
            "commit": "a" * 40,
            "dirty": False,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
            "feature_set": ["sd-gen1-multiblock"],
        }
        manifest = self.module._base_manifest(
            "rp2040-cpu-fixture", [], {"baseline_production": identity},
            candidate_id="P0-A2", cpu=0,
            measurement_policy={"inter_run_cooldown_seconds": 60.0},
        )
        self.assertEqual(
            manifest["measurement_policy"],
            {"inter_run_cooldown_seconds": 60.0},
        )

    def test_record_manifest_merges_measurement_policy_into_existing_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "rp2040-cpu-fixture"
            identity = {
                "commit": "a" * 40,
                "dirty": False,
                "runner_sha256": "b" * 64,
                "build_provenance_sha256": "c" * 64,
                "feature_set": ["sd-gen1-multiblock"],
            }
            base = self.module._base_manifest(
                record.name, [], {"baseline_production": identity},
                candidate_id="P0-A2", cpu=0,
            )
            self.module._record_manifest(record, base)
            self.module._write_sha256sums_once(record)
            with_policy = self.module._base_manifest(
                record.name, [], {"candidate_production": identity},
                candidate_id="P0-A2", cpu=0,
                measurement_policy={"inter_run_cooldown_seconds": 60.0},
            )
            self.module._record_manifest(record, with_policy)
            manifest = self.module._read_json(record / "manifest.json")
            self.assertEqual(
                manifest["measurement_policy"],
                {"inter_run_cooldown_seconds": 60.0},
            )

    def test_record_manifest_refuses_modified_leaf_after_checksum_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "rp2040-cpu-fixture"
            identity = {
                "record_id": record.name,
                "candidate_id": "candidate",
                "workloads": [],
                "backend_identities": {
                    "baseline_production": {"commit": "a" * 40, "dirty": False, "runner_sha256": "b" * 64}
                },
                "feature_set": [],
                "measurement_cpu": 0,
            }
            self.module._record_manifest(record, identity)
            self.module._write_sha256sums_once(record)
            (record / "manifest.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                self.module._record_manifest(record, identity)

    def test_environment_verifier_accepts_installed_schemas_and_records(self):
        verifier = load_verifier()
        checks = []
        verifier.verify_rp2040_cpu_application_records(checks, ROOT)
        self.assertEqual([check["status"] for check in checks], ["pass", "pass"])
        expected_records = len(
            list((ROOT / "firmware-validation" / "records").glob("rp2040-cpu-*"))
        )
        self.assertEqual(checks[1]["records"], expected_records)
        revised_null = ROOT / "firmware-validation" / "records" / "rp2040-cpu-p0-null-20260831-04"
        summary = json.loads((revised_null / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "invalid")
        self.assertTrue(summary["null_control"]["pass"])

    def test_environment_verifier_projection_matches_runner_audio_contract(self):
        verifier = load_verifier()
        report = {
            "backend_build": {"commit": "a" * 40, "dirty": False},
            "backend_commit": "a" * 40,
            "audio_sink": {
                "expected_count": 49152,
                "expected_sha256": "b" * 64,
                "dma_write_count": 49152,
                "pcm_sha256": "c" * 64,
            },
            "cycles": 123,
        }
        projection = verifier._rp2040_guest_observation_projection(report)
        self.assertNotIn("backend_build", projection)
        self.assertNotIn("backend_commit", projection)
        self.assertNotIn("expected_count", projection["audio_sink"])
        self.assertNotIn("expected_sha256", projection["audio_sink"])
        self.assertEqual(projection["audio_sink"]["dma_write_count"], 49152)
        self.assertEqual(projection["audio_sink"]["pcm_sha256"], "c" * 64)

    def test_admission_gate_rechecks_receipts_and_full_workload_identity(self):
        import picocalc

        identity = {
            "commit": "a" * 40,
            "dirty": False,
            "runner_sha256": "b" * 64,
            "build_provenance_sha256": "c" * 64,
            "feature_set": ["sd-gen1-multiblock"],
            "role": "baseline_production",
            "provenance_role": "baseline_production",
        }
        workloads = []
        for target_id in ("picotetris-opt1b-vrp5", "picoedit-r1-vrp2f"):
            target = picocalc.load_firmware_target(target_id)
            self.assertIsNotNone(target)
            workloads.append(
                {
                    "id": target_id,
                    "revision": target["revision"],
                    "firmware_sha256": target["artifacts"]["bin_sha256"],
                    "scenario_sha256": target["scenario"]["sha256"],
                    "contract_sha256": picocalc.firmware_target_contract_sha256(target),
                }
            )
        registered_report = {"cycles": 123, "observable": "fixed"}
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "rp2040-cpu-admission-fixture"
            manifest = self.module._base_manifest(
                record.name, workloads, {"baseline_production": identity},
                candidate_id="P0-0", cpu=0,
            )
            self.module._record_manifest(record, manifest)
            receipts = []
            for workload in workloads:
                digest = self.module.guest_observation_sha256(registered_report)
                measurement = {
                    "backend_commit": identity["commit"],
                    "runner_sha256": identity["runner_sha256"],
                    "build_provenance_sha256": identity["build_provenance_sha256"],
                    "guest_observation_sha256": digest,
                }
                receipt = {
                    "schema_id": self.module.DECISION_SCHEMA_ID,
                    "schema_version": 1,
                    "record_id": record.name,
                    "candidate_id": "P0-0",
                    "decision_kind": "admission",
                    "workload": workload["id"],
                    "backend_commit": identity["commit"],
                    "runner_sha256": identity["runner_sha256"],
                    "build_provenance_sha256": identity["build_provenance_sha256"],
                    "workloads": workloads,
                    "backend_identities": {"baseline_production": identity},
                    "feature_set": identity["feature_set"],
                    "registered_guest_observation_sha256": digest,
                    "runs": [measurement, dict(measurement)],
                    "correctness": {"status": "pass", "workload": workload["id"]},
                    "evidence": [measurement, dict(measurement)],
                    "status": "pass",
                }
                self.module._write_json_once(
                    record / "admission" / "admission-{}.json".format(workload["id"]), receipt
                )
                receipts.append(receipt)
            self.module._write_json_once(
                record / "decision.json",
                {
                    "schema_id": self.module.DECISION_SCHEMA_ID,
                    "schema_version": 1,
                    "record_id": record.name,
                    "candidate_id": "P0-0",
                    "decision_kind": "admission",
                    "status": "pass",
                    "correctness": {"status": "pass"},
                    "evidence": receipts,
                    "workloads": workloads,
                    "backend_identities": {"baseline_production": identity},
                    "feature_set": identity["feature_set"],
                },
            )
            self.module._write_sha256sums_once(record)
            with mock.patch.object(self.module, "_validate_record_root"):
                with mock.patch.object(self.module, "_registered_report", return_value=registered_report):
                    self.module._require_admission_gate(record, workloads, identity)
                    verifier = load_verifier()
                    verifier_root = Path(temporary) / "verifier-root"
                    (verifier_root / "firmware-validation" / "records").mkdir(parents=True)
                    for schema_path in (ROOT / "firmware-validation").glob("rp2040-cpu-*.schema.json"):
                        shutil.copy2(schema_path, verifier_root / "firmware-validation" / schema_path.name)
                    shutil.copytree(
                        record,
                        verifier_root / "firmware-validation" / "records" / record.name,
                    )
                    checks = []
                    verifier.verify_rp2040_cpu_application_records(checks, verifier_root)
                    self.assertEqual([check["status"] for check in checks], ["pass", "pass"])
                    tampered = self.module._read_json(
                        record / "admission" / "admission-{}.json".format(workloads[0]["id"])
                    )
                    tampered["workloads"][0]["revision"] = 99
                    self.module._write_json_replace(
                        record / "admission" / "admission-{}.json".format(workloads[0]["id"]), tampered
                    )
                    with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                        self.module._require_admission_gate(record, workloads, identity)


if __name__ == "__main__":
    unittest.main()
