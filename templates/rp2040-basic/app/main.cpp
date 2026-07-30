#include <stdio.h>

#include "pico/stdlib.h"
#include "picocalc/bsp.h"

namespace {

#if !PICOCALC_AUDIO_REFERENCE_TONE
uint32_t g_stream_phase = 0;

void service_audio_stream() {
    // Minimal copyable PCM producer: a centered square wave keeps the generic
    // stream path observable without pulling a synthesizer into the BSP.
    while (picocalc::audio::writable_samples() != 0u) {
        const int16_t sample = ((g_stream_phase / 24u) & 1u) != 0u ? 10000 : -10000;
        if (!picocalc::audio::write_sample(sample, sample)) {
            break;
        }
        ++g_stream_phase;
    }
}
#endif

void sd_log(const char* component, const char* status, uint32_t detail) {
    printf("[PICOCALC][SD] component=%s status=%s detail=%lu\n",
           component,
           status,
           static_cast<unsigned long>(detail));
}

const char* key_state_name(picocalc::keyboard::KeyState state) {
    switch (state) {
        case picocalc::keyboard::KeyState::Idle: return "idle";
        case picocalc::keyboard::KeyState::Pressed: return "pressed";
        case picocalc::keyboard::KeyState::Hold: return "hold";
        case picocalc::keyboard::KeyState::Released: return "released";
    }
    return "unknown";
}

void show_storage_result(bool lcd_ok,
                         const picocalc::filesystem::SmokeResult& result) {
    const bool sd_ok = result.ok();
    const bool ok = lcd_ok && sd_ok;
    picocalc::display::fill_rect(16, 184, 288, 48, ok ? 0x07e0 : 0xf800);
    printf("[PICOCALC][SMOKE] lcd=%s sd=%s stage=%s detail=%lu status_region=%s\n",
           lcd_ok ? "ok" : "fail",
           sd_ok ? "ok" : "fail",
           picocalc::filesystem::stage_name(result.stage),
           static_cast<unsigned long>(result.detail),
           ok ? "green" : "red");
}

}  // namespace

