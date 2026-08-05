/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * `emu_smoke` — Milestone 2's completion condition.
 *
 * "A dedicated application starts on the PC and produces screen, key and
 * file results deterministically." This is that application, and it also
 * serves as the worked example of how a test drives an app through
 * `picocalc::host`.
 *
 * Every check prints one line and the process exits non-zero if any of
 * them failed, so it is usable from CI without a test framework.
 *
 * Determinism is checked from the outside: `tools/picocalc.py` runs this
 * twice and compares the output byte for byte. Nothing here reads a wall
 * clock, a random source, or an address, so the two runs must agree.
 */

#include <stdio.h>
#include <string.h>

#include <string>

#include "pico/stdlib.h"
#include "picocalc/bsp.h"
#include "picocalc/host.h"

namespace {

int g_failures = 0;

void check(bool ok, const char* what, const std::string& detail) {
    printf("[%s] %s — %s\n", ok ? "pass" : "FAIL", what, detail.c_str());
    if (!ok) {
        ++g_failures;
    }
}

std::string number(unsigned long long n) {
    return std::to_string(n);
}

// --- the screen -------------------------------------------------------

void check_display() {
    picocalc::display::clear(0x0000);
    check(picocalc::host::non_black_pixels() == 0, "a cleared screen is black",
          number(picocalc::host::non_black_pixels()) + " non-black pixels");

    picocalc::display::fill_rect(10, 20, 30, 40, 0xF81F);
    check(picocalc::host::pixel(10, 20) == 0xF81F, "fill_rect paints its origin",
          "pixel (10,20) = " + number(picocalc::host::pixel(10, 20)));
    check(picocalc::host::pixel(39, 59) == 0xF81F, "fill_rect paints its far corner",
          "pixel (39,59) = " + number(picocalc::host::pixel(39, 59)));
    check(picocalc::host::pixel(40, 60) == 0x0000, "fill_rect stops at its edge",
          "pixel (40,60) = " + number(picocalc::host::pixel(40, 60)));
    check(picocalc::host::non_black_pixels_in(10, 20, 30, 40) == 30 * 40,
          "the rectangle is solid",
          number(picocalc::host::non_black_pixels_in(10, 20, 30, 40)) + " of 1200");

    // Off-viewport writes are dropped, not clamped. Clamping would paint
    // a stripe down the edge that hardware never shows.
    picocalc::display::fill_rect(-5, -5, 3, 3, 0xFFFF);
    check(picocalc::host::pixel(0, 0) == 0x0000, "off-screen writes are dropped",
          "pixel (0,0) = " + number(picocalc::host::pixel(0, 0)));

    // The window/write_pixels path, as an app streaming a sprite uses it.
    const uint16_t sprite[4] = {0x1111, 0x2222, 0x3333, 0x4444};
    picocalc::display::set_window(100, 100, 2, 2);
    picocalc::display::write_pixels(sprite, 4);
    const bool laid_out =
        picocalc::host::pixel(100, 100) == 0x1111 &&
        picocalc::host::pixel(101, 100) == 0x2222 &&
        picocalc::host::pixel(100, 101) == 0x3333 &&
        picocalc::host::pixel(101, 101) == 0x4444;
    check(laid_out, "write_pixels fills the window row by row",
          laid_out ? "all four in place" : "wrong order");

    // verify_pixels is what the template uses to decide app_status.
    const auto verify =
        picocalc::display::verify_pixels(100, 100, 2, 2, sprite, 4);
    check(verify.ok(), "verify_pixels reads back what was written",
          number(verify.pixels) + " pixels, " + number(verify.mismatches) +
              " mismatches");

    // The digest is the canonical RGB565 stream, identical in definition
    // to the firmware backend's — that is what makes host and firmware
    // runs comparable.
    const std::string digest = picocalc::host::framebuffer_sha256();
    check(digest.size() == 64, "the framebuffer digest is a SHA-256",
          digest.substr(0, 16) + "...");
    check(digest == picocalc::host::framebuffer_sha256(),
          "the digest is stable across calls", "unchanged");
}

// --- keys -------------------------------------------------------------

void check_keyboard() {
    picocalc::keyboard::init();
    picocalc::keyboard::KeyEvent event{};
    check(!picocalc::keyboard::read_event(&event), "an empty controller reports empty",
          number(picocalc::host::keys_queued()) + " queued");

    picocalc::host::queue_keys("ab");
    check(picocalc::host::keys_queued() == 4, "each key is a press and a release",
          number(picocalc::host::keys_queued()) + " events for 2 keys");

    // Drain the way an application does, keeping only presses.
    std::string pressed;
    while (picocalc::keyboard::read_event(&event)) {
        if (event.state == picocalc::keyboard::KeyState::Pressed) {
            pressed.push_back(static_cast<char>(event.key));
        }
    }
    check(pressed == "ab", "keys arrive in the order they were queued",
          "read '" + pressed + "'");

    // The controller's depth is a hardware constraint, reproduced here:
    // its count register carries the depth in five bits, so a queue of 32
    // would report itself empty and never be drained.
    picocalc::keyboard::init();
    for (int i = 0; i < 100; ++i) {
        picocalc::host::queue_key('x');
    }
    check(picocalc::host::keys_queued() == picocalc::host::max_queued_events,
          "the controller stops at the depth it can report",
          number(picocalc::host::keys_queued()) + " of " +
              number(picocalc::host::max_queued_events));
    check(picocalc::host::keys_dropped() == 200 - picocalc::host::max_queued_events,
          "overflow is counted, not silently absorbed",
          number(picocalc::host::keys_dropped()) + " dropped");
}

// --- files ------------------------------------------------------------

void check_filesystem() {
    namespace fs = picocalc::filesystem;
    // This exercises src/filesystem.cpp and ChanFatFS as the device
    // builds them; only the block device underneath is host memory.
    const fs::Error mounted = fs::mount();
    check(mounted == fs::Error::Ok, "the card mounts",
          fs::error_name(mounted));
    check(fs::mounted(), "the mount is visible to the app",
          fs::mounted() ? "mounted" : "not mounted");

    // The same sequence the template runs on the device: mount, write,
    // sync, read back, compare, remove. It is the BSP's own smoke test,
    // not a host-only substitute.
    const fs::SmokeResult smoke = fs::smoke_test();
    check(smoke.ok(), "the write/read/compare/remove sequence completes",
          std::string("stage=") + fs::stage_name(smoke.stage) +
              " detail=" + number(smoke.detail));

    check(picocalc::host::sd_sectors_written() > 0, "the card saw real writes",
          number(picocalc::host::sd_sectors_written()) + " sectors written");
    check(picocalc::host::sd_sectors_read() > 0, "and real reads",
          number(picocalc::host::sd_sectors_read()) + " sectors read");

    // A directory listing walks the root the smoke test just cleaned up.
    fs::DirectoryHandle dir{};
    const fs::Error opened = fs::open_dir("0:/", &dir);
    check(opened == fs::Error::Ok, "the root directory opens",
          fs::error_name(opened));
    if (opened == fs::Error::Ok) {
        fs::close_dir(&dir);
    }
}

// --- storage and time -------------------------------------------------

void check_psram_and_time() {
    check(picocalc::psram::available(), "PSRAM is available",
          number(picocalc::psram::capacity_bytes) + " bytes");

    const uint8_t pattern[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    uint8_t readback[8] = {};
    picocalc::psram::write(0x1000, pattern, sizeof(pattern));
    picocalc::psram::read(0x1000, readback, sizeof(readback));
    check(memcmp(pattern, readback, sizeof(pattern)) == 0,
          "PSRAM returns what was stored", "8 bytes at 0x1000");

    check(!picocalc::psram::write(picocalc::psram::capacity_bytes, pattern, 1),
          "a write past the end is refused", "at capacity");

    const uint64_t before = picocalc::host::now_us();
    sleep_ms(250);
    const uint64_t elapsed = picocalc::host::now_us() - before;
    check(elapsed == 250000, "sleep_ms advances virtual time without blocking",
          number(elapsed) + " us for 250 ms");
    (void)before;
}

}  // namespace

int main() {
    picocalc::host::reset_all();
    if (!picocalc::init()) {
        printf("[FAIL] picocalc::init() returned false\n");
        return 1;
    }

    check_display();
    check_keyboard();
    check_filesystem();
    check_psram_and_time();

    printf("emu_smoke: %s (%d failure%s)\n", g_failures == 0 ? "pass" : "FAIL",
           g_failures, g_failures == 1 ? "" : "s");
    return g_failures == 0 ? 0 : 1;
}
