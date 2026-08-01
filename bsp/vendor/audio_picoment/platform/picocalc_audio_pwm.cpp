/*
 * Picocalc_ment - standalone musical instrument firmware for PicoCalc.
 * Copyright (c) 2026 Fuyuki Yoneyama
 * SPDX-License-Identifier: MIT
 */

#include "platform/picocalc_audio_pwm.h"

#include <stdint.h>

#include "config/board_config.h"
#include "config/log_config.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/pwm.h"
#include "hardware/sync.h"
#include "pico/platform.h"
#include "picocalc/detail/audio_ring_spsc.h"

#if PICOMENT_FIXED_SINE_TEST
#include "diagnostics/fixed_sine_test.h"
#endif

namespace picoment::audio_pwm {
namespace {

constexpr uint32_t kHalfSamples = 128;
constexpr uint32_t kRingSamples = 512;
constexpr uint16_t kPwmCenter = (board::kAudioPwmWrap + 1u) / 2u;
constexpr uint32_t kPwmSteps = board::kAudioPwmWrap + 1u;
constexpr uint8_t kPwmResolutionBits =
    (kPwmSteps == 4096u) ? 12u : ((kPwmSteps == 1024u) ? 10u : ((kPwmSteps == 256u) ? 8u : 7u));
constexpr uint8_t kPwmQuantShift = 16u - kPwmResolutionBits;
constexpr uint8_t kErrorDiffusionPercent = 100;
using AudioRing = picocalc::detail::AudioRingSpsc<kRingSamples>;

static_assert(kPwmSteps == 128u || kPwmSteps == 256u || kPwmSteps == 1024u || kPwmSteps == 4096u,
              "PWM quantizer supports 7-bit, 8-bit, 10-bit, or 12-bit test modes");

// DMA consumes one half-buffer while the IRQ refills the other half from this
// ring. The producer in main.cpp writes decoded PRA32-U samples here; the IRQ
// never calls the synth, logs, or LCD code.
uint32_t g_dma_buffer[2][kHalfSamples];
uint32_t g_ring[kRingSamples];
volatile uint32_t g_irq_count = 0;
volatile uint32_t g_refill_count = 0;
volatile uint32_t g_sample_index = 0;
volatile uint32_t g_underrun_count = 0;
volatile uint32_t g_ring_read = 0;
volatile uint32_t g_ring_write = 0;
volatile uint32_t g_ring_write_drop_count = 0;
volatile uint32_t g_clip_count = 0;
volatile uint16_t g_peak_duty_delta = 0;
uint32_t g_carrier_hz = 0;
uint16_t g_dma_fraction_num = 0;
uint16_t g_dma_fraction_den = 0;
int g_dma_channel = -1;
int g_dma_timer = -1;
int g_pwm_slice = -1;
uint g_left_channel = PWM_CHAN_A;
uint g_right_channel = PWM_CHAN_B;
uint g_active_half = 0;
int32_t g_quant_error_left = 0;
int32_t g_quant_error_right = 0;
bool g_live = false;
volatile bool g_drain_requested = false;
volatile bool g_drain_final_pending = false;
volatile bool g_drain_stop_pending = false;
volatile bool g_drain_complete = true;
volatile uint8_t g_drain_final_half = 0;
#if PICOMENT_FIXED_SINE_TEST
bool g_stream_mode = false;
#endif
#if PICOMENT_SCREENSHOT_CAPTURE_BUILD
constexpr uint32_t kUiBusyToneHz = 880;
constexpr uint32_t kUiBusyToneMs = 70;
constexpr uint32_t kUiBusyPeriodMs = 500;
constexpr uint8_t kUiBusyAmplitude = 34;
volatile bool g_ui_busy_active = false;
volatile uint32_t g_ui_busy_pos = 0;
volatile uint32_t g_ui_tone_remaining = 0;
volatile uint32_t g_ui_tone_pos = 0;
volatile uint32_t g_ui_tone_half_period = 1;
volatile uint16_t g_ui_tone_amplitude = 0;
#endif

uint32_t gcd_u32(uint32_t a, uint32_t b) {
    while (b != 0u) {
        const uint32_t t = a % b;
        a = b;
        b = t;
    }
    return a;
}

void compute_dma_fraction(uint32_t sample_rate, uint32_t clk_hz, uint16_t* numerator, uint16_t* denominator) {
    uint32_t num = sample_rate;
    uint32_t den = clk_hz;
    const uint32_t gcd = gcd_u32(num, den);
    if (gcd != 0u) {
        num /= gcd;
        den /= gcd;
    }

    if (num <= 65535u && den <= 65535u) {
        *numerator = static_cast<uint16_t>(num);
        *denominator = static_cast<uint16_t>(den);
        return;
    }

    uint32_t best_num = 1u;
    uint32_t best_den = 1u;
    uint64_t best_err_num = UINT64_MAX;
    uint64_t best_err_den = 1u;

    for (uint32_t cand_den = 1u; cand_den <= 65535u; ++cand_den) {
        const uint64_t scaled = static_cast<uint64_t>(sample_rate) * cand_den;
        uint32_t cand_num = static_cast<uint32_t>((scaled + (clk_hz / 2u)) / clk_hz);
        if (cand_num == 0u) {
            cand_num = 1u;
        }
        if (cand_num > cand_den || cand_num > 65535u) {
            continue;
        }

        const uint64_t actual = static_cast<uint64_t>(clk_hz) * cand_num;
        const uint64_t target = static_cast<uint64_t>(sample_rate) * cand_den;
        const uint64_t err = (actual > target) ? (actual - target) : (target - actual);

        if (best_err_num == UINT64_MAX ||
            err * best_err_den < best_err_num * cand_den ||
            (err * best_err_den == best_err_num * cand_den && cand_den > best_den)) {
            best_num = cand_num;
            best_den = cand_den;
            best_err_num = err;
            best_err_den = cand_den;
        }
    }

    *numerator = static_cast<uint16_t>(best_num);
    *denominator = static_cast<uint16_t>(best_den);
}

uint32_t __not_in_flash_func(pack_pwm)(uint16_t left, uint16_t right) {
    uint32_t packed = 0;
    if (g_left_channel == PWM_CHAN_A) {
        packed |= left;
    } else {
        packed |= static_cast<uint32_t>(left) << 16;
    }
    if (g_right_channel == PWM_CHAN_A) {
        packed |= right;
    } else {
        packed |= static_cast<uint32_t>(right) << 16;
    }
    return packed;
}

uint16_t __not_in_flash_func(quantize_pwm)(int16_t sample, int32_t* quant_error) {
    // Keep PRA32-U's 16-bit output as long as possible, then shape the PWM
    // quantization error into the next sample. Plain truncation is kept only
    // for diagnostics because it was audibly worse on the PicoCalc speaker.
    const int32_t target = static_cast<int32_t>(sample) + 32768;
    int32_t shaped = target + ((*quant_error * kErrorDiffusionPercent) / 100);
    // Error diffusion may move a representable int16 sample just outside the
    // PWM input range. Clamp the shaped value before quantization; that is
    // quantizer state correction, not source-audio clipping.
    if (shaped < 0) shaped = 0;
    if (shaped > 65535) shaped = 65535;
    int32_t duty = (shaped + (1 << (kPwmQuantShift - 1u))) >> kPwmQuantShift;

    if (duty < 0) {
        duty = 0;
    } else if (duty > board::kAudioPwmWrap) {
        duty = board::kAudioPwmWrap;
    }

    const int32_t reconstructed =
        static_cast<int32_t>((static_cast<uint32_t>(duty) * 65535u + (board::kAudioPwmWrap / 2u)) /
                             board::kAudioPwmWrap);
    *quant_error = shaped - reconstructed;

    const int32_t delta = (duty > kPwmCenter) ? (duty - kPwmCenter) : (kPwmCenter - duty);
    if (delta > g_peak_duty_delta) {
        g_peak_duty_delta = static_cast<uint16_t>(delta);
    }

    return static_cast<uint16_t>(duty);
}

bool __not_in_flash_func(ring_pop)(uint32_t* sample) {
    const uint32_t read = g_ring_read;
    const uint32_t write = g_ring_write;
    if (AudioRing::empty(write, read)) {
        return false;
    }
    *sample = g_ring[AudioRing::slot(read)];
    __dmb();
    g_ring_read = read + 1u;
    return true;
}

#if PICOMENT_SCREENSHOT_CAPTURE_BUILD
uint16_t __not_in_flash_func(ui_amplitude_to_duty)(uint8_t amplitude) {
    return static_cast<uint16_t>(
        (static_cast<uint32_t>(amplitude) * board::kAudioPwmWrap + 127u) / 255u);
}

uint32_t __not_in_flash_func(ui_square_sample)(uint32_t pos,
                                               uint32_t half_period,
                                               uint16_t amplitude) {
    const uint16_t duty =
        (((pos / half_period) & 1u) != 0u)
            ? static_cast<uint16_t>(kPwmCenter - amplitude)
            : static_cast<uint16_t>(kPwmCenter + amplitude);
    return pack_pwm(duty, duty);
}

uint32_t __not_in_flash_func(ui_busy_sample)() {
    uint32_t period_samples = (board::kTargetSampleRate * kUiBusyPeriodMs) / 1000u;
    uint32_t tone_samples = (board::kTargetSampleRate * kUiBusyToneMs) / 1000u;
    uint32_t half_period = board::kTargetSampleRate / (kUiBusyToneHz * 2u);
    const uint32_t pos = g_ui_busy_pos++;

    if (period_samples == 0u) {
        period_samples = 1u;
    }
    if (tone_samples == 0u) {
        tone_samples = 1u;
    }
    if (half_period == 0u) {
        half_period = 1u;
    }
    if ((pos % period_samples) >= tone_samples) {
        return pack_pwm(kPwmCenter, kPwmCenter);
    }
    return ui_square_sample(pos, half_period, ui_amplitude_to_duty(kUiBusyAmplitude));
}
#endif

void __not_in_flash_func(refill_half)(uint half) {
    // IRQ-side refill is intentionally limited to copying pre-rendered samples
    // and substituting center duty on underrun. All expensive generation stays
    // in the foreground audio service.
    for (uint32_t i = 0; i < kHalfSamples; ++i) {
#if PICOMENT_SCREENSHOT_CAPTURE_BUILD
        if (g_ui_busy_active) {
            g_dma_buffer[half][i] = ui_busy_sample();
            ++g_sample_index;
            continue;
        }
        if (g_ui_tone_remaining > 0u) {
            g_dma_buffer[half][i] =
                ui_square_sample(g_ui_tone_pos++, g_ui_tone_half_period, g_ui_tone_amplitude);
            --g_ui_tone_remaining;
            ++g_sample_index;
            continue;
        }
#endif
#if PICOMENT_FIXED_SINE_TEST
        if (g_stream_mode) {
#endif
            uint32_t packed = pack_pwm(kPwmCenter, kPwmCenter);
            if (!ring_pop(&packed)) {
                if (g_live) {
                    ++g_underrun_count;
                }
            }
            g_dma_buffer[half][i] = packed;
            ++g_sample_index;
#if PICOMENT_FIXED_SINE_TEST
        } else {
            const uint32_t index = g_sample_index++;
            const int16_t sample = picoment::diagnostics::fixed_sine::sample_at(index);
            const uint16_t duty = quantize_pwm(sample, &g_quant_error_left);
            g_dma_buffer[half][i] = pack_pwm(duty, duty);
        }
#endif
    }
    ++g_refill_count;
}

uint32_t __not_in_flash_func(refill_drain_half)(uint half) {
    // EOF is a normal end condition, not an audio underrun.  Complete the
    // final DMA half with queued samples and intentional center-duty silence
    // for any short tail, without incrementing the underrun counter.
    uint32_t copied = 0;
    for (uint32_t i = 0; i < kHalfSamples; ++i) {
        uint32_t packed = pack_pwm(kPwmCenter, kPwmCenter);
        if (ring_pop(&packed)) {
            ++copied;
        }
        g_dma_buffer[half][i] = packed;
        ++g_sample_index;
    }
    ++g_refill_count;
    return copied;
}

void __not_in_flash_func(start_half)(uint half) {
    dma_channel_set_read_addr(static_cast<uint>(g_dma_channel), g_dma_buffer[half], false);
    dma_channel_set_transfer_count(static_cast<uint>(g_dma_channel), kHalfSamples, false);
    dma_start_channel_mask(1u << static_cast<uint>(g_dma_channel));
    g_active_half = half;
}

void __isr __not_in_flash_func(dma_irq0_handler)() {
    if (dma_channel_get_irq0_status(static_cast<uint>(g_dma_channel))) {
        dma_channel_acknowledge_irq0(static_cast<uint>(g_dma_channel));
    }
    if (!g_live) {
        return;
    }

    const uint next_half = g_active_half ^ 1u;
    if (g_drain_requested) {
        if (g_drain_stop_pending) {
            g_drain_requested = false;
            g_drain_complete = true;
            g_live = false;
            __dmb();
            dma_channel_set_irq0_enabled(static_cast<uint>(g_dma_channel), false);
            irq_set_enabled(DMA_IRQ_0, false);
            pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_left_channel, kPwmCenter);
            pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_right_channel, kPwmCenter);
            return;
        }
        if (g_drain_final_pending) {
            // The opposite DMA half has just completed. Start the half that
            // was filled with the final queued PCM, then stop on its IRQ.
            start_half(g_drain_final_half);
            g_drain_final_pending = false;
            g_drain_stop_pending = true;
            ++g_irq_count;
            return;
        }
        const uint32_t copied = refill_drain_half(g_active_half);
        if (AudioRing::empty(g_ring_write, g_ring_read)) {
            if (copied == 0u) {
                // No final PCM was needed in the completed half. The other
                // half already contains the last real samples.
                g_drain_stop_pending = true;
            } else {
                // Keep the just-filled half alive until the already-running
                // opposite half completes, then start it for one final DMA
                // interval before stopping.
                g_drain_final_half = static_cast<uint8_t>(g_active_half);
                g_drain_final_pending = true;
            }
        }
        start_half(next_half);
        ++g_irq_count;
        return;
    }
    refill_half(g_active_half);
    start_half(next_half);
    ++g_irq_count;
}

}  // namespace

