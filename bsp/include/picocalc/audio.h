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

// Reference baseline: initializes and starts the Picocalc_ment fixed -6 dBFS
// 1 kHz PWM/DMA tone. This is intentionally the copied hardware test path;
// the streaming producer is added only after this path passes on hardware.
bool init();
// Reserved for the later streaming producer; the reference tone is started by
// init() exactly as in Picocalc_ment.
void start();
void stop();
bool write_sample(int16_t left, int16_t right);
uint32_t writable_samples();
Stats stats();

}  // namespace picocalc::audio
