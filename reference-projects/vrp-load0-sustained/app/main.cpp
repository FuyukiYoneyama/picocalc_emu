// Copyright (c) 2026 Fuyuki Yoneyama
// SPDX-License-Identifier: MIT

#include <stdint.h>
#include <stdio.h>

#include "hardware/sync.h"
#include "pico/multicore.h"
#include "pico/platform.h"
#include "pico/stdlib.h"
#include "picocalc/bsp.h"

namespace {

constexpr uint64_t kHeartbeatPeriodUs = 10'000'000u;
constexpr uint32_t kFrameSeed = 0x4c4f4144u;
constexpr uint32_t kCpuSeed = 0x1357'9bdfu;
constexpr uint32_t kAudioSeed = 0x0048'0000u;
constexpr uint32_t kAudioPeriodSamples = 96u;
constexpr int32_t kAudioAmplitude = 12'000;

volatile bool g_core1_stop = false;
volatile bool g_core1_stopped = false;
volatile uint32_t g_core1_units = 0;
volatile uint32_t g_core1_digest = kCpuSeed;

uint32_t g_core0_units = 0;
uint32_t g_core0_digest = kCpuSeed ^ 0xa5a5'5a5au;
volatile uint32_t g_audio_phase = kAudioSeed;
volatile uint32_t g_audio_produced = 0;
uint32_t g_input_events = 0;
uint32_t g_input_digest = 0x811c'9dc5u;
uint32_t g_frame_count = 0;
uint32_t g_frame_digest = 0x811c'9dc5u;
uint32_t g_frame_lag_max_us = 0;

uint32_t mix32(uint32_t state, uint32_t value) {
    state ^= value + 0x9e37'79b9u + (state << 6) + (state >> 2);
    state ^= state >> 16;
    state *= 0x7feb'352du;
    state ^= state >> 15;
    return state;
}

uint32_t xorshift32(uint32_t value) {
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    return value;
}

void __not_in_flash_func(service_audio)();

void __not_in_flash_func(core1_load)() {
    uint32_t state = kCpuSeed ^ 0x2468'ace0u;
    while (!g_core1_stop) {
        // The BSP explicitly supports a core-1 producer racing the core-0
        // DMA IRQ. Keep the stream supplied while core 0 is occupied by the
        // full-screen transfer; this is part of the concurrent workload, not
        // an idle or event-skipping shortcut.
        service_audio();
        // This is intentionally a real instruction stream, not a delay. The
        // volatile publication makes each batch observable and prevents the
        // compiler from erasing the deterministic arithmetic workload.
        for (uint32_t i = 0; i < 256u; ++i) {
            state = xorshift32(state + i + g_core1_units);
            state = state * 1'664'525u + 1'013'904'223u;
            state ^= (state >> 7) | (state << 25);
        }
        g_core1_digest = state;
        ++g_core1_units;
    }
    g_core1_stopped = true;
    __dmb();
    // A Pico SDK core-1 entry must not return through core1_wrapper: its
    // bootstrap return address is not an application continuation. Publish
    // the stop state, then remain parked until the MCU is reset.
    while (true) {
        __wfe();
    }
}

void run_core0_load() {
    uint32_t state = g_core0_digest;
    for (uint32_t i = 0; i < 96u; ++i) {
        state = xorshift32(state + i + g_core0_units);
        state = state * 1'103'515'245u + 12'345u;
        state ^= (state >> 11) | (state << 21);
    }
    g_core0_digest = state;
    ++g_core0_units;
}

void __not_in_flash_func(service_audio)() {
    while (picocalc::audio::writable_samples() != 0u) {
        const uint32_t phase = g_audio_phase++ % kAudioPeriodSamples;
        const int32_t sample = phase < (kAudioPeriodSamples / 2u)
            ? -kAudioAmplitude + static_cast<int32_t>(phase) * 500
            : kAudioAmplitude - static_cast<int32_t>(phase - 48u) * 500;
        if (!picocalc::audio::write_sample(
                static_cast<int16_t>(sample), static_cast<int16_t>(-sample))) {
            break;
        }
        ++g_audio_produced;
    }
}

void service_input() {
    picocalc::keyboard::KeyEvent event{};
    while (picocalc::keyboard::read_event(&event)) {
        const uint32_t encoded =
            (static_cast<uint32_t>(event.key) << 8) |
            static_cast<uint32_t>(event.state);
        g_input_digest = mix32(g_input_digest, encoded);
        ++g_input_events;
    }
}

uint16_t frame_colour(uint32_t frame) {
    uint32_t state = xorshift32(kFrameSeed ^ (frame * 0x9e37'79b9u));
    const uint16_t red = static_cast<uint16_t>((state >> 19) & 0x1fu);
    const uint16_t green = static_cast<uint16_t>((state >> 10) & 0x3fu);
    const uint16_t blue = static_cast<uint16_t>((state >> 3) & 0x1fu);
    return static_cast<uint16_t>((red << 11) | (green << 5) | blue);
}

void render_frame(uint64_t deadline_us) {
    const uint16_t colour = frame_colour(g_frame_count);
    // display::clear is the public full-screen path. It performs the complete
    // 320x320 RGB565 transfer; no frame is discarded when the schedule falls
    // behind. Overdue frames are rendered on subsequent loop iterations.
    picocalc::display::clear(colour);
    g_frame_digest = mix32(g_frame_digest,
                           (static_cast<uint32_t>(colour) << 16) | g_frame_count);
    ++g_frame_count;
    const uint64_t after_us = time_us_64();
    const uint64_t lag_us = after_us > deadline_us ? after_us - deadline_us : 0u;
    if (lag_us > g_frame_lag_max_us) {
        g_frame_lag_max_us = lag_us > 0xffff'ffffu
            ? 0xffff'ffffu
            : static_cast<uint32_t>(lag_us);
    }
}

void print_heartbeat(uint64_t now_us) {
    const auto audio = picocalc::audio::stats();
    printf("[VRP-LOAD0][HEARTBEAT] virtual_us=%llu frames=%lu "
           "audio_produced=%lu audio_consumed=%lu audio_irq=%lu "
           "audio_underruns=%lu audio_write_drops=%lu core0_units=%lu "
           "core1_units=%lu input_events=%lu\n",
           static_cast<unsigned long long>(now_us),
           static_cast<unsigned long>(g_frame_count),
           static_cast<unsigned long>(g_audio_produced),
           static_cast<unsigned long>(audio.sample_index),
           static_cast<unsigned long>(audio.irq_count),
           static_cast<unsigned long>(audio.underrun_count),
           static_cast<unsigned long>(audio.ring_write_drop_count),
           static_cast<unsigned long>(g_core0_units),
           static_cast<unsigned long>(g_core1_units),
           static_cast<unsigned long>(g_input_events));
}

void print_completion(uint64_t now_us, uint64_t start_us) {
    const auto audio = picocalc::audio::stats();
    printf("[VRP-LOAD0][RESULT] duration_us=%llu elapsed_us=%llu "
           "frames=%lu frame_digest=0x%08lx frame_lag_max_us=%lu "
           "audio_produced=%lu audio_consumed=%lu audio_irq=%lu "
           "audio_underruns=%lu audio_write_drops=%lu audio_ring=%lu/%lu "
           "core0_units=%lu core0_digest=0x%08lx core1_units=%lu "
           "core1_digest=0x%08lx input_events=%lu input_digest=0x%08lx\n",
           static_cast<unsigned long long>(
               static_cast<uint64_t>(VRP_LOAD0_DURATION_SECONDS) * 1'000'000u),
           static_cast<unsigned long long>(now_us - start_us),
           static_cast<unsigned long>(g_frame_count),
           static_cast<unsigned long>(g_frame_digest),
           static_cast<unsigned long>(g_frame_lag_max_us),
           static_cast<unsigned long>(g_audio_produced),
           static_cast<unsigned long>(audio.sample_index),
           static_cast<unsigned long>(audio.irq_count),
           static_cast<unsigned long>(audio.underrun_count),
           static_cast<unsigned long>(audio.ring_write_drop_count),
           static_cast<unsigned long>(audio.ring_level),
           static_cast<unsigned long>(audio.ring_capacity),
           static_cast<unsigned long>(g_core0_units),
           static_cast<unsigned long>(g_core0_digest),
           static_cast<unsigned long>(g_core1_units),
           static_cast<unsigned long>(g_core1_digest),
           static_cast<unsigned long>(g_input_events),
           static_cast<unsigned long>(g_input_digest));
    // Keep the terminal marker after the complete result record. A scenario
    // runner may stop as soon as it observes the marker, so placing it at the
    // beginning would truncate the UART evidence after the first few fields.
    printf("[VRP-LOAD0][COMPLETE]\n");
}

}  // namespace

int main() {
    if (!picocalc::init()) {
        printf("[VRP-LOAD0][FAIL] reason=bsp_init_failed\n");
        while (true) {
            tight_loop_contents();
        }
    }

    const auto initial_audio = picocalc::audio::stats();
    if (initial_audio.ring_capacity == 0u) {
        printf("[VRP-LOAD0][FAIL] reason=audio_stream_unavailable\n");
        while (true) {
            tight_loop_contents();
        }
    }

    service_audio();
    picocalc::audio::start();
    multicore_launch_core1(core1_load);

    const uint64_t start_us = time_us_64();
    const uint64_t end_us = start_us +
        static_cast<uint64_t>(VRP_LOAD0_DURATION_SECONDS) * 1'000'000u;
    uint64_t next_frame_us = start_us;
    uint64_t next_heartbeat_us = start_us + kHeartbeatPeriodUs;

    printf("[VRP-LOAD0][START] profile=vrp-load0-r1 duration_s=%lu "
           "display=320x320_rgb565@30Hz audio=stereo_pcm@48000Hz "
           "cpu=core0+core1 input=scene-fixed-sequence "
           "frame_drop_policy=forbidden exact_idle_fast_forward=not_expected\n",
           static_cast<unsigned long>(VRP_LOAD0_DURATION_SECONDS));

    while (true) {
        service_input();
        const uint64_t now_us = time_us_64();
        if (now_us >= end_us) {
            g_core1_stop = true;
            __dmb();
            while (!g_core1_stopped) {
                run_core0_load();
                tight_loop_contents();
            }
            print_completion(time_us_64(), start_us);
            // Keep core 0 active and the audio producer supplied until the
            // scenario observes the completion marker. This avoids turning
            // the final observation window into an intentional idle interval.
            while (true) {
                service_input();
                service_audio();
                run_core0_load();
                tight_loop_contents();
            }
        }

        if (now_us >= next_frame_us) {
            const uint64_t deadline_us = next_frame_us;
            render_frame(deadline_us);
            // Use floor(n * 1,000,000 / 30) rather than accumulating a
            // rounded 33,333 us period. This schedules exactly 30 frames per
            // virtual second while retaining an integer timer boundary.
            next_frame_us = start_us +
                (static_cast<uint64_t>(g_frame_count) * 1'000'000u) / 30u;
            continue;
        }

        if (now_us >= next_heartbeat_us) {
            print_heartbeat(now_us);
            do {
                next_heartbeat_us += kHeartbeatPeriodUs;
            } while (next_heartbeat_us <= now_us);
        }

        run_core0_load();
    }
}
