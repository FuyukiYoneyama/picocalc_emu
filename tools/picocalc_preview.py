#!/usr/bin/env python3
"""Validated Realtime Preview frontend.

This module is deliberately a thin presentation client.  It never imports the
emulator core: the exact runner named by an admitted preview descriptor is
spawned as a child process and all machine interaction travels over the frozen
PCRP protocol.  Tk is imported lazily so protocol, input, and rendering tests
remain usable on hosts without a display server.
"""

from __future__ import annotations

import json
import hashlib
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Set, Tuple


MAGIC = b"PCRP"
PROTOCOL_VERSION = 1
HEADER_SIZE = 16
MAX_PAYLOAD = 8 * 1024 * 1024
DEFAULT_SKIN_SHA256 = "382c5d0a33225e3771c40ab0c3b0a421a87b82bc6104a1cb2bd22d8711d467da"
DEFAULT_SKIN_SIZE = (607, 1026)
LCD_SIZE = (320, 320)

KIND_HELLO = 1
KIND_STATUS = 2
KIND_FRAME_RGB565 = 3
KIND_AUDIO_PCM_S16 = 4
KIND_KEY_EVENT = 5
KIND_RESET = 6
KIND_QUIT = 7
KIND_UART_TX = 8
KIND_UART_RX = 9
KIND_ERROR = 10
KIND_GOODBYE = 11

RUNNER_KINDS = {
    KIND_HELLO,
    KIND_STATUS,
    KIND_FRAME_RGB565,
    KIND_AUDIO_PCM_S16,
    KIND_UART_TX,
    KIND_ERROR,
    KIND_GOODBYE,
}
INPUT_KINDS = {KIND_KEY_EVENT, KIND_RESET, KIND_QUIT, KIND_UART_RX}
KIND_NAMES = {
    KIND_HELLO: "hello",
    KIND_STATUS: "status",
    KIND_FRAME_RGB565: "frame_rgb565",
    KIND_AUDIO_PCM_S16: "audio_pcm_s16",
    KIND_KEY_EVENT: "key_event",
    KIND_RESET: "reset",
    KIND_QUIT: "quit",
    KIND_UART_TX: "uart_tx",
    KIND_UART_RX: "uart_rx",
    KIND_ERROR: "error",
    KIND_GOODBYE: "goodbye",
}


class PreviewProtocolError(ValueError):
    """A malformed or directionally invalid PCRP frame."""


