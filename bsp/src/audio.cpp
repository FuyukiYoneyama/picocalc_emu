#include "picocalc/audio.h"

#include "vendor/audio_picoment/platform/picocalc_audio_pwm.h"

namespace picocalc::audio {
namespace {

bool g_initialized = false;

}  // namespace

bool init() {
    if (g_initialized) {
        return true;
    }
    // Reference baseline: this is the exact Picocalc_ment fixed-sine path.
    // It starts the PWM/DMA output immediately, so this test cannot report a
    // false-positive "initialized" state while producing silence.
    picoment::audio_pwm::init_fixed_sine();
    g_initialized = picoment::audio_pwm::stats().ring_capacity != 0u;
    return g_initialized;
}

void start() {
    // The reference fixed-sine path is started by init_fixed_sine().
    static_cast<void>(g_initialized);
}

void stop() {
    if (g_initialized) {
        picoment::audio_pwm::stop_stream();
    }
}

bool write_sample(int16_t left, int16_t right) {
    if (!g_initialized) {
        return false;
    }
    return picoment::audio_pwm::write_sample(left, right);
}

uint32_t writable_samples() {
    if (!g_initialized) {
        return 0u;
    }
    return picoment::audio_pwm::writable_samples();
}

Stats stats() {
    const auto source = picoment::audio_pwm::stats();
    return {
        source.irq_count,
        source.refill_count,
        source.sample_index,
        source.underrun_count,
        source.ring_level,
        source.ring_capacity,
        source.ring_write_drop_count,
        source.carrier_hz,
        source.dma_fraction_num,
        source.dma_fraction_den,
        source.peak_duty_delta,
        source.clip_count,
    };
}

}  // namespace picocalc::audio
