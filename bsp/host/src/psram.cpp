/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * PSRAM as eight megabytes of host memory.
 *
 * The device's PSRAM is reached over PIO1 and DMA at a clock divider
 * chosen by probing; none of that exists here. What is kept is the part
 * an application can depend on: the capacity, the bounds behaviour, and
 * the fact that a failed init leaves PSRAM unavailable rather than
 * silently aliasing SRAM.
 *
 * `info().id` reports the identity the real chip returns, taken from the
 * hardware correlation run of 2026-08-05 rather than invented, so an app
 * that logs it prints the same bytes on both backends.
 */

#include "picocalc/psram.h"

#include <stdlib.h>
#include <string.h>

#include <vector>

namespace picocalc::psram {
namespace {

std::vector<uint8_t> g_memory;
Info g_info{};

bool in_range(uint32_t address, size_t bytes) {
    return address <= capacity_bytes && bytes <= capacity_bytes - address;
}

}  // namespace

bool init() {
    g_memory.assign(capacity_bytes, 0);
    g_info.initialized = true;
    g_info.system_clock_khz = 250000;
    g_info.clkdiv = 2.0f;
    g_info.spi_hz = 62500000;
    g_info.fudge = false;
    // The APS6404L identity the PicoCalc actually returned during
    // hardware correlation (hardware-validation/records/
    // bsp-0.8.8-20260804-02.json), not a placeholder.
    static const uint8_t kIdentity[8] = {0x0d, 0x5d, 0x53, 0x32,
                                         0xc6, 0x81, 0x79, 0x46};
    memcpy(g_info.id, kIdentity, sizeof(kIdentity));
    return true;
}

bool available() {
    return g_info.initialized;
}

const Info& info() {
    return g_info;
}

VerifyResult self_test() {
    VerifyResult result{};
    result.address = 0;
    result.bytes = max_transfer_chunk_bytes;
    if (!available()) {
        result.ok = false;
        result.mismatches = result.bytes;
        return result;
    }
    // The same pattern and chunk size the device driver uses, so the
    // log line reads identically on both backends.
    uint8_t pattern[max_transfer_chunk_bytes];
    for (size_t i = 0; i < sizeof(pattern); ++i) {
        pattern[i] = static_cast<uint8_t>(i * 7 + 1);
    }
    write(0, pattern, sizeof(pattern));
    uint8_t readback[max_transfer_chunk_bytes] = {};
    read(0, readback, sizeof(readback));
    for (size_t i = 0; i < sizeof(pattern); ++i) {
        if (pattern[i] != readback[i]) {
            ++result.mismatches;
        }
    }
    result.ok = result.mismatches == 0;
    return result;
}

bool read(uint32_t address, void* destination, size_t bytes) {
    if (!available() || destination == nullptr || !in_range(address, bytes)) {
        return false;
    }
    memcpy(destination, g_memory.data() + address, bytes);
    return true;
}

bool write(uint32_t address, const void* source, size_t bytes) {
    if (!available() || source == nullptr || !in_range(address, bytes)) {
        return false;
    }
    memcpy(g_memory.data() + address, source, bytes);
    return true;
}

CoexistenceResult probe_lcd_coexistence(CoexistenceDisplayStep display_step,
                                        uint32_t frames_per_candidate) {
    // On the device this walks the documented clock candidates while the
    // caller redraws, looking for one where PSRAM and the LCD do not
    // disturb each other. There is no clock and no contention here, so
    // the honest answer is that one candidate was considered and passed.
    // A test that needs the real answer has to use the firmware backend.
    CoexistenceResult result{};
    if (display_step != nullptr) {
        for (uint32_t frame = 0; frame < frames_per_candidate; ++frame) {
            if (!display_step(frame)) {
                break;
            }
        }
    }
    result.ok = available();
    result.candidates = 1;
    result.passed = result.ok ? 1 : 0;
    result.restored = true;
    return result;
}

}  // namespace picocalc::psram