def canonical_json(value: object) -> bytes:
    """Encode the schema-1 canonical JSON form used by the Rust peer."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PreviewProtocolError("cannot encode canonical JSON: {}".format(error)) from error


def _validate_binary_payload(kind: int, payload: bytes) -> None:
    if len(payload) > MAX_PAYLOAD:
        raise PreviewProtocolError("preview payload exceeds schema-1 limit")
    if kind in (KIND_RESET, KIND_QUIT) and payload:
        raise PreviewProtocolError("{} payload must be empty".format(KIND_NAMES[kind]))
    if kind == KIND_UART_RX and len(payload) != 1:
        raise PreviewProtocolError("uart_rx payload must be one byte")
    if kind == KIND_KEY_EVENT:
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PreviewProtocolError("key_event JSON is invalid: {}".format(error)) from error
        if canonical_json(value) != payload or not isinstance(value, dict):
            raise PreviewProtocolError("key_event JSON is not canonical")
        if not isinstance(value.get("key"), str) or value.get("state") not in {
            "down",
            "held",
            "up",
        }:
            raise PreviewProtocolError("key_event requires key and down/held/up state")
    if kind == KIND_UART_TX and len(payload) != 9:
        raise PreviewProtocolError("uart_tx payload must be nine bytes")
    if kind == KIND_FRAME_RGB565:
        if len(payload) < 12:
            raise PreviewProtocolError("frame_rgb565 payload is truncated")
        width = int.from_bytes(payload[8:10], "little")
        height = int.from_bytes(payload[10:12], "little")
        expected = 12 + width * height * 2
        if len(payload) != expected:
            raise PreviewProtocolError("frame_rgb565 payload length is invalid")
    if kind == KIND_AUDIO_PCM_S16:
        if len(payload) < 16:
            raise PreviewProtocolError("audio_pcm_s16 payload is truncated")
        channels = int.from_bytes(payload[12:14], "little")
        frames = int.from_bytes(payload[14:16], "little")
        expected = 16 + frames * channels * 2
        if channels == 0 or len(payload) != expected:
            raise PreviewProtocolError("audio_pcm_s16 payload length is invalid")
    if kind in (KIND_HELLO, KIND_STATUS, KIND_ERROR, KIND_GOODBYE):
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PreviewProtocolError("{} JSON is invalid: {}".format(KIND_NAMES[kind], error)) from error
        if canonical_json(value) != payload or not isinstance(value, dict):
            raise PreviewProtocolError("{} JSON is not canonical".format(KIND_NAMES[kind]))
        if kind == KIND_HELLO and (
            value.get("protocol") != "preview-ipc"
            or value.get("role") != "runner"
            or value.get("schema") != 1
        ):
            raise PreviewProtocolError("preview hello does not declare schema 1 runner")


def encode_frame(kind: int, sequence: int, payload: bytes = b"") -> bytes:
    """Encode one preview-to-runner frame and validate its direction."""

    if kind not in INPUT_KINDS:
        raise PreviewProtocolError("{} is not a preview input kind".format(kind))
    if type(sequence) is not int or sequence < 0 or sequence > 0xFFFFFFFF:
        raise PreviewProtocolError("preview sequence is outside uint32")
    _validate_binary_payload(kind, payload)
    return (
        MAGIC
        + PROTOCOL_VERSION.to_bytes(2, "little")
        + kind.to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
        + sequence.to_bytes(4, "little")
        + payload
    )


def encode_key_event(sequence: int, key: str, state: str) -> bytes:
    if state not in {"down", "held", "up"}:
        raise PreviewProtocolError("unsupported key state {}".format(state))
    return encode_frame(
        KIND_KEY_EVENT,
        sequence,
        canonical_json({"key": key, "state": state}),
    )


def encode_uart_rx(sequence: int, value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= 255:
        raise PreviewProtocolError("UART RX byte is outside uint8")
    return encode_frame(KIND_UART_RX, sequence, bytes((value,)))


def parse_rgb565_payload(payload: bytes) -> Tuple[int, int, int, bytes]:
    """Return (virtual_cycle, width, height, little-endian pixel bytes)."""

    _validate_binary_payload(KIND_FRAME_RGB565, payload)
    return (
        int.from_bytes(payload[0:8], "little"),
        int.from_bytes(payload[8:10], "little"),
        int.from_bytes(payload[10:12], "little"),
        payload[12:],
    )


def rgb565_to_rgb888(pixel: int) -> Tuple[int, int, int]:
    """Convert RGB565 to display RGB888 using bit replication."""

    red = (pixel >> 11) & 0x1F
    green = (pixel >> 5) & 0x3F
    blue = pixel & 0x1F
    return (
        (red << 3) | (red >> 2),
        (green << 2) | (green >> 4),
        (blue << 3) | (blue >> 2),
    )


def rgb565_to_ppm(payload: bytes, out_width: Optional[int] = None, out_height: Optional[int] = None) -> bytes:
    """Convert an RGB565 frame to a PPM image, optionally nearest-neighbour scaled."""

    _cycle, width, height, pixels = parse_rgb565_payload(payload)
    target_width = width if out_width is None else out_width
    target_height = height if out_height is None else out_height
    if target_width <= 0 or target_height <= 0:
        raise PreviewProtocolError("RGB565 target dimensions must be positive")
    rgb = bytearray(width * height * 3)
    for index in range(width * height):
        pixel = int.from_bytes(pixels[index * 2:index * 2 + 2], "little")
        rgb[index * 3:index * 3 + 3] = bytes(rgb565_to_rgb888(pixel))
    if target_width != width or target_height != height:
        scaled = bytearray(target_width * target_height * 3)
        for y in range(target_height):
            source_y = min(height - 1, y * height // target_height)
            for x in range(target_width):
                source_x = min(width - 1, x * width // target_width)
                src = (source_y * width + source_x) * 3
                dst = (y * target_width + x) * 3
                scaled[dst:dst + 3] = rgb[src:src + 3]
        rgb = scaled
    return (
        "P6\n{} {}\n255\n".format(target_width, target_height).encode("ascii")
        + bytes(rgb)
    )


def ppm_photo_data(ppm: bytes) -> bytes:
    """Return PPM bytes in the form accepted by Tk ``PhotoImage``."""

    # Tk accepts binary PPM data directly when ``format=PPM`` is supplied.
    # Base64 text is not portable across Tk builds (some interpret it as an
    # encoded GIF/PNG payload), so keep the presentation conversion explicit.
    return ppm


def canonical_key(keysym: str, char: str = "") -> Optional[str]:
    """Map Tk key names to the backend's stable key vocabulary."""

    aliases = {
        "Return": "Enter",
        "KP_Enter": "Enter",
        "Escape": "Escape",
        "space": "Space",
        "Tab": "Tab",
        "BackSpace": "Backspace",
    }
    if keysym in aliases:
        return aliases[keysym]
    if len(char) == 1 and ord(char) < 128 and char.isprintable():
        return char
    if len(keysym) == 1 and ord(keysym) < 128:
        return keysym
    return None


class KeyDispatcher:
    """Translate host key transitions while suppressing OS repeat key-downs."""

    def __init__(self, send: Callable[[str, str], None]) -> None:
        self._send = send
        self.held: Set[str] = set()

    def press(self, key: str) -> bool:
        if key in self.held:
            return False
        self.held.add(key)
        self._send(key, "down")
        return True

    def emit_held(self) -> int:
        for key in sorted(self.held):
            self._send(key, "held")
        return len(self.held)

    def release(self, key: str) -> bool:
        if key not in self.held:
            return False
        self.held.remove(key)
        self._send(key, "up")
        return True

    def release_all(self) -> None:
        for key in sorted(tuple(self.held)):
            self.release(key)


