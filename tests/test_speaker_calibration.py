import importlib.util
import hashlib
import json
import tempfile
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/analyze_speaker_calibration.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("speaker_calibration", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SpeakerCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    def insert_sync(self, samples, start_block, signature, amplitude=0.25):
        sample_rate = 48_000
        for block_index, kind in enumerate(signature):
            frequency = 1000 if kind == "tone_1000" else 2000 if kind == "tone_2000" else 0
            for within in range(self.tool.BLOCK_FRAMES):
                index = (start_block + block_index) * self.tool.BLOCK_FRAMES + within
                if frequency:
                    samples[index] = amplitude * math.sin(
                        2.0 * math.pi * frequency * within / sample_rate
                    )

    def test_sync_pattern_finds_multiple_markers_and_clock_mapping(self):
        signature = (["tone_1000"] * 12 + ["silence"] * 8 +
                     ["tone_2000"] * 12 + ["silence"] * 8 +
                     ["tone_1000"] * 20)
        samples = [0.0001 * math.sin(index * 0.013) for index in range(8 * 48_000)]
        self.insert_sync(samples, 50, signature)
        self.insert_sync(samples, 250, signature)

        scores = self.tool.sync_scores(samples, 48_000, signature)
        offsets = self.tool.select_sync_offsets(scores, 2, 48_000)
        self.assertEqual(offsets, [50, 250])
        offset, scale, residual = self.tool.linear_fit([2.0, 6.0], [1.0, 5.0])
        self.assertAlmostEqual(offset, -1.0)
        self.assertAlmostEqual(scale, 1.0)
        self.assertAlmostEqual(residual, 0.0)

    def test_sine_metrics_expose_hard_nonlinearity(self):
        sample_rate = 48_000
        clean = [
            0.8 * math.sin(2.0 * math.pi * 1000 * index / sample_rate)
            for index in range(16_384)
        ]
        clipped = [max(-0.25, min(0.25, value)) for value in clean]
        clean_metrics = self.tool.sine_metrics(clean, 1000, sample_rate)
        clipped_metrics = self.tool.sine_metrics(clipped, 1000, sample_rate)
        self.assertLess(clean_metrics["thd_percent"], 0.1)
        self.assertGreater(clipped_metrics["thd_percent"], 20.0)

        cases = [
            {"id": "base", "kind": "sine", "frequency_hz": 1000,
             "dbfs": -18, "metrics": clean_metrics},
            {"id": "bad", "kind": "sine", "frequency_hz": 1000,
             "dbfs": -9, "metrics": clipped_metrics},
        ]
        status, findings = self.tool.classify(cases)
        self.assertEqual(status, "fail")
        self.assertEqual(findings[0]["id"], "bad")
        self.assertIn("nonlinear_harmonic_growth", findings[0]["reasons"])

    def test_sine_analysis_uses_frequency_in_captured_clock(self):
        sample_rate = 48_000
        clock_scale = 1.0078331482
        captured_frequency = 1000.0 / clock_scale
        captured = [
            0.5 * math.sin(2.0 * math.pi * captured_frequency * index / sample_rate)
            for index in range(16_384)
        ]
        metrics = self.tool.sine_metrics(
            captured, captured_frequency, sample_rate, [0.0] * 7200
        )
        self.assertLess(metrics["thd_percent"], 0.1)
        self.assertGreater(metrics["fundamental_dbfs"], -10.0)

    def test_low_case_snr_is_unobservable_not_whole_recording_failure(self):
        cases = [{
            "id": "quiet", "kind": "sine", "frequency_hz": 80,
            "dbfs": -18, "metrics": {"snr_db": 2.0},
        }]
        status, findings = self.tool.classify(cases)
        self.assertEqual(status, "review_required")
        self.assertEqual(findings, [])
        self.assertEqual(cases[0]["decision"], "unobservable")

    def test_percussion_metrics_reject_pistol_like_clipping_residue(self):
        sample_rate = 48_000
        clean = []
        clipped = []
        for index in range(sample_rate):
            within = index % 12_000
            if within >= 5_760:
                value = 0.0
            else:
                envelope = ((5_760 - within) / 5_760) ** 2
                value = envelope * (
                    0.6 * math.sin(2.0 * math.pi * 100 * index / sample_rate) +
                    0.4 * math.sin(2.0 * math.pi * 1000 * index / sample_rate)
                )
            clean.append(value * 0.10)
            clipped.append(max(-0.07, min(0.07, value)))
        noise = [0.0] * 7200
        clean_metrics = self.tool.percussion_metrics(clean, noise, sample_rate)
        clipped_metrics = self.tool.percussion_metrics(clipped, noise, sample_rate)
        self.assertGreater(
            clipped_metrics["highband_ratio"], clean_metrics["highband_ratio"] * 1.6
        )

        cases = [
            {"id": "base", "kind": "percussion", "frequency_hz": 100,
             "frequency_2_hz": 1000, "dbfs": -18, "metrics": clean_metrics},
            {"id": "bad", "kind": "percussion", "frequency_hz": 100,
             "frequency_2_hz": 1000, "dbfs": 0, "metrics": clipped_metrics},
        ]
        status, findings = self.tool.classify(cases)
        self.assertEqual(status, "fail")
        self.assertEqual(findings[0]["id"], "bad")
        self.assertIn("pistol_like_broadband_residue", findings[0]["reasons"])

    def test_percussion_level_series_moves_baseline_above_phone_agc_floor(self):
        cases = [
            {"id": "floor", "kind": "percussion", "frequency_hz": 100,
             "frequency_2_hz": 1000, "dbfs": -18,
             "metrics": {"snr_db": 4.0, "rms_dbfs": -51.0,
                         "highband_ratio": 0.055}},
            {"id": "base", "kind": "percussion", "frequency_hz": 100,
             "frequency_2_hz": 1000, "dbfs": -12,
             "metrics": {"snr_db": 3.0, "rms_dbfs": -49.3,
                         "highband_ratio": 0.088}},
            {"id": "clean", "kind": "percussion", "frequency_hz": 100,
             "frequency_2_hz": 1000, "dbfs": -9,
             "metrics": {"snr_db": 3.0, "rms_dbfs": -46.8,
                         "highband_ratio": 0.094}},
        ]
        status, findings = self.tool.classify(cases)
        self.assertEqual(status, "review_required")
        self.assertEqual(cases[0]["decision"], "unobservable")
        self.assertEqual(cases[1]["decision"], "baseline")
        self.assertEqual(cases[2]["decision"], "provisional_safe")
        self.assertEqual(findings, [])

    def test_plan_digest_rejects_silent_mutation(self):
        plan = {"schema_version": 1, "sample_rate_hz": 48_000, "cases": []}
        encoded = json.dumps(
            plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8") + b"\n"
        plan["content_sha256"] = hashlib.sha256(encoded).hexdigest()
        self.tool.verify_plan(plan)
        plan["sample_rate_hz"] = 44_100
        with self.assertRaisesRegex(ValueError, "content SHA-256 mismatch"):
            self.tool.verify_plan(plan)

    def test_html_report_renders_css_and_snr_column(self):
        result = {
            "status": "review_required",
            "synchronization": {"max_residual_seconds": 0.0, "clock_scale": 1.0},
            "cases": [{
                "id": "SINE-1000-L18", "video_start_seconds": 1.0,
                "kind": "sine", "dbfs": -18, "decision": "provisional_safe",
                "metrics": {"rms_dbfs": -20.0, "snr_db": 30.0, "thd_percent": 1.0},
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.html"
            self.tool.write_html(target, result)
            document = target.read_text(encoding="utf-8")
        self.assertIn("body{font-family:sans-serif", document)
        self.assertIn("<th>SNR dB</th>", document)

    def test_review_required_never_exits_as_pass(self):
        self.assertEqual(self.tool.status_exit_code("pass"), 0)
        self.assertEqual(self.tool.status_exit_code("fail"), 1)
        self.assertEqual(self.tool.status_exit_code("review_required"), 2)


if __name__ == "__main__":
    unittest.main()
