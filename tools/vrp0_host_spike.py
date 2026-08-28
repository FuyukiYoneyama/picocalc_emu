#!/usr/bin/env python3
"""Probe the local WSLg GUI and silent playback capabilities for VRP-0.

The probe deliberately uses only Python's standard library plus the host's
native Tk and PulseAudio client libraries.  It is not a preview implementation
and does not add a runtime dependency to picocalc_emu.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
import sys
import tkinter as tk
from pathlib import Path
from typing import Any, Dict, Optional


class SampleSpec(ctypes.Structure):
    _fields_ = [("format", ctypes.c_int), ("rate", ctypes.c_uint32), ("channels", ctypes.c_uint8)]


def gui_probe() -> Dict[str, Any]:
    result: Dict[str, Any] = {"available": False}
    try:
        root = tk.Tk()
        root.title("PicoCalc VRP-0 host probe")
        root.geometry("160x40")
        root.update_idletasks()
        root.update()
        root.destroy()
        result["available"] = True
        result["toolkit"] = "tkinter/Tk"
    except Exception as error:  # pragma: no cover - depends on host display
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def audio_probe() -> Dict[str, Any]:
    result: Dict[str, Any] = {"available": False, "silent": True}
    library_name = ctypes.util.find_library("pulse-simple")
    if not library_name:
        result["error"] = "libpulse-simple was not found"
        return result
    try:
        pulse = ctypes.CDLL(library_name)
        pulse.pa_simple_new.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_char_p, ctypes.POINTER(SampleSpec), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
        ]
        pulse.pa_simple_new.restype = ctypes.c_void_p
        pulse.pa_simple_write.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int)]
        pulse.pa_simple_write.restype = ctypes.c_int
        pulse.pa_simple_drain.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        pulse.pa_simple_drain.restype = ctypes.c_int
        pulse.pa_simple_free.argtypes = [ctypes.c_void_p]
        pulse.pa_simple_free.restype = None

        # PA_SAMPLE_S16LE=3 and PA_STREAM_PLAYBACK=1 are stable libpulse ABI values.
        spec = SampleSpec(3, 48000, 1)
        error_code = ctypes.c_int(0)
        stream = pulse.pa_simple_new(
            None, b"picocalc-vrp0-host-spike", 1, None, b"vrp0-silence",
            ctypes.byref(spec), None, None, ctypes.byref(error_code),
        )
        if not stream:
            result["error"] = f"pa_simple_new failed with error {error_code.value}"
            return result
        try:
            silence = (ctypes.c_int16 * 480)()
            if pulse.pa_simple_write(stream, ctypes.byref(silence), ctypes.sizeof(silence), ctypes.byref(error_code)) != 0:
                result["error"] = f"pa_simple_write failed with error {error_code.value}"
                return result
            if pulse.pa_simple_drain(stream, ctypes.byref(error_code)) != 0:
                result["error"] = f"pa_simple_drain failed with error {error_code.value}"
                return result
        finally:
            pulse.pa_simple_free(stream)
        result["available"] = True
        result["backend"] = library_name
        result["sample_rate"] = 48000
        result["channels"] = 1
        result["frames"] = 480
    except (OSError, AttributeError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def run_probe() -> Dict[str, Any]:
    environment = {
        name: os.environ.get(name)
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "PULSE_SERVER")
    }
    environment["pulse_socket_exists"] = bool(
        environment.get("PULSE_SERVER", "").startswith("unix:")
        and Path(environment["PULSE_SERVER"][5:]).exists()
    )
    gui = gui_probe()
    audio = audio_probe()
    return {
        "schema_version": 1,
        "probe_id": "vrp0-host-spike-20260828",
        "host": "Ubuntu 24.04 on WSL2/WSLg x86_64",
        "environment": environment,
        "checks": {"gui_window_open_close": gui, "silent_audio_playback": audio},
        "candidate_stack": {
            "gui": "winit + software framebuffer (candidate; not pinned in VRP-0)",
            "audio": "cpal (candidate; not pinned in VRP-0)",
            "license_policy": "No Rust GUI/audio dependency was added in VRP-0; selected crate license metadata must be checked before VRP-1 lockfile changes."
        },
        "status": "pass" if gui.get("available") and audio.get("available") else "inconclusive",
        "production_code_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the probe result as JSON")
    args = parser.parse_args()
    result = run_probe()
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
