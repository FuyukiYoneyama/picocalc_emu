/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * Audio as a sample counter.
 *
 * There is no output device and no DMA. What a host test can ask is
 * whether the application produced the samples it meant to and whether
 * it kept the ring fed; both are answered from bookkeeping. What it
 * cannot ask is whether anything was audible, or whether the PWM
 * carrier and DMA pacing were right — those live in the hardware and
 * belong to the firmware backend.
 *
 * `underrun_count` therefore stays zero here. That is not a claim that
 * the app never underruns on the device: it is the absence of a claim,
 * because nothing on the host consumes samples on a schedule. A test
 * that treats zero underruns from this backend as evidence is reading
 * something that was never measured.
 */

#include "picocalc/audio.h"

#include <string.h>

#include "picocalc/host.h"

namespace picocalc::audio::detail {
// Named so the host-side observers below can read the same counters.
bool g_running = false;
uint64_t g_samples_written = 0;
}  // namespace picocalc::audio::detail

namespace picocalc::audio {
namespace {

constexpr uint32_t kRingCapacity = 512;

using detail::g_running;
using detail::g_samples_written;

bool g_initialized = false;
bool g_drain_requested = false;
uint32_t g_ring_level = 0;

}  // namespace

bool init() {
    g_initialized = true;
    g_running = false;
    g_drain_requested = false;
    g_samples_written = 0;
    g_ring_level = 0;
    return true;
}

bool init_reference_tone() {
    if (!init()) {
        return false;
    }
    g_running = true;
    return true;
}

void start() {
    if (g_initialized) {
        g_running = true;
    }
}

void stop() {
    g_running = false;
    g_ring_level = 0;
}

void request_drain() {
    g_drain_requested = true;
    g_ring_level = 0;
}

bool drain_complete() {
    // Nothing consumes on a schedule, so a requested drain is finished
    // as soon as it is asked for.
    return g_drain_requested;
}

bool write_sample(int16_t left, int16_t right) {
    (void)left;
    (void)right;
    if (!g_initialized) {
        return false;
    }
    if (g_ring_level >= kRingCapacity) {
        // Report the ring as full rather than accepting without bound,
        // so an app's back-pressure path is exercised here too.
        return false;
    }
    ++g_ring_level;
    ++g_samples_written;
    return true;
}

uint32_t writable_samples() {
    return g_initialized ? kRingCapacity - g_ring_level : 0;
}

Stats stats() {
    Stats s{};
    s.sample_index = static_cast<uint32_t>(g_samples_written);
    s.ring_level = g_ring_level;
    s.ring_capacity = kRingCapacity;
    s.carrier_hz = 976562;
    s.dma_fraction_num = 3;
    s.dma_fraction_den = 15625;
    return s;
}

}  // namespace picocalc::audio

namespace picocalc::host {

uint64_t audio_samples_written() {
    return picocalc::audio::detail::g_samples_written;
}

bool audio_running() {
    return picocalc::audio::detail::g_running;
}

}  // namespace picocalc::host
