/*
 * Canonical PicoCalc BSP — host build.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 *
 * The keyboard controller as a bounded queue.
 *
 * No I2C. `read_event` takes the next event straight off the queue, so a
 * test cannot see a bus failure here and `read_diagnostic` reports the
 * transaction results a healthy controller would have produced.
 *
 * The 31-event bound is not host bookkeeping. ClockworkPi's official
 * `PicoCalc/Code/picocalc_keyboard` firmware defines `FIFO_SIZE 31` and
 * `KEY_COUNT_MASK 0x1F`; the BSP driver reads the same field as
 * `key_info[0] & 0x1f`. The firmware backend hit an impossible backlog of
 * 224 before the bound was modelled, and the driver went permanently blind.
 * This host queue implements the official firmware's default overflow policy:
 * with `CFG_OVERFLOW_ON` clear, discard the arriving event.
 */

#include "picocalc/keyboard.h"

#include <string.h>

#include <deque>

#include "picocalc/host.h"

namespace picocalc::keyboard::detail {
// Named so the host-side queueing below can reach the same queue.
std::deque<KeyEvent> g_fifo;
uint64_t g_dropped = 0;
}  // namespace picocalc::keyboard::detail

namespace picocalc::keyboard {
namespace {

using detail::g_dropped;
using detail::g_fifo;

uint32_t g_read_count = 0;
uint32_t g_error_count = 0;
uint32_t g_empty_count = 0;

}  // namespace

void init() {
    g_fifo.clear();
    g_read_count = 0;
    g_error_count = 0;
    g_empty_count = 0;
    g_dropped = 0;
}

bool read_event(KeyEvent* event) {
    if (event == nullptr) {
        return false;
    }
    if (g_fifo.empty()) {
        ++g_empty_count;
        return false;
    }
    *event = g_fifo.front();
    g_fifo.pop_front();
    ++g_read_count;
    // The device driver ends with `return event->key != 0`, so a zero
    // key code reads as "nothing there" even after a successful
    // transaction. Same answer here, or an app would branch differently
    // between backends.
    return event->key != 0;
}

bool read_diagnostic(DiagnosticSample* sample) {
    if (sample == nullptr) {
        return false;
    }
    *sample = {};
    // What a healthy controller's two transactions would have returned:
    // one byte written, two read.
    sample->status_write_result = 1;
    sample->status_read_result = 2;
    // Byte 0 carries the depth in its low five bits, as hardware does.
    sample->status[0] = static_cast<uint8_t>(g_fifo.size() & 0x1f);
    sample->status[1] = 0;
    if ((sample->status[0] & 0x1f) == 0) {
        return true;
    }
    sample->fifo_read_attempted = true;
    sample->fifo_write_result = 1;
    sample->fifo_read_result = 2;
    sample->fifo[0] = static_cast<uint8_t>(g_fifo.front().state);
    sample->fifo[1] = g_fifo.front().key;
    return true;
}

uint32_t read_count() {
    return g_read_count;
}

uint32_t error_count() {
    return g_error_count;
}

uint32_t empty_count() {
    return g_empty_count;
}

}  // namespace picocalc::keyboard

namespace picocalc::host {
namespace {

void push(picocalc::keyboard::KeyEvent event) {
    if (picocalc::keyboard::detail::g_fifo.size() >= max_queued_events) {
        ++picocalc::keyboard::detail::g_dropped;
        return;
    }
    picocalc::keyboard::detail::g_fifo.push_back(event);
}

}  // namespace

void queue_key(uint8_t code) {
    push({picocalc::keyboard::KeyState::Pressed, code});
    push({picocalc::keyboard::KeyState::Released, code});
}

void queue_keys(const char* text) {
    if (text == nullptr) {
        return;
    }
    for (const char* p = text; *p != '\0'; ++p) {
        queue_key(static_cast<uint8_t>(*p));
    }
}

size_t keys_queued() {
    return picocalc::keyboard::detail::g_fifo.size();
}

uint64_t keys_dropped() {
    return picocalc::keyboard::detail::g_dropped;
}

}  // namespace picocalc::host
