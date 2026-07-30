#pragma once

#include <stdint.h>

namespace picocalc::audio {

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

// Initializes the proven Picocalc_ment PWM/DMA stream without starting audio.
// The output remains at the PWM midpoint until start() is called.
bool init();
void start();
void stop();
bool write_sample(int16_t left, int16_t right);
uint32_t writable_samples();
Stats stats();

}  // namespace picocalc::audio
