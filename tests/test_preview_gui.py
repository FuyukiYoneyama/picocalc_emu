"""VRP-3 presentation/input contract tests.

These tests intentionally avoid starting Tk so they run on a headless host.
The WSLg window/UART smoke is performed separately with ``preview-gui
--smoke-seconds``; all protocol and state decisions remain testable here.
"""

import importlib.util
import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/picocalc_preview.py"
FIXTURE_PATH = ROOT / "docs/validated-realtime-preview/preview-ipc-fixture-v1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("picocalc_preview_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: this also keeps the loader compatible with Python
    # versions that inspect ``sys.modules`` while resolving annotations.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PreviewGuiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = load_module()

    def test_frozen_input_frames_round_trip(self):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        expected_sequences = {"preview_to_runner": 0}
        for item in fixture["valid_frames"]:
            if item["direction"] != "preview_to_runner":
                continue
            frame = bytes.fromhex(item["frame_hex"])
            kind = int.from_bytes(frame[6:8], "little")
            sequence = int.from_bytes(frame[12:16], "little")
            self.assertEqual(sequence, expected_sequences[item["direction"]])
            self.assertEqual(
                self.preview.encode_frame(kind, sequence, frame[16:]),
                frame,
                item["name"],
            )
            expected_sequences[item["direction"]] += 1

    def test_key_dispatcher_suppresses_os_repeat_and_emits_held(self):
        events = []
        dispatcher = self.preview.KeyDispatcher(lambda key, state: events.append((key, state)))
        self.assertTrue(dispatcher.press("A"))
        self.assertFalse(dispatcher.press("A"))
        self.assertEqual(dispatcher.emit_held(), 1)
        self.assertTrue(dispatcher.release("A"))
        self.assertFalse(dispatcher.release("A"))
        self.assertEqual(events, [("A", "down"), ("A", "held"), ("A", "up")])

    def test_tk_key_mapping_reserves_escape_for_quit(self):
        self.assertEqual(self.preview.canonical_key("Return"), "Enter")
        self.assertEqual(self.preview.canonical_key("space"), "Space")
        self.assertEqual(self.preview.canonical_key("BackSpace"), "Backspace")
        self.assertEqual(self.preview.canonical_key("A", "a"), "a")
        self.assertIsNone(self.preview.canonical_key("F5"))

    def test_uart_window_keeps_printable_input_for_its_entry(self):
        app = self.preview.PreviewApp.__new__(self.preview.PreviewApp)
        window = object()

        class Widget:
            def winfo_toplevel(self):
                return window

            def winfo_class(self):
                return "Entry"

        app.console = SimpleNamespace(window=window)
        app.tk = SimpleNamespace(TclError=RuntimeError)
        app.key_dispatcher = SimpleNamespace(press=lambda *_args: self.fail("guest key was captured"))
        event = SimpleNamespace(widget=Widget(), keysym="a", char="a", state=0)
        self.assertEqual(app._on_key_press(event), "")

        class Button(Widget):
            def winfo_class(self):
                return "Button"

        button_event = SimpleNamespace(widget=Button(), keysym="a", char="a", state=0)
        self.assertFalse(app._event_is_uart_window(button_event))

    def test_rgb565_frame_is_decoded_and_scaled_without_core_changes(self):
        # One red pixel followed by one blue pixel, 2x1 -> 4x2 nearest-neighbor.
        payload = (
            (7).to_bytes(8, "little")
            + (2).to_bytes(2, "little")
            + (1).to_bytes(2, "little")
            + (0xF800).to_bytes(2, "little")
            + (0x001F).to_bytes(2, "little")
        )
        cycle, width, height, pixels = self.preview.parse_rgb565_payload(payload)
        self.assertEqual((cycle, width, height), (7, 2, 1))
        ppm = self.preview.rgb565_to_ppm(payload, 4, 2)
        self.assertTrue(ppm.startswith(b"P6\n4 2\n255\n"))
        self.assertEqual(len(ppm), len(b"P6\n4 2\n255\n") + 4 * 2 * 3)
        self.assertEqual(ppm[-12:-6], bytes((255, 0, 0)) * 2)
        self.assertEqual(ppm[-6:], bytes((0, 0, 255)) * 2)
        with self.assertRaises(self.preview.PreviewProtocolError):
            self.preview.rgb565_to_ppm(payload, 0, 2)

    def test_state_marks_coverage_and_protocol_errors_sticky(self):
        state = self.preview.PreviewState("fixture", 1)
        state.apply(
            self.preview.PreviewEvent(
                self.preview.KIND_STATUS,
                self.preview.canonical_json(
                    {
                        "coverage": "stopped",
                        "virtual_cycle": 1,
                        "observation": {
                            "projection": {"unsupported_mmio": {"count": 0, "truncated": False}}
                        },
                    }
                ),
            )
        )
        self.assertTrue(state.ux_invalid)
        self.assertIn("coverage=stopped", state.ux_reason)
        state.apply(self.preview.PreviewEvent(0, error=self.preview.PreviewProtocolError("truncated")))
        self.assertTrue(state.ux_invalid)
        self.assertIn("truncated", state.ux_reason)

    def test_status_line_exposes_admission_timing_and_hardware_boundary(self):
        state = self.preview.PreviewState(
            "fixture",
            2,
            receipt_id="fixture-receipt",
            backend_commit="0123456789abcdef",
            firmware_sha256="fedcba9876543210",
        )
        state.apply(
            self.preview.PreviewEvent(
                self.preview.KIND_STATUS,
                self.preview.canonical_json(
                    {
                        "audio": {"state": "not_streamed"},
                        "coverage": "ok",
                        "pacer": {"behind_count": 3, "lag_ns": -17, "ratio_ppm": 250000},
                        "uart": {"rx_accepted": 0, "rx_disabled": 1, "rx_overrun": 2, "tx_bytes": 4},
                        "virtual_cycle": 42,
                    }
                ),
            )
        )
        text = self.preview._status_text(state, True)
        self.assertIn("validation admitted receipt fixture-receipt", text)
        self.assertIn("backend 0123456789ab", text)
        self.assertIn("bin fedcba987654", text)
        self.assertIn("hardware not_claimed", text)
        self.assertIn("ratio 25.000%", text)
        self.assertIn("timing lag_ns -17 behind 3", text)
        self.assertIn("overrun 2 disabled 1", text)

    def test_lcd_renderer_rejects_non_picocalc_dimensions(self):
        app = self.preview.PreviewApp.__new__(self.preview.PreviewApp)
        app.canvas = object()
        app.state = self.preview.PreviewState("fixture", 1)
        app.state.frame_payload = (
            (1).to_bytes(8, "little")
            + (2).to_bytes(2, "little")
            + (2).to_bytes(2, "little")
            + b"\x00" * 8
        )
        with self.assertRaises(self.preview.PreviewProtocolError):
            app._render_frame()

    def test_reset_preserves_sticky_state(self):
        app = self.preview.PreviewApp.__new__(self.preview.PreviewApp)
        app.state = self.preview.PreviewState("fixture", 1)
        app.state.mark_invalid("coverage=stopped")
        calls = []
        app.key_dispatcher = SimpleNamespace(release_all=lambda: calls.append("release"))
        app.process = SimpleNamespace(send_reset=lambda: calls.append("reset"))
        self.assertEqual(app._on_reset(), "break")
        self.assertEqual(calls, ["release", "reset"])
        self.assertTrue(app.state.ux_invalid)

    def test_reload_clears_sticky_state_only_after_admission(self):
        class FakeProcess:
            instances = []

            def __init__(self, contract):
                self.contract = contract
                self.started = False
                self.stopped = False
                FakeProcess.instances.append(self)

            def start(self):
                self.started = True

            def stop(self):
                self.stopped = True

        app = self.preview.PreviewApp.__new__(self.preview.PreviewApp)
        app.descriptor = {
            "__path": "/tmp/descriptor.json",
            "backend": {"directory": "/tmp/backend"},
            "target": {"id": "old", "revision": 1},
        }
        old_process = FakeProcess({"old": True})
        app.process = old_process
        app.key_dispatcher = SimpleNamespace(release_all=lambda: None)
        app.state = self.preview.PreviewState("old", 1)
        app.state.mark_invalid("previous error")
        app.status_var = SimpleNamespace(set=lambda _value: None)
        app.skin_photo = None
        new_descriptor = {
            "backend": {"directory": "/tmp/backend", "commit": "new-backend"},
            "firmware": {"sha256": "new-bin"},
            "receipt_id": "new-receipt",
            "target": {"id": "new", "revision": 2},
        }
        fake_picocalc = SimpleNamespace(
            _validate_preview_descriptor=lambda _path, _backend: (
                new_descriptor,
                None,
                None,
                None,
                None,
                {"argv": ["runner"], "cwd": "/tmp"},
            )
        )
        with patch.dict(sys.modules, {"picocalc": fake_picocalc}), patch.object(
            self.preview, "PreviewProcess", FakeProcess
        ):
            self.assertEqual(app._on_reload(), "break")
        self.assertTrue(old_process.stopped)
        self.assertTrue(FakeProcess.instances[-1].started)
        self.assertEqual(app.state.target_id, "new")
        self.assertEqual(app.state.target_revision, 2)
        self.assertEqual(app.state.receipt_id, "new-receipt")
        self.assertFalse(app.state.ux_invalid)

    def test_reload_refusal_keeps_sticky_invalid_state(self):
        class FakeProcess:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        app = self.preview.PreviewApp.__new__(self.preview.PreviewApp)
        app.descriptor = {
            "__path": "/tmp/descriptor.json",
            "backend": {"directory": "/tmp/backend"},
            "target": {"id": "fixture", "revision": 1},
        }
        app.process = FakeProcess()
        app.state = self.preview.PreviewState("fixture", 1)
        app.status_var = SimpleNamespace(set=lambda _value: None)
        app.skin_photo = None
        fake_picocalc = SimpleNamespace(
            _validate_preview_descriptor=lambda _path, _backend: (_ for _ in ()).throw(
                ValueError("descriptor changed")
            )
        )
        with patch.dict(sys.modules, {"picocalc": fake_picocalc}):
            self.assertEqual(app._on_reload(), "break")
        self.assertTrue(app.process.stopped)
        self.assertTrue(app.state.ux_invalid)
        self.assertIn("RELOAD REFUSED", app.state.ux_reason)

    def test_uart_console_sends_text_and_raw_hex_without_faking_acceptance(self):
        sent = []
        lines = []

        class Entry:
            def __init__(self, value):
                self.value = value
                self.deleted = False

            def get(self):
                return self.value

            def delete(self, _start, _end):
                self.deleted = True

        class Mode:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        app = SimpleNamespace(
            process=SimpleNamespace(send_uart=lambda byte: sent.append(byte)),
            state=self.preview.PreviewState("fixture", 1),
        )
        console = self.preview.UartConsole.__new__(self.preview.UartConsole)
        console.app = app
        console._append = lines.append
        console.entry = Entry("Aé")
        console.mode = Mode("text")
        self.assertEqual(console._send_entry(), "break")
        self.assertEqual(sent, [0x41, 0xC3, 0xA9])
        self.assertTrue(console.entry.deleted)
        self.assertEqual(app.state.uart_rx_count, 0)

        console.entry = Entry("00 ff 41")
        console.mode = Mode("hex")
        self.assertEqual(console._send_entry(), "break")
        self.assertEqual(sent, [0x41, 0xC3, 0xA9, 0x00, 0xFF, 0x41])
        self.assertEqual(len(lines), 6)

    def test_uart_console_formats_tx_cycle_and_byte(self):
        console = self.preview.UartConsole.__new__(self.preview.UartConsole)
        lines = []
        console._append = lines.append
        console.append_tx((123).to_bytes(8, "little") + b"A")
        self.assertEqual(lines, ["[TX cycle=123] 0x41 'A'"])

    def test_input_direction_and_payload_guards_are_fail_closed(self):
        with self.assertRaises(self.preview.PreviewProtocolError):
            self.preview.encode_frame(self.preview.KIND_STATUS, 0, b"{}")
        with self.assertRaises(self.preview.PreviewProtocolError):
            self.preview.encode_uart_rx(0, 256)
        with self.assertRaises(self.preview.PreviewProtocolError):
            self.preview.encode_key_event(0, "A", "repeat")

    @staticmethod
    def audio_payload(rate=22_050, channels=2, frames=32, cycle=123):
        samples = []
        for frame in range(frames):
            for channel in range(channels):
                samples.append((frame * 17 + channel * 3) % 32_768)
        payload = (
            cycle.to_bytes(8, "little")
            + rate.to_bytes(4, "little")
            + channels.to_bytes(2, "little")
            + frames.to_bytes(2, "little")
        )
        return payload + b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)

    def test_audio_payload_accepts_variable_rate_and_block_length(self):
        payload = self.audio_payload(rate=22_050, frames=32)
        cycle, rate, channels, frames, samples = self.preview.parse_audio_pcm_payload(payload)
        self.assertEqual((cycle, rate, channels, frames), (123, 22_050, 2, 32))
        self.assertEqual(len(samples), 64)
        self.assertEqual(samples[:4], (0, 3, 17, 20))

    def test_audio_payload_rejects_unbounded_source_block(self):
        with self.assertRaises(self.preview.PreviewProtocolError):
            self.preview.parse_audio_pcm_payload(self.audio_payload(frames=129))

    def test_audio_resampler_is_stateful_and_bounded(self):
        resampler = self.preview.AudioResampler(48_000)
        first = resampler.process((0, 0) * 32, 22_050, 2)
        second = resampler.process((1_000, -1_000) * 32, 22_050, 2)
        tail = resampler.flush()
        self.assertTrue(resampler.resampled)
        self.assertGreater(len(first) + len(second) + len(tail), 0)
        self.assertLessEqual(resampler.max_buffer_frames, 64)
        self.assertEqual(len(first) % 2, 0)
        self.assertEqual(len(second) % 2, 0)

    def test_audio_monitor_off_never_starts_a_host_process(self):
        monitor = self.preview.AudioMonitor(enabled=False)
        try:
            self.assertTrue(monitor.consume_payload(self.audio_payload(rate=48_000)))
            status = monitor.status()
            self.assertEqual(status["state"], "off")
            self.assertEqual(status["frames_received"], 32)
            self.assertEqual(status["frames_sent"], 0)
            self.assertEqual(status["drop_count"], 0)
        finally:
            monitor.close()

    def test_audio_monitor_queue_drop_is_degraded_but_nonfatal(self):
        monitor = self.preview.AudioMonitor(enabled=True, queue_blocks=1)
        monitor._player_channels = 2
        with patch.object(monitor, "_ensure_player", return_value=True):
            self.assertTrue(monitor.consume_payload(self.audio_payload(rate=48_000)))
            self.assertTrue(monitor.consume_payload(self.audio_payload(rate=48_000, cycle=456)))
        try:
            status = monitor.status()
            self.assertEqual(status["state"], "degraded")
            self.assertEqual(status["drop_count"], 1)
            self.assertEqual(status["host_queue_drop_count"], 1)
            self.assertEqual(status["ingress_drop_count"], 0)
            self.assertEqual(status["overrun_count"], 1)
            self.assertEqual(status["queue_frames"], 32)
            self.assertEqual(status["frames_received"], 64)
        finally:
            monitor.close()

    def test_audio_monitor_records_reader_drops_separately(self):
        monitor = self.preview.AudioMonitor(enabled=False)
        try:
            monitor.record_ingress_drop(3)
            status = monitor.status()
            self.assertEqual(status["state"], "off")
            self.assertEqual(status["drop_count"], 3)
            self.assertEqual(status["ingress_drop_count"], 3)
            self.assertEqual(status["host_queue_drop_count"], 0)
            self.assertEqual(status["overrun_count"], 3)
        finally:
            monitor.close()

    def test_audio_monitor_reset_advances_stream_epoch_but_keeps_diagnostics(self):
        monitor = self.preview.AudioMonitor(enabled=False)
        try:
            self.assertEqual(monitor.status()["stream_epoch"], 0)
            monitor.record_ingress_drop()
            monitor.reset_stream()
            status = monitor.status()
            self.assertEqual(status["stream_epoch"], 1)
            self.assertEqual(status["drop_count"], 1)
            self.assertEqual(status["ingress_drop_count"], 1)
            self.assertEqual(status["source_rate_hz"], 0)
        finally:
            monitor.close()

    def test_preview_process_event_queue_is_bounded_and_counts_ingress_drops(self):
        process = self.preview.PreviewProcess({})
        self.assertEqual(process.events.maxsize, self.preview.EVENT_QUEUE_CAPACITY)
        process.events = self.preview.queue.Queue(maxsize=1)
        process.events.put(self.preview.PreviewEvent(self.preview.KIND_STATUS, b"{}"))
        process._enqueue_event(
            self.preview.PreviewEvent(
                self.preview.KIND_AUDIO_PCM_S16,
                self.audio_payload(rate=48_000),
            )
        )
        self.assertEqual(process.take_ingress_drops(), (1, 0, 0))

    def test_audio_monitor_rejects_unbounded_resample_expansion(self):
        monitor = self.preview.AudioMonitor(enabled=True)
        try:
            self.assertFalse(monitor.consume_payload(self.audio_payload(rate=1)))
            self.assertEqual(monitor.status()["state"], "degraded")
            self.assertEqual(monitor.status()["frames_received"], 32)
        finally:
            monitor.close()

    def test_audio_monitor_player_exit_is_degraded_not_emulation_failure(self):
        monitor = self.preview.AudioMonitor(
            enabled=True,
            player_command=[sys.executable, "-c", "import sys; sys.exit(0)"],
        )
        try:
            self.assertTrue(monitor.consume_payload(self.audio_payload(rate=48_000)))
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline and monitor.status()["state"] == "streaming":
                time.sleep(0.01)
            # A second block observes an already-exited player even when the
            # first short write raced with process startup.
            self.assertTrue(monitor.consume_payload(self.audio_payload(rate=48_000, cycle=456)))
            status = monitor.status()
            self.assertEqual(status["state"], "degraded")
            self.assertGreaterEqual(status["underrun_count"], 1)
        finally:
            monitor.close()

    def test_missing_host_player_is_timing_only(self):
        with patch.object(self.preview.shutil, "which", return_value=None):
            monitor = self.preview.AudioMonitor(enabled=True)
            try:
                self.assertTrue(monitor.consume_payload(self.audio_payload(rate=48_000)))
                self.assertEqual(monitor.status()["state"], "timing-only")
                self.assertEqual(monitor.status()["frames_received"], 32)
            finally:
                monitor.close()


if __name__ == "__main__":
    unittest.main()
