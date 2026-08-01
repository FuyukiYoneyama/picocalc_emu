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

// Initializes the copied Picocalc_ment PWM/DMA stream without starting it.
// The application fills it with PCM samples and then calls start().
bool init();
// Initializes and starts the copied Picocalc_ment fixed -6 dBFS 1 kHz tone.
// This is the standalone reference-hardware path used by the template when
// PICOCALC_AUDIO_REFERENCE_TONE is enabled.
bool init_reference_tone();
void start();
// Stops PWM/DMA output. Call this when a diagnostic tone or PCM stream is no
// longer wanted; stopping does not make the BSP unusable for a later init.
void stop();
// Finish already queued PCM and replace only the short EOF tail with
// intentional center-duty silence. Completion is reported by drain_complete().
void request_drain();
bool drain_complete();
bool write_sample(int16_t left, int16_t right);
uint32_t writable_samples();
Stats stats();

}  // namespace picocalc::audio