void start_output() {
    if (g_live) {
        return;
    }

    dma_channel_acknowledge_irq0(static_cast<uint>(g_dma_channel));
    irq_clear(DMA_IRQ_0);
    g_live = true;
    irq_set_enabled(DMA_IRQ_0, true);

    pwm_set_enabled(static_cast<uint>(g_pwm_slice), true);
    start_half(0);
}

void init_common(bool stream_mode, bool start_immediately) {
    gpio_set_function(board::kAudioPwmLeft, GPIO_FUNC_PWM);
    gpio_set_function(board::kAudioPwmRight, GPIO_FUNC_PWM);

    g_pwm_slice = static_cast<int>(pwm_gpio_to_slice_num(board::kAudioPwmLeft));
    g_left_channel = pwm_gpio_to_channel(board::kAudioPwmLeft);
    g_right_channel = pwm_gpio_to_channel(board::kAudioPwmRight);
    if (pwm_gpio_to_slice_num(board::kAudioPwmRight) != static_cast<uint>(g_pwm_slice)) {
        PM_LOG_BOOT("audio=pwm error=pin_pair_mismatch left=%u right=%u",
                    board::kAudioPwmLeft,
                    board::kAudioPwmRight);
        return;
    }

    pwm_config config = pwm_get_default_config();
    pwm_config_set_clkdiv(&config, 1.0f);
    pwm_config_set_wrap(&config, board::kAudioPwmWrap);
    pwm_init(static_cast<uint>(g_pwm_slice), &config, false);
    pwm_set_counter(static_cast<uint>(g_pwm_slice), 0);
    pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_left_channel, kPwmCenter);
    pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_right_channel, kPwmCenter);

    g_irq_count = 0;
    g_refill_count = 0;
    g_sample_index = 0;
    g_underrun_count = 0;
    g_ring_read = 0;
    g_ring_write = 0;
    g_ring_write_drop_count = 0;
    g_clip_count = 0;
    g_peak_duty_delta = 0;
    g_quant_error_left = 0;
    g_quant_error_right = 0;
    g_drain_requested = false;
    g_drain_final_pending = false;
    g_drain_stop_pending = false;
    g_drain_complete = true;
    g_drain_final_half = 0;
