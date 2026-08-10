#!/usr/bin/env python3
"""Analyze a no-input PicoCalc speaker-calibration video.

The analyzer deliberately separates obvious nonlinear failure from subjective
acceptance.  A first recording can produce ``fail`` or ``review_required``;
``pass`` is reserved for a later, versioned hardware profile built from
human-confirmed boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path


SCHEMA_VERSION = 1
BLOCK_FRAMES = 960
SYNC_NMS_SECONDS = 1.5


def db(value: float) -> float:
    if value <= 1e-15:
        return -300.0
    return 20.0 * math.log10(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def verify_plan(plan: dict) -> None:
    claimed = plan.get("content_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise ValueError("calibration plan has no valid content_sha256")
    unsigned = dict(plan)
    del unsigned["content_sha256"]
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != claimed:
        raise ValueError(
            f"calibration plan content SHA-256 mismatch: expected {claimed}, got {actual}"
        )


def rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def goertzel_rms(samples: list[float], frequency: float, sample_rate: int) -> float:
    """Return the RMS of one exact-frequency component using a Hann window."""
    count = len(samples)
    if count < 2 or frequency <= 0 or frequency >= sample_rate / 2:
        return 0.0
    omega = 2.0 * math.pi * frequency / sample_rate
    coefficient = 2.0 * math.cos(omega)
    previous = 0.0
    previous_2 = 0.0
    window_sum = 0.0
    for index, sample in enumerate(samples):
        weight = 0.5 - 0.5 * math.cos(2.0 * math.pi * index / (count - 1))
        current = sample * weight + coefficient * previous - previous_2
        previous_2 = previous
        previous = current
        window_sum += weight
    magnitude = math.sqrt(max(0.0, previous_2 * previous_2 + previous * previous -
                              coefficient * previous * previous_2))
    peak = 2.0 * magnitude / max(window_sum, 1e-15)
    return peak / math.sqrt(2.0)


def remove_dc(samples: list[float]) -> list[float]:
    if not samples:
        return []
    mean = sum(samples) / len(samples)
    return [value - mean for value in samples]


def read_mono_wav(path: Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("extracted WAV must be mono signed-16 PCM")
        sample_rate = source.getframerate()
        raw = source.readframes(source.getnframes())
    values = struct.unpack("<{}h".format(len(raw) // 2), raw)
    return sample_rate, [value / 32768.0 for value in values]


def tone_features(block: list[float], sample_rate: int) -> tuple[float, float, float]:
    centered = remove_dc(block)
    total = rms(centered)
    if total <= 1e-12:
        return 0.0, 0.0, -300.0
    tone_1 = goertzel_rms(centered, 1000.0, sample_rate)
    tone_2 = goertzel_rms(centered, 2000.0, sample_rate)
    return min(1.5, tone_1 * tone_1 / (total * total)), min(
        1.5, tone_2 * tone_2 / (total * total)
    ), db(total)


def sync_scores(samples: list[float], sample_rate: int, signature: list[str]) -> list[float]:
    if sample_rate != 48_000:
        raise ValueError("calibration analysis requires 48000 Hz extracted PCM")
    features = [
        tone_features(samples[start:start + BLOCK_FRAMES], sample_rate)
        for start in range(0, len(samples) - BLOCK_FRAMES + 1, BLOCK_FRAMES)
    ]
    scores: list[float] = []
    for offset in range(0, len(features) - len(signature) + 1):
        score = 0.0
        tone_blocks = 0
        for relative, expected in enumerate(signature):
            tone_1, tone_2, level = features[offset + relative]
            if expected == "tone_1000":
                score += tone_1 - tone_2 + max(0.0, min(0.4, (level + 50.0) / 100.0))
                tone_blocks += 1
            elif expected == "tone_2000":
                score += tone_2 - tone_1 + max(0.0, min(0.4, (level + 50.0) / 100.0))
                tone_blocks += 1
            else:
                score += max(0.0, 0.15 - tone_1 - tone_2)
        scores.append(score / max(tone_blocks, 1))
    return scores


def select_sync_offsets(scores: list[float], count: int, sample_rate: int) -> list[int]:
    radius = max(1, round(SYNC_NMS_SECONDS * sample_rate / BLOCK_FRAMES))
    candidates = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    selected: list[int] = []
    for index in candidates:
        if all(abs(index - other) > radius for other in selected):
            selected.append(index)
            if len(selected) == count:
                break
    return sorted(selected)


def linear_fit(expected: list[float], observed: list[float]) -> tuple[float, float, float]:
    if len(expected) != len(observed) or len(expected) < 2:
        raise ValueError("at least two synchronization observations are required")
    x_mean = sum(expected) / len(expected)
    y_mean = sum(observed) / len(observed)
    denominator = sum((value - x_mean) ** 2 for value in expected)
    if denominator <= 0:
        raise ValueError("synchronization timeline has no span")
    scale = sum((x - x_mean) * (y - y_mean) for x, y in zip(expected, observed)) / denominator
    offset = y_mean - scale * x_mean
    residual = max(abs(y - (offset + scale * x)) for x, y in zip(expected, observed))
    return offset, scale, residual


def sine_metrics(samples: list[float], frequency: float, sample_rate: int,
                 noise_samples: list[float] | None = None) -> dict:
    centered = remove_dc(samples)
    noise_centered = remove_dc(noise_samples or [])
    total_rms = rms(centered)
    noise_rms = rms(noise_centered)
    peak = max((abs(value) for value in centered), default=0.0)
    fundamental = goertzel_rms(centered, frequency, sample_rate)
    frequency_noise = goertzel_rms(noise_centered, frequency, sample_rate)
    harmonics = []
    harmonic = 2
    while harmonic <= 8 and harmonic * frequency < sample_rate / 2:
        harmonics.append(goertzel_rms(centered, harmonic * frequency, sample_rate))
        harmonic += 1
    harmonic_rms = math.sqrt(sum(value * value for value in harmonics))
    thd = harmonic_rms / max(fundamental, 1e-12)
    return {
        "rms_dbfs": round(db(total_rms), 4),
        "peak_dbfs": round(db(peak), 4),
        "analyzed_frequency_hz": round(frequency, 4),
        "fundamental_dbfs": round(db(fundamental), 4),
        "noise_rms_dbfs": round(db(noise_rms), 4),
        "broadband_snr_db": round(db(total_rms / max(noise_rms, 1e-12)), 4),
        "frequency_noise_dbfs": round(db(frequency_noise), 4),
        "snr_db": round(db(fundamental / max(frequency_noise, 1e-12)), 4),
        "thd_ratio": round(thd, 6),
        "thd_percent": round(thd * 100.0, 3),
    }


def transient_metrics(samples: list[float], noise_rms: float = 0.0) -> dict:
    centered = remove_dc(samples)
    total_rms = rms(centered)
    differences = [centered[index] - centered[index - 1]
                   for index in range(1, len(centered))]
    difference_ratio = rms(differences) / max(total_rms, 1e-12)
    crossings = sum(
        1 for previous, current in zip(centered, centered[1:])
        if (previous < 0 <= current) or (previous >= 0 > current)
    )
    return {
        "rms_dbfs": round(db(total_rms), 4),
        "peak_dbfs": round(db(max((abs(value) for value in centered), default=0.0)), 4),
        "noise_rms_dbfs": round(db(noise_rms), 4),
        "snr_db": round(db(total_rms / max(noise_rms, 1e-12)), 4),
        "difference_rms_ratio": round(difference_ratio, 6),
        "zero_crossing_ratio": round(crossings / max(len(centered) - 1, 1), 6),
    }


def highpass(samples: list[float], cutoff_hz: float,
             sample_rate: int, poles: int = 2) -> list[float]:
    """Apply a deterministic cascaded RC high-pass without optional modules."""
    result = list(samples)
    alpha = 1.0 / (1.0 + 2.0 * math.pi * cutoff_hz / sample_rate)
    for _ in range(poles):
        previous_input = 0.0
        previous_output = 0.0
        filtered = []
        for value in result:
            output = alpha * (previous_output + value - previous_input)
            filtered.append(output)
            previous_input = value
            previous_output = output
        result = filtered
    return result


def percussion_metrics(samples: list[float], noise_samples: list[float],
                       sample_rate: int) -> dict:
    """Measure the pistol-like broadband residue of an audible drum burst."""
    centered = remove_dc(samples)
    noise_centered = remove_dc(noise_samples)
    total_rms = rms(centered)
    noise_rms = rms(noise_centered)
    highband = highpass(centered, 3000.0, sample_rate)
    noise_highband = highpass(noise_centered, 3000.0, sample_rate)
    highband_rms = rms(highband)
    noise_highband_rms = rms(noise_highband)
    differences = [centered[index] - centered[index - 1]
                   for index in range(1, len(centered))]
    return {
        "rms_dbfs": round(db(total_rms), 4),
        "peak_dbfs": round(db(max((abs(value) for value in centered), default=0.0)), 4),
        "noise_rms_dbfs": round(db(noise_rms), 4),
        "snr_db": round(db(total_rms / max(noise_rms, 1e-12)), 4),
        "highband_rms_dbfs": round(db(highband_rms), 4),
        "highband_noise_dbfs": round(db(noise_highband_rms), 4),
        "highband_snr_db": round(
            db(highband_rms / max(noise_highband_rms, 1e-12)), 4
        ),
        "highband_ratio": round(highband_rms / max(total_rms, 1e-12), 6),
        "difference_rms_ratio": round(
            rms(differences) / max(total_rms, 1e-12), 6
        ),
    }


def classify(cases: list[dict]) -> tuple[str, list[dict]]:
    """Classify only clear nonlinear growth; leave border cases for review."""
    baselines: dict[tuple, dict] = {}
    percussion_baselines: dict[tuple, dict] = {}
    percussion_groups: dict[tuple, list[dict]] = {}
    for item in cases:
        if item["kind"] != "percussion":
            continue
        key = (item["kind"], item["frequency_hz"], item.get("frequency_2_hz", 0))
        percussion_groups.setdefault(key, []).append(item)
    for key, group in percussion_groups.items():
        ordered = sorted(group, key=lambda entry: entry["dbfs"])
        selected = ordered[0]
        # Find the first adjacent level step whose recorded RMS follows the
        # requested gain. Earlier cases are below the phone/speaker observation
        # floor; using them as a residue baseline manufactures false growth.
        for lower, upper in zip(ordered, ordered[1:]):
            expected = upper["dbfs"] - lower["dbfs"]
            observed = (upper["metrics"]["rms_dbfs"] -
                        lower["metrics"]["rms_dbfs"])
            if observed >= expected - 1.5:
                selected = lower
                break
        percussion_baselines[key] = selected

    findings: list[dict] = []
    for item in cases:
        # Phone AGC follows the level of repeated percussion into the short
        # pre-case silence, so its time-domain "noise" rises together with the
        # previous case. The controlled same-waveform level series remains
        # observable through monotonic RMS and residue growth. Do not discard
        # that evidence using the stationary-tone SNR gate.
        if (item["kind"] != "percussion" and
                item["metrics"].get("snr_db", 300.0) < 12.0):
            item["decision"] = "unobservable"
            item["reasons"] = ["speaker_output_below_recording_noise"]
            continue
        if item["kind"] == "sine":
            key = ("sine", item["frequency_hz"])
            baseline = baselines.setdefault(key, item)
            if item["dbfs"] == baseline["dbfs"]:
                item["decision"] = "baseline"
                continue
            thd = item["metrics"]["thd_ratio"]
            base_thd = baseline["metrics"]["thd_ratio"]
            expected_gain = item["dbfs"] - baseline["dbfs"]
            observed_gain = (item["metrics"]["fundamental_dbfs"] -
                             baseline["metrics"]["fundamental_dbfs"])
            item["metrics"]["expected_gain_db"] = expected_gain
            item["metrics"]["observed_gain_db"] = round(observed_gain, 4)
            severe_harmonics = thd >= 0.20 and thd >= max(base_thd * 3.0, base_thd + 0.10)
            # Small speakers commonly reach roughly ten percent harmonic
            # content near their useful maximum without the catastrophic
            # buzzing this profile is intended to reject. Keep the review
            # boundary above that correlated observation; compression remains
            # an independent warning even below this THD threshold.
            suspicious_harmonics = thd >= 0.12 and thd >= max(
                base_thd * 2.0, base_thd + 0.06
            )
            severe_compression = expected_gain >= 6 and observed_gain <= expected_gain - 8
            suspicious_compression = expected_gain >= 6 and observed_gain <= expected_gain - 5
            if severe_harmonics or (suspicious_harmonics and severe_compression):
                item["decision"] = "fail"
                reasons = []
                if severe_harmonics or suspicious_harmonics:
                    reasons.append("nonlinear_harmonic_growth")
                if severe_compression:
                    reasons.append("level_compression")
                item["reasons"] = reasons
                findings.append(item)
            elif suspicious_harmonics or suspicious_compression:
                item["decision"] = "review"
                item["reasons"] = [
                    "harmonic_growth_near_boundary" if suspicious_harmonics
                    else "level_compression_near_boundary"
                ]
                findings.append(item)
            else:
                item["decision"] = "provisional_safe"
        elif item["kind"] in ("kick", "multitone"):
            key = (item["kind"], item["frequency_hz"], item.get("frequency_2_hz", 0))
            baseline = baselines.setdefault(key, item)
            if item["dbfs"] == baseline["dbfs"]:
                item["decision"] = "baseline"
                continue
            current = item["metrics"].get("difference_rms_ratio", 0.0)
            reference = baseline["metrics"].get("difference_rms_ratio", 0.0)
            growth = current / max(reference, 1e-9)
            item["metrics"]["difference_ratio_growth"] = round(growth, 4)
            if current >= 0.65 and growth >= 2.5:
                item["decision"] = "fail"
                item["reasons"] = ["broadband_transient_growth"]
                findings.append(item)
            elif current >= 0.40 and growth >= 1.7:
                item["decision"] = "review"
                item["reasons"] = ["transient_growth_near_boundary"]
                findings.append(item)
            else:
                item["decision"] = "provisional_safe"
        elif item["kind"] == "percussion":
            key = (item["kind"], item["frequency_hz"], item.get("frequency_2_hz", 0))
            baseline = percussion_baselines[key]
            if item["dbfs"] < baseline["dbfs"]:
                item["decision"] = "unobservable"
                item["reasons"] = ["below_level_series_observation_floor"]
                continue
            if item["dbfs"] == baseline["dbfs"]:
                item["decision"] = "baseline"
                continue
            current = item["metrics"]["highband_ratio"]
            reference = baseline["metrics"]["highband_ratio"]
            growth = current / max(reference, 1e-9)
            expected_gain = item["dbfs"] - baseline["dbfs"]
            observed_gain = item["metrics"]["rms_dbfs"] - baseline["metrics"]["rms_dbfs"]
            item["metrics"]["highband_ratio_growth"] = round(growth, 4)
            item["metrics"]["expected_gain_db"] = expected_gain
            item["metrics"]["observed_gain_db"] = round(observed_gain, 4)
            # The ratio is normalized by the complete burst, so even hard
            # clipping grows it less dramatically than single-tone THD. These
            # limits deliberately target the sustained broadband crack seen in
            # the known-bad DOOM recording, not mild speaker coloration.
            severe_residue = growth >= 1.6 and current >= reference + 0.03
            suspicious_residue = growth >= 1.3 and current >= reference + 0.015
            severe_compression = expected_gain >= 6 and observed_gain <= expected_gain - 8
            suspicious_compression = expected_gain >= 6 and observed_gain <= expected_gain - 5
            if severe_residue or (suspicious_residue and severe_compression):
                item["decision"] = "fail"
                item["reasons"] = ["pistol_like_broadband_residue"]
                if severe_compression:
                    item["reasons"].append("level_compression")
                findings.append(item)
            elif suspicious_residue or suspicious_compression:
                item["decision"] = "review"
                item["reasons"] = [
                    "broadband_residue_near_boundary" if suspicious_residue
                    else "level_compression_near_boundary"
                ]
                findings.append(item)
            else:
                item["decision"] = "provisional_safe"

    if any(item.get("decision") == "fail" for item in cases):
        return "fail", findings
    # A first calibration cannot establish a pass boundary by itself.
    return "review_required", findings


def extract_audio(video: Path, wav_path: Path, ffmpeg: str) -> None:
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
         "-y", str(wav_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("ffmpeg audio extraction failed: " + completed.stderr.strip())


def write_mono_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    values = [max(-32768, min(32767, round(value * 32768.0))) for value in samples]
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack("<{}h".format(len(values)), *values))


def write_html(path: Path, result: dict) -> None:
    rows = []
    for item in result.get("cases", []):
        metrics = item.get("metrics", {})
        rows.append(
            "<tr class='{decision}'><td>{id}</td><td>{time:.3f}</td><td>{kind}</td>"
            "<td>{dbfs}</td><td>{rms}</td><td>{snr}</td><td>{thd}</td><td>{decision}</td>"
            "<td>{reasons}</td></tr>".format(
                decision=html.escape(item.get("decision", "")),
                id=html.escape(item["id"]), time=item["video_start_seconds"],
                kind=html.escape(item["kind"]), dbfs=item["dbfs"],
                rms=metrics.get("rms_dbfs", ""), snr=metrics.get("snr_db", ""),
                thd=metrics.get("thd_percent", ""),
                reasons=html.escape(", ".join(item.get("reasons", []))),
            )
        )
    document = """<!doctype html><meta charset='utf-8'><title>PicoCalc speaker calibration</title>
