#include "pico/stdlib.h"
#include "picocalc/audio.h"

void copy_audio_stream_example() {
    static uint32_t phase = 0;
    while (picocalc::audio::writable_samples() != 0u) {
        // Replace this PCM producer with the application's own samples.
        const int16_t sample = ((phase / 24u) & 1u) ? 10000 : -10000;
        if (!picocalc::audio::write_sample(sample, sample)) {
            break;
        }
        ++phase;
    }
}

// Setup once: picocalc::audio::init(); copy_audio_stream_example();
// Start once after the first fill: picocalc::audio::start();
// Call copy_audio_stream_example() from the main loop to keep the ring filled.