#if PICOMENT_FIXED_SINE_TEST
    g_stream_mode = stream_mode;
#else
    static_cast<void>(stream_mode);
#endif

    g_dma_channel = dma_claim_unused_channel(true);
    g_dma_timer = dma_claim_unused_timer(true);
    compute_dma_fraction(board::kTargetSampleRate,
                         clock_get_hz(clk_sys),
                         &g_dma_fraction_num,
                         &g_dma_fraction_den);
    dma_timer_set_fraction(static_cast<uint>(g_dma_timer), g_dma_fraction_num, g_dma_fraction_den);

    dma_channel_config dma_config = dma_channel_get_default_config(static_cast<uint>(g_dma_channel));
    channel_config_set_transfer_data_size(&dma_config, DMA_SIZE_32);
    channel_config_set_read_increment(&dma_config, true);
    channel_config_set_write_increment(&dma_config, false);
    channel_config_set_dreq(&dma_config, dma_get_timer_dreq(static_cast<uint>(g_dma_timer)));
    dma_channel_configure(static_cast<uint>(g_dma_channel),
                          &dma_config,
                          &pwm_hw->slice[g_pwm_slice].cc,
                          g_dma_buffer[0],
                          kHalfSamples,
                          false);

    refill_half(0);
    refill_half(1);

    dma_channel_acknowledge_irq0(static_cast<uint>(g_dma_channel));
    irq_clear(DMA_IRQ_0);
    dma_channel_set_irq0_enabled(static_cast<uint>(g_dma_channel), true);
    irq_set_exclusive_handler(DMA_IRQ_0, dma_irq0_handler);
    g_live = false;
    irq_set_enabled(DMA_IRQ_0, false);

    g_carrier_hz = clock_get_hz(clk_sys) / (board::kAudioPwmWrap + 1u);
    if (start_immediately) {
        start_output();
    }
}

