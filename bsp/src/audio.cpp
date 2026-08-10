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
    g_initialized = picoment::audio_pwm::init_stream();
    return g_initialized;
}

bool init_reference_tone() {
    if (g_initialized) {
        return true;
    }
    // This is the exact fixed-sine path copied from Picocalc_ment. It starts
    // output immediately and is kept separate from the generic stream API.
    g_initialized = picoment::audio_pwm::init_fixed_sine();
    return g_initialized;
}

void start() {
    if (g_initialized) {
        picoment::audio_pwm::start_stream();
    }
}

void stop() {
    if (g_initialized) {
        picoment::audio_pwm::stop_stream();
    }
}

void request_drain() {
    if (g_initialized) {
        picoment::audio_pwm::request_drain();
    }
}

bool drain_complete() {
    return !g_initialized || picoment::audio_pwm::drain_complete();
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
