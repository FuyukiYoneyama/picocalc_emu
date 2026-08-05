/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * Virtual time and the two Pico SDK entry points applications use.
 *
 * `sleep_ms` advancing a counter rather than blocking is what makes a
 * host run reproducible and instant: PicoTetris polls on a 16 ms cadence
 * and would otherwise take as long to test as to play. Nothing here
 * reads a wall clock, so two runs of the same app produce the same
 * timeline.
 */

#include "picocalc/host.h"

#include "pico/stdlib.h"

namespace {
uint64_t g_now_us = 0;
}  // namespace

namespace picocalc::host {

uint64_t now_us() {
    return g_now_us;
}

void advance_us(uint64_t us) {
    g_now_us += us;
}

void reset_time() {
    g_now_us = 0;
}

}  // namespace picocalc::host

extern "C" {

void stdio_init_all(void) {
    // The host's stdout is already open. Applications call this first,
    // so it has to exist; it has nothing to do.
}

void sleep_ms(uint32_t ms) {
    picocalc::host::advance_us(static_cast<uint64_t>(ms) * 1000u);
}

void sleep_us(uint64_t us) {
    picocalc::host::advance_us(us);
}

uint64_t time_us_64(void) {
    return picocalc::host::now_us();
}

uint32_t time_us_32(void) {
    return static_cast<uint32_t>(picocalc::host::now_us());
}

}  // extern "C"