#if PICOMENT_FIXED_SINE_TEST
void init_fixed_sine() {
    init_common(false, true);
    PM_LOG_BOOT("audio=fixed_sine rate=%lu tone=%lu amp_db=-6 pwm_wrap=%u carrier=%lu dma_half=%lu dma_timer=%d dma_frac=%u/%u quant=error_diffusion_%upct_%ubit",
                static_cast<unsigned long>(board::kTargetSampleRate),
                static_cast<unsigned long>(picoment::diagnostics::fixed_sine::kToneHz),
                board::kAudioPwmWrap,
                static_cast<unsigned long>(g_carrier_hz),
                static_cast<unsigned long>(kHalfSamples),
                g_dma_timer,
                g_dma_fraction_num,
                g_dma_fraction_den,
                kErrorDiffusionPercent,
                kPwmResolutionBits);
}
#endif

void init_stream() {
    init_common(true, false);
    PM_LOG_BOOT("audio=stream rate=%lu pwm_wrap=%u carrier=%lu dma_half=%lu ring=%lu dma_timer=%d dma_frac=%u/%u quant=error_diffusion_%upct_%ubit",
                static_cast<unsigned long>(board::kTargetSampleRate),
                board::kAudioPwmWrap,
                static_cast<unsigned long>(g_carrier_hz),
                static_cast<unsigned long>(kHalfSamples),
                static_cast<unsigned long>(kRingSamples),
                g_dma_timer,
                g_dma_fraction_num,
                g_dma_fraction_den,
                kErrorDiffusionPercent,
                kPwmResolutionBits);
}

