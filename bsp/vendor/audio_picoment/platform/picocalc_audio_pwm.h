/*
 * Picocalc_ment - standalone musical instrument firmware for PicoCalc.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <stdint.h>

#include "config/build_config.h"

namespace picoment::audio_pwm {

struct Stats {
    uint32_t irq_count;
    uint32_t refill_count;
    uint32_t sample_index;
    uint32_t underrun_count;
    uint32_t ring_level;
    uint32_t ring_capacity;
    uint32_t ring_write_drop_count;
    uint32_t carrier_hz;
    uint16_t dma_fraction_num;
    uint16_t dma_fraction_den;
    uint16_t peak_duty_delta;
    uint32_t clip_count;
};

#if PICOMENT_FIXED_SINE_TEST
// Diagnostic mode kept as the audio baseline. It bypasses PRA32-U and emits
// a fixed -6 dBFS 1 kHz sine through the PicoCalc PWM path for regression
// checks and PWM output comparisons. This function is compiled only when
// PICOMENT_FIXED_SINE_TEST is enabled.
void init_fixed_sine();
#endif

void init_stream();
void start_stream();
void stop_stream();
bool write_sample(int16_t left, int16_t right);
uint32_t writable_samples();
Stats stats();

#if PICOMENT_SCREENSHOT_CAPTURE_BUILD
void start_ui_busy_indicator();
void stop_ui_busy_indicator();
void play_ui_tone(uint32_t frequency_hz, uint32_t duration_ms, uint8_t amplitude);
#endif

}  // namespace picoment::audio_pwm