int main() {
    picocalc::sdcard::set_log_callback(sd_log);
    if (!picocalc::init()) {
        printf("[PICOCALC][APP] status=halt reason=bsp_init_failed\n");
        while (true) {
            sleep_ms(1000);
        }
    }
    printf("[PICOCALC][APP] version=%s compile=%s %s\n",
           PICOCALC_APP_VERSION, __DATE__, __TIME__);

#if !PICOCALC_AUDIO_REFERENCE_TONE
    service_audio_stream();
    picocalc::audio::start();
    printf("[PICOCALC][AUDIO] stream status=started waveform=square amplitude=10000\n");
#endif

    const auto psram_info = picocalc::psram::info();
    printf("[PICOCALC][VERIFY] psram=%s sysclk_khz=%lu clkdiv=%.2f spi_hz=%lu\n",
           picocalc::psram::available() ? "ok" : "unavailable",
           static_cast<unsigned long>(psram_info.system_clock_khz),
           static_cast<double>(psram_info.clkdiv),
           static_cast<unsigned long>(psram_info.spi_hz));
    sleep_ms(250);
    const auto audio_stats = picocalc::audio::stats();
    printf("[PICOCALC][AUDIO][VERIFY] mode=%s status=%s "
           "rate=48000 carrier_hz=%lu irq=%lu "
           "refill=%lu sample_index=%lu underruns=%lu pwm_wrap=255 "
           "dma_half=128 ring=%lu\n",
#if PICOCALC_AUDIO_REFERENCE_TONE
           "reference-fixed-sine",
#else
           "stream",
#endif
           audio_stats.ring_capacity != 0u ? "ok" : "unavailable",
           static_cast<unsigned long>(audio_stats.carrier_hz),
           static_cast<unsigned long>(audio_stats.irq_count),
           static_cast<unsigned long>(audio_stats.refill_count),
           static_cast<unsigned long>(audio_stats.sample_index),
           static_cast<unsigned long>(audio_stats.underrun_count),
           static_cast<unsigned long>(audio_stats.ring_capacity));

    printf("[PICOCALC][VERIFY] stage=begin components=lcd,sd,keyboard\n");

    const uint16_t solid_colors[] = {0x0000, 0xffff, 0xf800, 0x07e0, 0x001f};
    bool lcd_verify_ok = true;
    printf("[PICOCALC][LCD][VERIFY] stage=solid_fill_begin samples=8,8:2x2 "
           "colors=0x0000,0xffff,0xf800,0x07e0,0x001f\n");
    for (const uint16_t color : solid_colors) {
        picocalc::display::clear(color);
        const uint16_t expected[4] = {color, color, color, color};
        const auto result = picocalc::display::verify_pixels(
            8, 8, 2, 2, expected, 4);
        lcd_verify_ok = lcd_verify_ok && result.ok();
        printf("[PICOCALC][LCD][VERIFY] stage=solid_fill color=0x%04x status=%s "
               "pixels=%lu mismatches=%lu\n",
               color,
               result.ok() ? "pass" : "fail",
               static_cast<unsigned long>(result.pixels),
               static_cast<unsigned long>(result.mismatches));
    }

    printf("[PICOCALC][LCD][VERIFY] stage=pattern_begin pattern=known_regions "
           "width=320 height=320\n");
    picocalc::display::draw_test_pattern();
    printf("[PICOCALC][LCD][VERIFY] stage=end status=drawn "
           "regions=top(0,0,320,24),bottom(0,296,320,24),white(16,48,288,224),"
           "inset(20,52,280,216),red(32,72,80,80),green(120,72,80,80),"
           "blue(208,72,80,80) colors=top:0x07e0,bottom:0x001f,white:0xffff,"
           "inset:0x0000,red:0xf800,green:0x07e0,blue:0x001f\n");

    const uint16_t verify_pattern[] = {0xf800, 0x07e0, 0x001f, 0xffff};
    picocalc::display::set_window(32, 72, 2, 2);
    picocalc::display::write_pixels(verify_pattern, 4);
    const auto pattern_result = picocalc::display::verify_pixels(
        32, 72, 2, 2, verify_pattern, 4);
    lcd_verify_ok = lcd_verify_ok && pattern_result.ok();
    printf("[PICOCALC][LCD][VERIFY] stage=pattern_readback status=%s pixels=%lu "
           "mismatches=%lu\n",
           pattern_result.ok() ? "pass" : "fail",
           static_cast<unsigned long>(pattern_result.pixels),
           static_cast<unsigned long>(pattern_result.mismatches));
    printf("[PICOCALC][LCD][VERIFY] app_status=%s\n",
           lcd_verify_ok ? "pass" : "fail");

    constexpr const char* kSmokePath = "0:/PICOTEST.TXT";
    printf("[PICOCALC][SD][SMOKE] stage=begin path=%s "
           "sequence=mount,write,sync,close_write,read,compare,close_read,remove\n",
           kSmokePath);
    const auto storage = picocalc::filesystem::smoke_test();
    printf("[PICOCALC][SD][SMOKE] stage=end status=%s result_stage=%s detail=%lu\n",
           storage.ok() ? "ok" : "fail",
           picocalc::filesystem::stage_name(storage.stage),
           static_cast<unsigned long>(storage.detail));
    show_storage_result(lcd_verify_ok, storage);

    printf("[PICOCALC][KEY][VERIFY] stage=waiting requirement=multiple_press_release_events\n");
    printf("[PICOCALC][VERIFY] stage=ready lcd=%s sd=%s keyboard=waiting\n",
           lcd_verify_ok ? "ok" : "fail",
           storage.ok() ? "ok" : "fail");
    printf("[PICOCALC][READY] keyboard=waiting\n");
    uint32_t key_events = 0;
    uint32_t pressed_events = 0;
    uint32_t released_events = 0;
    while (true) {
        picocalc::keyboard::KeyEvent event{};
        if (picocalc::keyboard::read_event(&event)) {
            ++key_events;
            if (event.state == picocalc::keyboard::KeyState::Pressed) {
                ++pressed_events;
            } else if (event.state == picocalc::keyboard::KeyState::Released) {
                ++released_events;
            }
            printf("[PICOCALC][KEY] state=%u code=0x%02x\n",
                   static_cast<unsigned>(event.state),
                   event.key);
            printf("[PICOCALC][KEY][VERIFY] stage=event count=%lu state=%s state_code=%u "
                   "code=0x%02x pressed_count=%lu released_count=%lu\n",
                   static_cast<unsigned long>(key_events),
                   key_state_name(event.state),
                   static_cast<unsigned>(event.state),
                   event.key,
                   static_cast<unsigned long>(pressed_events),
                   static_cast<unsigned long>(released_events));
            picocalc::display::fill_rect(
                16,
                248,
                288,
                32,
                static_cast<uint16_t>(0x001f ^ (event.key << 8)));
        }
#if !PICOCALC_AUDIO_REFERENCE_TONE
        service_audio_stream();
#endif
        sleep_ms(10);
    }
}
