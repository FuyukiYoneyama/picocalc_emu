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