class PreviewEvent:
    def __init__(
        self,
        kind: int,
        payload: bytes = b"",
        error: Optional[BaseException] = None,
    ) -> None:
        self.kind = kind
        self.payload = payload
        self.error = error


class PreviewProcess:
    """Own the validated runner process and the protocol direction/sequence."""

    def __init__(self, contract: Dict[str, Any]) -> None:
        self.contract = contract
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.events: "queue.Queue[PreviewEvent]" = queue.Queue()
        self.stderr_lines: "queue.Queue[str]" = queue.Queue()
        self._send_lock = threading.Lock()
        self._next_sequence = 0
        self._reader: Optional[threading.Thread] = None
        self._stderr_reader: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.saw_goodbye = False

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    def start(self) -> None:
        if self.process is not None:
            raise RuntimeError("preview process is already running")
        argv = self.contract["argv"]
        self.process = subprocess.Popen(
            argv,
            cwd=self.contract["cwd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        self._reader = threading.Thread(target=self._read_loop, name="picocalc-preview-reader", daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(
            target=self._read_stderr_loop,
            name="picocalc-preview-stderr",
            daemon=True,
        )
        self._stderr_reader.start()

    def _read_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        sequence = 0
        stream = self.process.stdout
        try:
            while not self._stop.is_set():
                header = self._read_exact(stream, HEADER_SIZE)
                if not header:
                    if self._stop.is_set():
                        return
                    raise EOFError("preview backend closed stdout before goodbye")
                if len(header) != HEADER_SIZE:
                    raise PreviewProtocolError("preview backend sent truncated header")
                if header[:4] != MAGIC:
                    raise PreviewProtocolError("preview backend sent bad IPC magic")
                version = int.from_bytes(header[4:6], "little")
                kind = int.from_bytes(header[6:8], "little")
                length = int.from_bytes(header[8:12], "little")
                got_sequence = int.from_bytes(header[12:16], "little")
                if version != PROTOCOL_VERSION:
                    raise PreviewProtocolError("preview backend sent unsupported IPC version")
                if kind not in RUNNER_KINDS:
                    raise PreviewProtocolError("preview backend sent input-only or unknown kind {}".format(kind))
                if got_sequence != sequence:
                    raise PreviewProtocolError(
                        "preview backend sequence discontinuity: expected {}, got {}".format(
                            sequence, got_sequence
                        )
                    )
                if length > MAX_PAYLOAD:
                    raise PreviewProtocolError("preview backend payload exceeds schema-1 limit")
                payload = self._read_exact(stream, length)
                if len(payload) != length:
                    raise PreviewProtocolError("preview backend sent truncated payload")
                _validate_binary_payload(kind, payload)
                self.events.put(PreviewEvent(kind, payload))
                sequence += 1
                if kind == KIND_GOODBYE:
                    self.saw_goodbye = True
                    return
        except BaseException as error:  # reader errors must reach the UI as sticky invalid
            if not self._stop.is_set():
                self.events.put(PreviewEvent(0, error=error))

    @staticmethod
    def _read_exact(stream: Any, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = stream.read(length - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    def _read_stderr_loop(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        try:
            for line in iter(self.process.stderr.readline, b""):
                self.stderr_lines.put(line.decode("utf-8", errors="replace").rstrip("\r\n"))
        except OSError as error:
            if not self._stop.is_set():
                self.stderr_lines.put("stderr read failed: {}".format(error))

    def send(self, data: bytes) -> int:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("preview process is not running")
        with self._send_lock:
            sequence = self._next_sequence
            # The sequence is encoded by the caller.  Increment only after the
            # complete write so a failed pipe cannot silently consume a slot.
            if int.from_bytes(data[12:16], "little") != sequence:
                raise PreviewProtocolError("preview input sequence is out of order")
            self.process.stdin.write(data)
            self.process.stdin.flush()
            self._next_sequence += 1
            return sequence

    def send_key(self, key: str, state: str) -> int:
        return self.send(encode_key_event(self._next_sequence, key, state))

    def send_uart(self, value: int) -> int:
        return self.send(encode_uart_rx(self._next_sequence, value))

    def send_reset(self) -> int:
        return self.send(encode_frame(KIND_RESET, self._next_sequence))

    def send_quit(self) -> int:
        return self.send(encode_frame(KIND_QUIT, self._next_sequence))

    def stop(self, timeout: float = 2.0) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None and not self.saw_goodbye:
                self.send_quit()
                process.wait(timeout=timeout)
            elif process.poll() is None:
                process.wait(timeout=timeout)
        except (BrokenPipeError, OSError, RuntimeError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        finally:
            self._stop.set()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            self.process = None


class PreviewState:
    def __init__(
        self,
        target_id: str,
        target_revision: int,
        receipt_id: str = "",
        backend_commit: str = "",
        firmware_sha256: str = "",
        hardware_verdict: str = "not_claimed",
    ) -> None:
        self.target_id = target_id
        self.target_revision = target_revision
        self.receipt_id = receipt_id
        self.backend_commit = backend_commit
        self.firmware_sha256 = firmware_sha256
        self.hardware_verdict = hardware_verdict
        self.latest_status: Dict[str, Any] = {}
        self.frame_payload: Optional[bytes] = None
        self.frame_cycle = 0
        self.uart_tx_bytes = bytearray()
        self.uart_tx_count = 0
        self.uart_rx_count = 0
        self.uart_error_count = 0
        self.audio_frames = 0
        self.presentation_drop_count = 0
        self.diagnostics: Deque[str] = deque(maxlen=200)
        self.ux_invalid = False
        self.ux_reason = ""
        self.goodbye = False

    def mark_invalid(self, reason: str) -> None:
        self.ux_invalid = True
        self.ux_reason = reason
        self.diagnostics.append("UX INVALID: {}".format(reason))

    def apply_status(self, status: Dict[str, Any]) -> None:
        self.latest_status = status
        if status.get("coverage") not in (None, "ok"):
            self.mark_invalid("coverage={}".format(status.get("coverage")))
        observation = status.get("observation")
        if isinstance(observation, dict):
            projection = observation.get("projection")
            if isinstance(projection, dict):
                unsupported = projection.get("unsupported_mmio")
                if isinstance(unsupported, dict) and unsupported.get("truncated"):
                    self.mark_invalid("unsupported MMIO attribution truncated")
                if isinstance(unsupported, dict) and unsupported.get("count", 0):
                    self.mark_invalid("unsupported MMIO observed")

    def apply(self, event: PreviewEvent) -> None:
        if event.error is not None:
            self.mark_invalid(str(event.error))
            return
        if event.kind == KIND_HELLO:
            return
        if event.kind == KIND_STATUS:
            try:
                value = json.loads(event.payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                self.mark_invalid("status JSON decode failed: {}".format(error))
                return
            if isinstance(value, dict):
                self.apply_status(value)
            else:
                self.mark_invalid("status JSON is not an object")
        elif event.kind == KIND_FRAME_RGB565:
            try:
                _cycle, _width, _height, _pixels = parse_rgb565_payload(event.payload)
                self.frame_payload = event.payload
                self.frame_cycle = _cycle
            except PreviewProtocolError as error:
                self.mark_invalid(str(error))
        elif event.kind == KIND_UART_TX:
            cycle = int.from_bytes(event.payload[:8], "little")
            value = event.payload[8]
            self.uart_tx_bytes.append(value)
            self.uart_tx_count += 1
            self.diagnostics.append("TX @{}: 0x{:02x}".format(cycle, value))
        elif event.kind == KIND_AUDIO_PCM_S16:
            self.audio_frames += int.from_bytes(event.payload[14:16], "little")
        elif event.kind == KIND_ERROR:
            try:
                value = json.loads(event.payload.decode("utf-8"))
                code = value.get("code", "preview_error") if isinstance(value, dict) else "preview_error"
                message = value.get("message", "") if isinstance(value, dict) else ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                code, message = "preview_error", "malformed error payload"
            self.uart_error_count += 1
            self.mark_invalid("{}: {}".format(code, message).rstrip(": "))
        elif event.kind == KIND_GOODBYE:
            self.goodbye = True


def _status_text(state: PreviewState, skin_loaded: bool) -> str:
    status = state.latest_status
    pacer = status.get("pacer", {}) if isinstance(status, dict) else {}
    ratio = pacer.get("ratio_ppm")
    ratio_text = "n/a" if not isinstance(ratio, (int, float)) else "{:.3f}%".format(float(ratio) / 10000.0)
    coverage = status.get("coverage", "unknown") if isinstance(status, dict) else "unknown"
    audio = status.get("audio", {}) if isinstance(status, dict) else {}
    audio_state = audio.get("state", "unknown") if isinstance(audio, dict) else "unknown"
    uart = status.get("uart", {}) if isinstance(status, dict) else {}
    identity = "{} r{}".format(state.target_id, state.target_revision)
    receipt = state.receipt_id or "unknown"
    backend = state.backend_commit[:12] if state.backend_commit else "unknown"
    firmware = state.firmware_sha256[:12] if state.firmware_sha256 else "unknown"
    flags = [
        identity,
        "validation admitted receipt {}".format(receipt),
        "backend {}".format(backend),
        "bin {}".format(firmware),
        "hardware {}".format(state.hardware_verdict),
        "ratio {}".format(ratio_text),
        "cycle {}".format(status.get("virtual_cycle", state.frame_cycle)),
    ]
    flags.append(
        "timing lag_ns {} behind {}".format(
            pacer.get("lag_ns", "n/a"), pacer.get("behind_count", "n/a")
        )
    )
    flags.append("coverage {}".format(coverage))
    flags.append("audio {}".format(audio_state))
    flags.append(
        "UART TX {} RX {} overrun {} disabled {} errors {}".format(
            uart.get("tx_bytes", state.uart_tx_count),
            uart.get("rx_accepted", state.uart_rx_count),
            uart.get("rx_overrun", "n/a"),
            uart.get("rx_disabled", "n/a"),
            state.uart_error_count,
        )
    )
    flags.append("presentation drops {}".format(state.presentation_drop_count))
    flags.append("skin {}".format("on" if skin_loaded else "unavailable"))
    if state.ux_invalid:
        flags.append("UX INVALID: {}".format(state.ux_reason))
    return " | ".join(str(flag) for flag in flags)


def _default_skin_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets/preview/picocalc-device-skin.png"


class PreviewApp:
    """Tk presentation layer; importing this class does not require Tk."""

    def __init__(
        self,
        descriptor: Dict[str, Any],
        process: PreviewProcess,
        skin_path: Optional[Path],
        scale: int = 2,
        screenshot_dir: Optional[Path] = None,
        smoke_seconds: Optional[float] = None,
        skin_error: Optional[str] = None,
        backend_override: Optional[Path] = None,
    ) -> None:
        try:
            import tkinter as tk
        except ImportError as error:
            raise RuntimeError("Tkinter is required for preview-gui") from error
        self.tk = tk
        self.descriptor = descriptor
        self.process = process
        self.skin_path = skin_path
        self.scale = max(1, int(scale))
        self.screenshot_dir = screenshot_dir or Path.cwd() / "preview-screenshots"
        self.smoke_seconds = smoke_seconds
        self.backend_override = backend_override
        target = descriptor["target"]
        self.state = PreviewState(
            target["id"],
            target["revision"],
            receipt_id=str(descriptor.get("receipt_id", "")),
            backend_commit=str(descriptor.get("backend", {}).get("commit", "")),
            firmware_sha256=str(descriptor.get("firmware", {}).get("sha256", "")),
            hardware_verdict=str(descriptor.get("hardware_verdict", "not_claimed")),
        )
        if skin_error:
            self.state.mark_invalid(skin_error)
        self.root = tk.Tk()
        self.root.title("PicoCalc Preview — {} r{}".format(target["id"], target["revision"]))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<F5>", self._on_reset)
        self.root.bind("<Control-r>", self._on_reload)
        self.root.bind("<F12>", self._on_screenshot)
        self.root.bind("<Escape>", self._on_quit)
        self.root.bind_all("<KeyPress>", self._on_key_press, add="+")
        self.root.bind_all("<KeyRelease>", self._on_key_release, add="+")
        self.root.bind_all("<F5>", self._on_reset, add="+")
        self.root.bind_all("<Control-r>", self._on_reload, add="+")
        self.root.bind_all("<F12>", self._on_screenshot, add="+")
        self.root.bind_all("<Escape>", self._on_quit, add="+")
        self.skin_photo = None
        self.frame_photo = None
        self.canvas = None
        self.status_var = tk.StringVar(value="starting preview…")
        self._setup_main_window()
        self.console = UartConsole(self)
        self.key_dispatcher = KeyDispatcher(self._send_key)
        self._closed = False
        self.root.after(30, self._drain_events)
        self.root.after(120, self._emit_held)
        if smoke_seconds is not None:
            self.root.after(max(1, int(smoke_seconds * 1000)), self.close)

    def _setup_main_window(self) -> None:
        tk = self.tk
        if self.skin_path is not None:
            try:
                self.skin_photo = tk.PhotoImage(file=str(self.skin_path))
            except tk.TclError as error:
                self.state.mark_invalid("skin unavailable: {}".format(error))
                self.skin_photo = None
        if self.skin_photo is not None:
            width = self.skin_photo.width()
            height = self.skin_photo.height()
            if (width, height) != DEFAULT_SKIN_SIZE:
                self.state.mark_invalid(
                    "skin unavailable: expected {}x{}, got {}x{}".format(
                        DEFAULT_SKIN_SIZE[0], DEFAULT_SKIN_SIZE[1], width, height
                    )
                )
                self.skin_photo = None
        if self.skin_photo is not None:
            width = self.skin_photo.width()
            height = self.skin_photo.height()
            self.canvas = tk.Canvas(self.root, width=width, height=height, highlightthickness=0)
            self.canvas.pack(fill="both", expand=False)
            self.canvas.create_image(0, 0, image=self.skin_photo, anchor="nw", tags=("skin",))
        else:
            width = 320 * self.scale
            height = 320 * self.scale
            self.canvas = tk.Canvas(self.root, width=width, height=height, background="black", highlightthickness=0)
            self.canvas.pack(fill="both", expand=False)
        self.tk.Label(self.root, textvariable=self.status_var, anchor="w", justify="left").pack(fill="x")

    def _send_key(self, key: str, state: str) -> None:
        try:
            self.process.send_key(key, state)
        except (BrokenPipeError, OSError, RuntimeError, PreviewProtocolError) as error:
            self.state.mark_invalid("key send failed: {}".format(error))

    def _event_is_uart_window(self, event: Any) -> bool:
        """Return whether a Tk event belongs to a UART text-entry widget.

        The keyboard binding is installed with ``bind_all`` so the PicoCalc
        body remains usable regardless of focus.  Without this guard it would
        also consume printable KeyPress events in the UART entry/text widgets,
        making it impossible to type a UART command.  Buttons and radio
        controls are not excluded, so their normal Tk keyboard behavior stays
        available.  Reserved global shortcuts are handled by their own
        bindings and are intentionally not affected by this predicate.
        """

        console = getattr(self, "console", None)
        widget = getattr(event, "widget", None)
        if console is None or widget is None:
            return False
        try:
            return (
                str(widget.winfo_toplevel()) == str(console.window)
                and widget.winfo_class() in {"Entry", "Text"}
            )
        except (self.tk.TclError, AttributeError):
            return False

    def _on_key_press(self, event: Any) -> str:
        keysym = getattr(event, "keysym", "")
        # Let the dedicated global bindings receive operator shortcuts.  In
        # particular, Ctrl+R must not be turned into a guest ``r`` key event.
        if keysym in {"F5", "F12", "Escape"} or (
            getattr(event, "state", 0) & 0x4 and keysym.lower() == "r"
        ):
            return ""
        if self._event_is_uart_window(event):
            return ""
        key = canonical_key(keysym, getattr(event, "char", ""))
        if key is not None:
            self.key_dispatcher.press(key)
            return "break"
        return ""

    def _on_key_release(self, event: Any) -> str:
        keysym = getattr(event, "keysym", "")
        if keysym in {"F5", "F12", "Escape"} or (
            getattr(event, "state", 0) & 0x4 and keysym.lower() == "r"
        ):
            return ""
        if self._event_is_uart_window(event):
            return ""
        key = canonical_key(keysym, getattr(event, "char", ""))
        if key is not None:
            self.key_dispatcher.release(key)
            return "break"
        return ""

    def _emit_held(self) -> None:
        if not self._closed:
            self.key_dispatcher.emit_held()
            self.root.after(120, self._emit_held)

    def _on_reset(self, _event: Any = None) -> str:
        try:
            # Do not carry a host-held key across a machine reset.  The
            # release events belong to the old virtual input state and are
            # emitted before the reset command on the same PCRP stream.
            self.key_dispatcher.release_all()
            self.process.send_reset()
            self.state.diagnostics.append("operator reset requested; sticky UX state retained")
        except (BrokenPipeError, OSError, RuntimeError, PreviewProtocolError) as error:
            self.state.mark_invalid("reset failed: {}".format(error))
        return "break"

    def _on_reload(self, _event: Any = None) -> str:
        # Import lazily to avoid a tools package/module name collision when
        # picocalc.py is loaded by the test suite.
        try:
            import picocalc

            backend_override = getattr(self, "backend_override", None) or Path(
                self.descriptor["backend"]["directory"]
            )
            descriptor_path = Path(self.descriptor["__path"])
            new_descriptor, _target, _firmware, _backend, _runner, contract = picocalc._validate_preview_descriptor(
                descriptor_path, backend_override
            )
        except Exception as error:  # reload must be fail-closed, not a traceback-only UX
            self.state.mark_invalid("VALIDATION LOST — RELOAD REFUSED: {}".format(error))
            self.process.stop()
            self.status_var.set(_status_text(self.state, self.skin_photo is not None))
            return "break"
        self.key_dispatcher.release_all()
        self.process.stop()
        self.process = PreviewProcess(contract)
        try:
            self.process.start()
            self.key_dispatcher = KeyDispatcher(self._send_key)
            new_descriptor["__path"] = str(descriptor_path)
            self.descriptor = new_descriptor
            new_target = new_descriptor["target"]
            self.state.target_id = new_target["id"]
            self.state.target_revision = new_target["revision"]
            self.state.receipt_id = str(new_descriptor.get("receipt_id", ""))
            self.state.backend_commit = str(new_descriptor.get("backend", {}).get("commit", ""))
            self.state.firmware_sha256 = str(new_descriptor.get("firmware", {}).get("sha256", ""))
            self.state.hardware_verdict = str(new_descriptor.get("hardware_verdict", "not_claimed"))
            self.state.ux_invalid = False
            self.state.ux_reason = ""
            self.state.latest_status = {}
            self.state.frame_payload = None
            self.state.uart_tx_bytes.clear()
            self.state.uart_tx_count = 0
            self.state.uart_rx_count = 0
            self.state.uart_error_count = 0
            self.state.audio_frames = 0
            self.state.presentation_drop_count = 0
            self.state.goodbye = False
            self.state.diagnostics.append("admission revalidated; preview reloaded")
        except Exception as error:
            self.state.mark_invalid("reload start failed: {}".format(error))
        return "break"

    def _on_screenshot(self, _event: Any = None) -> str:
        try:
            path = self.save_screenshot()
            self.state.diagnostics.append("screenshot: {}".format(path))
        except (OSError, RuntimeError) as error:
            self.state.mark_invalid("screenshot failed: {}".format(error))
        return "break"

    def _on_quit(self, _event: Any = None) -> str:
        self.close()
        return "break"

    def _render_frame(self) -> None:
        if self.canvas is None or self.state.frame_payload is None:
            return
        _cycle, width, height, _pixels = parse_rgb565_payload(self.state.frame_payload)
        if (width, height) != LCD_SIZE:
            raise PreviewProtocolError(
                "framebuffer dimensions are {}x{}, expected {}x{}".format(
                    width, height, LCD_SIZE[0], LCD_SIZE[1]
                )
            )
        if self.skin_photo is not None:
            # Calibrated against the supplied 607x1026 portrait asset.  The
            # opening is intentionally presentation-only; it does not alter
            # the 320x320 framebuffer or any validation digest.
            opening = (38, 69, 520, 475)
            target_width, target_height = opening[2], opening[3]
            ppm = rgb565_to_ppm(self.state.frame_payload, target_width, target_height)
            self.frame_photo = self.tk.PhotoImage(data=ppm_photo_data(ppm), format="PPM")
            self.canvas.delete("lcd")
            self.canvas.create_image(opening[0], opening[1], image=self.frame_photo, anchor="nw", tags=("lcd",))
        else:
            ppm = rgb565_to_ppm(self.state.frame_payload, width * self.scale, height * self.scale)
            self.frame_photo = self.tk.PhotoImage(data=ppm_photo_data(ppm), format="PPM")
            self.canvas.delete("lcd")
            self.canvas.create_image(0, 0, image=self.frame_photo, anchor="nw", tags=("lcd",))

    def _drain_events(self) -> None:
        if self._closed:
            return
        latest_frame: Optional[PreviewEvent] = None
        while True:
            try:
                event = self.process.events.get_nowait()
            except queue.Empty:
                break
            if event.kind == KIND_FRAME_RGB565:
                if latest_frame is not None:
                    self.state.presentation_drop_count += 1
                latest_frame = event
            else:
                self.state.apply(event)
                if event.kind == KIND_UART_TX:
                    self.console.append_tx(event.payload)
                elif event.kind == KIND_ERROR:
                    self.console.append_diagnostic(self.state.ux_reason)
                elif event.kind == KIND_GOODBYE:
                    self.console.append_diagnostic("runner goodbye")
        if latest_frame is not None:
            self.state.apply(latest_frame)
            try:
                self._render_frame()
            except (RuntimeError, PreviewProtocolError, self.tk.TclError) as error:
                self.state.mark_invalid("frame presentation failed: {}".format(error))
                self.console.append_diagnostic(self.state.ux_reason)
        while True:
            try:
                line = self.process.stderr_lines.get_nowait()
            except queue.Empty:
                break
            self.state.diagnostics.append("runner stderr: {}".format(line))
            self.console.append_diagnostic(line)
        child = self.process.process
        reader_finished = self.process._reader is not None and not self.process._reader.is_alive()
        if (
            child is not None
            and child.poll() is not None
            and reader_finished
            and not self.process.saw_goodbye
        ):
            self.state.mark_invalid(
                "preview backend exited before goodbye (status {})".format(child.returncode)
            )
        self.status_var.set(_status_text(self.state, self.skin_photo is not None))
        self.root.after(30, self._drain_events)

    def save_screenshot(self) -> Path:
        if self.canvas is None or self.frame_photo is None:
            raise RuntimeError("no framebuffer has been received yet")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.screenshot_dir / "preview-{}.png".format(stamp)
        if self.skin_photo is None:
            self.frame_photo.write(str(path), format="png")
            return path
        # Tk can export the composed canvas as PostScript.  Use ImageMagick
        # only for the optional presentation artifact; if unavailable retain a
        # clearly named .ps file rather than pretending it is a PNG.
        with tempfile.NamedTemporaryFile(prefix="picocalc-preview-", suffix=".ps", delete=False) as temp:
            ps_path = Path(temp.name)
        try:
            self.canvas.postscript(file=str(ps_path), colormode="color")
            convert = shutil.which("convert")
            if convert is None:
                fallback = path.with_suffix(".ps")
                ps_path.replace(fallback)
                return fallback
            completed = subprocess.run(
                [convert, str(ps_path), str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError("ImageMagick convert failed: {}".format(completed.stderr.decode(errors="replace")))
            return path
        finally:
            if ps_path.exists():
                ps_path.unlink()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.key_dispatcher.release_all()
        self.process.stop()
        try:
            self.console.close_window()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


class UartConsole:
    """Separate UART0 TX/RX window automatically opened with the preview."""

    def __init__(self, app: PreviewApp) -> None:
        self.app = app
        tk = app.tk
        self.window = tk.Toplevel(app.root)
        self.window.title("PicoCalc UART0 — {}".format(app.state.target_id))
        self.window.protocol("WM_DELETE_WINDOW", self.close_window)
        self.text = tk.Text(self.window, width=100, height=24, state="disabled", wrap="none")
        self.text.pack(fill="both", expand=True)
        controls = tk.Frame(self.window)
        controls.pack(fill="x")
        self.mode = tk.StringVar(value="text")
        tk.Radiobutton(controls, text="text", variable=self.mode, value="text").pack(side="left")
        tk.Radiobutton(controls, text="raw hex", variable=self.mode, value="hex").pack(side="left")
        self.entry = tk.Entry(controls)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._send_entry)
        tk.Button(controls, text="Send RX", command=self._send_entry).pack(side="left")
        self.append_diagnostic("UART0 console connected (TX/RX are virtual UART wires)")

    def _append(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def append_diagnostic(self, line: str) -> None:
        self._append("[diag] {}".format(line))

    def append_tx(self, payload: bytes) -> None:
        cycle = int.from_bytes(payload[:8], "little")
        value = payload[8]
        char = chr(value) if 32 <= value < 127 else "·"
        self._append("[TX cycle={}] 0x{:02X} {}".format(cycle, value, repr(char)))

    def _send_entry(self, _event: Any = None) -> str:
        raw = self.entry.get()
        try:
            if self.mode.get() == "hex":
                compact = re.sub(r"[\s,:_-]+", "", raw)
                if not compact or len(compact) % 2:
                    raise ValueError("raw hex must contain complete byte pairs")
                data = bytes.fromhex(compact)
            else:
                data = raw.encode("utf-8")
            for value in data:
                self.app.process.send_uart(value)
                self._append("[RX] 0x{:02X} {}".format(value, repr(chr(value) if 32 <= value < 127 else "·")))
            self.entry.delete(0, "end")
        except (ValueError, UnicodeEncodeError, BrokenPipeError, OSError, RuntimeError, PreviewProtocolError) as error:
            self.app.state.mark_invalid("UART RX send failed: {}".format(error))
            self.append_diagnostic(self.app.state.ux_reason)
        return "break"

    def close_window(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.append_diagnostic("console closed; UART0 remains connected to the runner")
            self.window.withdraw()


def run_gui(
    descriptor_path: Path,
    backend_override: Optional[Path],
    skin_path: Optional[Path],
    scale: int,
    screenshot_dir: Optional[Path],
    smoke_seconds: Optional[float] = None,
) -> int:
    """Validate an admitted descriptor, then run the two-window preview."""

    try:
        # Import via the script directory when called from picocalc.py.  This
        # avoids `from tools import picocalc`, whose package name can collide
        # with unrelated installed modules.
        import picocalc

        descriptor, _target, _firmware, _backend, _runner, contract = picocalc._validate_preview_descriptor(
            descriptor_path.resolve(), backend_override
        )
        descriptor["__path"] = str(descriptor_path.resolve())
    except Exception as error:
        print("preview-gui: REFUSED: {}".format(error), file=os.sys.stderr)
        return 1
    explicit_no_skin = skin_path is not None and str(skin_path).lower() == "none"
    if skin_path is None:
        skin = _default_skin_path()
        skin_path = skin if skin.is_file() else None
    elif explicit_no_skin:
        skin_path = None
    skin_error = None
    if skin_path is None and not explicit_no_skin:
        skin_error = "skin unavailable: bundled asset is missing"
    elif skin_path is not None and skin_path.resolve() == _default_skin_path().resolve():
        actual_skin_sha = hashlib.sha256(skin_path.read_bytes()).hexdigest()
        if actual_skin_sha != DEFAULT_SKIN_SHA256:
            skin_error = "skin unavailable: bundled asset SHA-256 mismatch"
            skin_path = None
    process = PreviewProcess(contract)
    try:
        process.start()
        app = PreviewApp(
            descriptor,
            process,
            skin_path,
            scale,
            screenshot_dir,
            smoke_seconds,
            skin_error,
            backend_override,
        )
        app.run()
        return 0 if not app.state.ux_invalid else 2
    except Exception as error:
        print("preview-gui: FAIL: {}".format(error), file=os.sys.stderr)
        process.stop()
        return 2


__all__ = [
    "KIND_AUDIO_PCM_S16",
    "KIND_ERROR",
    "KIND_FRAME_RGB565",
    "KIND_GOODBYE",
    "KIND_HELLO",
    "KIND_KEY_EVENT",
    "KIND_QUIT",
    "KIND_RESET",
    "KIND_STATUS",
    "KIND_UART_RX",
    "KIND_UART_TX",
    "KeyDispatcher",
    "PreviewEvent",
    "PreviewProcess",
    "PreviewProtocolError",
    "PreviewState",
    "canonical_key",
    "canonical_json",
    "encode_frame",
    "encode_key_event",
    "encode_uart_rx",
    "parse_rgb565_payload",
    "rgb565_to_ppm",
    "run_gui",
]