<style>body{{font-family:sans-serif;max-width:1200px;margin:auto}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #aaa;padding:.3rem}}.fail{{background:#ffd5d5}}.review{{background:#fff3bd}}
.provisional_safe{{background:#e5ffe5}}.unobservable{{background:#eee}}</style>
<h1>PicoCalc speaker calibration</h1><p>Status: <strong>{status}</strong></p>
<p>Sync residual: {residual:.4f} s; clock scale: {scale:.8f}</p>
<table><thead><tr><th>case</th><th>video s</th><th>kind</th><th>dBFS</th><th>RMS dBFS</th>
<th>SNR dB</th><th>THD %</th><th>decision</th><th>reason</th></tr></thead><tbody>{rows}</tbody></table>
""".format(status=html.escape(result["status"]), residual=result["synchronization"]["max_residual_seconds"],
           scale=result["synchronization"]["clock_scale"], rows="\n".join(rows))
    path.write_text(document, encoding="utf-8")


def analyze(video: Path, plan_path: Path, output: Path, ffmpeg: str) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or plan.get("sample_rate_hz") != 48_000:
        raise ValueError("unsupported calibration plan")
    verify_plan(plan)
    output.mkdir(parents=True, exist_ok=True)
    wav_path = output / "captured-mono-48k.wav"
    extract_audio(video, wav_path, ffmpeg)
    sample_rate, samples = read_mono_wav(wav_path)
    signature = plan["sync_signature"]["blocks"]
    scores = sync_scores(samples, sample_rate, signature)
    sync_cases = [item for item in plan["cases"] if item["kind"] == "sync"]
    offsets = select_sync_offsets(scores, len(sync_cases), sample_rate)
    if len(offsets) != len(sync_cases):
        raise ValueError("could not locate every synchronization signature")
    expected = [item["stimulus_start_frame"] / sample_rate for item in sync_cases]
    observed = [offset * BLOCK_FRAMES / sample_rate for offset in offsets]
    time_offset, clock_scale, residual = linear_fit(expected, observed)
    selected_scores = [scores[offset] for offset in offsets]
    if not 0.99 <= clock_scale <= 1.01 or residual > 0.20 or min(selected_scores) < 0.20:
        raise ValueError(
            "synchronization confidence is insufficient "
            f"(scale={clock_scale:.8f}, residual={residual:.4f}, score={min(selected_scores):.4f})"
        )

    case_results = []
    for item in plan["cases"]:
        if item["kind"] == "sync":
            continue
        firmware_start = item["stimulus_start_frame"] / sample_rate
        firmware_duration = item["duration_frames"] / sample_rate
        video_start = time_offset + clock_scale * firmware_start
        video_duration = clock_scale * firmware_duration
        trim = 0.08 if item["kind"] in ("sine", "multitone") else 0.0
        start_sample = max(0, round((video_start + trim) * sample_rate))
        end_sample = min(len(samples), round((video_start + video_duration - trim) * sample_rate))
        captured = samples[start_sample:end_sample]
        noise_end = max(0, round(video_start * sample_rate))
        noise_frames = min(round(0.15 * sample_rate), item["pre_frames"])
        noise_start = max(0, noise_end - noise_frames)
        noise_level = rms(remove_dc(samples[noise_start:noise_end]))
        result = dict(item)
        result["video_start_seconds"] = round(video_start, 6)
        result["video_end_seconds"] = round(video_start + video_duration, 6)
        noise_samples = samples[noise_start:noise_end]
        if item["kind"] == "sine":
            # A phone's audio clock and the RP2040 playback clock need not map
            # one-to-one. The sync fit measures that stretch. Analyze the tone
            # at its frequency in the captured timeline, otherwise even a
            # sub-percent drift moves a long-window Goertzel bin far enough to
            # manufacture huge THD and false failures.
            captured_frequency = item["frequency_hz"] / clock_scale
            result["metrics"] = sine_metrics(
                captured, captured_frequency, sample_rate,
                noise_samples,
            )
        elif item["kind"] == "percussion":
            result["metrics"] = percussion_metrics(
                captured, noise_samples, sample_rate
            )
        else:
            result["metrics"] = transient_metrics(captured, noise_level)
        case_results.append(result)

    status, findings = classify(case_results)
    low_snr_count = sum(
        item["metrics"].get("snr_db", 300.0) < 12.0 for item in case_results
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "interpretation": "built_in_speaker_calibration_not_digital_audio_exactness",
        "video": {
            "path": str(video.resolve()),
            "sha256": sha256_file(video),
        },
        "plan": {
            "path": str(plan_path.resolve()),
            "plan_id": plan["plan_id"],
            "content_sha256": plan["content_sha256"],
        },
        "synchronization": {
            "markers_expected": len(sync_cases),
            "markers_found": len(offsets),
            "video_marker_seconds": [round(value, 6) for value in observed],
            "marker_scores": [round(value, 6) for value in selected_scores],
            "time_offset_seconds": round(time_offset, 8),
            "clock_scale": round(clock_scale, 10),
            "max_residual_seconds": round(residual, 8),
        },
        "summary": {
            "cases_analyzed": len(case_results),
            "automatic_failures": sum(item.get("decision") == "fail" for item in case_results),
            "human_review_cases": sum(item.get("decision") == "review" for item in case_results),
            "provisional_safe_cases": sum(item.get("decision") == "provisional_safe" for item in case_results),
            "unobservable_cases": sum(item.get("decision") == "unobservable" for item in case_results),
            "low_snr_cases": low_snr_count,
            "note": "first calibration never auto-passes; human labels create the versioned hardware profile",
        },
        "findings": [
            {"id": item["id"], "video_start_seconds": item["video_start_seconds"],
             "decision": item["decision"], "reasons": item.get("reasons", [])}
            for item in findings
        ],
        "cases": case_results,
    }
    (output / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_dir = output / "review"
    review_dir.mkdir(exist_ok=True)
    for item in findings:
        clip_start = max(0, round((item["video_start_seconds"] - 0.25) * sample_rate))
        clip_end = min(
            len(samples), round((item["video_end_seconds"] + 0.25) * sample_rate)
        )
        write_mono_wav(review_dir / f"{item['id']}.wav",
                       samples[clip_start:clip_end], sample_rate)
    write_html(output / "report.html", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    return parser.parse_args()


def status_exit_code(status: str) -> int:
    if status == "pass":
        return 0
    if status == "fail":
        return 1
    return 2


def main() -> int:
    args = parse_args()
    if not args.video.is_file():
        print(f"video does not exist: {args.video}", file=sys.stderr)
        return 2
    if not args.plan.is_file():
        print(f"plan does not exist: {args.plan}", file=sys.stderr)
        return 2
    if shutil.which(args.ffmpeg) is None:
        print(f"ffmpeg is unavailable: {args.ffmpeg}", file=sys.stderr)
        return 2
    try:
        result = analyze(args.video, args.plan, args.output, args.ffmpeg)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"speaker calibration: cannot_judge: {error}", file=sys.stderr)
        return 2
    print(f"speaker calibration: {result['status']}")
    print(f"  automatic failures: {result['summary']['automatic_failures']}")
    print(f"  human review cases: {result['summary']['human_review_cases']}")
    print(f"  report: {args.output / 'report.html'}")
    return status_exit_code(result["status"])


if __name__ == "__main__":
    raise SystemExit(main())