void start_stream() {
    g_drain_requested = false;
    g_drain_final_pending = false;
    g_drain_stop_pending = false;
    g_drain_complete = false;
    g_drain_final_half = 0;
    refill_half(0);
    refill_half(1);
    start_output();
}

void stop_stream() {
    if (!g_live) {
        g_drain_requested = false;
        g_drain_final_pending = false;
        g_drain_stop_pending = false;
        g_drain_complete = true;
        if (g_pwm_slice >= 0) {
            pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_left_channel, kPwmCenter);
            pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_right_channel, kPwmCenter);
        }
        return;
    }

    irq_set_enabled(DMA_IRQ_0, false);
    g_live = false;
    g_drain_requested = false;
    g_drain_final_pending = false;
    g_drain_stop_pending = false;
    g_drain_complete = true;
    g_drain_final_half = 0;
    __dmb();

    dma_channel_abort(static_cast<uint>(g_dma_channel));
    dma_channel_acknowledge_irq0(static_cast<uint>(g_dma_channel));
    irq_clear(DMA_IRQ_0);
    irq_set_enabled(DMA_IRQ_0, false);
    pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_left_channel, kPwmCenter);
    pwm_set_chan_level(static_cast<uint>(g_pwm_slice), g_right_channel, kPwmCenter);
    g_ring_read = 0;
    g_ring_write = 0;
    PM_LOG_BOOT("audio=stream stop");
}

void request_drain() {
    if (!g_live) {
        g_drain_complete = true;
        return;
    }
    g_drain_stop_pending = false;
    g_drain_final_pending = false;
    g_drain_complete = false;
    g_drain_final_half = 0;
    __dmb();
    g_drain_requested = true;
}

bool drain_complete() {
    return g_drain_complete || !g_live;
}

bool __not_in_flash_func(write_sample)(int16_t left, int16_t right) {
    // The producer owns g_ring_write and the DMA IRQ owns g_ring_read. The
    // release barrier publishes the sample before the consumer can observe the
    // new write cursor; no interrupt masking can protect a producer on core1
    // from a DMA IRQ on core0.
    const uint32_t write = g_ring_write;
    const uint32_t read = g_ring_read;
    if (AudioRing::full(write, read)) {
        ++g_ring_write_drop_count;
        return false;
    }

    const uint16_t left_duty = quantize_pwm(left, &g_quant_error_left);
    const uint16_t right_duty = quantize_pwm(right, &g_quant_error_right);
    g_ring[AudioRing::slot(write)] = pack_pwm(left_duty, right_duty);
    __dmb();
    g_ring_write = write + 1u;
    return true;
}

uint32_t __not_in_flash_func(writable_samples)() {
    return kRingSamples - AudioRing::level(g_ring_write, g_ring_read);
}

Stats stats() {
    Stats out{};
    out.irq_count = g_irq_count;
    out.refill_count = g_refill_count;
    out.sample_index = g_sample_index;
    out.underrun_count = g_underrun_count;
    out.ring_level = AudioRing::level(g_ring_write, g_ring_read);
    out.ring_capacity = kRingSamples;
    out.ring_write_drop_count = g_ring_write_drop_count;
    out.carrier_hz = g_carrier_hz;
    out.dma_fraction_num = g_dma_fraction_num;
    out.dma_fraction_den = g_dma_fraction_den;
    out.peak_duty_delta = g_peak_duty_delta;
    out.clip_count = g_clip_count;
    return out;
}

#if PICOMENT_SCREENSHOT_CAPTURE_BUILD
void start_ui_busy_indicator() {
    g_ui_busy_pos = 0;
    g_ui_busy_active = true;
}

void stop_ui_busy_indicator() {
    g_ui_busy_active = false;
}

void play_ui_tone(uint32_t frequency_hz, uint32_t duration_ms, uint8_t amplitude) {
    if (frequency_hz == 0u || duration_ms == 0u) {
        return;
    }
    uint32_t half_period = board::kTargetSampleRate / (frequency_hz * 2u);
    if (half_period == 0u) {
        half_period = 1u;
    }
    g_ui_tone_half_period = half_period;
    g_ui_tone_amplitude = ui_amplitude_to_duty(amplitude);
    g_ui_tone_pos = 0;
    g_ui_tone_remaining = (board::kTargetSampleRate * duration_ms) / 1000u;
}
#endif

}  // namespace picoment::audio_pwm
